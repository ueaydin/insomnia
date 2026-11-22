"""Zamanlayıcı sınamaları: sahte saat ve sahte güç katmanıyla, iş parçacığı olmadan."""

import os
import sys
import unittest
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from insomnia.engine import IDLE, RUNNING, WARNING, Engine  # noqa: E402


class FakePower:
    def __init__(self, hibernate=True, action_ok=True, sleep=True):
        self.sleep = sleep
        self.calls = []
        self.hibernate = hibernate
        self.action_ok = action_ok

    def keep_awake(self, keep_display):
        self.calls.append(("keep_awake", keep_display))

    def release(self):
        self.calls.append(("release",))

    def turn_off_screen(self):
        self.calls.append(("screen_off",))

    def wake_screen(self):
        self.calls.append(("wake",))

    def beep(self):
        self.calls.append(("beep",))

    def hibernate_available(self):
        return self.hibernate

    def sleep_available(self):
        return self.sleep

    def run_action(self, action):
        self.calls.append(("action", action))
        return self.action_ok

    def actions(self):
        return [c[1] for c in self.calls if c[0] == "action"]

    def count(self, name):
        return sum(1 for c in self.calls if c[0] == name)


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


def make(**power_args):
    clock = Clock()
    power = FakePower(**power_args)
    attention = []
    engine = Engine(power, clock=clock, wall=lambda: datetime(2026, 1, 1, 13, 35), on_attention=lambda: attention.append(1))
    return engine, clock, power, attention


def advance(engine, clock, seconds, step=1.0):
    """Saati küçük adımlarla ilerletir (gerçekte olduğu gibi sık denetim)."""
    start = clock.now
    steps = 0
    while clock.now < start + seconds:
        steps += 1
        clock.now = min(start + steps * step, start + seconds)  # kesir hatası birikmesin
        engine.step()


class StartValidation(unittest.TestCase):
    def test_rejects_bad_minutes(self):
        for bad in (0, -5, -1, 1441, 10**9, None, "60", 1.5, True, [], {}):
            engine, _, power, _ = make()
            result = engine.start_session(minutes=bad, action="shutdown")
            self.assertFalse(result["ok"], bad)
            self.assertEqual(engine.snapshot()["phase"], IDLE, bad)
            self.assertEqual(power.calls, [], bad)

    def test_negative_minutes_never_reach_the_action(self):
        engine, clock, power, _ = make()
        engine.start_session(minutes=-1, action="shutdown")
        advance(engine, clock, 120)
        self.assertEqual(power.actions(), [])

    def test_rejects_unknown_action_and_bad_flags(self):
        engine, _, _, _ = make()
        self.assertFalse(engine.start_session(minutes=5, action="format_disk")["ok"])
        self.assertFalse(engine.start_session(minutes=5, action=None)["ok"])
        self.assertFalse(engine.start_session(minutes=5, infinite="yes")["ok"])
        self.assertFalse(engine.start_session(minutes=5, sound=1)["ok"])

    def test_hibernate_rejected_when_unavailable(self):
        engine, _, _, _ = make(hibernate=False)
        result = engine.start_session(minutes=5, action="hibernate")
        self.assertEqual(result, {"ok": False, "error": "hibernate_unavailable"})

    def test_accepts_limits(self):
        for good in (1, 1440):
            engine, _, _, _ = make()
            self.assertTrue(engine.start_session(minutes=good)["ok"])


