const APP_VERSION='2.0';
const APP_BRANCH='';
const APP_BUILD_TIME='';
// ═══ 立即执行 — 确认脚本加载 ═══
document.addEventListener('DOMContentLoaded',()=>{
  document.getElementById('debugMode').textContent='JS ✓';
  // mock 模式下直接启动
  if(!window.pywebview || !window.pywebview.api) init();
});
// ═══ State ═══

// 全局错误 → toast（不沉默）
window.onerror=function(m,s,l,c,e){const msg='JS错误: '+(m||'未知')+' @ '+(s||'?')+':'+l;toast(msg);call('debug_log',msg);return false};
window.addEventListener('unhandledrejection',e=>{const msg='Promise错误: '+e.reason;toast(msg);call('debug_log',msg)});
const _origErr=console.error;console.error=function(...a){_origErr.apply(console,a);call('debug_log','CONSOLE: '+a.join(' '))};

let files=[], _firstDrop=true, sel=new Set(), methodDescMap={}, descLocked=false, undoAvail=false, _thumbs={};
const DIGIT_RULES={ep:/^\d{0,3}$/,sc:/^\d{0,2}$/,gr:/^\d{0,2}$/,ver:/^\d{0,2}(\.\d)?$/};
const DIGIT_STRICT={ep:/^(0[1-9]|[1-9]\d{1,2})$/,sc:/^(0[1-9]|[1-9]\d)$/,gr:/^(0[1-9]|[1-9]\d)$/,ver:/^(0[1-9]|[1-9]\d)(\.\d)?$/};
const tc=['#2a3a1a','#1a2a3a','#3a201a','#2a1a3a','#1a3a2a','#3a301a','#1a3a3a','#302a1a'];

// ═══ API ═══
function call(m,...a){
  try{
    if(window.pywebview&&window.pywebview.api)return window.pywebview.api[m](...a);
  }catch(e){toast("API错误: "+m);return null}
  return mock(m,...a);
}
function mock(m,...a){
  return new Promise(r=>{
    const C={ep:'01',sc:'01',gr:'01',desc:'',author:'',method:'',ver:'01',status:'OK',tk:'01'};
    switch(m){
      case'get_config':r({fields:[{key:'ep',label:'Ep 集数',def:'01',hint:'01'},{key:'sc',label:'Sc 场次',def:'01',hint:'01'},{key:'gr',label:'Gr 小场次',def:'01',hint:'01'},{key:'desc',label:'镜头描述',def:'',hint:'由制作方式决定'},{key:'method',label:'制作方式',def:'',dv:['请选择','智能分镜版','双轨版','角色专属版']},{key:'author',label:'制作者',def:'',hint:'请输入姓名'},{key:'ver',label:'版本号',def:'01',hint:'01'},{key:'status',label:'通过情况',def:'',dv:['请选择','OK','KP','NG']}],defaults:{},method_desc_map:{'智能分镜版':{mode:'locked',value:'智能分镜'},'双轨版':{mode:'dropdown',values:['请选择','智能分镜','幽灵角色','空镜','请手动输入…']},'角色专属版':{mode:'dropdown',values:['请选择','智能分镜','请手动输入…']}},name_format:[{pfx:'Ep',key:'ep'},{pfx:'Sc',key:'sc'},{pfx:'Gr',key:'gr'},{pfx:'Tk',key:'tk'},{pfx:'',key:'desc'},{pfx:'',key:'method'},{pfx:'',key:'author'},{pfx:'v',key:'ver'},{pfx:'',key:'status'}],field_rules:[{trigger:'method',targets:['desc'],map:{'智能分镜版':{desc:{locked:'智能分镜'}},'双轨版':{desc:{dropdown:['请选择','智能分镜','幽灵角色','空镜','请手动输入…']}},'角色专属版':{desc:{dropdown:['请选择','智能分镜','请手动输入…']}}}}]});break;
            case'validate_dest':r({ok:true,msg:'✓ 格式正确'});break;
      case'do_rename':r({ok:1,total:1,fail:[],renamed:[]});break;
      case'do_undo':r({ok:0,msg:'Mock: 无操作'});break;
      case'do_archive':r({ok:0,fail:['Mock mode'],total:1});break;
      case'add_files_via_dialog':case'add_folder_via_dialog':
        r({files:[
          {path:'/mock/test01.mp4',basename:'C01_男主中景_20260301_0930.mp4',ext:'.mp4',fields:{ep:'01',sc:'02',gr:'03',desc:'智能分镜',author:'张谭',method:'智能分镜版',ver:'01',status:'OK'},tags:[]},
          {path:'/mock/test02.mp4',basename:'C01_女主近景_20260301_0931.mp4',ext:'.mp4',fields:{ep:'01',sc:'02',gr:'03',desc:'空镜',author:'张谭',method:'双轨版',ver:'01',status:'OK'},tags:[]},
          {path:'/mock/test03.mp4',basename:'C01_空镜街道_20260301_0932.mp4',ext:'.mp4',fields:{ep:'01',sc:'02',gr:'03',desc:'空镜',author:'李四',method:'双轨版',ver:'01',status:'OK'},tags:[]},
          {path:'/mock/test04.mp4',basename:'C02_过肩中景_20260302_1400.mp4',ext:'.mp4',fields:{ep:'02',sc:'01',gr:'01',desc:'温时雨过肩中景',author:'温欣然',method:'角色专属版',ver:'02',status:'KP'},tags:[]},
          {path:'/mock/test05.mp4',basename:'C02_零字节文件_20260302_1401.mp4',ext:'.mp4',fields:{ep:'02',sc:'01',gr:'01',desc:'幽灵角色',author:'张谭',method:'双轨版',ver:'01',status:'OK'},tags:['zero']},
          {path:'/mock/test06.mp4',basename:'C02_缺失字段_20260302_1402.mp4',ext:'.mp4',fields:{ep:'02',sc:'01',gr:'02',desc:'',author:'',method:'',ver:'',status:''},tags:[]},
        ],total:6,duplicates:0});break;
      case'debug_log':r('ok');break;
      default:r({});
    }
  });
}

