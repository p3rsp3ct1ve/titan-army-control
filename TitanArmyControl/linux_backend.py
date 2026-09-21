"""Linux monitor and GNOME integration for Titan Army Control."""

from __future__ import annotations

import ast
import ctypes
import fcntl
import json
import os
import pathlib
import re
import select
import socket
import shlex
import shutil
import subprocess
import sys
import time
import tkinter as tk


APP_NAME = "Titan Army Control"
LOCAL_DIMMING = {"Off": 2, "Low": 3, "Medium": 5, "High": 6}
I2C_RDWR = 0x0707
DDC_ADDRESS = 0x37
SOURCE_ADDRESS = 0x51
CHECKSUM_SEED = 0x6E
AUTOSTART_PATH = pathlib.Path.home() / ".config/autostart/TitanArmyControl.desktop"
HOTKEY_ROOT = "/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/"
HOTKEY_SCHEMA = "org.gnome.settings-daemon.plugins.media-keys.custom-keybinding"
_instance_file = None
_instance_socket = None
_instance_socket_path = None


class I2CMessage(ctypes.Structure):
    _fields_ = [
        ("addr", ctypes.c_uint16),
        ("flags", ctypes.c_uint16),
        ("len", ctypes.c_uint16),
        ("buf", ctypes.POINTER(ctypes.c_uint8)),
    ]


class I2CTransfer(ctypes.Structure):
    _fields_ = [("msgs", ctypes.POINTER(I2CMessage)), ("nmsgs", ctypes.c_uint32)]


def set_vcp_packet(code: int, value: int) -> bytes:
    if not 0 <= code <= 255 or not 0 <= value <= 65535:
        raise ValueError("VCP code or value out of range")
    packet = bytes((SOURCE_ADDRESS, 0x84, 0x03, code, value >> 8, value & 0xFF))
    checksum = CHECKSUM_SEED
    for byte in packet:
        checksum ^= byte
    return packet + bytes((checksum,))


def write_packet(fd: int, packet: bytes) -> None:
    buffer = (ctypes.c_uint8 * len(packet)).from_buffer_copy(packet)
    message = I2CMessage(DDC_ADDRESS, 0, len(packet), buffer)
    transfer = I2CTransfer(ctypes.pointer(message), 1)
    libc = ctypes.CDLL(None, use_errno=True)
    result = libc.ioctl(fd, I2C_RDWR, ctypes.byref(transfer))
    if result != 1:
        error = ctypes.get_errno()
        raise OSError(error, os.strerror(error))


def set_vcp_pair(fd: int, code: int, value: int) -> None:
    write_packet(fd, set_vcp_packet(0x99, value))
    time.sleep(0.065)
    write_packet(fd, set_vcp_packet(code, value))


def display_choices() -> list[tuple[str, str, str]]:
    if not shutil.which("ddcutil"):
        raise RuntimeError("Install ddcutil to discover monitors")
    result = subprocess.run(
        ["ddcutil", "detect"], capture_output=True, text=True, timeout=25, check=False
    )
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip() or "ddcutil detect failed")
    choices = []
    for block in re.split(r"(?=^Display\s+\d+\s*$)", result.stdout, flags=re.MULTILINE):
        bus = re.search(r"I2C bus:\s*/dev/i2c-(\d+)", block)
        connector = re.search(r"DRM[_ ]connector:\s*(\S+)", block, re.IGNORECASE)
        model = re.search(r"Model:\s*(.+)", block)
        mfg = re.search(r"Mfg id:\s*(\S+)", block)
        if not bus:
            continue
        identity = connector.group(1) if connector else f"i2c-{bus.group(1)}"
        label = f"{identity}: {(model.group(1).strip() if model else 'Monitor')}"
        if mfg:
            label += f" ({mfg.group(1)})"
        choices.append((identity, bus.group(1), label))
    return choices


def _gnome_connector(identity: str) -> str:
    match = re.fullmatch(r"card\d+-(.+)", identity)
    if not match:
        raise RuntimeError("HDR requires a monitor with a DRM connector name")
    return match.group(1)


def set_linux_hdr(enabled: bool, identity: str) -> bool:
    if "GNOME" not in os.environ.get("XDG_CURRENT_DESKTOP", "").upper():
        raise RuntimeError("HDR switching currently requires GNOME Wayland")
    connector = _gnome_connector(identity)
    helper = pathlib.Path(__file__).resolve().with_name("hdr_helper.py")
    if getattr(sys, "frozen", False):
        helper = pathlib.Path(sys._MEIPASS) / "TitanArmyControl/hdr_helper.py"
    result = subprocess.run(
        ["/usr/bin/python3", str(helper), connector, "on" if enabled else "off"],
        capture_output=True, text=True, timeout=20, check=False,
    )
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip() or "GNOME HDR switch failed")
    return result.stdout.strip() == "CHANGED"


