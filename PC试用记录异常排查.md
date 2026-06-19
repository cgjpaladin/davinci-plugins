# PC 试用记录异常排查

## 问题

Windows PC 激活后，飞书 Base 试用记录表里**激活时间为空**。

## 数据

- Base: `BRfGbDgaJa6ZYCsViuOcau2PnSe`
- 试用表: `tblMAUMo8VQGPDZP`（TRIAL_TABLE_ID）
- 激活码表: `tbla9FSVEuuiayQH`（TABLE_ID）
- 异常记录: `recvn1r3Q44JB7`
- 机器指纹: `86a5b8acd06d0ac0bbf6cd9cf6fa3a896ba62038a49365e730f3fc154610fec1`

```
首次试用时间: 2026-06-20 04:06:23  ← 有值
激活时间:     （空）               ← 应为 04:08 左右
最后活跃:     2026-06-20 04:08:21  ← 有心跳
```

## 后端架构

阿里云 FC 运行的 `cloud/license_fc.js`（Node.js），飞书 Base 直接当数据库。无 SQLite。

### init_trial 流程（`handleInitTrial`, L184-225）

1. 按指纹查试用表 → 如果是新记录则 `addRecord`
2. 如果是已有记录则心跳更新（版本、系统、最后活跃）
3. **不碰激活时间**

### activate 流程（`handleActivate`, L109-152）

1. 按激活码查主表 → 校验状态是「待激活」
2. 更新主表：状态=已激活、机器指纹=fp、**激活时间=Date.now()**（仅首次）
3. 乐观锁等待 200ms → 重读确认未被并发覆盖
4. **记录转化**：按指纹查试用表 → 如果存在且激活时间为空 → 写入激活时间

## 根因（已确认）

**`handleActivate` 和 `handleInitTrial` 对机器指纹的处理不一致。**

```js
// handleInitTrial  L185:  trim 了
fp = (data.machine_fingerprint || '').trim()

// handleActivate  L111: 没 trim
fp = data.machine_fingerprint || ''
```

Windows 的 HWID 计算可能带尾部空白字符（换行/空格）。`init_trial` trim 后存入 Base，`activate` 不 trim 去查——指纹不匹配，查不到试用记录，跳过写入激活时间。

Mac 指纹天然无尾部空白，所以 Mac 一直正常。

## 修复

`license_fc.js` L111 加 `.trim()`：

```js
const fp = (data.machine_fingerprint || '').trim();
```

同时 L143 把 `catch(e){}` 改成 `catch(e){ console.error('trial update failed:', e.message); }` 方便下次排查。

## 手动修复本次

```bash
cd /Users/bryan/WorkBuddy/达芬奇插件工坊
lark-cli base +record-upsert \
  --base-token "BRfGbDgaJa6ZYCsViuOcau2PnSe" \
  --table-id "tblMAUMo8VQGPDZP" \
  --fields '[{"机器指纹":"86a5b8acd06d0ac0bbf6cd9cf6fa3a896ba62038a49365e730f3fc154610fec1","激活时间":"2026-06-20 04:08:00"}]' \
  --as user
```
