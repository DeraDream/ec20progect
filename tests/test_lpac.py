import io
import json
import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app" / "backend"))

from ec20 import EC20Error  # noqa: E402
from lpac import Lpac  # noqa: E402


class FakePopen:
    def __init__(self, command, stdout="", stderr="", returncode=0, timeout=False, **kwargs):
        self.command = command
        self.stdout = io.StringIO(stdout)
        self.stderr = io.StringIO(stderr)
        self.returncode = returncode
        self.timeout = timeout

    def wait(self, timeout=None):
        if self.timeout:
            self.timeout = False
            raise subprocess.TimeoutExpired(self.command, timeout)
        return self.returncode

    def kill(self):
        self.returncode = -9


class LpacTest(unittest.TestCase):
    def setUp(self):
        Lpac.logger = None

    @patch("lpac.shutil.which", return_value=None)
    @patch("lpac.subprocess.Popen")
    def test_returns_payload_data(self, popen, which):
        popen.return_value = FakePopen(
            ["lpac"], stdout=json.dumps({"payload": {"code": 0, "data": {"eid": "123"}}})
        )

        self.assertEqual(Lpac.run("/dev/ttyUSB2", "chip", "info"), {"eid": "123"})
        env = popen.call_args.kwargs["env"]
        self.assertEqual(env["LPAC_APDU"], "at")
        self.assertEqual(env["LPAC_APDU_AT_DEVICE"], "/dev/ttyUSB2")
        self.assertEqual(env["LIBEUICC_DEBUG_APDU"], "true")

    @patch("lpac.shutil.which", return_value="/usr/bin/stdbuf")
    @patch("lpac.subprocess.Popen")
    def test_uses_stdbuf_for_realtime_lpac_logs(self, popen, which):
        popen.return_value = FakePopen(
            ["lpac"], stdout=json.dumps({"payload": {"code": 0, "data": []}})
        )

        Lpac.run("/dev/ttyUSB2", "profile", "list")

        self.assertEqual(popen.call_args.args[0][:4], ["stdbuf", "-oL", "-eL", "lpac"])

    @patch("lpac.shutil.which", return_value=None)
    @patch("lpac.subprocess.Popen")
    def test_qmi_uses_separate_binary_and_transport(self, popen, which):
        popen.return_value = FakePopen(
            ["lpac-qmi"], stdout=json.dumps({"payload": {"code": 0, "data": []}})
        )

        Lpac.run("/dev/ttyUSB2", "profile", "list", backend="qmi", control_device="/dev/cdc-wdm0")

        self.assertEqual(popen.call_args.args[0][0], "lpac-qmi")
        env = popen.call_args.kwargs["env"]
        self.assertEqual(env["LPAC_APDU"], "qmi")
        self.assertEqual(env["LPAC_APDU_QMI_DEVICE"], "/dev/cdc-wdm0")
        self.assertEqual(env["LPAC_APDU_QMI_UIM_SLOT"], "1")

    @patch("lpac.Lpac.run")
    def test_read_operations_use_short_timeout(self, run):
        Lpac().info("/dev/ttyUSB2")
        run.assert_called_once_with("/dev/ttyUSB2", "chip", "info", timeout=20)

        run.reset_mock()
        Lpac().profiles("/dev/ttyUSB2")
        run.assert_called_once_with("/dev/ttyUSB2", "profile", "list", timeout=45)

    @patch("lpac.subprocess.Popen")
    def test_translates_qmi_symbol_lookup_error(self, popen):
        popen.return_value = FakePopen(
            ["lpac"], returncode=127,
            stderr="lpac: symbol lookup error: undefined symbol: qmi_message_uim_logical_channel_output_get_result",
        )

        with self.assertRaisesRegex(EC20Error, "动态库不兼容"):
            Lpac.run("/dev/ttyUSB2", "chip", "info")

    @patch("lpac.subprocess.Popen")
    def test_timeout_reports_apdu_stage(self, popen):
        popen.return_value = FakePopen(
            ["lpac"], stdout="AT_DEBUG: AT+CGLA=1,10,\"80E2910006\"\n", timeout=True
        )

        with self.assertRaisesRegex(EC20Error, "eUICC APDU 无响应"):
            Lpac.run("/dev/ttyUSB2", "chip", "info", timeout=20)

    @patch("lpac.subprocess.Popen")
    def test_timeout_reports_apdu_stage_from_stderr(self, popen):
        popen.return_value = FakePopen(
            ["lpac"], stderr="AT_DEBUG: AT+CCHO=\"A0000005591010FFFFFFFF8900000100\"\n", timeout=True
        )

        with self.assertRaisesRegex(EC20Error, "打开 eUICC ISD-R 逻辑通道时无响应"):
            Lpac.run("/dev/ttyUSB2", "chip", "info", timeout=20)

    @patch("lpac.subprocess.Popen")
    def test_timeout_reports_current_lpac_debug_format(self, popen):
        popen.return_value = FakePopen(
            ["lpac"], stderr='AT_DEBUG_TX(1.2): AT+CGLA=1,10,"80E2910006"\n', timeout=True
        )

        with self.assertRaisesRegex(EC20Error, "eUICC APDU 无响应"):
            Lpac.run("/dev/ttyUSB2", "chip", "info", timeout=20)

    @patch("lpac.subprocess.Popen")
    def test_at_csim_enables_at_debug(self, popen):
        popen.return_value = FakePopen(
            ["lpac"], stdout=json.dumps({"payload": {"code": 0, "data": []}})
        )

        Lpac.run("/dev/ttyUSB2", "profile", "list", backend="at_csim")

        env = popen.call_args.kwargs["env"]
        self.assertEqual(env["LPAC_APDU"], "at_csim")
        self.assertEqual(env["LPAC_APDU_AT_DEBUG"], "true")

    @patch("lpac.subprocess.Popen")
    def test_streams_lpac_output_to_logger(self, popen):
        popen.return_value = FakePopen(
            ["lpac"],
            stdout='AT_DEBUG: AT+CGLA=1,10,"80E2910006"\n'
            + json.dumps({"payload": {"code": 0, "data": []}})
            + "\n",
        )
        messages = []
        Lpac.logger = lambda source, message, level: messages.append((source, message, level))

        Lpac.run("/dev/ttyUSB2", "profile", "list")

        self.assertIn(("lpac/stdout", 'AT_DEBUG: AT+CGLA=1,10,"80E2910006"', "DEBUG"), messages)


if __name__ == "__main__":
    unittest.main()
