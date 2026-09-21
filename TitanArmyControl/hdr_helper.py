"""Change one GNOME monitor's HDR state while preserving the display layout."""

from __future__ import annotations

import sys


def plain(value):
    return value.unpack() if hasattr(value, "unpack") else value


def current_configuration(state, target: str, enabled: bool):
    serial, monitors, logical_monitors, properties = state
    monitor_by_connector = {monitor[0][0]: monitor for monitor in monitors}
    if target not in monitor_by_connector:
        raise RuntimeError(f"GNOME monitor {target} is disconnected")
    target_properties = monitor_by_connector[target][2]
    supported = plain(target_properties.get("supported-color-modes", []))
    mode_value = 1 if enabled else 0
    if supported and mode_value not in supported:
        raise RuntimeError(f"GNOME does not support {'HDR' if enabled else 'SDR'} on {target}")
    current = plain(target_properties.get("color-mode", 0))
    if current == mode_value:
        return serial, [], properties, False

    result = []
    target_active = False
    for logical in logical_monitors:
        x, y, scale, transform, primary, physical, _logical_properties = logical
        physical_result = []
        for monitor_spec in physical:
            connector = monitor_spec[0]
            if connector == target:
                target_active = True
            monitor = monitor_by_connector[connector]
            current_mode = next(
                (mode[0] for mode in monitor[1] if "is-current" in mode[6]), None
            )
            if current_mode is None:
                raise RuntimeError(f"GNOME did not report a current mode for {connector}")
            monitor_properties = monitor[2]
            options = {}
            if connector == target:
                options["color-mode"] = mode_value
            elif "color-mode" in monitor_properties:
                options["color-mode"] = plain(monitor_properties["color-mode"])
            if "rgb-range" in monitor_properties:
                options["rgb-range"] = plain(monitor_properties["rgb-range"])
            physical_result.append((connector, current_mode, options))
        result.append((x, y, scale, transform, primary, physical_result))
    if not target_active:
        raise RuntimeError(f"GNOME monitor {target} is not active")
    return serial, result, properties, True


def main() -> None:
    import gi

    gi.require_version("Gio", "2.0")
    from gi.repository import Gio, GLib

    connector, state_text = sys.argv[1:3]
    enabled = state_text == "on"
    proxy = Gio.DBusProxy.new_for_bus_sync(
        Gio.BusType.SESSION, Gio.DBusProxyFlags.NONE, None,
        "org.gnome.Mutter.DisplayConfig", "/org/gnome/Mutter/DisplayConfig",
        "org.gnome.Mutter.DisplayConfig", None,
    )
    state = proxy.call_sync("GetCurrentState", None, Gio.DBusCallFlags.NO_AUTO_START, 10000, None)
    serial, logical, properties, changed = current_configuration(state, connector, enabled)
    if not changed:
        print("UNCHANGED")
        return
    variant_logical = []
    for x, y, scale, transform, primary, physical in logical:
        variant_physical = []
        for name, mode, options in physical:
            variant_physical.append((
                name, mode, {key: GLib.Variant("u", int(value)) for key, value in options.items()},
            ))
        variant_logical.append((x, y, scale, transform, primary, variant_physical))
    apply_properties = {}
    if plain(properties.get("supports-changing-layout-mode", False)):
        apply_properties["layout-mode"] = GLib.Variant("u", int(plain(properties["layout-mode"])))
    request = GLib.Variant(
        "(uua(iiduba(ssa{sv}))a{sv})",
        (serial, 1, variant_logical, apply_properties),
    )
    proxy.call_sync("ApplyMonitorsConfig", request, Gio.DBusCallFlags.NO_AUTO_START, 15000, None)
    print("CHANGED")


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"HDR switch failed: {error}", file=sys.stderr)
        raise SystemExit(1)
