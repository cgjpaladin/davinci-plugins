#!/usr/bin/env python3
"""渲染队列批量提交工具。

从当前媒体池文件夹自动发现时间线，选择渲染预设，批量添加到渲染队列。
适合紧接在「交付自检」检查通过后使用。

扩展：预设列表动态读取，不硬编码。加预设改数据库即可，工具自动适配。
"""

import re
import os
import sys
import time
from datetime import datetime

# ── 配置区：新增预设无需改代码 ──
# 任意 `xx_` 开头的预设都算「常用交付合集」
_COMMON_DELIVERY_RE = re.compile(r"^\d{2}_")
# 分组映射：根据编号自动归类
def _preset_group_index(name):
    """返回 0=交付版, 1=音频分离, 2=特殊, 3=自定义。"""
    m = re.match(r"^(\d{2})_", name)
    if not m:
        return 3  # 自定义
    n = int(m.group(1))
    if 1 <= n <= 6:
        return 0  # 交付版（视频）
    if 7 <= n <= 9:
        return 1  # 音频分离（LPCM）
    return 2  # 特殊（00、10+）

_TIMELINE_NAME_RE = re.compile(r"^\d{2,3}$")
_PLACEHOLDER_NAME = "项目名称"
_EXPORT_SUFFIX = "_交付版本合集"
_EXPORT_SUBDIR = "11_导出"

# ── 版本 ──
try:
    from config import version_string, PRODUCT_NAME
except ImportError:
    version_string = lambda: "dev"
    PRODUCT_NAME = "渲染队列工具"

# ── 日志 ──
_LOG_DIR = os.path.expanduser("~/达芬奇插件工坊/logs")
try:
    os.makedirs(_LOG_DIR, exist_ok=True)
except Exception:
    _LOG_DIR = "/tmp"


def _log(msg):
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{stamp}] {msg}"
    try:
        with open(os.path.join(_LOG_DIR, "render_batch.log"), "a") as f:
            f.write(line + "\n")
    except Exception:
        pass
    print(line)

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "shared"))
from fusionscript_loader import bmd


def _derive_project_name(project_dir):
    if not project_dir:
        return ""
    folder = os.path.basename(project_dir.rstrip("/"))
    m = re.match(r"^\d{8}_(.*)", folder)
    return m.group(1) if m else folder


def _get_project_root_from_clip(project):
    """从一个时间线的第一个视频素材路径推导项目根。"""
    try:
        count = project.GetTimelineCount()
        for i in range(1, count + 1):
            t = project.GetTimelineByIndex(i)
            items = t.GetItemListInTrack("video", 1) or []
            for it in items:
                mp = it.GetMediaPoolItem()
                if mp:
                    path = mp.GetClipProperty().get("File Path", "")
                    if path:
                        return path
    except Exception:
        pass
    return ""


def _get_export_info(project):
    """获取导出基路径 + 项目名。从素材路径推导。"""
    clip_path = _get_project_root_from_clip(project)
    if clip_path:
        # 往上找匹配日期前缀的文件夹（yyyyMMdd_xxx）
        p = os.path.abspath(clip_path)
        while p and p != "/":
            basename = os.path.basename(p)
            if re.match(r"^\d{8}_", basename):
                return p, _derive_project_name(p)
            p = os.path.dirname(p)
    return "", _PLACEHOLDER_NAME


def _get_folder_timelines(project):
    try:
        folder = project.GetMediaPool().GetCurrentFolder()
        if not folder:
            return []
        clips = folder.GetClipList()
    except Exception:
        return []
    seen = set()
    names = []
    for clip in clips:
        try:
            props = clip.GetClipProperty()
        except Exception:
            continue
        clip_type = props.get("Type", "")
        if clip_type not in ("Timeline", "时间线"):
            continue
        name = clip.GetName()
        if name not in seen:
            seen.add(name)
            names.append(name)
    names.sort(key=lambda n: int(n) if n.isdigit() else float("inf"))
    return names


