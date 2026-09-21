from __future__ import annotations

import ctypes
import pathlib
import re
import sys
import threading
import time
import tkinter as tk
import winreg
from ctypes import wintypes

APP_NAME = "Titan Army Control"
LOCAL_DIMMING = {"Off": 2, "Low": 3, "Medium": 5, "High": 6}
AUTOSTART_NAME = "TitanArmyControl"
AUTOSTART_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
SINGLE_INSTANCE_MUTEX = r"Local\TitanArmyControl.SingleInstance"
INSTANCE_MUTEX_HANDLE = None

dxva2 = ctypes.WinDLL("Dxva2.dll", use_last_error=True)
user32 = ctypes.WinDLL("user32.dll", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32.dll", use_last_error=True)

kernel32.CreateMutexW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR]
kernel32.CreateMutexW.restype = wintypes.HANDLE
kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
kernel32.CloseHandle.restype = wintypes.BOOL
user32.FindWindowW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR]
user32.FindWindowW.restype = wintypes.HWND
user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
user32.ShowWindow.restype = wintypes.BOOL
user32.SetForegroundWindow.argtypes = [wintypes.HWND]
user32.SetForegroundWindow.restype = wintypes.BOOL


class PhysicalMonitor(ctypes.Structure):
    _fields_ = [("handle", wintypes.HANDLE), ("description", wintypes.WCHAR * 128)]


MonitorEnumProc = ctypes.WINFUNCTYPE(
    wintypes.BOOL,
    wintypes.HMONITOR,
    wintypes.HDC,
    ctypes.POINTER(wintypes.RECT),
    wintypes.LPARAM,
)

user32.EnumDisplayMonitors.argtypes = [
    wintypes.HDC,
    ctypes.POINTER(wintypes.RECT),
    MonitorEnumProc,
    wintypes.LPARAM,
]
user32.EnumDisplayMonitors.restype = wintypes.BOOL
dxva2.GetNumberOfPhysicalMonitorsFromHMONITOR.argtypes = [
    wintypes.HMONITOR,
    ctypes.POINTER(wintypes.DWORD),
]
dxva2.GetNumberOfPhysicalMonitorsFromHMONITOR.restype = wintypes.BOOL
dxva2.GetPhysicalMonitorsFromHMONITOR.argtypes = [
    wintypes.HMONITOR,
    wintypes.DWORD,
    ctypes.POINTER(PhysicalMonitor),
]
dxva2.GetPhysicalMonitorsFromHMONITOR.restype = wintypes.BOOL
dxva2.DestroyPhysicalMonitor.argtypes = [wintypes.HANDLE]
dxva2.DestroyPhysicalMonitor.restype = wintypes.BOOL
dxva2.GetVCPFeatureAndVCPFeatureReply.argtypes = [
    wintypes.HANDLE,
    wintypes.BYTE,
    ctypes.POINTER(wintypes.DWORD),
    ctypes.POINTER(wintypes.DWORD),
    ctypes.POINTER(wintypes.DWORD),
]
dxva2.GetVCPFeatureAndVCPFeatureReply.restype = wintypes.BOOL
dxva2.SetVCPFeature.argtypes = [wintypes.HANDLE, wintypes.BYTE, wintypes.DWORD]
dxva2.SetVCPFeature.restype = wintypes.BOOL


class Luid(ctypes.Structure):
    _fields_ = [("low_part", wintypes.DWORD), ("high_part", wintypes.LONG)]


class DisplayConfigRational(ctypes.Structure):
    _fields_ = [("numerator", wintypes.UINT), ("denominator", wintypes.UINT)]


class DisplayConfigPathSourceInfo(ctypes.Structure):
    _fields_ = [
        ("adapter_id", Luid), ("id", wintypes.UINT),
        ("mode_info_idx", wintypes.UINT), ("status_flags", wintypes.UINT),
    ]


