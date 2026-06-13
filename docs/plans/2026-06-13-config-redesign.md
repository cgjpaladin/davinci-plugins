# 配置页重构：独立授权区 + 分区 + 不关窗

> 设计已确认 | 2026-06-13

## 修改文件

`交付自检工具/ui.py`

## 布局

```
【授权管理】（独立区，不属于 CONFIG_SECTIONS）
  试用：⏳ 剩余 N 天 | ____-____-____ | [激活]
  已激活：✅ 已激活 | 永久授权 | [停用并释放授权]
  （操作结果提示）

─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─

【API 设置】
  DeepSeek / 飞书 App ID / 飞书 Secret

─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─

【脱机素材检测路径】
  [添加] [清空] 列表

─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─

【个人词典】
  [在 Finder 中定位] （右键 → WPS 打开）

─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─

                [保存] [关闭]
```

窗口 360×620

---

## Task 1: CONFIG_SECTIONS 去掉授权相关条目

删除 `activation_code` 和 `deactivate` 两条 dict。
`_do_save` 中授权相关分支（t == "activation_code" 大段 + _success_result 逻辑 + _activation_failed）全部删除。
`_build_activation_code` 和 `_build_deactivate` 两个函数保留但不再被 CONFIG_SECTIONS 驱动调用。

**验证**：编译通过；配置页不再显示激活码输入框和停用按钮

---

## Task 2: 新增 _build_separator() 和 _build_section_header() 辅助函数

```python
def _build_separator():
    return ui.Label({"Text": "─" * 48, "Weight": 0,
        "StyleSheet": "color:rgb(80,80,80);font-size:10px"})

def _build_section_header(text):
    return ui.Label({"Text": f"▸ {text}", "Weight": 0,
        "StyleSheet": "color:rgb(180,180,180);font-size:13px;font-weight:bold"})
```

**验证**：编译通过

---

## Task 3: 构建授权管理独立区域

在 `_show_config_dialog` 内、CONFIG_SECTIONS 循环之前，构建授权区：

所有控件双份（试用+已激活），初始根据 `is_activated` 设置 Visible。

**试用控件（id 加 trial_ 前缀避免重名）：**
- `cfg_trial_status`: Label → "⏳ 试用剩余 N 天"
- `cfg_trial_code_1/2/3`: 三个 LineEdit（同原 cfg_activation_1/2/3）
- `cfg_trial_activate_btn`: Button → "激活"
- `cfg_trial_hint`: Label → 激活结果反馈（初始空）

**已激活控件（id 不变）：**
- `cfg_auth_activated_label`: Label → "✅ 已激活 | 永久授权"
- `cfg_deactivate_btn`: Button → "停用并释放授权"（复用原 ID）
- `cfg_auth_hint`: Label → 停用结果反馈（初始空）

初始状态：`is_trial → 显示试用组隐藏已激活组；else → 反向`

**验证**：编译通过；打开配置 → 根据激活状态显示对应授权区

---

## Task 4: 激活按钮回调（_do_activate）

独立函数，不依赖 _do_save：

```python
def _do_activate(ev):
    c1 = cfg["cfg_trial_code_1"].Text.strip().upper()
    c2 = cfg["cfg_trial_code_2"].Text.strip().upper()
    c3 = cfg["cfg_trial_code_3"].Text.strip().upper()
    code = f"{c1}-{c2}-{c3}"
    if not (c1 and c2 and c3):
        cfg["cfg_trial_hint"].Text = "⚠ 请输入完整激活码"
        cfg["cfg_trial_hint"]["StyleSheet"] = "color:rgb(220,80,60);font-size:12px"
        return
    cfg["cfg_trial_hint"].Text = "⏳ 正在连接服务器…"
    cfg["cfg_trial_hint"]["StyleSheet"] = "color:rgb(220,160,40);font-size:12px"
    from shared.license import activate, load_credential
    c = load_credential()
    trial_save = 0
    if c and c.get("payload", {}).get("is_trial"):
        trial_save = max(0, c["payload"].get("expire_time", 0) - int(time.time()))
    ok, msg = activate(code)
    _action_log(f"🔑 激活: {'✅' if ok else '❌'} {msg}")
    if ok:
        # 持久化
        _keys = _load_api_keys(); _keys["activation_code"] = code
        if trial_save: _keys["trial_remain_secs"] = str(trial_save)
        _save_api_keys(_keys)
        # 主窗口
        _ai_allowed = True
        itm[BTN_AI_TYPO].Text = "字幕检测"; itm[BTN_AI_TYPO].Enabled = True
        itm[TRIAL_LB].Text = "已激活 ✓"; itm[HINT_LB].Text = ""
        # 切换配置页授权区
        cfg["cfg_trial_status"].Visible = False
        for _id in ("cfg_trial_code_1","cfg_trial_code_2","cfg_trial_code_3","cfg_trial_activate_btn"):
            try: cfg[_id].Visible = False
            except: pass
        cfg["cfg_auth_activated_label"].Visible = True
        cfg["cfg_deactivate_btn"].Visible = True
        cfg["cfg_deactivate_btn"].Enabled = True
        cfg["cfg_deactivate_btn"].Text = "停用并释放授权"
        cfg["cfg_trial_hint"].Text = ""
    else:
        cfg["cfg_trial_hint"].Text = f"⚠ {msg}"
        cfg["cfg_trial_hint"]["StyleSheet"] = "color:rgb(220,80,60);font-size:12px"
```

