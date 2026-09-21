from __future__ import annotations

import argparse
import json
import os
import pathlib
import shutil
import subprocess
import sys
import threading
import time
import tkinter as tk
import tkinter.font as tkfont
from tkinter import messagebox, ttk
from TitanArmyControl.version import VERSION

if sys.platform == "win32":
    from TitanArmyControl import windows_backend as backend
elif sys.platform == "linux":
    from TitanArmyControl import linux_backend as backend
else:
    raise RuntimeError(f"Unsupported platform: {sys.platform}")

HotkeyManager = backend.HotkeyManager
apply_monitor_profile = backend.apply_monitor_profile
display_choices = backend.display_choices
read_autostart_mode = backend.read_autostart_mode
write_autostart_mode = backend.write_autostart_mode


APP_NAME = "Titan Army Control"
UI_FONT = "DejaVu Sans" if sys.platform == "linux" else "Segoe UI"
MAX_PROFILES = 10
LOCAL_DIMMING = {"Off": 2, "Low": 3, "Medium": 5, "High": 6}
CONFIG_DIR = (pathlib.Path(os.environ.get("APPDATA", pathlib.Path.home())) / "TitanArmyControl" if sys.platform == "win32" else pathlib.Path(os.environ.get("XDG_CONFIG_HOME", pathlib.Path.home() / ".config")) / "titan-army-control")
CONFIG_FILE = CONFIG_DIR / "profiles.json"

TEXT = {
    "ru": {
        "profiles": "Профили", "profile_settings": "Настройка профиля",
        "name": "Название", "local": "Local Dimming", "halo": "Halo Control",
        "brightness": "Яркость", "hdr": "HDR", "on": "Вкл.", "off": "Выкл.",
        "hotkey": "Горячая клавиша", "delete": "Удалить", "save": "Сохранить",
        "apply": "Применить", "ready": "Готово", "language": "Язык",
        "open": "Открыть", "exit": "Выйти",
        "autostart": "Автозапуск", "start_window": "С окном", "start_tray": "Сразу в трее",
        "max_profiles": "Можно создать не более 10 профилей",
        "one_profile": "Должен остаться хотя бы один профиль",
        "enter_name": "Введите название профиля",
        "duplicate_hotkey": "Эта горячая клавиша уже назначена другому профилю",
        "saved": "Профиль сохранён", "applying": "Применяется: {name}…",
        "apply_error": "Ошибка применения", "applied": "Применён профиль: {name}",
        "monitor_missing": "Монитор Titan Army не найден",
        "multiple_monitors": "Найдено несколько подходящих мониторов",
        "hotkey_busy": "Горячая клавиша {hotkey} уже используется",
        "profile": "Профиль {number}", "desktop": "Рабочий стол", "sdr": "Игры SDR",
        "monitor": "Монитор", "refresh_monitors": "Обновить",
        "choose_monitor": "Выберите монитор",
    },
    "en": {
        "profiles": "Profiles", "profile_settings": "Profile settings",
        "name": "Name", "local": "Local Dimming", "halo": "Halo Control",
        "brightness": "Brightness", "hdr": "HDR", "on": "On", "off": "Off",
        "hotkey": "Hotkey", "delete": "Delete", "save": "Save",
        "apply": "Apply", "ready": "Ready", "language": "Language",
        "open": "Open", "exit": "Exit",
        "autostart": "Start automatically", "start_window": "Show window", "start_tray": "Start in tray",
        "max_profiles": "You can create up to 10 profiles",
        "one_profile": "At least one profile must remain",
        "enter_name": "Enter a profile name",
        "duplicate_hotkey": "This hotkey is already assigned to another profile",
        "saved": "Profile saved", "applying": "Applying: {name}…",
        "apply_error": "Apply failed", "applied": "Applied profile: {name}",
        "monitor_missing": "Titan Army monitor was not found",
        "multiple_monitors": "Multiple matching monitors were found",
        "hotkey_busy": "Hotkey {hotkey} is already in use",
        "profile": "Profile {number}", "desktop": "Desktop", "sdr": "SDR Gaming",
        "monitor": "Monitor", "refresh_monitors": "Refresh",
        "choose_monitor": "Select a monitor",
    },
}


