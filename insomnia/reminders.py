"""Tek seferlik hatırlatıcılar: %APPDATA%\\Insomnia\\reminders.json.

Oturum sayacından (engine.py) bağımsızdır ve onun tersine gerçek saate bakar:
bilgisayar uyusa da, program kapanıp açılsa da hatırlatıcı kaybolmaz; saati
geçmişse ilk denetimde "kaçırıldı" diye gösterilir. Hatırlatıcı bilgisayarı
uyanık tutmaz ve uykudan uyandırmaz.

Ekranda gösterilen hatırlatıcı kullanıcı "Tamam" ya da "Ertele" diyene kadar
dosyada kalır; program o sırada kapanırsa sonraki açılışta yeniden gösterilir.
Yalnız sesli hatırlatıcının onaylanacak bir ekranı yoktur: son zilinden sonra
kendiliğinden kapanır (yoksa her açılışta yeniden çalardı).
"""

import io
import json
import math
import os
import re
import secrets
import struct
import tempfile
import threading
import time
import wave
from datetime import datetime, timedelta

from . import settings

MAX_ITEMS = 3  # bekleyen hatırlatıcı sayısı: paneldeki listeye kaydırmadan sığan kadar (arayüzde ölçüldü)
NOTE_MAX = 80
SNOOZE_SECONDS = 600
RINGS = 3  # bakılmazsa zil en çok bu kadar çalar
RING_EVERY = 60
LATE_AFTER = 120  # bundan fazla gecikme = kaçırıldı (bilgisayar kapalıydı ya da uyuyordu)
MIN_LEFT = 60  # süre kısaltılırken kalan süre bunun altına inemez
TONES = ("soft", "alarm")  # yumuşak çan / belirgin alarm

_CLOCK = re.compile(r"^(\d{1,2})[:.](\d{2})$")


def file_path() -> str:
    return os.path.join(settings.config_dir(), "reminders.json")


_RATE = 22050
_wav_cache: dict[str, bytes] = {}


def _soft_samples() -> list[float]:
    """Yumuşak çan: sönerek biten iki nota (ding-dong), yaklaşık 1,4 saniye."""
    total = int(_RATE * 1.4)
    out = [0.0] * total
    # (başlangıç sn, frekans): mi5 -> do5. Üst sesler daha çabuk söner; çan tınısını bu verir.
    for start, freq in ((0.0, 659.25), (0.42, 523.25)):
        first = int(start * _RATE)
        for i in range(first, total):
            t = (i - first) / _RATE
            attack = min(1.0, t / 0.008)
            value = (
                math.sin(2 * math.pi * freq * t) * math.exp(-t / 0.38)
                + 0.30 * math.sin(2 * math.pi * freq * 2 * t) * math.exp(-t / 0.20)
                + 0.12 * math.sin(2 * math.pi * freq * 3 * t) * math.exp(-t / 0.10)
            )
            out[i] += 0.42 * attack * value
    fade = int(_RATE * 0.12)  # son kısım sıfıra iner; yoksa ses "çıt" diye kesilir
    for k in range(fade):
        out[total - 1 - k] *= k / fade
    return out


def _alarm_samples() -> list[float]:
    """Belirgin alarm: üç kısa darbe, kısa ara, yeniden üç darbe; yaklaşık 1,8 saniye."""
    pulse, gap, pause, edge = 0.13, 0.09, 0.42, 0.012
    out: list[float] = []
    for group in range(2):
        for _ in range(3):
            count = int(pulse * _RATE)
            for i in range(count):
                t = i / _RATE
                # Başı ve sonu yuvarlatılır; yoksa her darbe "çıt" diye başlar.
                env = min(1.0, t / edge, (pulse - t) / edge)
                env = 0.5 - 0.5 * math.cos(math.pi * max(0.0, env))
                value = math.sin(2 * math.pi * 987.77 * t) + 0.5 * math.sin(2 * math.pi * 1481.66 * t)
                out.append(0.40 * env * value)
            out.extend([0.0] * int(gap * _RATE))
        if group == 0:
            out.extend([0.0] * int(pause * _RATE))
    return out


