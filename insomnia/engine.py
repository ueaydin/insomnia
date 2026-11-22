"""Oturum zamanlayıcısı.

Tek bir kalıcı iş parçacığı hem zamanı sayar hem de Windows'a "uyuma" isteğini
verir (SetThreadExecutionState iş parçacığına bağlı olduğu için ikisi aynı
yerde durmalı). Bütün komutlar bu iş parçacığında sırayla işlenir; aynı anda
iki sayaç çalışması mümkün değildir.

Süre bir bitiş anına (time.monotonic) göre hesaplanır, saniye saniye
eksiltilmez; böylece sayaç kaymaz. İki denetim arasında 30 saniyeden uzun bir
boşluk görülürse bilgisayar uyumuş demektir: oturum bitiş işlemi yapılmadan
durdurulur. Bilgisayarı uyandıran kişi karşısında kapanan bir bilgisayar bulmaz.
"""

import math
import queue
import threading
import time
from datetime import datetime, timedelta

from .power import ACTIONS
from .settings import valid_minutes

IDLE = "idle"
RUNNING = "running"
WARNING = "warning"


class Engine(threading.Thread):
    TICK = 0.25  # saniye; komut bekleme ve denetim aralığı
    WARNING_SECONDS = 60  # bitiş işleminden önce vazgeçme süresi
    SCREEN_DELAY = 10  # ekranı kapatmadan önceki geri sayım
    SUSPEND_GAP = 30  # bundan uzun boşluk = bilgisayar uyudu
    ENDING_SECONDS = 300  # son 5 dakika uyarı rengi

    def __init__(self, power, clock=time.monotonic, wall=datetime.now, on_change=None, on_attention=None):
        super().__init__(name="insomnia-engine", daemon=True)
        self._power = power
        self._clock = clock
        self._wall = wall
        self._on_change = on_change
        self._on_attention = on_attention

        self._lock = threading.RLock()
        self._queue: queue.Queue = queue.Queue()
        self._quit = False

        self._phase = IDLE
        self._message = "never"
        self._infinite = False
        self._total = 0
        self._action = "none"
        self._sound = True
        self._monitor_off = False
        self._t_start = 0.0
        self._deadline = 0.0
        self._wall_start = None
        self._warn_deadline = 0.0
        self._acting = False
        self._screen_deadline = None
        self._last_tick = clock()
        self._last_key = None

    # ------------------------------------------------------------------ #
    #  Dışarıdan çağrılanlar (her iş parçacığından güvenli)               #
    # ------------------------------------------------------------------ #

    def start_session(self, minutes=None, infinite=False, action="none", sound=True, monitor_off=False):
        return self._call(self._do_start, minutes, infinite, action, sound, monitor_off)

    def stop_session(self):
        return self._call(self._do_stop, "stopped")

    def cancel_action(self):
        return self._call(self._do_cancel_action)

    def request_screen_off(self):
        return self._call(self._do_screen_off, True)

    def cancel_screen_off(self):
        return self._call(self._do_screen_off, False)

    def shutdown(self):
        """Program kapanırken: uyuma isteğini bırakır ve iş parçacığını bitirir."""
        self._call(self._do_quit)

    def snapshot(self) -> dict:
        with self._lock:
            return self._snapshot()

    # ------------------------------------------------------------------ #
    #  İş parçacığı                                                       #
    # ------------------------------------------------------------------ #

    def run(self):
        while not self._quit:
            try:
                item = self._queue.get(timeout=self.TICK)
            except queue.Empty:
                item = None
            if item is not None:
                fn, args, box, done = item
                try:
                    with self._lock:
                        box["result"] = fn(*args)
                finally:
                    done.set()
            self.step()

    def step(self):
        """Bir denetim turu. Sınamalar iş parçacığı olmadan bunu doğrudan çağırır."""
        with self._lock:
            effects = self._tick()
            key, changed = self._change_key()
        for effect in effects:
            effect()
        if changed and self._on_change:
            try:
                self._on_change(self.snapshot())
            except Exception:
                pass

    def _call(self, fn, *args):
        if not self.is_alive() or threading.current_thread() is self:
            with self._lock:
                return fn(*args)
        box: dict = {}
        done = threading.Event()
        self._queue.put((fn, args, box, done))
        done.wait(5)
        return box.get("result")

    # ------------------------------------------------------------------ #
    #  Komutlar (kilit altında, zamanlayıcı iş parçacığında)              #
    # ------------------------------------------------------------------ #

    def _do_start(self, minutes, infinite, action, sound, monitor_off):
        if not isinstance(infinite, bool) or not isinstance(sound, bool) or not isinstance(monitor_off, bool):
            return {"ok": False, "error": "bad_request"}
        if action not in ACTIONS:
            return {"ok": False, "error": "bad_action"}
        if infinite:
            action = "none"  # süresiz oturumun bitişi yok
        elif not valid_minutes(minutes):
            return {"ok": False, "error": "bad_minutes"}
        if action == "hibernate" and not self._power.hibernate_available():
            return {"ok": False, "error": "hibernate_unavailable"}

        if self._phase != IDLE:
            if self._acting:
                return {"ok": False, "error": "busy"}
            self._end_session()  # eski oturum tamamen kapanır; ikinci sayaç kalmaz

        now = self._clock()
        self._phase = RUNNING
        self._message = "running"
        self._infinite = infinite
        self._total = 0 if infinite else minutes * 60
        self._action = action
        self._sound = sound
        self._monitor_off = monitor_off
        self._t_start = now
        self._deadline = now + self._total
        self._wall_start = self._wall()
        self._last_tick = now
        self._power.keep_awake(keep_display=not monitor_off)
        self._screen_deadline = now + self.SCREEN_DELAY if monitor_off else None
        return {"ok": True}

    def _do_stop(self, message):
        if self._phase == IDLE or self._acting:
            return {"ok": False}
        self._end_session()
        self._message = message
        return {"ok": True}

    def _do_cancel_action(self):
        if self._phase != WARNING or self._acting:
            return {"ok": False}
        self._end_session()
        self._message = "cancelled"
        return {"ok": True}

    def _do_screen_off(self, on):
        self._screen_deadline = self._clock() + self.SCREEN_DELAY if on else None
        return {"ok": True}

    def _do_quit(self):
        if self._phase != IDLE:
            self._end_session()
        self._power.release()
        self._quit = True
        return {"ok": True}

    def _end_session(self):
        self._phase = IDLE
        self._acting = False
        self._screen_deadline = None
        self._power.release()

    # ------------------------------------------------------------------ #
    #  Denetim turu                                                       #
    # ------------------------------------------------------------------ #

    def _tick(self):
        effects = []
        now = self._clock()
        gap = now - self._last_tick
        self._last_tick = now

        if gap > self.SUSPEND_GAP:
            # Bilgisayar uyudu ve geri geldi: hiçbir şeyi "gecikmeli" yapma.
            self._screen_deadline = None
            if self._phase != IDLE and not self._acting:
                self._end_session()
                self._message = "suspended"
            return effects

        if self._screen_deadline is not None and now >= self._screen_deadline:
            self._screen_deadline = None
            effects.append(self._power.turn_off_screen)

        if self._phase == RUNNING and not self._infinite and now >= self._deadline:
            if self._sound:
                effects.append(self._power.beep)
            if self._action == "none":
                self._end_session()
                self._message = "finished"
            else:
                self._phase = WARNING
                self._warn_deadline = now + self.WARNING_SECONDS
                self._screen_deadline = None
                effects.append(self._power.wake_screen)
                if self._on_attention:
                    effects.append(self._on_attention)
        elif self._phase == WARNING and not self._acting and now >= self._warn_deadline:
            self._acting = True
            effects.append(self._finish_action)
        return effects

    def _finish_action(self):
        ok = self._power.run_action(self._action)
        with self._lock:
            self._end_session()
            self._message = "finished" if ok else "failed"

    # ------------------------------------------------------------------ #
    #  Durum                                                              #
    # ------------------------------------------------------------------ #

    def _remaining(self, now):
        if self._phase != RUNNING or self._infinite:
            return 0
        return max(0, math.ceil(self._deadline - now))

    def _ending(self, remaining):
        if self._phase == WARNING:
            return True
        if self._phase != RUNNING or self._infinite or self._action == "none":
            return False
        return remaining <= min(self.ENDING_SECONDS, self._total / 5)

    def _change_key(self):
        remaining = self._remaining(self._clock())
        key = (self._phase, self._message, self._ending(remaining), math.ceil(remaining / 60))
        changed = key != self._last_key
        self._last_key = key
        return key, changed

    def _snapshot(self) -> dict:
        now = self._clock()
        active = self._phase != IDLE
        remaining = self._remaining(now)
        ends = ""
        if active and not self._infinite and self._wall_start is not None:
            ends = (self._wall_start + timedelta(seconds=self._total)).strftime("%H:%M")
        return {
            "phase": self._phase,
            "message": self._message,
            "infinite": self._infinite if active else False,
            "total": self._total if active else 0,
            "remaining": remaining,
            "elapsed": max(0, int(now - self._t_start)) if active else 0,
            "action": self._action if active else "none",
            "sound": self._sound,
            "monitor_off": self._monitor_off,
            "started": self._wall_start.strftime("%H:%M") if active and self._wall_start else "",
            "ends": ends,
            "ending": self._ending(remaining),
            "warn_in": max(0, math.ceil(self._warn_deadline - now)) if self._phase == WARNING else 0,
            "screen_in": max(0, math.ceil(self._screen_deadline - now)) if self._screen_deadline is not None else 0,
        }
