"""Kumanda kapısı: başka programların (ör. Ulanzi eklentisi) Insomnia'yı yönetmesi.

Program açıkken yalnız bu bilgisayardan (127.0.0.1) erişilen küçük bir sunucu
çalışır. Kapı numarası ve rastgele bir anahtar şu dosyaya yazılır:

    %LOCALAPPDATA%\\Insomnia\\kumanda.json

Her istek anahtarı `X-Insomnia-Anahtar` başlığında taşımak zorundadır. Anahtar
dosyasını yalnız bu kullanıcının programları okuyabilir; tarayıcıda açık bir
web sayfası dosyayı okuyamadığı için bilgisayarı kapattıramaz.

    GET  /durum   -> oturum durumu
    POST /komut   -> {"komut": "...", ...}  (bkz. App.remote_command)

Aynı dosyada bir de istemci vardır: ikinci kez açılan kopya komut satırındaki
isteği (--baslat 60, --durdur, --ekran-kapat, --cik) çalışan kopyaya buradan iletir.
"""

import hmac
import json
import os
import secrets
import sys
import threading
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import APP_NAME, __version__, settings
from .power import ACTIONS

HEADER = "X-Insomnia-Anahtar"
MAX_BODY = 4096


def info_path() -> str:
    base = os.environ.get("LOCALAPPDATA") or settings.config_dir()
    return os.path.join(base, APP_NAME, "kumanda.json")


class Door:
    def __init__(self, get_state, run_command, log=lambda _m: None):
        self._get_state = get_state
        self._run_command = run_command
        self._log = log
        self._token = secrets.token_urlsafe(32)
        self._server = None
        self.port = 0

    def start(self) -> bool:
        door = self

        class Handler(BaseHTTPRequestHandler):
            server_version = "Insomnia"
            protocol_version = "HTTP/1.1"
            timeout = 5  # hiçbir şey yollamayan bağlantı bir iş parçacığını sonsuza dek tutmasın

            def log_message(self, *_args):
                pass

            def _reply(self, code, data):
                body = json.dumps(data, ensure_ascii=False).encode("utf-8")
                if code != 200:
                    self.close_connection = True  # okunmamış gövde sıradaki istek sanılmasın
                self.send_response(code)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(body)

            def _allowed(self) -> bool:
                host = (self.headers.get("Host") or "").split(":")[0]
                if host not in ("127.0.0.1", "localhost"):
                    return False
                if self.headers.get("Origin"):  # tarayıcıdan gelen istek kabul edilmez
                    return False
                given = self.headers.get(HEADER) or ""
                return hmac.compare_digest(given.encode("utf-8"), door._token.encode("utf-8"))

            def do_GET(self):
                if not self._allowed():
                    return self._reply(403, {"ok": False, "error": "forbidden"})
                if self.path != "/durum":
                    return self._reply(404, {"ok": False, "error": "not_found"})
                self._reply(200, door._get_state())

            def do_POST(self):
                if not self._allowed():
                    return self._reply(403, {"ok": False, "error": "forbidden"})
                if self.path != "/komut":
                    return self._reply(404, {"ok": False, "error": "not_found"})
                try:
                    size = int(self.headers.get("Content-Length") or 0)
                    if not 0 < size <= MAX_BODY:
                        raise ValueError
                    request = json.loads(self.rfile.read(size).decode("utf-8"))
                    if not isinstance(request, dict):
                        raise ValueError
                except (ValueError, UnicodeDecodeError):
                    return self._reply(400, {"ok": False, "error": "bad_request"})
                try:
                    result = door._run_command(request)
                except Exception as exc:  # komut hatası sunucuyu düşürmesin
                    door._log(f"remote: {exc!r}")
                    result = {"ok": False, "error": "failed"}
                self._reply(200, result)

        try:
            self._server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
            self._server.daemon_threads = True
            self.port = self._server.server_address[1]
            threading.Thread(target=self._server.serve_forever, name="insomnia-remote", daemon=True).start()
            self._write_info()
            return True
        except OSError as exc:
            self._log(f"remote start: {exc!r}")
            server, self._server = self._server, None
            if server is not None:  # dosya yazılamadıysa: kimsenin bulamayacağı sunucu açık kalmasın
                threading.Thread(target=lambda: (server.shutdown(), server.server_close()), daemon=True).start()
            return False

    def _write_info(self) -> None:
        path = info_path()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        data = {
            "app": APP_NAME,
            "version": __version__,
            "port": self.port,
            "token": self._token,
            "pid": os.getpid(),
            # Program kapalıyken eklenti buradan yeniden açar (kaynaktan çalışırken boş).
            "exe": sys.executable if getattr(sys, "frozen", False) else "",
        }
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        os.replace(tmp, path)

    def stop(self) -> None:
        server, self._server = self._server, None
        if server is None:
            return
        try:
            # Dosya kalır ama kapı numarası sıfırlanır: eklenti programın yerini bilmeye devam eder.
            path = info_path()
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if data.get("pid") == os.getpid():
                data.update(port=0, token="", pid=0)
                with open(path, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2)
        except (OSError, ValueError):
            pass
        threading.Thread(target=lambda: (server.shutdown(), server.server_close()), daemon=True).start()


# ---------------------------------------------------------------------- #
#  İstemci (ikinci kopya, komut satırı)                                   #
# ---------------------------------------------------------------------- #


def send(request: dict, timeout: float = 3.0):
    """Çalışan kopyaya komut yollar. Ulaşılamazsa None döner."""
    try:
        with open(info_path(), "r", encoding="utf-8") as f:
            info = json.load(f)
        port, token = info["port"], info["token"]
        if not (isinstance(port, int) and port > 0 and isinstance(token, str) and token):
            return None
        req = urllib.request.Request(
            f"http://127.0.0.1:{port}/komut",
            data=json.dumps(request).encode("utf-8"),
            headers={HEADER: token, "Content-Type": "application/json"},
            method="POST",
        )
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))  # vekil sunucuya gitmesin
        with opener.open(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except (OSError, ValueError, KeyError, TypeError, urllib.error.URLError):
        return None


def parse_args(argv) -> dict | None:
    """Komut satırını komuta çevirir; komut yoksa None, hatalıysa {"komut": "bad"}."""
    args = list(argv)
    if "--cik" in args:
        return {"komut": "quit"}
    if "--oturum-var" in args:
        return {"komut": "status"}
    if "--durdur" in args:
        return {"komut": "stop"}
    if "--ekran-kapat" in args:
        return {"komut": "screen_off"}
    if "--baslat" in args:
        i = args.index("--baslat")
        value = args[i + 1] if i + 1 < len(args) else ""
        if not value.isdigit():
            return {"komut": "bad"}
        minutes = int(value)
        if minutes > settings.MAX_MINUTES:
            return {"komut": "bad"}
        request = {"komut": "start", "infinite": minutes == 0, "minutes": minutes or None, "action": "none"}
        if "--islem" in args:
            j = args.index("--islem")
            request["action"] = args[j + 1] if j + 1 < len(args) else ""
            # Hatalı işlem adıyla program sessizce boşta açılmasın.
            if request["action"] not in ACTIONS or (minutes == 0 and request["action"] != "none"):
                return {"komut": "bad"}
        return request
    return None