class DisplayConfigPathTargetInfo(ctypes.Structure):
    _fields_ = [
        ("adapter_id", Luid), ("id", wintypes.UINT),
        ("mode_info_idx", wintypes.UINT), ("output_technology", wintypes.UINT),
        ("rotation", wintypes.UINT), ("scaling", wintypes.UINT),
        ("refresh_rate", DisplayConfigRational), ("scan_line_ordering", wintypes.UINT),
        ("target_available", wintypes.BOOL), ("status_flags", wintypes.UINT),
    ]


class DisplayConfigPathInfo(ctypes.Structure):
    _fields_ = [
        ("source_info", DisplayConfigPathSourceInfo),
        ("target_info", DisplayConfigPathTargetInfo),
        ("flags", wintypes.UINT),
    ]


class DisplayConfig2DRegion(ctypes.Structure):
    _fields_ = [("cx", wintypes.UINT), ("cy", wintypes.UINT)]


class DisplayConfigVideoSignalInfo(ctypes.Structure):
    _fields_ = [
        ("pixel_rate", ctypes.c_uint64),
        ("h_sync_freq", DisplayConfigRational), ("v_sync_freq", DisplayConfigRational),
        ("active_size", DisplayConfig2DRegion), ("total_size", DisplayConfig2DRegion),
        ("video_standard", wintypes.UINT), ("scan_line_ordering", wintypes.UINT),
    ]


class DisplayConfigTargetMode(ctypes.Structure):
    _fields_ = [("target_video_signal_info", DisplayConfigVideoSignalInfo)]


class DisplayConfigSourceMode(ctypes.Structure):
    _fields_ = [
        ("width", wintypes.UINT), ("height", wintypes.UINT),
        ("pixel_format", wintypes.UINT), ("position", wintypes.POINT),
    ]


class DisplayConfigDesktopImageInfo(ctypes.Structure):
    _fields_ = [
        ("path_source_size", wintypes.POINT),
        ("desktop_image_region", wintypes.RECT),
        ("desktop_image_clip", wintypes.RECT),
    ]


class DisplayConfigModeUnion(ctypes.Union):
    _fields_ = [
        ("target_mode", DisplayConfigTargetMode),
        ("source_mode", DisplayConfigSourceMode),
        ("desktop_image_info", DisplayConfigDesktopImageInfo),
    ]


class DisplayConfigModeInfo(ctypes.Structure):
    _anonymous_ = ("mode",)
    _fields_ = [
        ("info_type", wintypes.UINT), ("id", wintypes.UINT),
        ("adapter_id", Luid), ("mode", DisplayConfigModeUnion),
    ]


class DisplayConfigDeviceInfoHeader(ctypes.Structure):
    _fields_ = [
        ("type", wintypes.UINT), ("size", wintypes.UINT),
        ("adapter_id", Luid), ("id", wintypes.UINT),
    ]


class DisplayConfigTargetDeviceName(ctypes.Structure):
    _fields_ = [
        ("header", DisplayConfigDeviceInfoHeader), ("flags", wintypes.UINT),
        ("output_technology", wintypes.UINT), ("edid_manufacturer_id", wintypes.WORD),
        ("edid_product_code_id", wintypes.WORD), ("connector_instance", wintypes.UINT),
        ("friendly_name", wintypes.WCHAR * 64), ("device_path", wintypes.WCHAR * 128),
    ]


class DisplayConfigSourceDeviceName(ctypes.Structure):
    _fields_ = [
        ("header", DisplayConfigDeviceInfoHeader),
        ("view_gdi_device_name", wintypes.WCHAR * 32),
    ]


class MonitorInfoEx(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD), ("rcMonitor", wintypes.RECT),
        ("rcWork", wintypes.RECT), ("dwFlags", wintypes.DWORD),
        ("szDevice", wintypes.WCHAR * 32),
    ]


class DisplayConfigAdvancedColorInfo(ctypes.Structure):
    _fields_ = [
        ("header", DisplayConfigDeviceInfoHeader), ("value", wintypes.UINT),
        ("color_encoding", wintypes.UINT), ("bits_per_color_channel", wintypes.UINT),
    ]


class DisplayConfigSetAdvancedColorState(ctypes.Structure):
    _fields_ = [("header", DisplayConfigDeviceInfoHeader), ("enable", wintypes.UINT)]


