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

# ── 配置区：新增预设无需改代码 ──
_COMMON_DELIVERY_RE = re.compile(r"^(0[0-9]|1[01])_")
_TIMELINE_NAME_RE = re.compile(r"^\d{2,3}$")
_PLACEHOLDER_NAME = "项目名称"
_EXPORT_SUFFIX = "_交付版本合集"
_EXPORT_SUBDIR = "11_导出"

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "shared"))
from fusionscript_loader import bmd


def _derive_project_name(project_dir):
    if not project_dir:
        return ""
    folder = os.path.basename(project_dir.rstrip("/"))
    m = re.match(r"^\d{8}_(.*)", folder)
    return m.group(1) if m else folder


def _get_export_info(project):
    try:
        root = project.GetSetting("workingDirectory")
    except Exception:
        root = ""
    if not root:
        return "", _PLACEHOLDER_NAME
    return root, _derive_project_name(root) or _PLACEHOLDER_NAME


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
        if props.get("Type", "") != "Timeline":
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

    # 预设分组（纯展示，不影响选择逻辑）
    delivery_group = [n for n in preset_names if _COMMON_DELIVERY_RE.match(n) and int(n[:2]) <= 6]
    split_group = [n for n in preset_names if _COMMON_DELIVERY_RE.match(n) and 7 <= int(n[:2]) <= 9]
    special_group = [n for n in preset_names if _COMMON_DELIVERY_RE.match(n) and (n.startswith("00_") or int(n[:2]) >= 11)]
    custom_group = [n for n in preset_names if not _COMMON_DELIVERY_RE.match(n)]
    ordered_presets = delivery_group + split_group + special_group + custom_group

    export_root, project_name = _get_export_info(project)

    # ── 生成预创建 CheckBox（达芬奇 UIManager 不支持运行时 AddWidget）──
    # 时间线 CheckBox
    tl_cb_ids = []
    tl_cb_map = {}  # id → name
    tl_widgets = []
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
    has_delivery = bool(delivery_group)
    has_split = bool(split_group)
    need_sep1 = has_delivery and (has_split or special_group or custom_group)

    for i, name in enumerate(delivery_group):
        cb_id = f"PRCB_{i:02d}"
        pr_cb_ids.append(cb_id)
        pr_cb_map[cb_id] = name
        pr_widgets.append(_make_checkbox(ui, cb_id, name, True, True))
    idx = len(delivery_group)
    if need_sep1:
        pr_widgets.append(_sep_label("声轨分离"))
    for name in split_group:
        cb_id = f"PRCB_{idx:02d}"
        idx += 1
        pr_cb_ids.append(cb_id)
        pr_cb_map[cb_id] = name
        pr_widgets.append(_make_checkbox(ui, cb_id, name, True, True))
    if special_group:
        pr_widgets.append(_sep_label("特殊"))
    for name in special_group:
        cb_id = f"PRCB_{idx:02d}"
        idx += 1
        pr_cb_ids.append(cb_id)
        pr_cb_map[cb_id] = name
        pr_widgets.append(_make_checkbox(ui, cb_id, name, True, True))
    if custom_group:
        pr_widgets.append(_sep_label("自定义"))
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
        "WindowTitle": "渲染队列批量提交",
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
        tl_checked = [tl_cb_map[cid] for cid in _read_checked(tl_cb_ids) if not cid.startswith("TLSKP_")]
        pr_checked = [pr_cb_map[cid] for cid in _read_checked(pr_cb_ids)]

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
