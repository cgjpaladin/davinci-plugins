const APP_VERSION='DEV';
const APP_BRANCH='';
const APP_BUILD_TIME='';
const IS_PRODUCTION=false;
// 创壹特供版 v1.0 — 表格版前端
// ═══ 立即执行 ═══
document.addEventListener('DOMContentLoaded',()=>{
  document.getElementById('debugMode').textContent='JS ✓';
  if(!window.pywebview || !window.pywebview.api) init();
});
// ═══ State ═══
window.onerror=function(m,s,l,c,e){const msg='JS错误: '+(m||'未知')+' @ '+(s||'?')+':'+l;toast(msg);call('debug_log',msg);return false};
window.addEventListener('unhandledrejection',e=>{const msg='Promise错误: '+e.reason;toast(msg);call('debug_log',msg)});
const _origErr=console.error;console.error=function(...a){_origErr.apply(console,a);call('debug_log','CONSOLE: '+a.join(' '))};

let files=[], _firstDrop=true, sel=new Set(), undoAvail=false, _thumbs={};
let _sortKey=null,_sortAsc=true;
const _sortKeys={base:'basename',ep:'ep',sc:'sc',shot:'shot',tk:'tk',desc:'desc',type:'type',author:'author',ver:'ver',status:'status'};
function applySort(){if(!_sortKey||!files.length)return;const key=_sortKeys[_sortKey]||_sortKey;if(key==='basename'){files.sort((a,b)=>(a.basename||'').localeCompare(b.basename||''));if(!_sortAsc)files.reverse();return}const s0=files[0].fields[key];const cmp=typeof s0==='string'?((a,b)=>(a.fields[key]||'').localeCompare(b.fields[key]||'')):((a,b)=>parseInt(a.fields[key]||0)-parseInt(b.fields[key]||0));files.sort((a,b)=>_sortAsc?cmp(a,b):cmp(b,a))}
function reindex(){files.forEach((f,i)=>{f._idx=i})}
function updSortIndicators(){
  const tr=document.querySelector('#fileList thead tr');if(!tr)return;
  tr.querySelectorAll('th').forEach(th=>{
    const t=th.textContent.replace(/ [▲▼]$/,'');th.textContent=t;
    const cls=th.className.replace('col-','');
    if(cls===_sortKey)th.textContent=t+(_sortAsc?' ▲':' ▼');
  });
}
const DIGIT_RULES={ep:/^\d{0,3}$/,sc:/^\d{0,2}$/,ver:/^\d{0,2}$/};
const DIGIT_STRICT={ep:/^(0[1-9]|[1-9]\d{1,2})$/,sc:/^(0[1-9]|[1-9]\d)$/,ver:/^(0[1-9]|[1-9]\d)$/};
const tc=['#2a3a1a','#1a2a3a','#3a201a','#2a1a3a','#1a3a2a','#3a301a','#1a3a3a','#302a1a'];
const _REQUIRED_KEYS=['ep','sc','shot','type','author','ver','status'];
const _REQUIRED_PIC=[..._REQUIRED_KEYS,'desc'];

// ═══ API ═══
function call(m,...a){
  try{if(window.pywebview&&window.pywebview.api)return window.pywebview.api[m](...a);}
  catch(e){toast("API错误: "+m);return null}
  return mock(m,...a);
}
function mock(m,...a){
  return new Promise(r=>{
    const cfg_fields=[{key:'ep',label:'集数',def:'',hint:'01'},{key:'sc',label:'场次',def:'',hint:'01'},{key:'shot',label:'镜号',def:'',hint:'01'},{key:'desc',label:'镜头描述',def:'',hint:'仅图片'},{key:'type',label:'类型',def:''},{key:'author',label:'制作者',def:'',hint:'英文姓名'},{key:'ver',label:'版本号',def:'01',hint:'01'},{key:'status',label:'状态',def:'',dv:['请选择','OK','KP','NG']}];
    const fmt=[{pfx:'EP',key:'ep'},{pfx:'SC',key:'sc'},{pfx:'SH',key:'shot'},{pfx:'TK',key:'tk'},{pfx:'',key:'desc'},{pfx:'',key:'type'},{pfx:'',key:'author'},{pfx:'V',key:'ver'},{pfx:'',key:'status'}];
    switch(m){
      case'get_config':r({fields:cfg_fields,defaults:{},name_format:fmt,dev:true});break;
      case'do_rename':r({ok:1,total:1,fail:[],renamed:[]});break;
      case'do_undo':r({ok:0,msg:'Mock: 无操作'});break;
      case'add_files_via_dialog':case'add_folder_via_dialog':
        r({files:[
          {path:'/mock/ep01_sc01_sh01_aipic.png',basename:'EP01_SC01_SH01_TK01_测试_AIPIC_张三_V01_OK.png',ext:'.png',fields:{ep:'01',sc:'01',shot:'01',desc:'测试',type:'AIPIC',author:'张三',ver:'01',status:'OK'},tags:[],_shots:['01']},
          {path:'/mock/ep01_sc01_sh01_aivid.mp4',basename:'EP01_SC01_SH01_TK01_AIVID_李四_V01_OK.mp4',ext:'.mp4',fields:{ep:'01',sc:'01',shot:'01',desc:'',type:'AIVID',author:'李四',ver:'01',status:'OK'},tags:[],_shots:['01']},
          {path:'/mock/ep01_sc01_multi.mp4',basename:'EP01_SC01_SH01-02_TK01_AIVID_王五_V02_KP.mp4',ext:'.mp4',fields:{ep:'01',sc:'01',shot:'01-02',desc:'',type:'AIVID',author:'王五',ver:'02',status:'KP'},tags:[],_shots:['01','02']},
        ],total:3,duplicates:0});break;
      case'debug_log':r('ok');break;
      default:r({});
    }
  });
}

// ═══ Load ═══
async function init(){
  if(window._initialized)return;window._initialized=true;
  const dm=document.getElementById('debugMode');
  const isLive=_isLive();dm.textContent=isLive?'✔ Live':'✖ Mock';call("debug_log",`APP START: ${isLive?"pywebview":"MOCK"} mode, files=${files.length}`);

  const cfg=await call('get_config');
  _nameFmt=cfg.name_format||[];
  const _allFields=cfg.fields||[];
  window._fieldLabels={};_allFields.forEach(f=>{window._fieldLabels[f.key]=f.label});
  dm.textContent=IS_PRODUCTION?'📋':(cfg.dev?('🔧 '+APP_VERSION):'📋');
  dm.onclick=()=>{window.pywebview.api.debug_log('').then(r=>{const t=(r.log||[]).join('\n');if(t)navigator.clipboard.writeText(t).then(()=>toast('已复制 '+(r.log||[]).length+' 条日志'));else toast('无日志')})};

  const theadTr=document.querySelector('#fileList thead tr');
  const baseTh=theadTr.querySelector('.col-base');
  const headerKeys=['ep','sc','shot','tk','desc','type','author','ver','status'];
  const headerLabels={ep:'EP 集数',sc:'SC 场次',shot:'SH 镜号',tk:'TK 次数',desc:'镜头描述',type:'类型',author:'制作者',ver:'V 版本',status:'状态'};
  headerKeys.forEach(k=>{const th=document.createElement('th');th.className='col-'+k;th.textContent=headerLabels[k]||k;theadTr.insertBefore(th,baseTh)});
  window._headerKeys=headerKeys;

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
  _initColResize();

  setTimeout(()=>{
    if(window.pywebview)return;
    const dz=document.getElementById('fileList');
    dz.addEventListener('dragover',e=>{e.preventDefault()});
    dz.addEventListener('drop',e=>{e.preventDefault();const items=[...e.dataTransfer.files].filter(f=>f.name.match(/\.(mp4|mov|mxf|avi|mkv|png|jpg|jpeg|bmp|tiff|tif)$/i));if(!items.length)return;const mockFiles=items.map(f=>({path:f.name,basename:f.name,ext:'.'+(f.name.split('.').pop()||'mp4'),fields:{ep:'',sc:'',shot:'',desc:'',type:f.name.match(/\.(png|jpg|jpeg|bmp|tiff|tif)$/i)?'AIPIC':'AIVID',author:'',ver:'01',status:''},_shots:[''],tags:[]}));files=files.concat(mockFiles.filter(mf=>!files.some(ef=>ef.path===mf.path)));renderList();updButtons();toast('已追加 '+mockFiles.length+' 个文件 (预览模式)')})},500);
  setTimeout(()=>{if(!window.pywebview)_runSelfTest()},500);
  _initTBodyClick();
  renderList();
}

