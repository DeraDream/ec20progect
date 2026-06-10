import json
import os
import subprocess

from ec20 import EC20Error


class Lpac:
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
        debug_lines = [
            line.split("AT_DEBUG:", 1)[1].strip()
            for line in (output or "").splitlines()
            if "AT_DEBUG:" in line
        ]
        last_command = next((line for line in reversed(debug_lines) if line.startswith("AT+")), "")
        if last_command.startswith("AT+CCHO"):
            return "打开 eUICC ISD-R 逻辑通道时无响应"
        if last_command.startswith("AT+CGLA"):
            return "逻辑通道已打开，但 eUICC APDU 无响应"
        if last_command.startswith("AT+CCHC"):
            return "关闭旧逻辑通道时无响应"
        return "未收到 eUICC 响应"

    @staticmethod
    def run(port, *args, timeout=120, backend="at", control_device="", slot=1):
        env = os.environ.copy()
        env.update({
            "LPAC_APDU": backend,
            "LPAC_APDU_AT_DEVICE": port,
            "AT_DEVICE": port,
            "LPAC_HTTP": "curl",
        })
        if backend == "at":
            env["LPAC_APDU_AT_DEBUG"] = "true"
        if backend == "qmi":
            env["LPAC_APDU_QMI_DEVICE"] = control_device
            env["LPAC_APDU_QMI_UIM_SLOT"] = str(slot)
        try:
            process = subprocess.run(
                ["lpac-qmi" if backend == "qmi" else "lpac", *args],
                capture_output=True,
                text=True,
                timeout=timeout,
                env=env,
                check=False,
            )
        except FileNotFoundError as exc:
            name = "lpac-qmi" if backend == "qmi" else "lpac"
            raise EC20Error(f"系统未安装 {name}，请执行 ec20 更新") from exc
        except subprocess.TimeoutExpired as exc:
            partial = exc.stdout or ""
            if isinstance(partial, bytes):
                partial = partial.decode("utf-8", "replace")
            raise EC20Error(
                f"lpac 在 {timeout} 秒内超时：{Lpac._timeout_detail(partial)}"
            ) from exc
        stdout = process.stdout.strip()
        stderr = process.stderr.strip()
        output = stdout or stderr
        try:
            result = Lpac._json_result(stdout)
        except json.JSONDecodeError as exc:
            raise EC20Error(Lpac._friendly_error(output, process.returncode)) from exc
        payload = result.get("payload", {})
        if process.returncode != 0 or payload.get("code", 0) != 0:
            raise EC20Error(payload.get("message") or Lpac._friendly_error(stderr or output, process.returncode))
        return payload.get("data", {})

    def info(self, port, timeout=20, **transport):
        return self.run(port, "chip", "info", timeout=timeout, **transport)

    def profiles(self, port, timeout=20, **transport):
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
