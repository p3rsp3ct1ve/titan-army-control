#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

version=$(sed -n 's/^VERSION = "\([^"]*\)"$/\1/p' TitanArmyControl/version.py)
if [[ -z "$version" ]]; then
    echo "Application version is missing" >&2
    exit 1
fi
package_dir=$(mktemp -d)
trap 'rm -rf "$package_dir"' EXIT
app_dir="$package_dir/usr/lib/titan-army-control"
install -d "$app_dir/TitanArmyControl" "$package_dir/usr/bin" \
    "$package_dir/usr/share/applications" "$package_dir/DEBIAN"
install -m644 run_app.py "$app_dir/run_app.py"
install -m644 TitanArmyControl/{__init__,app,linux_backend,hdr_helper,tray_helper,version}.py \
    "$app_dir/TitanArmyControl/"
install -m644 TitanArmyControl/{ta-logo-white,ta-icon-black}.png \
    "$app_dir/TitanArmyControl/"
cat > "$package_dir/usr/bin/titan-army-control" <<'EOF'
#!/bin/sh
exec /usr/bin/python3 /usr/lib/titan-army-control/run_app.py "$@"
EOF
chmod 755 "$package_dir/usr/bin/titan-army-control"
install -Dm644 TitanArmyControl/ta-icon-black.png "$package_dir/usr/share/icons/hicolor/256x256/apps/titan-army-control.png"
cat > "$package_dir/usr/share/applications/titan-army-control.desktop" <<'EOF'
[Desktop Entry]
Type=Application
Name=Titan Army Control
Exec=titan-army-control
Icon=titan-army-control
Categories=Settings;Utility;
Terminal=false
EOF
cat > "$package_dir/DEBIAN/control" <<EOF
Package: titan-army-control
Version: $version
Architecture: all
Maintainer: Titan Army Control
Depends: python3-tk, python3-gi, gir1.2-gtk-3.0, gir1.2-ayatanaappindicator3-0.1, fonts-dejavu-core, ddcutil
Description: Titan Army monitor profile controller
EOF
dpkg-deb --build --root-owner-group "$package_dir" "dist/titan-army-control_${version}_all.deb"
