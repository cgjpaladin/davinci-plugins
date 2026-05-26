const APP_VERSION='DEV';
const APP_BRANCH='';
const APP_BUILD_TIME='';
// 创壹特供版 v1.0 — 卡片版前端
// ═══ 立即执行 — 确认脚本加载 ═══
document.addEventListener('DOMContentLoaded',()=>{
  document.getElementById('debugMode').textContent='JS ✓';
  if(!window.pywebview || !window.pywebview.api) init();
});
// ═══ State ═══
window.onerror=function(m,s,l,c,e){const msg='JS错误: '+(m||'未知')+' @ '+(s||'?')+':'+l;toast(msg);call('debug_log',msg);return false};
window.addEventListener('unhandledrejection',e=>{const msg='Promise错误: '+e.reason;toast(msg);call('debug_log',msg)});
const _origErr=console.error;console.error=function(...a){_origErr.apply(console,a);call('debug_log','CONSOLE: '+a.join(' '))};

let files=[], _firstDrop=true, sel=new Set(), undoAvail=false, _thumbs={};
const DIGIT_RULES={ep:/^\d{0,3}$/,sc:/^\d{0,2}$/,ver:/^\d{0,2}$/};
const DIGIT_STRICT={ep:/^(0[1-9]|[1-9]\d{1,2})$/,sc:/^(0[1-9]|[1-9]\d)$/,ver:/^(0[1-9]|[1-9]\d)$/};
const C={g:'var(--green)',y:'var(--yellow)',r:'var(--red)',b:'var(--text-bright)',d:'var(--text-dim)',gr:'var(--filled-bg)'};
const tc=['#2a3a1a','#1a2a3a','#3a201a','#2a1a3a','#1a3a2a','#3a301a','#1a3a3a','#302a1a'];

// 必填字段（视频 desc 除外）
const _REQUIRED_KEYS=['ep','sc','shot','tk','type','author','ver','status'];
const _REQUIRED_PIC=[..._REQUIRED_KEYS,'desc'];
const _PLACEHOLDERS=['请选择'];

// ═══ API ═══
function call(m,...a){
  try{if(window.pywebview&&window.pywebview.api)return window.pywebview.api[m](...a);}
  catch(e){toast("API错误: "+m);return null}
  return mock(m,...a);
}
function mock(m,...a){
  return new Promise(r=>{
    const cfg_fields=[{key:'ep',label:'集数',def:'',hint:'01'},{key:'sc',label:'场次',def:'',hint:'01'},{key:'shot',label:'镜号',def:'',hint:'01'},{key:'desc',label:'镜头描述',def:'',hint:'仅图片'},{key:'type',label:'类型',def:''},{key:'author',label:'制作者',def:'',hint:'请输入姓名'},{key:'ver',label:'版本号',def:'01',hint:'01'},{key:'status',label:'状态',def:'',dv:['请选择','OK','KP','NG']}];
    const fmt=[{pfx:'EP',key:'ep'},{pfx:'SC',key:'sc'},{pfx:'SH',key:'shot'},{pfx:'TK',key:'tk'},{pfx:'',key:'desc'},{pfx:'',key:'type'},{pfx:'',key:'author'},{pfx:'V',key:'ver'},{pfx:'',key:'status'}];
    switch(m){
      case'get_config':r({fields:cfg_fields,defaults:{},name_format:fmt,dev:true});break;
      case'do_rename':r({ok:1,total:1,fail:[],renamed:[]});break;
      case'do_undo':r({ok:0,msg:'Mock: 无操作'});break;
      case'debug_log':r('ok');break;
      default:r({});
    }
  });
}