class DisplayConfigAdvancedColorInfo2(ctypes.Structure):
    _fields_ = [
        ("header", DisplayConfigDeviceInfoHeader), ("value", wintypes.UINT),
        ("color_encoding", wintypes.UINT), ("bits_per_color_channel", wintypes.UINT),
        ("active_color_mode", wintypes.UINT),
    ]


class DisplayConfigSetHdrState(ctypes.Structure):
    _fields_ = [("header", DisplayConfigDeviceInfoHeader), ("enable", wintypes.UINT)]


user32.GetDisplayConfigBufferSizes.argtypes = [
    wintypes.UINT, ctypes.POINTER(wintypes.UINT), ctypes.POINTER(wintypes.UINT)
]
user32.GetDisplayConfigBufferSizes.restype = wintypes.LONG
user32.QueryDisplayConfig.argtypes = [
    wintypes.UINT, ctypes.POINTER(wintypes.UINT), ctypes.POINTER(DisplayConfigPathInfo),
    ctypes.POINTER(wintypes.UINT), ctypes.POINTER(DisplayConfigModeInfo), ctypes.c_void_p,
]
user32.QueryDisplayConfig.restype = wintypes.LONG
user32.DisplayConfigGetDeviceInfo.argtypes = [ctypes.POINTER(DisplayConfigDeviceInfoHeader)]
user32.DisplayConfigGetDeviceInfo.restype = wintypes.LONG
user32.DisplayConfigSetDeviceInfo.argtypes = [ctypes.POINTER(DisplayConfigDeviceInfoHeader)]
user32.DisplayConfigSetDeviceInfo.restype = wintypes.LONG
user32.GetMonitorInfoW.argtypes = [wintypes.HMONITOR, ctypes.POINTER(MonitorInfoEx)]
user32.GetMonitorInfoW.restype = wintypes.BOOL

QDC_ONLY_ACTIVE_PATHS = 0x00000002
GET_TARGET_NAME = 2
GET_SOURCE_NAME = 1
GET_ADVANCED_COLOR_INFO = 9
SET_ADVANCED_COLOR_STATE = 10
GET_ADVANCED_COLOR_INFO_2 = 15
SET_HDR_STATE = 16
ADVANCED_COLOR_MODE_HDR = 2


def enumerate_physical_monitors() -> list[tuple[str, PhysicalMonitor]]:
    logical: list[tuple[int, str]] = []

    @MonitorEnumProc
    def callback(handle, _hdc, _rect, _data):
        info = MonitorInfoEx()
        info.cbSize = ctypes.sizeof(info)
        if user32.GetMonitorInfoW(handle, ctypes.byref(info)):
            logical.append((handle, info.szDevice))
        return True

    if not user32.EnumDisplayMonitors(None, None, callback, 0):
        raise ctypes.WinError(ctypes.get_last_error())

    result: list[tuple[str, PhysicalMonitor]] = []
    for logical_handle, device_name in logical:
        count = wintypes.DWORD()
        if not dxva2.GetNumberOfPhysicalMonitorsFromHMONITOR(
            logical_handle, ctypes.byref(count)
        ):
            continue
        items = (PhysicalMonitor * count.value)()
        if dxva2.GetPhysicalMonitorsFromHMONITOR(logical_handle, count.value, items):
            result.extend((device_name, item) for item in items)
    return result


def read_vcp(handle, code: int) -> tuple[int, int] | None:
    kind = wintypes.DWORD()
    current = wintypes.DWORD()
    maximum = wintypes.DWORD()
    if dxva2.GetVCPFeatureAndVCPFeatureReply(
        handle,
        code,
        ctypes.byref(kind),
        ctypes.byref(current),
        ctypes.byref(maximum),
    ):
        return current.value, maximum.value
    return None


