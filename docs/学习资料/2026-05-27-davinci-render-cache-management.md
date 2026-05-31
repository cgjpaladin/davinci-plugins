# 达芬奇渲染缓存管理 — 多工作站运维视角

> **来源**:
> - [3 Best DaVinci Resolve Render Cache Settings (2025)](https://beginnersapproach.com/davinci-resolve-render-cache/) — 发布日期 2025
> - [How to Delete Render Cache](https://beginnersapproach.com/davinci-resolve-delete-render-cache/) — 发布日期 2025
> - [Quickly Delete Render Cache](https://teckers.io/delete-render-cache-davinci-resolve/) — 发布日期 2023-12
> - [DR 20 Setup & Troubleshooting Guide](https://irendering.net/davinci-resolve-20-setup-troubleshooting-guide-for-2025/) — 发布日期 2025-06
>
> **适用版本**: DaVinci Resolve 17 ~ 20（概念贯穿，DR 20 实测兼容）
> **对我们环境的适用性**: ✅ 完全适用。19 台 M4 Mac mini 共享 SMB 存储，每台本地 SSD 256GB，缓存管理是关键运维课题。

---

## 一、渲染缓存基础

### 1.1 什么触发缓存？

达芬奇在以下场景需要渲染缓存来保证实时播放：

| 效果类型 | 说明 |
|----------|------|
| Fusion 合成 | 节点图越复杂，越需缓存 |
| Resolve FX / OFX 插件 | 降噪、锐化、美颜等 |
| 转场效果 | 叠化、推拉等 |
| 非 Normal 合成模式 | Add、Multiply、Overlay 等 |
| 变速 / 速度效果 | 光流法尤其吃资源 |

### 1.2 缓存文件格式

缓存文件为 `.dvcc`（DaVinci Resolve 专有格式），存储在 `CacheClip/` 目录下随机命名的子文件夹中。

**格式建议**（Project Settings → Master Settings → Optimized Media and Render Cache → Render Cache Format）：

| 平台 | 推荐 | 替代 |
|------|------|------|
| **Mac（我们）** | **ProRes 422 Proxy** | ProRes 422 LT |
| Windows | DNxHR LB | DNxHR SQ |

> 对我们：19 台全是 Mac → 统一 ProRes Proxy，体积小、解码快。

---

## 二、两种缓存模式

### 2.1 Smart（智能模式）

- **路径**: Playback → Render Cache → Smart
- DR 自动判断哪些片段需要缓存
- 闲置 5 秒后自动开始后台缓存（可在 Project Settings 调整到 3 秒）
- 时间线标记：红线 = 需要缓存 / 蓝线 = 已缓存
- 优势：设置后即忘，适合不熟悉技术的剪辑师

### 2.2 User（手动模式）

- **路径**: Playback → Render Cache → User
- 右键片段 → Render Cache Fusion Output → On
- 用户完全控制哪些片段需要缓存
- 适合精确管理缓存范围

**推荐**：日常用户用 Smart，高级用户/调色师用 User。

---

## 三、缓存位置管理

### 3.1 默认位置

缓存默认存储在 **Preferences → System → Media Storage** 中列出的第一个卷。

对我们 19 台 Mac mini：
- 如果第一个卷是本地 SSD → 缓存写本地，不占 SMB
- 如果第一个卷是 SMB 共享 → 缓存写 SMB，浪费网络带宽且拖慢所有人

### 3.2 推荐配置

```
Project Settings → Master Settings → Working Folders → Cache Files Location
→ 指向本地 SSD 路径（如 /Users/Shared/DaVinciCache/）
```

**多工作站最佳实践**（来自 creativevideotips 协作教程确认）：

> "Each client computer can locally have its own cache files for the best performance."

每个客户端本地缓存各自项目，不共享缓存文件。理由：
1. 缓存文件是 `.dvcc` 专有格式，仅绑定生成它的那台机器
2. 本地 SSD 读写速度远快于 SMB
3. 不占用网络带宽

### 3.3 对我们环境的配置建议

每台 Mac mini 应该：
```
Preferences → System → Media Storage
  - 先列出 SMB 共享（放素材）
  - 再加本地路径（放缓存，设为第一个以确保缓存写本地）
```

或更明确地：
```
Project Settings → Working Folders → Cache Files Location
  → /Users/Shared/DaVinciCache/<项目名>/
```

---

## 四、缓存清理

### 4.1 三种清理方式

| 方式 | 路径 | 效果 |
|------|------|------|
| **项目内 All** | Playback → Delete Render Cache → All | 清空当前项目所有缓存 |
| **项目内 Unused** | Playback → Delete Render Cache → Unused | 仅清理时间线已移除片段的缓存 |
| **项目内 Selected Clips** | Playback → Delete Render Cache → Selected Clips | 仅清理选中片段 |
| **手动文件系统** | 删除 `CacheClip/` 下随机文件夹 | 彻底，可跨项目 |

### 4.2 重要限制

1. **DR 没有自动缓存清理功能** — 永远不会自动删缓存
2. **Playback 菜单删不干净** — 有时文件系统层面残留
3. **一次只能删一个项目的缓存** — 要跨项目清理必须逐个打开项目，或手动删文件

### 4.3 对我们环境的最佳实践（运维视角）

**场景 1：项目交付后清理**
```bash
# 单台机器
rm -rf /Users/Shared/DaVinciCache/<项目名>/CacheClip/
```

**场景 2：全集群清理（批量 SSH）**
使用我们新建的 `tools/davinci_cache_audit.sh` 审计 + 清理。

**场景 3：定期自动清理**
每台 Mac mini 设 weekly cron：
```bash
# 清理 30 天前的缓存
find /Users/Shared/DaVinciCache -name "CacheClip" -type d -mtime +30 -exec rm -rf {} \; 2>/dev/null
```

---

## 五、优化媒体 vs 渲染缓存

| 维度 | 优化媒体 (Optimized Media) | 渲染缓存 (Render Cache) |
|------|--------------------------|------------------------|
| 时机 | 编辑**前**生成 | 编辑**中**自动生成 |
| 作用范围 | 全局（编辑页、媒体页、时间线内外） | 仅时间线内特定片段 |
| 效果处理 | 无重型效果时流畅；加了效果仍会卡 | 将计算密集型效果烘焙 |
| 文件格式 | 转码为友好编解码（ProRes Proxy 等） | `.dvcc` 专有格式 |
| 清理 | Playback → Delete Optimized Media | Playback → Delete Render Cache |

两者互补：优化媒体保基础流畅 + 渲染缓存处理复杂效果。

---

## 六、对我们环境意味着什么

### 运维要点

| 编号 | 要点 | 优先级 |
|------|------|--------|
| 1 | **每台 Mac mini 缓存必须写本地 SSD，不能写 SMB** | 🔴 高 |
| 2 | **DR 不自动清缓存 → 256GB SSD 会逐渐填满 → 需定期清理** | 🔴 高 |
| 3 | 统一 ProRes Proxy 为渲染缓存格式（全 Mac 环境） | 🟡 中 |
| 4 | 建 `tools/davinci_cache_audit.sh` 跨 19 台审计缓存占用 | 🟡 中 |
| 5 | 项目交付后通知剪辑师手动清理 + 运维兜底 weekly cleanup | 🟢 低 |

### 已知用户习惯关联

- mini102（张江涛）下班不关 DR → 一次编辑天天累积缓存
- 长期不重启的机器 → 缓存累积更严重
- 20 人团队同时编辑 → 缓存总量可达 TB 级（人员 × 项目 × 缓存）

### 即时可用的操作

```bash
# 查看某台机器的缓存大小
ssh miniXXX "du -sh /Users/Shared/DaVinciCache/ 2>/dev/null || echo 'no cache dir'"

# 清理某台机器的所有缓存（确认后）
ssh miniXXX "rm -rf /Users/Shared/DaVinciCache/CacheClip/"
```
