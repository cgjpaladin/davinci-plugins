// License 中间件 — Node.js, 阿里云 FC
// v4: 单表「授权记录」，试用+激活合一，一行一指纹永生

const crypto = require('crypto');
const https = require('https');

// ── 配置 ──
const FEISHU_APP_ID = process.env.FEISHU_APP_ID || '';
const FEISHU_APP_SECRET = process.env.FEISHU_APP_SECRET || '';
const BASE_TOKEN = process.env.BASE_TOKEN || 'BRfGbDgaJa6ZYCsViuOcau2PnSe';
const TABLE_ID = process.env.TABLE_ID || 'tblGfiUYR3UHQT08';
const ADMIN_KEY = process.env.ADMIN_KEY || '';
const HMAC_SECRET = (process.env.HMAC_SECRET || 'change_me').substring(0, 64);
const OFFLINE_GRANT_DAYS = 30;

let cachedToken = null;
let tokenExpireAt = 0;

// ── Feishu API ──
function feishuReq(method, path, body) {
  return new Promise((resolve, reject) => {
    const opts = {
      hostname: 'open.feishu.cn',
      path: `/open-apis/${path}`,
      method,
      headers: {
        'Content-Type': 'application/json; charset=utf-8',
        'Authorization': `Bearer ${cachedToken}`,
      },
    };
    const req = https.request(opts, (res) => {
      let data = '';
      res.on('data', c => data += c);
      res.on('end', () => {
        try { resolve(JSON.parse(data)); } catch(e) { reject(new Error(`JSON parse: ${data.slice(0,200)}`)); }
      });
    });
    req.on('error', reject);
    req.setTimeout(15000, () => { req.destroy(); reject(new Error('timeout')); });
    if (body) req.write(JSON.stringify(body));
    req.end();
  });
}

async function getToken() {
  if (cachedToken && Date.now() < tokenExpireAt - 60000) return cachedToken;
  const resp = await feishuReq('POST', 'auth/v3/tenant_access_token/internal', {
    app_id: FEISHU_APP_ID, app_secret: FEISHU_APP_SECRET,
  });
  cachedToken = resp.tenant_access_token;
  tokenExpireAt = Date.now() + (resp.expire || 3600) * 1000;
  return cachedToken;
}

// ── Base CRUD ──
async function listRecords(filter) {
  await getToken();
  const path = `bitable/v1/apps/${BASE_TOKEN}/tables/${TABLE_ID}/records?page_size=20&filter=${encodeURIComponent(filter)}`;
  const resp = await feishuReq('GET', path);
  return (resp.data && resp.data.items) || [];
}

async function addRecord(fields) {
  await getToken();
  const resp = await feishuReq('POST',
    `bitable/v1/apps/${BASE_TOKEN}/tables/${TABLE_ID}/records`,
    { fields });
  return resp;
}

async function updateRecord(recordId, fields) {
  await getToken();
  const resp = await feishuReq('PUT',
    `bitable/v1/apps/${BASE_TOKEN}/tables/${TABLE_ID}/records/${recordId}`,
    { fields });
  return resp;
}

// ── Token 签名 ──
function makeToken(payload) {
  const hmac = crypto.createHmac('sha256', HMAC_SECRET);
  const payloadStr = JSON.stringify(payload);
  hmac.update(payloadStr);
  return JSON.stringify({ payload, signature: hmac.digest('hex') });
}

// ── 日期转换 ──
function msToOrdinal(ms) {
  const d = new Date(ms + 28800000); // +8h UTC
  const y = d.getFullYear(), m = d.getMonth(), day = d.getDate();
  const months = [31,28,31,30,31,30,31,31,30,31,30,31];
  let days = 0;
  for (let yr = 1970; yr < y; yr++)
    days += (yr%4===0&&yr%100!==0)||(yr%400===0) ? 366 : 365;
  const leap = (y%4===0&&y%100!==0)||(y%400===0);
  for (let i = 0; i < m; i++)
    days += months[i] + (i===1&&leap ? 1 : 0);
  days += day - 1;
  return 719163 + days;
}