def find_titan_army(monitors: list[PhysicalMonitor]) -> PhysicalMonitor:
    candidates = []
    for monitor in monitors:
        mode = read_vcp(monitor.handle, 0xE0)
        if mode is not None and mode[1] >= 14:
            candidates.append(monitor)
    if len(candidates) == 1:
        return candidates[0]
    if not candidates and len(monitors) == 1:
        return monitors[0]
    if not candidates:
        raise RuntimeError("Монитор Titan Army не найден")
    raise RuntimeError("Найдено несколько подходящих мониторов")


def set_widget_style(handle, code: int, value: int) -> None:
    if not dxva2.SetVCPFeature(handle, 0x99, value):
        raise ctypes.WinError(ctypes.get_last_error())
    time.sleep(0.065)
    if not dxva2.SetVCPFeature(handle, code, value):
        raise ctypes.WinError(ctypes.get_last_error())


def active_display_paths() -> list[DisplayConfigPathInfo]:
    for _ in range(3):
        path_count = wintypes.UINT()
        mode_count = wintypes.UINT()
        result = user32.GetDisplayConfigBufferSizes(
            QDC_ONLY_ACTIVE_PATHS, ctypes.byref(path_count), ctypes.byref(mode_count)
        )
        if result:
            raise ctypes.WinError(result)
        paths = (DisplayConfigPathInfo * path_count.value)()
        modes = (DisplayConfigModeInfo * mode_count.value)()
        result = user32.QueryDisplayConfig(
            QDC_ONLY_ACTIVE_PATHS,
            ctypes.byref(path_count), paths,
            ctypes.byref(mode_count), modes, None,
        )
        if result == 0:
            return list(paths[:path_count.value])
        if result != 122:
            raise ctypes.WinError(result)
    raise RuntimeError("Display configuration changed during query")


def device_header(info_type: int, target: DisplayConfigPathTargetInfo, size: int):
    return DisplayConfigDeviceInfoHeader(
        type=info_type,
        size=size,
        adapter_id=target.adapter_id,
        id=target.id,
    )


def target_name(target: DisplayConfigPathTargetInfo) -> DisplayConfigTargetDeviceName | None:
    info = DisplayConfigTargetDeviceName()
    info.header = device_header(GET_TARGET_NAME, target, ctypes.sizeof(info))
    if user32.DisplayConfigGetDeviceInfo(ctypes.byref(info.header)) == 0:
        return info
    return None


def source_name(source: DisplayConfigPathSourceInfo) -> str:
    info = DisplayConfigSourceDeviceName()
    info.header = DisplayConfigDeviceInfoHeader(
        type=GET_SOURCE_NAME, size=ctypes.sizeof(info),
        adapter_id=source.adapter_id, id=source.id,
    )
    if user32.DisplayConfigGetDeviceInfo(ctypes.byref(info.header)) == 0:
        return info.view_gdi_device_name
    return ""


def display_choices() -> list[tuple[str, str, str]]:
    choices = []
    for path in active_display_paths():
        name = target_name(path.target_info)
        source = source_name(path.source_info)
        if name is None or not name.device_path or not source:
            continue
        label = name.friendly_name or "Display"
        choices.append((name.device_path, source, f"{source}: {label}"))
    return choices


def advanced_color_info(target: DisplayConfigPathTargetInfo) -> DisplayConfigAdvancedColorInfo | None:
    info = DisplayConfigAdvancedColorInfo()
    info.header = device_header(GET_ADVANCED_COLOR_INFO, target, ctypes.sizeof(info))
    if user32.DisplayConfigGetDeviceInfo(ctypes.byref(info.header)) == 0:
        return info
    return None


def advanced_color_info_2(target: DisplayConfigPathTargetInfo) -> DisplayConfigAdvancedColorInfo2 | None:
    info = DisplayConfigAdvancedColorInfo2()
    info.header = device_header(GET_ADVANCED_COLOR_INFO_2, target, ctypes.sizeof(info))
    if user32.DisplayConfigGetDeviceInfo(ctypes.byref(info.header)) == 0:
        return info
    return None