class Countdown(unittest.TestCase):
    def test_counts_down_without_drift(self):
        engine, clock, _, _ = make()
        engine.start_session(minutes=60)
        self.assertEqual(engine.snapshot()["remaining"], 3600)
        advance(engine, clock, 1063, step=0.37)  # düzensiz denetim aralığı
        snap = engine.snapshot()
        self.assertEqual(snap["remaining"], 3600 - 1063)
        self.assertEqual(snap["elapsed"], 1063)
        self.assertEqual((snap["started"], snap["ends"]), ("13:35", "14:35"))

    def test_finish_with_no_action(self):
        engine, clock, power, attention = make()
        engine.start_session(minutes=1, action="none", sound=True)
        advance(engine, clock, 61)
        snap = engine.snapshot()
        self.assertEqual((snap["phase"], snap["message"]), (IDLE, "finished"))
        self.assertEqual(power.count("beep"), 1)
        self.assertEqual(power.actions(), [])
        self.assertEqual(attention, [])
        self.assertEqual(power.count("release"), 1)

    def test_no_beep_when_sound_off(self):
        engine, clock, power, _ = make()
        engine.start_session(minutes=1, sound=False)
        advance(engine, clock, 61)
        self.assertEqual(power.count("beep"), 0)

    def test_infinite_never_finishes_and_ignores_action(self):
        engine, clock, power, _ = make()
        self.assertTrue(engine.start_session(infinite=True, action="shutdown")["ok"])
        advance(engine, clock, 20 * 3600, step=20)
        snap = engine.snapshot()
        self.assertEqual((snap["phase"], snap["action"]), (RUNNING, "none"))
        self.assertEqual(power.actions(), [])


class EndAction(unittest.TestCase):
    def test_warning_then_action(self):
        engine, clock, power, attention = make()
        engine.start_session(minutes=1, action="shutdown")
        advance(engine, clock, 60.5)
        snap = engine.snapshot()
        self.assertEqual(snap["phase"], WARNING)
        self.assertEqual(power.actions(), [], "uyarı süresi dolmadan işlem yapılmamalı")
        self.assertEqual(attention, [1], "pencere öne getirilmeli")
        self.assertEqual(power.count("wake"), 1)
        advance(engine, clock, Engine.WARNING_SECONDS - 2)
        self.assertEqual(power.actions(), [])
        advance(engine, clock, 3)
        self.assertEqual(power.actions(), ["shutdown"])
        snap = engine.snapshot()
        self.assertEqual((snap["phase"], snap["message"]), (IDLE, "finished"))

    def test_action_runs_exactly_once(self):
        engine, clock, power, _ = make()
        engine.start_session(minutes=1, action="restart")
        advance(engine, clock, 600)
        self.assertEqual(power.actions(), ["restart"])

    def test_cancel_during_warning(self):
        engine, clock, power, _ = make()
        engine.start_session(minutes=1, action="shutdown")
        advance(engine, clock, 70)
        self.assertTrue(engine.cancel_action()["ok"])
        advance(engine, clock, 600)
        self.assertEqual(power.actions(), [])
        self.assertEqual(engine.snapshot()["message"], "cancelled")

    def test_stop_during_warning(self):
        engine, clock, power, _ = make()
        engine.start_session(minutes=1, action="hibernate")
        advance(engine, clock, 70)
        engine.stop_session()
        advance(engine, clock, 600)
        self.assertEqual(power.actions(), [])

    def test_cancel_action_does_nothing_while_running(self):
        engine, clock, _, _ = make()
        engine.start_session(minutes=5, action="shutdown")
        advance(engine, clock, 10)
        self.assertFalse(engine.cancel_action()["ok"])
        self.assertEqual(engine.snapshot()["phase"], RUNNING)

    def test_failed_action_is_reported(self):
        engine, clock, _, _ = make(action_ok=False)
        engine.start_session(minutes=1, action="hibernate")
        advance(engine, clock, 200)
        self.assertEqual(engine.snapshot()["message"], "failed")


class Restart(unittest.TestCase):
    def test_start_while_running_replaces_session(self):
        """Eski sürümde ikinci başlatma iki sayacı birden çalıştırıyordu."""
        engine, clock, power, _ = make()
        engine.start_session(minutes=60, action="shutdown")
        advance(engine, clock, 100)
        engine.start_session(minutes=30, action="none")
        self.assertEqual(engine.snapshot()["remaining"], 1800)
        advance(engine, clock, 100)
        snap = engine.snapshot()
        self.assertEqual(snap["remaining"], 1700, "sayaç tek hızda ilerlemeli")
        self.assertEqual(snap["action"], "none")
        advance(engine, clock, 4000)
        self.assertEqual(power.actions(), [], "eski oturumun kapatma işlemi yapılmamalı")

    def test_stop_releases_and_is_idempotent(self):
        engine, clock, power, _ = make()
        engine.start_session(minutes=5)
        self.assertTrue(engine.stop_session()["ok"])
        self.assertFalse(engine.stop_session()["ok"])
        self.assertEqual(engine.snapshot()["message"], "stopped")
        self.assertEqual(power.calls, [("keep_awake", True), ("release",)])


