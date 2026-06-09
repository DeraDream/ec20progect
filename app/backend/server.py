#!/usr/bin/env python3
import json
import os
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
API_TOKEN = os.environ.get("EC20_WEB_TOKEN", "")


def read_config():
    try:
        return json.loads(CONFIG_FILE.read_text("utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def write_config(config):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(json.dumps(config, ensure_ascii=False, indent=2), "utf-8")


def selected_port():
    config = read_config()
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

    def authorized(self):
        if not API_TOKEN:
            return True
        return self.headers.get("Authorization") == f"Bearer {API_TOKEN}"

    def do_GET(self):
        path = urlparse(self.path).path
        if not path.startswith("/api/"):
            return super().do_GET()
        if not self.authorized():
            return self.send_json({"error": "访问令牌无效"}, 401)
        try:
            if path == "/api/health":
                return self.send_json({"ok": True, "version": (APP_DIR / "VERSION").read_text().strip()})
            if path == "/api/ports":
                return self.send_json({"ports": MODEM.ports(), "selected": selected_port()})
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
        if not self.authorized():
            return self.send_json({"error": "访问令牌无效"}, 401)
        try:
            data = self.body_json()
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
