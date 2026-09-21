# Titan Army Control

Один интерфейс и одни профили для Windows и Linux (Ubuntu GNOME/Wayland).

## Возможности

- До 10 профилей, Local Dimming, яркость и Halo Control.
- Включение и выключение системного HDR для выбранного монитора.
- Глобальные горячие клавиши `Ctrl+Alt+0…9`, трей, автозапуск и экранное уведомление.
- Русский и английский интерфейс, выбор монитора.
- В HDR-профиле яркость и Halo скрыты и не применяются.

## Сборка

- Windows: запустите `build-windows.ps1` в PowerShell. Результат: `dist/TitanArmyControl.exe`.
- Linux: запустите `bash build-linux-deb.sh`. Результат: пакет `.deb` в `dist/`. При установке `apt` подтянет системный Python, Tk 8.6, шрифт и компоненты трея.

PyInstaller собирает бинарник для той ОС, на которой запущен. Для обновления обоих файлов нужно выполнить каждый сценарий на соответствующей ОС.

## Linux

Для работы приложения нужны `ddcutil` (поиск мониторов), системный Mutter (HDR в GNOME) и доступ пользователя к `/dev/i2c-*`. Для трея нужны `python3-gi`, `gir1.2-gtk-3.0` и `gir1.2-ayatanaappindicator3-0.1`; на GNOME также должно быть включено расширение AppIndicator. В Ubuntu эти пакеты можно установить так:

```bash
sudo apt install ddcutil python3-gi gir1.2-gtk-3.0 gir1.2-ayatanaappindicator3-0.1
```

Для доступа без `sudo` добавьте пользователя в группу `i2c` и войдите в сеанс заново:

```bash
sudo usermod -aG i2c "$USER"
```

Проверьте доступ командой `ddcutil detect` **без `sudo`**. Если система не даёт группе `i2c` права на `/dev/i2c-*`, понадобится правило udev для этой группы.

Linux-бэкенд отправляет записи `0x99 → 0x47` (Local Dimming) и `0x99 → 0x46` (Halo Control) через один открытый I²C-дескриптор с паузой 65 мс. Именно эта последовательность проверена на P275MS PLUS+ через DisplayPort. Яркость записывается через `0x10`.

HDR в GNOME переключается через Mutter DisplayConfig: приложение сохраняет текущую схему экранов и меняет цветовой режим только выбранного выхода. Его работу на конкретном мониторе нужно подтвердить после запуска Linux-билда.

На GNOME глобальные сочетания создаются в `gsettings` как пользовательские горячие клавиши. Они запускают бинарник с `--apply-profile N`. Приложение сохраняет остальные пользовательские сочетания.

Настройки Linux: `~/.config/titan-army-control/profiles.json`; Windows: `%APPDATA%\TitanArmyControl\profiles.json`.

## Проверка без GUI

```bash
./dist/TitanArmyControl-linux --help
./dist/TitanArmyControl-linux --apply-profile 0
```

Вторая команда применяет профиль с индексом 0 и меняет настройки монитора.
