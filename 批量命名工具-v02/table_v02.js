// 批量命名工具 v4.0 — Handsontable 版
const APP_VERSION = '4.0';
const APP_BRANCH = 'hot';
const APP_BUILD_TIME = '';

let hot, files = [], sel = new Set(), _dropCount = 0, _firstDrop = true;
let methodDescMap = {}, _ready = false;

// === Bridge ===
function call(m, ...a) {
  try {
    if (window.pywebview && window.pywebview.api) return window.pywebview.api[m](...a);
  } catch (e) { console.error('API error:', m, e); return null }
  return mock(m, ...a);
}
function mock(m, ...a) {
  return new Promise(r => {
    const C = { ep: '01', sc: '01', gr: '01', desc: '', author: '', method: '', ver: '01', status: 'OK', tk: '01' };
    switch (m) {
      case 'get_config': r({ fields: [], defaults: {}, method_desc_map: {}, name_format: [], field_rules: [] }); break;
      case 'echo': r({ received: a[0] }); break;
      case 'debug_log': r('ok'); break;
      default: r({});
    }
  });
}
function toast(msg) { document.getElementById('resultMsg').textContent = msg; setTimeout(() => { document.getElementById('resultMsg').textContent = ''; }, 3000); }

// === Init ===
function _tryStart() {
  if (_ready) return;
  const live = !!(window.pywebview && window.pywebview.api);
  if (!live) return;
  _ready = true;
  if (window._tryIv) clearInterval(window._tryIv);
  init().catch(e => { document.getElementById('emptyMsg').textContent = '启动失败: ' + e; document.getElementById('emptyMsg').classList.add('show'); });
}
window._tryIv = setInterval(_tryStart, 300);

async function init() {
  const dm = document.getElementById('debugMode');
  dm.textContent = '📋';
  dm.onclick = () => {
    window.pywebview.api.debug_log('').then(r => {
      const text = (r.log || []).join('\n');
      if (text) navigator.clipboard.writeText(text).then(() => toast('已复制 ' + r.log.length + ' 条日志'));
      else toast('无日志');
    });
  };

  const cfg = await call('get_config');
  const allFields = cfg.fields || [];
  methodDescMap = {};
  (cfg.method_desc_map || {}).forEach ? null : Object.assign(methodDescMap, cfg.method_desc_map || {});

  // Build Hot columns
  const columns = [
    { data: '_idx', title: '序号', readOnly: true, width: 44, renderer: idxRenderer },
    { data: '_thumb', title: '缩略图', readOnly: true, width: 52, renderer: thumbRenderer },
    { data: 'ep', title: 'Ep 集数', width: 60, validator: digitValidator('ep') },
    { data: 'sc', title: 'Sc 场次', width: 60, validator: digitValidator('sc') },
    { data: 'gr', title: 'Gr 小场次', width: 60, validator: digitValidator('gr') },
    { data: 'tk', title: 'Tk 次数', width: 60, readOnly: true },
    { data: 'desc', title: '镜头描述', width: 149, renderer: descRenderer },
    { data: 'method', title: '制作方式', width: 120, type: 'dropdown', source: ['', '智能分镜版', '双轨版', '角色专属版'], renderer: dropdownRenderer },
    { data: 'author', title: '制作者', width: 64, validator: chineseOnlyValidator },
    { data: 'ver', title: 'v 版本', width: 60, validator: digitValidator('ver') },
    { data: 'status', title: '通过', width: 66, type: 'dropdown', source: ['OK', 'KP', 'NG', ''], renderer: dropdownRenderer },
    { data: '_basename', title: '原文件名', readOnly: true, width: 90 },
  ];

  const hotElement = document.getElementById('hot');
  hot = new Handsontable(hotElement, {
    data: buildData(files),
    columns: columns,
    rowHeaders: false,
    colHeaders: true,
    height: '100%',
    width: '100%',
    stretchH: 'last',
    manualColumnResize: true,
    manualRowResize: false,
    outsideClickDeselects: false,
    selectionMode: 'multiple',
    autoWrapRow: true,
    autoWrapCol: true,
    enterBeginsEditing: true,
    allowInsertRow: false,
    allowInsertColumn: false,
    allowRemoveRow: false,
    allowRemoveColumn: false,
    contextMenu: ['row_above', 'row_below', 'remove_row', '---------', 'copy', 'cut'],
    licenseKey: 'non-commercial-and-evaluation',
    afterChange: (changes, source) => {
      if (!changes || source === 'loadData') return;
      changes.forEach(([row, prop, oldVal, newVal]) => {
        if (prop === 'method' && newVal !== oldVal) onMethodChange(row, oldVal, newVal);
      });
    },
    afterSelection: (r, c, r2, c2) => { updateUndoButton(); },
    beforeKeyDown: (e) => {
      if (e.key === 'Backspace' || e.key === 'Delete') {
        // Allow deletion — Handsontable sets value to ''
        return;
      }
    },
  });

  // Toolbar events
  document.getElementById('btnAddFiles').onclick = addFiles;
  document.getElementById('btnAddFolder').onclick = addFolder;
  document.getElementById('btnClear').onclick = clearAll;
  document.getElementById('btnRename').onclick = doRename;
  document.getElementById('btnArchive').onclick = doArchive;
  document.getElementById('btnUndo').onclick = doUndo;

  // Drop handled by Python（pywebview 原生拖拽拿到完整路径）

  updateEmpty();
  call('debug_log', `INIT: Handsontable ready, files=${files.length}`);
}

