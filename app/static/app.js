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
  const fields={model_clean:"设备型号",firmware:"固件版本",imei_clean:"IMEI",iccid_clean:"ICCID",operator_clean:"运营商",sim:"SIM 状态",registration:"网络注册",signal_percent:"信号强度",at_port:"AT 端口",usb_path:"USB 路径"};
  $("#overviewGrid").innerHTML=Object.entries(fields).map(([k,label])=>`<div class="info"><span>${label}</span><b>${esc((k==="signal_percent"&&s[k]!==undefined)?`${s[k]}%`:(s[k]??device[k]??"---"))}</b></div>`).join("");
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
function switchTab(id){document.querySelectorAll(".tabs button,.tab").forEach(x=>x.classList.remove("active"));document.querySelector(`[data-tab="${id}"]`).classList.add("active");$(`#${id}`).classList.add("active")}
document.querySelectorAll(".tabs button").forEach(b=>b.onclick=()=>switchTab(b.dataset.tab));
$("#searchInput").oninput=renderDevices;
$("#refreshButton").onclick=loadDevices;$("#scanButton").onclick=()=>scan(true);$("#addButton").onclick=()=>scan(true);$("#closeModal").onclick=()=>$("#modal").classList.remove("open");
$("#cancelAdd").onclick=()=>$("#modal").classList.remove("open");
$("#saveAdd").onclick=async()=>{try{const d=await post("/api/devices/save",formData($("#addForm")));$("#modal").classList.remove("open");toast("设备已添加");selected=d.device;await loadDevices()}catch(e){toast(e.message)}};
$("#saveButton").onclick=async()=>{try{const d=await post("/api/devices/save",formData());toast("设备配置已保存");selected=d.device;await loadDevices()}catch(e){toast(e.message)}};
$("#deleteButton").onclick=async()=>{if(!selected||!confirm(`删除设备 ${selected.name||selected.id}？`))return;try{await post("/api/devices/delete",{id:selected.id});selected=null;toast("设备已删除");await loadDevices()}catch(e){toast(e.message)}};
$("#atForm").onsubmit=async e=>{e.preventDefault();$("#atResult").textContent="执行中...";try{$("#atResult").textContent=(await post("/api/at",{command:$("#atInput").value})).response}catch(x){$("#atResult").textContent=x.message}};
$("#apduForm").onsubmit=async e=>{e.preventDefault();$("#apduResult").textContent="执行中...";try{$("#apduResult").textContent=(await post("/api/estk/apdu",{apdu:$("#apduInput").value})).response}catch(x){$("#apduResult").textContent=x.message}};
renderDevices();
loadDevices();