// ═══ Load ═══
async function init(){
  if(window._initialized)return;window._initialized=true;
  const dm=document.getElementById('debugMode');
  const isLive=_isLive();dm.textContent=isLive?'✔ Live':'✖ Mock';

  const cfg=await call('get_config');
  _nameFmt=cfg.name_format||[];
  const _allFields=cfg.fields||[];
  window._fieldKeys=_allFields.filter(f=>f.key!=='tk'&&f.key!=='type').map(f=>f.key);
  window._fieldKeysAll=_allFields.filter(f=>f.key!=='tk').map(f=>f.key);
  window._fieldLabels={};_allFields.forEach(f=>{window._fieldLabels[f.key]=f.label});
  const v=APP_VERSION||'?',br=APP_BRANCH||'',t=APP_BUILD_TIME||'';
  document.getElementById('debugMode').textContent=(cfg.dev?'🔧 DEV':'')+(br&&br!='main'?br+'@':'')+'v'+v+(t?' '+t:'');

  _buildInspector(cfg.fields);
  const d=cfg.defaults||{};
  for(const fd of cfg.fields){
    if(fd.key==='shot'||fd.key==='type')continue;
    if(d[fd.key]){const el=document.querySelector(`[data-key="${fd.key}"]`);if(el){if(el.tagName==='SELECT')el.value=d[fd.key];else{el.value=d[fd.key];_setVisual(el,d[fd.key])}}}
  }
  _bindInspectorListeners();

  setTimeout(() => {
    if(window.pywebview) return;
    const dz=document.getElementById('fileList');
    dz.addEventListener('dragover',e=>{e.preventDefault()});
    dz.addEventListener('drop',e=>{
      e.preventDefault();
      const items=[...e.dataTransfer.files].filter(f=>f.name.match(/\.(mp4|mov|mxf|avi|mkv|png|jpg|jpeg|bmp|tiff|tif)$/i));
      if(!items.length)return;
      const mockFiles=items.map(f=>({
        path:f.name,basename:f.name,ext:'.'+(f.name.split('.').pop()||'mp4'),
        fields:{ep:'',sc:'',shot:'',desc:'',type:f.name.match(/\.(png|jpg|jpeg|bmp|tiff|tif)$/i)?'AIPIC':'AIVID',author:'',ver:'01',status:''},
        _shots:[''],tags:[]
      }));
      files=files.concat(mockFiles.filter(mf=>!files.some(ef=>ef.path===mf.path)));
      renderList();updButtons();
      toast('已追加 '+mockFiles.length+' 个文件 (预览模式)');
    });
  }, 500);
  renderList();
}

let _ready=false;
function _tryStart(){
  if(_ready)return;
  const live=!!(window.pywebview&&window.pywebview.api);
  if(!live){document.getElementById('debugMode').textContent='⏳'+Math.floor(Date.now()/1000)%100;return}
  _ready=true;
  document.getElementById('debugMode').textContent='✔ Live';
  window.pywebview.api.echo('hello').then(r=>{
    document.getElementById('debugMode').textContent='✔ '+r.received;
    if(window._tryIv)clearInterval(window._tryIv);
    init();
  }).catch(()=>{init()});
}
window._tryIv=setInterval(_tryStart,300);

// ═══ 动态构建 Inspector ═══
function _buildInspector(fields){
  const ct=document.getElementById('inspector');ct.innerHTML='';
  fields.forEach(fd=>{
    const k=fd.key;
    if(k==='tk')return;
    if(k==='shot'){_buildShotInspector(ct,fd);return}
    const d=document.createElement('div');d.className='param'+(k==='desc'?' wide':'');
    const lb=document.createElement('label');lb.textContent=fd.label;d.appendChild(lb);
    if(k==='type'){
      const ip=document.createElement('input');ip.setAttribute('data-key','type');
      ip.readOnly=true;ip.style.cursor='default';ip.style.opacity='0.7';
      ip.value='';ip.placeholder='自动判定';
      d.appendChild(ip);
    }else if(fd.dv){
      const s=document.createElement('select');s.setAttribute('data-key',k);
      fd.dv.forEach(v=>{const o=document.createElement('option');o.value=v;o.textContent=v;s.appendChild(o)});
      d.appendChild(s);
    }else{
      const ip=document.createElement('input');ip.setAttribute('data-key',k);
      ip.placeholder=fd.hint||'';
      if(k==='desc'){ip.id='descInput';ip.readOnly=true;ip.style.opacity='0.7';ip.placeholder='视频无需描述'}
      d.appendChild(ip);
    }
    ct.appendChild(d);
  });
}

function _buildShotInspector(ct,fd){
  const d=document.createElement('div');d.className='param wide shot-param';
  const lb=document.createElement('label');lb.textContent='SH 镜号';d.appendChild(lb);
  const rows=document.createElement('div');rows.className='shot-rows';rows.id='shotRows';
  const initRow=_makeShotRow('');rows.appendChild(initRow);
  _updateShotButtons(rows);
  d.appendChild(rows);ct.appendChild(d);
}

