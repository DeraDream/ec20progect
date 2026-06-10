const $ = s => document.querySelector(s);
const esc = v => String(v ?? "").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const api = async (path, options={}) => {
  const response = await fetch(path,{headers:{"Content-Type":"application/json"},...options});
  const data = await response.json();
  if(!response.ok) throw new Error(data.error || "请求失败");
  return data;
};
const post = (path,data) => api(path,{method:"POST",body:JSON.stringify(data)});
const toast = text => {$("#toast").textContent=text;$("#toast").classList.add("show");setTimeout(()=>$("#toast").classList.remove("show"),2400)};
let devices=[], selected=null, scanned=[];

function renderDevices(){
  const keyword=$("#searchInput").value.toLowerCase();
  const shown=devices.filter(d=>JSON.stringify(d).toLowerCase().includes(keyword));
  $("#deviceList").innerHTML=shown.length?shown.map(d=>`<article class="device-item ${selected?.id===d.id?"active":""}" data-id="${esc(d.id)}"><header><b>${esc(d.name||d.id)}</b><i class="dot ${d.online?"online":""}"></i><span class="badge">${d.online?"在线":"离线"}</span></header><p>${esc(d.id)} · ${esc(d.at_port||"未配置 AT 端口")}</p><p>${esc(d.status?.operator_clean||d.imei||"等待设备...")}</p></article>`).join(""):`<div class="empty-state">暂无设备<br>点击右上角“添加设备”开始接管</div>`;
  document.querySelectorAll(".device-item").forEach(el=>el.onclick=()=>selectDevice(el.dataset.id));
}
function fillForm(device){
  const form=$("#configForm");
  ["id","name","imei","usb_path","network_interface","at_port","control_device","apn","mode"].forEach(k=>form.elements[k].value=device[k]|| (k==="mode"?"AT":""));
  form.elements.network_enabled.checked=Boolean(device.network_enabled);
  form.elements.vowifi.checked=Boolean(device.vowifi);
}
function showDevice(device){
  selected=device;renderDevices();fillForm(device);
  $("#emptyDevice").classList.add("hidden");$("#deviceContent").classList.remove("hidden");
  $("#deviceBanner").innerHTML=`<span class="logo">V</span><div><h2>${esc(device.name||device.id)}</h2><p class="meta"><span>${esc(device.id)}</span><span>AT：${esc(device.at_port||"---")}</span><span>IMEI：${esc(device.status?.imei_clean||device.imei||"---")}</span></p></div>`;
  const s=device.status||{};
  $("#overviewGrid").innerHTML=`<section class="overview-panel"><h4>运行状态</h4><div class="network-pill">● ${esc(s.operator_clean||"等待网络")}</div><div class="signal-big">${esc(s.signal_percent??0)}%</div><p>信号强度</p><dl><dt>网络模式</dt><dd>${esc(s.network_mode_clean||"---")}</dd><dt>注册状态</dt><dd>${esc(s.registration||"---")}</dd><dt>SIM 状态</dt><dd>${esc(s.sim||"---")}</dd></dl></section><section class="overview-panel"><h4>SIM / 设备</h4><dl><dt>IMEI</dt><dd>${esc(s.imei_clean||device.imei||"---")}</dd><dt>ICCID</dt><dd>${esc(s.iccid_clean||"---")}</dd><dt>IMSI</dt><dd>${esc(s.imsi_clean||"---")}</dd><dt>本机号码</dt><dd>${esc(s.number_clean||"---")}</dd><dt>固件版本</dt><dd>${esc(s.firmware||"---")}</dd><dt>运行模式</dt><dd>${esc(device.mode||"AT")}</dd></dl></section><section class="overview-panel"><h4>网络</h4><div class="network-empty">${device.network_enabled?"网络已开启":"数据未开启"}</div></section><section class="traffic-panel"><h3>当前设备流量分析</h3><p>数据每分钟采样一次，按日/周/月聚合</p><div>${device.network_enabled?"等待流量采样数据":"网络已禁用，暂无流量分析"}</div></section>`;
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
  ["id","name","imei","usb_path","network_interface","at_port","control_device","apn","mode"].forEach(k=>form.elements[k].value=device[k]||(k==="mode"?"AT":""));
  form.elements.network_enabled.checked=Boolean(device.network_enabled);form.elements.vowifi.checked=Boolean(device.vowifi);
}
function formData(form=$("#configForm")){
  const f=form.elements;return {id:f.id.value,name:f.name.value,imei:f.imei.value,usb_path:f.usb_path.value,network_interface:f.network_interface.value,at_port:f.at_port.value,control_device:f.control_device.value,apn:f.apn.value,mode:f.mode.value,network_enabled:f.network_enabled.checked,vowifi:f.vowifi.checked};
}
function switchTab(id){document.querySelectorAll(".tabs button,.tab").forEach(x=>x.classList.remove("active"));document.querySelector(`[data-tab="${id}"]`).classList.add("active");$(`#${id}`).classList.add("active");if(id==="esim")loadEsim()}
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
function renderEsimSummary(info,profiles){
  const eid=deepValue(info,["eid"])||"未提供";
  const name=deepValue(info,["applicationname","application_name"])||"eSTK / eSIM";
  const enabled=profiles.filter(p=>p.enabled).length;
  $("#esimName").textContent=name;
  $("#esimInfo").textContent=eid==="未提供"?"通过 lpac 管理 eSTK Profile":`EID ${eid}`;
  $("#esimSummary").innerHTML=`<article title="${esc(eid)}"><span>EID</span><b>${esc(eid)}</b></article><article><span>Profile</span><b>${profiles.length} 个</b></article><article><span>已启用</span><b>${enabled} 个</b></article><article><span>eUICC 状态</span><b>${profiles.length?"可用":"未安装 Profile"}</b></article>`;
}
async function loadEsim(){
  if(!selected)return;
  $("#reloadEsim").disabled=true;$("#reloadEsim").textContent="读取中...";
  $("#profileList").innerHTML=`<div class="empty-state">正在读取 eSIM...</div>`;
  try{
    const d=await api("/api/esim");
    const profiles=profileItems(d.profiles).map(normalizedProfile);
    renderEsimSummary(d.info||{},profiles);
    $("#profileList").innerHTML=profiles.length?profiles.map(profileCard).join(""):`<div class="empty-state">eUICC 已连接，但未发现 Profile<br>可在下方输入激活码下载</div>`;
  }catch(e){
    $("#esimInfo").textContent="eSIM 读取失败";
    $("#esimSummary").innerHTML=`<article><span>EID</span><b>读取失败</b></article><article><span>Profile</span><b>--</b></article><article><span>已启用</span><b>--</b></article><article><span>eUICC 状态</span><b>异常</b></article>`;
    $("#profileList").innerHTML=`<div class="esim-error"><b>无法读取 eSIM</b><span>${esc(e.message)}</span><small>请先确认 eSTK 已插入、AT 端口可用，并执行 ec20 更新检查 lpac。</small></div>`;
  }finally{$("#reloadEsim").disabled=false;$("#reloadEsim").textContent="刷新"}
}
function profileCard(p){return `<article class="profile-card"><header><b>${esc(p.name)}</b><span>ICCID ${esc(p.iccid||"未知")}</span></header><div class="profile-row"><i class="dot ${p.enabled?"online":""}"></i><div class="profile-meta"><b>${esc(p.provider)}</b><small>${p.enabled?"已启用":"已禁用"}</small><span class="profile-type">${esc(p.type)}</span></div><div class="profile-actions">${p.enabled?`<button data-action="disable" data-iccid="${esc(p.iccid)}">禁用</button>`:`<button class="enable" data-action="enable" data-iccid="${esc(p.iccid)}">启用</button>`}<button data-action="nickname" data-name="${esc(p.name)}" data-iccid="${esc(p.iccid)}">改名</button><button class="delete" data-action="delete" data-iccid="${esc(p.iccid)}">删除</button></div></div></article>`}
$("#profileList").onclick=async e=>{const b=e.target.closest("button[data-action]");if(!b||b.disabled)return;let nickname;if(!b.dataset.iccid){toast("该 Profile 没有可用 ICCID");return}if(b.dataset.action==="nickname"){nickname=prompt("输入新的 Profile 名称",b.dataset.name||"");if(nickname===null)return;if(!nickname.trim()){toast("名称不能为空");return}}if(b.dataset.action==="delete"&&!confirm("确定删除该 Profile？此操作不可恢复。"))return;try{b.disabled=true;await post("/api/esim/profile",{action:b.dataset.action,iccid:b.dataset.iccid,nickname});toast("eSIM 操作完成");await loadEsim()}catch(x){toast(x.message);b.disabled=false}};
$("#reloadEsim").onclick=loadEsim;
$("#downloadForm").onsubmit=async e=>{e.preventDefault();const f=e.target.elements,b=e.submitter||e.target.querySelector("button");try{b.disabled=true;b.textContent="正在下载...";await post("/api/esim/download",{activation_code:f.activation_code.value,smdp:f.smdp.value,matching_id:f.matching_id.value,confirmation_code:f.confirmation_code.value,imei:f.imei.value});toast("Profile 下载完成");e.target.reset();await loadEsim()}catch(x){toast(x.message)}finally{b.disabled=false;b.textContent="开始下载"}};
renderDevices();
loadDevices();
