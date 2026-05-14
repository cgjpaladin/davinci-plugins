const APP_VERSION='DEV';
const APP_BRANCH='';
const APP_BUILD_TIME='';
// ═══ 立即执行 — 确认脚本加载 ═══
document.addEventListener('DOMContentLoaded',()=>{
  document.getElementById('debugMode').textContent='JS ✓';
});
// ═══ State ═══

// 全局错误 → toast（不沉默）
window.onerror=function(m,s,l,c,e){const msg='JS错误: '+(m||'未知')+' @ '+(s||'?')+':'+l;toast(msg);call('debug_log',msg);return false};
window.addEventListener('unhandledrejection',e=>{const msg='Promise错误: '+e.reason;toast(msg);call('debug_log',msg)});
const _origErr=console.error;console.error=function(...a){_origErr.apply(console,a);call('debug_log','CONSOLE: '+a.join(' '))};

let files=[], sel=new Set(), methodDescMap={}, descLocked=false, undoAvail=false, _thumbs={};
const DIGIT_RULES={ep:/^\d{0,3}$/,sc:/^\d{0,2}$/,gr:/^\d{0,2}$/,ver:/^\d{0,2}(\.\d)?$/};
const C={g:'var(--green)',y:'var(--yellow)',r:'var(--red)',b:'var(--text-bright)',d:'var(--text-dim)',gr:'var(--filled-bg)'};
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
      case'get_config':r({fields:[{key:'ep',label:'Ep 集数',def:'01',hint:'01'},{key:'sc',label:'Sc 场次',def:'01',hint:'01'},{key:'gr',label:'Gr 小场次',def:'01',hint:'01'},{key:'desc',label:'镜头描述',def:'',hint:'由制作方式决定'},{key:'author',label:'制作者',def:'',hint:'请输入姓名'},{key:'method',label:'制作方式',def:'',dv:['请选择','智能分镜版','双轨版','角色专属版']},{key:'ver',label:'版本号',def:'01',hint:'01'},{key:'status',label:'通过情况',def:'',dv:['请选择','OK','KP','NG']}],defaults:{},method_desc_map:{'智能分镜版':{mode:'locked',value:'全能分镜'},'双轨版':{mode:'dropdown',values:['请选择','幽灵角色','空镜','手动输入…']},'角色专属版':{mode:'text',hint:'温时雨过肩中景'}},name_format:[{pfx:'Ep',key:'ep'},{pfx:'Sc',key:'sc'},{pfx:'Gr',key:'gr'},{pfx:'Tk',key:'tk'},{pfx:'',key:'desc'},{pfx:'',key:'author'},{pfx:'',key:'method'},{pfx:'v',key:'ver'},{pfx:'',key:'status'}],field_rules:[{trigger:'method',targets:['desc'],map:{'智能分镜版':{desc:{locked:'全能分镜'}},'双轨版':{desc:{dropdown:['请选择','幽灵角色','空镜','手动输入…']}},'角色专属版':{desc:{text_hint:'温时雨过肩中景'}}}}]});break;
            case'validate_dest':r({ok:true,msg:'✓ 格式正确'});break;
      case'do_rename':r({ok:1,total:1,fail:[],renamed:[]});break;
      case'do_undo':r({ok:0,msg:'Mock: 无操作'});break;
      case'do_archive':r({ok:0,fail:['Mock mode'],total:1});break;
      case'debug_log':r('ok');break;
      default:r({});
    }
  });
}

// ═══ 浏览器预览：拖入真文件 ═══
if(!window.pywebview){
  const dz=document.getElementById('fileList');
  dz.addEventListener('dragover',e=>{e.preventDefault()});
  dz.addEventListener('drop',e=>{
    e.preventDefault();
    const items=[...e.dataTransfer.files].filter(f=>f.type.startsWith('video/')||f.name.match(/\.(mp4|mov|mxf|avi|mkv)$/i));
    if(!items.length)return;
    const mockFiles=items.map((f,i)=>({
      path:f.name, basename:f.name, ext:'.'+(f.name.split('.').pop()||'mp4'),
      fields:{ep:'',sc:'',gr:'',desc:'',author:'',method:'',ver:'',status:''},
      tags:/(\.[^.]+)\1$/i.test(f.name)?['dbl_ext']:[]
    }));
    files=files.concat(mockFiles.filter(mf=>!files.some(ef=>ef.path===mf.path)));
    renderList();updButtons();
    toast(`已追加 ${mockFiles.length} 个文件 (预览模式)`);
  });
}

