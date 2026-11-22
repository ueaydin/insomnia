"""Kumandayla gelen yetenekler: süre ekle/çıkar, bitişi değiştir, şimdi yap ve kumanda kapısı."""

import json
import os
import sys
import tempfile
import unittest
import urllib.error
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from insomnia import remote  # noqa: E402
from insomnia.engine import IDLE, RUNNING, WARNING  # noqa: E402
from tests.test_engine import advance, make  # noqa: E402


class Adjust(unittest.TestCase):
    def test_add_and_remove_time(self):
        engine, clock, _power, _ = make()
        engine.start_session(minutes=60)
        advance(engine, clock, 600)
        self.assertTrue(engine.adjust(900)["ok"])
        s = engine.snapshot()
        self.assertEqual((s["remaining"], s["total"], s["ends"]), (3900, 4500, "14:50"))
        self.assertTrue(engine.adjust(-1800)["ok"])
        s = engine.snapshot()
        self.assertEqual((s["remaining"], s["total"], s["ends"]), (2100, 2700, "14:20"))

    def test_limits(self):
        engine, clock, _power, _ = make()
        engine.start_session(minutes=16)
        self.assertTrue(engine.adjust(-900)["ok"])  # tam 1 dakika kalır
        self.assertEqual(engine.adjust(-1)["error"], "too_short")
        self.assertEqual(engine.adjust(1440 * 60)["error"], "too_long")
        self.assertEqual(engine.snapshot()["remaining"], 60)

    def test_rejected_when_not_timed(self):
        engine, clock, _power, _ = make()
        self.assertEqual(engine.adjust(900)["error"], "not_running")
        engine.start_session(infinite=True)
        self.assertEqual(engine.adjust(900)["error"], "not_running")
        for bad in (None, "900", 1.5, True, 0):
            self.assertEqual(engine.adjust(bad)["error"], "bad_request")

    def test_shortened_session_still_ends_with_action(self):
        engine, clock, power, _ = make()
        engine.start_session(minutes=30, action="shutdown")
        engine.adjust(-900)
        advance(engine, clock, 900)
        self.assertEqual(engine.snapshot()["phase"], WARNING)
        advance(engine, clock, 61)
        self.assertEqual(power.actions(), ["shutdown"])


class SetAction(unittest.TestCase):
    def test_change_while_running(self):
        engine, clock, power, _ = make()
        engine.start_session(minutes=1, action="none")
        self.assertTrue(engine.set_action("restart")["ok"])
        self.assertEqual(engine.snapshot()["action"], "restart")
        advance(engine, clock, 121)
        self.assertEqual(power.actions(), ["restart"])

    def test_remove_action_while_running(self):
        engine, clock, power, _ = make()
        engine.start_session(minutes=1, action="shutdown")
        self.assertTrue(engine.set_action("none")["ok"])
        advance(engine, clock, 200)
        self.assertEqual((engine.snapshot()["phase"], power.actions()), (IDLE, []))

    def test_rejections(self):
        engine, clock, power, _ = make(hibernate=False)
        self.assertEqual(engine.set_action("shutdown")["error"], "not_running")
        engine.start_session(minutes=5)
        self.assertEqual(engine.set_action("format")["error"], "bad_action")
        self.assertEqual(engine.set_action("hibernate")["error"], "hibernate_unavailable")
        engine.start_session(infinite=True)
        self.assertEqual(engine.set_action("shutdown")["error"], "not_running")
        engine.start_session(minutes=1, action="shutdown")
        advance(engine, clock, 61)
        self.assertEqual(engine.set_action("none")["error"], "not_running")  # uyarıda değişmez