let _ready=false;
function _tryStart(){if(_ready)return;const live=!!(window.pywebview&&window.pywebview.api);if(!live)return;_ready=true;if(window._tryIv)clearInterval(window._tryIv);init().catch(()=>{document.getElementById('debugMode').textContent='❌ 启动失败'})}
window._tryIv=setInterval(_tryStart,300);

// ═══ Fields ═══
function getFields(){if(sel.size===0)return{};const ix=[...sel].sort((a,b)=>a-b)[0];return files[ix]?{...files[ix].fields}:{}}

// ═══ TK ═══
function buildTK(i){const fs=files[i].fields;const k=fs.ep+'|'+fs.sc+'|'+(fs.shot||'')+'|'+fs.ver;let n=0;for(let j=0;j<=i;j++){const g=files[j].fields;const jk=g.ep+'|'+g.sc+'|'+(g.shot||'')+'|'+g.ver;if(jk===k)n++}return String(n).padStart(2,'0')}
function _computeTK(i){return buildTK(i)}
let _nameFmt=[];
function buildName(f){const raw=_nameFmt.map(s=>s.pfx+(f[s.key]||'')).join('_');return raw.replace(/_+/g,'_').replace(/_$/,'')}

// ═══ Table Render ═══
function renderList(force){
  const seen=new Set();files=files.filter(f=>{const k=f.fp||f.path;if(seen.has(k)){call('debug_log','renderList: DROP dup fp='+k.slice(0,50));return false}seen.add(k);return true});
  const tbody=document.querySelector('#fileList tbody');
  const empty=document.querySelector('#fileList .fl-empty');
  const thead=document.querySelector('#fileList thead');
  if(files.length===0){tbody.innerHTML='';empty.classList.add('show');if(thead)thead.style.display='none';updCount();updButtons();return}
  empty.classList.remove('show');if(thead)thead.style.display='';

  const rows=[...tbody.querySelectorAll('tr')];
  if(force||rows.length!==files.length){
    const s=new Set();const dd=[];for(const f of files){const k=f.fp||f.path;if(!s.has(k)){s.add(k);dd.push(f)}}if(dd.length!==files.length)files=dd;
    call('debug_log',`renderList: FORCE rows=${rows.length} files=${files.length}`);
    tbody.innerHTML='';files.forEach((f,i)=>{tbody.appendChild(_buildRow(f,i))});
  }else{
    files.forEach((f,i)=>{
      const tr=rows[i];tr.className='';tr.dataset.index=i;tr.dataset.path=f.path;
      if(sel.has(i))tr.classList.add('sel');
      const ff={...f.fields,tk:_computeTK(i)};
      const req=ff.type==='AIPIC'?_REQUIRED_PIC:_REQUIRED_KEYS;
      const ready=req.every(k=>ff[k]&&ff[k]!=='请选择');
      tr.classList.add(ready?'rdy':'mis');
      if(f.archived)tr.classList.add('archived');
      const fillCount=[ff.ep,ff.sc,ff.shot,ff.desc,ff.type,ff.author,ff.ver,ff.status].filter(Boolean).length;
      const fillMax=ff.type==='AIPIC'?9:7;
      tr.classList.add(fillCount>=fillMax?'row-full':fillCount>=5?'row-most':'row-empty');
      const tags=f.tags||[];if(tags.length)tr.classList.add('warn');
      if(tags.includes('zero'))tr.classList.add('warn-zero');
      if(tags.includes('size'))tr.classList.add('warn-size');
      if(tags.includes('dbl_ext'))tr.classList.add('warn-dbl');
    });
  }
  updCount();updButtons();
}

function _buildRow(f,i){
  const tr=document.createElement('tr');tr.dataset.index=i;tr.dataset.path=f.path;
  const ff={...f.fields,tk:_computeTK(i)};
  const req=ff.type==='AIPIC'?_REQUIRED_PIC:_REQUIRED_KEYS;
  const ready=req.every(k=>ff[k]&&ff[k]!=='请选择');
  if(sel.has(i))tr.classList.add('sel');
  tr.classList.add(ready?'rdy':'mis');
  if(f.archived)tr.classList.add('archived');
  const fillCount=[ff.ep,ff.sc,ff.shot,ff.desc,ff.type,ff.author,ff.ver,ff.status].filter(Boolean).length;
  const fillMax=ff.type==='AIPIC'?9:8;
  tr.classList.add(fillCount>=fillMax?'row-full':fillCount>=5?'row-most':'row-empty');
  const tags=f.tags||[];if(tags.length)tr.classList.add('warn');
  if(tags.includes('zero'))tr.classList.add('warn-zero');
  if(tags.includes('size'))tr.classList.add('warn-size');
  if(tags.includes('dbl_ext'))tr.classList.add('warn-dbl');

  const tdNum=document.createElement('td');tdNum.className='col-num';tdNum.dataset.row=i;
  const pl=files.length>=100?3:files.length>=10?2:1;
  tdNum.appendChild(Object.assign(document.createElement('span'),{textContent:String(i+1).padStart(pl,'0')}));tr.appendChild(tdNum);
  const tdThumb=document.createElement('td');tdThumb.className='col-thumb';tdThumb.title='双击预览';
  const tsrc=_thumbs[f.path];
  if(tsrc){const img=document.createElement('img');img.className='cell-thumb';img.src=tsrc;img.alt='';tdThumb.appendChild(img)}
  else{const div=document.createElement('div');div.className='cell-thumb';div.style.background=`linear-gradient(135deg,${tc[i%tc.length]},${tc[(i+2)%tc.length]})`;tdThumb.appendChild(div)}
  tr.appendChild(tdThumb);
  for(const key of(window._headerKeys||['ep','sc','shot','tk','desc','type','author','ver','status'])){tr.appendChild(buildCellTD(key,ff,i))}
  const tdBase=document.createElement('td');tdBase.className='col-base';
  let baseText=f.basename||'';const tooltips=[];
  if(tags.length){const lbl={zero:'⚠零字节',size:'⚠大小异常',dbl_ext:'⚠双扩展名'};tooltips.push(...tags.map(t=>lbl[t]||t));baseText+=' · '+tags.map((t,i)=>i<2?'⚠':'').join('')}
  if(!ready){const lb={ep:'EP',sc:'SC',shot:'SH',desc:'描述',type:'类型',author:'作者',ver:'版本',status:'状态'};for(const k of req){if(!ff[k]||ff[k]==='请选择')tooltips.push('✎缺失: '+lb[k])}}
  tdBase.appendChild(Object.assign(document.createElement('span'),{textContent:baseText}));
  if(tooltips.length)tdBase.title=tooltips.join('\n');tr.appendChild(tdBase);
  return tr;
}