function _makeShotRow(val){
  const r=document.createElement('div');r.className='shot-row';
  const ip=document.createElement('input');ip.setAttribute('data-key','shot');
  ip.value=val||'';ip.placeholder='01';
  ip.style.width='100%';
  const btn=document.createElement('button');btn.className='shot-act shot-add-btn';btn.textContent='+';
  r.appendChild(ip);r.appendChild(btn);
  return r;
}

function _updateShotButtons(ct){
  const rows=ct.querySelectorAll('.shot-row');
  rows.forEach((r,i)=>{
    const btn=r.querySelector('button');
    if(i===rows.length-1){btn.textContent='+';btn.className='shot-act shot-add-btn';btn.onclick=()=>_addShotRow(ct)}
    else{btn.textContent='−';btn.className='shot-act shot-del-btn';btn.onclick=()=>_delShotRow(ct,i)}
  });
}

function _addShotRow(ct){
  const r=_makeShotRow('');
  ct.appendChild(r);
  _updateShotButtons(ct);
  r.querySelector('input').focus();
  if(sel.size>0){_applyInspectorToSelected();renderList();updButtons()}
}

function _delShotRow(ct,i){
  const rows=ct.querySelectorAll('.shot-row');
  if(rows.length<=1)return;
  rows[i].remove();
  _updateShotButtons(ct);
  if(sel.size>0){_applyInspectorToSelected();renderList();updButtons()}
}

function _bindInspectorListeners(){
  document.querySelectorAll('#inspector input[data-key]').forEach(el=>{
    const k=el.getAttribute('data-key');
    if(k==='type'||k==='shot')return;
    if(el.readOnly)return;
    el.addEventListener('focus',()=>{if(!sel.size)return;el.style.color=C.b;const v=el.value.trim();el.style.background=v&&v!=='请选择'?C.gr:'var(--surface2)'});
    el.addEventListener('blur',()=>{if(!sel.size)return;_setVisual(el,el.value.trim());
      const sr=DIGIT_STRICT[k];
      if(sr&&el.value&&!sr.test(el.value)){toast(`请输入${el.placeholder||'正确格式'}`);el.focus()}
    });
    const rx=DIGIT_RULES[k];
    if(rx){el.addEventListener('input',e=>{if(!sel.size)return;let v=el.value.replace(/[^\d.]/g,'');while(v&&!rx.test(v))v=v.slice(0,-1);if(v!==el.value){el.value=v;e.stopImmediatePropagation();return}},true)}
    el.addEventListener('input',()=>{if(!sel.size)return;_applyInspectorToSelected();renderList();updButtons()});
  });
  // desc 清洗：只保留中英文数字
  const di=document.getElementById('descInput');
  if(di)di.addEventListener('input',()=>{
    let v=di.value.replace(/[^\u4e00-\u9fff\u3400-\u4dbfa-zA-Z0-9]/g,'');
    if(v!==di.value){di.value=v;_applyInspectorToSelected();renderList();updButtons()}
  });
  // shot 输入事件
  document.querySelectorAll('#shotRows input[data-key="shot"]').forEach(el=>{
    el.addEventListener('input',()=>{if(!sel.size)return;_applyInspectorToSelected();renderList();updButtons()});
    el.addEventListener('blur',()=>{
      let v=el.value.replace(/[^\d]/g,'');if(v.length>2)v=v.slice(0,2);
      if(v!==el.value){el.value=v}
      _setVisual(el,v);
    });
  });
  // 下拉框
  document.querySelectorAll('#inspector select[data-key]').forEach(el=>{
    el.addEventListener('change',()=>{if(!sel.size)return;_setVisual(el,el.value);_applyInspectorToSelected();renderList();updButtons()});
  });
  // 制作者中文限制
  const ab=document.querySelector('[data-key="author"]');
  if(ab)ab.addEventListener('input',()=>{const o=ab.value;const c=o.replace(/[^\u4e00-\u9fff\u3400-\u4dbf]/g,'');if(c!==o){ab.value=c;toast('请输入完整中文姓名');_applyInspectorToSelected();renderList();updButtons()}});
}

// ═══ Fields ═══
function _getShotValues(){
  const rows=document.querySelectorAll('#shotRows input[data-key="shot"]');
  return [...rows].map(r=>r.value.replace(/[^\d]/g,'').slice(0,2)).filter(v=>v);
}

