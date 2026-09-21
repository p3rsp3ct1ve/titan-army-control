# Titan Army Control

Приложение для управления профилями мониторов Titan Army в Windows и Linux. Поддерживает Local Dimming, яркость, Halo Control, HDR, горячие клавиши и трей. Подробности и требования Linux — в [документации](TitanArmyControl/README.md).

## Готовые приложения

Скачивайте файлы со страницы **Releases**:

- Windows: `TitanArmyControl.exe` — запустите файл без установки.
- Ubuntu/Debian: `titan-army-control_0.1.3_all.deb` — установите пакет через менеджер пакетов.
- Другие системы Linux: исходники можно собрать локально; готовый `TitanArmyControl-linux` также можно приложить к Release, если он проверен на целевой системе.

Для работы с монитором нужны совместимый Titan Army и доступ к его управлению через DDC/CI. Проверенная последовательность команд описана в документации.

## Сборка из исходников

PyInstaller собирает приложение для той операционной системы, на которой запущен.

**Windows:** установите Python 3.12 с Tk/Tcl, затем в PowerShell из корня репозитория выполните:

```powershell
.\build-windows.ps1
```

Скрипт установит `pyinstaller`, `pillow` и `pystray` в локальное окружение. Результат: `dist/windows-0.1.3/TitanArmyControl.exe`.

**Ubuntu/Debian:** для пакета выполните:

```bash
bash build-linux-deb.sh
```

Результат: `dist/titan-army-control_0.1.3_all.deb`. Для автономного Linux-бинарника нужен Python 3 с Tk/Tcl и `bash build-linux.sh`; результат — `dist/TitanArmyControl-linux`.

Версия хранится в `TitanArmyControl/version.py`. Исходники приложены к каждому тегу GitHub автоматически; собранные приложения нужно прикреплять к Release отдельно.