// ═══════════════════════════════════════════
// Handler: init_trial
// 按指纹查 → 有则心跳更新，无则新建
// ═══════════════════════════════════════════
async function handleInitTrial(data) {
  const fp = (data.machine_fingerprint || '').trim();
  if (!fp) return { status: 'error', msg: '参数不完整' };

  const records = await listRecords(`CurrentValue.[机器指纹]="${fp}"`);

  const heartbeatFields = { '最后活跃': Date.now() };
  if (data.version) heartbeatFields['插件版本'] = data.version;
  if (data.os_version) heartbeatFields['系统版本'] = data.os_version;
  if (data.resolve_version) heartbeatFields['达芬奇版本'] = data.resolve_version;
  if (data.public_ip) heartbeatFields['最近IP'] = data.public_ip;
  if (data.ip_region) heartbeatFields['所属地区'] = data.ip_region;

  if (records.length > 0) {
    await updateRecord(records[0].record_id, heartbeatFields);
    return { status: 'ok', trial_date_ordinal: msToOrdinal(records[0].fields['首次试用时间']) };
  }

  // 新行
  const now = Date.now();
  await addRecord({
    机器指纹: fp,
    状态: '试用中',
    首次试用时间: now,
    最后活跃: now,
    插件版本: data.version || '',
    系统版本: data.os_version || '',
    达芬奇版本: data.resolve_version || '',
    最近IP: data.public_ip || '',
    所属地区: data.ip_region || '',
  });
  return { status: 'ok', trial_date_ordinal: msToOrdinal(now) };
}

// ═══════════════════════════════════════════
// Handler: activate
// 按激活码查 → 写入指纹+激活时间 → 已激活
// ═══════════════════════════════════════════
async function handleActivate(data) {
  const key = (data.activate_key || '').trim().toUpperCase();
  const fp = (data.machine_fingerprint || '').trim();
  if (!key || !fp) return { status: 'error', msg: '参数不完整' };

  const records = await listRecords(`CurrentValue.[激活码]="${key}"`);
  const match = records[0];
  if (!match) return { status: 'error', msg: '激活码不存在，请检查是否输入正确' };

  const currentStatus = match.fields.状态 || '';
  if (currentStatus === '已激活') {
    return { status: 'error', msg: '此激活码已在其他设备使用，请先在其他设备上停用' };
  }

  const now = Date.now();
  const updateFields = {
    状态: '已激活',
    机器指纹: fp,
    激活时间: match.fields.激活时间 || now,
    首次试用时间: match.fields.首次试用时间 || now,
  };
  if (data.public_ip) updateFields['最近IP'] = data.public_ip;
  if (data.ip_region) updateFields['所属地区'] = data.ip_region;
  await updateRecord(match.record_id, updateFields);

  const expireTime = Math.floor(now / 1000) + 365 * 86400 * 100;
  const payload = {
    activate_key: key, machine_fingerprint: fp, issue_time: Math.floor(now / 1000),
    expire_time: expireTime, offline_grant_end: Math.floor(now / 1000) + OFFLINE_GRANT_DAYS * 86400,
    nonce: crypto.randomBytes(8).toString('hex'),
    platform: data.platform || 'unknown', products: { delivery_checker: true }, is_trial: false,
  };
  return { status: 'ok', msg: '激活成功', license_token: makeToken(payload) };
}