function _initTBodyClick(){
  const tbody=document.querySelector('#fileList tbody');if(!tbody||tbody._clickInit)return;tbody._clickInit=true;
  tbody.addEventListener('click',e=>{
    const td=e.target.closest('td');if(!td)return;const tr=td.closest('tr');if(!tr)return;
    const i=parseInt(tr.dataset.index);if(isNaN(i))return;if(files[i]&&files[i].archived)return;
    if(td.classList.contains('editing'))return;
    const key=td.dataset.key;
    call('debug_log',`click: td=${td.className} i=${i} key=${key||'-'} detail=${e.detail}`);
    const isField=key&&key!=='tk'&&!td.classList.contains('readonly');
    // 缩略图双击 → 审查模式
    if(td.classList.contains('col-thumb')&&e.detail>=2){call('debug_log',`review: thumb dblclick i=${i}`);clearTimeout(window._shrinkTimer);if(files[i])openReview(i);return}
    if(isField){if(e.detail>=2){clearTimeout(window._shrinkTimer);activateEdit(td,key,i)}else{rowClick(e,i)}return}
    rowClick(e,i);
  });
}

function rowClick(e,i){
  if(e.metaKey||e.ctrlKey){if(sel.has(i))sel.delete(i);else sel.add(i)}
  else if(e.shiftKey&&sel.size>0){const s=[...sel].sort((a,b)=>a-b);const lo=Math.min(s[0],i),hi=Math.max(s[0],i);for(let j=lo;j<=hi;j++)sel.add(j)}
  else if(sel.has(i)){if(sel.size>1){clearTimeout(window._shrinkTimer);window._shrinkTimer=setTimeout(()=>{sel.clear();sel.add(i);renderList();updButtons()},350);return}else return}
  else{sel.clear();sel.add(i)}
  renderList();updButtons();
}

function buildCellTD(key,ff,i){
  const td=document.createElement('td');td.className=`col-${key}`;td.dataset.key=key;td.dataset.row=i;
  const v=ff[key]||'';td.dataset.value=v;
  if(key==='tk'){td.appendChild(Object.assign(document.createElement('span'),{textContent:v}));td.classList.add('readonly');return td}
  if(key==='type'){td.appendChild(Object.assign(document.createElement('span'),{textContent:v||'—'}));td.classList.add('readonly');if(!v)td.classList.add('empty');return td}
  if(key==='desc'&&ff.type==='AIVID'){td.appendChild(Object.assign(document.createElement('span'),{textContent:'视频无需描述'}));td.classList.add('readonly');return td}
  const s=document.createElement('span');s.textContent=v||'—';
  if(v===''||v==='请选择'){s.textContent='—';td.classList.add('empty')}
  td.appendChild(s);
  return td;
}

function activateEdit(td,key,i){
  if(td.classList.contains('editing')){call('debug_log',`activateEdit: SKIP already editing ${key}`);return;}
  call('debug_log',`activateEdit: key=${key} i=${i} oldVal='${td.dataset.value||'(空)'}' sel=${sel.size}`);
  if(window._activeCancel){window._activeCancel();window._activeCancel=null}
  const oldVal=td.dataset.value;
  if(sel.size>1&&sel.has(i)){const lbls={ep:'EP',sc:'SC',shot:'SH',desc:'描述',author:'作者',ver:'版本',status:'状态'};toast('编辑 '+sel.size+' 个文件的 '+((lbls[key]||key)))}
  if(key==='shot'){activateShotEdit(td,i,oldVal);return}

  const isSelect=(key==='status');
  let el;
  if(key==='status'){
    el=document.createElement('select');
    ['请选择','OK','KP','NG'].forEach(s=>{const o=document.createElement('option');o.value=s==='请选择'?'':s;o.textContent=s;if(s===oldVal)o.selected=true;el.appendChild(o)});
  }else{
    el=document.createElement('input');el.type='text';el.value=oldVal;
    if(['ep','sc','ver'].includes(key))el.setAttribute('inputmode','numeric');
    if(key==='author')el.placeholder='英文姓名';
    if(key==='desc')el.placeholder='请输入镜头描述';
  }

  td.classList.add('editing');td.textContent='';td.appendChild(el);
  if(el.tagName==='INPUT'&&!el.readOnly){el.focus();el.select()}else el.focus();

  if(key==='author'){el.addEventListener('input',()=>{const pos=el.selectionStart;el.value=el.value.replace(/[^a-zA-Z]/g,'');el.selectionStart=el.selectionEnd=Math.min(pos,el.value.length)})}
  if(key==='desc'){el.addEventListener('input',()=>{const pos=el.selectionStart;el.value=el.value.replace(/[^\u4e00-\u9fff\u3400-\u4dbfa-zA-Z0-9]/g,'');el.selectionStart=el.selectionEnd=Math.min(pos,el.value.length)})}

  const commit=(cancel)=>{
    const v=(el.value||'').trim();
    if(cancel){el.remove();td.classList.remove('editing');call('debug_log',`commit: CANCEL ${key} restore='${oldVal||'(空)'}'`);td.textContent=oldVal||(oldVal===''||oldVal==='请选择'?'—':oldVal);if(oldVal===''||oldVal==='请选择')td.classList.add('empty');return}
    const sr=DIGIT_STRICT[key];if(sr&&v&&!sr.test(v)){toast('请输入正确格式');el.remove();td.classList.remove('editing');td.textContent=oldVal||'—';if(!oldVal)td.classList.add('empty');return}
    el.remove();td.classList.remove('editing');
    let finalVal=v;
    if(key==='desc')finalVal=v.replace(/[^\u4e00-\u9fff\u3400-\u4dbfa-zA-Z0-9]/g,'');
    if(key==='author')finalVal=v.replace(/[^a-zA-Z]/g,'');

    const isMulti=sel.size>1;
    if(finalVal!==oldVal||isMulti){const rows=isMulti?[...sel]:[i];rows.forEach(r=>{files[r].fields[key]=finalVal});call('debug_log',`edit ${key}: ${oldVal||'(空)'} → ${finalVal||'(空)'} on ${rows.length} row(s)`);renderList(true);return}
    call('debug_log',`commit: NOCHANGE ${key} val='${finalVal||'(空)'}'`);
    const s=document.createElement('span');s.textContent=oldVal||(oldVal===''||oldVal==='请选择'?'—':oldVal);td.appendChild(s);
    if(oldVal===''||oldVal==='请选择')td.classList.add('empty');renderList();
  };

  if(isSelect){
    window._activeCancel=()=>commit(true);
    el.addEventListener('change',()=>{window._activeCancel=null;commit(false)});
  }else{
    window._activeCancel=()=>commit(true);
    el.addEventListener('keydown',e=>{if(e.key==='Enter'){e.preventDefault();window._activeCancel=null;commit(false)}if(e.key==='Escape'){el.value=oldVal;window._activeCancel=null;commit(true)}});
    el.addEventListener('blur',()=>{if(window._activeCancel){window._activeCancel=null;commit(false)}});
  }
}