// ═══ Load ═══
async function init(){
  if(window._initialized)return;window._initialized=true;
  const dm = document.getElementById('debugMode');
  const isLive=_isLive();dm.textContent=isLive?'✔ Live':'✖ Mock';call("debug_log",`APP START: ${isLive?"pywebview":"MOCK"} mode, files=${files.length}`);

  const cfg=await call('get_config');
  methodDescMap=cfg.method_desc_map||{};_nameFmt=cfg.name_format||[];
  // 收集所有预置镜头描述值供碰撞检测
  _reservedDesc.clear();
  for(const v of Object.values(methodDescMap)){
    if(v.value)_reservedDesc.add(v.value);
    if(v.values)v.values.forEach(x=>{_reservedDesc.add(x)});
  }
  const _allFields=cfg.fields||[];
  window._fieldKeys=_allFields.filter(f=>f.key!=='tk'&&!(f.dv)).map(f=>f.key);
  window._fieldKeysAll=_allFields.filter(f=>f.key!=='tk').map(f=>f.key);
  window._fieldLabels={};_allFields.forEach(f=>{window._fieldLabels[f.key]=f.label});
  const v=APP_VERSION||'?',br=APP_BRANCH||'',t=APP_BUILD_TIME||'';document.getElementById('debugMode').textContent=(cfg.dev?'🔧 DEV ':'')+(br&&br!='main'?br+'@':'')+'v'+v+(t?' '+t:'');

  // 动态生成表头（单一事实来源，防止 HTML/JS 列序漂移）
  const theadTr = document.querySelector('#fileList thead tr');
  const baseTh = theadTr.querySelector('.col-base');
  // 字段顺序与 build_filename 一致：desc → method → author → ver → status
  const headerKeys = ['ep','sc','gr','tk','desc','method','author','ver','status'];
  const headerLabels = {ep:'Ep 集数',sc:'Sc 场次',gr:'Gr 小场次',tk:'Tk 次数',desc:'镜头描述',method:'制作方式',author:'制作者',ver:'v 版本',status:'通过'};
  headerKeys.forEach(k => {
    const th = document.createElement('th');
    th.className = 'col-'+k;
    th.textContent = headerLabels[k] || k;
    theadTr.insertBefore(th, baseTh);
  });
  window._headerKeys = headerKeys;

  // 列宽拖拽
  _initColResize();

  // 浏览器预览模式：注册 mock 拖放（500ms 后确认无 pywebview 才激活）
  setTimeout(() => {
    if(window.pywebview) return;
    const dz=document.getElementById('fileList');
    dz.addEventListener('dragover',e=>{e.preventDefault()});
    dz.addEventListener('drop',e=>{
      e.preventDefault();
      const items=[...e.dataTransfer.files].filter(f=>f.type.startsWith('video/')||f.name.match(/\.(mp4|mov|mxf|avi|mkv)$/i));
      if(!items.length)return;
      const mockFiles=items.map(f=>({
        path:f.name,basename:f.name,ext:'.'+(f.name.split('.').pop()||'mp4'),
        fields:{ep:'',sc:'',gr:'',desc:'',author:'',method:'',ver:'',status:''},
        tags:/(\.[^.]+)\1$/i.test(f.name)?['dbl_ext']:[]
      }));
      files=files.concat(mockFiles.filter(mf=>!files.some(ef=>ef.path===mf.path)));
      renderList();updButtons();
      toast('已追加 '+mockFiles.length+' 个文件 (预览模式)');
    });
  }, 500);
  // 自测（仅在无 pywebview 时运行）
  setTimeout(() => { if(!window.pywebview) _runSelfTest(); }, 500);
  _initTBodyClick();
  renderList();  // 首次渲染（空状态或 mock 数据）
}
// ═══ init — 轮询等待 pywebview 桥接 ═══
let _ready=false;
function _tryStart(){
  if(_ready)return;
  const live=!!(window.pywebview&&window.pywebview.api);
  if(!live){document.getElementById('debugMode').textContent='⏳'+Math.floor(Date.now()/1000)%100;return}
  _ready=true;
  document.getElementById('debugMode').textContent='✔ Live';
  // 测试桥接
  window.pywebview.api.echo('hello').then(r=>{
    document.getElementById('debugMode').textContent='✔ '+r.received;
    if(window._tryIv)clearInterval(window._tryIv);
    init();
  }).catch(()=>{init()});
}
window._tryIv=setInterval(_tryStart,300);


// ═══ Fields ═══
function getFields(){
  if(sel.size===0)return{};
  const ix=[...sel].sort((a,b)=>a-b)[0];
  return files[ix]?{...files[ix].fields}:{};
}

// ═══ Method → Desc ═══
let _reservedDesc=new Set();
function onMethodChange(oldMethod, newMethod, ri){
  const m = newMethod;
  const cfg=methodDescMap[m]||{mode:'text',hint:'请先选择制作方式'};
  descLocked = cfg.mode === 'locked';
  const rows = sel.size > 0 ? [...sel] : (ri !== undefined ? [ri] : []);
  const changedRows = rows.filter(r => files[r] && files[r].fields.method === oldMethod && oldMethod !== m);
  call('debug_log',`onMethodChange: rows=${rows.length} sel=${sel.size} changed=${changedRows.length} old='${oldMethod||'(空)'}' new='${m||'(空)'}'`);
  if(!changedRows.length) return;
  changedRows.forEach(r => { files[r].fields.method = m; });
  if(cfg.mode === 'locked'){
    changedRows.forEach(r => { files[r].fields.desc = cfg.value; });
  } else if(m === ''){
    // 请选择 → 清空 desc 并锁定
    changedRows.forEach(r => { files[r].fields.desc = ''; });
  } else {
    changedRows.forEach(r => { files[r].fields.desc = ''; });
  }
  renderList(true); updButtons();
  // desc 高亮闪现
  changedRows.forEach(r => {
    const td = document.querySelector(`#fileList tbody tr[data-index="${r}"] td.col-desc`);
    if(td){td.classList.add('flash');setTimeout(()=>td.classList.remove('flash'),400)}
  });
  call('debug_log',`method→desc: ${changedRows.length} rows → desc='${files[changedRows[0]].fields.desc||'(空)'}' (mode=${cfg.mode})`);
}
function _checkDescCollision(v){
  if(v&&_reservedDesc.has(v)){call('debug_log','desc collision: '+v);toast('⚠ 镜头描述与预置词「'+v+'」冲突')}
}
// ═══ File List ═══
/* ═════════════════════════════
   TABLE renderList (replaces card view)
   ═════════════════════════════ */
