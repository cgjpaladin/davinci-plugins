# 🔬 达芬奇插件工坊 — UX 架构审计 & 重设计

> **审计日期**: 2026-05-24  
> **审计范围**: AI去字幕 v1.11.3-dev / 交付自检工具 v2.0.13-dev / 批量命名工具  
> **运行环境**: DaVinci Resolve Fusion UIManager (Qt-based, 非Web CSS)  
> **部署方式**: SMB 共享 / 灰度 roll-out / 独立 Python 进程窗口

---

## 目录

1. [UX 断点地图](#1-ux-断点地图)
2. [统一信息架构](#2-统一信息架构)
3. [CSS 设计系统](#3-css-设计系统)
4. [通用交互组件规范](#4-通用交互组件规范)
5. [响应式策略](#5-响应式策略)
6. [开发者交付清单](#6-开发者交付清单)

---

## 1. UX 断点地图

### 1.1 宏观断点全景

```
                        ┌─────────────────────────────┐
                        │   达芬奇 Workspace → Scripts  │
                        │   三个独立入口，无序排列       │
                        └──┬──────────┬──────────┬─────┘
                           │          │          │
                    ┌──────▼──┐ ┌────▼─────┐ ┌─▼──────────┐
                    │AI去字幕  │ │交付自检  │ │批量命名工具  │
                    │独立窗口  │ │独立窗口  │ │pywebview窗口│
                    └─────────┘ └──────────┘ └────────────┘
                    
                    问题：三个产品之间零关联感知
                    用户无法知道当前集群还有哪些工具可用
                    关闭 = 消失，无状态恢复
```

### 1.2 逐产品断点详细分析

#### 🔴 AI去字幕 (v1.11.3-dev) — 5 个关键断点

| # | 断点位置 | 严重度 | 症状 | 根因 | 用户影响 |
|---|---------|--------|------|------|----------|
| 1 | **进度条 90% 卡死** | 🔴 高 | 进度条到 90% 停住不动，预估时间归零但实际还在跑 | `_update_countdown()` 中 `est_ratio = min(0.95, elapsed / _t_estimated)` 硬上限 95%，且 `_t_estimated` 公式 `Σclip×2.3+60` 在短片段批量时严重低估 | 用户焦虑：以为卡死了，实际还在处理 |
| 2 | **SMB 断连提示隐晦** | 🟡 中 | 断开时只在日志区打印一行 `⚠ SMB 已断开`，用户可能已经离开 | `_check_smb()` 返回 False 时没有视觉阻断层，UI 控件只是静默失效 | 用户困惑：按钮变灰不知道为什么 |
| 3 | **引擎切换认知负担** | 🟡 中 | 引擎 ComboBox (260px 宽) 放在 Row2 最右端，标签仅"引擎"二字 | 新加功能，未提供引擎说明 tooltip、没标明积分差异、没默认推荐标记 | 非技术用户不知道选哪个引擎 |
| 4 | **Row1/Row2 功能过载** | 🟡 中 | Row1 放 4 个控件（确认+选择+路径+OSS余额），Row2 放 10 个控件 | 880px 宽窗口勉强容纳，14 寸笔记本（1440×900）窗口可能截断 | 小屏幕用户需要手动调窗口或横向滚动 |
| 5 | **窗口关闭即丢失进度** | 🔴 高 | 关闭窗口 → `_cleanup_done` → `disp.ExitLoop()` → 进程终止 | 没有"处理中关闭确认"弹窗，`_state["stop"]=True` 后只等 0.3 秒 | 误触关闭 = 前功尽弃 + 可能残留脏状态 |

#### 🔴 交付自检工具 (v2.0.13-dev) — 4 个关键断点

| # | 断点位置 | 严重度 | 症状 | 根因 | 用户影响 |
|---|---------|--------|------|------|----------|
| 1 | **UIManager Tree 无法交互勾选** | 🔴 高 | 右侧结果 Tree 只能看不能操作（无 SetItemChecked） | DaVinci Fusion UIManager 的 Tree 控件无复选框绑定 API | 用户看到问题列表但无法逐条标记"已处理" |
| 2 | **无 ScrollArea — 列表截断** | 🟡 中 | 检查结果超过 ~15 行时，Tree 控件内滚动区域受限 | UIManager 没有 ScrollArea 控件，依赖 Tree 自身滚动 | 20 项全部检查时结果可能溢出可视区 |
| 3 | **bare except: pass 吞错误** | 🔴 高 | `except Exception: pass` 在多处出现（[ui.py:428](交付自检工具/gray/ui.py:428)） | 防御性编程过度，真实错误被静默 | 排查问题无从下手，日志空白 |
| 4 | **检查进度无反馈** | 🟡 中 | `_start_check()` 同步执行，16 项检查全程无进度条 | 检查是同步 for 循环，没有分段回调 | 检查时间长时用户不知道是否卡死 |

#### 🟡 批量命名工具 (独立 pywebview) — 2 个关键断点

| # | 断点位置 | 严重度 | 症状 |
|---|---------|--------|------|
| 1 | **两个视图切换无状态保持** | 🟡 中 | app_table.js ↔ app.js 切换时丢失排序/筛选状态 |
| 2 | **与达芬奇生态完全隔离** | 🟢 低 | 无 launcher_router 集成，手动启动 |

### 1.3 全局断点 — 系统级问题

| # | 断点 | 影响面 | 描述 |
|---|------|--------|------|
| G1 | **无统一入口/启动器** | 全部 | 用户在达芬奇 Scripts 菜单看到 3 个独立条目，没有品牌归属感 |
| G2 | **窗口各自为政** | 全部 | 每个工具独立 PID 锁、独立窗口标题、独立版本号格式 |
| G3 | **部署一致性风险** | 全部 | bump_version.sh 只 bump AI去字幕；gray.json 每个产品一份；push_all.sh 无回滚 |
| G4 | **主题系统仅暗色** | 全部 | theme.json 只定义一套暗色值，无 `data-theme` 切换、无 light 模式、无系统跟随 |
| G5 | **品牌感知薄弱** | 全部 | 品牌名仅在底部状态栏出现"裁缝老师的达芬奇插件工坊 ✂️"，窗口标题只有"AI去字幕"/"交付自检" |

---

## 2. 统一信息架构

### 2.1 产品关系模型

```
┌─────────────────────────────────────────────────────────┐
│              裁缝老师的达芬奇插件工坊 ✂️                    │
│              DaVinci Plugin Workshop                     │
├─────────────────────────────────────────────────────────┤
│                                                         │
│   ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  │
│   │  🎬 AI 处理   │  │  🔍 质量检查  │  │  🛠️ 工具集   │  │
│   │              │  │              │  │              │  │
│   │ • AI去字幕    │  │ • 交付自检    │  │ • 批量命名    │  │
│   │ • AI换口型※   │  │              │  │ • TTS语音     │  │
│   │ • AI语音克隆※ │  │              │  │ • 字幕编辑器  │  │
│   │ • AI超分辨率※ │  │              │  │ • 批量IO渲染  │  │
│   │ • AI加字幕※   │  │              │  │              │  │
│   └──────────────┘  └──────────────┘  └──────────────┘  │
│                                                         │
│   ※ = planned/stub (product_registry.py 已注册)         │
└─────────────────────────────────────────────────────────┘
```

### 2.2 推荐入口策略 — 三阶段演进

#### Phase A (现在可做): 统一 launcher_router

当前已存在 `launcher_router.py`，但只有 AI去字幕 在用。直接把交付自检也接入：

```python
# 达芬奇 Scripts/Edit/ 下只需部署两个 .py 文件：
#   达芬奇插件工坊.py   → import launcher_router; launcher_router.route("AI去字幕", "stable_ui")
#   交付自检.py         → import launcher_router; launcher_router.route("交付自检工具", "ui")
```

**立即可得收益**：统一路由逻辑、Dry-run 自检、Dev/Gray/SMB 自动切换。

#### Phase B (1-2周): 轻量 Hub 启动面板

```
┌──────────────────────────────────────┐
│  裁缝老师的达芬奇插件工坊 ✂️         │
│  ─────────────────────────────────   │
│                                      │
│  🎬 AI 处理                          │
│  ┌─────────────────────────────────┐ │
│  │ AI去字幕  v1.11.3  [启动]       │ │
│  │ 一键去除短剧字幕，鬼手/无痕AI    │ │
│  ├─────────────────────────────────┤ │
│  │ AI换口型  即将推出              │ │
│  └─────────────────────────────────┘ │
│                                      │
│  🔍 质量检查                         │
│  ┌─────────────────────────────────┐ │
│  │ 交付自检  v2.0.13  [启动]       │ │
│  │ 20项时间线交付前自检             │ │
│  └─────────────────────────────────┘ │
│                                      │
│  🛠️ 工具集                           │
│  ┌─────────────────────────────────┐ │
│  │ 批量命名工具  [启动]            │ │
│  │ TTS语音工具  [启动]             │ │
│  └─────────────────────────────────┘ │
│                                      │
│  ─────────────────────────────────   │
│  ⚙ 设置  |  📊 OSS用量  |  🔄 检查更新 │
└──────────────────────────────────────┘
```

**实现成本**：一个 400 行 UIManager 窗口 + product_registry.py 驱动菜单。

#### Phase C (未来): 完全统一

- 批量命名工具 pywebview → 迁移到 UIManager（统一窗口管理）
- 加入插件市场/安装器
- 统一偏好设置面板

### 2.3 导航层级

```
Level 0: 达芬奇菜单 "Scripts → 达芬奇插件工坊"（单一入口）
Level 1: Hub 面板（产品分类卡片）
Level 2: 产品窗口（当前 AI去字幕 / 交付自检 独立窗口）
Level 3: 配置弹窗（各产品独立配置对话框）
```

### 2.4 窗口管理规范

| 属性 | 规范 | 当前状态 |
|------|------|----------|
| 窗口标题格式 | `{产品名} — 达芬奇插件工坊` | ❌ 只有产品名 |
| 窗口 ID 命名空间 | `com.myjc.{product_id}` | ✅ 已规范 |
| 置顶策略 | `WindowStaysOnTopHint` | ✅ 已统一 |
| 最小尺寸 | 800×500 (14寸安全尺寸) | ⚠️ AI去字幕 880×560 略大 |
| PID 锁 | `.ui_instance.lock` | ⚠️ 仅 AI去字幕 有 |
| 关闭保护 | 处理中弹窗确认 | ❌ 无 |

---

## 3. CSS 设计系统

> **⚠️ 关键约束**: 这些工具运行在 DaVinci Resolve Fusion UIManager 中。UIManager 基于 Qt 的 `StyleSheet` 属性，**不是 Web CSS**。以下设计系统同时提供：
> - **UIManager 映射**: 精确的 Qt 样式字符串
> - **Web 等价**: 用于批量命名工具 (pywebview) 的 CSS 等价声明
> - **theme.json 扩展**: shared/ui/theme.json 的结构化 token 定义

### 3.1 当前 theme.json 评估

```jsonc
// 当前: shared/ui/theme.json — 只有一套暗色，无主题切换
{
  "colors": {
    "bg": "#151515",       // → 太暗，DaVinci 默认背景是 #1a1a1a
    "surface": "#1e1e1e",  // → 可用
    "accent": "#e8870a",   // → 橙色，但 UI 中用蓝色 #3278DC 做主按钮
    "text": "#c0c0c0"      // → 偏暗，对比度勉强 AA
    // ❌ 缺少: light 主题、语义色、状态色
  }
}
```

### 3.2 重设计: 完整 Design Token 系统

```jsonc
{
  "_meta": {
    "version": "2.0",
    "description": "达芬奇插件工坊 — 统一设计令牌 (UIManager + pywebview 通用)",
    "theme_support": ["dark", "light", "system"],
    "default_theme": "system"
  },

  // ═══ 色彩系统 ═══
  "colors": {
    // ── 表面层级（bg 最深 → surface → surface2 → surface3 最浅）──
    "dark": {
      "bg":           "#1a1a1a",  // 页面背景（匹配 DaVinci 原生）
      "surface":      "#242424",  // 卡片/分组背景
      "surface2":     "#2d2d2d",  // 输入框/TextEdit 背景
      "surface3":     "#363636",  // hover 态
      "border":       "#3d3d3d",  // 默认边框
      "border_focus": "#5a5a5a",  // 聚焦边框
      "text":         "#d4d4d4",  // 正文（提升对比度 AA→AAA）
      "text_dim":     "#888888",  // 辅助文字
      "text_inverse": "#1a1a1a",  // 反色（用于亮底深字）
      
      // 语义色
      "accent":       "#4a90d9",  // 主色（统一为蓝，当前代码用 #3278DC）
      "accent_hover": "#5da0e5",
      "accent_dim":   "#2a5a8a",
      "success":      "#4caf50",  // 绿色（通过）
      "warning":      "#f5a623",  // 橙黄（警告）
      "error":        "#e53935",  // 红色（失败/停止）
      "info":         "#29b6f6",  // 信息蓝
      
      // 按钮专用
      "btn_default_bg":    "#3a3a3a",
      "btn_default_hover": "#484848",
      "btn_primary_bg":    "#3278dc",
      "btn_primary_hover": "#4288ec",
      "btn_danger_bg":     "#c83232",
      "btn_danger_hover":  "#dc4242",
      "btn_disabled_text": "#646464"
    },
    
    "light": {
      "bg":           "#f5f5f5",
      "surface":      "#ffffff",
      "surface2":     "#f0f0f0",
      "surface3":     "#e8e8e8",
      "border":       "#d0d0d0",
      "border_focus": "#a0a0a0",
      "text":         "#2a2a2a",
      "text_dim":     "#707070",
      "text_inverse": "#ffffff",
      
      "accent":       "#3278dc",
      "accent_hover": "#4288ec",
      "accent_dim":   "#a0c4f0",
      "success":      "#388e3c",
      "warning":      "#f57c00",
      "error":        "#d32f2f",
      "info":         "#0288d1",
      
      "btn_default_bg":    "#e0e0e0",
      "btn_default_hover": "#d0d0d0",
      "btn_primary_bg":    "#3278dc",
      "btn_primary_hover": "#4288ec",
      "btn_danger_bg":     "#d32f2f",
      "btn_danger_hover":  "#e53935",
      "btn_disabled_text": "#a0a0a0"
    }
  },

  // ═══ 字体系统 ═══
  "typography": {
    "family": {
      "ui":   ".AppleSystemUIFont",        // macOS 系统字体 (UIManager)
      "mono": "Menlo, monospace",          // 等宽（日志/时码）
      "web":  "system-ui, -apple-system, sans-serif"  // pywebview
    },
    "size": {
      "xs":   "10px",  // 底部状态、版本号
      "sm":   "11px",  // 辅助标签
      "base": "12px",  // 正文字体 ← 从当前 10px 提升
      "md":   "13px",  // 小标题/强调
      "lg":   "15px",  // 分组标题
      "xl":   "18px"   // 窗口标题（配置弹窗用）
    },
    "weight": {
      "normal": "400",
      "medium": "500",
      "bold":   "700"
    }
  },

  // ═══ 间距系统 (4px 基准) ═══
  "spacing": {
    "xs":  "2px",
    "sm":  "4px",
    "md":  "6px",
    "base":"8px",
    "lg":  "12px",
    "xl":  "16px",
    "2xl": "24px"
  },

  // ═══ 圆角 ═══
  "radius": {
    "sm": "3px",
    "md": "4px",
    "lg": "6px",
    "pill": "12px"
  },

  // ═══ 控件尺寸 ═══
  "sizing": {
    "btn_height":     "28px",
    "input_height":   "24px",
    "combo_height":   "24px",
    "progress_height":"8px",
    "row_gap":        "8px",    // HGroup 默认间距
    "section_gap":    "4px"     // VGroup 节间距
  },

  // ═══ 状态透明度 ═══
  "opacity": {
    "disabled": 0.45,
    "hover":    0.85,
    "muted":    0.60
  }
}
```

### 3.3 UIManager Qt Stylesheet 映射表

| Design Token | Qt StyleSheet 片段 | 使用位置 |
|-------------|-------------------|---------|
| `colors.dark.bg` | `background-color: #1a1a1a` | 窗口背景 |
| `colors.dark.surface` | `background-color: #242424` | VGroup 分组背景 |
| `colors.dark.surface2` | `background-color: #2d2d2d` | TextEdit/LineEdit |
| `colors.dark.text` | `color: #d4d4d4` | 正文 Label |
| `colors.dark.text_dim` | `color: #888888` | 辅助文字 |
| `colors.dark.accent` (按钮) | `background-color: #3278dc` | BTN_PRIMARY |
| `colors.dark.success` | `color: #4caf50` | 绿色状态 |
| `colors.dark.error` | `color: #e53935` | 错误/停止 |
| `colors.dark.warning` | `color: #f5a623` | 警告 |
| `typography.size.base` | `font-size: 12px` | 全局基础字号 |

**当前代码改进对照**:

```python
# 当前 (ui_widgets.py:85-106):
BTN_STYLE = (
    "QPushButton{max-height:28px;background-color:rgb(58,58,58);color:rgb(220,220,220);"
    "border:1px solid rgb(80,80,80);border-radius:4px;padding:4px 12px}"
    ...
)

# 建议: 从 theme.json 加载，统一管理
# 或者至少抽取为 shared/ui/styles.py 的常量
BTN_DEFAULT = _btn_style(TOKEN["btn_default_bg"], TOKEN["btn_default_hover"])
BTN_PRIMARY = _btn_style(TOKEN["btn_primary_bg"], TOKEN["btn_primary_hover"])
BTN_DANGER  = _btn_style(TOKEN["btn_danger_bg"], TOKEN["btn_danger_hover"])
```

### 3.4 主题切换实现约束

> **硬约束**: DaVinci UIManager 不支持 CSS `@media (prefers-color-scheme)` 也不支持 `data-theme` HTML 属性。主题切换必须在 Python 层面实现。

```python
# shared/ui/theme_manager.py (建议新增)

import json, os

class ThemeManager:
    """UIManager 主题管理器。
    硬约束：UIManager 不支持 CSS 变量和 data-theme，必须用 Python 字符串替换。
    """
    
    def __init__(self, token_path="shared/ui/theme.json"):
        self.tokens = self._load(token_path)
        self._current = self._detect()  # "dark" | "light"
    
    def _detect(self):
        """检测用户偏好：localStorage > 系统设置 > dark 默认"""
        # macOS: defaults read -g AppleInterfaceStyle
        try:
            import subprocess
            r = subprocess.run(["defaults", "read", "-g", "AppleInterfaceStyle"],
                             capture_output=True, text=True)
            if "Dark" in r.stdout:
                return "dark"
        except:
            pass
        return "dark"  # 视频编辑工具默认暗色
    
    def color(self, key):
        """获取当前主题的颜色值"""
        return self.tokens["colors"][self._current][key]
    
    def stylesheet(self, component):
        """返回当前主题下某组件的 Qt Stylesheet 字符串"""
        c = lambda k: self.color(k)
        sheets = {
            "btn_default": (
                f"QPushButton{{max-height:28px;background-color:{c('btn_default_bg')};"
                f"color:{c('text')};border:1px solid {c('border')};"
                f"border-radius:4px;padding:4px 12px}}"
                f"QPushButton:hover{{background-color:{c('btn_default_hover')}}}"
                f"QPushButton:disabled{{color:{c('btn_disabled_text')};background-color:{c('surface2')}}}"
            ),
            "btn_primary": (
                f"QPushButton{{max-height:28px;background-color:{c('btn_primary_bg')};"
                f"color:#ffffff;border:1px solid {c('accent_hover')};"
                f"border-radius:4px;padding:4px 12px;font-weight:bold}}"
                f"QPushButton:hover{{background-color:{c('btn_primary_hover')}}}"
                f"QPushButton:disabled{{color:{c('btn_disabled_text')};background-color:{c('surface2')}}}"
            ),
            "label_dim":  f"color:{c('text_dim')};font-size:12px",
            "label_body": f"color:{c('text')};font-size:12px",
            "text_edit":  f"color:{c('text')};background-color:{c('surface2')};border:1px solid {c('border')};border-radius:4px;padding:6px",
            "progress":   f"min-height:8px;max-height:8px;background-color:{c('success')};border-radius:3px",
        }
        return sheets.get(component, "")
    
    def toggle(self):
        self._current = "light" if self._current == "dark" else "dark"
        return self._current
```

### 3.5 图标/符号策略

由于 UIManager 不支持自定义图标字体，当前所有"图标"用 Unicode 符号：

| 用途 | 当前 | 建议 | 原因 |
|------|------|------|------|
| 通过 | `✅` | `✅` | 保持 |
| 失败 | `❌` | `❌` | 保持 |
| 警告 | `⚠` | `⚠` | 保持 |
| 处理中 | 无 | `⏳` | AI去字幕 已用 |
| 检查 | 无 | `🔍` | 扫描按钮前加 |
| 引擎 | 无 | `⚙` | 引擎选择前加 |
| 展开/折叠 | 无 | `▶` / `▼` | 分组折叠用 |

---

## 4. 通用交互组件规范

### 4.1 进度指示器 — 重设计

**当前问题**: AI去字幕用 Label+Resize 模拟进度条，硬上限 95%，时间估算公式不准。

**重设计规范**:

```
┌─────────────────────────────────────────────────┐
│  ⏳ AI 处理中 (3/8)  ·  还剩 1分23秒            │  ← PROJ_LB: 阶段+计数+倒计时
│  ████████████████░░░░░░░░░░░░░░  42%           │  ← 真实进度条（不要预估上限）
│  当前: EP01_g1_01_v01.mp4                       │  ← ST_LB: 当前处理文件
└─────────────────────────────────────────────────┘
```

**进度条状态机**:

```
[等待] → [扫描] → [上传] → [处理] → [下载] → [完成]
  │        │        │        │        │        │
 0%      5-15%   15-25%   25-85%  85-98%   100%
 
每个阶段:
  - 有明确百分比（来自 adapter 回调，非估算）
  - 有当前文件名
  - 倒计时用「剩余任务数 × 单任务平均耗时」动态更新
```

**UIManager 实现建议**:

```python
def progress_state(state: str, ratio: float, detail: str = ""):
    """统一进度更新（替代当前 _pg + _st 分离模式）"""
    states = {
        "waiting":   ("#888888", "准备中..."),
        "scanning":  ("#29b6f6", "扫描中..."),
        "uploading": ("#f5a623", "上传中..."),
        "processing":("#4a90d9", "AI 处理中..."),
        "downloading":("#7c4dff", "下载中..."),
        "complete":  ("#4caf50", "处理完成"),
        "error":     ("#e53935", "处理失败"),
        "stopped":   ("#f5a623", "已停止"),
    }
    color, label = states.get(state, ("#888888", state))
    # 更新进度条颜色 + 标签 + 百分比
    itm[PG_BAR].StyleSheet = f"min-height:8px;max-height:8px;background-color:{color};border-radius:3px"
    # ratio 来自 adapter 的真实回调，非时间估算
    _pg(ratio)
    _st(f"{label} {detail}")
```

**关键改进**:
1. 进度百分比来自 adapter 回调（真实处理进度），不再用时间估算
2. 进度条颜色随阶段变化（蓝→橙→绿），传递状态信息
3. 取消 95% 硬上限 —— 让进度条真实到达 100%

### 4.2 错误处理模式

**当前问题**: SMB 断开无视觉阻断，bare except: pass 吞错误。

**三级错误处理规范**:

```
Level 1: Toast 通知 (非阻塞)
  ┌──────────────────────────────┐
  │ ⚠ SMB 连接已断开，正在重连... │  ← 顶部浮动，3秒自动消失
  └──────────────────────────────┘

Level 2: 内联警告 (局部阻塞)
  ┌──────────────────────────────────────────┐
  │ ⚠ 无法连接达芬奇                          │
  │ 请确认 DaVinci Resolve 已启动并打开了项目   │
  │ [重试]                                   │
  └──────────────────────────────────────────┘

Level 3: 阻断式错误 (全局阻塞)
  ┌──────────────────────────────────────────┐
  │                                          │
  │        ⚠ SMB 共享已断开                   │
  │    插件需要访问 /Volumes/MYJC             │
  │                                          │
  │    请检查网络连接或联系管理员              │
  │                                          │
  │         [重试连接]   [退出]               │
  └──────────────────────────────────────────┘
```

**UIManager 实现**:

```python
# 替换当前 _check_smb() 返回 False 后的静默行为
def _smb_blocking_check():
    """SMB 阻断检查 — 断开时弹窗阻塞，不静默失败"""
    if os.path.exists(SMB_MOUNT):
        return True
    
    # 弹模态确认窗
    result = show_blocking_dialog(
        title="SMB 连接断开",
        message="插件需要访问共享存储 /Volumes/MYJC\n请检查网络连接后重试",
        buttons=["重试连接", "退出"],
        icon="warning"
    )
    if result == "重试连接":
        from macos_utils import mount_smb
        for _ in range(3):
            if mount_smb():
                return True
    return False
```

**日志规范**: 所有 `except Exception: pass` 改为 `except Exception as e: _event_log(f"[component] {e}")`

### 4.3 加载态 & 空状态

```
加载态:
  ┌──────────────────────────────────┐
  │  ⏳ 正在扫描时间线...              │
  │  ░░░░░░░░░░░░░░░░░░░░ (不确定)   │  ← 不确定进度条（来回扫描动画）
  └──────────────────────────────────┘

空状态 (无扫描结果):
  ┌──────────────────────────────────┐
  │                                  │
  │        📭 未找到橘色标记片段      │
  │                                  │
  │   当前时间线中没有橘色(Orange)     │
  │   标记的片段。请确认：             │
  │   • 片段已标记为橘色              │
  │   • 已选择正确的颜色筛选          │
  │                                  │
  │      [更改颜色]  [重新扫描]       │
  └──────────────────────────────────┘

空状态 (检查全通过):
  ┌──────────────────────────────────┐
  │                                  │
  │        ✅ 所有检查通过            │
  │                                  │
  │   20 项检查全部通过               │
  │   可以交付了！                    │
  │                                  │
  └──────────────────────────────────┘
```

### 4.4 按钮状态规范

```python
# shared/ui/button_states.py — 统一按钮状态管理

from enum import Enum

class BtnState(Enum):
    NORMAL    = "normal"      # 可点
    PRIMARY   = "primary"     # 主要操作（高亮蓝）
    DANGER    = "danger"      # 危险操作（红）
    DISABLED  = "disabled"    # 灰掉不可点
    LOADING   = "loading"     # 处理中，显示旋转/禁用
    SUCCESS   = "success"     # 完成态（绿，2秒后恢复）
    
# 使用:
# btn_set(BTN_START, BtnState.PRIMARY)
# btn_set(BTN_START, BtnState.LOADING, text="处理中...")
# btn_set(BTN_START, BtnState.SUCCESS, text="✅ 完成")
```

### 4.5 窗口关闭保护规范

```python
def on_close(ev):
    """关闭窗口 — 处理中进行确认"""
    if _state.get("processing"):
        # 弹确认窗
        from macos_utils import confirm
        if not confirm("正在处理中，确定要停止并关闭吗？\n已处理的内容将保留，未处理的需重新扫描。"):
            return  # 阻止关闭
        _state["stop"] = True
        time.sleep(0.5)  # 给处理线程 0.5 秒安全退出
    
    # 正常清理
    _cleanup()
    disp.ExitLoop()
```

---

## 5. 响应式策略

### 5.1 设备覆盖矩阵

| 设备 | 分辨率 | 窗口建议 | 布局策略 |
|------|--------|----------|----------|
| 14" MacBook Pro | 1440×900 * | 750×480 | 单列、最小间距 |
| 16" MacBook Pro | 1728×1117 | 880×560 | 当前默认 |
| 27" Studio Display | 2560×1440 | 950×650 | 展开日志区 |
| 双屏 (笔记本+外接) | 混合 | 跟随主屏 | 手动拖放 |

> \* 14" 默认缩放，达芬奇 UI 已占大量空间，剩余给插件窗口约 800×520

### 5.2 断点策略

```
Breakpoint 1: 窗口宽度 < 780px → Compact
  - Row1 折叠: 路径标签换行
  - Row2 引擎选择隐藏（用默认引擎）
  - 按钮最小宽度 60px
  - 日志区 min-height: 60px

Breakpoint 2: 窗口宽度 780-950px → Normal (当前)
  - 当前布局不变
  - Row1/Row2 一行排完

Breakpoint 3: 窗口宽度 > 950px → Expanded
  - 引擎选择展开显示余额详情
  - 日志区增大 min-height: 150px
  - 进度条显示更多详情
```

### 5.3 UIManager 响应式实现约束

> **硬约束**: UIManager 没有 CSS Media Queries。响应式只能通过 `Resize` 事件 + 手动 `RecalcLayout` 实现。

```python
# 窗口 Resize 事件中检查宽度并切换布局模式
_last_width = 880

def on_resize(ev):
    global _last_width
    try:
        geo = dlg.GetGeometry()
        w = geo[3] if geo.get(3, 0) > 0 else 880
        if (w < 780 and _last_width >= 780) or (w >= 780 and _last_width < 780):
            # 跨断点 → 重新计算布局
            _apply_responsive_layout(w)
        _last_width = w
    except:
        pass

def _apply_responsive_layout(width):
    if width < 780:
        # Compact: 隐藏引擎选择、缩小间距
        itm[API_CB].Visible = False
        # ... 调整其他控件
    else:
        itm[API_CB].Visible = True
    
    dlg.RecalcLayout()
```

**但实际操作建议**: 由于 UIManager 在动态调整控件显示/隐藏时容易布局错乱，**推荐固定两档**:

| 模式 | 触发 | 实现方式 |
|------|------|----------|
| Compact | 窗口初始化时检测屏幕 < 1680px 宽 | `Geomtry` 初始值不同 |
| Normal | 屏幕 ≥ 1680px | 当前默认值 |

--- 启动时一次性判断，避免运行时动态调整的复杂性。

### 5.4 窗口默认 Geometry

```python
# shared/ui/window_sizing.py

import subprocess

def get_screen_size():
    """获取主屏分辨率"""
    try:
        r = subprocess.run(
            ["osascript", "-e",
             "tell app \"Finder\" to get bounds of window of desktop"],
            capture_output=True, text=True
        )
        # 返回类似 "0, 0, 1728, 1117"
        parts = [int(x.strip()) for x in r.stdout.split(",")]
        return parts[2], parts[3]
    except:
        return 1920, 1080  # fallback

def default_geometry():
    sw, sh = get_screen_size()
    if sw <= 1440:
        return [50, 80, 750, 480]    # Compact
    elif sw <= 1920:
        return [100, 100, 880, 560]  # Normal
    else:
        return [200, 120, 950, 650]  # Expanded
```

---

## 6. 开发者交付清单

### 6.1 优先级 P0 — 本周修复（影响可用性）

| # | 任务 | 影响产品 | 工作量 | 描述 |
|---|------|---------|--------|------|
| 1 | **进度条重构** | AI去字幕 | 2h | 取消 95% 硬上限；adapter 回调真实百分比；颜色随阶段变化 |
| 2 | **SMB 阻断弹窗** | AI去字幕 | 1h | `_check_smb()` 失败时弹模态确认窗，不再静默 |
| 3 | **窗口关闭保护** | AI去字幕 | 0.5h | 处理中关闭弹确认 `macos_utils.confirm()` |
| 4 | **bare except 补日志** | 交付自检 | 1h | 所有 `except: pass` → `except Exception as e: _action_log(...)` |

### 6.2 优先级 P1 — 本月完成（体验一致性）

| # | 任务 | 影响产品 | 工作量 | 描述 |
|---|------|---------|--------|------|
| 5 | **theme.json v2 + ThemeManager** | 全部 | 3h | 扩展为 dark/light 双主题；新增 `shared/ui/theme_manager.py` |
| 6 | **统一窗口标题格式** | AI去字幕 + 交付自检 | 0.5h | `f"{PRODUCT_NAME} — 达芬奇插件工坊"` |
| 7 | **引擎选择优化** | AI去字幕 | 1h | 引擎选项加积分说明、推荐标记、默认值提示 |
| 8 | **交付自检进度反馈** | 交付自检 | 2h | `_start_check()` 改为分段回调，HINT_LB 显示当前检查项 |
| 9 | **launcher_router 统一接入** | 交付自检 | 1h | 交付自检接入 launcher_router，统一路由逻辑 |
| 10 | **PID 锁统一** | 交付自检 | 0.5h | 加入 `.ui_instance.lock` 防重复窗口 |

### 6.3 优先级 P2 — 下季度（架构升级）

| # | 任务 | 影响产品 | 工作量 | 描述 |
|---|------|---------|--------|------|
| 11 | **Hub 启动面板** | 全部 | 1d | 400 行 UIManager 窗口，product_registry.py 驱动 |
| 12 | **响应式窗口初始化** | AI去字幕 + 交付自检 | 2h | `default_geometry()` 根据屏幕尺寸选初始大小 |
| 13 | **样式常量提取** | AI去字幕 + 交付自检 | 3h | `BTN_STYLE` / `BTN_PRIMARY` / `LABEL_DIM` 抽取到 `shared/ui/styles.py` |
| 14 | **bump_version 统一** | 全部 | 1h | 修改 bump_version.sh 支持所有产品 |
| 15 | **gray/push 流程文档** | 全部 | 1h | 灰度发布 SOP 文档化 |

### 6.4 实现顺序依赖

```
P0 (本周):
  ① 进度条重构 ──→ ② SMB阻断弹窗 ──→ ③ 关闭保护
  ④ bare except补日志 (并行)

P1 (本月):
  ⑤ theme.json v2 ──→ ⑥ 窗口标题 ──→ ⑬ 样式常量提取
  ⑦ 引擎优化 (并行)
  ⑧ 交付自检进度 + ⑨ launcher_router + ⑩ PID锁 (并行)

P2 (下季度):
  ⑪ Hub面板 ──→ ⑫ 响应式 ──→ ⑭ bump统一 + ⑮ 文档
```

### 6.5 文件变更映射

| 新文件 | 路径 | 用途 |
|--------|------|------|
| `shared/ui/theme_manager.py` | 主题管理器 | 运行时读取 theme.json，输出 Qt Stylesheet |
| `shared/ui/styles.py` | 样式常量 | BTN_STYLE / BTN_PRIMARY 等统一管理 |
| `shared/ui/window_sizing.py` | 窗口尺寸 | `default_geometry()` 响应式初始化 |
| `shared/ui/toast.py` | Toast 通知 | 非阻塞浮动通知组件 |

| 修改文件 | 变更 |
|---------|------|
| `shared/ui/theme.json` | v1 → v2：添加 light 主题、语义色、组件 token |
| `AI去字幕/ui_widgets.py` | 进度条重构、样式常量引用、关闭保护 |
| `AI去字幕/stable_ui.py` | SMB 阻断弹窗、窗口标题格式 |
| `交付自检工具/gray/ui.py` | bare except 补日志、进度反馈、样式引用 |
| `交付自检工具/gray/launcher.py` | 接入 launcher_router |

---

## 附录 A: 进度条重构详细方案

> 当前 `_update_countdown()` 的问题链:
> 1. `_t_estimated = Σclip_duration × 2.3 + 60` → 公式偏差大
> 2. `est_ratio = min(0.95, elapsed / _t_estimated)` → 硬上限 95%
> 3. adapter 回调的 `ratio` 只在 `_st._last_ratio` 存着，没用于进度条上限

**重构后**:

```python
# 进度由两个源驱动，取 max：
#   Source A: adapter 真实回调 → _progress_real (0.0~1.0)
#   Source B: 时间估算 → min(0.90, elapsed / estimated)
#   最终显示: max(Source A, Source B)
#   关键改进: 取消 95% 硬上限，adapter 报 100% 就显示 100%

_progress_real = 0.0    # adapter 回调的真实进度
_progress_stage = ""     # 当前阶段: scanning/uploading/processing/downloading

def set_adapter_progress(ratio: float, stage: str = ""):
    """adapter 回调 — 真实进度"""
    global _progress_real, _progress_stage
    _progress_real = max(0.0, min(1.0, ratio))
    _progress_stage = stage or _progress_stage

def _update_countdown():
    """主线程轮询：显示 max(真实进度, 时间估算)"""
    now = time.time()
    elapsed = now - _t_start
    
    # 时间估算（保守，上限 90%）
    if _t_estimated > 0:
        est_ratio = min(0.90, elapsed / _t_estimated)
    else:
        est_ratio = 0.0
    
    # 真实进度优先
    ratio = max(_progress_real, est_ratio)
    
    # 不再硬上限！adapter 说 100% 就是 100%
    
    # 倒计时
    if _progress_real >= 1.0:
        time_str = "处理完成"
    elif ratio > 0 and _t_estimated > 0:
        remaining = max(0, _t_estimated - elapsed)
        mins, secs = divmod(int(remaining), 60)
        time_str = f"还剩 {mins}分{secs}秒" if mins else f"还剩 {secs}秒"
    else:
        time_str = "处理中..."
    
    # 阶段色
    stage_colors = {
        "scanning": "#29b6f6", "uploading": "#f5a623",
        "processing": "#4a90d9", "downloading": "#7c4dff",
        "": "#4a90d9"
    }
    color = stage_colors.get(_progress_stage, "#4a90d9")
    
    itm[PROJ_LB].Text = f"⏳ {_progress_stage or 'AI 处理中...'} {int(ratio*100)}%  ·  {time_str}"
    itm[PG_BAR].StyleSheet = f"min-height:8px;max-height:8px;background-color:{color};border-radius:3px"
    _pg(ratio)
```

---

## 附录 B: theme.json 加载约定

```
加载顺序（每个产品启动时）:
1. shared/ui/theme.json        ← 基础主题定义
2. {产品目录}/theme.json       ← 产品自定义覆盖（可选）
3. ~/达芬奇插件工坊/theme.json ← 用户个人偏好（未来）

合并策略: 深合并，用户 > 产品 > 基础
```

---

> **审计签名**: ArchitectUX Agent  
> **下次审计**: P1 完成后（预计 2026-06-15）  
> **审计范围扩展**: 批量IO渲染、TTS语音工具、字幕编辑器（待加入 unified 架构）
