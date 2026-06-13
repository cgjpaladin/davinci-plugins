// License 激活中间件 — Node.js, 阿里云 FC
// 飞书 Base 表格存激活码，FC 做中间层隐藏密钥
// v3 重构：纯激活码管理，试用纯本地，无心跳
// v3.1：试用指纹服务端防无限重试 + 时钟防退

const crypto = require('crypto');

const https = require('https');

// ── 配置 ──
const FEISHU_APP_ID = process.env.FEISHU_APP_ID || '';
const FEISHU_APP_SECRET = process.env.FEISHU_APP_SECRET || '';
const BASE_TOKEN = process.env.BASE_TOKEN || 'BRfGbDgaJa6ZYCsViuOcau2PnSe';
const TABLE_ID = process.env.TABLE_ID || 'tbla9FSVEuuiayQH';
const TRIAL_TABLE_ID = process.env.TRIAL_TABLE_ID || 'tblMAUMo8VQGPDZP';
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
      }
    };
    const req = https.request(opts, res => {
      let data = '';
      res.on('data', c => data += c);
      res.on('end', () => {
        try { resolve(JSON.parse(data)); }
        catch(e) { reject(new Error(data)); }
      });
    });
    req.on('error', reject);
    if (body) req.write(JSON.stringify(body));
    req.end();
  });
}

async function getToken() {
  if (cachedToken && Date.now() < tokenExpireAt) return cachedToken;
  const now = Date.now();
  const resp = await feishuReq('POST', 'auth/v3/tenant_access_token/internal', {
    app_id: FEISHU_APP_ID,
    app_secret: FEISHU_APP_SECRET,
  }, true);
  if (!resp.tenant_access_token) throw new Error(`Token failed: ${JSON.stringify(resp)}`);
  cachedToken = resp.tenant_access_token;
  tokenExpireAt = now + (resp.expire - 60) * 1000;
  return cachedToken;
}

// Override feishuReq to auto-get token
const _feishuReq = feishuReq;
feishuReq = async function(method, path, body, skipToken) {
  if (!skipToken) await getToken();
  return _feishuReq(method, path, body);
};

// ── Base CRUD ──
async function listRecords(filter, tableId) {
  const tid = tableId || TABLE_ID;
  const resp = await feishuReq('GET',
    `bitable/v1/apps/${BASE_TOKEN}/tables/${tid}/records?page_size=500${filter ? '&filter=' + encodeURIComponent(filter) : ''}`);
  return resp.data?.items || [];
}

async function addRecord(fields, tableId) {
  const tid = tableId || TABLE_ID;
  const resp = await feishuReq('POST',
    `bitable/v1/apps/${BASE_TOKEN}/tables/${tid}/records`,
    { fields });
  if (resp.code && resp.code !== 0) throw new Error(`Feishu addRecord: ${resp.code} ${resp.msg}`);
  return resp.data?.record;
}

async function updateRecord(recordId, fields) {
  const resp = await feishuReq('PUT',
    `bitable/v1/apps/${BASE_TOKEN}/tables/${TABLE_ID}/records/${recordId}`,
    { fields });
  if (resp.code && resp.code !== 0) throw new Error(`Feishu updateRecord: ${resp.code} ${resp.msg}`);
  return resp.data?.record;
}

// ── HMAC ──
function sign(payload) {
  const keys = Object.keys(payload).sort();
  const str = keys.map(k => `${k}=${encodeURIComponent(String(payload[k]))}`).join('&');
  return crypto.createHmac('sha256', HMAC_SECRET).update(str).digest('hex');
}

function makeToken(payload) {
  return JSON.stringify({ payload, signature: sign(payload) });
}

// ── Handlers ──

// 激活：仅接受「待激活」状态的码
async function handleActivate(data) {
  const key = (data.activate_key || '').trim().toUpperCase();
  const fp = data.machine_fingerprint || '';
  if (!key || !fp) return { status: 'error', msg: '参数不完整' };

  const records = await listRecords(`CurrentValue.[激活码]="${key}"`);
  const match = records[0];
  if (!match) return { status: 'error', msg: '此激活码不存在，请检查是否输入正确' };
  const currentStatus = match.fields.状态 || '';
  if (currentStatus !== '待激活') return { status: 'error', msg: currentStatus === '已激活' ? '此激活码已在其他设备使用，请先在其他设备上停用' : '此激活码不存在，请检查是否输入正确' };

  const now = Math.floor(Date.now() / 1000);
  const expireTime = now + 365 * 86400 * 100; // 永久（~100年）

  // 首次激活时记录时间，停用-再激活不覆盖
  const updateFields = { 状态: '已激活', 机器指纹: fp };
  if (!match.fields.激活时间) {
    updateFields.激活时间 = Date.now();
  }
  await updateRecord(match.record_id, updateFields);

  // 乐观锁：等待 200ms 后重读，确认未被并发写入覆盖
  await new Promise(r => setTimeout(r, 200));
  const verify = await listRecords(`CurrentValue.[激活码]="${key}"`);
  if (verify[0] && verify[0].fields.机器指纹 !== fp) {
    return { status: 'error', msg: '激活码已被其他设备抢先使用' };
  }

  const payload = {
    activate_key: key, machine_fingerprint: fp, issue_time: now,
    expire_time: expireTime, offline_grant_end: now + OFFLINE_GRANT_DAYS * 86400,
    nonce: crypto.randomBytes(8).toString('hex'),
    platform: data.platform || 'unknown', products: { delivery_checker: true }, is_trial: false,
  };
  return { status: 'ok', msg: '激活成功', license_token: makeToken(payload) };
}