function renderList(force){
  // 按 fp 去重（pywebview 重放可能产生幽灵条目）
  const seen = new Set();
  files = files.filter(f => {
    const k = f.fp || f.path;
    if(seen.has(k)){call('debug_log','renderList: DROP dup fp='+k.slice(0,50));return false}
    seen.add(k); return true;
  });

  const tbody = document.querySelector('#fileList tbody');
  const empty = document.querySelector('#fileList .fl-empty');
  const thead = document.querySelector('#fileList thead');
  if(files.length === 0){
    tbody.innerHTML = '';
    empty.classList.add('show');
    if(thead) thead.style.display = 'none';
    updCount(); updButtons();
    return;
  }
  empty.classList.remove('show');
  if(thead) thead.style.display = '';

  const rows = [...tbody.querySelectorAll('tr')];
  if(force || rows.length !== files.length){
    // 去重：pywebview evaluate_js 重放可能产生幽灵条目
    const seen = new Set(); const deduped = [];
    for(const f of files){
      const k = f.fp || f.path;
      if(!seen.has(k)){seen.add(k); deduped.push(f);}
    }
    if(deduped.length !== files.length){
      files = deduped;
    }
    call('debug_log',`renderList: FORCE rows=${rows.length} files=${files.length}`);
    tbody.innerHTML = '';
    files.forEach((f,i)=>{ tbody.appendChild(_buildRow(f,i)); });
  } else {
    files.forEach((f,i)=>{
      const tr = rows[i];
      tr.className = ''; tr.dataset.index = i; tr.dataset.path = f.path;
      if(sel.has(i)) tr.classList.add('sel');
      const ff = {...f.fields, tk: _computeTK(i)};
      const ready = ff.ep && ff.sc && ff.gr && ff.desc && ff.author && ff.method && ff.ver && ff.status;
      tr.classList.add(ready?'rdy':'mis');
      if(f.archived) tr.classList.add('archived');
      const fillCount = [ff.ep, ff.sc, ff.gr, ff.desc, ff.method, ff.author, ff.ver, ff.status].filter(Boolean).length;
      tr.classList.add(fillCount === 8 ? 'row-full' : fillCount >= 5 ? 'row-most' : 'row-empty');
      const tags = f.tags||[];
      if(tags.length) tr.classList.add('warn');
      if(tags.includes('zero')) tr.classList.add('warn-zero');
      if(tags.includes('size')) tr.classList.add('warn-size');
      if(tags.includes('dbl_ext')) tr.classList.add('warn-dbl');
    });
  }
  updCount(); updButtons();
}

function _buildRow(f,i){
  const tr = document.createElement('tr');
  tr.dataset.index = i; tr.dataset.path = f.path;
  const ff = {...f.fields, tk: _computeTK(i)};
  const ready = ff.ep && ff.sc && ff.gr && ff.desc && ff.author && ff.method && ff.ver && ff.status;
  if(sel.has(i)) tr.classList.add('sel');
  tr.classList.add(ready?'rdy':'mis');
  if(f.archived) tr.classList.add('archived');
  // 行完成度色条
  const fillCount = [ff.ep, ff.sc, ff.gr, ff.desc, ff.method, ff.author, ff.ver, ff.status].filter(Boolean).length;
  tr.classList.add(fillCount === 8 ? 'row-full' : fillCount >= 5 ? 'row-most' : 'row-empty');
  const tags = f.tags||[];
  if(tags.length) tr.classList.add('warn');
  if(tags.includes('zero')) tr.classList.add('warn-zero');
  if(tags.includes('size')) tr.classList.add('warn-size');
  if(tags.includes('dbl_ext')) tr.classList.add('warn-dbl');

  const tdNum = document.createElement('td');
  tdNum.className = 'col-num'; tdNum.dataset.row = i;
  tdNum.appendChild(Object.assign(document.createElement('span'),{textContent:i+1}));
  tr.appendChild(tdNum);

  const tdThumb = document.createElement('td');
  tdThumb.className = 'col-thumb';
  const tsrc = _thumbs[f.path];
  if(tsrc){
    const img = document.createElement('img');
    img.className = 'cell-thumb'; img.src = tsrc; img.alt = '';
    tdThumb.appendChild(img);
  } else {
    const div = document.createElement('div');
    div.className = 'cell-thumb';
    div.style.background = `linear-gradient(135deg,${tc[i%tc.length]},${tc[(i+2)%tc.length]})`;
    tdThumb.appendChild(div);
  }
  tr.appendChild(tdThumb);

  for(const key of (window._headerKeys||['ep','sc','gr','tk','desc','method','author','ver','status'])){
    tr.appendChild(buildCellTD(key, ff, i));
  }

  const tdBase = document.createElement('td');
  tdBase.className = 'col-base';
  let baseText = f.basename || '';
  const tooltips = [];
  if(tags.length){
    const lbl={zero:'⚠零字节',size:'⚠大小异常',dbl_ext:'⚠双扩展名'};
    tooltips.push(...tags.map(t=>lbl[t]||t));
    baseText += ' · ' + tags.map((t,i)=>i<2?'⚠':'').join('');
  }
  if(!ready){
    const lb={ep:'Ep',sc:'Sc',gr:'Gr',desc:'描述',author:'作者',method:'方式',ver:'版本',status:'通过'};
    for(const k of ['ep','sc','gr','desc','author','method','ver','status']){
      if(!ff[k]) tooltips.push('✎缺失: '+lb[k]);
    }
  }
  const sBase = Object.assign(document.createElement('span'),{textContent:baseText});
  tdBase.appendChild(sBase);
  if(tooltips.length) tdBase.title = tooltips.join('\n');
  tr.appendChild(tdBase);
  return tr;
}

// ═══ tbody 事件委派 ═══
function _initTBodyClick(){
  const tbody = document.querySelector('#fileList tbody');
  if(!tbody || tbody._clickInit) return;
  tbody._clickInit = true;
  tbody.addEventListener('click', e => {
    const td = e.target.closest('td');
    if(!td) return;
    const tr = td.closest('tr');
    if(!tr) return;
    const i = parseInt(tr.dataset.index);
    if(isNaN(i)) return;
    if(files[i] && files[i].archived) return;  // 已归档，不可编辑
    if(td.classList.contains('editing')) return;
    const key = td.dataset.key;
    call('debug_log',`click: td=${td.className} i=${i} key=${key||'-'} detail=${e.detail}`);
    const isField = key && key !== 'tk' && !td.classList.contains('locked') && !td.classList.contains('readonly');

    if(isField){
      if(e.detail >= 2){
        // 浏览器原生双击
        clearTimeout(window._shrinkTimer);
        call('debug_log',`dblClick (detail=${e.detail}): activate ${key} on row ${i}`);
        activateEdit(td, key, i);
      } else {
        call('debug_log',`singleClick: rowClick ${i}`);
        rowClick(e, i);
      }
      return;
    }
    rowClick(e, i);
  });
}

