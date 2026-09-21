"""System GTK AppIndicator process for the Linux packaged application."""

from __future__ import annotations

import json
import sys

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("AyatanaAppIndicator3", "0.1")
from gi.repository import AyatanaAppIndicator3, GLib, Gtk  # noqa: E402


def main() -> None:
    icon_path, open_label, exit_label = sys.argv[1:4]
    initialized, _argv = Gtk.init_check(None)
    if not initialized:
        raise RuntimeError("GTK could not connect to the desktop session")
    indicator = AyatanaAppIndicator3.Indicator.new(
        "titan-army-control", icon_path,
        AyatanaAppIndicator3.IndicatorCategory.APPLICATION_STATUS,
    )
    indicator.set_status(AyatanaAppIndicator3.IndicatorStatus.ACTIVE)

    def set_menu(open_text: str, exit_text: str) -> None:
        menu = Gtk.Menu()
        for label, command in ((open_text, "OPEN"), (exit_text, "EXIT")):
            item = Gtk.MenuItem(label=label)
            item.connect("activate", lambda _item, value=command: print(value, flush=True))
            menu.append(item)
        menu.show_all()
        indicator.set_menu(menu)

    set_menu(open_label, exit_label)

    def on_stdin(_source, _condition):
        line = sys.stdin.readline()
        if not line:
            Gtk.main_quit()
            return False
        command = json.loads(line)
        if command.get("type") == "labels":
            set_menu(command["open"], command["exit"])
        elif command.get("type") == "quit":
            Gtk.main_quit()
            return False
        return True

    GLib.io_add_watch(sys.stdin, GLib.IO_IN | GLib.IO_HUP, on_stdin)
    print("READY", flush=True)
    Gtk.main()


if __name__ == "__main__":
    main()
