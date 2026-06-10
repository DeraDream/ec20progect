import sys
import unittest
from pathlib import Path
from unittest.mock import patch


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app" / "backend"))

from ec20 import EC20Modem  # noqa: E402


class EC20ModemTest(unittest.TestCase):
    def test_status_value_parsers(self):
        modem = EC20Modem()

        self.assertEqual(modem._operator('+COPS: 0,2,"46001",7\nOK'), "46001")
        self.assertEqual(modem._network_mode('+QNWINFO: "FDD LTE","46001","LTE BAND 1",100\nOK'), "FDD LTE · LTE BAND 1")
        self.assertEqual(modem._registration("+CREG: 0,5\nOK"), "已注册（漫游）")
        self.assertEqual(modem._sim_state("+CPIN: READY\nOK"), "就绪")
        self.assertEqual(modem._value("EC20CEFHLGR06A03M1G\nOK"), "EC20CEFHLGR06A03M1G")

    @patch.object(EC20Modem, "esim_capability")
    @patch.object(EC20Modem, "command")
    @patch.object(EC20Modem, "at_ports")
    def test_find_esim_port_uses_compatible_port_for_same_imei(self, at_ports, command, capability):
        modem = EC20Modem()
        at_ports.return_value = ["/dev/ttyUSB0", "/dev/ttyUSB2"]
        command.return_value = "867394046880703\nOK"
        capability.side_effect = [
            {"supported": False, "unsupported": ["AT+CCHO=?"], "responses": {}},
            {"supported": True, "unsupported": [], "responses": {}},
        ]

        port, result = modem.find_esim_port("/dev/ttyUSB0")

        self.assertEqual(port, "/dev/ttyUSB2")
        self.assertTrue(result["supported"])


if __name__ == "__main__":
    unittest.main()
