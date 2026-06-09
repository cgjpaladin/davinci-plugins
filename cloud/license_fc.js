// License 激活中间件 — Node.js, 阿里云 FC
// 飞书 Base 表格存激活码，FC 做中间层隐藏密钥

const crypto = require('crypto');
const https = require('https');

// ── 配置 ──
const FEISHU_APP_ID = process.env.FEISHU_APP_ID || '';
const FEISHU_APP_SECRET = process.env.FEISHU_APP_SECRET || '';
const BASE_TOKEN = process.env.BASE_TOKEN || 'JEqDbwMoiazH4ds8VIwcEBj8n9f';
const TABLE_ID = process.env.TABLE_ID || 'tblKV7yxqsqgyAyK';
const ADMIN_KEY = process.env.ADMIN_KEY || '';
const HMAC_SECRET = (process.env.HMAC_SECRET || 'change_me').substring(0, 64);
const TRIAL_DAYS = 30;
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
async function listRecords(filter) {
  const resp = await feishuReq('GET',
    `bitable/v1/apps/${BASE_TOKEN}/tables/${TABLE_ID}/records?page_size=500${filter ? '&filter=' + encodeURIComponent(filter) : ''}`);
  return resp.data?.items || [];
}

async function addRecord(fields) {
  const resp = await feishuReq('POST',
    `bitable/v1/apps/${BASE_TOKEN}/tables/${TABLE_ID}/records`,
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
async function handleInitTrial(data) {
  const fp = data.machine_fingerprint || '';
  if (!fp) return { status: 'error', msg: '机器指纹为空' };

  // Check existing trial records
  const records = await listRecords(`CurrentValue.[状态]="试用中"`);
  const existing = records.find(r => r.fields.机器指纹 === fp);
  const now = Math.floor(Date.now() / 1000);

  if (existing) {
    const trialEnd = existing.fields.创建时间 ? Math.floor(existing.fields.创建时间 / 1000) + TRIAL_DAYS * 86400 : now + TRIAL_DAYS * 86400;
    if (now > trialEnd) return { status: 'error', msg: '试用已结束，请购买正式授权' };
    const days = Math.max(0, Math.floor((trialEnd - now) / 86400));
    const payload = {
      activate_key: '', machine_fingerprint: fp, issue_time: now,
      expire_time: trialEnd, offline_grant_end: now + OFFLINE_GRANT_DAYS * 86400,
      nonce: crypto.randomBytes(8).toString('hex'),
      platform: data.platform || 'unknown', products: {}, is_trial: true,
    };
    return { status: 'ok', msg: `试用中，剩余 ${days} 天`, license_token: makeToken(payload), trial_days: days };
  }

  const trialEnd = now + TRIAL_DAYS * 86400;
  await addRecord({ 激活码: '', 状态: '试用中', 机器指纹: fp, 创建时间: Date.now() });

  const payload = {
    activate_key: '', machine_fingerprint: fp, issue_time: now,
    expire_time: trialEnd, offline_grant_end: now + OFFLINE_GRANT_DAYS * 86400,
    nonce: crypto.randomBytes(8).toString('hex'),
    platform: data.platform || 'unknown', products: {}, is_trial: true,
  };
  return { status: 'ok', msg: `试用开始，剩余 ${TRIAL_DAYS} 天`, license_token: makeToken(payload), trial_days: TRIAL_DAYS };
}

async function handleActivate(data) {
  const key = (data.activate_key || '').trim().toUpperCase();
  const fp = data.machine_fingerprint || '';
  if (!key || !fp) return { status: 'error', msg: '参数不完整' };

  const records = await listRecords(`CurrentValue.[激活码]="${key}"`);
  const match = records[0];
  if (!match) return { status: 'error', msg: '激活码无效' };
  const currentStatus = match.fields.状态 || '待售'; // 旧记录无状态字段视为待售
  if (currentStatus !== '待售') return { status: 'error', msg: `激活码状态异常（${currentStatus}）` };

  const now = Math.floor(Date.now() / 1000);
  const expireTime = now + 365 * 86400 * 10; // 10 年买断

  await updateRecord(match.record_id, { 状态: '已激活', 机器指纹: fp, 创建时间: Date.now() });

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

async function handleHeartbeat(data) {
  const fp = data.machine_fingerprint || '';
  if (!fp) return { status: 'error', msg: '机器指纹为空' };

  const now = Math.floor(Date.now() / 1000);
  const grantEnd = now + OFFLINE_GRANT_DAYS * 86400;

  const records = await listRecords(`CurrentValue.[机器指纹]="${fp}"`);
  const activated = records.find(r => r.fields.状态 === '已激活' && r.fields.激活码);
  if (activated) {
    const payload = {
      activate_key: activated.fields.激活码, machine_fingerprint: fp,
      issue_time: Math.floor(activated.fields.创建时间 / 1000) || now,
      expire_time: (Math.floor(activated.fields.创建时间 / 1000) || now) + 365 * 86400 * 10,
      offline_grant_end: grantEnd, nonce: crypto.randomBytes(8).toString('hex'),
      platform: data.platform || 'unknown', products: { delivery_checker: true }, is_trial: false,
    };
    return { status: 'ok', msg: '心跳成功', license_token: makeToken(payload) };
  }

  const trial = records.find(r => r.fields.状态 === '试用中');
  if (trial) {
    const trialEnd = (Math.floor(trial.fields.创建时间 / 1000) || now) + TRIAL_DAYS * 86400;
    if (now > trialEnd) return { status: 'error', msg: '试用已结束' };
    const payload = {
      activate_key: '', machine_fingerprint: fp,
      issue_time: Math.floor(trial.fields.创建时间 / 1000) || now,
      expire_time: trialEnd, offline_grant_end: grantEnd,
      nonce: crypto.randomBytes(8).toString('hex'),
      platform: data.platform || 'unknown', products: {}, is_trial: true,
    };
    return { status: 'ok', msg: '心跳成功', license_token: makeToken(payload) };
  }

  return { status: 'error', msg: '未找到授权记录' };
}

async function handleDeactivate(data) {
  const fp = (data.machine_fingerprint || '').trim();
  if (!fp) return { status: 'error', msg: '机器指纹为空' };
  const records = await listRecords(`CurrentValue.[机器指纹]="${fp}"`);
  const activated = records.find(r => r.fields.状态 === '已激活');
  if (!activated) return { status: 'error', msg: '未找到此机器的激活记录' };
  // 重置为待售，释放激活码
  await updateRecord(activated.record_id, { 状态: '待售', 机器指纹: '' });
  return { status: 'ok', msg: '已停用，激活码已释放' };
}

async function handleManage(data) {
  if (!data.admin_key || data.admin_key !== ADMIN_KEY) return { status: 'error', msg: '管理密钥错误' };

  const action = data.manage_action || '';
  if (action === 'gen_key') {
    const newKey = crypto.randomBytes(6).toString('hex').toUpperCase();
    const formatted = `${newKey.slice(0,4)}-${newKey.slice(4,8)}-${newKey.slice(8,12)}`;
    const now = Math.floor(Date.now() / 1000);
    await addRecord({ 激活码: formatted, 状态: '待售', 机器指纹: '', 创建时间: Date.now() });
    return { status: 'ok', key: formatted, msg: `激活码已生成: ${formatted}` };
  }
  if (action === 'list_keys') {
    const records = await listRecords('');
    return { status: 'ok', keys: records.map(r => ({ ...r.fields, record_id: r.record_id })) };
  }
  if (action === 'delete_trial') {
    const fp = data.machine_fingerprint || '';
    if (!fp) return { status: 'error', msg: '缺少 machine_fingerprint' };
    const records = await listRecords(`CurrentValue.[machine_fp]="${fp}"`);
    for (const r of records) {
      if (r.fields.状态 === '试用中') {
        await feishuReq('DELETE', `bitable/v1/apps/${BASE_TOKEN}/tables/${TABLE_ID}/records/${r.record_id}`);
      }
    }
    return { status: 'ok', msg: `已删除试用记录: ${fp.slice(0,12)}...` };
  }
  return { status: 'error', msg: `未知管理操作: ${action}` };
}

const ROUTES = { init_trial: handleInitTrial, activate: handleActivate, heartbeat: handleHeartbeat, deactivate: handleDeactivate, manage: handleManage };

// ── FC 入口 ──
exports.main_handler = async function(event, context) {
  let body;
  try {
    // FC 3.0 HTTP trigger: event is a Buffer containing the full request JSON
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