function rowClick(e, i){
  if(e.metaKey || e.ctrlKey){
    if(sel.has(i)){sel.delete(i);call('debug_log',`rowClick: Cmd-del ${i} sel=${sel.size}`);}
    else{sel.add(i);call('debug_log',`rowClick: Cmd-add ${i} sel=${sel.size}`);}
  } else if(e.shiftKey && sel.size > 0){
    const s = [...sel].sort((a,b)=>a-b);
    const lo = Math.min(s[0], i);
    const hi = Math.max(s[0], i);
    for(let j=lo; j<=hi; j++) sel.add(j);
    call('debug_log',`rowClick: Shift ${lo}-${hi} sel=${sel.size}`);
  } else if(sel.has(i)){
    if(sel.size > 1){
      // 多选态点已选行 → 延迟 350ms：双击编辑，单击收缩
      clearTimeout(window._shrinkTimer);
      window._shrinkTimer = setTimeout(() => {
        sel.clear(); sel.add(i);
        call('debug_log',`rowClick: shrink-to ${i} sel=${sel.size}`);
        renderList(); updButtons();
      }, 350);
      return;
    } else {
      call('debug_log',`rowClick: SKIP already-single ${i}`);
      return;
    }
  } else {
    sel.clear(); sel.add(i);
    call('debug_log',`rowClick: single ${i} sel=${sel.size}`);
  }
  renderList(); updButtons();
}

function buildCellTD(key, ff, i){
  const td = document.createElement('td');
  td.className = `col-${key}`;
  td.dataset.key = key;
  td.dataset.row = i;

  const v = ff[key] || '';
  td.dataset.value = v;

  if(key === 'tk'){
    const s = document.createElement('span'); s.textContent = v;
    td.appendChild(s);
    td.classList.add('readonly');
    return td;
  }

  // locked desc: 灰化
  if(key === 'desc'){
    const method = files[i].fields.method || '';
    const cfg = methodDescMap[method];
    if(!cfg){
      const s = document.createElement('span'); s.textContent = '—';
      td.appendChild(s);
      td.classList.add('readonly','empty');
      return td;
    }
    if(cfg.mode === 'locked'){
      const s = document.createElement('span'); s.textContent = v || '—';
      td.appendChild(s);
      td.classList.add('locked');
      if(!v) td.classList.add('empty');
      return td;
    }
  }

  // Default: span wrapping for consistent click target
  const s = document.createElement('span');
  s.textContent = v || '—';
  if(v === '' || v === '请选择' || v === '请手动输入…'){
    s.textContent = '—';
    td.classList.add('empty');
  }
  td.appendChild(s);

  // 点击编辑由 tr click handler 统一分发
  return td;
}

