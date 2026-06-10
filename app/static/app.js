const $ = s => document.querySelector(s);
const esc = v => String(v ?? "").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const api = async (path, options={}) => {
  const timeout=options.timeout||0,controller=timeout?new AbortController():null;
  const timer=controller?setTimeout(()=>controller.abort(),timeout):null;
  try{
    const response = await fetch(path,{headers:{"Content-Type":"application/json"},...options,signal:controller?.signal||options.signal});
    const data = await response.json();
    if(!response.ok) throw new Error(data.error || "请求失败");
    return data;
  }catch(error){
    if(error.name==="AbortError")throw new Error("请求超时，请检查 eSTK、AT 端口或 lpac 状态");
    throw error;
  }finally{if(timer)clearTimeout(timer)}
};
const post = (path,data) => api(path,{method:"POST",body:JSON.stringify(data)});
const toast = text => {$("#toast").textContent=text;$("#toast").classList.add("show");setTimeout(()=>$("#toast").classList.remove("show"),2400)};
let devices=[], selected=null, scanned=[], esimLoading=false, esimDiagnostic=null, logSource=null;

const displayNumber = status => status?.number_clean||"SIM 未存储号码";
const signalText = status => status?.signal_dbm===null||status?.signal_dbm===undefined?"信号未知":`${status.signal_quality} · ${status.signal_dbm} dBm`;