def resource_path(name: str) -> pathlib.Path:
    base = pathlib.Path(getattr(sys, "_MEIPASS", pathlib.Path(__file__).resolve().parent))
    return base / name



def default_profiles() -> list[dict]:
    return [
        {"name": "Рабочий стол", "local_dimming": "Off", "brightness": 40, "halo": 0, "hdr": False, "hotkey": "Ctrl+Alt+1"},
        {"name": "Игры SDR", "local_dimming": "Medium", "brightness": 100, "halo": 100, "hdr": False, "hotkey": "Ctrl+Alt+2"},
        {"name": "HDR", "local_dimming": "High", "brightness": 100, "halo": 100, "hdr": True, "hotkey": "Ctrl+Alt+3"},
    ]


def load_settings() -> tuple[list[dict], str, str | None]:
    try:
        raw = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        profiles = raw.get("profiles", [])
        if not isinstance(profiles, list) or not profiles:
            raise ValueError
        for profile in profiles:
            profile.setdefault("brightness", 100)
            profile.setdefault("hdr", False)
        language = raw.get("language", "ru")
        selected_path = raw.get("selected_monitor")
        return profiles[:MAX_PROFILES], language if language in TEXT else "ru", selected_path if isinstance(selected_path, str) else None
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return default_profiles(), "ru", None


