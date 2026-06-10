import sys
import unittest
from pathlib import Path
from unittest.mock import call, patch


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app" / "backend"))

from ec20 import EC20Error  # noqa: E402
import server  # noqa: E402


class ServerEsimTransportTest(unittest.TestCase):
    def setUp(self):
        self.capability = {"supported": True, "unsupported": [], "responses": {}}
        server.RUNTIME_LOG.path = None
        server.ESIM_AT_BACKENDS.clear()

    def test_ordered_esim_ports_prefers_ttyusb3_over_status_port(self):
        ports = server.ordered_esim_ports(
            ["/dev/ttyUSB2", "/dev/ttyUSB0", "/dev/ttyUSB3", "/dev/ttyUSB1"],
            status_port="/dev/ttyUSB2",
        )

        self.assertEqual(ports, ["/dev/ttyUSB3", "/dev/ttyUSB2", "/dev/ttyUSB0", "/dev/ttyUSB1"])

    def test_ordered_esim_ports_prefers_explicit_configuration(self):
        ports = server.ordered_esim_ports(
            ["/dev/ttyUSB2", "/dev/ttyUSB3", "/dev/ttyUSB1"],
            configured_port="/dev/ttyUSB1",
            status_port="/dev/ttyUSB2",
        )

        self.assertEqual(ports, ["/dev/ttyUSB1", "/dev/ttyUSB3", "/dev/ttyUSB2"])

    @patch.object(server.MODEM, "sibling_at_ports", return_value=["/dev/ttyUSB2", "/dev/ttyUSB3"])
    def test_default_esim_port_uses_ttyusb3(self, sibling_at_ports):
        self.assertEqual(server.default_esim_port("/dev/ttyUSB2"), "/dev/ttyUSB3")

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
        self.assertEqual(capability["at_candidates"], ["/dev/ttyUSB2", "/dev/ttyUSB0"])
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

        with self.assertRaisesRegex(EC20Error, "ttyUSB2/at: 超时.*ttyUSB0/at: 超时"):
            server.selected_esim_transport()

    @patch.object(server.LPAC, "info")
    @patch.object(server, "ensure_esim_port_available")
    @patch.object(server.MODEM, "esim_capability")
    @patch.object(server.MODEM, "sibling_at_ports", return_value=["/dev/ttyUSB2", "/dev/ttyUSB0"])
    @patch.object(server.MODEM, "qrtr_available", return_value=False)
    @patch.object(server.MODEM, "control_devices", return_value=[])
    @patch.object(server, "selected_device", return_value={"esim_backend": "AUTO"})
    @patch.object(server, "selected_port", return_value="/dev/ttyUSB2")
    def test_auto_at_rejects_chip_info_without_eid(
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
        info.side_effect = [{}, {"eidValue": "123"}]

        port, capability, transport = server.selected_esim_transport()

        self.assertEqual(port, "/dev/ttyUSB0")
        self.assertEqual(capability["probe_info"], {"eidValue": "123"})
        self.assertEqual(transport, {"backend": "at"})

    @patch.object(server.LPAC, "info")
    @patch.object(server, "ensure_esim_port_available")
    @patch.object(server.MODEM, "esim_capability")
    @patch.object(server.MODEM, "sibling_at_ports", return_value=["/dev/ttyUSB2"])
    @patch.object(server.MODEM, "qrtr_available", return_value=False)
    @patch.object(server.MODEM, "control_devices", return_value=[])
    @patch.object(server, "selected_device", return_value={"esim_backend": "AUTO"})
    @patch.object(server, "selected_port", return_value="/dev/ttyUSB2")
    def test_auto_at_retries_chip_info_with_csim(
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
        capability = dict(self.capability)
        capability["backend"] = "at"
        capability["responses"] = {"AT+CSIM=?": "OK"}
        esim_capability.return_value = capability
        info.side_effect = [{}, {"eidValue": "123"}]

        port, result, transport = server.selected_esim_transport()

        self.assertEqual(port, "/dev/ttyUSB2")
        self.assertEqual(result["backend"], "at_csim")
        self.assertEqual(transport, {"backend": "at_csim"})
        self.assertEqual(server.remembered_at_backend("/dev/ttyUSB2"), "at_csim")

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
        self.assertRegex(result["profiles_error"], "ttyUSB0: Profile 超时.*ttyUSB0/CSIM: Profile 超时")
        self.assertNotIn("probe_info", result["capability"])
        self.assertEqual(
            profiles.call_args_list,
            [
                call("/dev/ttyUSB0", timeout=45, backend="at"),
                call("/dev/ttyUSB0", timeout=30, backend="at_csim"),
            ],
        )

    @patch.object(server.LPAC, "profiles", return_value=[])
    @patch.object(
        server,
        "selected_esim_transport",
        return_value=(
            "/dev/ttyUSB2",
            {"supported": True, "backend": "qmi", "probe_info": {"eid": "123"}},
            {"backend": "qmi", "control_device": "/dev/cdc-wdm0"},
        ),
    )
    def test_read_esim_keeps_short_profile_timeout_for_qmi(self, selected_transport, profiles):
        result = server.read_esim()

        self.assertEqual(result["profiles"], [])
        profiles.assert_called_once_with(
            "/dev/ttyUSB2",
            timeout=20,
            backend="qmi",
            control_device="/dev/cdc-wdm0",
        )

    @patch.object(server.LPAC, "profiles")
    @patch.object(server, "ensure_esim_port_available")
    @patch.object(server.MODEM, "same_port", side_effect=lambda first, second: first == second)
    @patch.object(
        server,
        "selected_esim_transport",
        return_value=(
            "/dev/ttyUSB2",
            {
                "supported": True,
                "backend": "at",
                "probe_info": {"eid": "123"},
                "at_candidates": ["/dev/ttyUSB2", "/dev/ttyUSB0"],
            },
            {"backend": "at"},
        ),
    )
    def test_read_esim_retries_profile_on_sibling_at_port(
        self, selected_transport, same_port, ensure_available, profiles
    ):
        profiles.side_effect = [EC20Error("主端口超时"), EC20Error("CSIM 超时"), [{"iccid": "8986"}]]

        result = server.read_esim()

        self.assertEqual(result["profiles"], [{"iccid": "8986"}])
        self.assertEqual(result["profiles_error"], "")
        self.assertEqual(result["port"], "/dev/ttyUSB0")
        self.assertEqual(result["capability"]["profile_fallback_port"], "/dev/ttyUSB0")
        self.assertEqual(
            profiles.call_args_list,
            [
                call("/dev/ttyUSB2", timeout=45, backend="at"),
                call("/dev/ttyUSB2", timeout=30, backend="at_csim"),
                call("/dev/ttyUSB0", timeout=30, backend="at"),
            ],
        )

    @patch.object(server.LPAC, "profiles")
    @patch.object(server.MODEM, "same_port", side_effect=lambda first, second: first == second)
    def test_profile_retry_uses_and_remembers_csim_backend(self, same_port, profiles):
        profiles.return_value = [{"iccid": "8986"}]

        result = server.retry_profiles_on_at_candidates(
            "/dev/ttyUSB2",
            {"at_candidates": ["/dev/ttyUSB2"]},
            {"backend": "at"},
            EC20Error("CGLA 超时"),
        )

        self.assertEqual(result[0], [{"iccid": "8986"}])
        self.assertEqual(server.remembered_at_backend("/dev/ttyUSB2"), "at_csim")
        profiles.assert_called_once_with("/dev/ttyUSB2", timeout=30, backend="at_csim")

    @patch.object(server.LPAC, "profiles")
    @patch.object(server, "ensure_esim_port_available")
    @patch.object(server.MODEM, "same_port", side_effect=lambda first, second: first == second)
    def test_profile_retry_reports_each_failed_at_port(self, same_port, ensure_available, profiles):
        profiles.side_effect = EC20Error("备用端口超时")

        result = server.retry_profiles_on_at_candidates(
            "/dev/ttyUSB2",
            {"at_candidates": ["/dev/ttyUSB2", "/dev/ttyUSB0"]},
            {"backend": "at"},
            EC20Error("主端口超时"),
        )

        self.assertEqual(result[0], [])
        self.assertRegex(result[2], "ttyUSB2: 主端口超时.*ttyUSB0: 备用端口超时")


if __name__ == "__main__":
    unittest.main()
