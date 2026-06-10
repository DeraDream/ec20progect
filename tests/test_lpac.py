import json
import subprocess
import sys
import unittest
from pathlib import Path
from subprocess import CompletedProcess
from unittest.mock import patch


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app" / "backend"))

from ec20 import EC20Error  # noqa: E402
from lpac import Lpac  # noqa: E402


class LpacTest(unittest.TestCase):
    @patch("lpac.subprocess.run")
    def test_returns_payload_data(self, run):
        run.return_value = CompletedProcess(
            ["lpac"],
            0,
            stdout=json.dumps({"payload": {"code": 0, "data": {"eid": "123"}}}),
            stderr="",
        )

        self.assertEqual(Lpac.run("/dev/ttyUSB2", "chip", "info"), {"eid": "123"})
        env = run.call_args.kwargs["env"]
        self.assertEqual(env["LPAC_APDU"], "at")
        self.assertEqual(env["LPAC_APDU_AT_DEVICE"], "/dev/ttyUSB2")

    @patch("lpac.subprocess.run")
    def test_qmi_uses_separate_binary_and_transport(self, run):
        run.return_value = CompletedProcess(
            ["lpac-qmi"],
            0,
            stdout=json.dumps({"payload": {"code": 0, "data": []}}),
            stderr="",
        )

        Lpac.run("/dev/ttyUSB2", "profile", "list", backend="qmi", control_device="/dev/cdc-wdm0")

        self.assertEqual(run.call_args.args[0][0], "lpac-qmi")
        env = run.call_args.kwargs["env"]
        self.assertEqual(env["LPAC_APDU"], "qmi")
        self.assertEqual(env["LPAC_APDU_QMI_DEVICE"], "/dev/cdc-wdm0")
        self.assertEqual(env["LPAC_APDU_QMI_UIM_SLOT"], "1")

    @patch("lpac.Lpac.run")
    def test_read_operations_use_short_timeout(self, run):
        Lpac().info("/dev/ttyUSB2")
        run.assert_called_once_with("/dev/ttyUSB2", "chip", "info", timeout=20)

        run.reset_mock()
        Lpac().profiles("/dev/ttyUSB2")
        run.assert_called_once_with("/dev/ttyUSB2", "profile", "list", timeout=20)

    @patch("lpac.subprocess.run")
    def test_translates_qmi_symbol_lookup_error(self, run):
        run.return_value = CompletedProcess(
            ["lpac"],
            127,
            stdout="",
            stderr="lpac: symbol lookup error: undefined symbol: qmi_message_uim_logical_channel_output_get_result",
        )

        with self.assertRaisesRegex(EC20Error, "动态库不兼容"):
            Lpac.run("/dev/ttyUSB2", "chip", "info")

    @patch("lpac.subprocess.run")
    def test_timeout_reports_apdu_stage(self, run):
        run.side_effect = subprocess.TimeoutExpired(
            ["lpac"],
            20,
            output="AT_DEBUG: AT+CGLA=1,10,\"80E2910006\"\n",
        )

        with self.assertRaisesRegex(EC20Error, "eUICC APDU 无响应"):
            Lpac.run("/dev/ttyUSB2", "chip", "info", timeout=20)


if __name__ == "__main__":
    unittest.main()
