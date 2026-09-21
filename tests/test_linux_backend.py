from __future__ import annotations

import unittest
import os
from unittest.mock import MagicMock, patch

from TitanArmyControl import linux_backend as backend
from TitanArmyControl import hdr_helper


class LinuxBackendTests(unittest.TestCase):
    def test_tray_exit_command_calls_exit_callback(self):
        tray = backend.TrayIcon.__new__(backend.TrayIcon)
        tray.process = MagicMock()
        tray.process.poll.return_value = None
        tray.process.stdout.readline.return_value = "EXIT\n"
        tray.root = MagicMock()
        tray.exit_callback = MagicMock()
        with patch.object(backend.select, "select", return_value=([tray.process.stdout], [], [])):
            tray._poll_commands()
        tray.exit_callback.assert_called_once_with()

    def test_packets_match_captured_ddc_exchange(self):
        self.assertEqual(
            backend.set_vcp_packet(0x99, 6),
            bytes.fromhex("51 84 03 99 00 06 27"),
        )
        self.assertEqual(
            backend.set_vcp_packet(0x47, 6),
            bytes.fromhex("51 84 03 47 00 06 f9"),
        )

    def test_detect_uses_drm_connector_and_bus(self):
        output = """Display 1
   I2C bus:  /dev/i2c-7
   DRM_connector:           card1-DP-2
   EDID synopsis:
      Mfg id:               LHC - Beihai Century Joint Innovation Technology Co.,Ltd
      Model:                P275MS PLUS+
"""
        with patch.object(backend.shutil, "which", return_value="/usr/bin/ddcutil"), \
             patch.object(backend.subprocess, "run") as run:
            run.return_value.returncode = 0
            run.return_value.stdout = output
            self.assertEqual(
                backend.display_choices(),
                [("card1-DP-2", "7", "card1-DP-2: P275MS PLUS+ (LHC)")],
            )

    def test_profile_writes_local_brightness_and_halo_in_order(self):
        writes = []
        fake_device = MagicMock()
        fake_device.__enter__.return_value.fileno.return_value = 17
        with patch.object(backend, "display_choices", return_value=[("card1-DP-2", "7", "Monitor")]), \
             patch.object(backend, "set_linux_hdr") as hdr, \
             patch.object(backend, "write_packet", side_effect=lambda _fd, packet: writes.append(packet)), \
             patch.object(backend.fcntl, "flock"), \
             patch.object(backend.time, "sleep"), \
             patch("builtins.open", return_value=fake_device):
            backend.apply_monitor_profile("High", 80, 100, False, "card1-DP-2")
        hdr.assert_called_once_with(False, "card1-DP-2")
        self.assertEqual(
            [(packet[3], int.from_bytes(packet[4:6], "big")) for packet in writes],
            [(0x99, 6), (0x47, 6), (0x10, 80), (0x99, 100), (0x46, 100)],
        )

    def test_hdr_targets_selected_gnome_connector(self):
        with patch.dict(os.environ, {"XDG_CURRENT_DESKTOP": "ubuntu:GNOME"}), \
             patch.object(backend.subprocess, "run") as run:
            run.return_value.returncode = 0
            run.return_value.stdout = "CHANGED\n"
            backend.set_linux_hdr(True, "card1-DP-2")
        self.assertEqual(run.call_args.args[0][-2:], ["DP-2", "on"])

    def test_hdr_keeps_other_monitors_and_layout(self):
        mode = lambda name: (name, 0, 0, 0, 0, [], {"is-current": True})
        monitors = [
            (("DP-2", "LHC", "P275MS PLUS+", ""), [mode("mode-a")], {"color-mode": 0, "supported-color-modes": [0, 1]}),
            (("HDMI-1", "DEL", "Other", ""), [mode("mode-b")], {"color-mode": 0, "rgb-range": 2}),
        ]
        logical = [
            (0, 0, 1.0, 0, True, [("DP-2", "LHC", "P275MS PLUS+", "")], {}),
            (2560, 0, 1.0, 0, False, [("HDMI-1", "DEL", "Other", "")], {}),
        ]
        serial, result, _properties, changed = hdr_helper.current_configuration(
            (42, monitors, logical, {}), "DP-2", True
        )
        self.assertTrue(changed)
        self.assertEqual(serial, 42)
        self.assertEqual(result[0][-1], [("DP-2", "mode-a", {"color-mode": 1})])
        self.assertEqual(result[1], (2560, 0, 1.0, 0, False, [("HDMI-1", "mode-b", {"color-mode": 0, "rgb-range": 2})]))

    def test_gnome_hotkey_uses_accelerator_and_preserves_existing_shortcuts(self):
        calls = []
        def gsettings(*args):
            calls.append(args)
            return "['/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/custom0/']" if args[0] == "get" else ""
        with patch.dict(os.environ, {"XDG_CURRENT_DESKTOP": "ubuntu:GNOME"}), \
             patch.object(backend.shutil, "which", return_value="/usr/bin/gsettings"), \
             patch.object(backend, "_gsettings", side_effect=gsettings):
            backend.HotkeyManager(MagicMock(), MagicMock()).start([
                {"name": "HDR", "hotkey": "Ctrl+Alt+3"},
            ])
        self.assertIn("<Control><Alt>3", calls[3])
        self.assertIn("custom0/", calls[-1][-1])
        self.assertIn("titanarmy0/", calls[-1][-1])


if __name__ == "__main__":
    unittest.main()
