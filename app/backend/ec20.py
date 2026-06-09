import glob
import os
import re
import select
import termios
import threading
import time


class EC20Error(RuntimeError):
    pass


class EC20Modem:
    def __init__(self):
        self._lock = threading.RLock()

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
        result["signal_percent"] = self._signal_percent(result["signal"])
        result["model_clean"] = self._value(result["model"])
        result["imei_clean"] = self._value(result["imei"])
        result["iccid_clean"] = self._value(result["iccid"], "+QCCID:")
        result["operator_clean"] = self._value(result["operator"], "+COPS:")
        result["imsi_clean"] = self._value(result["imsi"])
        result["number_clean"] = self._value(result["number"], "+CNUM:")
        result["network_mode_clean"] = self._value(result["network_mode"], "+QNWINFO:")
        return result

    @staticmethod
    def _value(value, prefix=""):
        lines = [line.strip() for line in (value or "").splitlines() if line.strip() not in ("OK", "ERROR")]
        if prefix:
            lines = [line[len(prefix):].strip() if line.startswith(prefix) else line for line in lines]
        return lines[0] if lines else ""

    @staticmethod
    def _signal_percent(value):
        match = re.search(r"\+CSQ:\s*(\d+)", value or "")
        if not match:
            return 0
        rssi = int(match.group(1))
        return 0 if rssi == 99 else min(100, round(rssi / 31 * 100))

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