def tone_wav(tone: str) -> bytes:
    """Sesi bellekte WAV olarak üretir (dosya gerekmez, her bilgisayarda aynı duyulur)."""
    if tone not in TONES:
        tone = TONES[0]
    if tone not in _wav_cache:
        samples = _soft_samples() if tone == "soft" else _alarm_samples()
        frames = b"".join(struct.pack("<h", int(max(-1.0, min(1.0, v)) * 32767)) for v in samples)
        buffer = io.BytesIO()
        with wave.open(buffer, "wb") as f:
            f.setnchannels(1)
            f.setsampwidth(2)
            f.setframerate(_RATE)
            f.writeframes(frames)
        _wav_cache[tone] = buffer.getvalue()
    return _wav_cache[tone]


def play(tone: str = "soft") -> None:
    """Hatırlatıcı sesini çalar; çağıranı bekletmez."""

    def _play():
        try:
            import winsound

            # Bellekten çalma yalnız eşzamanlı yapılabiliyor; bu yüzden ayrı iş parçacığında.
            winsound.PlaySound(tone_wav(tone), winsound.SND_MEMORY | winsound.SND_NODEFAULT)
        except Exception:
            pass

    threading.Thread(target=_play, name="insomnia-chime", daemon=True).start()


def clean_note(value) -> str:
    if not isinstance(value, str):
        return ""
    return " ".join(value.split())[:NOTE_MAX]


def parse_clock(value):
    """"9:05" / "09.05" -> (9, 5); geçersizse None."""
    if not isinstance(value, str):
        return None
    match = _CLOCK.match(value.strip())
    if not match:
        return None
    hour, minute = int(match.group(1)), int(match.group(2))
    return (hour, minute) if hour < 24 and minute < 60 else None


def _clean_item(data):
    if not isinstance(data, dict):
        return None
    at = data.get("at")
    if not isinstance(at, (int, float)) or isinstance(at, bool) or not 0 < at < 1e11:
        return None
    ident = data.get("id")
    if not isinstance(ident, str) or not 0 < len(ident) <= 40:
        return None
    show, sound = data.get("show"), data.get("sound")
    if not isinstance(show, bool) or not isinstance(sound, bool):
        return None
    if not (show or sound):
        show = True
    tone = data.get("tone") if data.get("tone") in TONES else TONES[0]  # eski dosyada yok
    span = data.get("span")
    if not isinstance(span, (int, float)) or isinstance(span, bool) or not 0 < span <= 2 * 86400:
        span = 0  # bilinmiyor: ilk bakışta kalan süre sayılır
    return {
        "id": ident, "at": float(at), "note": clean_note(data.get("note")),
        "show": show, "sound": sound, "tone": tone, "span": float(span),
    }