// ═══ Load ═══
async function init(){
  const dm = document.getElementById('debugMode');
  dm.textContent = _isLive() ? '✔ Live' : '✖ Mock';

  const cfg=await call('get_config');
  methodDescMap=cfg.method_desc_map||{};_nameFmt=cfg.name_format||[];
  const v=APP_VERSION||'?',br=APP_BRANCH||'',t=APP_BUILD_TIME||'';document.getElementById('debugMode').textContent=(cfg.dev?'🔧 DEV ':'')+(br&&br!='main'?br+'@':'')+'v'+v+(t?' '+t:'');

  // 动态构建 inspector
  _buildInspector(cfg.fields);
  // 应用保存的默认值
  const d=cfg.defaults||{};
  for(const fd of cfg.fields){
    if(d[fd.key]){const el=document.querySelector(`[data-key="${fd.key}"]`);if(el){if(el.tagName==='SELECT')el.value=d[fd.key];else{el.value=d[fd.key];el.style.color='var(--text-bright)'}}}
  }
  document.getElementById('methodSelect').value=d.method||'';
  onMethodChange();
  // 绑定事件（在元素创建后）
  _bindInspectorListeners();
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

// ═══ 动态构建 Inspector ═══
function _buildInspector(fields){
  const ct=document.getElementById('inspector');ct.innerHTML='';
  fields.forEach(fd=>{
    const d=document.createElement('div');d.className='param'+(fd.key==='desc'?' wide':'');
    const lb=document.createElement('label');lb.textContent=fd.label;d.appendChild(lb);
    if(fd.dv){
      const s=document.createElement('select');s.setAttribute('data-key',fd.key);s.style.color='var(--text-dim)';
      if(fd.key==='method')s.id='methodSelect';
      fd.dv.forEach(v=>{const o=document.createElement('option');o.value=v;o.textContent=v;s.appendChild(o)});
      d.appendChild(s);
    }else{
      const ip=document.createElement('input');ip.setAttribute('data-key',fd.key);
      ip.placeholder=fd.hint||'';ip.value='';
      if(fd.key==='tk'){ip.value='自动排序';ip.readOnly=true}
      if(fd.key==='desc'){ip.id='descInput';ip.readOnly=true}
      if(fd.key==='author')ip.id='authorInput';
      d.appendChild(ip);
    }
    ct.appendChild(d);
  });
}

function _bindInspectorListeners(){
  // 输入框：数字验证 + 泛用 handler
  document.querySelectorAll('#inspector input[data-key]').forEach(el=>{
    if(el.readOnly)return;
    el.addEventListener('focus',()=>{if(!sel.size)return;el.style.color=C.b;el.style.background=''});
    el.addEventListener('blur',()=>{if(!sel.size)return;if(!el.value.trim()){el.style.color=C.d;el.style.background=''}else{el.style.background=C.gr}});
    const rx=DIGIT_RULES[el.getAttribute('data-key')];
    if(rx){
      el.addEventListener('input',e=>{if(!sel.size)return;let v=el.value.replace(/[^\d.]/g,'');const dp=v.indexOf('.');if(dp>=0)v=v.slice(0,dp+1)+v.slice(dp+1).replace(/\./g,'');while(v&&!rx.test(v))v=v.slice(0,-1);if(v!==el.value){el.value=v;e.stopImmediatePropagation();return}},true);
    }
    el.addEventListener('input',()=>{if(!sel.size)return;_applyInspectorToSelected();renderList();updButtons()});
  });
  // 下拉框
  document.querySelectorAll('#inspector select[data-key]').forEach(el=>{
    if(el.id==='descInput'||el.id==='methodSelect')return;
    el.addEventListener('change',()=>{if(!sel.size)return;el.style.color='var(--text-bright)';_applyInspectorToSelected();renderList();updButtons()});
  });
  // methodSelect
  document.getElementById('methodSelect').addEventListener('change',onMethodChange);
  // 制作者中文限制
  const ab=document.getElementById('authorInput');
  if(ab)ab.addEventListener('input',()=>{const o=ab.value;const c=o.replace(/[^\u4e00-\u9fff\u3400-\u4dbf]/g,'');if(c!==o){ab.value=c;toast('请输入完整中文姓名');_applyInspectorToSelected();renderList();updButtons()}});
}

// ═══ Fields ═══
function getFields(){
  const PLACEHOLDERS=['请选择','手动输入…'];
  const f={};
  for(const el of document.querySelectorAll('#inspector [data-key]')){
    if(el.id==='descInput'&&document.getElementById('descCustomInput'))continue;
    let v=el.value.trim();
    if(PLACEHOLDERS.includes(v))v='';
    // 手动输入模式下空值不返回（防止_applyInspector误清）
    if(el.getAttribute('data-key')==='desc'&&!v&&document.getElementById('descCustomInput'))continue;
    f[el.getAttribute('data-key')]=v||'';
  }
  if(sel.size>0){const s=[...sel].sort((a,b)=>a-b);f.tk=String(s[0]+1).padStart(2,'0')}else f.tk='';
  return f;
}

// ═══ Method → Desc ═══
let _prevMethod='';
function onMethodChange(){
  const m=document.getElementById('methodSelect').value;
  const cfg=methodDescMap[m]||{mode:'text',hint:'请先选择制作方式'};
  const methodChanged=m!==_prevMethod;
  _prevMethod=m;
  if(cfg.mode==='locked'){descInput('text',cfg.value,true);descLocked=true}
  else if(cfg.mode==='dropdown'){descSelect(cfg.values);descLocked=false}
  else{const ro=cfg.hint.includes('请先选择');descInput('text','',ro,cfg.hint);descLocked=false}
  // 跨方法时清 desc，但 locked 模式写入固定值
  if(methodChanged&&sel.size>0){
    const dv=cfg.mode==='locked'?cfg.value:'';
    for(const i of sel) files[i].fields.desc=dv;
    renderList();updButtons();
  }
}
// 获取选中文件的存储 desc（单文件返回该值，多文件不一致返回空，无选中返回空）
function descInput(t,v,ro,ph){
  const ci=document.getElementById('descCustomInput');if(ci)ci.remove();
  const el=document.getElementById('descInput');
  if(el&&el.tagName==='INPUT'){el.value=v||'';el.readOnly=ro||false;el.placeholder=ph||'由制作方式决定';el.style.color=(ro&&v)?'var(--text-bright)':(v?'var(--text-bright)':'var(--text-dim)');el.style.background=v?'var(--filled-bg)':'';if(!ro)el.oninput=()=>{if(!descLocked){_applyInspectorToSelected();renderList();updButtons()}};return}
  const ip=document.createElement('input');ip.id='descInput';ip.setAttribute('data-key','desc');
  ip.value=v||'';ip.readOnly=ro||false;ip.placeholder=ph||'由制作方式决定';
  ip.style.cssText=el?el.style.cssText:'';ip.style.color=(ro&&v)?'var(--text-bright)':(v?'var(--text-bright)':'var(--text-dim)');ip.style.background=v?'var(--filled-bg)':'';
  if(!ro)ip.oninput=()=>{if(!descLocked){_applyInspectorToSelected();renderList();updButtons()}};
  if(el)el.replaceWith(ip);
}
function descSelect(vs){
  const el=document.getElementById('descInput');
  const ci=document.getElementById('descCustomInput');if(ci)ci.remove();
  const s=document.createElement('select');s.id='descInput';s.setAttribute('data-key','desc');
  s.style.cssText=el?el.style.cssText:'';
  vs.forEach(v=>{const o=document.createElement('option');o.text=v;o.value=v;s.add(o)});
  s.onchange=function(){
    const ci2=document.getElementById('descCustomInput');
    if(s.value==='手动输入…'){
      if(!ci2){const ip=document.createElement('input');ip.id='descCustomInput';ip.setAttribute('data-key','desc');ip.placeholder='输入自定义描述';ip.style.cssText='margin-left:4px;flex:1;';ip.oninput=()=>{_applyInspectorToSelected();renderList();updButtons()};s.after(ip)}
    }else{if(ci2)ci2.remove();_applyInspectorToSelected();renderList();updButtons()}
  };
  if(el)el.replaceWith(s);
}
// ═══ File List ═══
function renderList(){
  const ct=document.getElementById('fileList');ct.innerHTML='';
  if(files.length===0){ct.innerHTML='<div class="fl-empty">拖放文件到此处 或 点击 +文件</div>';document.getElementById('fileCount').innerHTML='文件列表 · 0 个';updButtons();return}
  const srt=[...sel].sort((a,b)=>a-b);
  files.forEach((f,i)=>{
    const d=document.createElement('div');d.className='fl-item';
    if(sel.has(i))d.classList.add('sel');
    let ff={...f.fields,tk:_computeTK(i)},nm=buildName(ff);
    const ready=ff.ep&&ff.sc&&ff.gr&&ff.desc&&ff.author&&ff.method&&ff.ver&&ff.status;
    d.classList.add(ready?'rdy':'mis');
    // 自动检查标注
    const tt=f.tags;if(tt&&tt.length){if(tt.includes('zero'))d.classList.add('warn-zero');if(tt.includes('size'))d.classList.add('warn-size');if(tt.includes('dbl_ext'))d.classList.add('warn-dbl')}
    const th=document.createElement('div');th.className='fl-thumb';
    const tsrc=_thumbs[f.path];
    if(tsrc){th.style.backgroundImage=`url(${tsrc})`;th.style.backgroundSize='cover';th.style.backgroundPosition='center'}
    else{th.style.background=`linear-gradient(135deg,${tc[i%tc.length]},${tc[(i+2)%tc.length]})`}
    const nn=document.createElement('span');nn.className='fl-new';
    nn.textContent=nm+' '+f.ext;
    const ar=document.createElement('span');ar.className='fl-arrow-sym';ar.textContent='←';
    const on=document.createElement('span');on.className='fl-old';on.textContent=f.basename;
    const dot=document.createElement('span');dot.className='fl-dot';
    const tags=f.tags||[];
    dot.style.background=tags.length?'var(--red)':(ready?'var(--green)':'var(--yellow)');
    // 缺失字段 / 检查警告
    const tag=document.createElement('span');tag.className='fl-tag';
    if(tags.length){const lbl={zero:'零字节',size:'大小异常',dbl_ext:'双扩展名'};tag.textContent=tags.map(t=>lbl[t]||t).join(' · ');tag.style.color='var(--red)'}
    else if(!ready){
      const m=[];const lb={ep:'Ep集数',sc:'Sc场次',gr:'Gr小场次',desc:'镜头描述',author:'制作者',method:'制作方式',ver:'版本号',status:'通过情况'};
      for(const k of['ep','sc','gr','desc','author','method','ver','status']){if(!ff[k])m.push(lb[k])}
      tag.textContent='请填写: '+m.join(' · ');
    }else{tag.textContent='✓'}
    d.append(th,nn,ar,on,dot,tag);
    d.addEventListener('click',e=>{
      if(e.metaKey||e.ctrlKey){if(sel.has(i))sel.delete(i);else sel.add(i)}
      else if(e.shiftKey&&sel.size>0){const s=[...sel].sort((a,b)=>a-b);const[l,h]=[Math.min(s[0],i),Math.max(s[0],i)];for(let j=l;j<=h;j++)sel.add(j)}
      else if(sel.size===1&&sel.has(i))return;
      else{sel.clear();sel.add(i)}
      renderList();updButtons();
      _syncInspectorFromSelection();
    });
    ct.appendChild(d);
  });
  updCount();updButtons();
}
function updCount(){
  let ok2=0;files.forEach(f=>{const ff=f.fields;if(ff.ep&&ff.sc&&ff.gr&&ff.desc&&ff.author&&ff.method&&ff.ver&&ff.status)ok2++});document.getElementById('fileCount').innerHTML=`文件列表 · <span style="color:var(--green)">${ok2}</span>/${files.length} 就绪  ·  选中 ${sel.size}`;
}
function _lockInspector(lock){
  document.querySelectorAll('#inspector input:not([data-key="tk"]), #inspector select').forEach(el=>{
    if(el.id==='descInput'&&descLocked)return;
    if(el.tagName==='SELECT')el.disabled=lock;
    else el.readOnly=lock;
    el.style.cursor=lock?'default':'';
    // locked — keep visual state
  });
}
function updButtons(){
  const hf=files.length>0,hs=sel.size>0,fd=getFields();
  const af=fd.ep&&fd.sc&&fd.gr&&fd.author&&fd.method&&fd.ver&&fd.status&&fd.desc;
  document.getElementById('btnRename').disabled=!(hs&&af);
  document.getElementById('btnArchive').disabled=!(hs&&af);
  document.getElementById('btnUndo').disabled=!undoAvail;
  // 状态栏：列出缺失字段 + 点颜色
  const dot=document.querySelector('.sb-dot');
  if(!hf){dot.style.background='var(--green)';setStatus('就绪  ·  Ctrl+Z 撤销  ·  Del 移除');return}
  if(hs&&af){dot.style.background='var(--green)';setStatus('字段齐全，可以重命名');return}
  const missing=[];
  const labels={ep:'Ep集数',sc:'Sc场次',gr:'Gr小场次',desc:'镜头描述',author:'制作者',method:'制作方式',ver:'版本号',status:'通过情况'};
  for(const k of['ep','sc','gr','desc','author','method','ver','status']){if(!fd[k])missing.push(labels[k])}
  // 检查警告
  let warn=[];
  for(const t of files){if(t.tags&&t.tags.length)warn.push(...t.tags)}
  if(warn.length){const wl={zero:'零字节',size:'大小异常',dbl_ext:'双扩展名'};dot.style.background='var(--red)';setStatus('⚠ '+[...new Set(warn)].map(w=>wl[w]||w).join(' · '));return}
  dot.style.background='var(--yellow)';
  let t_ok=0;files.forEach(f=>{const ff=f.fields;if(ff.ep&&ff.sc&&ff.gr&&ff.desc&&ff.author&&ff.method&&ff.ver&&ff.status)t_ok++});
  _lockInspector(hs);setStatus(missing.length?('缺失: '+missing.join(' · ')+'  ·  '+t_ok+'/'+files.length+' 就绪'):('就绪  ·  Ctrl+Z 撤销  ·  '+t_ok+'/'+files.length+' 就绪'));
  _lockInspector(!hs);
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
// 选中文件时，把它们的字段反映到 inspector
function _syncInspectorFromSelection(){
  const ix=[...sel].sort((a,b)=>a-b);
  if(ix.length===0)return;
  if(ix.length===1){
    const f=files[ix[0]];
    for(const k of Object.keys(f.fields)){
      const el=document.querySelector(`[data-key="${k}"]`);
      if(!el||el.id==='descInput')continue;
      const v=f.fields[k]||'';
      if(el.tagName==='SELECT'){el.value=v;const filled=v&&v!=='请选择';el.style.color=filled?'var(--text-bright)':'var(--text-dim)';el.style.background=filled?'var(--filled-bg)':''}
      else{el.value=v;const filled=!!v;el.style.color=filled?'var(--text-bright)':'var(--text-dim)';el.style.background=filled?'var(--filled-bg)':''}
    }
    document.getElementById('methodSelect').value=f.fields.method||'';
    onMethodChange();
    _setDescValue(f.fields.desc||'');
  }else{
    const ks=['ep','sc','gr','author','ver','status'];
    for(const k of ks){
      const vals=new Set(ix.map(i=>files[i].fields[k]||''));
      const el=document.querySelector(`[data-key="${k}"]`);
      if(!el||el.id==='descInput')continue;
      const single=vals.size===1?[...vals][0]:'';
      if(el.tagName==='SELECT'){el.value=vals.size===1?[...vals][0]:'';const filled=single&&single!=='请选择';el.style.color=filled?'var(--text-bright)':'var(--text-dim)';el.style.background=filled?'var(--filled-bg)':''}
      else{el.value=single||'';const filled=!!single;el.style.color=filled?'var(--text-bright)':'var(--text-dim)';el.style.background=filled?'var(--filled-bg)':''}
    }
    const mv=new Set(ix.map(i=>files[i].fields.method||''));
    document.getElementById('methodSelect').value=mv.size===1?[...mv][0]:'';
    onMethodChange();
    const dv=new Set(ix.map(i=>files[i].fields.desc||''));
    _setDescValue(dv.size===1?[...dv][0]:'');
  }
  const tkEl=document.querySelector('[data-key="tk"]');
  if(tkEl){tkEl.value=sel.size?'自动排序':'';tkEl.style.color='var(--text-dim)'}
}
function _setDescValue(v){
  const ci=document.getElementById('descCustomInput');
  if(ci){ci.value=v||'';return}
  const el=document.getElementById('descInput');
  if(!el||!v)return;
  if(el.tagName==='SELECT'){
    for(let i=0;i<el.options.length;i++){if(el.options[i].value===v){el.value=v;return}}
    // 不在选项里 → 切到「手动输入…」并填值
    el.value='手动输入…';
    const ip=document.createElement('input');ip.id='descCustomInput';ip.setAttribute('data-key','desc');
    ip.value=v;ip.placeholder='输入自定义描述';ip.style.cssText='margin-left:4px;flex:1;';
    ip.oninput=()=>{_applyInspectorToSelected();renderList();updButtons()};
    el.after(ip);
  }else if(el.tagName==='INPUT'){
    el.value=v;el.style.color='var(--text-bright)';el.style.background='var(--filled-bg)';
  }
}

async function doRename(){
  if(sel.size===0)return;
  const srt=[...sel].sort((a,b)=>a-b);
  // 用每个文件自己的 fields，不是 inspector 全局值
  const sfs=srt.map((i,p)=>{
    const f={...files[i]};
    f.fields={...f.fields,tk:String(srt[0]+p+1).padStart(2,'0')};
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
    toast(`完成 ${r.ok}/${r.total}`)}
  if(r.fail&&r.fail.length){setTimeout(()=>toast('失败: '+r.fail.join('; ')),2000)}
  renderList();updButtons();
}
function _computeTK(i){
  const fs=files[i].fields;
  const k=fs.ep+'|'+fs.sc+'|'+fs.gr+'|'+fs.desc+'|'+(fs.method||'')+'|'+fs.ver;
  let n=0;
  for(let j=0;j<=i;j++){
    const g=files[j].fields;
    const jk=g.ep+'|'+g.sc+'|'+g.gr+'|'+g.desc+'|'+(g.method||'')+'|'+g.ver;
    if(jk===k)n++;
  }
  return String(n).padStart(2,'0');
}
let _nameFmt=[];
function buildName(f){
  const raw=_nameFmt.map(s=>s.pfx+(f[s.key]||'')).join('_');
  return raw.replace(/_+/g,'_').replace(/_$/,'');
}
async function doUndo(){const r=await call('do_undo');toast(r.msg);undoAvail=(r.remaining||0)>0;updButtons()}

function removeSelected(){if(sel.size===0)return;files=files.filter((_,i)=>!sel.has(i));sel.clear();renderList();toast('已移除')}
async function doArchive(){
  if(sel.size===0){toast('未选中文件');return}
  const dest=document.getElementById('destInput').value.trim();
  if(!dest){toast('请先输入目标路径');return}
  const srt=[...sel].sort((a,b)=>a-b);
  const sfs=srt.map((i,p)=>{const f={...files[i]};f.fields={...f.fields,tk:String(srt[0]+p+1).padStart(2,'0')};return f});
  if(!await showDialog('确认归档',`确认归档 ${sfs.length} 个文件到?\n${dest}/EP${sfs[0].fields.ep||'??'}/SC${sfs[0].fields.sc||'??'}/...`))return;
  call('debug_log','archive: starting');
  const r=await call('do_archive',sfs,dest);
  call('debug_log','archive: result='+JSON.stringify({ok:r.ok,total:r.total}));
  if(r.ok>0)toast(`归档完成 ${r.ok}/${r.total}`);
  if(r.fail&&r.fail.length){setTimeout(()=>toast('失败: '+r.fail.join('; ')),2000)}
}
// ═══ Thumbnails ═══
async function loadThumbs(){
  const paths=files.map(f=>f.path);
  call('debug_log','loadThumbs: '+paths.length+' files');
  const r=await call('generate_thumbnails',paths);
  call('debug_log','loadThumbs result: '+(r&&r.thumbs?Object.keys(r.thumbs).length:0)+' thumbs');
  if(r&&r.thumbs){_thumbs=r.thumbs;renderList()}
}

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
  if(result&&result.files){
    _dropCount++;
    call('debug_log',`onDropResult #${_dropCount}: ${result.files.length} files, existing=${files.length}`);
    const exist=new Set(files.map(f=>f.path));
    const fresh=result.files.filter(f=>!exist.has(f.path));
    const dup=result.files.length-fresh.length;
    files=files.concat(fresh);
    let msg=`已追加 ${fresh.length} 个文件`;
    if(dup) msg+=` · ${dup} 个重复跳过`;
    if(result.subdirs_skipped) msg+=` · ${result.subdirs_skipped} 个子文件夹跳过`;
    if(result.truncated) msg+=` (上限${result.max}个)`;
    renderList();toast(msg);
    loadThumbs();
  }
}

// ═══ Keyboard ═══
document.addEventListener('keydown',e=>{
  if((e.ctrlKey||e.metaKey)&&e.key==='z'){e.preventDefault();doUndo()}
  if((e.key==='Delete'||e.key==='Backspace')&&e.target.tagName!=='INPUT'&&e.target.tagName!=='SELECT'){e.preventDefault();removeSelected()}
  // Enter → 确认输入，取消选中回到列表
  // Enter → 跳到下一个字段，最后一个跳到列表
  if(e.key==='Enter'&&e.target.closest('#inspector')&&sel.size){
    e.preventDefault();
    const all=[...document.querySelectorAll('#inspector input:not([readonly]), #inspector select')];
    const idx=all.indexOf(e.target);
    if(idx>=0&&idx+1<all.length){all[idx+1].focus();all[idx+1].select()}
    else{sel.clear();renderList();updButtons();e.target.blur()}
  }
  // Cmd+A: input 里正常全选；其他位置 → 全选文件列表
  if((e.metaKey||e.ctrlKey)&&e.key==='a'){
    if(e.target.tagName==='INPUT'||e.target.tagName==='TEXTAREA')return;
    e.preventDefault();
    sel=new Set([...Array(files.length).keys()]);
    renderList();updButtons();
  }
});

// ═══ Inspector: 修改 → 写入选中文件的字段 ═══
function _applyInspectorToSelected(){
  if(sel.size===0)return;
  const fd=getFields();
  const changed=[];
  for(const i of sel){
    for(const k of Object.keys(fd)){
      if(k==='tk')continue;
      if(files[i].fields[k]!==fd[k]){changed.push(k);files[i].fields[k]=fd[k]}
    }
  }
  if(changed.length)call('debug_log','fields changed: '+[...new Set(changed)].join(',')+' on '+sel.size+' files');
}

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
document.getElementById('btnAdd').addEventListener('click',addFiles);
document.getElementById('btnRename').addEventListener('click',doRename);
document.getElementById('btnArchive').addEventListener('click',doArchive);
document.getElementById('btnUndo').addEventListener('click',doUndo);

// 缩放滑块
const zs=document.getElementById('zoomSlider'),zl=document.getElementById('zoomLabel');
zs.addEventListener('input',()=>{
  const v=parseInt(zs.value);
  zl.textContent=v+'%';
  document.querySelector('.file-section').style.setProperty('--thumb-scale',v/100);
});
// Cmd+滚轮 也支持缩放
document.getElementById('fileList').addEventListener('wheel',e=>{
  if(e.metaKey||e.ctrlKey){
    e.preventDefault();
    zs.value=Math.max(50,Math.min(200,parseInt(zs.value)+(e.deltaY<0?10:-10)));
    zs.dispatchEvent(new Event('input'));
  }
});

// ═══ Toast ═══
let tt;function toast(m){const el=document.getElementById('toast');el.textContent=m;el.classList.add('show');clearTimeout(tt);tt=setTimeout(()=>el.classList.remove('show'),2500)}

setStatus('就绪  ·  Ctrl+Z 撤销  ·  Del 移除');