// ═══ SH 多镜编辑器 ═══
function activateShotEdit(td,i,oldVal){
  const shots=(oldVal||'').split('-').filter(v=>v);
  if(!shots.length)shots.push('');
  td.classList.add('editing');td.textContent='';
  const ct=document.createElement('div');ct.className='shot-edit-panel';

  function _mkRow(v){const r=document.createElement('div');r.className='shot-edit-row';const ip=document.createElement('input');ip.value=v||'';ip.setAttribute('inputmode','numeric');
    // 实时只允许数字
    ip.addEventListener('input',()=>{let x=ip.value.replace(/[^\d]/g,'');if(x.length>2)x=x.slice(0,2);if(x!==ip.value)ip.value=x});
    // 失焦补零
    ip.addEventListener('blur',()=>{const x=ip.value.replace(/[^\d]/g,'');if(x&&x.length<2&&parseInt(x,10)>0){ip.value=x.padStart(2,'0')}});
    r.appendChild(ip);const btn=document.createElement('button');btn.textContent='+';btn.className='shot-act shot-add-btn';r.appendChild(btn);return r}

  shots.forEach(v=>ct.appendChild(_mkRow(v)));
  _updShotBtns(ct);
  // 提示
  const hint=document.createElement('div');hint.className='shot-hint';hint.textContent='+ 添加镜号 · − 删除 · ESC 取消';ct.appendChild(hint);
  td.appendChild(ct);
  ct.querySelector('input').focus();

  function _updShotBtns(c){const rows=c.querySelectorAll('.shot-edit-row');rows.forEach((r,j)=>{const btn=r.querySelector('button');if(j===rows.length-1){btn.textContent='+';btn.className='shot-act shot-add-btn';btn.onclick=()=>{c.appendChild(_mkRow(''));_updShotBtns(c);c.querySelectorAll('input')[c.querySelectorAll('input').length-1].focus()}}else{btn.textContent='−';btn.className='shot-act shot-del-btn';btn.onclick=()=>{if(c.querySelectorAll('.shot-edit-row').length<=1)return;r.remove();_updShotBtns(c)}}})}

  const commit=(cancel)=>{
    if(cancel){td.textContent='';td.classList.remove('editing');call('debug_log',`commit: CANCEL shot restore='${oldVal||'(空)'}'`);td.appendChild(Object.assign(document.createElement('span'),{textContent:oldVal||'—'}));if(!oldVal)td.classList.add('empty');return}
    const vals=[...ct.querySelectorAll('input')].map(ip=>{let v=ip.value.replace(/[^\d]/g,'');if(v.length>2)v=v.slice(0,2);const n=parseInt(v,10);return (n>0&&n<100)?String(n).padStart(2,'0'):''}).filter(v=>v);
    const nv=vals.join('-');
    const isMulti=sel.size>1;const rows=isMulti?[...sel]:[i];
    rows.forEach(r=>{files[r].fields.shot=nv||'';files[r]._shots=vals.length?vals:['']});
    call('debug_log',`edit shot: ${oldVal||'(空)'} → ${nv||'(空)'} on ${rows.length} row(s)`);
    td.textContent='';td.classList.remove('editing');renderList(true);
  };

  window._activeCancel=()=>commit(true);
  let _clickOut=null;
  ct.addEventListener('keydown',e=>{if(e.key==='Escape'){if(_clickOut){document.removeEventListener('click',_clickOut);_clickOut=null}window._activeCancel=null;commit(true)}});
  // click outside → commit
  setTimeout(()=>{
    _clickOut=function _out(e){if(!td.contains(e.target)){document.removeEventListener('click',_out);_clickOut=null;if(window._activeCancel){window._activeCancel=null;const hasVal=[...ct.querySelectorAll('input')].some(ip=>ip.value.trim());commit(!hasVal)}}};
    document.addEventListener('click',_clickOut);
  },0);
}

function updCount(){
  let ok2=0;files.forEach(f=>{const ff=f.fields;const req=ff.type==='AIPIC'?_REQUIRED_PIC:_REQUIRED_KEYS;if(req.every(k=>ff[k]&&ff[k]!=='请选择'))ok2++});
  document.getElementById('fileCount').innerHTML=`文件列表 · <span style="color:var(--green)">${ok2}</span>/${files.length} 就绪  ·  选中 ${sel.size}`;
}
function updButtons(){
  const hf=files.length>0,hs=sel.size>0,fd=getFields();
  let af=true;
  if(hs){for(const i of sel){const ff=files[i].fields;const req=ff.type==='AIPIC'?_REQUIRED_PIC:_REQUIRED_KEYS;if(!req.every(k=>ff[k]&&ff[k]!=='请选择')){af=false;break}}}
  document.getElementById('btnRename').disabled=!(hs&&af);
  document.getElementById('btnUndo').disabled=!undoAvail;
  const dot=document.querySelector('.sb-dot');
  if(!hf){dot.style.background='var(--green)';setStatus('就绪  ·  拖入文件开始  ·  Ctrl+Z 撤销  ·  Del 移除');return}
  if(hs&&af){dot.style.background='var(--green)';setStatus('字段齐全，点击重命名  ·  Ctrl+Enter 重命名');call('debug_log',`updButtons: GREEN hs=${hs} af=${af}`);return}
  // 全部就绪但未选中 → 绿色
  let ok=0;files.forEach(f=>{const ff=f.fields;const req=ff.type==='AIPIC'?_REQUIRED_PIC:_REQUIRED_KEYS;if(req.every(k=>ff[k]&&ff[k]!=='请选择'))ok++});
  if(ok===files.length&&files.length>0){dot.style.background='var(--green)';setStatus('全部就绪 · 选中文件后重命名  ·  Ctrl+Enter');call('debug_log',`updButtons: ALL-GREEN ok=${ok}/${files.length}`);return}
  const missing=[];const _lbs=window._fieldLabels||{};
  const fdType=fd.type||''; const chkKeys=fdType==='AIPIC'?_REQUIRED_PIC:_REQUIRED_KEYS;
  for(const k of chkKeys){if(!fd[k]||fd[k]==='请选择')missing.push(_lbs[k]||k)}
  let warn=[];for(const t of files){if(t.tags&&t.tags.length)warn.push(...t.tags)}
  if(warn.length){const wl={zero:'零字节',size:'大小异常',dbl_ext:'双扩展名'};dot.style.background='var(--red)';setStatus('⚠ '+[...new Set(warn)].map(w=>wl[w]||w).join(' · '));return}
  dot.style.background='var(--yellow)';call('debug_log',`updButtons: YELLOW ok=${ok}/${files.length} hs=${hs} missing=${missing.join(',')}`);
  setStatus((missing.length?('双击单元格编辑 · 缺失: '+missing.join(' · ')):'双击单元格编辑字段')+'  ·  '+ok+'/'+files.length+' 就绪');
}

// ═══ Dialog ═══
function showDialog(title,msg){return new Promise(r=>{document.getElementById('dialogTitle').textContent=title;document.getElementById('dialogMsg').textContent=msg;document.getElementById('dialogOverlay').classList.add('show');document.getElementById('dialogOk').onclick=()=>{document.getElementById('dialogOverlay').classList.remove('show');r(true)};document.getElementById('dialogCancel').onclick=()=>{document.getElementById('dialogOverlay').classList.remove('show');r(false)}})}

// ═══ Actions ═══
async function addFiles(){const r=await call('add_files_via_dialog');if(r&&r.files){const ex=new Set(files.map(f=>f.path));const fr=r.files.filter(f=>!ex.has(f.path));files=files.concat(fr);applySort();reindex();r.total=fr.length;r.duplicates=r.files.length-fr.length;call("debug_log",`FILES list: ${files.length} total (addFiles)`);renderList();_toastResult(r);loadThumbs()}}
async function addFolder(){const r=await call('add_folder_via_dialog');if(r&&r.files){const ex=new Set(files.map(f=>f.path));const fr=r.files.filter(f=>!ex.has(f.path));files=files.concat(fr);applySort();reindex();r.total=fr.length;r.duplicates=r.files.length-fr.length;call("debug_log",`FILES list: ${files.length} total (addFolder)`);renderList();_toastResult(r);loadThumbs()}}
function _toastResult(r){let m=`已追加 ${r.total} 个文件`;if(r.duplicates)m+=` · ${r.duplicates} 个重复跳过`;if(r.subdirs_skipped)m+=` · ${r.subdirs_skipped} 个子文件夹跳过`;if(r.truncated)m+=` (上限${r.max}个)`;toast(m)}