# ═══════════════════════════════════════════════════════════
# 主窗口
# ═══════════════════════════════════════════════════════════

def _make_checkbox(ui, cb_id, label, checked=True, enabled=True):
    """生成 CheckBox widget。"""
    return ui.CheckBox(cb_id, {
        "Text": label,
        "Checked": checked,
        "Enabled": enabled,
    })


def show():
    resolve = bmd.scriptapp("Resolve")
    if not resolve:
        print("达芬奇未运行")
        return
    fu = bmd.scriptapp("Fusion")
    if not fu:
        print("Fusion 不可用")
        return
    ui = fu.UIManager
    pm = resolve.GetProjectManager()
    project = pm.GetCurrentProject()
    if not project:
        print("未打开项目")
        return

    # ── 数据收集 ──
    timeline_names = _get_folder_timelines(project)
    compliant_tls = [n for n in timeline_names if _TIMELINE_NAME_RE.match(n)]
    skipped_tls = [n for n in timeline_names if n not in set(compliant_tls)]

    preset_names = project.GetRenderPresetList()
    if not preset_names:
        print("项目没有渲染预设")
        return

    # 预设按编号自然排序：0x_ 视频文件, 7-9_ 音频文件, 其余放后面
    video_group = [n for n in preset_names if _COMMON_DELIVERY_RE.match(n) and 1 <= int(n[:2]) <= 6]
    audio_group = [n for n in preset_names if _COMMON_DELIVERY_RE.match(n) and 7 <= int(n[:2]) <= 9]
    other_numbered = [n for n in preset_names if _COMMON_DELIVERY_RE.match(n) and n not in set(video_group + audio_group)]
    custom_group = [n for n in preset_names if not _COMMON_DELIVERY_RE.match(n)]
    ordered_presets = video_group + audio_group + other_numbered + custom_group

    export_root, project_name = _get_export_info(project)

    # ── 生成预创建 CheckBox（达芬奇 UIManager 不支持运行时 AddWidget）──
    # 时间线 CheckBox
    tl_cb_ids = []
    tl_cb_map = {}  # id → name
    tl_widgets = []
    if not compliant_tls and not skipped_tls:
        tl_widgets.append(ui.Label("TLNone", {"Text": "当前文件夹无时间线"}))
    else:
        for i, name in enumerate(compliant_tls):
            cb_id = f"TLCB_{i}"
            tl_cb_ids.append(cb_id)
            tl_cb_map[cb_id] = name
            tl_widgets.append(_make_checkbox(ui, cb_id, name, True, True))
        for i, name in enumerate(skipped_tls):
            cb_id = f"TLSKP_{i}"
            tl_cb_ids.append(cb_id)
            tl_cb_map[cb_id] = f"{name} (不合规)"
            tl_widgets.append(_make_checkbox(ui, cb_id, f"{name} (不合规)", False, False))

    # 分隔线 Label（用 Label 做视觉分隔）
    def _sep_label(text):
        return ui.Label(f"PRSEP_{text}", {"Text": f"── {text} ──", "Weight": 0})

    # 预设 CheckBox
    pr_cb_ids = []
    pr_cb_map = {}
    pr_widgets = []
    has_video = bool(video_group)
    has_audio = bool(audio_group)
    need_sep = has_video and (has_audio or other_numbered or custom_group)

    for i, name in enumerate(video_group):
        cb_id = f"PRCB_{i:02d}"
        pr_cb_ids.append(cb_id)
        pr_cb_map[cb_id] = name
        pr_widgets.append(_make_checkbox(ui, cb_id, name, True, True))
    idx = len(video_group)
    if need_sep:
        pr_widgets.append(_sep_label("音频"))
    for name in audio_group:
        cb_id = f"PRCB_{idx:02d}"
        idx += 1
        pr_cb_ids.append(cb_id)
        pr_cb_map[cb_id] = name
        pr_widgets.append(_make_checkbox(ui, cb_id, name, True, True))
    if other_numbered:
        pr_widgets.append(_sep_label("其他"))
    for name in other_numbered:
        cb_id = f"PRCB_{idx:02d}"
        idx += 1
        pr_cb_ids.append(cb_id)
        pr_cb_map[cb_id] = name
        pr_widgets.append(_make_checkbox(ui, cb_id, name, True, True))
    if custom_group:
        pr_widgets.append(_sep_label("其他预设"))
    for name in custom_group:
        cb_id = f"PRCB_{idx:02d}"
        idx += 1
        pr_cb_ids.append(cb_id)
        pr_cb_map[cb_id] = name
        pr_widgets.append(_make_checkbox(ui, cb_id, name, False, True))

    # ── 构建窗口 ──
    win_elements = [
        ui.VGroup("RootV", [
            # ── 输出目录 ──
            ui.VGap(0.01),
            ui.HGroup("DirHeader", [
                ui.Label("DirTitle", {"Text": "输出目录", "Weight": 1}),
                ui.Label("DirStatus", {"Text": "目录不存在"}),
            ]),
            ui.Label("DirHint", {"Text": f"项目: {os.path.basename(export_root) if export_root else '?'}"}),
            ui.HGroup("DirBar", [
                ui.LineEdit("DirNameEdit", {"Text": project_name}),
                ui.Label("DirSuffix", {"Text": "_交付版本合集/"}),
            ]),
            ui.VGap(0.02),
            # ── 时间线 / 预设（并排）──
            ui.HGroup("MainPanels", [
                ui.VGroup("TLCol", [
                    ui.HGroup("TLTitleBar", [
                        ui.Label("TLTitle", {"Text": "时间线", "Weight": 1}),
                        ui.Label("TLCount", {"Text": f"{len(compliant_tls)} 合规 / {len(skipped_tls)} 跳过"}),
                    ]),
                    ui.VGap(0.005),
                    *tl_widgets,
                    ui.VGap(0.005),
                    ui.HGroup("TLBtns", [
                        ui.Button("TLSelectAll", {"Text": "全选合规"}),
                    ]),
                ]),
                ui.VGap(0.03),
                ui.VGroup("PRCol", [
                    ui.HGroup("PRTitleBar", [
                        ui.Label("PRTitle", {"Text": "渲染预设", "Weight": 1}),
                        ui.Label("PRCount", {"Text": f"{len([1 for n in ordered_presets if _COMMON_DELIVERY_RE.match(n)])}/{len(ordered_presets)} 已选"}),
                    ]),
                    ui.VGap(0.005),
                    ui.HGroup("PRQuick", [
                        ui.Button("PRCommon", {"Text": "常用交付合集"}),
                    ]),
                    ui.VGap(0.005),
                    *pr_widgets,
                ]),
            ]),
            ui.VGap(0.02),
            # ── 底部 ──
            ui.HGroup("Bottom", [
                ui.Label("Stats", {"Text": "", "Weight": 1}),
                ui.Button("Submit", {"Text": "加入渲染队列"}),
            ]),
            ui.VGap(0.01),
        ]),
    ]

    disp = bmd.UIDispatcher(ui)
    win = disp.AddWindow({
        "WindowTitle": f"{PRODUCT_NAME} v{version_string()}",
        "ID": "RenderBatchWin",
        "Geometry": [100, 100, 580, max(400, 140 + len(tl_widgets) * 22 + len(pr_widgets) * 22)],
    }, win_elements)
    win.RecalcLayout()

    items = win.GetItems()
    dir_edit = items["DirNameEdit"]

    # ── 统计更新 ──
    def _read_checked(ids):
        result = []
        for cid in ids:
            try:
                cb = items[cid]
                if cb and cb.Checked:
                    result.append(cid)
            except Exception:
                pass
        return result

    def _update_stats():
        tl_c = len(_read_checked(tl_cb_ids))
        pr_c = len(_read_checked(pr_cb_ids))
        items["Stats"].Text = f"{tl_c} x {pr_c} = {tl_c * pr_c} 个渲染任务"

    # ── 回调 ──
    def _on_tl_select_all(ev):
        for cid in tl_cb_ids:
            if cid.startswith("TLSKP_"):
                continue
            try:
                items[cid].Checked = True
            except Exception:
                pass
        _update_stats()

    def _on_pr_common(ev):
        for i, cid in enumerate(pr_cb_ids):
            name = pr_cb_map.get(cid, "")
            try:
                items[cid].Checked = bool(_COMMON_DELIVERY_RE.match(name))
            except Exception:
                pass
        _update_stats()

    def _on_submit(ev):
        _log(f"=== 开始提交渲染队列 (v{version_string()}) ===")
        _log(f"项目: {project.GetName()}, 数据库: {pm.GetCurrentDatabase().get('DbName','?')}")
        tl_checked = [tl_cb_map[cid] for cid in _read_checked(tl_cb_ids) if not cid.startswith("TLSKP_")]
        pr_checked = [pr_cb_map[cid] for cid in _read_checked(pr_cb_ids)]
        _log(f"选中时间线: {len(tl_checked)} 条, 预设: {len(pr_checked)} 个")

        if not tl_checked:
            disp.ShowMessage("提示", "没有选中合规时间线")
            return
        if not pr_checked:
            disp.ShowMessage("提示", "没有选中渲染预设")
            return

        proj_name = dir_edit.Text.strip()
        if not proj_name or proj_name == _PLACEHOLDER_NAME:
            disp.ShowMessage("提示", "请填写项目名称（占位名「项目名称」不可用）")
            return

        export_dir = os.path.join(export_root, _EXPORT_SUBDIR,
                                  f"{proj_name}{_EXPORT_SUFFIX}")
        if not os.path.isdir(export_dir):
            try:
                os.makedirs(export_dir, exist_ok=True)
            except Exception as e:
                disp.ShowMessage("错误", f"创建目录失败: {e}")
                return

        # 收集时间线对象
        tl_objs = {}
        for i in range(1, project.GetTimelineCount() + 1):
            try:
                t = project.GetTimelineByIndex(i)
                if t.GetName() in tl_checked:
                    tl_objs[t.GetName()] = t
            except Exception:
                continue

        failed = []
        success = 0
        for tl_name in sorted(tl_checked):
            t = tl_objs.get(tl_name)
            if not t:
                failed.append(tl_name)
                continue
            project.SetCurrentTimeline(t)
            for pr_name in pr_checked:
                try:
                    if not project.LoadRenderPreset(pr_name):
                        failed.append(f"{tl_name} → {pr_name}")
                        continue
                    project.SetRenderSettings({"TargetDir": export_dir})
                    jid = project.AddRenderJob()
                    if jid:
                        success += 1
                    else:
                        failed.append(f"{tl_name} → {pr_name}")
                except Exception as e:
                    failed.append(f"{tl_name} → {pr_name} ({e})")
                time.sleep(0.03)

        msg = f"成功添加 {success} 个渲染任务"
        if failed:
            msg += f"\n跳过 {len(failed)} 个: " + " ".join(failed[:10])
        _log(f"结果: 成功 {success}, 失败 {len(failed)}, 输出目录: {export_dir}")
        disp.ShowMessage("完成", msg)

    # ── 绑定 ──
    win.On.TLSelectAll.Clicked = _on_tl_select_all
    win.On.PRCommon.Clicked = _on_pr_common
    win.On.Submit.Clicked = _on_submit
    win.On.RenderBatchWin.Close = lambda ev: disp.ExitLoop()

    _update_stats()
    win.Show()
    disp.RunLoop()
    win.Hide()


if __name__ == "__main__":
    show()
