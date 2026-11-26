"""Kalıcı ayarlar: %APPDATA%\\Insomnia\\settings.json.

Dosyadaki her değer okunurken denetlenir; bozuk ya da beklenmeyen bir değer
programı düşürmez, yerine varsayılan kullanılır. Bitiş işlemi (kapat, yeniden
başlat, hazırda beklet) bilerek saklanmaz: program her açılışta "hiçbir şey
yapma" ile başlar.
"""

import json
import os
import tempfile

from . import APP_NAME

MIN_MINUTES = 1
MAX_MINUTES = 1440
LANGUAGES = ("tr", "en", "de", "fr", "es")
# Program nerede görünsün: ikisi de, yalnız saatin yanı (tepsi), yalnız görev çubuğu
VISIBILITY = ("both", "tray", "taskbar")
REMINDER_TONES = ("soft", "alarm")  # reminders.TONES ile aynı (sınama denetler)

DEFAULTS = {
    "duration_minutes": 60,
    "infinite": False,
    "sound_enabled": True,
    "monitor_off": False,
    "language": "tr",
    "visibility": "both",
    "tray_hint_shown": False,
    "reminder_show": True,
    "reminder_sound": True,
    "reminder_tone": "soft",
    "reminder_minutes": 15,  # yeni hatırlatıcının başlangıç süresi (Ayarlar'dan değişir)
}


def config_dir() -> str:
    base = os.environ.get("APPDATA") or os.path.expanduser("~")
    return os.path.join(base, APP_NAME)


def config_path() -> str:
    return os.path.join(config_dir(), "settings.json")


def valid_minutes(value) -> bool:
    # bool, int'in alt sınıfıdır; True'nun 1 dakika sayılmasını istemeyiz.
    return isinstance(value, int) and not isinstance(value, bool) and MIN_MINUTES <= value <= MAX_MINUTES


def clean(data) -> dict:
    """Herhangi bir girdiden geçerli bir ayar sözlüğü üretir."""
    out = dict(DEFAULTS)
    if not isinstance(data, dict):
        return out
    for key in ("duration_minutes", "reminder_minutes"):
        if valid_minutes(data.get(key)):
            out[key] = data[key]
    for key in ("infinite", "sound_enabled", "monitor_off", "tray_hint_shown", "reminder_show", "reminder_sound"):
        if isinstance(data.get(key), bool):
            out[key] = data[key]
    if data.get("language") in LANGUAGES:
        out["language"] = data["language"]
    if data.get("visibility") in VISIBILITY:
        out["visibility"] = data["visibility"]
    if data.get("reminder_tone") in REMINDER_TONES:
        out["reminder_tone"] = data["reminder_tone"]
    return out


def load(path: str | None = None) -> dict:
    try:
        with open(path or config_path(), "r", encoding="utf-8") as f:
            return clean(json.load(f))
    except (OSError, ValueError):
        return dict(DEFAULTS)


def save(settings: dict, path: str | None = None) -> bool:
    """Önce geçici dosyaya yazar, sonra yerine koyar; yarım dosya kalmaz."""
    path = path or config_path()
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), prefix="settings-", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(clean(settings), f, indent=2, ensure_ascii=False)
            os.replace(tmp, path)
        except BaseException:
            try:
                os.remove(tmp)
            except OSError:
                pass
            raise
        return True
    except OSError:
        return False