class Sleep(unittest.TestCase):
    def test_sleep_runs_after_warning_and_releases_first(self):
        engine, clock, power, _ = make()
        self.assertTrue(engine.start_session(minutes=1, action="sleep")["ok"])
        advance(engine, clock, 61)
        self.assertEqual(engine.snapshot()["phase"], WARNING)
        advance(engine, clock, 61)
        self.assertEqual(power.actions(), ["sleep"])
        i = power.calls.index(("action", "sleep"))
        self.assertEqual(power.calls[i - 1], ("release",), "uyanık tutma uykudan önce bırakılmalı")
        self.assertEqual(engine.snapshot()["phase"], IDLE)

    def test_waking_up_after_sleep_does_nothing_more(self):
        engine, clock, power, _ = make()
        engine.start_session(minutes=1, action="sleep")
        advance(engine, clock, 122)
        clock.now += 8 * 3600  # bilgisayar saatlerce uyudu
        engine.step()
        advance(engine, clock, 120)
        self.assertEqual(power.actions(), ["sleep"])
        self.assertEqual(engine.snapshot()["message"], "finished")

    def test_rejected_when_unavailable(self):
        engine, clock, power, _ = make(sleep=False)
        self.assertEqual(engine.start_session(minutes=5, action="sleep"), {"ok": False, "error": "sleep_unavailable"})
        engine.start_session(minutes=5)
        self.assertEqual(engine.set_action("sleep")["error"], "sleep_unavailable")

    def test_command_line(self):
        self.assertEqual(remote.parse_args(["--baslat", "30", "--islem", "sleep"])["action"], "sleep")


class ActNow(unittest.TestCase):
    def test_only_during_warning(self):
        engine, clock, power, _ = make()
        self.assertFalse(engine.act_now()["ok"])
        engine.start_session(minutes=1, action="hibernate")
        self.assertFalse(engine.act_now()["ok"])
        advance(engine, clock, 61)
        self.assertEqual(engine.snapshot()["phase"], WARNING)
        self.assertTrue(engine.act_now()["ok"])
        self.assertEqual(power.actions(), [])
        advance(engine, clock, 1)
        self.assertEqual(power.actions(), ["hibernate"])
        self.assertEqual(engine.snapshot()["phase"], IDLE)
        advance(engine, clock, 120)
        self.assertEqual(power.actions(), ["hibernate"], "işlem iki kez yapılmamalı")

    def test_cancel_wins_if_first(self):
        engine, clock, power, _ = make()
        engine.start_session(minutes=1, action="shutdown")
        advance(engine, clock, 61)
        engine.cancel_action()
        self.assertFalse(engine.act_now()["ok"])
        advance(engine, clock, 120)
        self.assertEqual(power.actions(), [])


class DoorTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old = os.environ.get("LOCALAPPDATA")
        os.environ["LOCALAPPDATA"] = self.tmp.name
        self.seen = []
        self.door = remote.Door(lambda: {"ok": True, "phase": "idle"}, self._run)
        self.assertTrue(self.door.start())
        with open(remote.info_path(), encoding="utf-8") as f:
            self.info = json.load(f)

    def tearDown(self):
        self.door.stop()
        if self.old is None:
            os.environ.pop("LOCALAPPDATA", None)
        else:
            os.environ["LOCALAPPDATA"] = self.old
        self.tmp.cleanup()

    def _run(self, request):
        self.seen.append(request)
        if request.get("komut") == "patla":
            raise RuntimeError("x")
        return {"ok": True}

    def _http(self, path, data=None, headers=None, method=None):
        req = urllib.request.Request(
            f"http://127.0.0.1:{self.info['port']}{path}", data=data, headers=headers or {}, method=method
        )
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        try:
            with opener.open(req, timeout=3) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read())

    def test_info_file(self):
        self.assertEqual(self.info["app"], "Insomnia")
        self.assertEqual(self.info["pid"], os.getpid())
        self.assertGreater(len(self.info["token"]), 30)

    def test_status_needs_key(self):
        self.assertEqual(self._http("/durum")[0], 403)
        self.assertEqual(self._http("/durum", headers={remote.HEADER: "yanlis"})[0], 403)
        self.assertEqual(self._http("/durum", headers={remote.HEADER: self.info["token"]}), (200, {"ok": True, "phase": "idle"}))

    def test_browser_request_refused_even_with_key(self):
        h = {remote.HEADER: self.info["token"], "Origin": "https://ornek.com"}
        self.assertEqual(self._http("/komut", data=b'{"komut":"stop"}', headers=h)[0], 403)
        h = {remote.HEADER: self.info["token"], "Host": "ornek.com"}
        self.assertEqual(self._http("/durum", headers=h)[0], 403)
        self.assertEqual(self.seen, [])

    def test_command_roundtrip(self):
        self.assertEqual(remote.send({"komut": "stop"}), {"ok": True})
        self.assertEqual(self.seen, [{"komut": "stop"}])

    def test_bad_bodies(self):
        h = {remote.HEADER: self.info["token"]}
        for body in (b"", b"[1]", b"{bozuk", b"\xff\xfe", b"x" * 5000):
            self.assertEqual(self._http("/komut", data=body, headers=h, method="POST")[0], 400, body[:10])
        self.assertEqual(self._http("/baska", headers=h)[0], 404)
        self.assertEqual(self.seen, [])

    def test_failing_command_does_not_kill_server(self):
        self.assertEqual(remote.send({"komut": "patla"}), {"ok": False, "error": "failed"})
        self.assertEqual(remote.send({"komut": "stop"}), {"ok": True})

    def test_stop_clears_port_and_send_returns_none(self):
        self.door.stop()
        with open(remote.info_path(), encoding="utf-8") as f:
            info = json.load(f)
        self.assertEqual((info["port"], info["token"]), (0, ""))
        self.assertIsNone(remote.send({"komut": "stop"}))

    def test_silent_connection_is_dropped(self):
        import socket
        import time

        s = socket.create_connection(("127.0.0.1", self.info["port"]), timeout=10)
        try:
            basla = time.monotonic()
            self.assertEqual(s.recv(1), b"", "sunucu sessiz bağlantıyı kapatmalı")
            self.assertLess(time.monotonic() - basla, 9)
        finally:
            s.close()

    def test_refused_post_body_is_not_parsed_as_next_request(self):
        import socket

        s = socket.create_connection(("127.0.0.1", self.info["port"]), timeout=5)
        try:
            govde = b"GET /durum HTTP/1.1\r\nHost: 127.0.0.1\r\nX-Insomnia-Anahtar: " + self.info["token"].encode() + b"\r\n\r\n"
            s.sendall(b"POST /komut HTTP/1.1\r\nHost: 127.0.0.1\r\nContent-Length: " + str(len(govde)).encode() + b"\r\n\r\n" + govde)
            yanit = b""
            while True:
                p = s.recv(4096)
                if not p:
                    break
                yanit += p
        finally:
            s.close()
        self.assertEqual(yanit.count(b"HTTP/1.1 "), 1)
        self.assertIn(b"403", yanit.split(b"\r\n")[0])
        self.assertNotIn(b"phase", yanit)

    def test_send_without_file(self):
        os.remove(remote.info_path())
        self.assertIsNone(remote.send({"komut": "stop"}))


class ParseArgs(unittest.TestCase):
    def test_commands(self):
        p = remote.parse_args
        self.assertIsNone(p([]))
        self.assertIsNone(p(["--tray"]))
        self.assertEqual(p(["--durdur"]), {"komut": "stop"})
        self.assertEqual(p(["--cik"]), {"komut": "quit"})
        self.assertEqual(p(["--oturum-var"]), {"komut": "status"})
        self.assertEqual(p(["--ekran-kapat"]), {"komut": "screen_off"})
        self.assertEqual(p(["--baslat", "60"]), {"komut": "start", "infinite": False, "minutes": 60, "action": "none"})
        self.assertEqual(p(["--baslat", "0"]), {"komut": "start", "infinite": True, "minutes": None, "action": "none"})
        self.assertEqual(p(["--baslat", "30", "--islem", "shutdown"])["action"], "shutdown")
        for bad in (["--baslat"], ["--baslat", "abc"], ["--baslat", "-5"], ["--baslat", "1441"],
                    ["--baslat", "30", "--islem"], ["--baslat", "30", "--islem", "kapat"],
                    ["--baslat", "0", "--islem", "shutdown"]):
            self.assertEqual(p(bad), {"komut": "bad"})


if __name__ == "__main__":
    unittest.main()