// ═══════════════════════════════════════════
// Handler: deactivate
// 按指纹查已激活行 → 清指纹+状态回试用中
// ═══════════════════════════════════════════
async function handleDeactivate(data) {
  const fp = (data.machine_fingerprint || '').trim();
  if (!fp) return { status: 'error', msg: '机器指纹为空' };

  const records = await listRecords(`CurrentValue.[机器指纹]="${fp}"`);
  const activated = records.find(r => r.fields.状态 === '已激活');
  if (!activated) return { status: 'error', msg: '未找到此机器的激活记录' };

  await updateRecord(activated.record_id, { 状态: '已停用', 机器指纹: '' });
  return { status: 'ok', msg: '已停用，激活码已释放' };
}

// ═══════════════════════════════════════════
// Handler: verify_status
// 启动时双验证：激活码+指纹都匹配才有效
// ═══════════════════════════════════════════
async function handleVerifyStatus(data) {
  const key = (data.activate_key || '').trim().toUpperCase();
  const fp = (data.machine_fingerprint || '').trim();
  if (!key || !fp) return { status: 'error', msg: '参数不完整' };

  const records = await listRecords(`CurrentValue.[激活码]="${key}"`);
  const match = records[0];
  if (!match) return { status: 'revoked', msg: '授权已失效' };
  if (match.fields.状态 !== '已激活') return { status: 'revoked', msg: '授权已失效' };
  if (match.fields.机器指纹 !== fp) return { status: 'revoked', msg: '授权已失效' };

  // 心跳
  const fields = { '最后活跃': Date.now() };
  if (data.version) fields['插件版本'] = data.version;
  if (data.os_version) fields['系统版本'] = data.os_version;
  if (data.resolve_version) fields['达芬奇版本'] = data.resolve_version;
  if (data.public_ip) fields['最近IP'] = data.public_ip;
  if (data.ip_region) fields['所属地区'] = data.ip_region;
  try { await updateRecord(match.record_id, fields); } catch(e) { console.error('verify_status update:', e.message); }

  const now = Math.floor(Date.now() / 1000);
  const payload = {
    activate_key: key, machine_fingerprint: fp, issue_time: now,
    expire_time: now + 365 * 86400 * 100, offline_grant_end: now + OFFLINE_GRANT_DAYS * 86400,
    nonce: crypto.randomBytes(8).toString('hex'),
    platform: data.platform || 'unknown', products: { delivery_checker: true }, is_trial: false,
  };
  return { status: 'ok', msg: '授权有效', license_token: makeToken(payload) };
}

// ═══════════════════════════════════════════
// Handler: manage (管理员)
// ═══════════════════════════════════════════
async function handleManage(data) {
  if (!data.admin_key || data.admin_key !== ADMIN_KEY) return { status: 'error', msg: '管理密钥错误' };
  return { status: 'ok', msg: 'ok' };
}

const ROUTES = {
  init_trial: handleInitTrial,
  activate: handleActivate,
  deactivate: handleDeactivate,
  verify_status: handleVerifyStatus,
  manage: handleManage,
};

// ── FC 入口 ──
exports.main_handler = async function(event, context) {
  let body;
  try {
    const raw = Buffer.from(event).toString('utf-8');
    const evt = JSON.parse(raw);
    const bodyStr = evt.body;
    if (evt.isBase64Encoded) {
      body = JSON.parse(Buffer.from(bodyStr, 'base64').toString('utf-8'));
    } else {
      body = typeof bodyStr === 'string' ? JSON.parse(bodyStr) : bodyStr;
    }
  } catch(e) {
    return { statusCode: 400, body: JSON.stringify({ status: 'error', msg: `请求格式错误: ${e.message}` }) };
  }

  const handler = ROUTES[body.action || ''];
  if (!handler) {
    return { statusCode: 400, body: JSON.stringify({ status: 'error', msg: `未知动作: ${body.action}` }) };
  }

  try {
    const result = await handler(body);
    const code = result.status === 'ok' ? 200 : 401;
    return { statusCode: code, body: JSON.stringify(result) };
  } catch(e) {
    return { statusCode: 500, body: JSON.stringify({ status: 'error', msg: `服务端异常: ${e.message}` }) };
  }
};