async function doRename(){
  if(sel.size===0)return;
  const srt=[...sel].sort((a,b)=>a-b);
  const sfs=srt.map((i,p)=>{const f={...files[i]};f.fields={...f.fields,tk:buildTK(i)};return f});
  const nm=buildName(sfs[0].fields)+sfs[0].ext;
  const msg=sfs.length===1?`确认重命名?\n${sfs[0].basename}\n→ ${nm}`:`确认重命名 ${sfs.length} 个?\n${buildName(sfs[0].fields)+sfs[0].ext}\n  ...\n${buildName(sfs[sfs.length-1].fields)+sfs[sfs.length-1].ext}`;
  if(!await showDialog('确认重命名',msg))return;
  call('debug_log','rename: starting '+sfs.length+' files');
  const r=await call('do_rename',sfs);
  call('debug_log','rename: ok='+r.ok+' fail='+(r.fail||[]).length+' depth='+(r.stack_depth||0));
  if(r.ok>0){undoAvail=true;r.renamed.forEach(rn=>{const f=files.find(x=>x.path===rn.old_path);if(f){f.path=rn.new_path;f.basename=rn.new_path.replace(/^.*[/\\]/,'')}});r.renamed.forEach(rn=>{if(_thumbs[rn.old_path]){_thumbs[rn.new_path]=_thumbs[rn.old_path];delete _thumbs[rn.old_path]}});toast(`完成 ${r.ok}/${r.total}`);result(`✅ 重命名完成 ${r.ok}/${r.total}`)}
  if(r.fail&&r.fail.length)result(`✅ 重命名完成 ${r.ok}/${r.total}  ·  ⚠️ ${r.fail.join('; ')}`);
  renderList();updButtons();
}

async function doUndo(){
  call('debug_log','undo: starting');
  const r=await call('do_undo');call('debug_log','undo: ok='+r.ok+' remaining='+(r.remaining||0));
  toast(r.msg);result(r.msg);undoAvail=(r.remaining||0)>0;
  if(r.renamed){r.renamed.forEach(rn=>{const f=files.find(x=>x.path===rn.old_path);if(f)f.path=rn.new_path;if(_thumbs[rn.old_path]){_thumbs[rn.new_path]=_thumbs[rn.old_path];delete _thumbs[rn.old_path]}})}
  renderList();updButtons();
}
function removeSelected(){if(sel.size===0)return;call('debug_log','remove: '+sel.size+' files');files=files.filter((_,i)=>!sel.has(i));sel.clear();renderList();toast('已移除')}

// ═══ Thumbnails ═══
async function loadThumbs(){const paths=files.map(f=>f.path);call('debug_log','loadThumbs: '+paths.length+' files');const r=await call('generate_thumbnails',paths);call('debug_log','loadThumbs done: '+(r?r.total:0)+' thumbs')}
function setThumb(path,thumb){_thumbs[path]=thumb;const el=document.querySelector(`[data-path="${CSS.escape(path)}"]`);if(!el)return;let thumbEl=el.querySelector('.cell-thumb');if(thumbEl&&thumbEl.tagName==='DIV'){const img=document.createElement('img');img.className='cell-thumb';img.src=thumb;img.alt='';thumbEl.replaceWith(img)}else if(thumbEl)thumbEl.src=thumb}

// ═══ Drag & Drop ═══
function _isLive(){return!!(window.pywebview&&window.pywebview.api)}
let dg=0;
const dropZone=document.getElementById('fileList');const overlay=document.getElementById('dropOverlay');
dropZone.addEventListener('dragover',e=>{e.preventDefault();if(e.dataTransfer)e.dataTransfer.dropEffect='copy'});
dropZone.addEventListener('dragenter',e=>{e.preventDefault();dg++;overlay.classList.add('show')});
dropZone.addEventListener('dragleave',e=>{e.preventDefault();dg--;if(dg<=0){dg=0;overlay.classList.remove('show')}});
dropZone.addEventListener('drop',e=>{e.preventDefault();dg=0;overlay.classList.remove('show')});

let _dropCount=0;
function onDropResult(result){
  if(!result||!result.files)return;_dropCount++;
  if(_firstDrop){_firstDrop=false;call('debug_log',`_firstDrop: was ${files.length}, clearing`);files=[];sel.clear()}
  call('debug_log',`onDropResult #${_dropCount}: ${result.files.length} files, existing=${files.length}`);
  const exist=new Set(files.map(f=>f.fp||f.path));
  const fresh=result.files.filter(f=>!(exist.has(f.fp||f.path)));
  const dup=result.duplicates||0;
  const sk=result.skipped||0;
  if(fresh.length===0&&dup===0&&sk>0){toast(`${sk} 个格式不支持`);return}
  if(fresh.length===0){const skipped=result.files.length;toast(`全部重复 · ${skipped} 个已跳过`);return}
  fresh.forEach(f=>{if(!f._shots){f._shots=(f.fields.shot||'').split('-').filter(v=>v);if(!f._shots.length)f._shots=['']}});
  files=files.concat(fresh);applySort();reindex();
  let msg=`已追加 ${fresh.length} 个文件`;if(dup)msg+=` · ${dup} 个重复跳过`;if(sk)msg+=` · ${sk} 个格式不支持`;if(result.subdirs_skipped)msg+=` · ${result.subdirs_skipped} 个子文件夹跳过`;if(result.truncated)msg+=` (上限${result.max}个)`;
  renderList();toast(msg);loadThumbs();
}

// ═══ Keyboard ═══
document.addEventListener('keydown',e=>{
  // 审查模式快捷键（输入框中不触发）
  if(_reviewIdx>=0&&e.target.tagName!=='INPUT'&&e.target.tagName!=='TEXTAREA'){
    if(e.key==='Escape'){e.preventDefault();closeReview();return}
    if(e.ctrlKey&&e.key==='ArrowLeft'){e.preventDefault();navReview(-1);return}
    if(e.ctrlKey&&e.key==='ArrowRight'){e.preventDefault();navReview(1);return}
    if(e.key===' '){e.preventDefault();const v=document.getElementById('reviewVideo');if(v.src){if(v.paused){v.play();document.getElementById('rcPlay').textContent='⏸'}else{v.pause();document.getElementById('rcPlay').textContent='▶'}};return}
    if(e.key==='ArrowLeft'&&!e.ctrlKey){const v=document.getElementById('reviewVideo');if(v.src&&v.duration){v.currentTime=Math.max(0,v.currentTime-2);return}}
    if(e.key==='ArrowRight'&&!e.ctrlKey){const v=document.getElementById('reviewVideo');if(v.src&&v.duration){v.currentTime=Math.min(v.duration,v.currentTime+2);return}}
    if(e.key===','){const v=document.getElementById('reviewVideo');if(v.src){v.pause();v.currentTime=Math.max(0,v.currentTime-1/25);document.getElementById('rcPlay').textContent='▶';return}}
    if(e.key==='.'){const v=document.getElementById('reviewVideo');if(v.src){v.pause();v.currentTime=Math.min(v.duration||999,v.currentTime+1/25);document.getElementById('rcPlay').textContent='▶';return}}
    // JKL 穿梭
    if(e.key==='j'||e.key==='J'){
      const v=document.getElementById('reviewVideo');if(!v.src)return;
      const rates=[1,0.5,0.25,0.1];let ri=rates.indexOf(v.playbackRate);ri=ri<0?0:(ri+1)%rates.length;
      v.playbackRate=rates[ri];document.getElementById('rcSpeed').textContent=rates[ri]+'×';
      if(v.paused){v.play();document.getElementById('rcPlay').textContent='⏸'}
      return;
    }
    if(e.key==='k'||e.key==='K'){
      const v=document.getElementById('reviewVideo');if(!v.src)return;
      v.pause();v.playbackRate=1;document.getElementById('rcPlay').textContent='▶';document.getElementById('rcSpeed').textContent='1×';
      return;
    }
    if(e.key==='l'||e.key==='L'){
      const v=document.getElementById('reviewVideo');if(!v.src)return;
      const rates=[1,2,4,8];let ri=v.paused?0:rates.indexOf(v.playbackRate);ri=ri<0?0:(ri+1)%rates.length;
      v.playbackRate=rates[ri];document.getElementById('rcSpeed').textContent=rates[ri]+'×';
      if(v.paused){v.play();document.getElementById('rcPlay').textContent='⏸'}
      return;
    }
  }
  if((e.ctrlKey||e.metaKey)&&e.key==='z'){e.preventDefault();doUndo()}
  if((e.ctrlKey||e.metaKey)&&e.key==='Enter'){e.preventDefault();doRename();return}
  if((e.key==='Delete'||e.key==='Backspace')&&e.target.tagName!=='INPUT'&&e.target.tagName!=='SELECT'){e.preventDefault();removeSelected()}
  if((e.key==='ArrowUp'||e.key==='ArrowDown')&&sel.size===1&&files.length>0){if(e.target.tagName!=='INPUT'||(e.key==='ArrowUp'&&e.target.selectionStart===0)||(e.key==='ArrowDown'&&e.target.selectionStart===e.target.value.length)){e.preventDefault();const cur=[...sel][0];const next=cur+(e.key==='ArrowDown'?1:-1);if(next>=0&&next<files.length){sel.clear();sel.add(next);renderList();updButtons()}}}
  if((e.key==='Home'||e.key==='End')&&sel.size===1&&files.length>0){if(e.target.tagName!=='INPUT'||e.target.selectionStart===0){e.preventDefault();const i=e.key==='Home'?0:files.length-1;sel.clear();sel.add(i);renderList();updButtons()}}
  if((e.metaKey||e.ctrlKey)&&e.key==='a'){if(e.target.tagName==='INPUT'||e.target.tagName==='TEXTAREA')return;e.preventDefault();sel=new Set([...Array(files.length).keys()]);renderList();updButtons()}
});