function renderDevices(){
  const keyword=$("#searchInput").value.toLowerCase();
  const shown=devices.filter(d=>JSON.stringify(d).toLowerCase().includes(keyword));
  $("#deviceList").innerHTML=shown.length?shown.map(d=>`<article class="device-item ${selected?.id===d.id?"active":""}" data-id="${esc(d.id)}"><header><b>${esc(d.name||"蜂窝设备")}</b><i class="dot ${d.online?"online":""}"></i><span class="badge">${d.online?"在线":"离线"}</span></header><p class="device-network">${esc(d.status?.operator_clean||"等待网络")} · ${esc(d.status?.network_mode_clean||"网络未知")}</p><p>${esc(signalText(d.status))}</p></article>`).join(""):`<div class="empty-state">暂无设备<br>点击右上角“添加设备”开始接管</div>`;
  document.querySelectorAll(".device-item").forEach(el=>el.onclick=()=>selectDevice(el.dataset.id));
}
function fillForm(device){
  const form=$("#configForm");
  ["id","name","imei","usb_path","network_interface","at_port","control_device","apn","mode","esim_backend"].forEach(k=>form.elements[k].value=device[k]|| (k==="mode"?"AT":k==="esim_backend"?"AUTO":""));
  form.elements.network_enabled.checked=Boolean(device.network_enabled);
  form.elements.vowifi.checked=Boolean(device.vowifi);
}
function showDevice(device){
  selected=device;renderDevices();fillForm(device);
  $("#emptyDevice").classList.add("hidden");$("#deviceContent").classList.remove("hidden");
  const s=device.status||{};
  $("#deviceBanner").innerHTML=`<span class="logo">V</span><div><h2>${esc(device.name||"蜂窝设备")}</h2><p class="meta"><span class="status-dot ${device.online?"online":""}">${device.online?"在线":"离线"}</span><span>${esc(s.operator_clean||"等待网络")}</span><span>${esc(s.network_mode_clean||"网络未知")}</span><span>${esc(displayNumber(s))}</span></p></div>`;
  const signalValue=s.signal_percent===null||s.signal_percent===undefined?"--":`${s.signal_percent}%`;
  $("#overviewGrid").innerHTML=`<section class="overview-panel"><h4>移动网络</h4><div class="network-pill">● ${esc(s.operator_clean||"等待网络")}</div><div class="signal-head"><div><div class="signal-big">${esc(signalValue)}</div><p>信号质量 · ${esc(s.signal_quality||"未知")}</p><small>百分比根据模组 CSQ 粗略估算</small></div><b>${esc(s.signal_dbm===null||s.signal_dbm===undefined?"-- dBm":`${s.signal_dbm} dBm`)}</b></div><div class="signal-meter"><i style="width:${esc(s.signal_percent??0)}%"></i></div><dl><dt>网络制式</dt><dd>${esc(s.network_mode_clean||"未知")}</dd><dt>注册状态</dt><dd>${esc(s.registration_clean||"未知")}</dd><dt>SIM 状态</dt><dd>${esc(s.sim_clean||"未知")}</dd></dl></section><section class="overview-panel"><h4>SIM 卡</h4><div class="phone-number"><span>本机号码</span><b>${esc(displayNumber(s))}</b>${s.number_clean?"":`<small>运营商未将号码写入 SIM，无法由设备自动读取</small>`}</div><dl><dt>ICCID</dt><dd>${esc(s.iccid_clean||"未知")}</dd><dt>IMSI</dt><dd>${esc(s.imsi_clean||"未知")}</dd></dl></section><section class="overview-panel"><h4>数据连接</h4><div class="network-empty">${device.network_enabled?"移动数据已开启":"移动数据未开启"}</div></section><section class="traffic-panel"><h3>当前设备流量分析</h3><p>数据每分钟采样一次，按日/周/月聚合</p><div>${device.network_enabled?"等待流量采样数据":"网络已禁用，暂无流量分析"}</div></section>`;
}
async function loadDevices(){
  try{
    const data=await api("/api/devices");devices=data.devices;
    const current=devices.find(d=>d.id===(selected?.id||data.selected))||devices[0];
    renderDevices();
    if(current)showDevice(current);
    else{selected=null;$("#deviceContent").classList.add("hidden");$("#emptyDevice").classList.remove("hidden")}
  }catch(e){toast(e.message)}
}
async function scan(open=true){
  if(open){$("#modal").classList.add("open");$("#scanResults").innerHTML=`<div class="empty-state">正在扫描设备...</div>`;$("#addConfig").classList.add("hidden")}
  try{
    $("#scanButton").textContent="扫描中...";
    scanned=(await post("/api/devices/scan",{})).devices;
    const available=scanned.filter(d=>!d.configured);
    $("#scanResults").innerHTML=available.length?available.map(d=>`<article class="scan-card" data-id="${esc(d.id)}"><b>${esc(d.name||d.id)}</b><p>AT：${esc(d.at_port)} · IMEI：${esc(d.imei||"未知")}</p><p>USB：${esc(d.usb_path||"未知")}</p></article>`).join(""):`<div class="empty-state">暂无可添加设备（或系统未发现新的模组）</div>`;
    $("#addConfig").classList.add("hidden");
    document.querySelectorAll(".scan-card").forEach(el=>el.onclick=()=>chooseScanned(el,available.find(x=>x.id===el.dataset.id)));
  }catch(e){toast(e.message)}finally{$("#scanButton").textContent="◌ 重新扫描"}
}
async function selectDevice(id){
  const device=devices.find(d=>d.id===id);if(!device)return;showDevice(device);
  if(device.configured)try{await post("/api/devices/select",{id})}catch(e){toast(e.message)}
}
function chooseScanned(element,device){
  document.querySelectorAll(".scan-card").forEach(x=>x.classList.remove("active"));element.classList.add("active");
  $("#selectedScan").innerHTML=`<b>${esc(device.name||device.id)}</b><p>AT：${esc(device.at_port)} · IMEI：${esc(device.imei||"未知")} · USB：${esc(device.usb_path||"未知")}</p>`;
  fillNamedForm($("#addForm"),device);$("#addConfig").classList.remove("hidden");
}
function fillNamedForm(form,device){
  ["id","name","imei","usb_path","network_interface","at_port","control_device","apn","mode","esim_backend"].forEach(k=>form.elements[k].value=device[k]||(k==="mode"?"AT":k==="esim_backend"?"AUTO":""));
  form.elements.network_enabled.checked=Boolean(device.network_enabled);form.elements.vowifi.checked=Boolean(device.vowifi);
}
function formData(form=$("#configForm")){
  const f=form.elements;return {id:f.id.value,name:f.name.value,imei:f.imei.value,usb_path:f.usb_path.value,network_interface:f.network_interface.value,at_port:f.at_port.value,control_device:f.control_device.value,apn:f.apn.value,mode:f.mode.value,esim_backend:f.esim_backend.value,network_enabled:f.network_enabled.checked,vowifi:f.vowifi.checked};
}
function switchTab(id){document.querySelectorAll(".tabs button,.tab").forEach(x=>x.classList.remove("active"));document.querySelector(`[data-tab="${id}"]`).classList.add("active");$(`#${id}`).classList.add("active");if(id==="esim")loadEsim();if(id==="logs")startLogs();else stopLogs()}
document.querySelectorAll(".tabs button").forEach(b=>b.onclick=()=>switchTab(b.dataset.tab));
$("#searchInput").oninput=renderDevices;
$("#refreshButton").onclick=loadDevices;$("#scanButton").onclick=()=>scan(true);$("#addButton").onclick=()=>scan(true);$("#closeModal").onclick=()=>$("#modal").classList.remove("open");
$("#cancelAdd").onclick=()=>$("#modal").classList.remove("open");
$("#saveAdd").onclick=async()=>{try{const d=await post("/api/devices/save",formData($("#addForm")));$("#modal").classList.remove("open");toast("设备已添加");selected=d.device;await loadDevices()}catch(e){toast(e.message)}};
$("#saveButton").onclick=async()=>{try{const d=await post("/api/devices/save",formData());toast("设备配置已保存");selected=d.device;await loadDevices()}catch(e){toast(e.message)}};
$("#deleteButton").onclick=async()=>{if(!selected||!confirm(`删除设备 ${selected.name||selected.id}？`))return;try{await post("/api/devices/delete",{id:selected.id});selected=null;toast("设备已删除");await loadDevices()}catch(e){toast(e.message)}};
function addSession(container,command,response){const empty=container.querySelector(".session-empty");if(empty)empty.remove();container.insertAdjacentHTML("beforeend",`<article class="session-entry"><b>› ${esc(command)}</b><pre>${esc(response)}</pre></article>`);container.scrollTop=container.scrollHeight}
$("#atTemplate").onchange=e=>{$("#atInput").value=e.target.value};
$("#clearAt").onclick=()=>$("#atHistory").innerHTML=`<div class="session-empty">暂无 AT 会话记录</div>`;
$("#clearUssd").onclick=()=>$("#ussdHistory").innerHTML=`<div class="session-empty">暂无 USSD 会话记录</div>`;
function appendLog(line){
  const terminal=$("#logTerminal"),nearBottom=terminal.scrollHeight-terminal.scrollTop-terminal.clientHeight<80;
  const lines=(terminal.textContent?terminal.textContent.split("\n"):[]).concat(line).slice(-1000);
  terminal.textContent=lines.join("\n");
  if(nearBottom)terminal.scrollTop=terminal.scrollHeight;
}
async function startLogs(){
  if(logSource)return;
  const terminal=$("#logTerminal"),status=$("#logStatus");
  status.textContent="连接中";status.classList.remove("online");
  let sequence=0;
  try{
    const snapshot=await api("/api/logs",{timeout:10000});
    sequence=snapshot.sequence||0;
    terminal.textContent=(snapshot.lines||[]).join("\n")||"暂无运行日志";
    terminal.scrollTop=terminal.scrollHeight;
  }catch(e){terminal.textContent=`日志快照读取失败：${e.message}`}
  logSource=new EventSource(`/api/logs/stream?after=${sequence}`);
  logSource.onopen=()=>{status.textContent="实时连接";status.classList.add("online")};
  logSource.onmessage=e=>{try{appendLog(JSON.parse(e.data).line)}catch(error){appendLog(e.data)}};
  logSource.onerror=()=>{status.textContent="正在重连";status.classList.remove("online")};
}
function stopLogs(){if(logSource){logSource.close();logSource=null}const status=$("#logStatus");if(status){status.textContent="未连接";status.classList.remove("online")}}
$("#clearLogs").onclick=()=>{$("#logTerminal").textContent=""};
$("#atForm").onsubmit=async e=>{e.preventDefault();const cmd=$("#atInput").value;try{const d=await post("/api/at",{command:cmd,timeout:Math.ceil(Number($("#atTimeout").value)/1000)});addSession($("#atHistory"),cmd,d.response)}catch(x){addSession($("#atHistory"),cmd,`ERROR: ${x.message}`)}};
$("#ussdForm").onsubmit=async e=>{e.preventDefault();const code=$("#ussdInput").value;try{const d=await post("/api/ussd",{code,timeout:Math.ceil(Number($("#ussdTimeout").value)/1000)});addSession($("#ussdHistory"),code,d.response)}catch(x){addSession($("#ussdHistory"),code,`ERROR: ${x.message}`)}};
function deepValue(value,keys){
  if(!value||typeof value!=="object")return "";
  for(const [key,item] of Object.entries(value)){
    if(keys.includes(key.toLowerCase())&&item!==null&&typeof item!=="object")return String(item);
  }
  for(const item of Object.values(value)){const found=deepValue(item,keys);if(found)return found}
  return "";
}
function profileItems(value){
  if(Array.isArray(value))return value;
  if(!value||typeof value!=="object")return [];
  for(const key of ["profiles","profileList","profileInfoList","profile_info_list"]){
    if(Array.isArray(value[key]))return value[key];
  }
  for(const item of Object.values(value)){const found=profileItems(item);if(found.length)return found}
  return [];
}
function normalizedProfile(profile){
  const p=profile.profile||profile.profileInfo||profile;
  const state=deepValue(p,["state","profilestate","profile_state"])||"disabled";
  const enabled=/enable|active/i.test(state)&&!/disable|inactive/i.test(state);
  const iccid=deepValue(p,["iccid"]);
  return {
    iccid,
    name:deepValue(p,["nickname","profilename","profile_name"])||deepValue(p,["serviceprovidername","service_provider_name"])||iccid||"未命名 Profile",
    provider:deepValue(p,["serviceprovidername","service_provider_name","operatorname"])||"eSIM Profile",
    type:deepValue(p,["profileclass","profile_class","profiletype","profile_type"])||"Operational",
    enabled,
  };
}
function renderEsimSummary(info,profiles,capability={},profilesError=""){
  const eid=deepValue(info,["eid"])||"未提供";
  const name=deepValue(info,["applicationname","application_name"])||"eSTK / eSIM";
  const enabled=profiles.filter(p=>p.enabled).length;
  $("#esimName").textContent=name;
  const backend=String(capability.backend||"").toUpperCase();
  $("#esimInfo").textContent=eid==="未提供"?`通过 ${backend||"自动"} 后端管理 eSIM`:`EID ${eid} · ${backend||"AUTO"}`;
  const profileCount=profilesError?"读取失败":`${profiles.length} 个`;
  const enabledCount=profilesError?"--":`${enabled} 个`;
  const status=profilesError?"已连接":profiles.length?"可用":"未安装 Profile";
  $("#esimSummary").innerHTML=`<article title="${esc(eid)}"><span>EID</span><b>${esc(eid)}</b></article><article><span>Profile</span><b>${profileCount}</b></article><article><span>已启用</span><b>${enabledCount}</b></article><article><span>eUICC 状态</span><b>${status}</b></article>`;
}
async function loadEsim(){
  if(!selected||esimLoading)return;
  esimLoading=true;
  $("#reloadEsim").disabled=true;$("#reloadEsim").textContent="读取中...";
  $("#profileList").innerHTML=`<div class="empty-state">正在读取 eSIM...</div>`;
  try{
    esimDiagnostic=await api("/api/esim/diagnostics",{timeout:10000});
    $("#esimInfo").textContent=`${esimDiagnostic.configured} → ${esimDiagnostic.selected} · ${esimDiagnostic.reason}`;
    const d=await api("/api/esim",{timeout:150000});
    const profiles=profileItems(d.profiles).map(normalizedProfile);
    renderEsimSummary(d.info||{},profiles,d.capability||{},d.profiles_error||"");
    if(d.profiles_error){
      $("#profileList").innerHTML=`<div class="esim-warning"><b>eUICC 已连接，但 Profile 列表读取失败</b><span>${esc(d.profiles_error)}</span><small>基础信息已正常显示；可刷新重试，或继续检查当前 eSIM 通道。</small></div>`;
    }else{
      $("#profileList").innerHTML=profiles.length?profiles.map(profileCard).join(""):`<div class="empty-state">eUICC 已连接，但未发现 Profile<br>可在下方输入激活码下载</div>`;
    }
  }catch(e){
    $("#esimInfo").textContent=esimDiagnostic?`${esimDiagnostic.configured} → ${esimDiagnostic.selected} · 读取失败`:"eSIM 读取失败";
    $("#esimSummary").innerHTML=`<article><span>EID</span><b>读取失败</b></article><article><span>Profile</span><b>--</b></article><article><span>已启用</span><b>--</b></article><article><span>eUICC 状态</span><b>异常</b></article>`;
    const diagnostic=esimDiagnostic?.reason?`当前通道：${esimDiagnostic.reason}`:"未能完成通道诊断";
    $("#profileList").innerHTML=`<div class="esim-error"><b>无法读取 eSIM</b><span>${esc(e.message)}</span><small>${esc(diagnostic)}</small></div>`;
  }finally{esimLoading=false;$("#reloadEsim").disabled=false;$("#reloadEsim").textContent="刷新"}
}
function profileCard(p){return `<article class="profile-card"><header><b>${esc(p.name)}</b><span>ICCID ${esc(p.iccid||"未知")}</span></header><div class="profile-row"><i class="dot ${p.enabled?"online":""}"></i><div class="profile-meta"><b>${esc(p.provider)}</b><small>${p.enabled?"已启用":"已禁用"}</small><span class="profile-type">${esc(p.type)}</span></div><div class="profile-actions">${p.enabled?`<button data-action="disable" data-iccid="${esc(p.iccid)}">禁用</button>`:`<button class="enable" data-action="enable" data-iccid="${esc(p.iccid)}">启用</button>`}<button data-action="nickname" data-name="${esc(p.name)}" data-iccid="${esc(p.iccid)}">改名</button><button class="delete" data-action="delete" data-iccid="${esc(p.iccid)}">删除</button></div></div></article>`}
$("#profileList").onclick=async e=>{const b=e.target.closest("button[data-action]");if(!b||b.disabled)return;let nickname;if(!b.dataset.iccid){toast("该 Profile 没有可用 ICCID");return}if(b.dataset.action==="nickname"){nickname=prompt("输入新的 Profile 名称",b.dataset.name||"");if(nickname===null)return;if(!nickname.trim()){toast("名称不能为空");return}}if(b.dataset.action==="delete"&&!confirm("确定删除该 Profile？此操作不可恢复。"))return;try{b.disabled=true;await post("/api/esim/profile",{action:b.dataset.action,iccid:b.dataset.iccid,nickname});toast("eSIM 操作完成");await loadEsim()}catch(x){toast(x.message);b.disabled=false}};
$("#reloadEsim").onclick=loadEsim;
$("#downloadForm").onsubmit=async e=>{e.preventDefault();const f=e.target.elements,b=e.submitter||e.target.querySelector("button");try{b.disabled=true;b.textContent="正在下载...";await post("/api/esim/download",{activation_code:f.activation_code.value,smdp:f.smdp.value,matching_id:f.matching_id.value,confirmation_code:f.confirmation_code.value,imei:f.imei.value});toast("Profile 下载完成");e.target.reset();await loadEsim()}catch(x){toast(x.message)}finally{b.disabled=false;b.textContent="开始下载"}};
renderDevices();
loadDevices();