def save_settings(profiles: list[dict], language: str, selected_monitor: str | None = None) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    temporary = CONFIG_FILE.with_suffix(".tmp")
    temporary.write_text(
        json.dumps({"profiles": profiles, "language": language, "selected_monitor": selected_monitor}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    temporary.replace(CONFIG_FILE)



class App:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.profiles, self.language, self.selected_monitor = load_settings()
        self.selected = 0
        self.apply_lock = threading.Lock()
        self.hotkeys = HotkeyManager(root, self.apply_profile)
        self.tray_icon = None
        self.exiting = False

        root.title(APP_NAME)
        root.geometry("650x550")
        root.minsize(650, 550)
        root.protocol("WM_DELETE_WINDOW", self.hide_to_tray)
        self.configure_style()
        self.build_ui()
        self.apply_language()
        self.refresh_list()
        self.select_profile(0)
        self.start_tray()
        try:
            self.hotkeys.start(self.profiles)
        except (ValueError, RuntimeError) as error:
            messagebox.showwarning(APP_NAME, str(error))
        if "--minimized" in sys.argv and self.tray_icon:
            root.after(0, root.withdraw)

    def configure_style(self) -> None:
        if sys.platform == "linux":
            for name in ("TkDefaultFont", "TkTextFont", "TkMenuFont", "TkHeadingFont"):
                tkfont.nametofont(name).configure(family=UI_FONT)
        self.root.configure(bg="#15181d")
        style = ttk.Style()
        style.theme_use("clam")
        style.configure(".", background="#15181d", foreground="#f1f3f5", fieldbackground="#22262d",
                        font=(UI_FONT, 10))
        style.configure("TButton", padding=(12, 7))
        style.configure("Accent.TButton", background="#21c77a", foreground="#07140e")
        style.map("Accent.TButton", background=[("active", "#43dd93")])
        style.configure("TLabel", background="#15181d")
        style.configure("TFrame", background="#15181d")
        style.configure("TLabelframe", background="#15181d")
        style.configure("TLabelframe.Label", background="#15181d", foreground="#aeb6c2")
        style.configure(
            "Dark.TCombobox",
            fieldbackground="#22262d",
            background="#22262d",
            foreground="#ffffff",
            arrowcolor="#ffffff",
            selectbackground="#22262d",
            selectforeground="#ffffff",
        )
        style.map(
            "Dark.TCombobox",
            fieldbackground=[("readonly", "#22262d")],
            foreground=[("readonly", "#ffffff")],
            selectbackground=[("readonly", "#22262d")],
            selectforeground=[("readonly", "#ffffff")],
        )
        self.root.option_add("*TCombobox*Listbox.background", "#22262d")
        self.root.option_add("*TCombobox*Listbox.foreground", "#ffffff")
        self.root.option_add("*TCombobox*Listbox.selectBackground", "#21c77a")
        self.root.option_add("*TCombobox*Listbox.selectForeground", "#07140e")

    def build_ui(self) -> None:
        outer = ttk.Frame(self.root, padding=16)
        outer.pack(fill="both", expand=True)

        header = ttk.Frame(outer)
        header.pack(fill="x", pady=(0, 12))
        icon_path = resource_path("ta-icon-black.png")
        if icon_path.is_file():
            self.icon_image = tk.PhotoImage(file=icon_path)
            self.root.iconphoto(True, self.icon_image)
        logo_path = resource_path("ta-logo-white.png")
        if logo_path.is_file():
            self.logo_image = tk.PhotoImage(file=logo_path)
            self.logo_small = self.logo_image.subsample(24, 24)
            tk.Label(header, image=self.logo_small, bg="#15181d", borderwidth=0).pack(side="left")
        ttk.Label(header, text=f"v{VERSION}", foreground="#929baa").pack(side="left", padx=(8, 0))
        self.language_label = ttk.Label(header)
        self.language_label.pack(side="right", padx=(8, 0))
        self.language_var = tk.StringVar(value="Русский" if self.language == "ru" else "English")
        self.language_combo = ttk.Combobox(
            header,
            width=10,
            state="readonly",
            style="Dark.TCombobox",
            textvariable=self.language_var,
            values=("Русский", "English"),
        )
        self.language_combo.pack(side="right")
        self.language_combo.bind("<<ComboboxSelected>>", self.change_language)

        startup = ttk.Frame(outer)
        startup.pack(fill="x", pady=(0, 12))
        current_startup = read_autostart_mode()
        self.autostart_var = tk.BooleanVar(value=current_startup != "off")
        self.autostart_check = ttk.Checkbutton(
            startup, variable=self.autostart_var, command=self.change_autostart
        )
        self.autostart_check.pack(side="left")
        self.autostart_mode_var = tk.StringVar(value=current_startup if current_startup != "off" else "tray")
        self.autostart_mode_combo = ttk.Combobox(
            startup, width=18, state="readonly", style="Dark.TCombobox",
            textvariable=self.autostart_mode_var, values=("window", "tray"),
        )
        self.autostart_mode_combo.pack(side="left", padx=(10, 0))
        self.autostart_mode_combo.bind("<<ComboboxSelected>>", self.change_autostart)
        if current_startup == "off":
            self.autostart_mode_combo.configure(state="disabled")

        monitor_row = ttk.Frame(outer)
        monitor_row.pack(fill="x", pady=(0, 12))
        self.monitor_label = ttk.Label(monitor_row)
        self.monitor_label.pack(side="left")
        self.monitor_var = tk.StringVar()
        self.monitor_combo = ttk.Combobox(
            monitor_row, state="readonly", style="Dark.TCombobox",
            textvariable=self.monitor_var,
        )
        self.monitor_combo.pack(side="left", fill="x", expand=True, padx=(10, 8))
        self.monitor_combo.bind("<<ComboboxSelected>>", self.change_monitor)
        self.monitor_refresh = ttk.Button(monitor_row, command=self.refresh_monitors)
        self.monitor_refresh.pack(side="right")
        self.monitor_choices = []
        self.refresh_monitors()

        content = ttk.Frame(outer)
        content.pack(fill="both", expand=True)

        left = ttk.Frame(content)
        left.pack(side="left", fill="y", padx=(0, 16))
        self.profiles_label = ttk.Label(left, font=(UI_FONT, 13, "bold"))
        self.profiles_label.pack(anchor="w", pady=(0, 8))
        self.profile_list = tk.Listbox(
            left,
            width=25,
            height=14,
            bg="#22262d",
            fg="#f1f3f5",
            selectbackground="#21c77a",
            selectforeground="#07140e",
            borderwidth=0,
            highlightthickness=0,
            font=(UI_FONT, 10),
            activestyle="none",
        )
        self.profile_list.pack(fill="y", expand=True)
        self.profile_list.bind("<<ListboxSelect>>", self.on_select)

        buttons = ttk.Frame(left)
        buttons.pack(fill="x", pady=(10, 0))
        ttk.Button(buttons, text="+", width=4, command=self.add_profile).pack(side="left")
        self.delete_button = ttk.Button(buttons, command=self.delete_profile)
        self.delete_button.pack(side="left", padx=(6, 0))

        self.editor = ttk.LabelFrame(content, padding=16)
        editor = self.editor
        editor.pack(side="left", fill="both", expand=True)

        self.name_label = ttk.Label(editor)
        self.name_label.grid(row=0, column=0, sticky="w", pady=6)
        self.name_var = tk.StringVar()
        self.name_entry = tk.Entry(
            editor,
            textvariable=self.name_var,
            bg="#22262d",
            fg="#ffffff",
            insertbackground="#21c77a",
            insertwidth=2,
            selectbackground="#21c77a",
            selectforeground="#07140e",
            relief="flat",
            font=(UI_FONT, 10),
        )
        self.name_entry.grid(row=0, column=1, sticky="ew", padx=(14, 0), pady=6, ipady=5)

        self.local_label = ttk.Label(editor)
        self.local_label.grid(row=1, column=0, sticky="w", pady=6)
        self.local_var = tk.StringVar()
        self.local_combo = ttk.Combobox(
            editor,
            textvariable=self.local_var,
            values=list(LOCAL_DIMMING),
            state="readonly",
            style="Dark.TCombobox",
        )
        self.local_combo.grid(row=1, column=1, sticky="ew", padx=(14, 0), pady=6)

        self.hdr_var = tk.BooleanVar()
        self.hdr_check = ttk.Checkbutton(
            editor, variable=self.hdr_var, command=self.on_hdr_toggle
        )
        self.hdr_check.grid(row=2, column=0, columnspan=2, sticky="w", pady=6)

        self.brightness_label = ttk.Label(editor)
        self.brightness_label.grid(row=3, column=0, sticky="w", pady=6)
        self.brightness_row = ttk.Frame(editor)
        self.brightness_row.grid(row=3, column=1, sticky="ew", padx=(14, 0), pady=6)
        self.brightness_var = tk.IntVar()
        self.brightness_scale = ttk.Scale(
            self.brightness_row, from_=0, to=100, command=self.on_brightness_slide
        )
        self.brightness_scale.pack(side="left", fill="x", expand=True)
        self.brightness_input = tk.Spinbox(
            self.brightness_row, from_=0, to=100, width=4,
            textvariable=self.brightness_var, command=self.on_brightness_input,
            bg="#22262d", fg="#ffffff", insertbackground="#21c77a",
            buttonbackground="#303640", relief="flat", justify="center",
            font=(UI_FONT, 10),
        )
        self.brightness_input.pack(side="left", padx=(9, 0), ipady=3)
        self.brightness_input.bind("<KeyRelease>", self.on_brightness_input)
        self.brightness_input.bind("<FocusOut>", self.on_brightness_input)

        self.halo_title_label = ttk.Label(editor)
        self.halo_title_label.grid(row=4, column=0, sticky="w", pady=6)
        self.halo_row = ttk.Frame(editor)
        halo_row = self.halo_row
        halo_row.grid(row=4, column=1, sticky="ew", padx=(14, 0), pady=6)
        self.halo_var = tk.IntVar()
        self.halo_scale = ttk.Scale(halo_row, from_=0, to=100, command=self.on_halo_slide)
        self.halo_scale.pack(side="left", fill="x", expand=True)
        self.halo_input = tk.Spinbox(
            halo_row,
            from_=0,
            to=100,
            width=4,
            textvariable=self.halo_var,
            command=self.on_halo_input,
            bg="#22262d",
            fg="#ffffff",
            insertbackground="#21c77a",
            buttonbackground="#303640",
            relief="flat",
            justify="center",
            font=(UI_FONT, 10),
        )
        self.halo_input.pack(side="left", padx=(9, 0), ipady=3)
        self.halo_input.bind("<KeyRelease>", self.on_halo_input)
        self.halo_input.bind("<FocusOut>", self.on_halo_input)

        self.hotkey_label = ttk.Label(editor)
        self.hotkey_label.grid(row=5, column=0, sticky="w", pady=6)
        hotkey_row = ttk.Frame(editor)
        hotkey_row.grid(row=5, column=1, sticky="w", padx=(14, 0), pady=6)
        ttk.Label(hotkey_row, text="Ctrl + Alt +", font=(UI_FONT, 10, "bold")).pack(side="left")
        self.hotkey_digit_var = tk.StringVar()
        self.hotkey_combo = ttk.Combobox(
            hotkey_row,
            width=3,
            state="readonly",
            style="Dark.TCombobox",
            values=tuple(str(i) for i in range(10)),
            textvariable=self.hotkey_digit_var,
        )
        self.hotkey_combo.pack(side="left", padx=(8, 0))

        editor.columnconfigure(1, weight=1)
        actions = ttk.Frame(editor)
        actions.grid(row=6, column=0, columnspan=2, sticky="sew", pady=(20, 0))
        self.save_button = ttk.Button(actions, command=self.save_current)
        self.save_button.pack(side="left")
        self.apply_button = ttk.Button(
            actions,
            style="Accent.TButton",
            command=self.save_and_apply,
        )
        self.apply_button.pack(side="right")

        self.status_var = tk.StringVar()
        ttk.Label(editor, textvariable=self.status_var, foreground="#929baa").grid(
            row=7, column=0, columnspan=2, sticky="w", pady=(14, 0)
        )

    def refresh_list(self) -> None:
        self.profile_list.delete(0, "end")
        for profile in self.profiles:
            self.profile_list.insert("end", profile["name"])

    def t(self, key: str, **values) -> str:
        return TEXT[self.language][key].format(**values)

    def apply_language(self) -> None:
        self.language_label.configure(text="🌐  Language / Язык")
        self.autostart_check.configure(text=self.t("autostart"))
        self.autostart_mode_combo.configure(
            values=(self.t("start_window"), self.t("start_tray"))
        )
        mode = self.autostart_mode_var.get()
        if mode in ("window", "tray"):
            self.autostart_mode_var.set(
                self.t("start_tray") if mode == "tray" else self.t("start_window")
            )
        self.profiles_label.configure(text=self.t("profiles"))
        self.monitor_label.configure(text=self.t("monitor"))
        self.monitor_refresh.configure(text=self.t("refresh_monitors"))
        if not self.selected_monitor:
            self.monitor_var.set(self.t("choose_monitor"))
        self.editor.configure(text=self.t("profile_settings"))
        self.name_label.configure(text=self.t("name"))
        self.local_label.configure(text=self.t("local"))
        self.brightness_label.configure(text=self.t("brightness"))
        self.halo_title_label.configure(text=self.t("halo"))
        self.hdr_check.configure(text=self.t("hdr"))
        self.hotkey_label.configure(text=self.t("hotkey"))
        self.delete_button.configure(text=self.t("delete"))
        self.save_button.configure(text=self.t("save"))
        self.apply_button.configure(text=self.t("apply"))
        self.status_var.set(self.t("ready"))

    def change_language(self, _event=None) -> None:
        mode = self.selected_autostart_mode()
        self.language = "ru" if self.language_var.get() == "Русский" else "en"
        self.apply_language()
        self.autostart_mode_var.set(
            self.t("start_tray") if mode == "tray" else self.t("start_window")
        )
        if self.tray_icon:
            if sys.platform == "linux":
                self.tray_icon.set_labels(self.t("open"), self.t("exit"))
            else:
                self.tray_icon.menu = self.tray_menu()
                self.tray_icon.update_menu()
        try:
            save_settings(self.profiles, self.language, self.selected_monitor)
        except OSError as error:
            messagebox.showerror(APP_NAME, str(error))

    def selected_autostart_mode(self) -> str:
        return "tray" if self.autostart_mode_var.get() in ("tray", self.t("start_tray")) else "window"

    def refresh_monitors(self) -> None:
        try:
            self.monitor_choices = display_choices()
        except (OSError, RuntimeError, subprocess.TimeoutExpired) as error:
            messagebox.showerror(APP_NAME, str(error))
            return
        self.monitor_combo.configure(values=[item[2] for item in self.monitor_choices])
        matches = [item for item in self.monitor_choices if item[0] == self.selected_monitor]
        if not self.selected_monitor and len(self.monitor_choices) == 1:
            self.selected_monitor = self.monitor_choices[0][0]
            matches = self.monitor_choices
        self.monitor_var.set(matches[0][2] if matches else self.t("choose_monitor"))

    def change_monitor(self, _event=None) -> None:
        index = self.monitor_combo.current()
        if index < 0:
            return
        self.selected_monitor = self.monitor_choices[index][0]
        try:
            save_settings(self.profiles, self.language, self.selected_monitor)
        except OSError as error:
            messagebox.showerror(APP_NAME, str(error))

    def change_autostart(self, _event=None) -> None:
        mode = self.selected_autostart_mode() if self.autostart_var.get() else "off"
        try:
            write_autostart_mode(mode)
        except OSError as error:
            messagebox.showerror(APP_NAME, str(error))
            return
        self.autostart_mode_combo.configure(
            state="readonly" if self.autostart_var.get() else "disabled"
        )

    def select_profile(self, index: int) -> None:
        self.selected = max(0, min(index, len(self.profiles) - 1))
        self.profile_list.selection_clear(0, "end")
        self.profile_list.selection_set(self.selected)
        self.profile_list.activate(self.selected)
        profile = self.profiles[self.selected]
        self.name_var.set(profile["name"])
        self.local_var.set(profile["local_dimming"])
        self.brightness_var.set(profile.get("brightness", 100))
        self.brightness_scale.set(profile.get("brightness", 100))
        self.halo_var.set(profile["halo"])
        self.halo_scale.set(profile["halo"])
        self.hdr_var.set(bool(profile.get("hdr", False)))
        self.on_hdr_toggle()
        hotkey = str(profile.get("hotkey", "Ctrl+Alt+0"))
        digit = hotkey.rsplit("+", 1)[-1] if hotkey.rsplit("+", 1)[-1] in "0123456789" else "0"
        self.hotkey_digit_var.set(digit)

    def on_select(self, _event=None) -> None:
        selection = self.profile_list.curselection()
        if selection:
            self.select_profile(selection[0])

    def on_halo_slide(self, value: str) -> None:
        halo = int(round(float(value)))
        self.halo_var.set(halo)

    def on_halo_input(self, _event=None) -> None:
        try:
            halo = max(0, min(100, int(self.halo_var.get())))
        except (ValueError, tk.TclError):
            return
        self.halo_var.set(halo)
        self.halo_scale.set(halo)

    def on_brightness_slide(self, value: str) -> None:
        self.brightness_var.set(int(round(float(value))))

    def on_brightness_input(self, _event=None) -> None:
        try:
            value = max(0, min(100, int(self.brightness_var.get())))
        except (ValueError, tk.TclError):
            return
        self.brightness_var.set(value)
        self.brightness_scale.set(value)

    def on_hdr_toggle(self) -> None:
        if self.hdr_var.get():
            self.brightness_label.grid_remove()
            self.brightness_row.grid_remove()
            self.halo_title_label.grid_remove()
            self.halo_row.grid_remove()
        else:
            self.brightness_label.grid()
            self.brightness_row.grid()
            self.halo_title_label.grid()
            self.halo_row.grid()

    def add_profile(self) -> None:
        if len(self.profiles) >= MAX_PROFILES:
            messagebox.showinfo(APP_NAME, self.t("max_profiles"))
            return
        number = len(self.profiles) + 1
        hotkey_number = number if number < 10 else 0
        self.profiles.append(
            {
                "name": self.t("profile", number=number),
                "local_dimming": "Off",
                "brightness": 100,
                "halo": 0,
                "hdr": False,
                "hotkey": f"Ctrl+Alt+{hotkey_number}",
            }
        )
        self.refresh_list()
        self.select_profile(len(self.profiles) - 1)

    def delete_profile(self) -> None:
        if len(self.profiles) == 1:
            messagebox.showinfo(APP_NAME, self.t("one_profile"))
            return
        del self.profiles[self.selected]
        self.refresh_list()
        self.select_profile(min(self.selected, len(self.profiles) - 1))
        self.persist_and_register()

    def save_current(self) -> bool:
        name = self.name_var.get().strip()
        if not name:
            messagebox.showwarning(APP_NAME, self.t("enter_name"))
            return False
        hotkey = f"Ctrl+Alt+{self.hotkey_digit_var.get()}"
        duplicate = next(
            (i for i, profile in enumerate(self.profiles) if i != self.selected and profile["hotkey"].upper() == hotkey.upper()),
            None,
        )
        if duplicate is not None:
            messagebox.showwarning(APP_NAME, self.t("duplicate_hotkey"))
            return False
        try:
            halo = max(0, min(100, int(self.halo_var.get())))
        except (ValueError, tk.TclError):
            halo = 0
            self.halo_var.set(halo)
            self.halo_scale.set(halo)
        try:
            brightness = max(0, min(100, int(self.brightness_var.get())))
        except (ValueError, tk.TclError):
            brightness = 100
            self.brightness_var.set(brightness)
            self.brightness_scale.set(brightness)
        self.profiles[self.selected] = {
            "name": name,
            "local_dimming": self.local_var.get(),
            "brightness": brightness,
            "halo": halo,
            "hdr": bool(self.hdr_var.get()),
            "hotkey": hotkey,
        }
        if self.persist_and_register():
            self.refresh_list()
            self.select_profile(self.selected)
            self.status_var.set(self.t("saved"))
            return True
        return False

    def save_and_apply(self) -> None:
        if self.save_current():
            self.apply_profile(self.selected)

    def persist_and_register(self) -> bool:
        try:
            self.hotkeys.start(self.profiles)
            save_settings(self.profiles, self.language, self.selected_monitor)
            return True
        except (OSError, ValueError, RuntimeError) as error:
            messagebox.showerror(APP_NAME, str(error))
            return False

    def apply_profile(self, index: int) -> None:
        if index < 0 or index >= len(self.profiles):
            return
        profile = dict(self.profiles[index])
        selected_monitor = self.selected_monitor
        self.status_var.set(self.t("applying", name=profile["name"]))

        def work():
            if not self.apply_lock.acquire(blocking=False):
                return
            try:
                apply_monitor_profile(
                    profile["local_dimming"], int(profile.get("brightness", 100)),
                    int(profile["halo"]), bool(profile.get("hdr", False)), selected_monitor,
                )
            except Exception as error:
                self.root.after(0, self.apply_failed, str(error))
            else:
                self.root.after(0, self.apply_succeeded, profile)
            finally:
                self.apply_lock.release()

        threading.Thread(target=work, daemon=True).start()

    def apply_failed(self, error: str) -> None:
        self.status_var.set(self.t("apply_error"))
        messagebox.showerror(APP_NAME, error)

    def apply_succeeded(self, profile: dict) -> None:
        self.status_var.set(self.t("applied", name=profile["name"]))
        self.show_osd(profile)

    def show_osd(self, profile: dict) -> None:
        popup = tk.Toplevel(self.root)
        popup.overrideredirect(True)
        popup.attributes("-topmost", True)
        popup.attributes("-alpha", 0.96)
        popup.configure(bg="#101318")
        frame = tk.Frame(popup, bg="#101318", padx=22, pady=15)
        frame.pack()
        tk.Label(
            frame,
            text=profile["name"],
            bg="#101318",
            fg="#ffffff",
            font=(UI_FONT, 11, "bold"),
        ).pack(anchor="w")
        details = (
            f"{self.t('local')}: {profile['local_dimming']}    HDR: {self.t('on')}"
            if profile.get("hdr", False)
            else f"{self.t('local')}: {profile['local_dimming']}    "
                 f"{self.t('brightness')}: {profile.get('brightness', 100)}    "
                 f"{self.t('halo')}: {profile['halo']}    HDR: {self.t('off')}"
        )
        tk.Label(
            frame,
            text=details,
            bg="#101318",
            fg="#aeb6c2",
            font=(UI_FONT, 10),
        ).pack(anchor="w", pady=(4, 0))
        popup.update_idletasks()
        width = popup.winfo_reqwidth()
        height = popup.winfo_reqheight()
        x = (popup.winfo_screenwidth() - width) // 2
        y = popup.winfo_screenheight() - height - 90
        popup.geometry(f"{width}x{height}+{x}+{y}")

        def fade(alpha=0.96):
            alpha -= 0.08
            if alpha <= 0:
                popup.destroy()
            else:
                popup.attributes("-alpha", alpha)
                popup.after(35, fade, alpha)

        popup.after(1600, fade)

    def tray_menu(self):
        import pystray
        return pystray.Menu(
            pystray.MenuItem(self.t("open"), self.show_window, default=True),
            pystray.MenuItem(self.t("exit"), self.exit_application),
        )

    def start_tray(self) -> None:
        icon_path = resource_path("ta-icon-black.png")
        if sys.platform == "linux":
            try:
                self.tray_icon = backend.TrayIcon(
                    self.root, icon_path, self.t("open"), self.t("exit"),
                    self.show_window, self.exit_application,
                )
            except RuntimeError as error:
                self.tray_icon = None
                messagebox.showwarning(APP_NAME, str(error))
            return
        import pystray
        from PIL import Image
        image = Image.open(icon_path).convert("RGBA")
        self.tray_icon = pystray.Icon(
            "TitanArmyControl",
            image,
            APP_NAME,
            self.tray_menu(),
        )
        self.tray_icon.run_detached()

    def hide_to_tray(self) -> None:
        if self.tray_icon:
            self.root.withdraw()
        else:
            self.close()

    def show_window(self, _icon=None, _item=None) -> None:
        self.root.after(0, self._show_window_on_ui_thread)

    def _show_window_on_ui_thread(self) -> None:
        self.root.deiconify()
        self.root.lift()
        self.root.focus_force()

    def exit_application(self, _icon=None, _item=None) -> None:
        self.root.after(0, self.close)

    def close(self) -> None:
        if self.exiting:
            return
        self.exiting = True
        if self.tray_icon:
            self.tray_icon.stop()
            self.tray_icon = None
        self.hotkeys.stop()
        self.root.destroy()


def main() -> None:
    parser = argparse.ArgumentParser(description=APP_NAME)
    parser.add_argument("--version", action="version", version=f"{APP_NAME} {VERSION}")
    parser.add_argument("--minimized", action="store_true")
    parser.add_argument("--apply-profile", type=int, metavar="INDEX")
    args = parser.parse_args()
    if args.apply_profile is not None:
        profiles, _language, selected_monitor = load_settings()
        if not 0 <= args.apply_profile < len(profiles):
            parser.error("profile index out of range")
        profile = profiles[args.apply_profile]
        try:
            apply_monitor_profile(
                profile["local_dimming"], int(profile.get("brightness", 100)),
                int(profile["halo"]), bool(profile.get("hdr", False)), selected_monitor,
            )
        except Exception as error:
            if sys.platform == "linux" and shutil.which("notify-send"):
                subprocess.run(
                    ["notify-send", "-u", "critical", APP_NAME, str(error)],
                    check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                )
            raise
        if sys.platform == "linux" and shutil.which("notify-send"):
            subprocess.run(
                ["notify-send", APP_NAME, f"{profile['name']} applied"],
                check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
        return
    if not backend.acquire_single_instance():
        return
    root = tk.Tk()
    try:
        app = App(root)
        if sys.platform == "linux":
            backend.start_instance_listener(root, app.show_window)
        root.mainloop()
    finally:
        backend.release_single_instance()


if __name__ == "__main__":
    main()
