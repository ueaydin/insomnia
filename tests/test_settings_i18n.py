"""Ayar dosyası ve çeviri sınamaları."""

import json
import os
import re
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from insomnia import i18n, icons, settings  # noqa: E402


class Settings(unittest.TestCase):
    def test_bad_values_fall_back_to_defaults(self):
        dirty = {
            "duration_minutes": "abc",
            "infinite": "yes",
            "sound_enabled": 1,
            "monitor_off": None,
            "language": "xx",
            "power_action": "shutdown",
            "junk": [1, 2],
        }
        self.assertEqual(settings.clean(dirty), settings.DEFAULTS)

    def test_power_action_is_never_kept(self):
        self.assertNotIn("power_action", settings.clean({"power_action": "shutdown"}))

    def test_minutes_range(self):
        for bad in (0, -3, 1441, True, 2.5):
            self.assertEqual(settings.clean({"duration_minutes": bad})["duration_minutes"], 60, bad)
        self.assertEqual(settings.clean({"duration_minutes": 1440})["duration_minutes"], 1440)

    def test_non_dict_and_broken_file(self):
        for junk in (None, [], "x", 5):
            self.assertEqual(settings.clean(junk), settings.DEFAULTS)
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, "settings.json")
            with open(path, "w", encoding="utf-8") as f:
                f.write("{ bozuk json")
            self.assertEqual(settings.load(path), settings.DEFAULTS)
            self.assertEqual(settings.load(os.path.join(folder, "yok.json")), settings.DEFAULTS)

    def test_save_and_load_roundtrip(self):
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, "alt", "settings.json")
            data = dict(settings.DEFAULTS, duration_minutes=95, language="de", monitor_off=True)
            self.assertTrue(settings.save(data, path))
            self.assertEqual(settings.load(path), data)
            self.assertEqual(os.listdir(os.path.dirname(path)), ["settings.json"], "geçici dosya kalmamalı")
            with open(path, encoding="utf-8") as f:
                self.assertEqual(json.load(f)["duration_minutes"], 95)

    def test_old_version_file_is_readable(self):
        old = {"duration_minutes": 60, "sound_enabled": True, "monitor_off": True, "power_action": "none", "language": "tr"}
        cleaned = settings.clean(old)
        self.assertTrue(cleaned["monitor_off"])
        self.assertEqual(cleaned["language"], "tr")


class Translations(unittest.TestCase):
    def test_every_language_has_the_same_keys(self):
        base = set(i18n.TRANSLATIONS["tr"])
        for code, table in i18n.TRANSLATIONS.items():
            self.assertEqual(set(table), base, code)
            self.assertTrue(all(isinstance(v, str) and v for v in table.values()), code)

    def test_placeholders_match(self):
        pattern = re.compile(r"\{(\w+)\}")
        for key, text in i18n.TRANSLATIONS["tr"].items():
            expected = sorted(pattern.findall(text))
            for code, table in i18n.TRANSLATIONS.items():
                self.assertEqual(sorted(pattern.findall(table[key])), expected, f"{code}:{key}")

    def test_languages_match_settings(self):
        self.assertEqual(set(i18n.TRANSLATIONS), set(settings.LANGUAGES))
        self.assertEqual(set(i18n.LANGUAGE_NAMES), set(settings.LANGUAGES))

    def test_ui_uses_only_known_keys(self):
        ui = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "insomnia", "ui", "index.html")
        with open(ui, encoding="utf-8") as f:
            html = f.read()
        used = set(re.findall(r'data-ta?="(\w+)"', html)) | set(re.findall(r"\bt\('(\w+)'", html))
        used = {key for key in used if not key.endswith("_")}  # 'msg_' + kod gibi birleştirilenler aşağıda
        prefixes = set(re.findall(r"\bt\('(\w+_)' \+", html))
        known = set(i18n.TRANSLATIONS["tr"])
        self.assertEqual(used - known, set())
        for prefix in prefixes:
            self.assertTrue(any(k.startswith(prefix) for k in known), prefix)
        for code in ("never", "stopped", "finished", "suspended", "cancelled", "failed"):
            self.assertIn("msg_" + code, known)
        for action in ("none", "shutdown", "restart", "hibernate"):
            for prefix in ("act_", "end_"):
                self.assertIn(prefix + action, known)
            if action != "none":
                self.assertIn("warn_" + action, known)

    def test_set_language(self):
        self.assertFalse(i18n.set_language("xx"))
        self.assertTrue(i18n.set_language("en"))
        self.assertEqual(i18n.t("tip_left", m=5), "Insomnia · 5 min left")
        i18n.set_language("tr")


class Icons(unittest.TestCase):
    def test_moon_and_app_icon(self):
        moon = icons.moon(icons.GOLD, 64)
        self.assertEqual((moon.size, moon.mode), ((64, 64), "RGBA"))
        alpha = moon.getchannel("A")
        self.assertEqual(alpha.getpixel((0, 0)), 0, "köşe saydam olmalı")
        self.assertGreater(alpha.getpixel((13, 43)), 200, "hilalin gövdesi dolu olmalı")
        self.assertEqual(alpha.getpixel((40, 28)), 0, "hilalin oyuğu saydam olmalı")
        self.assertGreater(alpha.getpixel((50, 13)), 200, "yıldız dolu olmalı")
        self.assertEqual(icons.app_icon(256).size, (256, 256))

class VisibilityTests(unittest.TestCase):
    def test_default_is_both(self):
        self.assertEqual(settings.clean({})["visibility"], "both")

    def test_valid_values_are_kept(self):
        for mode in settings.VISIBILITY:
            self.assertEqual(settings.clean({"visibility": mode})["visibility"], mode)

    def test_invalid_values_fall_back(self):
        for bad in ("none", "", None, 3, ["tray"]):
            self.assertEqual(settings.clean({"visibility": bad})["visibility"], "both")

class RingIconTests(unittest.TestCase):
    def test_step_bounds(self):
        self.assertEqual(icons.ring_step(0, 600), 0)
        self.assertEqual(icons.ring_step(600, 600), icons.RING_STEPS)
        self.assertEqual(icons.ring_step(1, 600), 1)
        self.assertEqual(icons.ring_step(300, 600), icons.RING_STEPS // 2)
        self.assertEqual(icons.ring_step(5, 0), 0)
        self.assertEqual(icons.ring_step(0, 0, infinite=True), icons.RING_STEPS)

    def test_ring_shrinks_clockwise_from_top(self):
        full = icons.ring_moon(icons.GOLD, icons.RING_STEPS, 64)
        half = icons.ring_moon(icons.GOLD, icons.RING_STEPS // 2, 64)
        self.assertEqual(full.size, (64, 64))

        def near(image, xy, color):  # küçültme renkleri bir iki birim oynatır
            return all(abs(a - b) <= 6 for a, b in zip(image.getpixel(xy)[:3], color))

        self.assertTrue(near(full, (3, 32), icons.GOLD))   # sol: dolu halkada altın
        self.assertTrue(near(half, (60, 32), icons.GOLD))  # sağ: ilk yarı duruyor
        self.assertTrue(near(half, (3, 32), icons.TRACK))  # sol: ikinci yarı bitti
        self.assertTrue(near(icons.ring_moon(icons.GOLD, 0, 64), (60, 32), icons.TRACK))


if __name__ == "__main__":
    unittest.main()