// ═══ 审查模式 ═══
let _reviewIdx=-1;
let _mediaBlobUrl=null;
let _metaGen=0;
const _speeds=[0.5,1,2];let _speedI=1;
function formatTime(s){if(!isFinite(s)||s<0)return'0:00';const m=Math.floor(s/60),sec=Math.floor(s%60);return m+':'+String(sec).padStart(2,'0')}

async function openReview(i){
  call('debug_log',`openReview: START i=${i} file=${files[i]?.basename}`);
  _reviewIdx=i;const f=files[i];const ff=f.fields;const isVideo=ff.type==='AIVID';
  // 标题
  const tk=buildTK(i);
  document.getElementById('reviewFilename').textContent=`EP${ff.ep||'__'}_SC${ff.sc||'__'}_SH${ff.shot||'__'}_TK${tk}${ff.type?'_'+ff.type:''}_${ff.author||'__'}_V${ff.ver||'__'}_${ff.status||'__'}`;
  // 媒体
  const video=document.getElementById('reviewVideo');video.removeAttribute('src');
  const img=document.getElementById('reviewImage');img.removeAttribute('src');
  if(_mediaBlobUrl){URL.revokeObjectURL(_mediaBlobUrl);_mediaBlobUrl=null}
  try{const r=await call('get_media_data',f.path);call('debug_log',`openReview: media r=${r?'ok':'null'} size=${r?.size||0}`);
    if(r&&r.data){
    const bytes=Uint8Array.from(atob(r.data),c=>c.charCodeAt(0));
    const blob=new Blob([bytes],{type:r.mime});
    _mediaBlobUrl=URL.createObjectURL(blob);
    if(isVideo){video.src=_mediaBlobUrl;video.style.display='';img.style.display='none';_speedI=1;document.getElementById('rcSpeed').textContent='1×';video.playbackRate=1;video.play().catch(()=>{});initReviewControls(video)}
    else{img.src=_mediaBlobUrl;img.style.display='';video.style.display='none';video.pause();document.getElementById('reviewControls').style.display='none'}
  }else{call('debug_log','openReview: NO media data')}
  }catch(e){call('debug_log','openReview: media ERROR '+e.message)}
  // 字段
  buildReviewFields(ff,isVideo);
  // 状态高亮
  highlightStatusBtn(ff.status||'');
  // 元数据
  loadMediaMeta(f.path,isVideo,video,img);
  // 导航按钮
  document.getElementById('reviewPrev').disabled=i===0;
  document.getElementById('reviewNext').disabled=i>=files.length-1;
  // 显示
  document.getElementById('reviewOverlay').classList.add('show');
  call('debug_log',`openReview: DONE i=${i} overlay=shown`);
}

function closeReview(){
  call('debug_log','closeReview: START');
  const v=document.getElementById('reviewVideo');v.pause();v.removeAttribute('src');v.load();
  document.getElementById('reviewImage').removeAttribute('src');
  if(_mediaBlobUrl){URL.revokeObjectURL(_mediaBlobUrl);_mediaBlobUrl=null}
  if(_rcInterval){clearInterval(_rcInterval);_rcInterval=null}
  _reviewIdx=-1;document.getElementById('reviewOverlay').classList.remove('show');
  document.getElementById('reviewControls').style.display='';
  renderList(true);
}

async function navReview(dir){
  const next=_reviewIdx+dir;if(next<0||next>=files.length)return;
  call('debug_log',`navReview: dir=${dir} from=${_reviewIdx} to=${next}`);
  _reviewIdx=next;
  const f=files[next];const ff=f.fields;const isVideo=ff.type==='AIVID';
  // 标题
  const tk=buildTK(next);
  document.getElementById('reviewFilename').textContent=`EP${ff.ep||'__'}_SC${ff.sc||'__'}_SH${ff.shot||'__'}_TK${tk}${ff.type?'_'+ff.type:''}_${ff.author||'__'}_V${ff.ver||'__'}_${ff.status||'__'}`;
  // 媒体
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
  // 字段 — 重建
  buildReviewFields(ff,isVideo);
  // 状态高亮
  highlightStatusBtn(ff.status||'');
  // 元数据
  loadMediaMeta(f.path,isVideo,video,img);
  // 导航按钮
  document.getElementById('reviewPrev').disabled=next===0;
  document.getElementById('reviewNext').disabled=next>=files.length-1;
  // 已编辑数据同步到表格
  renderList(true);
  call('debug_log',`navReview: DONE to=${next}`);
}