**验证**：试用状态 → 输入码 → 点「激活」→ 授权区切换为已激活 → 主窗口同步

---

## Task 5: 停用按钮回调（_do_deactivate）重写

基于现有 _do_deactivate 但结果不关窗，切换授权区：

```python
def _do_deactivate(ev):
    cfg["cfg_auth_hint"].Text = "⏳ 正在连接服务器…"
    cfg["cfg_auth_hint"]["StyleSheet"] = "color:rgb(220,160,40);font-size:12px"
    from shared.license import deactivate, load_credential
    ok, msg = deactivate()
    _action_log(f"🔓 停用: {'✅' if ok else '❌'} {msg}")
    if ok:
        _ai_allowed = False
        _keys = _load_api_keys()
        if _keys.get("activation_code"): del _keys["activation_code"]; _save_api_keys(_keys)
        itm[BTN_AI_TYPO].Text = "字幕检测(需激活码)"; itm[BTN_AI_TYPO].Enabled = False
        itm[TRIAL_LB].Text = ""; itm[HINT_LB].Text = "授权已停用"
        # 切换授权区为试用
        cred = load_credential()
        p = cred.get("payload", {}) if cred else {}
        tsd = p.get("trial_start_date")
        if tsd:
            from datetime import date as _dt
            d = max(0, 30 - (_dt.today() - _dt.fromordinal(tsd)).days)
            cfg["cfg_trial_status"].Text = f"⏳ 试用剩余 {d} 天"
        else:
            cfg["cfg_trial_status"].Text = "⏳ 试用剩余 — 天"
        cfg["cfg_trial_status"].Visible = True
        for _id in ("cfg_trial_code_1","cfg_trial_code_2","cfg_trial_code_3","cfg_trial_activate_btn"):
            try: cfg[_id].Visible = True
            except: pass
        cfg["cfg_auth_activated_label"].Visible = False
        cfg["cfg_deactivate_btn"].Visible = False
        cfg["cfg_trial_code_1"].Text = cfg["cfg_trial_code_2"].Text = cfg["cfg_trial_code_3"].Text = ""
        cfg["cfg_auth_hint"].Text = ""
    else:
        cfg["cfg_auth_hint"].Text = f"⚠ {msg}"
        cfg["cfg_auth_hint"]["StyleSheet"] = "color:rgb(220,80,60);font-size:12px"
```

**验证**：已激活 → 点「停用」→ 授权区切换为试用 → 主窗口同步

---

## Task 6: 拼装布局 + 分隔符

在 `_show_config_dialog` 中，按以下顺序拼装 VGroup：

1. `_build_section_header("授权管理")`
2. 授权区控件（双份）
3. `_build_separator()`
4. CONFIG_SECTIONS 各区域，每个区域前后加 header + separator
   - API 设置: header("API 设置") + api_key 控件 + separator
   - 脱机素材检测路径: header + smb_paths 控件 + separator
   - 个人词典: header + censor_personal 控件 + separator
5. 底部按钮 HGroup（保存 + 关闭）

窗口尺寸：`[360, 620]`（适配四区）

**验证**：编译通过；打开配置 → 见分区 + 分隔线

---

## Task 7: 全链路冒烟

1. 试用 → 打开配置 → 见试用授权区 → 输码点激活 → 授权区切换已激活 → 点关闭 → 重启 → 已激活 ✓
2. 已激活 → 打开配置 → 见已激活区 → 点停用 → 授权区切换试用 → 点关闭 → 重启 → 试用 ✓
3. 改 API Key → 点保存 → 重启 → Key 持久
4. 输错码 → 点激活 → 红字提示 → 可重试
5. 停用失败 → 红字提示