// === Data ===
function buildData(files) {
  return files.map((f, i) => ({
    _idx: String(i + 1).padStart(Math.max(2, String(files.length).length), '0'),
    _thumb: f.thumb || '',
    _basename: f.basename || '',
    _path: f.path,
    _fp: f.fp || f.path,
    ...f.fields,
    tk: f.tk || _computeTK(i),
  }));
}

// === Renderers ===
function idxRenderer(instance, td, row, col, prop, value) {
  td.innerHTML = value;
  td.style.textAlign = 'left';
  td.style.fontSize = '13px';
  return td;
}
function thumbRenderer(instance, td, row, col, prop, value) {
  if (value) td.innerHTML = `<img src="${value}" style="width:32px;height:18px;object-fit:cover;border-radius:2px;vertical-align:middle">`;
  td.style.padding = '4px';
  return td;
}
function descRenderer(instance, td, row, col, prop, value, cellProperties) {
  const method = instance.getDataAtRowProp(row, 'method') || '';
  if (!method) {
    td.innerHTML = '<span style="color:#555">请先选择制作方式</span>';
    cellProperties.readOnly = true;
  } else {
    const cfg = methodDescMap[method] || {};
    cellProperties.readOnly = cfg.mode === 'locked';
    td.innerHTML = value || (value === '' ? '<span style="color:#3a3a3a">—</span>' : value);
  }
  return td;
}
function dropdownRenderer(instance, td, row, col, prop, value) {
  td.innerHTML = value || '<span style="color:#3a3a3a">—</span>';
  return td;
}

// === Validators ===
function digitValidator(key) {
  const strict = { ep: /^(0[1-9]|[1-9]\d{1,2})$/, sc: /^(0[1-9]|[1-9]\d)$/, gr: /^(0[1-9]|[1-9]\d)$/, ver: /^(0[1-9]|[1-9]\d)(\.\d)?$/ };
  const re = strict[key];
  return function(value, callback) {
    if (!value || !re) return callback(true);
    callback(re.test(value));
  };
}
function chineseOnlyValidator(value, callback) {
  if (!value) return callback(true);
  callback(/^[\u4e00-\u9fff\u3400-\u4dbf]+$/.test(value));
}

// === Method → Desc ===
function onMethodChange(row, oldMethod, newMethod) {
  const cfg = methodDescMap[newMethod] || { mode: 'text', hint: '请先选择制作方式' };
  if (cfg.mode === 'locked') {
    hot.setDataAtRowProp(row, 'desc', cfg.value);
  } else if (!newMethod) {
    hot.setDataAtRowProp(row, 'desc', '');
  } else if (oldMethod && oldMethod !== newMethod) {
    hot.setDataAtRowProp(row, 'desc', '');
  }
  hot.render();
}

// === File Operations ===
async function addFiles() {
  const r = await call('add_files_via_dialog');
  handleAddResult(r);
}
async function addFolder() {
  const r = await call('add_folder_via_dialog');
  handleAddResult(r);
}
function onDropResult(r) {
  // 由 Python evaluate_js 调用（pywebview 原生拖拽）
  _dropCount++;
  if (_firstDrop) { _firstDrop = false; files = []; sel.clear(); }
  handleAddResult(r);
}
function handleAddResult(r) {
  if (!r || !r.files) return;
  const exist = new Set(files.map(f => f.fp || f.path));
  const fresh = r.files.filter(f => !exist.has(f.fp || f.path));
  if (fresh.length === 0) return toast('全部重复');
  files = files.concat(fresh);
  hot.updateData(buildData(files));
  updateEmpty();
  toast(`已添加 ${fresh.length} 个文件`);
  call('debug_log', `FILES: ${files.length} total (added ${fresh.length})`);
  loadThumbs();
}

async function clearAll() {
  files = [];
  sel.clear();
  _firstDrop = true;
  hot.updateData([]);
  updateEmpty();
  toast('已清空');
}

async function doRename() {
  const paths = files.map(f => f.path);
  const fields = files.map(f => f.fields);
  const r = await call('do_rename', paths, JSON.stringify(fields));
  toast(r.msg || '重命名完成');
  updateUndoButton();
}
async function doArchive() {
  const paths = files.map(f => f.path);
  const fields = files.map(f => f.fields);
  const r = await call('do_archive', paths, JSON.stringify(fields));
  toast(r.msg || '归档完成');
  updateUndoButton();
}
async function doUndo() {
  const r = await call('undo');
  if (r.ok > 0) toast(`已撤销 ${r.ok} 个`);
  else toast('无可撤销');
  updateUndoButton();
}
async function updateUndoButton() {
  const avail = await call('undo_available');
  document.getElementById('btnUndo').disabled = !avail;
}

// === Drop ===
// === Thumbnails ===
async function loadThumbs() {
  const paths = files.map(f => f.path);
  const thumbs = await call('get_thumbs', JSON.stringify(paths));
  // TODO: implement thumbnail generation
}

// === Helpers ===
function updateEmpty() {
  const el = document.getElementById('emptyMsg');
  if (files.length === 0) el.classList.add('show');
  else el.classList.remove('show');
}
function _computeTK(i) {
  let n = 1;
  const key = files[i].fields.ep + '|' + files[i].fields.sc + '|' + files[i].fields.gr;
  for (let j = 0; j < i; j++) {
    const jk = files[j].fields.ep + '|' + files[j].fields.sc + '|' + files[j].fields.gr;
    if (jk === key) n++;
  }
  return String(n).padStart(2, '0');
}