function activateEdit(td, key, i){
  if(td.classList.contains('editing')){call('debug_log',`activateEdit: SKIP already editing ${key}`);return;}
  call('debug_log',`activateEdit: key=${key} i=${i} oldVal='${td.dataset.value||'(空)'}' sel=${sel.size}`);
  if(window._activeCancel){ window._activeCancel(); window._activeCancel = null; }
  if(sel.size > 1 && sel.has(i)){
    const lbls = {ep:'Ep 集数',sc:'Sc 场次',gr:'Gr 小场次',desc:'镜头描述',author:'制作者',method:'制作方式',ver:'版本号',status:'通过情况'};
    toast('编辑 '+sel.size+' 个文件的 '+ (lbls[key]||key));
  }
  const oldVal = td.dataset.value;
  const isSelect = (key === 'method' || key === 'status' || (key === 'desc' && files[i] && files[i].fields.method && methodDescMap[files[i].fields.method] && methodDescMap[files[i].fields.method].mode === 'dropdown'));
  let el;

  if(key === 'method'){
    el = document.createElement('select');
    const opts = ['请选择','智能分镜版','双轨版','角色专属版'];
    opts.forEach(m => {
      const o = document.createElement('option'); o.value = m === '请选择' ? '' : m; o.textContent = m;
      if(m === oldVal) o.selected = true;
      el.appendChild(o);
    });
  } else if(key === 'status'){
    el = document.createElement('select');
    ['OK','KP','NG',''].forEach(s => {
      const o = document.createElement('option'); o.value = s; o.textContent = s || '—';
      if(s === oldVal) o.selected = true;
      el.appendChild(o);
    });
  } else if(key === 'desc'){
    const method = files[i].fields.method || '';
    const cfg = methodDescMap[method] || {mode:'text',hint:'输入镜头描述'};
    if(cfg.mode === 'locked'){
      el = document.createElement('input'); el.type = 'text'; el.value = cfg.value || ''; el.readOnly = true;
    } else if(cfg.mode === 'dropdown'){
      const rawOpts = cfg.values||[];
      if(rawOpts.includes('请手动输入…')){
        el = document.createElement('select');
        rawOpts.filter(o => o !== '请手动输入…').forEach(opt => {
          const o = document.createElement('option'); o.value = opt; o.textContent = opt;
          if(opt === oldVal) o.selected = true;
          el.appendChild(o);
        });
        const o = document.createElement('option'); o.value = '__free__'; o.textContent = '✐ 手动输入…';
        el.appendChild(o);
      } else {
        el = document.createElement('select');
        rawOpts.forEach(opt => {
          const o = document.createElement('option'); o.value = opt; o.textContent = opt;
          if(opt === oldVal) o.selected = true;
          el.appendChild(o);
        });
      }
    } else {
      el = document.createElement('input'); el.type = 'text'; el.value = oldVal;
      el.placeholder = cfg.hint || '输入镜头描述';
    }
  } else {
    el = document.createElement('input'); el.type = 'text'; el.value = oldVal;
    if(['ep','sc','gr','ver'].includes(key)) el.setAttribute('inputmode','numeric');
    if(key === 'author') el.placeholder = '请输入姓名';
  }

  td.classList.add('editing');
  td.textContent = '';
  td.appendChild(el);
  if(el.tagName === 'INPUT' && !el.readOnly){ el.focus(); el.select(); }
  else { el.focus(); }

  // 制作者：实时过滤非中文
  if(key === 'author'){
    el.addEventListener('input', () => {
      const pos = el.selectionStart;
      el.value = el.value.replace(/[^\u4e00-\u9fff\u3400-\u4dbf]/g, '');
      el.selectionStart = el.selectionEnd = Math.min(pos, el.value.length);
    });
  }

  // ═══ Commit logic ═══
  const commit = (cancel) => {
    const v = (el.value||'').trim();
    el.remove(); // 物理销毁编辑控件，杜绝残留
    td.classList.remove('editing');
    if(cancel){
      call('debug_log',`commit: CANCEL ${key} restore='${oldVal||'(空)'}'`);
      td.textContent = oldVal || (oldVal===''||oldVal==='请选择'||oldVal==='请手动输入…'?'—':oldVal);
      if(oldVal === '' || oldVal === '请选择' || oldVal === '请手动输入…') td.classList.add('empty');
      return;
    }
    let finalVal = v;
    if(key === 'author') finalVal = v.replace(/[^\u4e00-\u9fff\u3400-\u4dbf]/g, '');
    if(key === 'desc') finalVal = v.replace(/_/g, '');
    if(key === 'desc' && finalVal && !isSelect) _checkDescCollision(finalVal);

    if(finalVal !== oldVal){
      if(key === 'method'){
        onMethodChange(oldVal, finalVal, i);
        return;
      }
      const rows = sel.size > 1 ? [...sel] : [i];
      rows.forEach(r => { files[r].fields[key] = finalVal; });
      call('debug_log',`edit ${key}: ${oldVal||'(空)'} → ${finalVal||'(空)'} on ${rows.length} row(s)`);
      renderList(true);
      return;
    }
    // 值没变 → 恢复显示，增量更新
    call('debug_log',`commit: NOCHANGE ${key} val='${finalVal||'(空)'}'`);
    const s = document.createElement('span');
    s.textContent = oldVal || (oldVal===''||oldVal==='请选择'||oldVal==='请手动输入…'?'—':oldVal);
    td.appendChild(s);
    if(oldVal === '' || oldVal === '请选择' || oldVal === '请手动输入…') td.classList.add('empty');
    renderList();
  };

    // SELECT: change/Escape only. Click-outside → revert without commit.
    if(isSelect){
      const cancel = () => commit(true);
      window._activeCancel = cancel;
      el.addEventListener('change', () => {
        if(el.value === '__free__'){
          // 自由输入 → 切换为 input
          el.remove();
          const input = document.createElement('input');
          input.type = 'text'; input.placeholder = '输入镜头描述';
          input.value = (oldVal === '请手动输入…' || oldVal === '请选择') ? '' : oldVal;
          td.appendChild(input);
          input.focus(); input.select();
          el = input; // 更新引用，确保 commit 读到输入值
          // 重新绑定 INPUT 事件
          let _focused = false;
          window._activeCancel = () => commit(true);
          input.addEventListener('focus', () => { _focused = true; });
          input.addEventListener('keydown', e => {
            if(e.key === 'Enter'){ e.preventDefault(); window._activeCancel = null; commit(false); }
            if(e.key === 'Escape'){ input.value = oldVal; window._activeCancel = null; commit(true); }
          });
          input.addEventListener('blur', () => {
            if(window._activeCancel){ window._activeCancel = null; commit(false); }
          });
        } else {
          window._activeCancel = null; commit(false);
        }
      });
  } else {
    // INPUT: 响应 Enter / Escape / blur
    let _focused = false;
    window._activeCancel = () => commit(true);
    el.addEventListener('focus', () => { _focused = true; });
    el.addEventListener('keydown', e => {
      if(e.key === 'Enter'){ e.preventDefault(); window._activeCancel = null; commit(false); }
      if(e.key === 'Escape'){ el.value = oldVal; window._activeCancel = null; commit(true); }
    });
    el.addEventListener('blur', () => {
      if(window._activeCancel){ window._activeCancel = null; commit(false); }
    });
  }
}
function updCount(){
  let ok2=0;files.forEach(f=>{const ff=f.fields;if(ff.ep&&ff.sc&&ff.gr&&ff.desc&&ff.author&&ff.method&&ff.ver&&ff.status)ok2++});document.getElementById('fileCount').innerHTML=`文件列表 · <span style="color:var(--green)">${ok2}</span>/${files.length} 就绪  ·  选中 ${sel.size}`;
}

function updButtons(){
  const hf=files.length>0,hs=sel.size>0,fd=getFields();
  // af: 用文件实际数据算（不用 inspector，避免混合态误判）
  let af=true;
  if(hs){for(const i of sel){const ff=files[i].fields;let ok=true;for(const k of (window._fieldKeysAll||['ep','sc','gr','desc','author','method','ver','status'])){if(!ff[k]){ok=false;break}}if(!ok){af=false;break}}}
  document.getElementById('btnRename').disabled=!(hs&&af);
  document.getElementById('btnArchive').disabled=!(hs&&af);
  document.getElementById('btnUndo').disabled=!undoAvail;
  const dot=document.querySelector('.sb-dot');
  if(!hf){dot.style.background='var(--green)';setStatus('就绪  ·  Ctrl+Z 撤销  ·  Del 移除');return}
  // 全就绪
  if(hs&&af){dot.style.background='var(--green)';setStatus('字段齐全，可以重命名');return}
  // 混合态标注（与缺失区分）
  const missing=[];
  const _lbs=window._fieldLabels||{};
  for(const k of (window._fieldKeysAll||['ep','sc','gr','desc','author','method','ver','status'])){if(!fd[k])missing.push(_lbs[k]||k)}
  // 检查警告
  let warn=[];
  for(const t of files){if(t.tags&&t.tags.length)warn.push(...t.tags)}
  if(warn.length){const wl={zero:'零字节',size:'大小异常',dbl_ext:'双扩展名'};dot.style.background='var(--red)';setStatus('⚠ '+[...new Set(warn)].map(w=>wl[w]||w).join(' · '));return}
  dot.style.background='var(--yellow)';
  let t_ok=0;files.forEach(f=>{const ff=f.fields;if(ff.ep&&ff.sc&&ff.gr&&ff.desc&&ff.author&&ff.method&&ff.ver&&ff.status)t_ok++});
  let msg=missing.length?('缺失: '+missing.join(' · ')):'';
  if(!msg)msg='就绪  ·  Ctrl+Z 撤销';
  setStatus(msg+'  ·  '+t_ok+'/'+files.length+' 就绪');
}