def titan_army_hdr_target(selected_path: str | None = None) -> tuple[DisplayConfigPathTargetInfo, bool]:
    supported = []
    exact = []
    for path in active_display_paths():
        target = path.target_info
        color2 = advanced_color_info_2(target)
        if color2 is not None:
            # Windows 11 24H2 exposes HDR separately from WCG/advanced color.
            hdr_supported = bool(color2.value & (1 << 4))
            enabled = color2.active_color_mode == ADVANCED_COLOR_MODE_HDR
        else:
            color = advanced_color_info(target)
            if color is None:
                continue
            hdr_supported = bool(color.value & 0x1)
            enabled = bool(color.value & 0x2)
        name = target_name(target)
        if selected_path is not None and (name is None or name.device_path != selected_path):
            continue
        if not hdr_supported:
            continue
        supported.append((target, enabled))
        identity = "" if name is None else f"{name.friendly_name} {name.device_path}".upper()
        if "LHC916D" in identity or "TITAN" in identity:
            exact.append((target, enabled))
    if len(exact) == 1:
        return exact[0]
    if len(supported) == 1:
        return supported[0]
    if not supported:
        raise RuntimeError("The selected display is disconnected or does not support HDR")
    raise RuntimeError("Multiple HDR displays are active and Titan Army could not be identified")


def set_windows_hdr(enabled: bool, selected_path: str | None = None) -> bool:
    target, current = titan_army_hdr_target(selected_path)
    if current == enabled:
        return False
    if advanced_color_info_2(target) is not None:
        state = DisplayConfigSetHdrState()
        state.header = device_header(SET_HDR_STATE, target, ctypes.sizeof(state))
        state.enable = int(enabled)
    else:
        state = DisplayConfigSetAdvancedColorState()
        state.header = device_header(SET_ADVANCED_COLOR_STATE, target, ctypes.sizeof(state))
        state.enable = int(enabled)
    result = user32.DisplayConfigSetDeviceInfo(ctypes.byref(state.header))
    if result:
        raise ctypes.WinError(result)
    for _ in range(12):
        time.sleep(0.15)
        _target, actual = titan_army_hdr_target(selected_path)
        if actual == enabled:
            return True
    raise RuntimeError("Windows reported success, but the HDR state did not change")


def apply_monitor_profile(local_dimming: str, brightness: int, halo: int, hdr: bool,
                          selected_path: str | None = None) -> None:
    choices = display_choices()
    if selected_path is None:
        if len(choices) != 1:
            raise RuntimeError("Select a monitor in the application first")
        selected_path = choices[0][0]
    source = next((item[1] for item in choices if item[0] == selected_path), None)
    if source is None:
        raise RuntimeError("The selected monitor is disconnected; select it again")
    monitors = enumerate_physical_monitors()
    try:
        matching = [item for device, item in monitors if device == source]
        if len(matching) != 1:
            raise RuntimeError("The selected display does not map to one physical monitor")
        monitor = matching[0]
        changed = set_windows_hdr(hdr, selected_path)
        if changed:
            time.sleep(0.8)
        set_widget_style(monitor.handle, 0x47, LOCAL_DIMMING[local_dimming])
        if not hdr:
            time.sleep(0.08)
            if not dxva2.SetVCPFeature(monitor.handle, 0x10, brightness):
                raise ctypes.WinError(ctypes.get_last_error())
            time.sleep(0.08)
            set_widget_style(monitor.handle, 0x46, halo)
    finally:
        for _device, item in monitors:
            dxva2.DestroyPhysicalMonitor(item.handle)


def autostart_command(minimized: bool) -> str:
    executable = pathlib.Path(sys.executable).resolve()
    command = f'"{executable}"'
    return f"{command} --minimized" if minimized else command


def read_autostart_mode() -> str:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, AUTOSTART_KEY) as key:
            command, _kind = winreg.QueryValueEx(key, AUTOSTART_NAME)
    except FileNotFoundError:
        return "off"
    return "tray" if "--minimized" in str(command).lower() else "window"


def write_autostart_mode(mode: str) -> None:
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, AUTOSTART_KEY) as key:
        if mode == "off":
            try:
                winreg.DeleteValue(key, AUTOSTART_NAME)
            except FileNotFoundError:
                pass
        else:
            winreg.SetValueEx(
                key, AUTOSTART_NAME, 0, winreg.REG_SZ,
                autostart_command(mode == "tray"),
            )


