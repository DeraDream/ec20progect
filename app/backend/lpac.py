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
    def run(port, *args, timeout=120):
        env = os.environ.copy()
        env.update({
            "LPAC_APDU": "at",
            "AT_DEVICE": port,
            "LPAC_HTTP": "curl",
        })
        try:
            process = subprocess.run(
                ["lpac", *args],
                capture_output=True,
                text=True,
                timeout=timeout,
                env=env,
                check=False,
            )
        except FileNotFoundError as exc:
            raise EC20Error("系统未安装 lpac，请执行更新脚本") from exc
        except subprocess.TimeoutExpired as exc:
            raise EC20Error("lpac 操作超时") from exc
        stdout = process.stdout.strip()
        stderr = process.stderr.strip()
        output = stdout or stderr
        try:
            result = json.loads(stdout)
        except json.JSONDecodeError as exc:
            raise EC20Error(Lpac._friendly_error(output, process.returncode)) from exc
        payload = result.get("payload", {})
        if process.returncode != 0 or payload.get("code", 0) != 0:
            raise EC20Error(payload.get("message") or Lpac._friendly_error(stderr or output, process.returncode))
        return payload.get("data", {})

    def info(self, port):
        return self.run(port, "chip", "info")

    def profiles(self, port):
        return self.run(port, "profile", "list")

    def profile_action(self, port, action, iccid, value=None):
        args = ["profile", action, iccid]
        if value is not None:
            args.append(value)
        return self.run(port, *args)

    def download(self, port, data):
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
        return self.run(port, *args, timeout=300)