function buildReviewFields(ff,isVideo){
  const container=document.getElementById('reviewFields');container.innerHTML='';
  const fields=[
    [{key:'ep',label:'EP',w:1,attr:'inputmode=numeric maxlength=3'},{key:'sc',label:'SC',w:1,attr:'inputmode=numeric maxlength=2'}],
    [{key:'shot',label:'SH',w:1,attr:'placeholder=\"点击编辑多镜号\" readonly onclick=\"reviewShotEdit(this)\"'},{key:'ver',label:'V',w:1,attr:'inputmode=numeric maxlength=2'}],
    [{key:'author',label:'作者',w:2,attr:'placeholder=\"英文姓名\"'}],
    [{key:'desc',label:'描述',w:2,attr:'placeholder=\"镜头描述\"'+(isVideo?' readonly':'')}],
  ];
  fields.forEach(row=>{row.forEach(fd=>{
    const wrap=document.createElement('div');wrap.className=fd.w>1?'rf-full':'';
    const lb=document.createElement('label');lb.textContent=fd.label;wrap.appendChild(lb);
    const ip=document.createElement('input');ip.value=ff[fd.key]||'';
    if(fd.attr){const attrs=fd.attr.split(' ');attrs.forEach(a=>{const[ak,av]=a.split('=');if(av)ip.setAttribute(ak,av.replace(/"/g,''));else ip.setAttribute(ak,'')})}
    wrap.appendChild(ip);container.appendChild(wrap);
    // 事件
    if(fd.attr.includes('readonly')){ip.readOnly=true;return}
    const key=fd.key;
    if(key==='author'){ip.addEventListener('input',()=>{const pos=ip.selectionStart;ip.value=ip.value.replace(/[^a-zA-Z]/g,'');ip.selectionStart=ip.selectionEnd=Math.min(pos,ip.value.length);files[_reviewIdx].fields[key]=ip.value.trim();updateReviewTitle()})}
    else if(key==='desc'){ip.addEventListener('input',()=>{const pos=ip.selectionStart;ip.value=ip.value.replace(/[^\u4e00-\u9fff\u3400-\u4dbfa-zA-Z0-9]/g,'');ip.selectionStart=ip.selectionEnd=Math.min(pos,ip.value.length);files[_reviewIdx].fields[key]=ip.value.trim()})}
    else{ip.addEventListener('input',()=>{files[_reviewIdx].fields[key]=ip.value.trim();updateReviewTitle()})}
    const sr=DIGIT_STRICT[key];
    if(sr){ip.addEventListener('blur',()=>{let v=ip.value.replace(/[^\d]/g,'');if(v&&sr.test(v.padStart(2,'0'))){v=v.padStart(2,'0');ip.value=v;files[_reviewIdx].fields[key]=v}else if(!v){files[_reviewIdx].fields[key]=''}else{ip.value=ff[key]||'';files[_reviewIdx].fields[key]=ff[key]||''};updateReviewTitle()})}
  })});
}

function highlightStatusBtn(st){
  document.querySelectorAll('.review-status button').forEach(b=>b.classList.remove('active'));
  if(st==='OK')document.getElementById('rsOK').classList.add('active');
  else if(st==='KP')document.getElementById('rsKP').classList.add('active');
  else if(st==='NG')document.getElementById('rsNG').classList.add('active');
}
function updateReviewTitle(){
  if(_reviewIdx<0)return;
  const ff=files[_reviewIdx].fields;const tk=buildTK(_reviewIdx);
  document.getElementById('reviewFilename').textContent=`EP${ff.ep||'__'}_SC${ff.sc||'__'}_SH${ff.shot||'__'}_TK${tk}${ff.type?'_'+ff.type:''}_${ff.author||'__'}_V${ff.ver||'__'}_${ff.status||'__'}`;
}
function setReviewStatus(st){call('debug_log',`setReviewStatus: ${st}`);files[_reviewIdx].fields.status=st;highlightStatusBtn(st);updateReviewTitle();renderList(true)}

// SH 多镜编辑器（审阅模式）
function reviewShotEdit(ip){
  const wrap=ip.parentElement;const oldVal=ip.value||'';
  const shots=oldVal.split('-').filter(v=>v);if(!shots.length)shots.push('');
  ip.style.display='none';
  const ct=document.createElement('div');ct.className='shot-edit-panel';ct.style.position='static';ct.style.margin='0';
  function _mkRow(v){const r=document.createElement('div');r.className='shot-edit-row';const inp=document.createElement('input');inp.value=v||'';inp.setAttribute('inputmode','numeric');
    inp.addEventListener('input',()=>{let x=inp.value.replace(/[^\d]/g,'');if(x.length>2)x=x.slice(0,2);if(x!==inp.value)inp.value=x});
    inp.addEventListener('blur',()=>{const x=inp.value.replace(/[^\d]/g,'');if(x&&x.length<2&&parseInt(x,10)>0){inp.value=x.padStart(2,'0')}});
    r.appendChild(inp);const btn=document.createElement('button');btn.textContent='+';btn.className='shot-act shot-add-btn';r.appendChild(btn);return r}
  shots.forEach(v=>ct.appendChild(_mkRow(v)));
  function _updBtns(c){const rows=c.querySelectorAll('.shot-edit-row');rows.forEach((r,j)=>{const btn=r.querySelector('button');if(j===rows.length-1){btn.textContent='+';btn.className='shot-act shot-add-btn';btn.onclick=()=>{c.appendChild(_mkRow(''));_updBtns(c);c.querySelectorAll('input')[c.querySelectorAll('input').length-1].focus()}}else{btn.textContent='−';btn.className='shot-act shot-del-btn';btn.onclick=()=>{if(c.querySelectorAll('.shot-edit-row').length<=1)return;r.remove();_updBtns(c)}}})}
  _updBtns(ct);
  const commit=()=>{const vals=[...ct.querySelectorAll('input')].map(inp=>{let v=inp.value.replace(/[^\d]/g,'').slice(0,2);const n=parseInt(v,10);return(n>0&&n<100)?String(n).padStart(2,'0'):''}).filter(v=>v);const nv=vals.join('-');ip.value=nv;files[_reviewIdx].fields.shot=nv||'';files[_reviewIdx]._shots=vals.length?vals:[''];ct.remove();ip.style.display='';updateReviewTitle()};
  ct.addEventListener('keydown',e=>{if(e.key==='Escape'){ip.value=oldVal;commit()}if(e.key==='Enter'&&e.target.tagName==='INPUT'){e.preventDefault();commit()}});
  wrap.appendChild(ct);ct.querySelector('input').focus();
}
document.getElementById('rsOK').addEventListener('click',()=>setReviewStatus('OK'));
document.getElementById('rsKP').addEventListener('click',()=>setReviewStatus('KP'));  
document.getElementById('rsNG').addEventListener('click',()=>setReviewStatus('NG'));
document.getElementById('reviewPrev').addEventListener('click',()=>navReview(-1));
document.getElementById('reviewNext').addEventListener('click',()=>navReview(1));
document.getElementById('reviewClose').addEventListener('click',closeReview);
document.getElementById('reviewOverlay').addEventListener('click',e=>{if(e.target===e.currentTarget)closeReview()});
document.getElementById('reviewOverlay').addEventListener('dragover',e=>{e.preventDefault()});
document.getElementById('reviewOverlay').addEventListener('drop',e=>{e.preventDefault()});

async function loadMediaMeta(path,isVideo,video,img){
  call('debug_log',`loadMediaMeta: video=${isVideo} gen=${_metaGen}`);
  const meta=document.getElementById('reviewMeta');meta.innerHTML='';
  const parts=[];
  const f=files[_reviewIdx];
  if(f.size)parts.push(`📦 ${(f.size/1048576).toFixed(1)} MB`);
  parts.push(f.ext||'');
  const _generation=++_metaGen;
  if(isVideo){
    const onMeta=()=>{
      if(_generation!==_metaGen)return;
      if(video.videoWidth)parts.unshift(`📹 ${video.videoWidth}×${video.videoHeight}`);
      if(video.duration)parts.push(`⏱ ${formatTime(video.duration)}`);
      meta.innerHTML=parts.map(p=>`<span>${p}</span>`).join('');
    };
    if(video.readyState>=1)onMeta();else video.addEventListener('loadedmetadata',onMeta,{once:true});
    try{const r=await call('get_media_info',path);if(r&&_generation===_metaGen){
      const extra=[];
      if(r.fps)extra.push(Number(r.fps).toFixed(0)+'fps');
      if(r.codec)extra.push(r.codec.toUpperCase());
      if(extra.length)meta.innerHTML+='<span> · '+extra.join(' · ')+'</span>';
    }}catch(e){}
  }else{
    const onLoad=()=>{if(_generation!==_metaGen)return;parts.unshift(`🖼 ${img.naturalWidth}×${img.naturalHeight}`);meta.innerHTML=parts.map(p=>`<span>${p}</span>`).join('')};
    if(img.complete)onLoad();else img.addEventListener('load',onLoad,{once:true});
  }
}

// ═══ 自定义播放控制 ═══
let _rcInterval=null;
function initReviewControls(video){
  call('debug_log','initReviewControls');
  const ctrls=document.getElementById('reviewControls');ctrls.style.display='';
  // 清理旧监听器
  if(ctrls._init){video.removeEventListener('timeupdate',ctrls._ontu);video.removeEventListener('ended',ctrls._onend)}
  const playBtn=document.getElementById('rcPlay'),seek=document.getElementById('rcSeek'),
    time=document.getElementById('rcTime'),frame=document.getElementById('rcFrame'),
    vol=document.getElementById('rcVolume'),speedBtn=document.getElementById('rcSpeed');
  video.removeAttribute('controls');vol.value=video.volume*100;
  const upd=()=>{if(!video.duration)return;seek.value=(video.currentTime/video.duration)*100;time.textContent=formatTime(video.currentTime)+' / '+formatTime(video.duration);frame.textContent='帧 '+Math.floor(video.currentTime*25)}
  if(_rcInterval)clearInterval(_rcInterval);
  _rcInterval=setInterval(upd,200);
  const togglePlay=()=>{if(video.paused){video.play();playBtn.textContent='⏸'}else{video.pause();playBtn.textContent='▶'}};
  video.onclick=togglePlay;
  const ontu=()=>{if(!video.seeking)upd()};
  const onend=()=>{playBtn.textContent='▶';clearInterval(_rcInterval)};
  video.addEventListener('timeupdate',ontu);video.addEventListener('ended',onend);
  ctrls._ontu=ontu;ctrls._onend=onend;ctrls._init=true;
  playBtn.textContent=video.paused?'▶':'⏸';
  playBtn.onclick=togglePlay;
  seek.oninput=()=>{video.currentTime=(seek.value/100)*video.duration;upd()};
  vol.oninput=()=>{video.volume=vol.value/100};
  speedBtn.onclick=()=>{_speedI=(_speedI+1)%3;const s=_speeds[_speedI];video.playbackRate=s;speedBtn.textContent=s+'×'};
  document.getElementById('rcStepBack').onclick=()=>{video.pause();video.currentTime=Math.max(0,video.currentTime-1/25);playBtn.textContent='▶';upd()};
  document.getElementById('rcStepFwd').onclick=()=>{video.pause();video.currentTime=Math.min(video.duration||999,video.currentTime+1/25);playBtn.textContent='▶';upd()};
  document.getElementById('rcFS').onclick=()=>{if(video.requestFullscreen)video.requestFullscreen();else if(video.webkitRequestFullscreen)video.webkitRequestFullscreen()};
  document.getElementById('rcSnap').onclick=()=>{const c=document.createElement('canvas');c.width=video.videoWidth;c.height=video.videoHeight;c.getContext('2d').drawImage(video,0,0);const a=document.createElement('a');a.download='frame_'+formatTime(video.currentTime).replace(':','_')+'.png';a.href=c.toDataURL('image/png');a.click();toast('截图已保存')};
}

// ═══ Buttons + Zoom ═══
document.getElementById('btnAddBig').addEventListener('click',addFiles);
document.getElementById('btnRename').addEventListener('click',doRename);
document.getElementById('btnUndo').addEventListener('click',doUndo);

const zs=document.getElementById('zoomSlider'),zl=document.getElementById('zoomLabel');
let _zoomTimer=null;
zs.addEventListener('input',()=>{const v=parseInt(zs.value);zl.textContent=v+'%';document.querySelector('.file-section').style.setProperty('--thumb-scale',v/100);clearTimeout(_zoomTimer);_zoomTimer=setTimeout(()=>renderList(),80)});
document.getElementById('fileList').addEventListener('wheel',e=>{if(e.metaKey||e.ctrlKey){e.preventDefault();zs.value=Math.max(50,Math.min(200,parseInt(zs.value)+(e.deltaY<0?10:-10)));zs.dispatchEvent(new Event('input'))}});

// ═══ Column resize ═══
let _resizing=null;
function _initColResize(){
  const thead=document.querySelector('#fileList thead');if(!thead)return;
  thead.querySelectorAll('th:not(.col-base)').forEach(th=>{th.addEventListener('mousedown',e=>{const rect=th.getBoundingClientRect();if(e.clientX<rect.right-6||e.clientX>rect.right+2)return;e.preventDefault();_resizing={th,startX:e.clientX,startW:rect.width,ghost:null};const ghost=document.createElement('div');ghost.className='resize-ghost';ghost.style.left=rect.right+'px';ghost.style.top=rect.top+'px';ghost.style.height=rect.height+'px';document.body.appendChild(ghost);_resizing.ghost=ghost;th.classList.add('resizing')})});
  document.addEventListener('mousemove',e=>{if(!_resizing)return;const dx=e.clientX-_resizing.startX;const nw=Math.max(32,_resizing.startW+dx);_resizing.ghost.style.left=(_resizing.th.getBoundingClientRect().left+nw)+'px'});
  document.addEventListener('mouseup',()=>{if(!_resizing)return;const rect=_resizing.th.getBoundingClientRect();const nw=Math.max(32,rect.width+(_resizing.ghost?parseInt(_resizing.ghost.style.left)-rect.right:0));_resizing.th.style.width=nw+'px';_resizing.th.style.minWidth=nw+'px';_resizing.th.classList.remove('resizing');if(_resizing.ghost){_resizing.ghost.remove();_resizing.ghost=null}_resizing=null});
}

// ═══ Self-test ═══
function _runSelfTest(){
  const ok=[],fail=[];
  function t(name,fn){try{fn();ok.push(name)}catch(e){fail.push(name+': '+e.message)}}
  t('files array',()=>{if(!Array.isArray(files))throw new Error('files not array')});
  t('sel is Set',()=>{if(!(sel instanceof Set))throw new Error('sel not Set')});
  t('_nameFmt',()=>{if(!Array.isArray(_nameFmt))throw new Error('_nameFmt not array')});
  t('DIGIT_RULES',()=>{if(!DIGIT_RULES.ep)throw new Error('DIGIT_RULES missing')});
  t('_computeTK',()=>{files=[{fields:{ep:'01',sc:'01',shot:'01',type:'AIVID',ver:'01'}}];sel.add(0);const tk=_computeTK(0);files=[];sel.clear();if(tk!=='01')throw new Error('_computeTK '+tk)});
  t('buildTK group',()=>{files=[{fields:{ep:'01',sc:'01',shot:'01',type:'AIVID',ver:'01'}},{fields:{ep:'01',sc:'01',shot:'01',type:'AIVID',ver:'01'}}];const t2=buildTK(1);files=[];if(t2!=='02')throw new Error('buildTK '+t2)});
  t('buildName',()=>{const nm=buildName({ep:'01',sc:'01',shot:'01',tk:'01',desc:'测试',type:'AIPIC',author:'张三',ver:'01',status:'OK'});if(!nm.includes('EP01'))throw new Error(nm);if(!nm.includes('张三'))throw new Error(nm)});
  t('buildName multi-shot',()=>{const nm=buildName({ep:'01',sc:'01',shot:'01-02',tk:'01',desc:'',type:'AIVID',author:'John',ver:'01',status:'OK'});if(!nm.includes('SH01-02'))throw new Error(nm)});
  t('renderList table',()=>{files=[{path:'/t/a.mp4',basename:'a.mp4',ext:'.mp4',fields:{ep:'01',sc:'01',shot:'01',desc:'',type:'AIVID',author:'John',ver:'01',status:'OK'},_shots:['01'],tags:[]}];renderList();const tr=document.querySelector('#fileList tbody tr');if(!tr)throw new Error('no tr');const tds=tr.querySelectorAll('td');if(tds.length<12)throw new Error('expected 12+ tds, got '+tds.length);files=[];renderList()});
  call('debug_log','_runSelfTest: '+ok.length+'/'+(ok.length+fail.length)+' passed');
  if(fail.length)toast('⚠ 自测: '+ok.length+'/'+(ok.length+fail.length)+' — '+fail.join('; '));
}

// ═══ Toast ═══
let tt;function toast(m){call('debug_log','TOAST: '+m);const el=document.getElementById('toast');el.textContent=m;el.classList.add('show');clearTimeout(tt);tt=setTimeout(()=>el.classList.remove('show'),2500)}
function result(m){call('debug_log','result: '+m);document.getElementById('resultMsg').textContent=m}
function setStatus(s){document.getElementById('statusText').textContent=s}

setStatus('就绪  ·  Ctrl+Z 撤销  ·  Del 移除');