// ═══ Dialog ═══
function showDialog(title,msg){return new Promise(r=>{
  document.getElementById('dialogTitle').textContent=title;
  document.getElementById('dialogMsg').textContent=msg;
  document.getElementById('dialogOverlay').classList.add('show');
  document.getElementById('dialogOk').onclick=()=>{document.getElementById('dialogOverlay').classList.remove('show');r(true)};
  document.getElementById('dialogCancel').onclick=()=>{document.getElementById('dialogOverlay').classList.remove('show');r(false)};
})}

// ═══ Actions ═══
async function addFiles(){const r=await call('add_files_via_dialog');if(r&&r.files){const ex=new Set(files.map(f=>f.path));const fr=r.files.filter(f=>!ex.has(f.path));files=files.concat(fr);r.total=fr.length;r.duplicates=r.files.length-fr.length;call("debug_log",`FILES list: ${files.length} total (addFiles)`);renderList();_toastResult(r);loadThumbs()}}
async function addFolder(){const r=await call('add_folder_via_dialog');if(r&&r.files){const ex=new Set(files.map(f=>f.path));const fr=r.files.filter(f=>!ex.has(f.path));files=files.concat(fr);r.total=fr.length;r.duplicates=r.files.length-fr.length;call("debug_log",`FILES list: ${files.length} total (addFiles)`);renderList();_toastResult(r);loadThumbs()}}
function _toastResult(r){let m=`已追加 ${r.total} 个文件`;if(r.duplicates)m+=` · ${r.duplicates} 个重复跳过`;if(r.subdirs_skipped)m+=` · ${r.subdirs_skipped} 个子文件夹跳过`;if(r.truncated)m+=` (上限${r.max}个)`;toast(m)}

async function doRename(){
  if(sel.size===0)return;
  const srt=[...sel].sort((a,b)=>a-b);
  // 用每个文件自己的 fields，不是 inspector 全局值
  const sfs=srt.map((i,p)=>{
    const f={...files[i]};
    f.fields={...f.fields,tk:buildTK(i)};
    return f;
  });
  const nm=buildName(sfs[0].fields)+sfs[0].ext;
  const msg=sfs.length===1?`确认重命名?\n${sfs[0].basename}\n→ ${nm}`:`确认重命名 ${sfs.length} 个?\n${buildName(sfs[0].fields)+sfs[0].ext}\n  ...\n${buildName(sfs[sfs.length-1].fields)+sfs[sfs.length-1].ext}`;
  if(!await showDialog('确认重命名',msg))return;
  call('debug_log','rename: starting '+sfs.length+' files');
  const r=await call('do_rename',sfs);
  call('debug_log','rename: ok='+r.ok+' fail='+(r.fail||[]).length+' depth='+(r.stack_depth||0));
  if(r.ok>0){undoAvail=true;
    r.renamed.forEach(rn=>{const f=files.find(x=>x.path===rn.old_path);if(f)f.path=rn.new_path});
    // 缩略图 key 同步更新
    r.renamed.forEach(rn=>{if(_thumbs[rn.old_path]){_thumbs[rn.new_path]=_thumbs[rn.old_path];delete _thumbs[rn.old_path]}});
    toast(`完成 ${r.ok}/${r.total}`); result(`✅ 重命名完成 ${r.ok}/${r.total}`)}
  if(r.fail&&r.fail.length){setTimeout(()=>toast('失败: '+r.fail.join('; ')),2000)}
  renderList();updButtons();
}
function buildTK(i){
  const fs=files[i].fields;
  const k=fs.ep+'|'+fs.sc+'|'+fs.gr+'|'+(fs.desc||'')+'|'+(fs.method||'')+'|'+fs.ver;
  let n=0;
  for(let j=0;j<=i;j++){
    const g=files[j].fields;
    const jk=g.ep+'|'+g.sc+'|'+g.gr+'|'+(g.desc||'')+'|'+(g.method||'')+'|'+g.ver;
    if(jk===k)n++;
  }
  return String(n).padStart(2,'0');
}
function _computeTK(i){return buildTK(i)}
let _nameFmt=[];
function buildName(f){
  const raw=_nameFmt.map(s=>s.pfx+(f[s.key]||'')).join('_');
  return raw.replace(/_+/g,'_').replace(/_$/,'');
}
async function doUndo(){
  call('debug_log','undo: starting');
  const r=await call('do_undo');
  call('debug_log','undo: ok='+r.ok+' remaining='+(r.remaining||0)+' type='+(r.type||'rename'));
  toast(r.msg);result(r.msg);
  undoAvail=(r.remaining||0)>0;
  if(r.type === 'archive'){
    // 撤销归档：去掉 archived 标记（rn.new_path = 源路径）
    if(r.renamed){
      r.renamed.forEach(rn => {
        const f=files.find(x=>x.path===rn.new_path);
        if(f) delete f.archived;
      });
    }
  }else if(r.renamed){
    r.renamed.forEach(rn=>{
      const f=files.find(x=>x.path===rn.old_path);
      if(f)f.path=rn.new_path;
      if(_thumbs[rn.old_path]){_thumbs[rn.new_path]=_thumbs[rn.old_path];delete _thumbs[rn.old_path]}
    });
  }
  renderList();updButtons();
}

function removeSelected(){if(sel.size===0)return;call('debug_log','remove: '+sel.size+' files');files=files.filter((_,i)=>!sel.has(i));sel.clear();renderList();toast('已移除')}
async function doArchive(){
  if(sel.size===0){toast('未选中文件');return}
  const dest=document.getElementById('destInput').value.trim();
  if(!dest){toast('请先输入目标路径');return}
  const srt=[...sel].sort((a,b)=>a-b);
  const sfs=srt.map((i,p)=>{const f={...files[i]};f.fields={...f.fields,tk:buildTK(i)};return f});
  if(!await showDialog('确认归档',`确认归档 ${sfs.length} 个文件到?\n${dest}/EP${sfs[0].fields.ep||'??'}/SC${sfs[0].fields.sc||'??'}/...`))return;
  call('debug_log','archive: starting');
  const r=await call('do_archive',sfs,dest);
  call('debug_log','archive: result='+JSON.stringify({ok:r.ok,total:r.total,dup:r.dup||0}));
  if(r.ok>0){
    // 标记已归档
    srt.forEach(i => { files[i].archived = true; });
    sel.clear();
    undoAvail = true;
  }
  let m=`归档完成 ${r.ok} 个`;if(r.dup>0)m+=` · ${r.dup} 个重复已跳过`;if(r.fail&&r.fail.length>0)m+=` · ${r.fail.length} 失败`;toast(m);result(m);
  renderList();updButtons();
}
// ═══ Thumbnails ═══
async function loadThumbs(){
  const paths=files.map(f=>f.path);
  call('debug_log','loadThumbs: '+paths.length+' files');
  const r=await call('generate_thumbnails',paths);
  call('debug_log','loadThumbs done: '+(r?r.total:0)+' thumbs');
}