class Suspend(unittest.TestCase):
    def test_wake_after_deadline_does_not_shut_down(self):
        engine, clock, power, _ = make()
        engine.start_session(minutes=10, action="shutdown")
        advance(engine, clock, 60)
        clock.now += 3 * 3600  # bilgisayar uyudu, 3 saat sonra açıldı
        engine.step()
        advance(engine, clock, 600)
        snap = engine.snapshot()
        self.assertEqual((snap["phase"], snap["message"]), (IDLE, "suspended"))
        self.assertEqual(power.actions(), [])

    def test_suspend_during_warning_cancels_action(self):
        engine, clock, power, _ = make()
        engine.start_session(minutes=1, action="shutdown")
        advance(engine, clock, 70)
        clock.now += 500
        engine.step()
        advance(engine, clock, 100)
        self.assertEqual(power.actions(), [])
        self.assertEqual(engine.snapshot()["message"], "suspended")

    def test_short_stall_is_not_a_suspend(self):
        engine, clock, _, _ = make()
        engine.start_session(minutes=10)
        clock.now += 20
        engine.step()
        self.assertEqual(engine.snapshot()["phase"], RUNNING)


class Screen(unittest.TestCase):
    def test_monitor_off_option(self):
        engine, clock, power, _ = make()
        engine.start_session(minutes=5, monitor_off=True)
        self.assertEqual(power.calls[0], ("keep_awake", False))
        self.assertEqual(engine.snapshot()["screen_in"], 10)
        advance(engine, clock, 9)
        self.assertEqual(power.count("screen_off"), 0)
        advance(engine, clock, 2)
        self.assertEqual(power.count("screen_off"), 1)
        self.assertEqual(engine.snapshot()["screen_in"], 0)

    def test_stop_cancels_pending_screen_off(self):
        engine, clock, power, _ = make()
        engine.start_session(minutes=5, monitor_off=True)
        advance(engine, clock, 3)
        engine.stop_session()
        advance(engine, clock, 60)
        self.assertEqual(power.count("screen_off"), 0)

    def test_manual_screen_off_and_cancel(self):
        engine, clock, power, _ = make()
        engine.request_screen_off()
        advance(engine, clock, 4)
        self.assertEqual(engine.snapshot()["screen_in"], 6)
        engine.cancel_screen_off()
        advance(engine, clock, 60)
        self.assertEqual(power.count("screen_off"), 0)
        engine.request_screen_off()
        advance(engine, clock, 11)
        self.assertEqual(power.count("screen_off"), 1)


class Ending(unittest.TestCase):
    def test_ending_flag_last_five_minutes(self):
        engine, clock, _, _ = make()
        engine.start_session(minutes=60, action="shutdown")
        advance(engine, clock, 3290, step=5)
        self.assertFalse(engine.snapshot()["ending"])
        advance(engine, clock, 20, step=5)
        self.assertTrue(engine.snapshot()["ending"])

    def test_no_ending_flag_without_action(self):
        engine, clock, _, _ = make()
        engine.start_session(minutes=60, action="none")
        advance(engine, clock, 3590, step=5)
        self.assertFalse(engine.snapshot()["ending"])


class Threaded(unittest.TestCase):
    def test_real_thread_start_stop(self):
        import threading

        power = FakePower()
        seen = []
        power.keep_awake = lambda keep_display: seen.append(threading.current_thread().name)
        power.release = lambda: seen.append(threading.current_thread().name)
        engine = Engine(power)
        engine.start()
        try:
            self.assertTrue(engine.start_session(minutes=5)["ok"])
            self.assertEqual(engine.snapshot()["phase"], RUNNING)
            self.assertTrue(engine.stop_session()["ok"])
        finally:
            engine.shutdown()
            engine.join(3)
        self.assertFalse(engine.is_alive())
        self.assertEqual(set(seen), {"insomnia-engine"}, "uyuma isteği yalnız zamanlayıcı iş parçacığından verilmeli")


if __name__ == "__main__":
    unittest.main()