function getFields(){
  const f={shot:''};
  const sh=_getShotValues();
  f.shot=sh.length?sh.join('/'):'';
  for(const el of document.querySelectorAll('#inspector [data-key]')){
    const k=el.getAttribute('data-key');
    if(k==='shot')continue;
    if(k==='type'){f[k]=el.value||'';continue}
    let v=el.value.trim();
    if(_PLACEHOLDERS.includes(v))v='';
    f[k]=v||'';
  }
  return f;
}

// ═══ TK ═══
function buildTK(i){
  const fs=files[i].fields;
  const k=fs.ep+'|'+fs.sc+'|'+(fs.shot||'')+'|'+fs.ver;
  let n=0;
  for(let j=0;j<=i;j++){
    const g=files[j].fields;
    const jk=g.ep+'|'+g.sc+'|'+(g.shot||'')+'|'+g.ver;
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

// ═══ File List ═══
function renderList(){
  const seen=new Set(); files=files.filter(f=>{const k=f.fp||f.path;if(seen.has(k))return false;seen.add(k);return true});
  const ct=document.getElementById('fileList');ct.innerHTML='';
  if(files.length===0){ct.innerHTML='<div class="fl-empty">拖放文件到此处 或 点击 +文件</div>';document.getElementById('fileCount').innerHTML='文件列表 · 0 个';updButtons();return}
  files.forEach((f,i)=>{
    if(!f._shots)f._shots=(f.fields.shot||'').split('/').filter(v=>v);
    if(!f._shots.length)f._shots=[''];
    const d=document.createElement('div');d.className='fl-item';d.setAttribute('data-path',f.path);
    if(sel.has(i))d.classList.add('sel');
    let ff={...f.fields,tk:_computeTK(i)},nm=buildName(ff);
    const req=f.fields.type==='AIPIC'?_REQUIRED_PIC:_REQUIRED_KEYS;
    const ready=req.every(k=>ff[k]&&!_PLACEHOLDERS.includes(ff[k]));
    d.classList.add(ready?'rdy':'mis');
    if(f.archived) d.classList.add('archived');
    const tt=f.tags;if(tt&&tt.length){if(tt.includes('zero'))d.classList.add('warn-zero');if(tt.includes('size'))d.classList.add('warn-size');if(tt.includes('dbl_ext'))d.classList.add('warn-dbl')}
    const th=document.createElement('div');th.className='fl-thumb';
    const tsrc=_thumbs[f.path];
    if(tsrc){th.style.backgroundImage=`url(${tsrc})`;th.style.backgroundSize='contain';th.style.backgroundRepeat='no-repeat';th.style.backgroundPosition='center'}
    else{th.style.background=`linear-gradient(135deg,${tc[i%tc.length]},${tc[(i+2)%tc.length]})`}
    const nn=document.createElement('span');nn.className='fl-new';nn.textContent=nm+f.ext;
    const ar=document.createElement('span');ar.className='fl-arrow-sym';ar.textContent='←';
    const on=document.createElement('span');on.className='fl-old';on.textContent=f.basename;
    const dot=document.createElement('span');dot.className='fl-dot';
    const tags=f.tags||[];
    dot.style.background=tags.length?'var(--red)':(ready?'var(--green)':'var(--yellow)');
    const tag=document.createElement('span');tag.className='fl-tag';
    if(tags.length){const lbl={zero:'零字节',size:'大小异常',dbl_ext:'双扩展名'};tag.textContent=tags.map(t=>lbl[t]||t).join(' · ');tag.style.color='var(--red)'}
    else if(!ready){
      const m=[];const _lbs=window._fieldLabels||{};
      for(const k of req){if(!ff[k]||_PLACEHOLDERS.includes(ff[k]))m.push(_lbs[k]||k)}
      tag.textContent='请填写: '+m.join(' · ');
    }else{tag.textContent='✓'}
    d.append(th,nn,ar,on,dot,tag);
    d.addEventListener('click',e=>{
      if(e.metaKey||e.ctrlKey){if(sel.has(i))sel.delete(i);else sel.add(i)}
      else if(e.shiftKey&&sel.size>0){const s=[...sel].sort((a,b)=>a-b);const[l,h]=[Math.min(s[0],i),Math.max(s[0],i)];for(let j=l;j<=h;j++)sel.add(j)}
      else if(sel.size===1&&sel.has(i))return;
      else{sel.clear();sel.add(i)}
      renderList();updButtons();_syncInspectorFromSelection();
    });
    ct.appendChild(d);
  });
  updCount();updButtons();
}
function updCount(){
  let ok2=0;files.forEach(f=>{const ff=f.fields;const req=ff.type==='AIPIC'?_REQUIRED_PIC:_REQUIRED_KEYS;if(req.every(k=>ff[k]&&!_PLACEHOLDERS.includes(ff[k])))ok2++});
  document.getElementById('fileCount').innerHTML=`文件列表 · <span style="color:var(--green)">${ok2}</span>/${files.length} 就绪  ·  选中 ${sel.size}`;
}

function _setVisual(el,v){
  const filled=v&&!_PLACEHOLDERS.includes(v);
  el.style.color=filled?'var(--text-bright)':'var(--text-dim)';
  if(filled)el.style.background='var(--filled-bg)';
  else el.style.background='var(--surface2)';
}
function _lockInspector(lock){
  document.querySelectorAll('#inspector input:not([data-key="type"]):not([data-key="shot"]), #inspector select').forEach(el=>{
    if(el.tagName==='SELECT')el.disabled=lock;
    else el.readOnly=lock;
  });
}
function updButtons(){
  const hf=files.length>0,hs=sel.size>0;
  let af=true;
  if(hs){for(const i of sel){const ff=files[i].fields;const req=ff.type==='AIPIC'?_REQUIRED_PIC:_REQUIRED_KEYS;if(!req.every(k=>ff[k]&&!_PLACEHOLDERS.includes(ff[k]))){af=false;break}}}
  document.getElementById('btnRename').disabled=!(hs&&af);
  document.getElementById('btnUndo').disabled=!undoAvail;
  const dot=document.querySelector('.sb-dot');
  if(!hf){dot.style.background='var(--green)';setStatus('就绪  ·  Ctrl+Z 撤销  ·  Del 移除');return}
  if(hs&&af){dot.style.background='var(--green)';setStatus('字段齐全，可以重命名');return}
  const missing=[];
  const fd=getFields();const _lbs=window._fieldLabels||{};
  for(const k of _REQUIRED_KEYS){if(!fd[k]||_PLACEHOLDERS.includes(fd[k]))missing.push(_lbs[k]||k)}
  let warn=[];
  for(const t of files){if(t.tags&&t.tags.length)warn.push(...t.tags)}
  if(warn.length){const wl={zero:'零字节',size:'大小异常',dbl_ext:'双扩展名'};dot.style.background='var(--red)';setStatus('⚠ '+[...new Set(warn)].map(w=>wl[w]||w).join(' · '));return}
  dot.style.background='var(--yellow)';
  let ok=0;files.forEach(f=>{const ff=f.fields;const req=ff.type==='AIPIC'?_REQUIRED_PIC:_REQUIRED_KEYS;if(req.every(k=>ff[k]&&!_PLACEHOLDERS.includes(ff[k])))ok++});
  setStatus((missing.length?('缺失: '+missing.join(' · ')):'')+'  ·  '+ok+'/'+files.length+' 就绪');
  _lockInspector(true);_lockInspector(false);
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
async function addFiles(){const r=await call('add_files_via_dialog');if(r&&r.files){const ex=new Set(files.map(f=>f.path));const fr=r.files.filter(f=>!ex.has(f.path));files=files.concat(fr);r.total=fr.length;r.duplicates=r.files.length-fr.length;renderList();_toastResult(r);loadThumbs()}}
async function addFolder(){const r=await call('add_folder_via_dialog');if(r&&r.files){const ex=new Set(files.map(f=>f.path));const fr=r.files.filter(f=>!ex.has(f.path));files=files.concat(fr);r.total=fr.length;r.duplicates=r.files.length-fr.length;renderList();_toastResult(r);loadThumbs()}}
function _toastResult(r){let m=`已追加 ${r.total} 个文件`;if(r.duplicates)m+=` · ${r.duplicates} 个重复跳过`;if(r.subdirs_skipped)m+=` · ${r.subdirs_skipped} 个子文件夹跳过`;if(r.truncated)m+=` (上限${r.max}个)`;toast(m)}

// 选中文件 → inspector 反射
function _syncInspectorFromSelection(){
  const ix=[...sel].sort((a,b)=>a-b);
  if(ix.length===0)return;
  if(ix.length===1){
    const f=files[ix[0]];
    for(const k of Object.keys(f.fields)){
      if(k==='shot')continue;
      if(k==='type'){const el=document.querySelector('[data-key="type"]');if(el){el.value=f.fields.type||'';_setVisual(el,f.fields.type||'')}continue}
      const el=document.querySelector(`[data-key="${k}"]`);
      if(!el)continue;
      const v=f.fields[k]||'';
      if(el.tagName==='SELECT'){el.value=v;_setVisual(el,v)}
      else{el.value=v;_setVisual(el,v)}
    }
    // 反射 SH
    _syncShotsFromFile(f);
    // 反射 desc 状态
    _syncDescState(f);
  }else{
    const ks=(window._fieldKeys||['ep','sc','author','ver','status']);
    for(const k of ks){
      const vals=new Set(ix.map(i=>files[i].fields[k]||''));
      const el=document.querySelector(`[data-key="${k}"]`);
      if(!el||k==='type')continue;
      const first=ix.sort((a,b)=>a-b)[0];
      const v=files[first].fields[k]||'';
      if(el.tagName==='SELECT'){el.value=v}else{el.value=v}
      _setVisual(el,v);
      const bdg=el.nextElementSibling;if(bdg&&bdg.className==='mix-badge')bdg.remove();
      if(vals.size>1){const b=document.createElement('span');b.className='mix-badge';b.textContent='['+vals.size+'种]';b.style.cssText='margin-left:6px;color:var(--text-dim);font-size:11px';el.after(b)}
    }
    // 类型混合态
    const tv=new Set(ix.map(i=>files[i].fields.type||''));
    const tel=document.querySelector('[data-key="type"]');
    if(tel){tel.value=tv.size===1?[...tv][0]:'';_setVisual(tel,'')}
    // SH 用第一个文件
    _syncShotsFromFile(files[ix.sort((a,b)=>a-b)[0]]);
  }
}
function _syncShotsFromFile(f){
  const ct=document.getElementById('shotRows');
  if(!ct)return;
  const shots=(f.fields.shot||'').split('/').filter(v=>v);
  if(!shots.length)shots.push('');
  ct.innerHTML='';
  shots.forEach(v=>ct.appendChild(_makeShotRow(v)));
  _updateShotButtons(ct);
}

function _syncDescState(f){
  const di=document.getElementById('descInput');
  if(!di)return;
  if(f.fields.type==='AIVID'){di.value='';di.readOnly=true;di.style.opacity='0.7';di.style.cursor='default';di.placeholder='视频无需描述';_setVisual(di,'')}
  else{di.readOnly=false;di.style.opacity='1';di.style.cursor='';di.placeholder='请输入镜头描述'}
}

// inspector 修改 → 写入选中文件
function _applyInspectorToSelected(){
  if(sel.size===0)return;
  const fd=getFields();
  for(const i of sel){
    for(const k of Object.keys(fd)){
      if(k==='tk')continue;
      files[i].fields[k]=fd[k];
    }
    // 同步 _shots
    const sh=_getShotValues();
    files[i]._shots=sh.length?sh:[''];
    files[i].fields.shot=sh.join('/');
  }
}

async function doRename(){
  if(sel.size===0)return;
  const srt=[...sel].sort((a,b)=>a-b);
  const sfs=srt.map((i,p)=>{const f={...files[i]};f.fields={...f.fields,tk:buildTK(i)};return f});
  const nm=buildName(sfs[0].fields)+sfs[0].ext;
  const msg=sfs.length===1?`确认重命名?\n${sfs[0].basename}\n→ ${nm}`:`确认重命名 ${sfs.length} 个?\n${buildName(sfs[0].fields)+sfs[0].ext}\n  ...\n${buildName(sfs[sfs.length-1].fields)+sfs[sfs.length-1].ext}`;
  if(!await showDialog('确认重命名',msg))return;
  call('debug_log','rename: starting '+sfs.length+' files');
  const r=await call('do_rename',sfs);
  if(r.ok>0){undoAvail=true;
    r.renamed.forEach(rn=>{const f=files.find(x=>x.path===rn.old_path);if(f)f.path=rn.new_path});
    r.renamed.forEach(rn=>{if(_thumbs[rn.old_path]){_thumbs[rn.new_path]=_thumbs[rn.old_path];delete _thumbs[rn.old_path]}});
    toast(`完成 ${r.ok}/${r.total}`); result(`✅ 重命名完成 ${r.ok}/${r.total}`)}
  if(r.fail&&r.fail.length){result(`✅ 重命名完成 ${r.ok}/${r.total}  ·  ⚠️ ${r.fail.join('; ')}`)}
  renderList();updButtons();
}

async function doUndo(){
  const r=await call('do_undo');
  toast(r.msg);result(r.msg);undoAvail=(r.remaining||0)>0;
  if(r.renamed){
    r.renamed.forEach(rn=>{const f=files.find(x=>x.path===rn.old_path);if(f)f.path=rn.new_path;
      if(_thumbs[rn.old_path]){_thumbs[rn.new_path]=_thumbs[rn.old_path];delete _thumbs[rn.old_path]}});
  }
  renderList();updButtons();
}

function removeSelected(){if(sel.size===0)return;files=files.filter((_,i)=>!sel.has(i));sel.clear();renderList();toast('已移除')}

// ═══ Thumbnails ═══
async function loadThumbs(){
  const paths=files.map(f=>f.path);
  call('debug_log','loadThumbs: '+paths.length+' files');
  await call('generate_thumbnails',paths);
}

function setThumb(path,thumb){
  _thumbs[path]=thumb;
  const el=document.querySelector(`[data-path="${CSS.escape(path)}"]`);
  if(el){const td=el.querySelector('.fl-thumb');if(td){
    const img=new Image();
    img.onload=()=>{const r=img.naturalWidth/img.naturalHeight;const H=36*_thumbScale();td.style.width=(H*r)+'px';td.style.height=H+'px';td.style.backgroundImage='url('+thumb+')';td.style.backgroundSize='cover';td.style.backgroundPosition='center'};
    img.src=thumb;
  }}
}
function _thumbScale(){const v=getComputedStyle(document.querySelector('.file-section')).getPropertyValue('--thumb-scale');return parseFloat(v)||1}
function setStatus(s){document.getElementById('statusText').textContent=s}

// ═══ Drag & Drop ═══
function _isLive(){return!!(window.pywebview&&window.pywebview.api)}
let dg=0;
const dropZone=document.getElementById('fileList');
const overlay=document.getElementById('dropOverlay');
dropZone.addEventListener('dragover',e=>{e.preventDefault();if(e.dataTransfer)e.dataTransfer.dropEffect='copy'});
dropZone.addEventListener('dragenter',e=>{e.preventDefault();dg++;overlay.classList.add('show')});
dropZone.addEventListener('dragleave',e=>{e.preventDefault();dg--;if(dg<=0){dg=0;overlay.classList.remove('show')}});
dropZone.addEventListener('drop',e=>{e.preventDefault();dg=0;overlay.classList.remove('show')});

let _dropCount=0;
function onDropResult(result){
  if(result&&result.files){
    _dropCount++;
    if(_firstDrop){_firstDrop=false;call('debug_log','_firstDrop: clearing');files=[];sel.clear()}
    const exist=new Set(files.map(f=>f.fp||f.path));
    const fresh=result.files.filter(f=>!(exist.has(f.fp||f.path)));
    const dup=result.duplicates||(result.files.length-fresh.length);
    if(fresh.length===0){toast(`全部重复 · ${dup} 个已跳过`);return}
    // 初始化 _shots
    fresh.forEach(f=>{if(!f._shots){f._shots=(f.fields.shot||'').split('/').filter(v=>v);if(!f._shots.length)f._shots=['']}});
    files=files.concat(fresh);call("debug_log",`FILES list: ${files.length} total`);
    let msg=`已追加 ${fresh.length} 个文件`;
    if(dup) msg+=` · ${dup} 个重复跳过`;
    if(result.subdirs_skipped) msg+=` · ${result.subdirs_skipped} 个子文件夹跳过`;
    if(result.truncated) msg+=` (上限${result.max}个)`;
    renderList();toast(msg);loadThumbs();
  }
}

// ═══ Keyboard ═══
document.addEventListener('keydown',e=>{
  if((e.ctrlKey||e.metaKey)&&e.key==='z'){e.preventDefault();doUndo()}
  if((e.key==='Delete'||e.key==='Backspace')&&e.target.tagName!=='INPUT'&&e.target.tagName!=='SELECT'){e.preventDefault();removeSelected()}
  if(e.key==='Enter'&&e.target.closest('#inspector')&&sel.size){
    e.preventDefault();
    const all=[...document.querySelectorAll('#inspector input:not([readonly]):not([data-key="type"]):not([data-key="shot"]), #inspector select')];
    const idx=all.indexOf(e.target);
    if(idx>=0&&idx+1<all.length){all[idx+1].focus();if(typeof all[idx+1].select==='function')all[idx+1].select()}
    else{sel.clear();renderList();updButtons();e.target.blur()}
  }
  if((e.key==='ArrowLeft'||e.key==='ArrowRight')&&sel.size){
    if(e.target.tagName==='INPUT'||e.target.tagName==='SELECT'){
      if(e.target.tagName==='INPUT'){const cs=e.target.selectionStart,len=e.target.value.length;if(e.key==='ArrowLeft'&&cs===0){e.preventDefault();_moveField(e.target,-1)}else if(e.key==='ArrowRight'&&cs===len){e.preventDefault();_moveField(e.target,1)}}
      else if(e.target.tagName==='SELECT'){e.preventDefault();_moveField(e.target,e.key==='ArrowRight'?1:-1)}
    }else{e.preventDefault();const all=[...document.querySelectorAll('#inspector input:not([readonly]):not([data-key="type"]):not([data-key="shot"]), #inspector select')];if(all.length)all[0].focus()}
  }
  if((e.key==='ArrowUp'||e.key==='ArrowDown')&&sel.size===1&&files.length>0){
    if(e.target.tagName!=='INPUT'||(e.key==='ArrowUp'&&e.target.selectionStart===0)||(e.key==='ArrowDown'&&e.target.selectionStart===e.target.value.length)){
      e.preventDefault();const cur=[...sel][0];const next=cur+(e.key==='ArrowDown'?1:-1);
      if(next>=0&&next<files.length){sel.clear();sel.add(next);renderList();_syncInspectorFromSelection();updButtons()}
    }
  }
  if((e.key==='Home'||e.key==='End')&&sel.size===1&&files.length>0){
    if(e.target.tagName!=='INPUT'||e.target.selectionStart===0){e.preventDefault();const i=e.key==='Home'?0:files.length-1;sel.clear();sel.add(i);renderList();_syncInspectorFromSelection();updButtons()}
  }
  if((e.metaKey||e.ctrlKey)&&e.key==='a'){
    if(e.target.tagName==='INPUT'||e.target.tagName==='TEXTAREA')return;
    e.preventDefault();sel=new Set([...Array(files.length).keys()]);renderList();_syncInspectorFromSelection();updButtons();
  }
});

function _moveField(el,delta){
  const all=[...document.querySelectorAll('#inspector input:not([readonly]):not([data-key="type"]):not([data-key="shot"]), #inspector select')];
  const idx=all.indexOf(el);const nxt=idx+delta;
  if(nxt>=0&&nxt<all.length){all[nxt].focus();if(typeof all[nxt].select==='function')all[nxt].select()}
}

// ═══ Buttons + Zoom ═══
document.getElementById('btnAdd').addEventListener('click',addFiles);
document.getElementById('btnRename').addEventListener('click',doRename);
document.getElementById('btnUndo').addEventListener('click',doUndo);

const zs=document.getElementById('zoomSlider'),zl=document.getElementById('zoomLabel');
zs.addEventListener('input',()=>{const v=parseInt(zs.value);zl.textContent=v+'%';document.querySelector('.file-section').style.setProperty('--thumb-scale',v/100)});
document.getElementById('fileList').addEventListener('wheel',e=>{
  if(e.metaKey||e.ctrlKey){e.preventDefault();zs.value=Math.max(50,Math.min(200,parseInt(zs.value)+(e.deltaY<0?10:-10)));zs.dispatchEvent(new Event('input'))}
});

// ═══ Toast ═══
let tt;function toast(m){call('debug_log','TOAST: '+m);const el=document.getElementById('toast');el.textContent=m;el.classList.add('show');clearTimeout(tt);tt=setTimeout(()=>el.classList.remove('show'),2500)}
function result(m){call('debug_log','result: '+m);document.getElementById('resultMsg').textContent=m}

setStatus('就绪  ·  Ctrl+Z 撤销  ·  Del 移除');