// 停用：将已激活码重置为待激活，释放到其他机器
async function handleDeactivate(data) {
  const fp = (data.machine_fingerprint || '').trim();
  if (!fp) return { status: 'error', msg: '机器指纹为空' };
  const records = await listRecords(`CurrentValue.[机器指纹]="${fp}"`);
  const activated = records.find(r => r.fields.状态 === '已激活');
  if (!activated) return { status: 'error', msg: '未找到此机器的激活记录' };
  await updateRecord(activated.record_id, { 状态: '待激活', 机器指纹: '' });
  return { status: 'ok', msg: '已停用，激活码已释放' };
}

// 管理后台
async function handleManage(data) {
  if (!data.admin_key || data.admin_key !== ADMIN_KEY) return { status: 'error', msg: '管理密钥错误' };

  const action = data.manage_action || '';
  if (action === 'gen_key') {
    const newKey = crypto.randomBytes(6).toString('hex').toUpperCase();
    const formatted = `${newKey.slice(0,4)}-${newKey.slice(4,8)}-${newKey.slice(8,12)}`;
    await addRecord({ 激活码: formatted, 状态: '待售', 机器指纹: '' });
    return { status: 'ok', key: formatted, msg: `激活码已生成: ${formatted}` };
  }
  if (action === 'list_keys') {
    const records = await listRecords('');
    return { status: 'ok', keys: records.map(r => ({ ...r.fields, record_id: r.record_id })) };
  }
  return { status: 'error', msg: `未知管理操作: ${action}` };
}

// 试用记录：服务端返回日期序数，消除时区歧义
async function handleInitTrial(data) {
  const fp = (data.machine_fingerprint || '').trim();
  if (!fp) return { status: 'error', msg: '参数不完整' };

  const records = await listRecords(`CurrentValue.[机器指纹]="${fp}"`, TRIAL_TABLE_ID);

  const msToOrdinal = (ms) => {
    // Feishu 日期存 UTC ms，但表格显示+8时区。加 8 小时后转当地日期
    const d = new Date(ms + 28800000);  // +8h
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
  };

  if (records.length > 0) {
    return { status: 'ok', trial_date_ordinal: msToOrdinal(records[0].fields['首次试用时间']) };
  }

  const now = Date.now();
  await addRecord({ 机器指纹: fp, 首次试用时间: now }, TRIAL_TABLE_ID);
  return { status: 'ok', trial_date_ordinal: msToOrdinal(now) };
}

// 启动时校验：激活码状态 + 指纹是否仍匹配
async function handleVerifyStatus(data) {
  const key = (data.activate_key || '').trim().toUpperCase();
  const fp = data.machine_fingerprint || '';
  if (!key || !fp) return { status: 'error', msg: '参数不完整' };

  const records = await listRecords(`CurrentValue.[激活码]="${key}"`);
  const match = records[0];
  if (!match) return { status: 'revoked', msg: '授权已失效' };
  if (match.fields.状态 !== '已激活') return { status: 'revoked', msg: '授权已失效' };
  if (match.fields.机器指纹 !== fp) return { status: 'revoked', msg: '授权已失效' };

  const now = Math.floor(Date.now() / 1000);
  const payload = {
    activate_key: key, machine_fingerprint: fp, issue_time: now,
    expire_time: now + 365 * 86400 * 100, offline_grant_end: now + OFFLINE_GRANT_DAYS * 86400,
    nonce: crypto.randomBytes(8).toString('hex'),
    platform: data.platform || 'unknown', products: { delivery_checker: true }, is_trial: false,
  };
  return { status: 'ok', msg: '授权有效', license_token: makeToken(payload) };
}

const ROUTES = {
  activate: handleActivate,
  deactivate: handleDeactivate,
  verify_status: handleVerifyStatus,
  init_trial: handleInitTrial,
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
