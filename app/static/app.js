const $ = (s) => document.querySelector(s);
const api = async (path, options = {}) => {
  let token = localStorage.getItem("ec20Token") || "";
  let response = await fetch(path, {headers: {"Content-Type": "application/json", "Authorization": `Bearer ${token}`}, ...options});
  if (response.status === 401) {
    token = prompt("请输入安装时生成的 EC20 Web 访问令牌") || "";
    localStorage.setItem("ec20Token", token);
    response = await fetch(path, {headers: {"Content-Type": "application/json", "Authorization": `Bearer ${token}`}, ...options});
  }
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || "请求失败");
  return data;
};
const toast = (text) => {
  $("#toast").textContent = text; $("#toast").classList.add("show");
  setTimeout(() => $("#toast").classList.remove("show"), 2400);
};
const escapeHtml = (v) => String(v ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));

document.querySelectorAll("nav button").forEach(button => button.onclick = () => {
  document.querySelectorAll("nav button,.page").forEach(el => el.classList.remove("active"));
  button.classList.add("active"); $(`#${button.dataset.page}`).classList.add("active");
  $("#pageTitle").textContent = button.textContent;
  if (button.dataset.page === "sms") loadSms();
});

async function loadPorts() {
  try {
    const data = await api("/api/ports");
    $("#portSelect").innerHTML = data.ports.map(p => `<option ${p === data.selected ? "selected":""}>${escapeHtml(p)}</option>`).join("");
    $("#stateText").textContent = data.selected ? `已连接 ${data.selected}` : "未发现 EC20";
    $("#stateDot").classList.toggle("ok", Boolean(data.selected));
    if (data.selected) loadStatus();
  } catch (e) { toast(e.message); }
}
async function loadStatus() {
  try {
    const data = await api("/api/status");
    const keys = {model:"设备型号",firmware:"固件版本",imei:"IMEI",sim:"SIM 状态",iccid:"ICCID",operator:"运营商",registration:"网络注册",port:"AT 串口"};
    $("#statusGrid").innerHTML = Object.entries(keys).map(([key,label]) => `<article class="card"><span>${label}</span><strong>${escapeHtml(data[key] || "--")}</strong></article>`).join("");
    $("#signalValue").textContent = `${data.signal_percent}%`; $("#signalBar").style.width = `${data.signal_percent}%`;
  } catch (e) { toast(e.message); }
}
async function loadSms() {
  $("#smsList").innerHTML = "<p>正在读取短信...</p>";
  try {
    const {messages} = await api("/api/sms");
    $("#smsList").innerHTML = messages.length ? messages.map(m => `<article class="sms-item"><header><strong>${escapeHtml(m.sender)}</strong><button onclick="deleteSms(${m.id})">删除</button></header><small>${escapeHtml(m.time)} · ${escapeHtml(m.status)}</small><p>${escapeHtml(m.text)}</p></article>`).join("") : "<p>SIM 卡内暂无短信。</p>";
  } catch (e) { $("#smsList").innerHTML = `<p>${escapeHtml(e.message)}</p>`; }
}
window.deleteSms = async id => { if (!confirm("删除这条短信？")) return; try { await api("/api/sms/delete",{method:"POST",body:JSON.stringify({id})}); loadSms(); } catch(e){toast(e.message)} };
$("#refreshPorts").onclick = loadPorts;
$("#portSelect").onchange = async e => { try { await api("/api/ports/select",{method:"POST",body:JSON.stringify({port:e.target.value})}); toast("串口已切换"); loadStatus(); } catch(err){toast(err.message)} };
$("#reloadSms").onclick = loadSms;
$("#smsForm").onsubmit = async e => { e.preventDefault(); $("#smsResult").textContent="正在发送..."; try { const d=await api("/api/sms/send",{method:"POST",body:JSON.stringify({number:$("#smsNumber").value,text:$("#smsText").value})}); $("#smsResult").textContent=d.response; toast("短信已提交发送"); } catch(err){$("#smsResult").textContent=err.message} };
$("#atForm").onsubmit = async e => { e.preventDefault(); $("#atResult").textContent="执行中..."; try { const d=await api("/api/at",{method:"POST",body:JSON.stringify({command:$("#atInput").value})}); $("#atResult").textContent=d.response; } catch(err){$("#atResult").textContent=err.message} };
$("#apduForm").onsubmit = async e => { e.preventDefault(); $("#apduResult").textContent="执行中..."; try { const d=await api("/api/estk/apdu",{method:"POST",body:JSON.stringify({apdu:$("#apduInput").value})}); $("#apduResult").textContent=d.response; } catch(err){$("#apduResult").textContent=err.message} };
loadPorts();
