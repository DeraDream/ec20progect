#!/usr/bin/env python3
import json
import os
import re
import threading
import traceback
from contextlib import contextmanager
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from ec20 import EC20Error, EC20Modem
from lpac import Lpac


APP_DIR = Path(__file__).resolve().parent.parent
STATIC_DIR = APP_DIR / "static"
DATA_DIR = Path(os.environ.get("EC20_DATA_DIR", "/opt/ec20-manager/data"))
CONFIG_FILE = DATA_DIR / "config.json"
MODEM = EC20Modem()
LPAC = Lpac()
ESIM_LOCK = threading.Lock()


def read_config():
    try:
        return json.loads(CONFIG_FILE.read_text("utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def write_config(config):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(json.dumps(config, ensure_ascii=False, indent=2), "utf-8")


def device_id_for_port(port):
    return re.sub(r"[^a-zA-Z0-9_-]+", "-", Path(port).name).strip("-").lower() or "ec20"


def devices_config():
    config = read_config()
    return config.setdefault("devices", {})


def scan_devices():
    config = read_config()
    configured = config.setdefault("devices", {})
    discovered = []
    seen_modems = set()
    for port in MODEM.at_ports():
        existing = next((item for item in configured.values() if MODEM.same_port(item.get("at_port"), port)), None)
        status = MODEM.status(port)
        identity = status.get("imei_clean") or os.path.realpath(port)
        if identity in seen_modems:
            continue
        seen_modems.add(identity)
        device_id = existing.get("id") if existing else device_id_for_port(port)
        discovered.append({
            "id": device_id,
            "name": (existing or {}).get("name") or status.get("model_clean") or device_id,
            "at_port": port,
            "imei": status.get("imei_clean", ""),
            "usb_path": MODEM.usb_path(port),
            "network_interface": (existing or {}).get("network_interface", ""),
            "control_device": (existing or {}).get("control_device", ""),
            "esim_backend": (existing or {}).get("esim_backend", "AUTO"),
            "esim_slot": (existing or {}).get("esim_slot", 1),
            "apn": (existing or {}).get("apn", ""),
            "mode": (existing or {}).get("mode", "AT"),
            "network_enabled": bool((existing or {}).get("network_enabled", False)),
            "vowifi": bool((existing or {}).get("vowifi", False)),
            "configured": bool(existing),
            "online": True,
            "status": status,
        })
    return discovered


def all_devices():
    config = read_config()
    configured = config.setdefault("devices", {})
    discovered = {item["id"]: item for item in scan_devices()}
    result = []
    for device_id, device in configured.items():
        merged = dict(device)
        merged.update(discovered.pop(device_id, {}))
        merged["online"] = bool(any(MODEM.same_port(merged.get("at_port"), port) for port in MODEM.ports()) and merged.get("status"))
        merged["configured"] = True
        result.append(merged)
    return result


def selected_port():
    config = read_config()
    selected_id = config.get("selected_device")
    selected = config.get("devices", {}).get(selected_id, {})
    if any(MODEM.same_port(selected.get("at_port"), item) for item in MODEM.ports()):
        return selected["at_port"]
    port = config.get("port")
    if any(MODEM.same_port(port, item) for item in MODEM.ports()):
        return port
    port = MODEM.find_at_port()
    if port:
        config["port"] = port
        write_config(config)
    return port


def selected_device():
    config = read_config()
    return config.get("devices", {}).get(config.get("selected_device"), {})


def selected_esim_transport():
    port = selected_port()
    if not port:
        raise EC20Error("没有检测到可响应 AT 指令的 EC20 串口")
    device = selected_device()
    backend = str(device.get("esim_backend", "AUTO")).upper()
    control_device = str(device.get("control_device", "")).strip()
    control_devices = MODEM.control_devices()
    if not control_device and len(control_devices) == 1:
        control_device = control_devices[0]
    if backend == "QMI" or (backend == "AUTO" and control_device):
        if not control_device or not os.path.exists(control_device):
            raise EC20Error("eSIM 已选择 QMI 后端，但未配置可用的 QMI 控制设备（例如 /dev/cdc-wdm0）")
        slot = max(1, min(5, int(device.get("esim_slot", 1))))
        return port, {"supported": True, "backend": "qmi"}, {
            "backend": "qmi",
            "control_device": control_device,
            "slot": slot,
        }
    esim_port, capability = MODEM.find_esim_port(port)
    if not capability["supported"]:
        missing = "、".join(capability["unsupported"])
        raise EC20Error(
            f"同一设备的 AT 端口均不支持 eSIM 逻辑通道命令：{missing}。"
            "请确认模组固件支持 AT+CCHO、AT+CCHC 和 AT+CGLA"
        )
    capability["backend"] = "at"
    return esim_port, capability, {"backend": "at"}


@contextmanager
def esim_operation():
    if not ESIM_LOCK.acquire(blocking=False):
        raise EC20Error("另一个 eSIM 读取或操作仍在进行，请稍后再试")
    try:
        with MODEM.serial_session():
            yield
    finally:
        ESIM_LOCK.release()


def ensure_esim_port_available(port):
    holders = MODEM.port_holders(port)
    if holders:
        processes = "、".join(f'{item["name"]} (PID {item["pid"]})' for item in holders)
        raise EC20Error(f"eSIM AT 端口正被其他程序占用：{processes}。请停止该程序后重试")


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(STATIC_DIR), **kwargs)

    def log_message(self, fmt, *args):
        print(f"{self.address_string()} - {fmt % args}")

    def end_headers(self):
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate")
        self.send_header("Pragma", "no-cache")
        self.send_header("Expires", "0")
        super().end_headers()

    def send_json(self, value, status=200):
        body = json.dumps(value, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def body_json(self):
        length = int(self.headers.get("Content-Length", 0))
        if length > 1024 * 1024:
            raise ValueError("请求内容过大")
        return json.loads(self.rfile.read(length) or b"{}")

    def do_GET(self):
        path = urlparse(self.path).path
        if not path.startswith("/api/"):
            return super().do_GET()
        try:
            if path == "/api/health":
                return self.send_json({"ok": True, "version": (APP_DIR / "VERSION").read_text().strip()})
            if path == "/api/ports":
                return self.send_json({"ports": MODEM.ports(), "selected": selected_port()})
            if path == "/api/devices":
                config = read_config()
                return self.send_json({"devices": all_devices(), "selected": config.get("selected_device")})
            port = selected_port()
            if not port:
                raise EC20Error("没有检测到可响应 AT 指令的 EC20 串口")
            if path == "/api/status":
                return self.send_json(MODEM.status(port))
            if path == "/api/sms":
                return self.send_json({"messages": MODEM.list_sms(port)})
            if path == "/api/esim":
                with esim_operation():
                    esim_port, capability, transport = selected_esim_transport()
                    if transport["backend"] == "at":
                        ensure_esim_port_available(esim_port)
                    info = LPAC.info(esim_port, **transport)
                    profiles = LPAC.profiles(esim_port, **transport)
                return self.send_json({"info": info, "profiles": profiles, "capability": capability, "port": esim_port})
            return self.send_json({"error": "接口不存在"}, 404)
        except Exception as exc:
            self.send_json({"error": str(exc)}, 503)

    def do_POST(self):
        path = urlparse(self.path).path
        try:
            data = self.body_json()
            if path == "/api/devices/scan":
                return self.send_json({"devices": scan_devices()})
            if path == "/api/devices/save":
                device_id = re.sub(r"[^a-zA-Z0-9_-]+", "-", str(data.get("id", "")).strip())
                port = str(data.get("at_port", ""))
                if not device_id:
                    raise EC20Error("设备 ID 不能为空")
                if not any(MODEM.same_port(port, item) for item in MODEM.ports()):
                    raise EC20Error("AT 端口不存在")
                if "OK" not in MODEM.command(port, "AT", timeout=2):
                    raise EC20Error("AT 端口未响应")
                config = read_config()
                device = {
                    "id": device_id,
                    "name": str(data.get("name", "")).strip() or device_id,
                    "imei": str(data.get("imei", "")).strip(),
                    "usb_path": str(data.get("usb_path", "")).strip(),
                    "network_interface": str(data.get("network_interface", "")).strip(),
                    "at_port": port,
                    "control_device": str(data.get("control_device", "")).strip(),
                    "esim_backend": str(data.get("esim_backend", "AUTO")).upper(),
                    "esim_slot": max(1, min(5, int(data.get("esim_slot", 1)))),
                    "apn": str(data.get("apn", "")).strip(),
                    "mode": str(data.get("mode", "AT")),
                    "network_enabled": bool(data.get("network_enabled")),
                    "vowifi": bool(data.get("vowifi")),
                }
                config.setdefault("devices", {})[device_id] = device
                config["selected_device"] = device_id
                config["port"] = port
                write_config(config)
                return self.send_json({"ok": True, "device": device})
            if path == "/api/devices/select":
                device_id = str(data.get("id", ""))
                config = read_config()
                device = config.get("devices", {}).get(device_id)
                if not device:
                    raise EC20Error("设备不存在或尚未保存")
                config["selected_device"] = device_id
                config["port"] = device.get("at_port")
                write_config(config)
                return self.send_json({"ok": True})
            if path == "/api/devices/delete":
                device_id = str(data.get("id", ""))
                config = read_config()
                config.setdefault("devices", {}).pop(device_id, None)
                if config.get("selected_device") == device_id:
                    config.pop("selected_device", None)
                write_config(config)
                return self.send_json({"ok": True})
            if path == "/api/ports/select":
                port = data.get("port")
                if not any(MODEM.same_port(port, item) for item in MODEM.ports()):
                    raise EC20Error("串口不存在")
                if "OK" not in MODEM.command(port, "AT", timeout=2):
                    raise EC20Error("该串口未响应 AT 指令")
                config = read_config()
                config["port"] = port
                write_config(config)
                return self.send_json({"ok": True, "port": port})

            port = selected_port()
            if not port:
                raise EC20Error("没有检测到可响应 AT 指令的 EC20 串口")
            if path == "/api/at":
                timeout = max(1, min(120, int(data.get("timeout", 10))))
                return self.send_json({"response": MODEM.command(port, str(data.get("command", "")), timeout=timeout)})
            if path == "/api/ussd":
                timeout = max(5, min(120, int(data.get("timeout", 45))))
                return self.send_json({"response": MODEM.ussd(port, str(data.get("code", "")), timeout)})
            if path == "/api/sms/send":
                response = MODEM.send_sms(port, str(data.get("number", "")), str(data.get("text", "")))
                return self.send_json({"ok": True, "response": response})
            if path == "/api/sms/delete":
                response = MODEM.delete_sms(port, data.get("id"))
                return self.send_json({"ok": True, "response": response})
            if path == "/api/estk/apdu":
                return self.send_json({"response": MODEM.apdu(port, str(data.get("apdu", "")))})
            if path == "/api/esim/profile":
                with esim_operation():
                    esim_port, _, transport = selected_esim_transport()
                    if transport["backend"] == "at":
                        ensure_esim_port_available(esim_port)
                    action = str(data.get("action", ""))
                    if action not in ("enable", "disable", "delete", "nickname"):
                        raise EC20Error("不支持的 Profile 操作")
                    value = str(data.get("nickname", "")) if action == "nickname" else None
                    result = LPAC.profile_action(esim_port, action, str(data.get("iccid", "")), value, **transport)
                return self.send_json({"ok": True, "result": result})
            if path == "/api/esim/download":
                with esim_operation():
                    esim_port, _, transport = selected_esim_transport()
                    if transport["backend"] == "at":
                        ensure_esim_port_available(esim_port)
                    if not str(data.get("imei", "")).strip():
                        data["imei"] = MODEM.status(port).get("imei_clean", "")
                    result = LPAC.download(esim_port, data, **transport)
                return self.send_json({"ok": True, "result": result})
            return self.send_json({"error": "接口不存在"}, 404)
        except (ValueError, TypeError, EC20Error) as exc:
            self.send_json({"error": str(exc)}, 400)
        except Exception as exc:
            traceback.print_exc()
            self.send_json({"error": str(exc)}, 503)


def main():
    host = os.environ.get("EC20_WEB_HOST", "0.0.0.0")
    port = int(os.environ.get("EC20_WEB_PORT", "7571"))
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    print(f"EC20 Manager listening on http://{host}:{port}")
    ThreadingHTTPServer((host, port), Handler).serve_forever()


if __name__ == "__main__":
    main()
