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
async function loadEsim(){if(!selected)return;$("#profileList").innerHTML=`<div class="empty-state">正在读取 eSIM...</div>`;try{const d=await api("/api/esim");$("#esimName").textContent=d.info?.euiccInfo2?.extCardResource?.installedApplication?.[0]?.applicationName||"eSTK / eSIM";const profiles=Array.isArray(d.profiles)?d.profiles:(d.profiles?.profiles||[]);$("#profileList").innerHTML=profiles.length?profiles.map(profileCard).join(""):`<div class="empty-state">未发现 Profile</div>`}catch(e){$("#profileList").innerHTML=`<div class="empty-state">${esc(e.message)}</div>`}}
function profileCard(p){const iccid=p.iccid||p.profile?.iccid||"";const name=p.nickname||p.profileName||p.serviceProviderName||iccid;const enabled=String(p.state||p.profileState||"").toLowerCase().includes("enable");return `<article class="profile-card"><header><b>${esc(name)}</b><span>ICCID ${esc(iccid)}</span></header><div class="profile-row"><i class="dot ${enabled?"online":""}"></i><div class="profile-meta"><b>${esc(name)}</b><small>${esc(p.serviceProviderName||p.service_provider_name||"eSIM Profile")} · ${enabled?"已启用":"已禁用"}</small></div><div class="profile-actions">${enabled?`<button data-action="disable" data-iccid="${esc(iccid)}">禁用</button>`:`<button class="enable" data-action="enable" data-iccid="${esc(iccid)}">切换</button>`}<button data-action="nickname" data-iccid="${esc(iccid)}">改名</button><button class="delete" data-action="delete" data-iccid="${esc(iccid)}">删除</button></div></div></article>`}
$("#profileList").onclick=async e=>{const b=e.target.closest("button[data-action]");if(!b)return;let nickname;if(b.dataset.action==="nickname"){nickname=prompt("输入新的 Profile 名称");if(nickname===null)return}if(b.dataset.action==="delete"&&!confirm("确定删除该 Profile？"))return;try{await post("/api/esim/profile",{action:b.dataset.action,iccid:b.dataset.iccid,nickname});toast("操作完成");loadEsim()}catch(x){toast(x.message)}};
$("#reloadEsim").onclick=loadEsim;
$("#downloadForm").onsubmit=async e=>{e.preventDefault();const f=e.target.elements;try{await post("/api/esim/download",{activation_code:f.activation_code.value,smdp:f.smdp.value,matching_id:f.matching_id.value,confirmation_code:f.confirmation_code.value,imei:f.imei.value});toast("Profile 下载完成");loadEsim()}catch(x){toast(x.message)}};
renderDevices();
loadDevices();
