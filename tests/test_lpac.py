import json
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


if __name__ == "__main__":
    unittest.main()