def apply_monitor_profile(local_dimming: str, brightness: int, halo: int, hdr: bool,
                          selected_path: str | None = None) -> None:
    choices = display_choices()
    if selected_path is None:
        if len(choices) != 1:
            raise RuntimeError("Select a monitor in the application first")
        selected_path = choices[0][0]
    bus = next((item[1] for item in choices if item[0] == selected_path), None)
    if bus is None:
        raise RuntimeError("The selected monitor is disconnected; select it again")
    if local_dimming not in LOCAL_DIMMING or not 0 <= brightness <= 100 or not 0 <= halo <= 100:
        raise ValueError("Invalid profile values")

    runtime = pathlib.Path(os.environ.get("XDG_RUNTIME_DIR", "/tmp"))
    lock_path = runtime / f"titan-army-i2c-{bus}-{os.getuid()}.lock"
    with open(lock_path, "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        changed = set_linux_hdr(hdr, selected_path)
        if changed:
            time.sleep(0.8)
        path = f"/dev/i2c-{bus}"
        try:
            with open(path, "rb+", buffering=0) as device:
                fd = device.fileno()
                set_vcp_pair(fd, 0x47, LOCAL_DIMMING[local_dimming])
                if not hdr:
                    time.sleep(0.08)
                    write_packet(fd, set_vcp_packet(0x10, brightness))
                    time.sleep(0.08)
                    set_vcp_pair(fd, 0x46, halo)
        except PermissionError as error:
            raise PermissionError(f"No access to {path}; add your user to the i2c group and log in again") from error


def _launcher_parts(minimized: bool = False) -> list[str]:
    if getattr(sys, "frozen", False):
        parts = [str(pathlib.Path(sys.executable).resolve())]
    else:
        entry = pathlib.Path(__file__).resolve().parent.parent / "run_app.py"
        parts = [str(pathlib.Path(sys.executable).resolve()), str(entry)]
    if minimized:
        parts.append("--minimized")
    return parts


def _launcher_command(minimized: bool = False) -> str:
    return " ".join(shlex.quote(part) for part in _launcher_parts(minimized))


def _desktop_command(minimized: bool = False) -> str:
    def quote(part: str) -> str:
        return '"' + part.replace('\\', '\\\\').replace('"', '\\"') + '"'
    return " ".join(quote(part) for part in _launcher_parts(minimized))


def read_autostart_mode() -> str:
    try:
        data = AUTOSTART_PATH.read_text(encoding="utf-8")
    except FileNotFoundError:
        return "off"
    return "tray" if "--minimized" in data else "window"


def write_autostart_mode(mode: str) -> None:
    if mode == "off":
        AUTOSTART_PATH.unlink(missing_ok=True)
        return
    if mode not in {"window", "tray"}:
        raise ValueError("Invalid autostart mode")
    AUTOSTART_PATH.parent.mkdir(parents=True, exist_ok=True)
    command = _desktop_command(minimized=mode == "tray")
    AUTOSTART_PATH.write_text(
        f"[Desktop Entry]\nType=Application\nName={APP_NAME}\nExec={command}\n"
        "Terminal=false\nX-GNOME-Autostart-enabled=true\n",
        encoding="utf-8",
    )


def _gsettings(*args: str) -> str:
    result = subprocess.run(["gsettings", *args], capture_output=True, text=True, timeout=8, check=False)
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or "gsettings failed")
    return result.stdout.strip()


class HotkeyManager:
    """GNOME custom shortcuts run the same packaged app in profile mode."""

    def __init__(self, root: tk.Tk, callback):
        self.root = root
        self.callback = callback

    def start(self, profiles: list[dict]) -> None:
        if "GNOME" not in os.environ.get("XDG_CURRENT_DESKTOP", "").upper():
            raise ValueError("Global hotkeys currently require GNOME")
        if not shutil.which("gsettings"):
            raise ValueError("gsettings is required for global hotkeys")
        existing = _gsettings("get", "org.gnome.settings-daemon.plugins.media-keys", "custom-keybindings")
        paths = ast.literal_eval(existing) if existing != "@as []" else []
        own = [f"{HOTKEY_ROOT}titanarmy{i}/" for i in range(len(profiles))]
        retained = [path for path in paths if not path.startswith(f"{HOTKEY_ROOT}titanarmy")]
        command = _launcher_command()
        for index, profile in enumerate(profiles):
            schema = f"{HOTKEY_SCHEMA}:{own[index]}"
            binding = profile.get("hotkey", "")
            match = re.fullmatch(r"Ctrl\+Alt\+([0-9])", binding, re.IGNORECASE)
            if not match:
                raise ValueError(f"Unsupported GNOME hotkey: {binding}")
            _gsettings("set", schema, "name", f"Titan Army: {profile['name']}")
            _gsettings("set", schema, "command", f"{command} --apply-profile {index}")
            _gsettings("set", schema, "binding", f"<Control><Alt>{match.group(1)}")
        serialized = "[" + ", ".join(repr(path) for path in retained + own) + "]"
        _gsettings("set", "org.gnome.settings-daemon.plugins.media-keys", "custom-keybindings", serialized)

    def stop(self) -> None:
        pass


