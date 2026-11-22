"""Windows açılışında başlatma (HKCU\\...\\Run altında "Insomnia" değeri).

is_enabled yalnızca okur; kayıt defterine hiçbir zaman kendiliğinden yazmaz.
Değer başka bir kopyayı gösteriyorsa "kapalı" sayılır; kullanıcı açarsa bu
kopyanın yolu yazılır.
"""

import os
import sys
import winreg

from . import APP_NAME

_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"


def command() -> str:
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}" --tray'
    main_py = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "main.py")
    pythonw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
    exe = pythonw if os.path.exists(pythonw) else sys.executable
    return f'"{exe}" "{main_py}" --tray'


def current_value() -> str | None:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY, 0, winreg.KEY_READ) as key:
            value, _ = winreg.QueryValueEx(key, APP_NAME)
            return value if isinstance(value, str) else None
    except OSError:
        return None


def is_enabled() -> bool:
    value = current_value()
    return value is not None and value.strip().lower() == command().lower()


def enable() -> bool:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
            winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, command())
        return True
    except OSError:
        return False


def disable() -> bool:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
            winreg.DeleteValue(key, APP_NAME)
        return True
    except FileNotFoundError:
        return True
    except OSError:
        return False


def toggle() -> bool:
    """Yeni durumu döndürür."""
    if is_enabled():
        disable()
        return False
    return enable()
