import json
import os
import tempfile
import unittest
from datetime import datetime

from insomnia import reminders
from insomnia.reminders import Reminders


class Clock:
    def __init__(self, start):
        self.now = start

    def __call__(self):
        return self.now


# Yerel saatle 26 Kasım 2026 14:00:00
START = datetime(2026, 11, 26, 14, 0, 0).timestamp()


class RemindersTest(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.path = os.path.join(self.folder.name, "reminders.json")
        self.clock = Clock(START)
        self.shown = 0
        self.rings = 0
        self.tones = []
        self.notes = []
        self.rem = self.make()

    def make(self):
        return Reminders(
            path=self.path,
            now=self.clock,
            on_show=lambda: setattr(self, "shown", self.shown + 1),
            on_sound=self.ring,
            on_notify=self.notes.append,
        )

    def ring(self, tone):
        self.rings += 1
        self.tones.append(tone)

    def test_tone_is_kept_and_passed_to_sound(self):
        self.assertEqual(self.rem.add(minutes=1, tone="siren")["error"], "bad_tone")
        self.assertEqual(self.rem.add(minutes=1, tone=None)["error"], "bad_tone")
        self.rem.add(minutes=1, tone="alarm")
        again = self.make()  # ses seçimi dosyada saklanır
        self.clock.now += 60
        again.step()
        self.assertEqual(self.tones, ["alarm"])
        again.snooze(again.snapshot()["due"]["id"])  # ertelenince de aynı ses
        self.clock.now += reminders.SNOOZE_SECONDS
        again.step()
        self.assertEqual(self.tones, ["alarm", "alarm"])

    def test_default_tone_and_one_sound_per_step(self):
        self.rem.add(minutes=1)
        self.rem.add(minutes=1, tone="alarm")
        self.rem.add(minutes=1)
        self.clock.now += 60
        self.rem.step()
        self.assertEqual(self.tones, ["alarm"])  # üst üste üç ses çalmaz; belirgin olan çalar

    def test_old_file_without_tone_gets_soft(self):
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump({"items": [{"id": "a", "at": START + 60, "note": "", "show": True, "sound": True},
                                 {"id": "b", "at": START + 90, "note": "", "show": True, "sound": True, "tone": "x"}]}, f)
        rem = self.make()
        self.clock.now += 60
        rem.step()
        self.assertEqual(self.tones, ["soft"])

    def test_tone_wav_is_valid_audio(self):
        import io
        import struct
        import wave

        from insomnia import settings

        self.assertEqual(reminders.TONES, settings.REMINDER_TONES)
        for tone, (low, high) in (("soft", (1.0, 1.6)), ("alarm", (1.4, 2.2))):
            with wave.open(io.BytesIO(reminders.tone_wav(tone))) as f:
                self.assertEqual((f.getnchannels(), f.getsampwidth()), (1, 2))
                seconds = f.getnframes() / f.getframerate()
                data = f.readframes(f.getnframes())
            self.assertTrue(low <= seconds <= high, (tone, seconds))
            samples = struct.unpack("<%dh" % (len(data) // 2), data)
            peak = max(abs(v) for v in samples)
            self.assertTrue(8000 < peak < 32767, (tone, peak))  # duyulur ama kırpılmaz
            self.assertEqual(samples[0], 0)  # "çıt" sesiyle başlamaz
            self.assertLess(abs(samples[-1]), 1200, tone)  # sönerek biter

    def test_fires_after_minutes(self):
        self.assertTrue(self.rem.add(minutes=15, note="  çayı   kapat ")["ok"])
        snap = self.rem.snapshot()
        self.assertEqual(snap["pending"][0]["time"], "14:15")
        self.assertEqual(snap["pending"][0]["note"], "çayı kapat")
        self.assertIsNone(snap["due"])
        self.clock.now += 15 * 60 - 1
        self.rem.step()
        self.assertEqual((self.shown, self.rings), (0, 0))
        self.clock.now += 1
        self.rem.step()
        self.assertEqual((self.shown, self.rings), (1, 1))
        due = self.rem.snapshot()["due"]
        self.assertEqual((due["note"], due["time"], due["late"], due["more"]), ("çayı kapat", "14:15", False, 0))
        self.assertEqual(self.rem.snapshot()["pending"], [])

    def test_clock_today_and_tomorrow(self):
        self.rem.add(clock="14:30")
        self.rem.add(clock="9.05")
        first, second = self.rem.snapshot()["pending"]
        self.assertEqual((first["time"], first["tomorrow"]), ("14:30", False))
        self.assertEqual((second["time"], second["tomorrow"]), ("09:05", True))
        # tam şu anki saat de yarına gider
        self.rem.add(clock="14:00")
        self.assertTrue(self.rem.snapshot()["pending"][-1]["tomorrow"])

    def test_bad_requests(self):
        for kwargs in (
            {},
            {"minutes": 5, "clock": "10:00"},
            {"minutes": 0},
            {"minutes": 1441},
            {"minutes": True},
            {"minutes": "5"},
            {"clock": "24:00"},
            {"clock": "9"},
            {"clock": 900},
            {"minutes": 5, "show": False, "sound": False},
            {"minutes": 5, "show": "yes"},
        ):
            self.assertFalse(self.rem.add(**kwargs)["ok"], kwargs)
        self.assertFalse(self.rem.has_any())
        self.assertFalse(os.path.exists(self.path))

    def test_note_is_trimmed_and_non_text_ignored(self):
        self.rem.add(minutes=1, note="x" * 200)
        self.rem.add(minutes=2, note=None)
        self.rem.add(minutes=3, note="satır\nsonu")
        notes = [p["note"] for p in self.rem.snapshot()["pending"]]
        self.assertEqual(notes, ["x" * reminders.NOTE_MAX, "", "satır sonu"])

    def test_limit(self):
        for i in range(reminders.MAX_ITEMS):
            self.assertTrue(self.rem.add(minutes=i + 1)["ok"])
        self.assertEqual(self.rem.add(minutes=30)["error"], "full")
        ident = self.rem.snapshot()["pending"][0]["id"]
        self.assertTrue(self.rem.remove(ident)["ok"])
        self.assertTrue(self.rem.add(minutes=30)["ok"])

    def test_sound_repeats_three_times_then_stops(self):
        self.rem.add(minutes=1)
        self.clock.now += 60
        for _ in range(10):  # aynı dakika içinde yeniden çalmaz
            self.rem.step()
        self.assertEqual(self.rings, 1)
        for _ in range(5):
            self.clock.now += reminders.RING_EVERY
            self.rem.step()
        self.assertEqual(self.rings, reminders.RINGS)
        self.assertEqual(self.shown, 1)

    def test_dismiss_stops_sound(self):
        self.rem.add(minutes=1)
        self.clock.now += 60
        self.rem.step()
        ident = self.rem.snapshot()["due"]["id"]
        self.assertTrue(self.rem.dismiss(ident)["ok"])
        self.assertFalse(self.rem.dismiss(ident)["ok"])
        self.clock.now += 600
        self.rem.step()
        self.assertEqual(self.rings, 1)
        self.assertFalse(self.rem.has_any())

    def test_dismiss_does_not_touch_pending(self):
        self.rem.add(minutes=5)
        ident = self.rem.snapshot()["pending"][0]["id"]
        self.assertFalse(self.rem.dismiss(ident)["ok"])
        self.assertTrue(self.rem.has_any())

    def test_snooze(self):
        self.rem.add(minutes=1, note="ilaç")
        self.clock.now += 60
        self.rem.step()
        ident = self.rem.snapshot()["due"]["id"]
        self.assertTrue(self.rem.snooze(ident)["ok"])
        snap = self.rem.snapshot()
        self.assertIsNone(snap["due"])
        self.assertEqual((snap["pending"][0]["time"], snap["pending"][0]["note"]), ("14:11", "ilaç"))
        self.clock.now += reminders.SNOOZE_SECONDS
        self.rem.step()
        self.assertEqual((self.shown, self.rings), (2, 2))
        self.assertFalse(self.rem.snapshot()["due"]["late"])

    def test_sound_only_notifies_without_window(self):
        self.rem.add(minutes=1, note="fırın", show=False, sound=True)
        self.clock.now += 60
        self.rem.step()
        self.assertEqual((self.shown, self.rings, self.notes), (0, 1, ["fırın"]))
        self.assertEqual(self.rem.snapshot()["due"]["note"], "fırın")  # pencere açılınca görülür

    def test_sound_only_closes_itself_after_last_ring(self):
        self.rem.add(minutes=1, note="fırın", show=False, sound=True)
        self.clock.now += 60
        for _ in range(reminders.RINGS - 1):
            self.rem.step()
            self.assertIsNotNone(self.rem.snapshot()["due"])
            self.clock.now += reminders.RING_EVERY
        self.rem.step()
        self.assertEqual(self.rings, reminders.RINGS)
        self.assertFalse(self.rem.has_any())
        self.assertFalse(self.make().has_any())  # dosyadan da silindi
        self.assertEqual(self.notes, ["fırın"])  # baloncuk bir kez

    def test_missed_sound_only_does_not_ring_at_every_start(self):
        self.rem.add(minutes=1, note="ilaç", show=False, sound=True)
        self.clock.now += 3600
        first = self.make()
        first.step()
        self.assertEqual((self.rings, self.notes, self.shown), (1, ["ilaç"], 0))
        second = self.make()  # program yeniden açıldı
        second.step()
        self.assertEqual((self.rings, self.notes), (1, ["ilaç"]))
        self.assertFalse(second.has_any())

    def test_adjust_moves_pending_reminder(self):
        self.rem.add(minutes=10, note="a")
        ident = self.rem.snapshot()["pending"][0]["id"]
        self.assertTrue(self.rem.adjust(ident, 300)["ok"])
        first = self.rem.snapshot(detail=True)["pending"][0]
        self.assertEqual((first["time"], first["left"], first["span"]), ("14:15", 900, 900))
        self.assertTrue(self.rem.adjust(ident, -600)["ok"])
        first = self.rem.snapshot(detail=True)["pending"][0]
        self.assertEqual((first["time"], first["left"], first["span"]), ("14:05", 300, 300))
        self.assertEqual(self.rem.adjust(ident, -300)["error"], "too_short")  # en az 1 dakika kalır
        self.assertTrue(self.rem.adjust(ident, -240)["ok"])
        self.assertEqual(self.rem.adjust(ident, 24 * 3600)["error"], "too_long")
        for bad in (0, 1.5, True, "60", None):
            self.assertEqual(self.rem.adjust(ident, bad)["error"], "bad_request", bad)
        self.assertEqual(self.rem.adjust("yok", 60)["error"], "not_found")
        self.assertEqual(self.make().snapshot()["pending"][0]["time"], "14:01")  # dosyaya yazıldı

    def test_adjust_keeps_order_and_ignores_due(self):
        self.rem.add(minutes=5, note="önce")
        self.rem.add(minutes=10, note="sonra")
        first = self.rem.snapshot()["pending"][0]["id"]
        self.rem.adjust(first, 600)
        self.assertEqual([p["note"] for p in self.rem.snapshot()["pending"]], ["sonra", "önce"])
        self.clock.now += 600
        self.rem.step()
        due = self.rem.snapshot()["due"]["id"]
        self.assertEqual(self.rem.adjust(due, 60)["error"], "not_found")  # çalan hatırlatıcı ertelenir, ayarlanmaz

    def test_detail_snapshot_has_left_and_span(self):
        self.rem.add(minutes=20)
        self.assertNotIn("left", self.rem.snapshot()["pending"][0])  # pencere listesi her saniye yeniden kurulmasın
        self.clock.now += 300
        first = self.rem.snapshot(detail=True)["pending"][0]
        self.assertEqual((first["left"], first["span"]), (900, 1200))
        again = self.make().snapshot(detail=True)["pending"][0]
        self.assertEqual((again["left"], again["span"]), (900, 1200))

    def test_old_file_without_span(self):
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump({"items": [{"id": "a", "at": START + 600, "note": "", "show": True, "sound": True}]}, f)
        first = self.make().snapshot(detail=True)["pending"][0]
        self.assertEqual((first["left"], first["span"]), (600, 600))

    def test_screen_only_is_silent(self):
        self.rem.add(minutes=1, show=True, sound=False)
        self.clock.now += 60
        self.rem.step()
        self.clock.now += 60
        self.rem.step()
        self.assertEqual((self.shown, self.rings, self.notes), (1, 0, []))

    def test_several_due_are_queued(self):
        self.rem.add(minutes=1, note="bir")
        self.rem.add(minutes=2, note="iki")
        self.clock.now += 120
        self.rem.step()
        due = self.rem.snapshot()["due"]
        self.assertEqual((due["note"], due["more"]), ("bir", 1))
        self.rem.dismiss(due["id"])
        due = self.rem.snapshot()["due"]
        self.assertEqual((due["note"], due["more"]), ("iki", 0))

    def test_survives_restart(self):
        self.rem.add(minutes=30, note="toplantı")
        again = self.make()
        self.assertEqual(again.snapshot()["pending"][0]["note"], "toplantı")
        self.clock.now += 30 * 60
        again.step()
        self.assertFalse(again.snapshot()["due"]["late"])

    def test_missed_while_off_is_shown_late_and_rings_once(self):
        self.rem.add(minutes=30, note="toplantı")
        self.clock.now += 3 * 3600  # program kapalıydı ya da bilgisayar uyuyordu
        again = self.make()
        again.step()
        due = again.snapshot()["due"]
        self.assertEqual((due["note"], due["time"], due["late"]), ("toplantı", "14:30", True))
        for _ in range(5):
            self.clock.now += reminders.RING_EVERY
            again.step()
        self.assertEqual((self.shown, self.rings), (1, 1))

    def test_due_reminder_survives_restart_until_dismissed(self):
        self.rem.add(minutes=1, note="kapanmadan önce")
        self.clock.now += 60
        self.rem.step()
        again = self.make()  # "Tamam" denmeden program kapandı
        self.clock.now += 5
        again.step()
        due = again.snapshot()["due"]
        self.assertEqual(due["note"], "kapanmadan önce")
        again.dismiss(due["id"])
        self.assertFalse(self.make().has_any())

    def test_broken_file_is_ignored(self):
        for content in ("", "{", "[]", '{"items": 5}', '{"items": [1, {"id": "a"}, {"id": "b", "at": "x"}]}'):
            with open(self.path, "w", encoding="utf-8") as f:
                f.write(content)
            self.assertFalse(self.make().has_any(), content)

    def test_file_values_are_cleaned(self):
        items = [
            {"id": "a", "at": START + 60, "note": "n" * 500, "show": False, "sound": False},
            {"id": "a", "at": START + 90, "note": "aynı kimlik", "show": True, "sound": True},
            {"id": "b", "at": START + 30, "note": 7, "show": True, "sound": True, "fazla": 1},
        ]
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump({"items": items}, f)
        pending = self.make().snapshot()["pending"]
        self.assertEqual([p["id"] for p in pending], ["b", "a"])
        self.assertEqual(pending[0]["note"], "")
        self.assertEqual(len(pending[1]["note"]), reminders.NOTE_MAX)
        self.assertTrue(pending[1]["show"])  # ikisi de kapalı olamaz

    def test_parse_clock(self):
        self.assertEqual(reminders.parse_clock(" 7:05 "), (7, 5))
        self.assertEqual(reminders.parse_clock("23.59"), (23, 59))
        for bad in ("7:5", "24:00", "12:60", "abc", "", None, 12):
            self.assertIsNone(reminders.parse_clock(bad), bad)

    def test_callback_error_does_not_break_step(self):
        def boom():
            raise RuntimeError

        rem = Reminders(path=self.path, now=self.clock, on_show=boom, on_sound=lambda tone: boom())
        rem.add(minutes=1)
        self.clock.now += 60
        rem.step()
        self.assertIsNotNone(rem.snapshot()["due"])


class ReminderSettingsTest(unittest.TestCase):
    def test_default_minutes(self):
        from insomnia import settings

        self.assertEqual(settings.DEFAULTS["reminder_minutes"], 15)
        self.assertEqual(settings.clean({"reminder_minutes": 45})["reminder_minutes"], 45)
        for bad in (0, 1441, "20", True, None, 2.5):
            self.assertEqual(settings.clean({"reminder_minutes": bad})["reminder_minutes"], 15, bad)
        self.assertEqual(settings.clean({"reminder_tone": "alarm"})["reminder_tone"], "alarm")
        self.assertEqual(settings.clean({"reminder_tone": "siren"})["reminder_tone"], "soft")


if __name__ == "__main__":
    unittest.main()
