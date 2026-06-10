import sys
import unittest
from pathlib import Path
from unittest.mock import patch


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app" / "backend"))

from ec20 import EC20Modem  # noqa: E402


class EC20ModemTest(unittest.TestCase):
    def test_status_value_parsers(self):
        modem = EC20Modem()

        self.assertEqual(modem._operator('+COPS: 0,2,"46001",7\nOK'), "中国联通")
        self.assertEqual(modem._operator('+COPS: 0,0,"CHN-UNICOM",7\nOK'), "中国联通")
        self.assertEqual(modem._network_mode('+QNWINFO: "FDD LTE","46001","LTE BAND 1",100\nOK'), "FDD LTE · LTE BAND 1")
        self.assertEqual(modem._registration("+CREG: 0,5\nOK"), "已注册（漫游）")
        self.assertEqual(modem._sim_state("+CPIN: READY\nOK"), "就绪")
        self.assertEqual(modem._number('+CNUM: ,"13800138000",129\nOK'), "13800138000")
        self.assertEqual(modem._number("OK"), "")
        self.assertEqual(
            modem._signal("+CSQ: 28,99\nOK"),
            {"signal_percent": 90, "signal_dbm": -57, "signal_quality": "优秀"},
        )
        self.assertEqual(modem._value("EC20CEFHLGR06A03M1G\nOK"), "EC20CEFHLGR06A03M1G")

    @patch("ec20.glob.glob")
    def test_control_devices(self, glob):
        glob.side_effect = [["/dev/cdc-wdm0"], [], []]
        self.assertEqual(EC20Modem.control_devices(), ["/dev/cdc-wdm0"])

    @patch("ec20.os.path.exists")
    def test_qrtr_available(self, exists):
        exists.side_effect = lambda path: path == "/sys/class/qrtr"
        self.assertTrue(EC20Modem.qrtr_available())

    @patch.object(EC20Modem, "esim_capability")
    @patch.object(EC20Modem, "sibling_at_ports")
    def test_find_esim_port_uses_compatible_sibling_port(self, sibling_at_ports, capability):
        modem = EC20Modem()
        sibling_at_ports.return_value = ["/dev/ttyUSB0", "/dev/ttyUSB2"]
        capability.side_effect = [
            {"supported": False, "unsupported": ["AT+CCHO=?"], "responses": {}},
            {"supported": True, "unsupported": [], "responses": {}},
        ]

        port, result = modem.find_esim_port("/dev/ttyUSB0")

        self.assertEqual(port, "/dev/ttyUSB2")
        self.assertTrue(result["supported"])

    @patch.object(EC20Modem, "command")
    def test_esim_capability_accepts_csim_only_port(self, command):
        command.side_effect = ["ERROR", "ERROR", "ERROR", "OK"]

        result = EC20Modem().esim_capability("/dev/ttyUSB0")

        self.assertTrue(result["supported"])
        self.assertEqual(result["backend"], "at_csim")

    @patch.object(EC20Modem, "ports")
    @patch.object(EC20Modem, "at_ports")
    @patch.object(EC20Modem, "usb_device_path")
    def test_sibling_at_ports_groups_ports_by_physical_usb_device(self, usb_device_path, at_ports, ports):
        modem = EC20Modem()
        at_ports.return_value = ["/dev/ttyUSB2", "/dev/ttyUSB4"]
        ports.return_value = ["/dev/ttyUSB0", "/dev/ttyUSB2", "/dev/ttyUSB4"]
        usb_device_path.side_effect = {
            "/dev/ttyUSB0": "/sys/devices/usb1/1-8",
            "/dev/ttyUSB2": "/sys/devices/usb1/1-8",
            "/dev/ttyUSB4": "/sys/devices/usb1/1-9",
        }.get

        self.assertEqual(modem.sibling_at_ports("/dev/ttyUSB2"), ["/dev/ttyUSB2", "/dev/ttyUSB0"])

    @patch.object(EC20Modem, "usb_path")
    def test_usb_device_path_returns_parent_before_interface(self, usb_path):
        usb_path.return_value = "/sys/devices/pci/usb1/1-8/1-8:1.2/ttyUSB2"

        self.assertEqual(EC20Modem.usb_device_path("/dev/ttyUSB2"), "/sys/devices/pci/usb1/1-8")

    @patch("ec20.os.path.exists")
    @patch.object(EC20Modem, "usb_path")
    def test_usb_device_path_uses_usb_identity_files(self, usb_path, exists):
        usb_path.return_value = "/sys/devices/pci/usb1/1-8/1-8:1.10/ttyUSB2"
        exists.side_effect = lambda path: path in (
            "/sys/devices/pci/usb1/1-8/idVendor",
            "/sys/devices/pci/usb1/1-8/idProduct",
        )

        self.assertEqual(EC20Modem.usb_device_path("/dev/ttyUSB2"), "/sys/devices/pci/usb1/1-8")

    @patch("ec20.glob.glob")
    @patch("ec20.os.path.realpath")
    @patch("ec20.os.path.isdir")
    @patch("ec20.os.getpid")
    def test_port_holders_reports_other_process(self, getpid, isdir, realpath, glob):
        getpid.return_value = 100
        isdir.return_value = True
        glob.side_effect = [["/proc/200"], ["/proc/200/fd/3"]]
        realpath.side_effect = lambda value: "/dev/ttyUSB2" if value in ("/dev/ttyUSB2", "/proc/200/fd/3") else value

        with patch("ec20.Path.read_text", return_value="vohive\n"):
            self.assertEqual(
                EC20Modem.port_holders("/dev/ttyUSB2"),
                [{"pid": 200, "name": "vohive"}],
            )


if __name__ == "__main__":
    unittest.main()
