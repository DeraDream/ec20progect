import sys
import unittest
from pathlib import Path
from unittest.mock import patch


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app" / "backend"))

from ec20 import EC20Error  # noqa: E402
import server  # noqa: E402


class ServerEsimTransportTest(unittest.TestCase):
    def setUp(self):
        self.capability = {"supported": True, "unsupported": [], "responses": {}}

    @patch.object(server.LPAC, "info")
    @patch.object(server, "ensure_esim_port_available")
    @patch.object(server.MODEM, "esim_capability")
    @patch.object(server.MODEM, "sibling_at_ports")
    @patch.object(server.MODEM, "qrtr_available", return_value=False)
    @patch.object(server.MODEM, "control_devices", return_value=[])
    @patch.object(server, "selected_device", return_value={"esim_backend": "AUTO"})
    @patch.object(server, "selected_port", return_value="/dev/ttyUSB2")
    def test_auto_at_selects_first_sibling_with_real_euicc_response(
        self,
        selected_port,
        selected_device,
        control_devices,
        qrtr_available,
        sibling_at_ports,
        esim_capability,
        ensure_available,
        info,
    ):
        sibling_at_ports.return_value = ["/dev/ttyUSB2", "/dev/ttyUSB0"]
        esim_capability.side_effect = [dict(self.capability), dict(self.capability)]
        info.side_effect = [EC20Error("超时"), {"eid": "123"}]

        port, capability, transport = server.selected_esim_transport()

        self.assertEqual(port, "/dev/ttyUSB0")
        self.assertEqual(capability["probe_info"], {"eid": "123"})
        self.assertEqual(capability["candidate_count"], 2)
        self.assertEqual(transport, {"backend": "at"})

    @patch.object(server.LPAC, "info", side_effect=EC20Error("超时"))
    @patch.object(server, "ensure_esim_port_available")
    @patch.object(server.MODEM, "esim_capability")
    @patch.object(server.MODEM, "sibling_at_ports", return_value=["/dev/ttyUSB2", "/dev/ttyUSB0"])
    @patch.object(server.MODEM, "qrtr_available", return_value=False)
    @patch.object(server.MODEM, "control_devices", return_value=[])
    @patch.object(server, "selected_device", return_value={"esim_backend": "AT"})
    @patch.object(server, "selected_port", return_value="/dev/ttyUSB2")
    def test_at_reports_each_failed_sibling(
        self,
        selected_port,
        selected_device,
        control_devices,
        qrtr_available,
        sibling_at_ports,
        esim_capability,
        ensure_available,
        info,
    ):
        esim_capability.side_effect = [dict(self.capability), dict(self.capability)]

        with self.assertRaisesRegex(EC20Error, "ttyUSB2: 超时.*ttyUSB0: 超时"):
            server.selected_esim_transport()

    @patch.object(server.LPAC, "profiles", side_effect=EC20Error("Profile 超时"))
    @patch.object(server, "ensure_esim_port_available")
    @patch.object(
        server,
        "selected_esim_transport",
        return_value=(
            "/dev/ttyUSB0",
            {"supported": True, "backend": "at", "probe_info": {"eid": "123"}},
            {"backend": "at"},
        ),
    )
    def test_read_esim_keeps_chip_info_when_profiles_fail(self, selected_transport, ensure_available, profiles):
        result = server.read_esim()

        self.assertEqual(result["info"], {"eid": "123"})
        self.assertEqual(result["profiles"], [])
        self.assertEqual(result["profiles_error"], "Profile 超时")
        self.assertNotIn("probe_info", result["capability"])
        profiles.assert_called_once_with("/dev/ttyUSB0", timeout=10, backend="at")


if __name__ == "__main__":
    unittest.main()
