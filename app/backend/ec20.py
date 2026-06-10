import glob
import os
import re
import select
import termios
import threading
import time
from contextlib import contextmanager
from pathlib import Path


class EC20Error(RuntimeError):
    pass


class EC20Modem:
    def __init__(self):
        self._lock = threading.RLock()

    @contextmanager
    def serial_session(self):
        with self._lock:
            yield

    @staticmethod
    def ports():
        patterns = ("/dev/ttyUSB*", "/dev/ttyACM*", "/dev/serial/by-id/*")
        found = []
        for pattern in patterns:
            found.extend(glob.glob(pattern))
        # /dev/serial/by-id/* entries are stable symlinks to ttyUSB/ttyACM
        # nodes. Keep one display path per physical serial endpoint.
        unique = {}
        for port in found:
            real_port = os.path.realpath(port)
            current = unique.get(real_port)
            if current is None or ("/dev/serial/by-id/" in port and "/dev/serial/by-id/" not in current):
                unique[real_port] = port
        return sorted(unique.values())

    @staticmethod
    def control_devices():
        devices = []
        for pattern in ("/dev/cdc-wdm*", "/dev/wwan*qmi*", "/dev/mhi_*qmi*"):
            devices.extend(glob.glob(pattern))
        return sorted(set(devices))

    @staticmethod
    def qrtr_available():
        return any(os.path.exists(path) for path in ("/sys/class/qrtr", "/proc/net/qrtr", "/dev/qrtr"))

    @classmethod
    def same_port(cls, first, second):
        return bool(first and second and os.path.realpath(first) == os.path.realpath(second))

    @staticmethod
    def _configure(fd):
        attrs = termios.tcgetattr(fd)
        attrs[0] = termios.IGNPAR
        attrs[1] = 0
        attrs[2] = termios.CS8 | termios.CREAD | termios.CLOCAL
        attrs[3] = 0
        attrs[4] = termios.B115200
        attrs[5] = termios.B115200
        attrs[6][termios.VMIN] = 0
        attrs[6][termios.VTIME] = 1
        termios.tcsetattr(fd, termios.TCSANOW, attrs)
        termios.tcflush(fd, termios.TCIOFLUSH)

    def command(self, port, command, timeout=5, prompt=None, payload=None, wait_pattern=None):
        if not port or not any(self.same_port(port, item) for item in self.ports()):
            raise EC20Error("串口不存在或未连接")
        if not command.startswith("AT"):
            raise EC20Error("只允许执行 AT 指令")

        with self._lock:
            fd = os.open(port, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
            try:
                self._configure(fd)
                os.write(fd, (command.strip() + "\r").encode("ascii", "strict"))
                output = self._read(fd, timeout, prompt, wait_pattern)
                if prompt and prompt in output and payload is not None:
                    os.write(fd, payload + b"\x1a")
                    output += self._read(fd, timeout, None, wait_pattern)
                return self._clean(command, output)
            finally:
                os.close(fd)

    @staticmethod
    def _read(fd, timeout, prompt, wait_pattern=None):
        deadline = time.monotonic() + timeout
        chunks = []
        while time.monotonic() < deadline:
            readable, _, _ = select.select([fd], [], [], 0.2)
            if not readable:
                continue
            chunk = os.read(fd, 4096)
            if not chunk:
                continue
            chunks.append(chunk)
            text = b"".join(chunks).decode("utf-8", "replace")
            if prompt and prompt in text:
                break
            if wait_pattern and re.search(wait_pattern, text):
                break
            if wait_pattern:
                continue
            if re.search(r"(?:^|\r\n)(OK|ERROR|\+CME ERROR:.*|\+CMS ERROR:.*)\r\n?$", text):
                break
        return b"".join(chunks).decode("utf-8", "replace")

    @staticmethod
    def _clean(command, output):
        lines = [line.strip() for line in output.replace("\r", "").split("\n")]
        return "\n".join(line for line in lines if line and line != command.strip())

    def find_at_port(self):
        ports = self.at_ports()
        return ports[0] if ports else None

    def at_ports(self):
        result = []
        for port in self.ports():
            try:
                if "OK" in self.command(port, "AT", timeout=1):
                    result.append(port)
            except (EC20Error, OSError, termios.error):
                continue
        return result

    @staticmethod
    def usb_path(port):
        try:
            resolved = os.path.realpath(port)
            device = os.path.basename(resolved)
            path = os.path.realpath(f"/sys/class/tty/{device}/device")
            return path if path != f"/sys/class/tty/{device}/device" else ""
        except OSError:
            return ""

    @classmethod
    def usb_device_path(cls, port):
        path = cls.usb_path(port)
        while path and path != "/":
            if os.path.exists(os.path.join(path, "idVendor")) and os.path.exists(os.path.join(path, "idProduct")):
                return path
            if re.search(r":\d+\.\d+$", os.path.basename(path)):
                parent = os.path.dirname(path)
                if parent:
                    return parent
            path = os.path.dirname(path)
        return ""

    def sibling_at_ports(self, preferred_port):
        at_ports = self.at_ports()
        result = [port for port in at_ports if self.same_port(port, preferred_port)]
        usb_device = self.usb_device_path(preferred_port)
        if usb_device:
            ports = self.ports()
            result.extend(
                port
                for port in ports
                if port not in result and self.usb_device_path(port) == usb_device
            )
            return result

        ports = at_ports
        try:
            preferred_imei = self._value(self.command(preferred_port, "AT+CGSN", timeout=2))
        except (EC20Error, OSError, termios.error):
            preferred_imei = ""
        for port in ports:
            if port in result:
                continue
            try:
                imei = self._value(self.command(port, "AT+CGSN", timeout=2))
                if preferred_imei and imei == preferred_imei:
                    result.append(port)
            except (EC20Error, OSError, termios.error):
                continue
        return result

    def status(self, port):
        commands = {
            "manufacturer": "AT+CGMI",
            "model": "AT+CGMM",
            "firmware": "AT+CGMR",
            "imei": "AT+CGSN",
            "sim": "AT+CPIN?",
            "iccid": "AT+QCCID",
            "operator": "AT+COPS?",
            "signal": "AT+CSQ",
            "registration": "AT+CREG?",
            "imsi": "AT+CIMI",
            "number": "AT+CNUM",
            "network_mode": "AT+QNWINFO",
        }
        result = {"port": port, "connected": True}
        for key, command in commands.items():
            try:
                result[key] = self.command(port, command, timeout=2)
            except Exception as exc:
                result[key] = f"ERROR: {exc}"
        result.update(self._signal(result["signal"]))
        result["model_clean"] = self._value(result["model"])
        result["firmware_clean"] = self._value(result["firmware"])
        result["imei_clean"] = self._value(result["imei"])
        result["iccid_clean"] = self._value(result["iccid"], "+QCCID:")
        result["operator_clean"] = self._operator(result["operator"])
        result["imsi_clean"] = self._value(result["imsi"])
        result["number_clean"] = self._number(result["number"])
        result["network_mode_clean"] = self._network_mode(result["network_mode"])
        result["registration_clean"] = self._registration(result["registration"])
        result["sim_clean"] = self._sim_state(result["sim"])
        return result

    @staticmethod
    def _value(value, prefix=""):
        lines = [
            line.strip()
            for line in (value or "").splitlines()
            if line.strip() not in ("OK", "ERROR") and not line.strip().startswith(("+CME ERROR:", "+CMS ERROR:"))
        ]
        if prefix:
            lines = [line[len(prefix):].strip() for line in lines if line.startswith(prefix)]
        return lines[0] if lines else ""

    @classmethod
    def _operator(cls, value):
        raw = cls._value(value, "+COPS:")
        match = re.match(r'\d+,\d+,"([^"]*)"(?:,\d+)?', raw)
        operator = match.group(1) if match else raw
        operators = {
            "46000": "中国移动",
            "46002": "中国移动",
            "46004": "中国移动",
            "46007": "中国移动",
            "46008": "中国移动",
            "46001": "中国联通",
            "46006": "中国联通",
            "46009": "中国联通",
            "46003": "中国电信",
            "46005": "中国电信",
            "46011": "中国电信",
            "46015": "中国广电",
            "CHINA MOBILE": "中国移动",
            "CHN-CMCC": "中国移动",
            "CHINA UNICOM": "中国联通",
            "CHN-UNICOM": "中国联通",
            "CHINA TELECOM": "中国电信",
            "CHN-CT": "中国电信",
        }
        return operators.get(operator.upper(), operator)

    @classmethod
    def _number(cls, value):
        raw = cls._value(value, "+CNUM:")
        match = re.search(r'"(\+?[0-9]{5,20})"', raw)
        return match.group(1) if match else ""

    @classmethod
    def _network_mode(cls, value):
        raw = cls._value(value, "+QNWINFO:")
        fields = re.findall(r'"([^"]*)"', raw)
        if not fields:
            return raw
        return " · ".join(item for item in (fields[0], fields[2] if len(fields) > 2 else "") if item)

    @classmethod
    def _registration(cls, value):
        raw = cls._value(value, "+CREG:")
        match = re.match(r"\d+,(\d+)", raw)
        states = {
            "0": "未注册",
            "1": "已注册（本地）",
            "2": "正在搜索",
            "3": "注册被拒绝",
            "4": "未知",
            "5": "已注册（漫游）",
        }
        return states.get(match.group(1), raw) if match else raw

    @classmethod
    def _sim_state(cls, value):
        raw = cls._value(value, "+CPIN:")
        states = {
            "READY": "就绪",
            "SIM PIN": "需要 SIM PIN",
            "SIM PUK": "需要 SIM PUK",
            "NOT INSERTED": "未插卡",
        }
        return states.get(raw.upper(), raw)

    def esim_capability(self, port):
        managed = ("AT+CCHO=?", "AT+CCHC=?", "AT+CGLA=?")
        required = (*managed, "AT+CSIM=?")
        results = {}
        for command in required:
            try:
                response = self.command(port, command, timeout=3)
            except Exception as exc:
                response = f"ERROR: {exc}"
            results[command] = response
        managed_unsupported = [command for command in managed if not self._command_ok(results[command])]
        csim_supported = self._command_ok(results["AT+CSIM=?"])
        backend = "at" if not managed_unsupported else "at_csim" if csim_supported else ""
        unsupported = [] if backend else [*managed_unsupported, "AT+CSIM=?"]
        return {
            "supported": bool(backend),
            "backend": backend,
            "unsupported": unsupported,
            "responses": results,
        }

    def find_esim_port(self, preferred_port):
        candidates = self.sibling_at_ports(preferred_port) or [preferred_port]
        preferred_capability = None
        for port in candidates:
            capability = self.esim_capability(port)
            if self.same_port(port, preferred_port):
                preferred_capability = capability
            if capability["supported"]:
                return port, capability
        return preferred_port, preferred_capability or self.esim_capability(preferred_port)

    @staticmethod
    def port_holders(port):
        if not port or not os.path.isdir("/proc"):
            return []
        target = os.path.realpath(port)
        holders = []
        for process_dir in glob.glob("/proc/[0-9]*"):
            try:
                pid = int(os.path.basename(process_dir))
                if pid == os.getpid():
                    continue
                if not any(os.path.realpath(fd) == target for fd in glob.glob(f"{process_dir}/fd/*")):
                    continue
                name = Path(f"{process_dir}/comm").read_text("utf-8").strip()
                holders.append({"pid": pid, "name": name or "未知进程"})
            except (FileNotFoundError, PermissionError, OSError, ValueError):
                continue
        return holders

    @staticmethod
    def _command_ok(response):
        lines = [line.strip() for line in (response or "").splitlines() if line.strip()]
        return bool(lines and lines[-1] == "OK")

    @staticmethod
    def _signal(value):
        match = re.search(r"\+CSQ:\s*(\d+)", value or "")
        if not match:
            return {"signal_percent": None, "signal_dbm": None, "signal_quality": "未知"}
        rssi = int(match.group(1))
        if rssi == 99:
            return {"signal_percent": None, "signal_dbm": None, "signal_quality": "未知"}
        percent = min(100, round(rssi / 31 * 100))
        dbm = -113 + 2 * rssi
        if dbm >= -75:
            quality = "优秀"
        elif dbm >= -85:
            quality = "良好"
        elif dbm >= -95:
            quality = "一般"
        else:
            quality = "较弱"
        return {"signal_percent": percent, "signal_dbm": dbm, "signal_quality": quality}

    @staticmethod
    def _signal_percent(value):
        return EC20Modem._signal(value)["signal_percent"]

    def list_sms(self, port):
        self.command(port, "AT+CMGF=1", timeout=2)
        raw = self.command(port, 'AT+CMGL="ALL"', timeout=10)
        messages = []
        current = None
        for line in raw.splitlines():
            match = re.match(r'\+CMGL:\s*(\d+),"([^"]*)","([^"]*)","[^"]*","([^"]*)"', line)
            if match:
                current = {
                    "id": int(match.group(1)),
                    "status": match.group(2),
                    "sender": match.group(3),
                    "time": match.group(4),
                    "text": "",
                }
                messages.append(current)
            elif current and line not in ("OK", "ERROR"):
                current["text"] += ("\n" if current["text"] else "") + line
        for message in messages:
            message["sender"] = self._decode_ucs2(message["sender"])
            message["text"] = self._decode_ucs2(message["text"])
        return messages

    def send_sms(self, port, number, text):
        if not re.fullmatch(r"\+?[0-9]{3,20}", number):
            raise EC20Error("手机号格式不正确")
        if not text or len(text) > 500:
            raise EC20Error("短信内容长度必须为 1-500 字符")
        self.command(port, "AT+CMGF=1", timeout=2)
        unicode_mode = not text.isascii()
        if unicode_mode:
            self.command(port, 'AT+CSCS="UCS2"', timeout=2)
            self.command(port, "AT+CSMP=17,167,0,8", timeout=2)
            target = number.encode("utf-16-be").hex().upper()
            payload = text.encode("utf-16-be").hex().upper().encode("ascii")
        else:
            self.command(port, 'AT+CSCS="GSM"', timeout=2)
            self.command(port, "AT+CSMP=17,167,0,0", timeout=2)
            target = number
            payload = text.encode("ascii")
        return self.command(
            port,
            f'AT+CMGS="{target}"',
            timeout=30,
            prompt=">",
            payload=payload,
        )

    def delete_sms(self, port, message_id):
        return self.command(port, f"AT+CMGD={int(message_id)}", timeout=5)

    def apdu(self, port, apdu):
        compact = re.sub(r"\s+", "", apdu).upper()
        if not compact or not re.fullmatch(r"[0-9A-F]+", compact) or len(compact) % 2:
            raise EC20Error("APDU 必须是偶数长度的十六进制字符串")
        if len(compact) > 1024:
            raise EC20Error("APDU 长度超过首版限制")
        return self.command(port, f'AT+CSIM={len(compact)},"{compact}"', timeout=20)

    def ussd(self, port, code, timeout=45):
        if not code or len(code) > 100 or '"' in code:
            raise EC20Error("USSD 代码格式不正确")
        self.command(port, 'AT+CSCS="GSM"', timeout=2)
        return self.command(
            port,
            f'AT+CUSD=1,"{code}",15',
            timeout=timeout,
            wait_pattern=r"(?:^|\r\n)\+CUSD:",
        )

    @staticmethod
    def _decode_ucs2(value):
        compact = value.strip()
        if len(compact) < 4 or len(compact) % 4 or not re.fullmatch(r"[0-9A-Fa-f]+", compact):
            return value
        try:
            return bytes.fromhex(compact).decode("utf-16-be")
        except UnicodeDecodeError:
            return value
