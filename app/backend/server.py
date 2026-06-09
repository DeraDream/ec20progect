#!/usr/bin/env python3
import json
import os
import re
import traceback
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from ec20 import EC20Error, EC20Modem


APP_DIR = Path(__file__).resolve().parent.parent
STATIC_DIR = APP_DIR / "static"
DATA_DIR = Path(os.environ.get("EC20_DATA_DIR", "/opt/ec20-manager/data"))
CONFIG_FILE = DATA_DIR / "config.json"
MODEM = EC20Modem()


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
    for port in MODEM.at_ports():
        existing = next((item for item in configured.values() if item.get("at_port") == port), None)
        status = MODEM.status(port)
        device_id = existing.get("id") if existing else device_id_for_port(port)
        discovered.append({
            "id": device_id,
            "name": (existing or {}).get("name") or status.get("model_clean") or device_id,
            "at_port": port,
            "imei": status.get("imei_clean", ""),
            "usb_path": MODEM.usb_path(port),
            "network_interface": (existing or {}).get("network_interface", ""),
            "control_device": (existing or {}).get("control_device", ""),
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
        merged["online"] = bool(merged.get("at_port") in MODEM.ports() and merged.get("status"))
        merged["configured"] = True
        result.append(merged)
    result.extend(discovered.values())
    return result


def selected_port():
    config = read_config()
    selected_id = config.get("selected_device")
    selected = config.get("devices", {}).get(selected_id, {})
    if selected.get("at_port") in MODEM.ports():
        return selected["at_port"]
    port = config.get("port")
    if port in MODEM.ports():
        return port
    port = MODEM.find_at_port()
    if port:
        config["port"] = port
        write_config(config)
    return port


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(STATIC_DIR), **kwargs)

    def log_message(self, fmt, *args):
        print(f"{self.address_string()} - {fmt % args}")

    def send_json(self, value, status=200):
        body = json.dumps(value, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
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
                if port not in MODEM.ports():
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
                if port not in MODEM.ports():
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
                return self.send_json({"response": MODEM.command(port, str(data.get("command", "")))})
            if path == "/api/sms/send":
                response = MODEM.send_sms(port, str(data.get("number", "")), str(data.get("text", "")))
                return self.send_json({"ok": True, "response": response})
            if path == "/api/sms/delete":
                response = MODEM.delete_sms(port, data.get("id"))
                return self.send_json({"ok": True, "response": response})
            if path == "/api/estk/apdu":
                return self.send_json({"response": MODEM.apdu(port, str(data.get("apdu", "")))})
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