MODIFIERS = {"CTRL": 0x0002, "ALT": 0x0001, "SHIFT": 0x0004, "WIN": 0x0008}


def parse_hotkey(text: str) -> tuple[int, int]:
    parts = [part.strip().upper() for part in text.split("+") if part.strip()]
    if len(parts) < 2:
        raise ValueError("Пример горячей клавиши: Ctrl+Alt+1")
    modifiers = 0
    for part in parts[:-1]:
        if part not in MODIFIERS:
            raise ValueError(f"Неизвестный модификатор: {part}")
        modifiers |= MODIFIERS[part]
    key = parts[-1]
    if len(key) == 1 and key in "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789":
        virtual_key = ord(key)
    elif re.fullmatch(r"F(?:[1-9]|1[0-2])", key):
        virtual_key = 0x70 + int(key[1:]) - 1
    else:
        raise ValueError("Поддерживаются A–Z, 0–9 и F1–F12")
    return modifiers | 0x4000, virtual_key


class HotkeyManager:
    def __init__(self, root: tk.Tk, callback):
        self.root = root
        self.callback = callback
        self.thread: threading.Thread | None = None
        self.thread_id: int | None = None
        self.ready = threading.Event()
        self.error: str | None = None

    def start(self, profiles: list[dict]) -> None:
        self.stop()
        self.ready.clear()
        self.error = None
        hotkeys = [(1000 + i, profile.get("hotkey", "")) for i, profile in enumerate(profiles)]
        self.thread = threading.Thread(target=self._listen, args=(hotkeys,), daemon=True)
        self.thread.start()
        self.ready.wait(2)
        if self.error:
            raise ValueError(self.error)

    def _listen(self, hotkeys: list[tuple[int, str]]) -> None:
        self.thread_id = kernel32.GetCurrentThreadId()
        registered: list[int] = []
        try:
            for hotkey_id, text in hotkeys:
                modifiers, key = parse_hotkey(text)
                if not user32.RegisterHotKey(None, hotkey_id, modifiers, key):
                    self.error = f"Горячая клавиша {text} уже используется"
                    for registered_id in registered:
                        user32.UnregisterHotKey(None, registered_id)
                    return
                registered.append(hotkey_id)
        except ValueError as error:
            self.error = str(error)
            return
        finally:
            self.ready.set()

        message = wintypes.MSG()
        while user32.GetMessageW(ctypes.byref(message), None, 0, 0) > 0:
            if message.message == 0x0312:
                index = int(message.wParam) - 1000
                self.root.after(0, self.callback, index)
        for hotkey_id in registered:
            user32.UnregisterHotKey(None, hotkey_id)

    def stop(self) -> None:
        if self.thread_id:
            user32.PostThreadMessageW(self.thread_id, 0x0012, 0, 0)
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=1)
        self.thread = None
        self.thread_id = None


def acquire_single_instance() -> bool:
    global INSTANCE_MUTEX_HANDLE
    INSTANCE_MUTEX_HANDLE = kernel32.CreateMutexW(None, False, SINGLE_INSTANCE_MUTEX)
    if not INSTANCE_MUTEX_HANDLE:
        raise ctypes.WinError(ctypes.get_last_error())
    if ctypes.get_last_error() == 183:
        existing = user32.FindWindowW(None, APP_NAME)
        if existing:
            user32.ShowWindow(existing, 9)
            user32.SetForegroundWindow(existing)
        else:
            user32.MessageBoxW(None, "Titan Army Control уже запущен.", APP_NAME, 0x40)
        kernel32.CloseHandle(INSTANCE_MUTEX_HANDLE)
        INSTANCE_MUTEX_HANDLE = None
        return False
    return True


def release_single_instance() -> None:
    global INSTANCE_MUTEX_HANDLE
    if INSTANCE_MUTEX_HANDLE:
        kernel32.CloseHandle(INSTANCE_MUTEX_HANDLE)
        INSTANCE_MUTEX_HANDLE = None