class Reminders:
    TICK = 0.5

    def __init__(self, path=None, now=time.time, on_show=None, on_sound=None, on_notify=None):
        self._path = path or file_path()
        self._now = now
        self._on_show = on_show  # ekranda gösterilecek hatırlatıcı geldi
        self._on_sound = on_sound  # ses çal; çalınacak sesin adını alır (bkz. TONES)
        self._on_notify = on_notify  # yalnız sesli hatırlatıcının notu (saatin yanında baloncuk)
        self._lock = threading.RLock()
        self._pending: list[dict] = []  # zamanı gelmemiş, saate göre sıralı
        self._due: list[dict] = []  # zamanı gelmiş, kullanıcıyı bekliyor
        self._stop = threading.Event()
        self._thread = None
        self._load()

    # ------------------------------------------------------------------ #
    #  Dışarıdan çağrılanlar (her iş parçacığından güvenli)               #
    # ------------------------------------------------------------------ #

    def add(self, minutes=None, clock=None, note="", show=True, sound=True, tone="soft") -> dict:
        """`minutes` dakika sonra ya da `clock` ("SS:DD") saatinde hatırlatır; yalnız biri verilir."""
        if not isinstance(show, bool) or not isinstance(sound, bool) or not (show or sound):
            return {"ok": False, "error": "bad_request"}
        if tone not in TONES:
            return {"ok": False, "error": "bad_tone"}
        if (minutes is None) == (clock is None):
            return {"ok": False, "error": "bad_request"}
        with self._lock:
            now = self._now()
            if minutes is not None:
                if not settings.valid_minutes(minutes):
                    return {"ok": False, "error": "bad_minutes"}
                at = now + minutes * 60
            else:
                parsed = parse_clock(clock)
                if parsed is None:
                    return {"ok": False, "error": "bad_clock"}
                target = datetime.fromtimestamp(now).replace(hour=parsed[0], minute=parsed[1], second=0, microsecond=0)
                if target.timestamp() <= now:
                    target += timedelta(days=1)  # saat bugün geçtiyse yarın
                at = target.timestamp()
            if len(self._pending) >= MAX_ITEMS:
                return {"ok": False, "error": "full"}
            item = {
                "id": secrets.token_hex(6), "at": at, "note": clean_note(note),
                "show": show, "sound": sound, "tone": tone, "span": at - now,
            }
            self._insert(item)
            self._save()
            return {"ok": True, "id": item["id"]}

    def remove(self, ident) -> dict:
        """Bekleyen ya da zamanı gelmiş hatırlatıcıyı siler."""
        with self._lock:
            before = len(self._pending) + len(self._due)
            self._pending = [i for i in self._pending if i["id"] != ident]
            self._due = [i for i in self._due if i["id"] != ident]
            if len(self._pending) + len(self._due) == before:
                return {"ok": False}
            self._save()
            return {"ok": True}

    def dismiss(self, ident) -> dict:
        """Zamanı gelmiş hatırlatıcıyı kapatır ("Tamam")."""
        with self._lock:
            if not any(i["id"] == ident for i in self._due):
                return {"ok": False}
            return self.remove(ident)

    def snooze(self, ident) -> dict:
        """Zamanı gelmiş hatırlatıcıyı 10 dakika sonraya atar."""
        with self._lock:
            for item in self._due:
                if item["id"] == ident:
                    self._due.remove(item)
                    again = {k: item[k] for k in ("id", "note", "show", "sound", "tone")}
                    again["at"] = self._now() + SNOOZE_SECONDS
                    again["span"] = float(SNOOZE_SECONDS)
                    self._insert(again)
                    self._save()
                    return {"ok": True}
            return {"ok": False}

    def adjust(self, ident, seconds) -> dict:
        """Bekleyen hatırlatıcıyı ileri (artı) ya da geri (eksi) alır."""
        if not isinstance(seconds, int) or isinstance(seconds, bool) or seconds == 0:
            return {"ok": False, "error": "bad_request"}
        with self._lock:
            for item in self._pending:
                if item["id"] == ident:
                    left = item["at"] - self._now() + seconds
                    if left < MIN_LEFT:
                        return {"ok": False, "error": "too_short"}
                    if left > settings.MAX_MINUTES * 60:
                        return {"ok": False, "error": "too_long"}
                    item["at"] += seconds
                    item["span"] = max(item["span"] + seconds, left)
                    self._pending.sort(key=lambda i: i["at"])
                    self._save()
                    return {"ok": True}
            return {"ok": False, "error": "not_found"}

    def has_any(self) -> bool:
        with self._lock:
            return bool(self._pending or self._due)

    def snapshot(self, detail=False) -> dict:
        """`detail`: kalan ve toplam saniyeler de eklenir (kumanda kapısı için; her saniye değişir)."""
        with self._lock:
            now = self._now()
            today = datetime.fromtimestamp(now).date()
            pending = []
            for item in self._pending:
                when = datetime.fromtimestamp(item["at"])
                pending.append({
                    "id": item["id"],
                    "time": when.strftime("%H:%M"),
                    "tomorrow": when.date() != today,
                    "note": item["note"],
                    "show": item["show"],
                    "sound": item["sound"],
                })
                if detail:
                    left = max(0, math.ceil(item["at"] - now))
                    pending[-1].update(left=left, span=max(left, round(item["span"])))
            due = None
            if self._due:
                first = self._due[0]
                due = {
                    "id": first["id"],
                    "note": first["note"],
                    "time": datetime.fromtimestamp(first["at"]).strftime("%H:%M"),
                    "late": first["late"],
                    "more": len(self._due) - 1,
                }
            return {"pending": pending, "due": due, "max": MAX_ITEMS, "snooze": SNOOZE_SECONDS // 60}

    # ------------------------------------------------------------------ #
    #  Denetim                                                            #
    # ------------------------------------------------------------------ #

    def start(self) -> None:
        if self._thread is None:
            self._thread = threading.Thread(target=self._run, name="insomnia-reminders", daemon=True)
            self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def _run(self):
        while not self._stop.wait(self.TICK):
            try:
                self.step()
            except Exception:
                pass

    def step(self):
        """Bir denetim turu. Sınamalar iş parçacığı olmadan bunu doğrudan çağırır."""
        show = False
        ring = None  # çalınacak ses; aynı turda birkaç hatırlatıcı varsa tek ses, belirgin olan öncelikli
        notes = []
        with self._lock:
            now = self._now()
            while self._pending and self._pending[0]["at"] <= now:
                item = self._pending.pop(0)
                item["late"] = now - item["at"] > LATE_AFTER
                # Kaçırılmış hatırlatıcı bir kez çalar: saatler sonra üç kez çalmasının anlamı yok.
                item["rings"] = (1 if item["late"] else RINGS) if item["sound"] else 0
                item["next_ring"] = now
                self._due.append(item)
                if item["show"]:
                    show = True
                else:
                    notes.append(item["note"])
            for item in self._due:
                if item["rings"] > 0 and now >= item["next_ring"]:
                    item["rings"] -= 1
                    item["next_ring"] = now + RING_EVERY
                    if ring != "alarm":
                        ring = item["tone"]
            finished = [item["id"] for item in self._due if not item["show"] and item["rings"] <= 0]
            if finished:
                self._due = [item for item in self._due if item["id"] not in finished]
                self._save()
        if ring and self._on_sound:
            self._safe(self._on_sound, ring)
        if show and self._on_show:
            self._safe(self._on_show)
        if self._on_notify:
            for note in notes:
                self._safe(self._on_notify, note)

    @staticmethod
    def _safe(callback, *args):
        try:
            callback(*args)
        except Exception:
            pass

    # ------------------------------------------------------------------ #
    #  Saklama                                                            #
    # ------------------------------------------------------------------ #

    def _insert(self, item):
        self._pending.append(item)
        self._pending.sort(key=lambda i: i["at"])

    def _load(self):
        try:
            with open(self._path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, ValueError):
            return
        items = data.get("items") if isinstance(data, dict) else None
        if not isinstance(items, list):
            return
        seen = set()
        for raw in items:
            item = _clean_item(raw)
            if item and item["id"] not in seen:
                seen.add(item["id"])
                self._pending.append(item)
        self._pending.sort(key=lambda i: i["at"])
        del self._pending[MAX_ITEMS * 2:]

    def _save(self) -> bool:
        """Önce geçici dosyaya yazar, sonra yerine koyar; yarım dosya kalmaz."""
        items = [
            {k: item[k] for k in ("id", "at", "note", "show", "sound", "tone", "span")}
            for item in sorted(self._due + self._pending, key=lambda i: i["at"])
        ]
        try:
            os.makedirs(os.path.dirname(self._path), exist_ok=True)
            fd, tmp = tempfile.mkstemp(dir=os.path.dirname(self._path), prefix="reminders-", suffix=".tmp")
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    json.dump({"items": items}, f, indent=2, ensure_ascii=False)
                os.replace(tmp, self._path)
            except BaseException:
                try:
                    os.remove(tmp)
                except OSError:
                    pass
                raise
            return True
        except OSError:
            return False
