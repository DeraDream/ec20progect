import json
import os
import shutil
import subprocess
import threading

from ec20 import EC20Error


class Lpac:
    logger = None
    LOAD_ERRORS = (
        "error while loading shared libraries",
        "symbol lookup error",
        "undefined symbol",
    )

    @classmethod
    def _friendly_error(cls, output, returncode):
        lowered = output.lower()
        if any(marker in lowered for marker in cls.LOAD_ERRORS):
            return "lpac 与当前系统动态库不兼容，请执行 ec20 更新以重新安装 lpac"
        if "permission denied" in lowered:
            return "没有权限访问 eSIM/串口，请检查服务用户和设备权限"
        if "no such file or directory" in lowered:
            return "lpac 或其依赖文件缺失，请执行 ec20 更新"
        return output or f"lpac 执行失败：{returncode}"

    @staticmethod
    def _json_result(output):
        for line in reversed((output or "").splitlines()):
            try:
                value = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(value, dict) and "payload" in value:
                return value
        raise json.JSONDecodeError("lpac 未返回 JSON", output or "", 0)

    @staticmethod
    def _timeout_detail(output):
        debug_lines = []
        for line in (output or "").splitlines():
            if "AT_DEBUG:" in line:
                debug_lines.append(line.split("AT_DEBUG:", 1)[1].strip())
            elif "AT_DEBUG_TX" in line:
                debug_lines.append(line.split(":", 1)[1].strip())
            elif "APDU" in line.upper():
                debug_lines.append(line.strip())
        last_command = next((line for line in reversed(debug_lines) if line.startswith("AT+")), "")
        if last_command.startswith("AT+CCHO"):
            return "打开 eUICC ISD-R 逻辑通道时无响应"
        if last_command.startswith("AT+CGLA"):
            return "逻辑通道已打开，但 eUICC APDU 无响应"
        if last_command.startswith("AT+CCHC"):
            return "关闭旧逻辑通道时无响应"
        if debug_lines:
            return f"最后调试信息：{debug_lines[-1]}"
        return "未收到 eUICC 响应"

    @staticmethod
    def run(port, *args, timeout=120, backend="at", control_device=""):
        env = os.environ.copy()
        env.update({
            "LPAC_APDU": backend,
            "LPAC_APDU_AT_DEVICE": port,
            "AT_DEVICE": port,
            "LPAC_HTTP": "curl",
            "LIBEUICC_DEBUG_APDU": "true",
        })
        if backend in ("at", "at_csim"):
            env["LPAC_APDU_AT_DEBUG"] = "true"
        if backend in ("qmi", "qmi_qrtr"):
            env["LPAC_APDU_QMI_UIM_SLOT"] = "1"
        if backend == "qmi":
            env["LPAC_APDU_QMI_DEVICE"] = control_device
        binary = "lpac-qmi" if backend in ("qmi", "qmi_qrtr") else "lpac"
        command = [binary, *args]
        if shutil.which("stdbuf"):
            command = ["stdbuf", "-oL", "-eL", *command]
        operation = " ".join(args[:2])
        Lpac._log(f"开始 {operation}，后端={backend}，端口={port}，超时={timeout}s")
        try:
            process = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                env=env,
                bufsize=1,
            )
        except FileNotFoundError as exc:
            raise EC20Error(f"系统未安装 {binary}，请执行 ec20 更新") from exc
        stdout_lines = []
        stderr_lines = []
        readers = [
            threading.Thread(target=Lpac._read_stream, args=(process.stdout, stdout_lines, "stdout"), daemon=True),
            threading.Thread(target=Lpac._read_stream, args=(process.stderr, stderr_lines, "stderr"), daemon=True),
        ]
        for reader in readers:
            reader.start()
        try:
            process.wait(timeout=timeout)
        except subprocess.TimeoutExpired as exc:
            process.kill()
            process.wait()
            for reader in readers:
                reader.join(timeout=2)
            partial = "\n".join(stdout_lines + stderr_lines)
            Lpac._log(f"{operation} 超时：{Lpac._timeout_detail(partial)}", "ERROR")
            raise EC20Error(
                f"lpac 在 {timeout} 秒内超时：{Lpac._timeout_detail(partial)}"
            ) from exc
        for reader in readers:
            reader.join(timeout=2)
        stdout = "\n".join(stdout_lines).strip()
        stderr = "\n".join(stderr_lines).strip()
        output = stdout or stderr
        try:
            result = Lpac._json_result(stdout)
        except json.JSONDecodeError as exc:
            raise EC20Error(Lpac._friendly_error(output, process.returncode)) from exc
        payload = result.get("payload", {})
        if process.returncode != 0 or payload.get("code", 0) != 0:
            raise EC20Error(payload.get("message") or Lpac._friendly_error(stderr or output, process.returncode))
        Lpac._log(f"完成 {operation}")
        return payload.get("data", {})

    @staticmethod
    def _read_stream(stream, output, stream_name):
        if not stream:
            return
        for line in iter(stream.readline, ""):
            clean = line.rstrip("\r\n")
            output.append(clean)
            if clean:
                Lpac._log(clean, "DEBUG", f"lpac/{stream_name}")
        stream.close()

    @staticmethod
    def _log(message, level="INFO", source="lpac"):
        if Lpac.logger:
            Lpac.logger(source, message, level)

    def info(self, port, timeout=20, **transport):
        return self.run(port, "chip", "info", timeout=timeout, **transport)

    def profiles(self, port, timeout=45, **transport):
        return self.run(port, "profile", "list", timeout=timeout, **transport)

    def profile_action(self, port, action, iccid, value=None, **transport):
        args = ["profile", action, iccid]
        if value is not None:
            args.append(value)
        return self.run(port, *args, **transport)

    def download(self, port, data, **transport):
        args = ["profile", "download"]
        activation = str(data.get("activation_code", "")).strip()
        if activation:
            args.extend(["-a", activation])
        else:
            server = str(data.get("smdp", "")).strip()
            if not server:
                raise EC20Error("必须填写 SM-DP+ 地址或完整激活码")
            args.extend(["-s", server])
            for flag, key in (("-m", "matching_id"), ("-c", "confirmation_code"), ("-i", "imei")):
                value = str(data.get(key, "")).strip()
                if value:
                    args.extend([flag, value])
        return self.run(port, *args, timeout=300, **transport)
