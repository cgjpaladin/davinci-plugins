# 达芬奇崩溃治理 — Resource Coalition 根因与对策

> 2026-05-23 全公司排查

## 问题

部分机器达芬奇频繁闪退（黄霈 6 次、葛晨阳 6 次、杨惠雯 4 次、惠洋 3 次），崩溃日志显示 `Exception Type: EXC_RESOURCE` + `Resource Coalition`，非 SIGSEGV。

## 机制

macOS 的 **Resource Coalition** 把 DR 及其子进程（Fusion 渲染引擎、解码器等）打包成资源联盟，共享内存配额。超出配额时系统杀 coalition 领头进程（DR），不等它优雅退出。

## 根因

16GB 机器上 DR 默认配置占 **75%**（12GB），只剩 4GB 给系统、Chrome、飞书、微信。一开大项目立刻爆。

## config.dat 结构

路径：`~/Library/Preferences/Blackmagic Design/DaVinci Resolve/config.dat`
格式：**明文 ASCII**（非二进制）

关键行：
```
Local.Resource.ResolveMemoryPercentage = 75
Local.Resource.FusionMemoryPercentage = 67
```

- `ResolveMemoryPercentage`：DR 占系统总内存的百分比
- `FusionMemoryPercentage`：Fusion 缓存在 DR 已分配内存中的百分比

## 推荐值

| 总内存 | Resolve% | DR 可用 | 系统剩余 |
|--------|----------|---------|---------|
| 16GB   | **60%**  | 9.6GB   | 6.4GB   |
| 24GB   | **65%**  | 15.6GB  | 8.4GB   |
| 32GB   | 70%      | 22.4GB  | 9.6GB   |

## 修改方法

⚠️ **必须 DR 关闭时改**——开着改会被 DR 退出时覆盖原始值。

```bash
# 读当前值
grep MemoryPercentage ~/Library/Preferences/Blackmagic\ Design/DaVinci\ Resolve/config.dat

# 改（16GB）
sed -i '' 's/ResolveMemoryPercentage = 75/ResolveMemoryPercentage = 60/' \
  ~/Library/Preferences/Blackmagic\ Design/DaVinci\ Resolve/config.dat
```

## 全公司内存压力分布（2026-05-23）

| 压力 | 机器数 | 机器 |
|------|--------|------|
| 80%+ | 2 | 黄霈(88%)、秦雪彤(83%) |
| 60-80% | 2 | 葛晨阳(71%)、杨惠雯(66%) |
| 40-60% | 14 | 其余 |
| <40% | 0 | — |

## 对策优先级

1. **硬件升级**：16GB → 32GB（一次性，根本解决）
2. **关闭后台软件**：干活时关 Chrome/飞书/微信（免费但不靠人）
3. **降低 DR 内存百分比**：16GB 改 60%，24GB 改 65%（不改硬件的最快方案）
