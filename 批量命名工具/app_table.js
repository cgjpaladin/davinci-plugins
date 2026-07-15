const APP_VERSION='3.8.0';
const APP_GIT_HASH='';
const APP_BRANCH='';
const APP_BUILD_TIME='';
const EXPORT_FILENAME_PREFIX='批量命名导出_';
// ═══ 立即执行 — 确认脚本加载 ═══
document.addEventListener('DOMContentLoaded',()=>{
  document.getElementById('debugMode').textContent='JS ✓';  // _tryStart 轮询统一处理 mock/live 初始化
});
// ═══ State ═══

// 全局错误 → toast（不沉默）
window.onerror=function(m,s,l,c,e){const msg='JS错误: '+(m||'未知')+' @ '+(s||'?')+':'+l;toast(msg);call('debug_log',msg);return false};
window.addEventListener('unhandledrejection',e=>{const msg='Promise错误: '+e.reason;toast(msg);call('debug_log',msg)});
const _origErr=console.error;console.error=function(...a){_origErr.apply(console,a);call('debug_log','CONSOLE: '+a.join(' '))};

let files=[], _firstDrop=true, sel=new Set(), methodDescMap={}, undoAvail=false, _thumbs={}, _undoSnap=null, _localUndos=[];
let _sortKey=null,_sortAsc=true;
const _sortKeys={base:'basename',ep:'ep',sc:'sc',gr:'gr',tk:'tk',desc:'desc',method:'method',author:'author',ver:'ver',status:'status'};
function applySort(){if(!_sortKey||!files.length)return;const key=_sortKeys[_sortKey]||_sortKey;if(key==='basename'){files.sort((a,b)=>(a.basename||'').localeCompare(b.basename||''));if(!_sortAsc)files.reverse();return}const s0=files[0].fields[key];const cmp=typeof s0==='string'?((a,b)=>(a.fields[key]||'').localeCompare(b.fields[key]||'')):((a,b)=>parseInt(a.fields[key]||0)-parseInt(b.fields[key]||0));files.sort((a,b)=>_sortAsc?cmp(a,b):cmp(b,a))}

// 制作者字段过滤：仅允许中英文、数字，拦截一切符号（空格、换行、_、-、标点等）
const _sanitizeAuthor = (v) => v.replace(/[^a-zA-Z0-9\u4e00-\u9fff\u3400-\u4dbf]/g, '');

// 字段实时过滤注册表 — 表格和审查模式共用。返回过滤后的值，不返回则不过滤
const FIELD_SANITIZE = {
  author: _sanitizeAuthor,
  desc:   (v) => v.replace(/_/g, ''),
  ep:     (v) => v.replace(/[^\d]/g, ''),
  sc:     (v) => v.replace(/[^\d]/g, ''),
  gr:     (v) => v.replace(/[^\d]/g, ''),
  ver:    (v) => { let r=v.replace(/[^\d.]/g,''); const d=r.indexOf('.'); if(d>=0)r=r.slice(0,d+1)+r.slice(d+1).replace(/\./g,''); return r; },
};

// 以下为 fallback 默认值，生产环境由 get_config 的 fields[] 覆盖
const _FIELD_KEYS  = ['ep','sc','gr','desc','method','author','ver','status'];
const _HEADER_KEYS = ['ep','sc','gr','tk','desc','method','author','ver','status'];
const STATUS_OPTIONS = ['OK','KP','NG'];
const STATUS_TOOLTIPS = {OK:'通过 — 素材合格', KP:'备选', NG:'不合格 — 标记废弃'};
const METHOD_OPTIONS = ['智能分镜版','双轨版','角色专属版'];
const HINT_NO_METHOD = '请先选择制作方式';  // 未选择制作方式时的提示
const HINT_DESC = '输入镜头描述';           // 镜头描述输入框占位

function reindex(){files.forEach((f,i)=>{f._idx=i})}
function updSortIndicators(){
  const tr=document.querySelector('#fileList thead tr');if(!tr)return;
  tr.querySelectorAll('th').forEach(th=>{
    const t=th.textContent.replace(/ [▲▼]$/,'');th.textContent=t;
    const cls=th.className.replace('col-','');
    if(cls===_sortKey)th.textContent=t+(_sortAsc?' ▲':' ▼');
  });
}
const DIGIT_RULES={ep:/^\d{0,3}$/,sc:/^\d{0,2}$/,gr:/^\d{0,2}$/,ver:/^\d{0,2}(\.\d)?$/};
const DIGIT_STRICT={ep:/^(0[1-9]|[1-9]\d{1,2})$/,sc:/^(0[1-9]|[1-9]\d)$/,gr:/^(0[1-9]|[1-9]\d)$/,ver:/^(0[1-9]|[1-9]\d)(\.\d)?$/};
const tc=['#2a3a1a','#1a2a3a','#3a201a','#2a1a3a','#1a3a2a','#3a301a','#1a3a3a','#302a1a'];

// ═══ API ═══
function call(m,...a){
  try{
    if(window.pywebview&&window.pywebview.api)return window.pywebview.api[m](...a);
  }catch(e){toast("API错误: "+m+" - "+e);return null}
  return mock(m,...a);
}
function mock(m,...a){
  return new Promise(r=>{
    const C={ep:'01',sc:'01',gr:'01',desc:'',author:'',method:'',ver:'01',status:'OK',tk:'01'};
    switch(m){
      case'get_config':r({fields:[{key:'ep',label:'Ep 集数',def:'01',hint:'01'},{key:'sc',label:'Sc 场次',def:'01',hint:'01'},{key:'gr',label:'Gr 小场次',def:'01',hint:'01'},{key:'desc',label:'镜头描述',def:'',hint:'由制作方式决定'},{key:'method',label:'制作方式',def:'',dv:['请选择','智能分镜版','双轨版','角色专属版']},{key:'author',label:'制作者',def:'',hint:'请输入姓名'},{key:'ver',label:'制作批次',def:'01',hint:'01'},{key:'status',label:'通过情况',def:'',dv:['请选择',...STATUS_OPTIONS]}],defaults:{},method_desc_map:{'智能分镜版':{mode:'locked',value:'智能分镜'},'双轨版':{mode:'dropdown',values:['请选择','智能分镜','幽灵角色','空镜','请手动输入…']},'角色专属版':{mode:'dropdown',values:['请选择','智能分镜','请手动输入…']}},name_format:[{pfx:'Ep',key:'ep'},{pfx:'Sc',key:'sc'},{pfx:'Gr',key:'gr'},{pfx:'Tk',key:'tk'},{pfx:'',key:'desc'},{pfx:'',key:'method'},{pfx:'',key:'author'},{pfx:'v',key:'ver'},{pfx:'',key:'status'}],field_rules:[{trigger:'method',targets:['desc'],map:{'智能分镜版':{desc:{locked:'智能分镜'}},'双轨版':{desc:{dropdown:['请选择','智能分镜','幽灵角色','空镜','请手动输入…']}},'角色专属版':{desc:{dropdown:['请选择','智能分镜','请手动输入…']}}}}],video_formats:['mp4','mov','mxf','avi','mkv','webm','m4v','mts','mpg','mpeg','wmv','3gp','flv','r3d','braw'],image_formats:['jpg','jpeg','png','bmp','tiff','tif','gif','webp','tga','psd']});break;
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
      case'export_debug_package':toast('Mock: 日志导出仅在生产环境可用');r({ok:false,error:'Mock'});break;
      case'open_manual':toast('Mock: 使用手册仅在生产环境可用');r({ok:false,error:'Mock'});break;
      default:r({});
    }
  });
}

