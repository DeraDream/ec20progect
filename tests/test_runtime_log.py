import unittest
from unittest.mock import mock_open, patch

from app.backend.runtime_log import RuntimeLog


class RuntimeLogTest(unittest.TestCase):
    def test_writes_snapshot_file_and_wait_entries(self):
        output = mock_open()
        log = RuntimeLog("runtime.log", max_lines=2)
        with patch("app.backend.runtime_log.Path.mkdir"), patch(
            "app.backend.runtime_log.Path.exists", return_value=False
        ), patch("app.backend.runtime_log.Path.open", output):
            log.write("test", "first")
            sequence = log.latest_sequence()
            log.write("test", "second")
            log.write("test", "third")

        self.assertEqual(len(log.snapshot()), 2)
        self.assertTrue(log.snapshot()[-1].endswith("[test] third"))
        self.assertEqual(len(log.wait(sequence, timeout=0)), 2)
        self.assertIn("[test] first\n", output().write.call_args_list[0].args[0])


if __name__ == "__main__":
    unittest.main()