async function loadThumbsEx(paths){
  call('debug_log','loadThumbsEx: '+paths.length+' files');
  const r=await call('generate_thumbnails',paths);
  call('debug_log','loadThumbsEx done: '+(r?r.total:0)+' thumbs');
}

function setThumb(path,thumb){
  _thumbs[path]=thumb;
  const el=document.querySelector(`[data-path="${CSS.escape(path)}"]`);
  if(!el)return;
  let thumbEl=el.querySelector('.cell-thumb');
  if(thumbEl&&thumbEl.tagName==='DIV'){
    const img=document.createElement('img');
    img.className='cell-thumb';img.src=thumb;img.alt='';
    thumbEl.replaceWith(img);
  }else if(thumbEl){
    thumbEl.src=thumb;
  }
}
function _thumbScale(){const v=getComputedStyle(document.querySelector('.file-section')).getPropertyValue('--thumb-scale');return parseFloat(v)||1}
function setStatus(s){document.getElementById('statusText').textContent=s}

// ═══ Drag & Drop 遮罩 — 只在文件列表区 ═══
function _isLive(){return!!(window.pywebview&&window.pywebview.api)}
let dg=0;
const dropZone=document.getElementById('fileList');
const overlay=document.getElementById('dropOverlay');
dropZone.addEventListener('dragover',e=>{e.preventDefault();if(e.dataTransfer)e.dataTransfer.dropEffect='copy'});
dropZone.addEventListener('dragenter',e=>{e.preventDefault();dg++;overlay.classList.add('show')});
dropZone.addEventListener('dragleave',e=>{e.preventDefault();dg--;if(dg<=0){dg=0;overlay.classList.remove('show')}});
dropZone.addEventListener('drop',e=>{e.preventDefault();dg=0;overlay.classList.remove('show')});

// ═══ Drop results from Python ═══
let _dropCount=0;
function onDropResult(result){
  if(!result||!result.files) return;
  _dropCount++;
  if(_firstDrop){_firstDrop=false;call('debug_log',`_firstDrop: was ${files.length}, clearing`);files=[];sel.clear()}
  call('debug_log',`onDropResult #${_dropCount}: ${result.files.length} files, existing=${files.length}`);
  const exist=new Set(files.map(f=>f.fp||f.path));
  const fresh=result.files.filter(f=>!(exist.has(f.fp||f.path)));
  const dup = result.duplicates || (result.files.length - fresh.length);
  if(fresh.length===0){toast(`全部重复 · ${dup} 个已跳过`);return}
  files=files.concat(fresh);
  call("debug_log",`FILES list: ${files.length} total (added ${fresh.length})`);
  let msg=`已追加 ${fresh.length} 个文件`;
  if(dup) msg+=` · ${dup} 个重复跳过`;
  if(result.subdirs_skipped) msg+=` · ${result.subdirs_skipped} 个子文件夹跳过`;
  if(result.truncated) msg+=` (上限${result.max}个)`;
  renderList();toast(msg);
  loadThumbs();
}

// ═══ Keyboard ═══
document.addEventListener('keydown',e=>{
  if((e.ctrlKey||e.metaKey)&&e.key==='z'){e.preventDefault();doUndo()}
  if((e.key==='Delete'||e.key==='Backspace')&&e.target.tagName!=='INPUT'&&e.target.tagName!=='SELECT'){e.preventDefault();removeSelected()}
  // ↑↓ 切换文件
  if((e.key==='ArrowUp'||e.key==='ArrowDown')&&sel.size===1&&files.length>0){
    if(e.target.tagName!=='INPUT'||(e.key==='ArrowUp'&&e.target.selectionStart===0)||(e.key==='ArrowDown'&&e.target.selectionStart===e.target.value.length)){
      e.preventDefault();
      const cur=[...sel][0];
      const next=cur+(e.key==='ArrowDown'?1:-1);
      if(next>=0&&next<files.length){sel.clear();sel.add(next);renderList();updButtons()}
    }
  }
  // Home → 第一个文件, End → 最后一个
  if((e.key==='Home'||e.key==='End')&&sel.size===1&&files.length>0){
    if(e.target.tagName!=='INPUT'||e.target.selectionStart===0){
      e.preventDefault();
      const i=e.key==='Home'?0:files.length-1;
      sel.clear();sel.add(i);renderList();updButtons();
    }
  }
  // Cmd+A: input 里正常全选；其他位置 → 全选文件列表
  if((e.metaKey||e.ctrlKey)&&e.key==='a'){
    if(e.target.tagName==='INPUT'||e.target.tagName==='TEXTAREA')return;
    e.preventDefault();
    sel=new Set([...Array(files.length).keys()]);
    renderList();updButtons();
  }
});

// ═══ Dest validation（smb:// 静默转换，前端不跳） ═══
const di=document.getElementById('destInput'),ds=document.getElementById('destStatus');
di.addEventListener('input',async ()=>{
  const r=await call('validate_dest',di.value);
  ds.textContent=r.msg||'';ds.style.color=r.ok?'var(--green)':'var(--red)';
  updButtons();
});

// ═══ Dest: browse button (无拖拽) ═══
document.getElementById('btnBrowseDest').addEventListener('click',async ()=>{
  const r=await call('pick_dest_folder');
  if(r&&r.path){document.getElementById('destInput').value=r.path;di.dispatchEvent(new Event('input'))}
});

// ═══ Buttons + Zoom ═══
document.getElementById('btnAddBig').addEventListener('click',addFiles);
document.getElementById('btnRename').addEventListener('click',doRename);
document.getElementById('btnArchive').addEventListener('click',doArchive);
document.getElementById('btnUndo').addEventListener('click',doUndo);