// ═══ Load ═══
async function init(){
  if(window._initialized)return;window._initialized=true;
  const dm = document.getElementById('debugMode');
  const isLive=_isLive();dm.textContent=isLive?'✔ Live':'✖ Mock';call("debug_log",`APP START: ${isLive?"pywebview":"MOCK"} mode, files=${files.length}`);
  document.getElementById('updateStatus').textContent = 'v' + APP_VERSION;

  const cfg=await call('get_config');

  // 自动查更新（后台线程，不阻塞 UI）
  setTimeout(() => call('trigger_bg_update').catch(()=>{}), 3000);
  methodDescMap=cfg.method_desc_map||{};_nameFmt=cfg.name_format||[];
  // 收集所有预置镜头描述值供碰撞检测
  _reservedDesc.clear();
  for(const v of Object.values(methodDescMap)){
    if(v.value)_reservedDesc.add(v.value);
    if(v.values)v.values.forEach(x=>{_reservedDesc.add(x)});
  }
  const _allFields=cfg.fields||[];
  window._fieldKeysAll=_allFields.filter(f=>f.key!=='tk').map(f=>f.key);
  window._headerKeys=_allFields.map(f=>f.key);  // 含 tk，用于表头渲染
  window._fieldLabels={};_allFields.forEach(f=>{window._fieldLabels[f.key]=f.label});

  // 从 fields[] 派生选项，加字段时自动跟随（无需手动同步）
  methodDescMap=cfg.method_desc_map||{};_nameFmt=cfg.name_format||[];
  const _fdMethod=_allFields.find(f=>f.key==='method');
  const _fdStatus=_allFields.find(f=>f.key==='status');
  window.METHOD_OPTIONS=(_fdMethod?.dv||['智能分镜版','双轨版','角色专属版']).filter(v=>v!=='请选择');
  window.STATUS_OPTIONS=(_fdStatus?.dv||['OK','KP','NG']).filter(v=>v!=='请选择');

  // 审查状态按钮 — 从 STATUS_OPTIONS 动态生成，加状态只改 Python dv
  const _rsContainer=document.getElementById('reviewStatusBtns');
  if(_rsContainer){_rsContainer.innerHTML='';
    window.STATUS_OPTIONS.forEach(s=>{
      const btn=document.createElement('button');
      btn.className='rs-'+s.toLowerCase();btn.id='rs'+s;btn.textContent=s;
      btn.title=STATUS_TOOLTIPS[s]||s;
      btn.addEventListener('click',()=>setReviewStatus(s));  // ⚠️ 事件绑定必须在此处，不能等DOM初始化
      _rsContainer.appendChild(btn);
    });
  }

  // 审查面板字段：排除方法联动字段（desc/method）和专用 UI 字段（tk/status）
  window._REVIEW_FIELDS=_allFields.filter(f=>!['desc','method','tk','status'].includes(f.key));

  // 视频/图片格式从 Python SUPPORTED_EXT 派生，加格式只改 Python
  if(cfg.video_formats) _VIDEO_EXT=new Set(cfg.video_formats.map(s=>s.toLowerCase()));
  if(cfg.image_formats) _IMG_EXT=new Set(cfg.image_formats.map(s=>s.toLowerCase()));

  // 收集所有预置镜头描述值供碰撞检测
  _reservedDesc.clear();
  for(const v of Object.values(methodDescMap)){
    if(v.value)_reservedDesc.add(v.value);
    if(v.values)v.values.forEach(x=>{_reservedDesc.add(x)});
  }
  dm.textContent = cfg.dev ? ('🔧 '+APP_VERSION) : '📋 导出日志';
  dm.title = '导出诊断日志';
  dm.onclick = () => {
    dm.textContent = '⏳ 导出中…';
    call('export_debug_package').then(r => {
      if(r && r.ok){
        toast('✅ 已导出: '+r.name);
        dm.textContent = '✅ 已导出';
        setTimeout(() => { dm.textContent = cfg.dev ? ('🔧 '+APP_VERSION) : '📋 导出日志'; }, 3000);
      } else {
        toast('导出失败: '+(r?r.error:'未知'));
        dm.textContent = cfg.dev ? ('🔧 '+APP_VERSION) : '📋 导出日志';
      }
    }).catch(e => {
      toast('导出异常: '+e);
      dm.textContent = cfg.dev ? ('🔧 '+APP_VERSION) : '📋 导出日志';
    });
  };

  // 使用教程按钮
  const mb = document.getElementById('manualBtn');
  if(mb){
    mb.title = '使用教程';
    mb.onclick = () => {
      call('open_manual').then(r => {
        if(!r || !r.ok){ toast('打开教程失败'); return; }
        if(r.method === 'browser') return; // 浏览器已打开
        // 离线 QR 弹窗
        if(r.method === 'qr'){
          if(_dialogEl){_dialogEl.remove();_dialogEl=null;}
          _dialogEl=document.createElement('div');_dialogEl.className='update-overlay show';
          _dialogEl.addEventListener('click',e=>{if(e.target===_dialogEl){_dialogEl.remove();_dialogEl=null;}});
          _dialogEl.innerHTML='<div class="update-dialog" style="text-align:center">'+
            '<div class="up-title">📖 使用教程</div>'+
            '<div class="up-body" style="user-select:text;-webkit-user-select:text">当前离线，手机扫码查看：</div>'+
            '<img src="data:image/png;base64,'+r.qr+'" style="width:'+r.size+'px;height:'+r.size+'px;margin:12px auto;display:block">'+
            '<div class="up-actions"><button class="up-btn-cancel" onclick="if(_dialogEl){_dialogEl.remove();_dialogEl=null;}">关闭</button></div>'+
            '</div>';
          document.body.appendChild(_dialogEl);
        }
      }).catch(e => toast('打开教程异常: '+e));
    };
  }

  // 动态生成表头（单一事实来源，防止 HTML/JS 列序漂移）
  const theadTr = document.querySelector('#fileList thead tr');
  const baseTh = theadTr.querySelector('.col-base');
  const headerKeys=_allFields.map(f=>f.key);
  headerKeys.forEach(k => {
    const th = document.createElement('th');
    th.className = 'col-'+k;
    th.textContent = window._fieldLabels[k] || k;
    theadTr.insertBefore(th, baseTh);
  });
  window._headerKeys = headerKeys;

  // ── 表头点击排序 ──
  theadTr.querySelectorAll('th').forEach(th=>{
    const cls=th.className.replace('col-','');
    if(cls==='num'||cls==='thumb'||cls==='tk')return;
    th.style.cursor='pointer';th.title='点击排序';
    th.addEventListener('click',()=>{
      if(_sortKey===cls){if(_sortAsc){_sortAsc=false}else{_sortKey=null;_sortAsc=true;files.sort((a,b)=>a._idx-b._idx);renderList(true);updSortIndicators();return}}
      else{_sortKey=cls;_sortAsc=true}
      applySort();renderList(true);updSortIndicators();
    });
  });
  files.forEach((f,i)=>{f._idx=i});

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
  setTimeout(() => { if(!window.pywebview) _runSelfTest(); }, 2000);
  _initTBodyClick();
  // 审查面板事件
  document.getElementById('reviewClose').addEventListener('click',closeReview);
  STATUS_OPTIONS.forEach(s=>{const btn=document.getElementById('rs'+s);if(btn)btn.addEventListener('click',()=>setReviewStatus(s))});
  document.getElementById('reviewPrev').addEventListener('click',()=>navReview(-1));
  document.getElementById('reviewNext').addEventListener('click',()=>navReview(1));
  // 点击遮罩关闭
  document.getElementById('reviewOverlay').addEventListener('click',e=>{if(e.target===document.getElementById('reviewOverlay'))closeReview()});
  renderList();  // 首次渲染（空状态或 mock 数据）
}
// ═══ init — 轮询等待 pywebview 桥接（无 pywebview 则 1s 后 mock 启动） ═══
let _ready=false;
function _tryStart(){
  if(_ready)return;
  const live=!!(window.pywebview&&window.pywebview.api);
  if(live){
    _ready=true;
    if(window._tryIv)clearInterval(window._tryIv);
    init().catch(()=>{ document.getElementById('debugMode').textContent='❌ 启动失败'; });
  }
}
window._tryIv=setInterval(_tryStart,300);
// Fallback: 2s 后仍无 pywebview → mock 模式启动
setTimeout(()=>{ if(!_ready){ _ready=true; clearInterval(window._tryIv); init().catch(()=>{}); } }, 2000);


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
  const cfg=methodDescMap[m]||{mode:'text',hint:HINT_NO_METHOD};
  const rows = sel.size > 0 ? [...sel] : (ri !== undefined ? [ri] : []);
  const changedRows = rows.filter(r => files[r] && files[r].fields.method === oldMethod && oldMethod !== m);
  call('debug_log',`onMethodChange: rows=${rows.length} sel=${sel.size} changed=${changedRows.length} old='${oldMethod||'(空)'}' new='${m||'(空)'}'`);
  if(!changedRows.length) return;
  // snapshot old values for undo (method + desc both change)
  const mcChanges = changedRows.map(r => ({
    idx: r,
    method: files[r].fields.method || '',
    desc: files[r].fields.desc || ''
  }));
  _localUndos.push({type:'methodChange', changes: mcChanges});
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
      const ff = {...f.fields, tk: buildTK(i)};
      const fieldKeys = window._fieldKeysAll || _FIELD_KEYS;
      const ready = fieldKeys.every(k => ff[k]);
      tr.classList.add(ready?'rdy':'mis');
      if(f.archived) tr.classList.add('archived');
      const nFields = fieldKeys.length;
      const fillCount = fieldKeys.filter(k => ff[k]).length;
      tr.classList.add(fillCount === nFields ? 'row-full' : fillCount >= Math.ceil(nFields/2) ? 'row-most' : 'row-empty');
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
  const ff = {...f.fields, tk: buildTK(i)};
  const fieldKeys = window._fieldKeysAll || _FIELD_KEYS;
  const nFields = fieldKeys.length;
  const ready = fieldKeys.every(k => ff[k]);
  if(sel.has(i)) tr.classList.add('sel');
  tr.classList.add(ready?'rdy':'mis');
  if(f.archived) tr.classList.add('archived');
  // 行完成度色条
  const fillCount = fieldKeys.filter(k => ff[k]).length;
  tr.classList.add(fillCount === nFields ? 'row-full' : fillCount >= Math.ceil(nFields/2) ? 'row-most' : 'row-empty');
  const tags = f.tags||[];
  if(tags.length) tr.classList.add('warn');
  if(tags.includes('zero')) tr.classList.add('warn-zero');
  if(tags.includes('size')) tr.classList.add('warn-size');
  if(tags.includes('dbl_ext')) tr.classList.add('warn-dbl');

  const tdNum = document.createElement('td');
  tdNum.className = 'col-num'; tdNum.dataset.row = i;
  if(!f.archived) tdNum.classList.add('grip');
  const pl = Math.max(2, String(files.length).length);
  tdNum.appendChild(Object.assign(document.createElement('span'),{textContent:String(i+1).padStart(pl,'0')}));
  tr.appendChild(tdNum);

  const tdThumb = document.createElement('td');
  tdThumb.className = 'col-thumb';
  tdThumb.title = '单击预览';
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

  for(const key of (window._headerKeys||_HEADER_KEYS)){
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
    for(const k of _FIELD_KEYS){
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

    // 单击缩略图 → 打开审查模式
    if(td.classList.contains('col-thumb')&&e.detail===1){
      sel.clear();sel.add(i);openReview(i);
      return;
    }

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
  // 右键菜单
  tbody.addEventListener('contextmenu', e => {
    const tr = e.target.closest('tr'); if(!tr) return;
    const i = parseInt(tr.dataset.index); if(isNaN(i)||!files[i]) return;
    e.preventDefault();
    // 清理旧菜单 + 更新选中
    const old = document.getElementById('ctxMenu'); if(old) old.remove();
    if(!sel.has(i)){sel.clear();sel.add(i)}
    // 高亮选中行（不重渲染整表）
    tbody.querySelectorAll('tr').forEach(r=>r.classList.toggle('sel',sel.has(parseInt(r.dataset.index))));
    const menu = document.createElement('div'); menu.id='ctxMenu';
    menu.style.cssText='position:fixed;z-index:10000;background:var(--surface);border:1px solid var(--border);border-radius:4px;padding:2px 0;min-width:160px;font-size:12px;box-shadow:0 4px 12px rgba(0,0,0,.5)';
    const safePath = files[i].path.replace(/\\/g,'\\\\').replace(/"/g,'&quot;').replace(/'/g,'\\x27');
    menu.innerHTML=[
      `<div style="padding:6px 12px;cursor:pointer;color:var(--text)" onmouseover="this.style.background='var(--surface2)'" onmouseout="this.style.background='transparent'" onclick="document.getElementById('ctxMenu').remove();call('reveal_in_finder','${safePath}')">📂 在 Finder 中显示</div>`,
      `<div style="padding:6px 12px;cursor:pointer;color:#e55" onmouseover="this.style.background='var(--surface2)'" onmouseout="this.style.background='transparent'" onclick="document.getElementById('ctxMenu').remove();removeSelected()">🗑 从列表移除</div>`,
    ].join('');
    // 防止菜单溢出屏幕
    const maxX = window.innerWidth - 170; const maxY = window.innerHeight - 60;
    menu.style.left = Math.min(e.clientX, maxX) + 'px';
    menu.style.top = Math.min(e.clientY, maxY) + 'px';
    document.body.appendChild(menu);
    setTimeout(()=>document.addEventListener('click',function cm(e){const m=document.getElementById('ctxMenu');if(m&&!m.contains(e.target)){m.remove()};document.removeEventListener('click',cm)},{once:true}),0);
  });
  // 拖拽排序 — 用鼠标事件而非 HTML5 DnD（pywebview 原生拖放拦截导致 dragover 不可靠）
  let _dragIdx=-1, _dragGhost=null, _dragPlaceholder=null, _dragOffsetY=0;
  function _showPlaceholder(tr, before){
    const ref = before ? tr : tr.nextSibling;
    if(!_dragPlaceholder){
      _dragPlaceholder=document.createElement('tr');_dragPlaceholder.className='drag-place';
      const cells=tr.cells;
      for(let c=0;c<cells.length;c++){
        const td=document.createElement('td');
        const w=cells[c].offsetWidth;
        td.style.cssText=`height:2px;padding:0!important;border:none!important;background:#39f!important;width:${w}px`;
        _dragPlaceholder.appendChild(td);
      }
      tr.parentNode.insertBefore(_dragPlaceholder, ref);
    } else if(_dragPlaceholder.nextSibling !== ref || _dragPlaceholder.previousSibling === ref) {
      // 只在位置变化时才移动，避免每帧重建
      tr.parentNode.insertBefore(_dragPlaceholder, ref);
    }
  }
  function _hidePlaceholder(){if(_dragPlaceholder&&_dragPlaceholder.parentNode)_dragPlaceholder.parentNode.removeChild(_dragPlaceholder)}
  function _finishDrag() {
    _dragIdx=-1;_dropIdx=-1;  // 必须最先设——防 double-run（blur→_finishDrag→松手→_onDragEnd→guard 拦截）
    if(_dragGhost){
      _dragGhost.style.position='';_dragGhost.style.zIndex='';_dragGhost.style.left='';_dragGhost.style.top='';
      _dragGhost.style.width='';_dragGhost.style.pointerEvents='';_dragGhost.style.opacity='';_dragGhost.style.boxShadow='';
      _dragGhost.classList.remove('dragging');_dragGhost=null
    }
    _hidePlaceholder();
    document.removeEventListener('mousemove',_onDragMove);
    document.removeEventListener('mouseup',_onDragEnd);
    window.removeEventListener('blur',_onDragBlur);
    document.removeEventListener('keydown',_onDragEsc);
  }
  function _onDragBlur(){ _finishDrag(); }
  function _onDragEsc(e){ if(e.key==='Escape'){ e.preventDefault(); _finishDrag(); } }
  function _onDragMove(e){
    if(!_dragGhost||_dragIdx<0) return;
    _dragGhost.style.top=(e.clientY-_dragOffsetY)+'px';
    const tr=document.elementFromPoint(e.clientX,e.clientY)?.closest('tbody tr:not(.dragging):not(.drag-place)');
    if(tr){
      const rect=tr.getBoundingClientRect();
      const before=e.clientY<rect.top+rect.height/2;
      _showPlaceholder(tr,before);
      _dropIdx=before?parseInt(tr.dataset.index):parseInt(tr.dataset.index)+1;
    }
  }
  function _onDragEnd(){
    if(_dragIdx<0) return;
    const oldIdx=_dragIdx;
    const insertAt=_dropIdx>=0?_dropIdx:oldIdx;
    _finishDrag();
    if(insertAt===oldIdx||insertAt===oldIdx+1) return;
    _undoSnap=files.map(f=>({...f,fields:{...f.fields}}));
    const row=files.splice(oldIdx,1)[0];
    const actualInsert=insertAt>oldIdx?insertAt-1:insertAt;
    files.splice(actualInsert,0,row);
    _sortKey=null;_sortAsc=true;sel.clear();reindex();
    // 只移动 DOM 行
    const trs=document.querySelectorAll('#fileList tbody tr:not(.drag-place)');
    const dragged=trs[oldIdx];
    if(dragged){const ref=trs[actualInsert];if(ref&&ref!==dragged)tbody.insertBefore(dragged,ref);else if(actualInsert>=trs.length)tbody.appendChild(dragged)}
    tbody.querySelectorAll('tr:not(.drag-place)').forEach((tr,j)=>{
      tr.dataset.index=j;
      const s=tr.querySelector('.col-num span');if(s)s.textContent=String(j+1).padStart(Math.max(2,String(files.length).length),'0');
      const tk=tr.querySelector('.col-tk');if(tk)tk.textContent=buildTK(j);
    });
    updSortIndicators();
    _dragIdx=-1;_dropIdx=-1;
  }
  // 在 col-num 上按下开始拖拽
  tbody.addEventListener('mousedown', e => {
    const td=e.target.closest('.col-num');if(!td||td.classList.contains('locked'))return;
    const tr=td.closest('tr');if(!tr||tr.dataset.index==null)return;
    const i=parseInt(tr.dataset.index);if(isNaN(i)||!files[i]||files[i].archived)return;
    if(e.button!==0)return;  // 只响应左键
    const cm=document.getElementById('ctxMenu');if(cm)cm.remove();
    if(window._shrinkTimer){clearTimeout(window._shrinkTimer);window._shrinkTimer=null}
    _dragIdx=i;_dropIdx=-1;
    const rect=tr.getBoundingClientRect();
    _dragOffsetY=e.clientY-rect.top;
    // 升起 ghost 行
    _dragGhost=tr;
    _dragGhost.style.position='fixed';
    _dragGhost.style.zIndex='10000';
    _dragGhost.style.left=rect.left+'px';
    _dragGhost.style.top=(e.clientY-_dragOffsetY)+'px';
    _dragGhost.style.width=rect.width+'px';
    _dragGhost.style.pointerEvents='none';
    _dragGhost.style.opacity='.85';
    _dragGhost.style.boxShadow='0 4px 16px rgba(0,0,0,.5)';
    _dragGhost.classList.add('dragging');
    // 原位置显示占位
    _showPlaceholder(tr,true);
    document.addEventListener('mousemove',_onDragMove);
    document.addEventListener('mouseup',_onDragEnd);
    window.addEventListener('blur',_onDragBlur);
    document.addEventListener('keydown',_onDragEsc);
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
      const s = document.createElement('span'); s.textContent = HINT_NO_METHOD;
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
    const lbls = {ep:'Ep 集数',sc:'Sc 场次',gr:'Gr 小场次',desc:'镜头描述',author:'制作者',method:'制作方式',ver:'制作批次',status:'通过情况'};
    toast('编辑 '+sel.size+' 个文件的 '+ (lbls[key]||key));
  }
  const oldVal = td.dataset.value;
  const isSelect = (key === 'method' || key === 'status' || (key === 'desc' && files[i] && files[i].fields.method && methodDescMap[files[i].fields.method] && methodDescMap[files[i].fields.method].mode === 'dropdown'));
  let el;

  if(key === 'method'){
    el = document.createElement('select');
    const opts = ['请选择', ...(window.METHOD_OPTIONS || METHOD_OPTIONS)];
    opts.forEach(m => {
      const o = document.createElement('option'); o.value = m === '请选择' ? '' : m; o.textContent = m;
      if(m === oldVal) o.selected = true;
      el.appendChild(o);
    });
  } else if(key === 'status'){
    el = document.createElement('select');
    STATUS_OPTIONS.concat(['']).forEach(s => {
      const o = document.createElement('option'); o.value = s; o.textContent = s || '—';
      if(s === oldVal) o.selected = true;
      el.appendChild(o);
    });
  } else if(key === 'desc'){
    const method = files[i].fields.method || '';
    const cfg = methodDescMap[method] || {mode:'text',hint:HINT_DESC};
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
      el.placeholder = cfg.hint || HINT_DESC;
    }
  } else {
    el = document.createElement('input'); el.type = 'text'; el.value = oldVal;
    if(DIGIT_STRICT[key]) el.setAttribute('inputmode','numeric');
    if(key === 'author') el.placeholder = '中英文、数字';
  }

  td.classList.add('editing');
  td.textContent = '';
  td.appendChild(el);
  if(el.tagName === 'INPUT' && !el.readOnly){ el.focus(); el.select(); }
  else { el.focus(); }

  // 实时过滤：查注册表，只对定义了规则的字段生效
  const sanitizer = FIELD_SANITIZE[key];
  if (sanitizer) {
    el.addEventListener('input', () => {
      const pos = el.selectionStart;
      el.value = sanitizer(el.value);
      el.selectionStart = el.selectionEnd = Math.min(pos, el.value.length);
    });
  }

  // ═══ Commit logic ═══
  const commit = (cancel) => {
    let v = (el.value||'').trim();
    if(cancel){
      el.remove();
      td.classList.remove('editing');
      call('debug_log',`commit: CANCEL ${key} restore='${oldVal||'(空)'}'`);
      td.textContent = oldVal || (oldVal===''||oldVal==='请选择'||oldVal==='请手动输入…'?'—':oldVal);
      if(oldVal === '' || oldVal === '请选择' || oldVal === '请手动输入…') td.classList.add('empty');
      return;
    }
    // 严格校验（自动补零：输入"1"→"01"通过）
    const sr = DIGIT_STRICT[key];
    if(sr && v){
      let testVal = v;
      if(key==='ver'){
        const d = v.indexOf('.');
        const intPart = d>=0 ? v.slice(0,d) : v;
        if(/^\d+$/.test(intPart) && intPart.length < 2){
          const padded = intPart.padStart(2,'0');
          testVal = d>=0 ? padded + v.slice(d) : padded;
        }
      }else if(/^\d+$/.test(v)){
        testVal = v.padStart(2,'0');
      }
      if(!sr.test(testVal)){
        toast(`请输入正确格式`);
        el.remove(); td.classList.remove('editing');
        td.textContent = oldVal || '—';
        if(!oldVal) td.classList.add('empty');
        return;
      }
      if(testVal !== v){ v = testVal; el.value = v; }
    }
    el.remove(); // 物理销毁编辑控件，杜绝残留
    td.classList.remove('editing');
    let finalVal = v;
    // 字段过滤：统一查注册表
    if (FIELD_SANITIZE[key]) finalVal = FIELD_SANITIZE[key](finalVal);
    if(key === 'desc' && finalVal && !isSelect) _checkDescCollision(finalVal);

    const isMulti = sel.size > 1;
    if(finalVal !== oldVal || isMulti){
      if(key === 'method'){
        onMethodChange(oldVal, finalVal, i);
        return;
      }
      const rows = isMulti ? [...sel] : [i];
      // snapshot old values for undo
      const changes = rows.map(r => ({idx: r, key, oldVal: files[r].fields[key] || ''}));
      _localUndos.push({type:'edit', changes});
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
          input.type = 'text'; input.placeholder = HINT_DESC;
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
  const keys=window._fieldKeysAll||_FIELD_KEYS;
  let ok2=0;files.forEach(f=>{const ff=f.fields;if(keys.every(k=>ff[k]))ok2++});document.getElementById('fileCount').innerHTML=`文件列表 · <span style="color:var(--green)">${ok2}</span>/${files.length} 就绪  ·  选中 ${sel.size}`;
}

function updButtons(){
  const hf=files.length>0,hs=sel.size>0,fd=getFields(),dest=document.getElementById('destInput').value.trim();
  // af: 用文件实际数据算（不用 inspector，避免混合态误判）
  let af=true;
  if(hs){for(const i of sel){const ff=files[i].fields;let ok=true;for(const k of (window._fieldKeysAll||_FIELD_KEYS)){if(!ff[k]){ok=false;break}}if(!ok){af=false;break}}}
  document.getElementById('btnRename').disabled=!(hs&&af);
  document.getElementById('btnArchive').disabled=!(hs&&af&&dest);
  document.getElementById('btnUndo').disabled=!undoAvail;
  const dot=document.querySelector('.sb-dot');
  if(!hf){dot.style.background='var(--green)';setStatus('就绪  ·  拖入文件开始  ·  拖拽排序  ·  右键菜单  ·  Ctrl+Z 撤销  ·  Del 移除');return}
  // 全就绪
  if(hs&&af){dot.style.background='var(--green)';setStatus('字段齐全，可以重命名');call('debug_log',`updButtons: GREEN hs=${hs} af=${af}`);return}
  // 全部就绪但未选中 → 绿色
  let allOk=0;const fks=window._fieldKeysAll||_FIELD_KEYS;files.forEach(f=>{const ff=f.fields;if(fks.every(k=>ff[k]))allOk++});
  if(allOk===files.length&&files.length>0){dot.style.background='var(--green)';setStatus('全部就绪 · 选中文件后重命名');call('debug_log',`updButtons: ALL-GREEN ok=${allOk}/${files.length}`);return}
  // 混合态标注（与缺失区分）
  const missing=[];
  const _lbs=window._fieldLabels||{};
  for(const k of (window._fieldKeysAll||_FIELD_KEYS)){if(!fd[k])missing.push(_lbs[k]||k)}
  // 检查警告
  let warn=[];
  for(const t of files){if(t.tags&&t.tags.length)warn.push(...t.tags)}
  if(warn.length){const wl={zero:'零字节',size:'大小异常',dbl_ext:'双扩展名'};dot.style.background='var(--red)';setStatus('⚠ '+[...new Set(warn)].map(w=>wl[w]||w).join(' · '));return}
  dot.style.background='var(--yellow)';
  let t_ok=0;files.forEach(f=>{const ff=f.fields;if(fks.every(k=>ff[k]))t_ok++});
  call('debug_log',`updButtons: YELLOW ok=${t_ok}/${files.length} missing=${missing.join(',')}`);
  let msg=missing.length?('双击单元格编辑 · 缺失: '+missing.join(' · ')):'';
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
async function addFiles(){const r=await call('add_files_via_dialog');if(r&&r.files){const ex=new Set(files.map(f=>f.path));const fr=r.files.filter(f=>!ex.has(f.path));files=files.concat(fr);_undoSnap=null;_localUndos=[];applySort();reindex();r.total=fr.length;r.duplicates=r.files.length-fr.length;call("debug_log",`FILES list: ${files.length} total (addFiles)`);renderList();_toastResult(r);loadThumbs()}}
async function addFolder(){const r=await call('add_folder_via_dialog');if(r&&r.files){const ex=new Set(files.map(f=>f.path));const fr=r.files.filter(f=>!ex.has(f.path));files=files.concat(fr);_undoSnap=null;_localUndos=[];applySort();reindex();r.total=fr.length;r.duplicates=r.files.length-fr.length;call("debug_log",`FILES list: ${files.length} total (addFiles)`);renderList();_toastResult(r);loadThumbs()}}
function _toastResult(r){let m=`已追加 ${r.total} 个文件`;if(r.skipped)m+=` · ${r.skipped} 个格式不支持`;if(r.duplicates)m+=` · ${r.duplicates} 个重复跳过`;if(r.subdirs_skipped)m+=` · ${r.subdirs_skipped} 个子文件夹跳过`;if(r.truncated)m+=` (上限${r.max}个)`;toast(m)}

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
  // 进度条
  let _rnDone=false; const _rnOverlay=showProgressOverlay('重命名中…');
  const _rnTimer=setInterval(async()=>{
    if(_rnDone){clearInterval(_rnTimer);return}
    try{
      const p=await (await fetch('/rename_progress')).json();
      if(p){_rnOverlay.querySelector('#_pPct').textContent=p.percent+'%';_rnOverlay.querySelector('#_pBar').style.width=p.percent+'%';_rnOverlay.querySelector('#_pStatus').textContent=p.status||'';if(p.done){_rnDone=true;clearInterval(_rnTimer)}}
    }catch(ex){}
  },300);
  const r=await call('do_rename',sfs);
  if(!_rnDone){clearInterval(_rnTimer);_rnOverlay.remove()}
  call('debug_log','rename: ok='+r.ok+' fail='+(r.fail||[]).length+' depth='+(r.stack_depth||0));
  if(r.ok>0){undoAvail=true;
    r.renamed.forEach(rn=>{const f=files.find(x=>x.path===rn.old_path);if(f){f.path=rn.new_path;f.basename=rn.new_path.replace(/^.*[/\\]/,'')}});
    // 缩略图 key 同步更新
    r.renamed.forEach(rn=>{if(_thumbs[rn.old_path]){_thumbs[rn.new_path]=_thumbs[rn.old_path];delete _thumbs[rn.old_path]}});
    toast(`完成 ${r.ok}/${r.total}`); result(`✅ 重命名完成 ${r.ok}/${r.total}`)}
  if(r.fail&&r.fail.length){result(`✅ 重命名完成 ${r.ok}/${r.total}  ·  ⚠️ ${r.fail.join('; ')}`)}
  renderList(true);updButtons();
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
  renderList(true);updButtons();
}

function removeSelected(){
  if(sel.size===0)return;
  call('debug_log','remove: '+sel.size+' files');
  const removed=[], indices=[];
  for(const i of sel){removed.push(files[i]);indices.push(i)}
  _localUndos.push({type:'remove', rows:removed, indices:[...indices].sort((a,b)=>a-b)});
  files=files.filter((_,i)=>!sel.has(i));
  sel.clear();renderList();toast('已移除 · Ctrl+Z 可撤销');
}
function undoLocal(){
  if(_localUndos.length===0) return;
  const entry=_localUndos.pop();
  if(entry.type==='remove'){
    let offset=0;
    entry.indices.forEach((idx,i)=>{
      files.splice(idx+offset,0,entry.rows[i]); offset++;
    });
    reindex();renderList();
    toast(`已撤销删除 · ${entry.rows.length} 个文件`);
  } else if(entry.type==='edit'){
    entry.changes.forEach(({idx,key,oldVal})=>{ files[idx].fields[key]=oldVal; });
    renderList(true);
    toast(`已撤销编辑 · ${entry.changes.length} 个字段`);
  } else if(entry.type==='methodChange'){
    entry.changes.forEach(({idx,method,desc})=>{ files[idx].fields.method=method;files[idx].fields.desc=desc; });
    renderList(true);
    toast(`已撤销方式 · ${entry.changes.length} 行`);
  }
}
async function doArchive(){
  if(sel.size===0){toast('未选中文件');return}
  const dest=document.getElementById('destInput').value.trim();
  if(!dest){toast('请先输入目标路径');return}
  const srt=[...sel].sort((a,b)=>a-b);
  const sfs=srt.map((i,p)=>{const f={...files[i]};f.fields={...f.fields,tk:buildTK(i)};return f});
  if(!await showDialog('确认归档',`确认归档 ${sfs.length} 个文件到?\n${dest}/EP${sfs[0].fields.ep||'??'}/SC${sfs[0].fields.sc||'??'}/...`))return;
  
  // 进度条
  let _pOverlay=document.createElement('div');
  _pOverlay.className='update-overlay show';
  _pOverlay.innerHTML='<div class="update-dialog" style="max-width:360px;text-align:center">'+
    '<div class="up-title">📂 归档中…</div>'+
    '<div style="margin:8px 0;font-size:12px;color:var(--text-dim)" id="_pStatus">准备中…</div>'+
    '<div style="background:var(--surface2);border-radius:4px;height:6px;overflow:hidden;margin:8px 0">'+
      '<div id="_pBar" style="background:#448;height:100%;width:0%;transition:width .2s"></div>'+
    '</div>'+
    '<div id="_pPct" style="font-size:11px;color:var(--text-dim)">0%</div>'+
  '</div>';
  document.body.appendChild(_pOverlay);
  
  let _pDone=false;
  const _pTimer=setInterval(async ()=>{
    try{
      const resp=await fetch('/archive_progress');
      const p=await resp.json();
      if(p){
        document.getElementById('_pBar').style.width=p.percent+'%';
        document.getElementById('_pPct').textContent=p.percent+'%';
        document.getElementById('_pStatus').textContent=p.status||'';
        if(p.done){_pDone=true;clearInterval(_pTimer);setTimeout(()=>{_pOverlay.remove()},600)}
      }
    }catch(e){}
  },300);
  
  call('debug_log','archive: starting');
  const r=await call('do_archive',sfs,dest);
  call('debug_log','archive: result='+JSON.stringify({ok:r.ok,total:r.total,dup:r.dup||0,fail:r.fail,verify:r.verify}));
  
  if(!_pDone){clearInterval(_pTimer);_pOverlay.remove()}
  if(r.ok>0){
    srt.forEach(i => { files[i].archived = true; });
    sel.clear();
    undoAvail = true;
  }
  let m=`归档完成 ${r.ok} 个`;if(r.dup>0)m+=` · ${r.dup} 个重复已跳过`;if(r.fail&&r.fail.length>0)m+=` · ${r.fail.length} 失败`;
  if(r.verify){
    const v=r.verify;
    if(v.missing&&v.missing.length>0)m+=` · ⚠ ${v.missing.length} 个丢失`;
    if(v.size_mismatch&&v.size_mismatch.length>0)m+=` · ⚠ ${v.size_mismatch.length} 个大小异常`;
    if(v.tmp_orphans&&v.tmp_orphans.length>0)m+=` · ⚠ ${v.tmp_orphans.length} 个残片已修复`;
    if(v.verified!==r.ok)m+=` (${v.verified}/${r.ok} 已确认)`;
  }
  toast(m);result(m);
  renderList();updButtons();
}
// ═══ Excel 导出 ═══
async function exportExcel(){
  if(files.length===0){toast('无文件可导出');return}
  toast('生成中…');call('debug_log','exportExcel: '+files.length+' files');
  const fieldKeys=window._fieldKeysAll||_FIELD_KEYS;
  const rows=files.map((f,i)=>{
    const ff=f.fields;
    const row={ext:f.ext||'',thumb:_thumbs[f.path]||''};
    for(const k of fieldKeys) row[k]=ff[k]||'';
    row.tk=buildTK(i);  // tk 由 buildTK 计算，不从 ff 读
    return row;
  });
  try{
    const r=await call('export_table',rows);
    if(!r||!r.data){toast('生成失败');return}
    const now=new Date(),pad=n=>String(n).padStart(2,'0');
    const dn=EXPORT_FILENAME_PREFIX+now.getFullYear()+'-'+pad(now.getMonth()+1)+'-'+pad(now.getDate())+'-'+pad(now.getHours())+pad(now.getMinutes())+'.xlsx';
    const sv=await call('save_file',r.data,dn);
    if(sv&&sv.ok){toast('已保存: '+sv.path.split('/').pop());call('debug_log','exportExcel: saved to '+sv.path)}
    else{toast('取消导出')}
  }catch(e){toast('导出失败: '+e.message)}
}
// ═══ Thumbnails ═══
async function loadThumbs(){
  const paths=files.map(f=>f.path);
  call('debug_log','loadThumbs: '+paths.length+' files');
  const r=await call('generate_thumbnails',paths);
  call('debug_log','loadThumbs done: '+(r?r.total:0)+' thumbs');
  if(r&&r.thumbs){
    for(const [p,t] of Object.entries(r.thumbs)){
      _thumbs[p]=t;
      const rows=document.querySelectorAll('[data-path]');
      for(let i=0;i<rows.length;i++){
        if(rows[i].dataset.path===p){
          let thumbEl=rows[i].querySelector('.cell-thumb');
          if(thumbEl&&thumbEl.tagName==='DIV'){
            const img=document.createElement('img');
            img.className='cell-thumb';img.src=t;img.alt='';
            thumbEl.replaceWith(img);
          }else if(thumbEl){
            thumbEl.src=t;
          }
          break;
        }
      }
    }
  }
}

function setThumb(path,thumb){
  _thumbs[path]=thumb;
  const rows=document.querySelectorAll('[data-path]');
  let el=null;
  for(let i=0;i<rows.length;i++){
    if(rows[i].dataset.path===path){el=rows[i];break}
  }
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
  const dup = result.duplicates || 0;
  const sk = result.skipped || 0;
  if(fresh.length===0 && dup===0 && sk>0){toast(`${sk} 个格式不支持`);return}
  if(fresh.length===0){toast(`全部重复 · ${dup} 个已跳过`);return}
  files=files.concat(fresh);_undoSnap=null;_localUndos=[];applySort();reindex();
  call("debug_log",`FILES list: ${files.length} total (added ${fresh.length})`);
  let msg=`已追加 ${fresh.length} 个文件`;
  if(dup) msg+=` · ${dup} 个重复跳过`;
  if(sk) msg+=` · ${sk} 个格式不支持`;
  if(result.subdirs_skipped) msg+=` · ${result.subdirs_skipped} 个子文件夹跳过`;
  if(result.truncated) msg+=` (上限${result.max}个)`;
  renderList();toast(msg);
  loadThumbs();
}

// ═══ 审查模式 ═══
let _reviewIdx=-1, _mediaBlobUrl=null, _metaGen=0, _rcInterval=null, _vidCheckTimeout=null;
const _speeds=[0.5,1,2];let _speedI=1;
function formatTime(s){if(!isFinite(s)||s<0)return'0:00';const m=Math.floor(s/60),sec=Math.floor(s%60);return m+':'+String(sec).padStart(2,'0')}
// 视频/图片格式 — fallback 默认值，生产环境由 get_config 覆盖
let _VIDEO_EXT=new Set(['mp4','mov','mxf','avi','mkv','webm','m4v','mts','mpg','mpeg','wmv','3gp','flv','r3d','braw']);
let _IMG_EXT=new Set(['jpg','jpeg','png','bmp','tiff','tif','gif','webp','tga','psd']);
function _isVideo(ext){return _VIDEO_EXT.has((ext||'').toLowerCase().replace('.',''))}

// 审查模式文件名 — 从 get_config.name_format 生成，加字段时自动跟随
function _buildReviewTitle(ff,tk){
  return (_nameFmt||[]).map(({pfx,key}) => pfx + (key==='tk' ? tk : (ff[key]||(pfx?'__':'')))).join('_');
}

async function openReview(i){
  call('debug_log',`openReview: START i=${i} file=${files[i]?.basename}`);
  if(_vidCheckTimeout){clearTimeout(_vidCheckTimeout);_vidCheckTimeout=null}
  _reviewIdx=i;const f=files[i];const ff=f.fields;const isVideo=_isVideo(f.ext);
  const tk=buildTK(i);
  document.getElementById('reviewFilename').textContent=_buildReviewTitle(ff,tk);
  const video=document.getElementById('reviewVideo');video.removeAttribute('src');
  const img=document.getElementById('reviewImage');img.removeAttribute('src');
  if(_mediaBlobUrl){URL.revokeObjectURL(_mediaBlobUrl);_mediaBlobUrl=null}
  const mediaErr=document.getElementById('reviewMediaErr');if(mediaErr)mediaErr.style.display='none';
  // 视频：通过 bottle HTTP 路由加载（WKWebView 禁止 file://）
  if(isVideo){
    const mediaUrl=await call('get_media_url',f.path);
    call('debug_log',`openReview: mediaUrl=${mediaUrl||'(empty)'}`);
    if(mediaUrl){
      video.src=mediaUrl;video.style.display='';img.style.display='none';
      _speedI=1;document.getElementById('rcSpeed').textContent='1×';video.playbackRate=1;
      // 3 秒后检查是否真的在播（兼容编码不支持的黑屏）
      if(_vidCheckTimeout) clearTimeout(_vidCheckTimeout);
      _vidCheckTimeout=setTimeout(()=>{
        if(video.readyState<2||video.videoWidth===0){
          video.style.display='none';
          if(mediaErr){mediaErr.innerHTML='⚠ 视频编码不支持<br><span style="color:#39f;cursor:pointer;text-decoration:underline" onclick="call(\"reveal_in_finder\",\"'+f.path.replace(/\\/g,'\\\\').replace(/"/g,'&quot;').replace(/'/g,'\\x27')+'\")">→ 在 Finder 中打开</span>';mediaErr.style.display='block'}
        }
      },3000);
      video.addEventListener('loadeddata',()=>{clearTimeout(_vidCheckTimeout)}, {once:true});
      video.play().catch(()=>{if(mediaErr){mediaErr.textContent='⏯ 单击缩略图播放';mediaErr.style.display='block'}});
      initReviewControls(video);
    }else{
      if(mediaErr){mediaErr.textContent='⚠ 无法加载视频';mediaErr.style.display='block'};
      video.style.display='none';img.style.display='none';
    }
  }else{
    // 图片或其他文件：尝试 base64 加载
    try{const r=await call('get_media_data',f.path);
      call('debug_log',`openReview: media r=${r?'ok':'null'} size=${r?.size||0}`);
      if(r&&r.data){
        const bytes=Uint8Array.from(atob(r.data),c=>c.charCodeAt(0));
        const blob=new Blob([bytes],{type:r.mime});
        _mediaBlobUrl=URL.createObjectURL(blob);
        img.src=_mediaBlobUrl;img.style.display='';video.style.display='none';
        video.pause();document.getElementById('reviewControls').style.display='none';
      }else if(r&&r.error){
        call('debug_log','openReview: media ERR '+r.error);
        if(mediaErr){mediaErr.textContent=r.error;mediaErr.style.display='block'}
        video.style.display='none';img.style.display='none';
      }else{
        call('debug_log','openReview: NO media data');
        video.style.display='none';img.style.display='none';
      }
    }catch(e){call('debug_log','openReview: media ERROR '+e.message)}
  }
  buildReviewFields(ff,isVideo);
  highlightStatusBtn(ff.status||'');
  loadMediaMeta(f.path,isVideo,video,img);
  document.getElementById('reviewPrev').disabled=i===0;
  document.getElementById('reviewNext').disabled=i>=files.length-1;
  document.getElementById('reviewOverlay').classList.add('show');
  call('debug_log',`openReview: DONE i=${i} overlay=shown`);
}

function closeReview(){
  call('debug_log','closeReview: START');
  const v=document.getElementById('reviewVideo');v.pause();v.removeAttribute('src');v.load();
  document.getElementById('reviewImage').removeAttribute('src');
  if(_mediaBlobUrl){URL.revokeObjectURL(_mediaBlobUrl);_mediaBlobUrl=null}
  if(_rcInterval){clearInterval(_rcInterval);_rcInterval=null}
  if(_vidCheckTimeout){clearTimeout(_vidCheckTimeout);_vidCheckTimeout=null}
  _reviewIdx=-1;document.getElementById('reviewOverlay').classList.remove('show');
  document.getElementById('reviewControls').style.display='';
  renderList(true);
}

async function navReview(dir){
  const next=_reviewIdx+dir;if(next<0||next>=files.length)return;
  call('debug_log',`navReview: dir=${dir} from=${_reviewIdx} to=${next}`);
  _reviewIdx=next;const f=files[next];const ff=f.fields;const isVideo=_isVideo(f.ext);
  const tk=buildTK(next);
  document.getElementById('reviewFilename').textContent=_buildReviewTitle(ff,tk);
  const video=document.getElementById('reviewVideo');video.pause();video.removeAttribute('src');
  const img=document.getElementById('reviewImage');img.removeAttribute('src');
  if(_mediaBlobUrl){URL.revokeObjectURL(_mediaBlobUrl);_mediaBlobUrl=null}
  if(_rcInterval){clearInterval(_rcInterval);_rcInterval=null}
  try{const r=await call('get_media_data',f.path);if(r&&r.data){
    const bytes=Uint8Array.from(atob(r.data),c=>c.charCodeAt(0));
    const blob=new Blob([bytes],{type:r.mime});
    _mediaBlobUrl=URL.createObjectURL(blob);
    if(isVideo){video.src=_mediaBlobUrl;video.style.display='';img.style.display='none';_speedI=1;document.getElementById('rcSpeed').textContent='1×';video.playbackRate=1;video.play().catch(()=>{});initReviewControls(video);document.getElementById('reviewControls').style.display=''}
    else{img.src=_mediaBlobUrl;img.style.display='';video.style.display='none';document.getElementById('reviewControls').style.display='none'}
  }}catch(e){}
  buildReviewFields(ff,isVideo);
  highlightStatusBtn(ff.status||'');
  document.getElementById('reviewPrev').disabled=next===0;
  document.getElementById('reviewNext').disabled=next>=files.length-1;
  renderList(true);
  call('debug_log',`navReview: DONE to=${next}`);
}

function buildReviewFields(ff,isVideo){
  const container=document.getElementById('reviewFields');container.innerHTML='';
  container.style.gridTemplateColumns='repeat(4,1fr)';

  // 从 get_config.fields 自动生成布局（排除 desc/method/tk）
  const rvf = window._REVIEW_FIELDS || []; const labels = window._fieldLabels || {};
  const rows = [[], []];
  rvf.forEach(fd => {
    const isDigit = !!DIGIT_STRICT[fd.key];  // 有严格校验 → 数字小字段
    const w = isDigit ? 1 : 2;
    const attr = isDigit
      ? `inputmode=numeric maxlength=${fd.key==='ep'?3:2}`
      : `placeholder="${labels[fd.key]||fd.key}"`;
    (w === 1 ? rows[0] : rows[1]).push({...fd, w, attr, label: labels[fd.key] || fd.key});
  });
  const fields = rows.filter(r => r.length > 0);
  const initCfg=methodDescMap[ff.method||'']||{mode:'text',hint:HINT_NO_METHOD,readonly:true};
  // desc 重建函数（三种模式：locked / dropdown / text）
  function _buildDesc(cfg,oldVal){
    oldVal=oldVal||'';
    const dw=document.createElement('div');dw.className='rf-full';dw.id='reviewDescWrap';
    const lb=document.createElement('label');lb.textContent='镜头描述';dw.appendChild(lb);
    if(cfg.mode==='locked'){
      const ip=document.createElement('input');ip.type='text';ip.value=cfg.value||'';ip.readOnly=true;ip.classList.add('rf-filled');
      dw.appendChild(ip);files[_reviewIdx].fields.desc=cfg.value||'';
    }else if(cfg.mode==='dropdown'){
      const sel=document.createElement('select');sel.style.cssText='width:100%;background:#2a2a2a;border:1px solid var(--border);color:var(--text);padding:5px 7px;border-radius:4px;font-size:12px;font-family:var(--font-mono);box-sizing:border-box';
      (cfg.values||[]).filter(o=>o!=='请手动输入…').forEach(opt=>{
        const o=document.createElement('option');o.value=opt;o.textContent=opt;
        if(opt===oldVal)o.selected=true;sel.appendChild(o);
      });
      const fo=document.createElement('option');fo.value='__free__';fo.textContent='✐ 手动输入…';
      if(oldVal==='请手动输入…')fo.selected=true;sel.appendChild(fo);
      sel.addEventListener('change',()=>{
        if(sel.value==='__free__'){
          const inp=document.createElement('input');inp.type='text';inp.placeholder=HINT_DESC;inp.value='';
          inp.style.cssText='width:100%;background:#2a2a2a;border:1px solid var(--border);color:var(--text);padding:5px 7px;border-radius:4px;font-size:12px;font-family:var(--font-mono);box-sizing:border-box';
          inp.addEventListener('input',()=>{const v=FIELD_SANITIZE.desc(inp.value);inp.value=v;files[_reviewIdx].fields.desc=v;updateReviewTitle()});
          sel.replaceWith(inp);inp.focus();
        }else{files[_reviewIdx].fields.desc=sel.value==='请选择'?'':sel.value;updateReviewTitle()}
      });
      dw.appendChild(sel);files[_reviewIdx].fields.desc=oldVal==='请选择'?'':oldVal;
    }else{
      const ip=document.createElement('input');ip.type='text';ip.placeholder=cfg.hint||HINT_DESC;ip.value=oldVal;
      ip.style.cssText='width:100%;background:#2a2a2a;border:1px solid var(--border);color:var(--text);padding:5px 7px;border-radius:4px;font-size:12px;font-family:var(--font-mono);box-sizing:border-box';
      if(cfg.readonly){ip.readOnly=true}
      else{ip.addEventListener('input',()=>{const v=FIELD_SANITIZE.desc(ip.value);ip.value=v;files[_reviewIdx].fields.desc=v})}
      dw.appendChild(ip);
    }
    return dw;
  }
  // 初始 desc
  const descWrap=_buildDesc(initCfg,ff.desc||'');
  // method 下拉（联动 desc）
  const mWrap=document.createElement('div');mWrap.className='rf-full';
  const mLb=document.createElement('label');mLb.textContent='制作方式';mWrap.appendChild(mLb);
  const mSel=document.createElement('select');mSel.style.cssText='width:100%;background:#2a2a2a;border:1px solid var(--border);color:var(--text);padding:5px 7px;border-radius:4px;font-size:12px;font-family:var(--font-mono);box-sizing:border-box';
  ['请选择', ...(window.METHOD_OPTIONS || METHOD_OPTIONS)].forEach(m=>{const o=document.createElement('option');o.value=m==='请选择'?'':m;o.textContent=m;if(m===ff.method)o.selected=true;mSel.appendChild(o)});
  mWrap.appendChild(mSel);
  mSel.addEventListener('change',()=>{
    const nm=mSel.value;files[_reviewIdx].fields.method=nm;
    const cfg=methodDescMap[nm]||{mode:'text',hint:HINT_NO_METHOD,readonly:true};
    // 对齐 onMethodChange：非 locked 模式清 desc
    if(cfg.mode!=='locked')files[_reviewIdx].fields.desc='';
    const oldWrap=document.getElementById('reviewDescWrap');
    const newWrap=_buildDesc(cfg,files[_reviewIdx].fields.desc);
    if(oldWrap)oldWrap.replaceWith(newWrap);
    updateReviewTitle();updateReviewMeta();
  });
  fields.forEach(row=>{row.forEach(fd=>{
    if(fd.key==='desc')return;  // desc 由 _buildDesc 处理
    const wrap=document.createElement('div');wrap.className=fd.w>1?'rf-full':'';
    const lb=document.createElement('label');lb.textContent=fd.label;wrap.appendChild(lb);
    const ip=document.createElement('input');ip.value=ff[fd.key]||'';ip.setAttribute('data-rkey',fd.key);
    if(fd.attr){const attrs=fd.attr.split(' ');attrs.forEach(a=>{const[ak,av]=a.split('=');if(av)ip.setAttribute(ak,av.replace(/\"/g,''));else ip.setAttribute(ak,'')})}
    wrap.appendChild(ip);container.appendChild(wrap);
    const key=fd.key;
    // 实时过滤：查注册表
    const sanitizer = FIELD_SANITIZE[key];
    if (sanitizer) {
      ip.addEventListener('input', () => {
        const pos = ip.selectionStart;
        ip.value = sanitizer(ip.value);
        ip.selectionStart = ip.selectionEnd = Math.min(pos, ip.value.length);
        files[_reviewIdx].fields[key] = ip.value.trim();
        updateReviewTitle();
      });
    } else {
      ip.addEventListener('input', () => {
        files[_reviewIdx].fields[key] = ip.value.trim();
        updateReviewTitle();
      });
    }
    const sr=DIGIT_STRICT[key];
    const updFill=()=>{const v=ip.value.trim();if(v)ip.classList.add('rf-filled');else ip.classList.remove('rf-filled');updateReviewMeta()};
    ip.addEventListener('input',updFill);ip.addEventListener('blur',updFill);
    if(ip.value.trim())ip.classList.add('rf-filled');
    if(sr){ip.addEventListener('blur',()=>{let v=key==='ver'?ip.value.replace(/[^\d.]/g,''):ip.value.replace(/[^\d]/g,'');if(v&&key==='ver'){const d=v.indexOf('.');let intPart=d>=0?v.slice(0,d):v;intPart=intPart.padStart(2,'0');v=d>=0?intPart+v.slice(d):intPart;if(sr.test(v)){ip.value=v;files[_reviewIdx].fields[key]=v}else{ip.value=ff[key]||'';files[_reviewIdx].fields[key]=ff[key]||''}}else if(v&&sr.test(v.padStart(2,'0'))){v=v.padStart(2,'0');ip.value=v;files[_reviewIdx].fields[key]=v}else if(!v){files[_reviewIdx].fields[key]=''}else{ip.value=ff[key]||'';files[_reviewIdx].fields[key]=ff[key]||''};updateReviewTitle();updFill()})}
    // Tab/Enter 切下一个可编辑字段
    const cycleField=(e)=>{if(e.key==='Tab'||e.key==='Enter'){e.preventDefault();const inputs=[...container.querySelectorAll('input:not([readonly])')];const idx=inputs.indexOf(e.target);const next=inputs[(idx+1)%inputs.length];if(next)next.focus()}};
    ip.addEventListener('keydown',cycleField);
  })});
  container.appendChild(descWrap);
  container.appendChild(mWrap);
  updateReviewMeta();
}

function highlightStatusBtn(st){
  document.querySelectorAll('.review-status button').forEach(b=>b.classList.remove('active'));
  STATUS_OPTIONS.forEach(s=>{if(st===s){const btn=document.getElementById('rs'+s);if(btn)btn.classList.add('active')}});
}
function updateReviewTitle(){
  if(_reviewIdx<0)return;
  const ff=files[_reviewIdx].fields;const tk=buildTK(_reviewIdx);
  document.getElementById('reviewFilename').textContent=_buildReviewTitle(ff,tk);
}
function updateReviewMeta(){
  if(_reviewIdx<0)return;
  const ff=files[_reviewIdx].fields;
  const keys=window._fieldKeysAll||_FIELD_KEYS;
  const filled=keys.filter(k=>ff[k]).length;
  const total=keys.length;
  const el=document.getElementById('reviewMeta');
  if(!el._readySpan){el._readySpan=document.createElement('span');el.appendChild(el._readySpan)}
  el._readySpan.innerHTML=`${filled}/${total} 就绪`;
  el._readySpan.style.cssText=`color:${filled===total?'var(--green)':'var(--yellow)'};margin-left:8px`;
}
function setReviewStatus(st){call('debug_log',`setReviewStatus: ${st}`);files[_reviewIdx].fields.status=st;highlightStatusBtn(st);updateReviewTitle();renderList(true)}
async function loadMediaMeta(path,isVideo,video,img){
  if(!isVideo){document.getElementById('reviewMeta').innerHTML=`<span>🖼 图片</span>`;updateReviewMeta();return}
  _metaGen++;const gen=_metaGen;
  document.getElementById('reviewMeta').innerHTML='<span>📹 加载中…</span>';
  try{const r=await call('get_media_info',path);if(gen!==_metaGen||_reviewIdx<0)return;
    if(r){const parts=[];
      if(r.width&&r.height)parts.push(`${r.width}×${r.height}`);
      if(r.duration)parts.push(formatTime(r.duration));
      if(r.fps)parts.push(`${r.fps}fps`);
      if(r.codec)parts.push(`${r.codec}`);
      if(r.size_mb)parts.push(`${r.size_mb}MB`);
      document.getElementById('reviewMeta').innerHTML='<span>📹 '+parts.join(' · ')+'</span>';
    }else{document.getElementById('reviewMeta').innerHTML='<span>📹 无元数据</span>'}
  }catch(e){document.getElementById('reviewMeta').innerHTML='<span>📹 获取失败</span>'}
  updateReviewMeta();
}
function initReviewControls(video){
  if(_rcInterval)clearInterval(_rcInterval);
  const playBtn=document.getElementById('rcPlay'),seek=document.getElementById('rcSeek'),
    timeEl=document.getElementById('rcTime'),frameEl=document.getElementById('rcFrame'),
    speedBtn=document.getElementById('rcSpeed'),vol=document.getElementById('rcVolume');
  playBtn.onclick=()=>{if(video.paused){video.play();playBtn.textContent='⏸'}else{video.pause();playBtn.textContent='▶'}};
  seek.oninput=()=>{video.currentTime=seek.value/100*video.duration};
  vol.oninput=()=>{video.volume=vol.value/100};
  speedBtn.onclick=()=>{_speedI=(_speedI+1)%_speeds.length;video.playbackRate=_speeds[_speedI];speedBtn.textContent=_speeds[_speedI]+'×'};
  document.getElementById('rcStepBack').onclick=()=>{video.pause();video.currentTime=Math.max(0,video.currentTime-1/25);playBtn.textContent='▶'};
  document.getElementById('rcStepFwd').onclick=()=>{video.pause();video.currentTime=Math.min(video.duration||999,video.currentTime+1/25);playBtn.textContent='▶'};
  video.onplay=()=>{playBtn.textContent='⏸'};
  video.onpause=()=>{playBtn.textContent='▶'};
  video.ontimeupdate=()=>{if(!video.duration)return;seek.value=video.currentTime/video.duration*100;timeEl.textContent=formatTime(video.currentTime)+' / '+formatTime(video.duration);frameEl.textContent='帧 '+Math.floor(video.currentTime*25)};
  _rcInterval=setInterval(()=>{if(video.paused)return;seek.value=video.currentTime/video.duration*100;timeEl.textContent=formatTime(video.currentTime)+' / '+formatTime(video.duration);frameEl.textContent='帧 '+Math.floor(video.currentTime*25)},200);
  document.getElementById('reviewControls').style.display='';
  video.addEventListener('click',()=>{if(video.paused){video.play();playBtn.textContent='⏸'}else{video.pause();playBtn.textContent='▶'}});
}

// ═══ Keyboard ═══
document.addEventListener('keydown',e=>{
  // 审查模式入口：空格键 → 打开审阅
  if(_reviewIdx<0&&e.key===' '&&e.target.tagName!=='INPUT'&&e.target.tagName!=='TEXTAREA'&&e.target.tagName!=='SELECT'&&sel.size>0){
    e.preventDefault();
    const idx=Math.min(...sel);
    if(files[idx])openReview(idx);
    return;
  }
  // 审查模式快捷键
  if(_reviewIdx>=0&&e.target.tagName!=='INPUT'&&e.target.tagName!=='TEXTAREA'&&e.target.tagName!=='SELECT'){
    if(e.key==='Escape'){e.preventDefault();closeReview();return}
    if(e.ctrlKey&&e.key==='ArrowLeft'){e.preventDefault();navReview(-1);return}
    if(e.ctrlKey&&e.key==='ArrowRight'){e.preventDefault();navReview(1);return}
    if(e.key===' '){e.preventDefault();const v=document.getElementById('reviewVideo');if(v.src){if(v.paused){v.play();document.getElementById('rcPlay').textContent='⏸'}else{v.pause();document.getElementById('rcPlay').textContent='▶'}};return}
    if(e.key==='ArrowLeft'&&!e.ctrlKey){const v=document.getElementById('reviewVideo');if(v.src&&v.duration){v.currentTime=Math.max(0,v.currentTime-2);return}}
    if(e.key==='ArrowRight'&&!e.ctrlKey){const v=document.getElementById('reviewVideo');if(v.src&&v.duration){v.currentTime=Math.min(v.duration,v.currentTime+2);return}}
    if(e.key===','){const v=document.getElementById('reviewVideo');if(v.src){v.pause();v.currentTime=Math.max(0,v.currentTime-1/25);document.getElementById('rcPlay').textContent='▶';return}}
    if(e.key==='.'){const v=document.getElementById('reviewVideo');if(v.src){v.pause();v.currentTime=Math.min(v.duration||999,v.currentTime+1/25);document.getElementById('rcPlay').textContent='▶';return}}
    if(e.key==='j'||e.key==='J'){const v=document.getElementById('reviewVideo');if(!v.src)return;const rates=[1,0.5,0.25,0.1];let ri=rates.indexOf(v.playbackRate);ri=ri<0?0:(ri+1)%rates.length;v.playbackRate=rates[ri];document.getElementById('rcSpeed').textContent=rates[ri]+'×';if(v.paused){v.play();document.getElementById('rcPlay').textContent='⏸'}return}
    if(e.key==='k'||e.key==='K'){const v=document.getElementById('reviewVideo');if(!v.src)return;v.pause();v.playbackRate=1;document.getElementById('rcPlay').textContent='▶';document.getElementById('rcSpeed').textContent='1×';return}
    if(e.key==='Home'){const v=document.getElementById('reviewVideo');if(v.src){v.currentTime=0;return}}
    if(e.key==='End'){const v=document.getElementById('reviewVideo');if(v.src){v.currentTime=v.duration;return}}
    if(e.key==='l'||e.key==='L'){const v=document.getElementById('reviewVideo');if(!v.src)return;const rates=[1,2,4,8];let ri=v.paused?0:rates.indexOf(v.playbackRate);ri=ri<0?0:(ri+1)%rates.length;v.playbackRate=rates[ri];document.getElementById('rcSpeed').textContent=rates[ri]+'×';if(v.paused){v.play();document.getElementById('rcPlay').textContent='⏸'}return}
  }
  if((e.ctrlKey||e.metaKey)&&e.key==='z'){e.preventDefault();if(_undoSnap){files=_undoSnap;_undoSnap=null;reindex();renderList();toast('已撤销排序')}else if(_localUndos.length>0){undoLocal()}else{doUndo()}}
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
document.getElementById('btnExport').addEventListener('click',exportExcel);

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
  t('DIGIT_RULES',()=>{if(!DIGIT_RULES.ep)throw new Error('DIGIT_RULES missing')});
  t('buildTK',()=>{
    files=[{fields:{ep:'01',sc:'01',gr:'01',desc:'A',method:'X',ver:'01'}}];
    sel.add(0);
    const tk=buildTK(0);
    files=[];sel.clear();
    if(tk!=='01')throw new Error('buildTK returned '+tk);
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
function result(m){call('debug_log','result: '+m);document.getElementById('resultMsg').textContent=m}

// ═══ 自动更新（Downie 式：后台下载，状态栏进度） ═══
// ═══ 自动更新（弹窗公告 + 差分下载） ═══
let _updateVer='', _updateNotes='', _updating=false, _updateReady=false, _dlStart=0, _dialogEl=null;
function onUpdateFound(ver, notes){
  _updateVer=ver;_updateNotes=notes;
  const el=document.getElementById('updateStatus');
  el.innerHTML='<span class="up-dot"></span> v'+ver+' 可用 <button class="up-btn" onclick="showUpdateDialog()">更新</button>';
}
function showUpdateDialog(){
  if(!_updateVer)return;
  if(_dialogEl){_dialogEl.remove();_dialogEl=null;}
  _dialogEl=document.createElement('div');_dialogEl.className='update-overlay show';
  _dialogEl.addEventListener('click',e=>{if(e.target===_dialogEl){_updating=false;_dialogEl.remove();_dialogEl=null;}});
  document.addEventListener('keydown',function esc(e){if(e.key==='Escape'){_updating=false;_dialogEl.remove();_dialogEl=null;document.removeEventListener('keydown',esc);}});
  _dialogEl.innerHTML=`<div class="update-dialog">
    <div class="up-title">\uD83C\uDF89 v${_updateVer}</div>
    <div class="up-body" id="upBody" style="user-select:text;-webkit-user-select:text;white-space:pre-wrap">${APP_VERSION} \u2192 ${_updateVer}\n\n${(_updateNotes||'\u6682\u65E0\u66F4\u65B0\u8BF4\u660E')}</div>
    <div class="up-progress" id="upProgress" style="display:none"><div class="up-progress-bar" id="upProgressBar"></div></div>
    <div class="up-speed" id="upSpeed" style="display:none"></div>
    <div class="up-actions" id="upActions">
      <button class="up-btn-cancel" onclick="closeUpdateDialog()">\u53D6\u6D88</button>
      <button class="up-btn-go" id="upGoBtn" onclick="doDownload()">\u4E0B\u8F7D\u66F4\u65B0</button>
    </div>
  </div>`;
  document.body.appendChild(_dialogEl);
}
function closeUpdateDialog(){
  _updating=false;
  if(_dialogEl){_dialogEl.remove();_dialogEl=null;}
}
async function doDownload(){
  if(_updating)return;
  _updating=true;_updateReady=false;_dlStart=Date.now();
  const btn=document.getElementById('upGoBtn');btn.textContent='\u4E0B\u8F7D\u4E2D\u2026';btn.disabled=true;btn.onclick=null;
  const prg=document.getElementById('upProgress');prg.style.display='block';
  const spd=document.getElementById('upSpeed');spd.style.display='block';
  const tr=await call('trigger_delta');
  if(!tr||!tr.ok){
    document.getElementById('upBody').textContent='\u4E0B\u8F7D\u5931\u8D25: '+(tr?tr.error:'\u7F51\u7EDC\u4E0D\u53EF\u8FBE');
    btn.textContent='\u4E0B\u8F7D\u66F4\u65B0';btn.onclick=doDownload;btn.disabled=false;
    _updating=false;return;
  }
  pollProgress();
}
function pollProgress(){
  if(!_updating)return;
  call('get_update_progress').then(p=>{
    if(!_updating)return;
    const body=document.getElementById('upBody');const btn=document.getElementById('upGoBtn');
    const pbar=document.getElementById('upProgressBar');const spd=document.getElementById('upSpeed');
    const el=document.getElementById('updateStatus');
    if(p.total>0){
      const pct=Math.min(99,Math.round(p.downloaded*100/p.total));
      const mbDown=(p.downloaded/1048576).toFixed(1);const elapsed=((Date.now()-_dlStart)/1000).toFixed(0);
      pbar.style.width=pct+'%';spd.textContent=`${mbDown}MB \u00B7 ${elapsed}s`;
      el.innerHTML=`\u2B07 ${pct}%`;
      body.textContent='\u4E0B\u8F7D\u4E2D\u2026';
    }
    if(p.ready){
      _updating=false;_updateReady=true;
      btn.textContent='\u7ACB\u5373\u91CD\u542F';btn.className='up-btn-go';btn.onclick=doRestart;btn.disabled=false;
      body.textContent='\u66F4\u65B0\u5305\u5DF2\u4E0B\u8F7D\u5B8C\u6210\uFF0C\u70B9\u51FB\u91CD\u542F';
      spd.textContent='';el.innerHTML='\u2705 \u66F4\u65B0\u5C31\u7EEA';
      return;
    }
    setTimeout(pollProgress,500);
  });
}
async function doRestart(){
  if(!_updateReady)return;
  const btn=document.getElementById('upGoBtn');btn.textContent='\u91CD\u542F\u4E2D\u2026';btn.disabled=true;
  const el=document.getElementById('updateStatus');el.innerHTML='\u91CD\u542F\u4E2D\u2026';
  try{
    // apply_delta 末尾 os._exit → Promise 不会 resolve，用 fire-and-forget
    call('apply_delta').catch(e=>{el.innerHTML='\u274C \u5931\u8D25: '+e;call('debug_log','doRestart failed: '+e)});
  }catch(e){
    el.innerHTML='\u274C \u5931\u8D25: '+e;
    call('debug_log','doRestart exception: '+e);
  }
}
function checkUpdate(){ call('check_update').then(r=>{if(r.update_available)onUpdateFound(r.latest,r.notes);else toast('已是最新版本 v'+APP_VERSION);}); }
function onUpdateCheckDone(r){
  var st=document.getElementById('updateStatus');
  if(!r){ st.innerHTML='⚠ <a href="#" onclick="checkUpdate();return false" style="color:#e88">网络不可用</a>'; return; }
  if(r.reason){ st.innerHTML='⚠ <a href="#" onclick="checkUpdate();return false" style="color:#e88">'+_errHuman(r.reason)+'</a>'; return; }
  if(r.update_available){ onUpdateFound(r.latest,r.notes); }
  else{ st.textContent='v'+APP_VERSION; }
}
function _errHuman(s){ s=s||''; if(/timeout|timed out|URLError|urlopen/i.test(s)) return '网络超时'; if(/429|Too Many/i.test(s)) return '服务器繁忙'; if(/所有.*不可达/i.test(s)) return '无法连接服务器'; return '检测失败'; }
function showAbout(){ toast('批量文件命名工具 v'+APP_VERSION+' — 裁缝老师的插件工坊'); }

setStatus('\u5C31\u7EEA  \u00B7  \u62D6\u62FD\u6392\u5E8F  \u00B7  \u53F3\u952E\u83DC\u5355  \u00B7  Ctrl+Z \u64A4\u9500  \u00B7  Del \u79FB\u9664');