class TrayIcon:
    def __init__(self, root: tk.Tk, icon_path: pathlib.Path, open_label: str,
                 exit_label: str, open_callback, exit_callback):
        helper = pathlib.Path(__file__).resolve().with_name("tray_helper.py")
        if getattr(sys, "frozen", False):
            helper = pathlib.Path(sys._MEIPASS) / "TitanArmyControl/tray_helper.py"
        if not helper.is_file():
            raise RuntimeError("Linux tray helper is missing")
        self.root = root
        self.open_callback = open_callback
        self.exit_callback = exit_callback
        self.process = subprocess.Popen(
            ["/usr/bin/python3", str(helper), str(icon_path), open_label, exit_label],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, bufsize=1,
        )
        readable, _, _ = select.select([self.process.stdout], [], [], 5)
        if not readable:
            self.process.terminate()
            raise RuntimeError("GTK AppIndicator did not start within 5 seconds")
        ready = self.process.stdout.readline().strip()
        if ready != "READY":
            error = self.process.stderr.read().strip()
            if "AyatanaAppIndicator3" in error and "not available" in error.lower():
                raise RuntimeError(
                    "Для значка в трее установите пакет: "
                    "sudo apt install gir1.2-ayatanaappindicator3-0.1"
                )
            raise RuntimeError(error or "GTK AppIndicator could not start")
        self.root.after(100, self._poll_commands)

    def _poll_commands(self) -> None:
        if self.process.poll() is not None:
            return
        while select.select([self.process.stdout], [], [], 0)[0]:
            command = self.process.stdout.readline().strip()
            if command == "OPEN":
                self.open_callback()
            elif command == "EXIT":
                self.exit_callback()
                return
        self.root.after(100, self._poll_commands)

    def set_labels(self, open_label: str, exit_label: str) -> None:
        if self.process.poll() is None and self.process.stdin:
            self.process.stdin.write(json.dumps({
                "type": "labels", "open": open_label, "exit": exit_label,
            }) + "\n")
            self.process.stdin.flush()

    def stop(self) -> None:
        if self.process.poll() is None and self.process.stdin:
            try:
                self.process.stdin.write('{"type":"quit"}\n')
                self.process.stdin.flush()
                self.process.wait(timeout=2)
            except (OSError, subprocess.TimeoutExpired):
                self.process.terminate()


def acquire_single_instance() -> bool:
    global _instance_file
    runtime = pathlib.Path(os.environ.get("XDG_RUNTIME_DIR", "/tmp"))
    path = runtime / f"titan-army-control-{os.getuid()}.lock"
    _instance_file = open(path, "w")
    try:
        fcntl.flock(_instance_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        _instance_file.close()
        _instance_file = None
        path = runtime / f"titan-army-control-{os.getuid()}.sock"
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as notifier:
                notifier.sendto(b"SHOW", str(path))
        except OSError:
            pass
        return False
    return True


def start_instance_listener(root: tk.Tk, show_callback) -> None:
    global _instance_socket, _instance_socket_path
    runtime = pathlib.Path(os.environ.get("XDG_RUNTIME_DIR", "/tmp"))
    path = runtime / f"titan-army-control-{os.getuid()}.sock"
    try:
        path.unlink(missing_ok=True)
        listener = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
        listener.bind(str(path))
        listener.setblocking(False)
    except OSError:
        return
    _instance_socket = listener
    _instance_socket_path = path

    def poll() -> None:
        if _instance_socket is not listener:
            return
        try:
            while listener.recv(64):
                show_callback()
        except BlockingIOError:
            pass
        root.after(200, poll)

    root.after(200, poll)


def release_single_instance() -> None:
    global _instance_file, _instance_socket, _instance_socket_path
    if _instance_socket:
        _instance_socket.close()
        _instance_socket = None
    if _instance_socket_path:
        _instance_socket_path.unlink(missing_ok=True)
        _instance_socket_path = None
    if _instance_file:
        _instance_file.close()
        _instance_file = None