// 缩放滑块
const zs=document.getElementById('zoomSlider'),zl=document.getElementById('zoomLabel');
let _zoomTimer=null;
zs.addEventListener('input',()=>{
  const v=parseInt(zs.value);
  zl.textContent=v+'%';
  document.querySelector('.file-section').style.setProperty('--thumb-scale',v/100);
  clearTimeout(_zoomTimer);
  _zoomTimer=setTimeout(()=>renderList(),80);
});
// Cmd+滚轮 也支持缩放
document.getElementById('fileList').addEventListener('wheel',e=>{
  if(e.metaKey||e.ctrlKey){
    e.preventDefault();
    zs.value=Math.max(50,Math.min(200,parseInt(zs.value)+(e.deltaY<0?10:-10)));
    zs.dispatchEvent(new Event('input'));
  }
});

// ═══ Column resize ═══
let _resizing=null;
function _initColResize(){
  const thead=document.querySelector('#fileList thead');
  if(!thead)return;
  thead.querySelectorAll('th:not(.col-base)').forEach(th=>{
    th.addEventListener('mousedown',e=>{
      const rect=th.getBoundingClientRect();
      if(e.clientX < rect.right-6 || e.clientX > rect.right+2) return; // 只响应右边缘 6px
      e.preventDefault();
      _resizing={th, startX:e.clientX, startW:rect.width, ghost:null};
      const ghost=document.createElement('div');
      ghost.className='resize-ghost';
      ghost.style.left=rect.right+'px';
      ghost.style.top=rect.top+'px';
      ghost.style.height=rect.height+'px';
      document.body.appendChild(ghost);
      _resizing.ghost=ghost;
      th.classList.add('resizing');
    });
  });
  document.addEventListener('mousemove',e=>{
    if(!_resizing)return;
    const dx=e.clientX-_resizing.startX;
    const nw=Math.max(32, _resizing.startW+dx);
    _resizing.ghost.style.left=(_resizing.th.getBoundingClientRect().left+nw)+'px';
  });
  document.addEventListener('mouseup',()=>{
    if(!_resizing)return;
    const rect=_resizing.th.getBoundingClientRect();
    const nw=Math.max(32, rect.width+(_resizing.ghost?parseInt(_resizing.ghost.style.left)-rect.right:0));
    _resizing.th.style.width=nw+'px';
    _resizing.th.style.minWidth=nw+'px';
    _resizing.th.classList.remove('resizing');
    if(_resizing.ghost){_resizing.ghost.remove();_resizing.ghost=null}
    _resizing=null;
  });
}

// ═══ Self-test (mock mode) ═══
function _runSelfTest(){
  call('debug_log','_runSelfTest: START');
  const ok=[],fail=[];
  function t(name,fn){try{fn();ok.push(name)}catch(e){fail.push(name+': '+e.message)}}
  t('files array',()=>{if(!Array.isArray(files))throw new Error('files not array')});
  t('sel is Set',()=>{if(!(sel instanceof Set))throw new Error('sel not Set')});
  t('methodDescMap',()=>{if(Object.keys(methodDescMap).length<3)throw new Error('methodDescMap empty')});
  t('_nameFmt',()=>{if(!Array.isArray(_nameFmt))throw new Error('_nameFmt not array')});
  t('_reservedDesc',()=>{if(_reservedDesc.size<3)throw new Error('_reservedDesc empty')});
  t('descLocked boolean',()=>{if(typeof descLocked!=='boolean')throw new Error('descLocked not bool')});
  t('DIGIT_RULES',()=>{if(!DIGIT_RULES.ep)throw new Error('DIGIT_RULES missing')});
  t('_computeTK',()=>{
    files=[{fields:{ep:'01',sc:'01',gr:'01',desc:'A',method:'X',ver:'01'}}];
    sel.add(0);
    const tk=_computeTK(0);
    files=[];sel.clear();
    if(tk!=='01')throw new Error('_computeTK returned '+tk);
  });
  t('onMethodChange locked',()=>{
    files=[{fields:{ep:'01',sc:'01',gr:'01',desc:'',author:'',method:'',ver:'01',status:''}}];
    sel.add(0);
    onMethodChange('','智能分镜版',0);
    const desc=files[0].fields.desc;
    const ok2=desc==='智能分镜';
    files=[];sel.clear();
    if(!ok2)throw new Error('desc='+desc+' expected 智能分镜');
  });
  t('onMethodChange dropdown',()=>{
    files=[{fields:{ep:'01',sc:'01',gr:'01',desc:'空镜',author:'',method:'双轨版',ver:'01',status:''}}];
    sel.add(0);
    onMethodChange('双轨版','角色专属版',0);
    const desc=files[0].fields.desc;
    files=[];sel.clear();
    if(desc!=='')throw new Error('desc='+desc+' expected empty after dropdown clear');
  });
  t('buildTK desc',()=>{
    files=[
      {fields:{ep:'01',sc:'01',gr:'01',desc:'A',method:'X',ver:'01'}},
      {fields:{ep:'01',sc:'01',gr:'01',desc:'A',method:'X',ver:'01'}},
    ];
    const t2=buildTK(1);
    files=[];
    if(t2!=='02')throw new Error('buildTK returned '+t2+' expected 02');
  });
  t('buildName',()=>{
    const nm=buildName({ep:'01',sc:'02',gr:'03',tk:'01',desc:'智能分镜',author:'张谭',method:'智能分镜版',ver:'01',status:'OK'});
    if(!nm.includes('Ep01'))throw new Error('buildName missing Ep: '+nm);
    if(!nm.includes('张谭'))throw new Error('buildName missing author: '+nm);
  });
  t('renderList table',()=>{
    files=[{path:'/t/a.mp4',basename:'a.mp4',ext:'.mp4',fields:{ep:'01',sc:'01',gr:'01',desc:'',author:'',method:'',ver:'01',status:''},tags:[]}];
    renderList();
    const tr=document.querySelector('#fileList tbody tr');
    if(!tr)throw new Error('no tr in tbody');
    const tds=tr.querySelectorAll('td');
    if(tds.length<12)throw new Error('expected 12+ tds, got '+tds.length);
    files=[];renderList();
  });
  if(fail.length){
    toast('⚠ 自测: '+ok.length+'/'+(ok.length+fail.length)+' — '+fail.join('; '));
  }
}

// ═══ Toast ═══
let tt;function toast(m){call('debug_log','TOAST: '+m);const el=document.getElementById('toast');el.textContent=m;el.classList.add('show');clearTimeout(tt);tt=setTimeout(()=>el.classList.remove('show'),2500)}
function result(m){document.getElementById('resultMsg').textContent=m}

setStatus('就绪  ·  Ctrl+Z 撤销  ·  Del 移除');