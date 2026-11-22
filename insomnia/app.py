"""Pencere, tepsi simgesi ve zamanlayıcıyı birbirine bağlar."""

import ctypes
import os
import sys
import threading
from ctypes import wintypes

import webview

from . import APP_NAME, __version__, i18n, settings, single_instance, startup
from .engine import IDLE, Engine
from .power import Power
from .tray import Tray

WIDTH, HEIGHT = 720, 420

_user32 = ctypes.WinDLL("user32", use_last_error=True)
_user32.SetWindowPos.argtypes = [
    wintypes.HWND, ctypes.c_void_p, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.UINT,
]
_user32.SetWindowPos.restype = wintypes.BOOL
_user32.SetForegroundWindow.argtypes = [wintypes.HWND]
_user32.SetForegroundWindow.restype = wintypes.BOOL
_HWND_TOPMOST = ctypes.c_void_p(-1)
_HWND_NOTOPMOST = ctypes.c_void_p(-2)
_SWP_NOSIZE = 0x0001
_SWP_NOMOVE = 0x0002
_SWP_NOZORDER = 0x0004
_SWP_NOACTIVATE = 0x0010
_user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
_user32.GetWindowRect.restype = wintypes.BOOL
_user32.GetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int]
_user32.GetWindowLongPtrW.restype = ctypes.c_ssize_t
_user32.SetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_ssize_t]
_user32.SetWindowLongPtrW.restype = ctypes.c_ssize_t
_user32.IsWindowVisible.argtypes = [wintypes.HWND]
_user32.IsWindowVisible.restype = wintypes.BOOL
_user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
_user32.ShowWindow.restype = wintypes.BOOL
_GWL_EXSTYLE = -20
_WS_EX_TOOLWINDOW = 0x00000080
_WS_EX_APPWINDOW = 0x00040000
_user32.IsIconic.argtypes = [wintypes.HWND]
_user32.IsIconic.restype = wintypes.BOOL
_SM_SHUTTINGDOWN = 0x2000
_SW_HIDE = 0
_SW_SHOW = 5


def _resource(*parts) -> str:
    base = getattr(sys, "_MEIPASS", None) or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, "insomnia", *parts)


def _local_dir() -> str:
    base = os.environ.get("LOCALAPPDATA") or settings.config_dir()
    return os.path.join(base, APP_NAME)


class Api:
    """Arayüzün (JavaScript) çağırabildiği işlemler. Girdiler burada yeniden denetlenir."""

    def __init__(self, app):
        self._app = app

    def init(self):
        return self._app.ui_init()

    def state(self):
        return self._app.ui_state()

    def start(self, request):
        return self._app.ui_start(request)

    def stop(self):
        self._app.engine.stop_session()
        return self._app.ui_state()

    def cancel_action(self):
        self._app.engine.cancel_action()
        return self._app.ui_state()

    def screen_off(self):
        self._app.engine.request_screen_off()
        return self._app.ui_state()

    def cancel_screen_off(self):
        self._app.engine.cancel_screen_off()
        return self._app.ui_state()

    def remember(self, prefs):
        self._app.remember(prefs)

    def fit(self, inner_width, inner_height, scale):
        self._app.fit_window(inner_width, inner_height, scale)

    def set_visibility(self, mode):
        return self._app.set_visibility(mode)

    def set_language(self, code):
        self._app.set_language(code)

    def set_startup(self, enabled):
        return self._app.set_startup(enabled)

    def minimize(self):
        self._app.minimize_window()

    def hide(self):
        self._app.hide_window()

    def log(self, message):
        self._app.log(f"js: {message}")


class App:
    def __init__(self, start_hidden: bool = False):
        self.settings = settings.load()
        i18n.set_language(self.settings["language"])
        self._visibility = self.settings["visibility"]
        # Tepsi simgesi yokken gizli başlamak programı erişilmez yapar; küçültülmüş başlar.
        self._start_minimized = start_hidden and self._visibility == "taskbar"
        self._start_hidden = start_hidden and not self._start_minimized
        self._visible = not self._start_hidden
        self._minimized = self._start_minimized
        self._quitting = False
        self._fitted = False
        self._lang_rev = 0
        self._lock = threading.Lock()
        self.window = None

        self.power = Power()
        self.engine = Engine(self.power, on_change=self._on_engine_change, on_attention=self.show_window)
        self.tray = Tray(
            on_toggle_window=self.toggle_window,
            on_quick_start=self.quick_start,
            on_stop=self.engine.stop_session,
            on_language=self.set_language,
            on_exit=self.quit,
            is_running=lambda: self.engine.snapshot()["phase"] != IDLE,
        )

    # ------------------------------------------------------------------ #
    #  Çalıştırma                                                         #
    # ------------------------------------------------------------------ #

    def run(self) -> None:
        with open(_resource("ui", "index.html"), "r", encoding="utf-8") as f:
            html = f.read()
        self.window = webview.create_window(
            APP_NAME,
            html=html,
            js_api=Api(self),
            width=WIDTH,
            height=HEIGHT,
            resizable=False,
            frameless=True,
            easy_drag=False,
            hidden=self._start_hidden,
            minimized=self._start_minimized,
            background_color="#1b1b1d",
        )
        self.window.events.loaded += self._apply_taskbar_button
        self.window.events.before_show += self._allow_windows_shutdown
        self.window.events.closing += self._on_closing
        self.window.events.minimized += lambda: self._set_minimized(True)
        self.window.events.restored += lambda: self._set_minimized(False)

        self.engine.start()
        self.tray.start(visible=self._visibility != "taskbar")
        single_instance.listen(self.show_window)
        try:
            webview.start(
                gui="edgechromium",
                private_mode=True,
                storage_path=os.path.join(_local_dir(), "webview"),
            )
        finally:
            self._quitting = True
            self.engine.shutdown()
            self.tray.stop()

    def quit(self) -> None:
        self._quitting = True
        self.engine.shutdown()
        self.tray.stop()
        try:
            self.window.destroy()
        except Exception:
            pass

    # ------------------------------------------------------------------ #
    #  Pencere                                                            #
    # ------------------------------------------------------------------ #

    def _set_minimized(self, value: bool) -> None:
        self._minimized = value

    def fit_window(self, inner_width, inner_height, scale) -> None:
        """Pencerenin iç alanını tam WIDTH x HEIGHT yapar.

        İstenen boyuttan pencere çerçevesi payı düşülebildiği için iç alan
        küçük kalabiliyor; arayüz açılınca ölçtüğü değeri ve ekran ölçeğini
        bildirir, fark bir kez eklenir.
        """
        if self._fitted or self.window is None:
            return
        values = (inner_width, inner_height, scale)
        if not all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in values) or not 0.5 <= scale <= 5:
            return
        dw, dh = round((WIDTH - inner_width) * scale), round((HEIGHT - inner_height) * scale)
        try:
            # pywebview'in resize'ı kullanılmaz: SWP_SHOWWINDOW ile çağırdığı için
            # tepside (gizli) başlayan pencereyi görünür yapıyordu.
            hwnd = int(self.window.native.Handle.ToInt64())
            if not hwnd or _user32.IsIconic(hwnd) or abs(dw) > 300 or abs(dh) > 300:
                return  # küçültülmüşken ölçü anlamsız; arayüz pencere açılınca yeniden bildirir
            self._fitted = True
            if not (dw or dh):
                return
            rect = wintypes.RECT()
            if _user32.GetWindowRect(hwnd, ctypes.byref(rect)):
                _user32.SetWindowPos(
                    hwnd, None, 0, 0, rect.right - rect.left + dw, rect.bottom - rect.top + dh,
                    _SWP_NOMOVE | _SWP_NOZORDER | _SWP_NOACTIVATE,
                )
        except Exception as exc:
            self.log(f"fit_window: {exc!r}")

    def _on_closing(self):
        if self._quitting:
            return True
        if _user32.GetSystemMetrics(_SM_SHUTTINGDOWN):
            return True  # Windows kapanıyor: kapanmayı engelleme
        self.hide_window()  # Alt+F4 de × gibi davranır
        return False

    def _allow_windows_shutdown(self) -> None:
        """Windows kapanırken ya da oturum kapatılırken pencerenin kapanmasına izin verir.

        Pencereyi kapatma isteği normalde reddedilir (tepsiye gizlenir). Aynı ret
        Windows'un "kapanabilir miyim" sorusuna da gidiyor ve pencere açıkken
        Windows'u "bu uygulama kapanmayı engelliyor" ekranında bekletiyordu.
        """
        try:
            from System.Windows.Forms import CloseReason, FormClosingEventHandler

            def handler(_sender, args):
                if args.CloseReason in (CloseReason.WindowsShutDown, CloseReason.TaskManagerClosing):
                    args.Cancel = False

            self._closing_handler = FormClosingEventHandler(handler)  # çöp toplanmasın
            self.window.native.FormClosing += self._closing_handler
        except Exception as exc:
            self.log(f"allow_windows_shutdown: {exc!r}")

    def show_window(self) -> None:
        if self.window is None or self._quitting:
            return
        try:
            self.window.show()
            if self._minimized:
                self.window.restore()
            self._bring_to_front()
        except Exception as exc:
            self.log(f"show_window: {exc!r}")
        self._visible = True
        self._minimized = False

    def _bring_to_front(self) -> None:
        """Pencereyi öne getirir.

        pywebview'in on_top özelliği burada kullanılmaz: pencere iş parçacığı
        dışından ayarlanınca Python kilidini tutarak bekler ve pencere iş
        parçacığıyla karşılıklı kilitlenir (program tepside başlayıp pencere
        ilk kez gösterilirken donuyordu). ctypes çağrıları kilidi bırakır.
        """
        hwnd = int(self.window.native.Handle.ToInt64())
        if not hwnd:
            return
        flags = _SWP_NOMOVE | _SWP_NOSIZE
        _user32.SetWindowPos(hwnd, _HWND_TOPMOST, 0, 0, 0, 0, flags)
        _user32.SetWindowPos(hwnd, _HWND_NOTOPMOST, 0, 0, 0, 0, flags)
        _user32.SetForegroundWindow(hwnd)

    def hide_window(self) -> None:
        if self.window is None:
            return
        if self._visibility == "taskbar":
            # Tepsi simgesi yok: gizlenen pencereye ulaşılamazdı. Oturum sürüyorsa
            # yanlışlıkla sonlanmasın diye küçültülür; boştayken × programı kapatır.
            if self.engine.snapshot()["phase"] != IDLE:
                self.minimize_window()
            else:
                threading.Timer(0.1, self.quit).start()
            return
        try:
            self.window.hide()
        except Exception as exc:
            self.log(f"hide_window: {exc!r}")
        self._visible = False
        self._minimized = False
        if not self.settings["tray_hint_shown"]:
            self.settings["tray_hint_shown"] = True
            settings.save(self.settings)
            self.tray.notify(i18n.t("tray_hint"))

    def minimize_window(self) -> None:
        if self._visibility == "tray":
            self.hide_window()  # görev çubuğunda düğme yok: küçültmek yerine tepsiye gizle
            return
        try:
            self.window.minimize()
            self._minimized = True
        except Exception as exc:
            self.log(f"minimize_window: {exc!r}")

    # ------------------------------------------------------------------ #
    #  Görünüm: saatin yanı / görev çubuğu                                #
    # ------------------------------------------------------------------ #

    def set_visibility(self, mode) -> str:
        if mode in settings.VISIBILITY and mode != self._visibility:
            with self._lock:
                self._visibility = mode
                self.settings["visibility"] = mode
                settings.save(self.settings)
            self.tray.set_visible(mode != "taskbar")
            self._apply_taskbar_button()
        return self._visibility

    def _apply_taskbar_button(self) -> None:
        """Görev çubuğu düğmesini görünüm ayarına göre gösterir ya da kaldırır.

        Düğme pencerenin genişletilmiş stiliyle belirlenir (araç penceresi =
        düğme yok). Stil yalnız pencere gizliyken değiştirilince etkili olur;
        bu yüzden pencere açıksa bir an gizlenip yeniden gösterilir. Hepsi
        ctypes ile yapılır (bkz. _bring_to_front'taki kilitlenme notu).
        """
        if self.window is None or self._quitting:
            return
        try:
            hwnd = int(self.window.native.Handle.ToInt64())
            if not hwnd:
                return
            style = _user32.GetWindowLongPtrW(hwnd, _GWL_EXSTYLE)
            if self._visibility == "tray":
                wanted = (style | _WS_EX_TOOLWINDOW) & ~_WS_EX_APPWINDOW
            else:
                wanted = style & ~_WS_EX_TOOLWINDOW
            if wanted == style:
                return
            shown = bool(_user32.IsWindowVisible(hwnd))
            if shown:
                _user32.ShowWindow(hwnd, _SW_HIDE)
            _user32.SetWindowLongPtrW(hwnd, _GWL_EXSTYLE, wanted)
            if shown:
                _user32.ShowWindow(hwnd, _SW_SHOW)
        except Exception as exc:
            self.log(f"taskbar_button: {exc!r}")

    def set_startup(self, enabled) -> bool:
        if isinstance(enabled, bool):
            (startup.enable if enabled else startup.disable)()
        return startup.is_enabled()

    def toggle_window(self) -> None:
        if self._visible and not self._minimized:
            self.hide_window()
        else:
            self.show_window()

    # ------------------------------------------------------------------ #
    #  Tepsi                                                              #
    # ------------------------------------------------------------------ #

    def quick_start(self, minutes: int) -> None:
        """Tepsiden hızlı başlatma: yalnız uyanık tutar, bitişte hiçbir işlem yapmaz."""
        self.engine.start_session(
            minutes=minutes or None,
            infinite=minutes == 0,
            action="none",
            sound=self.settings["sound_enabled"],
            monitor_off=False,
        )

    def set_language(self, code: str) -> None:
        if not i18n.set_language(code):
            return
        with self._lock:
            self.settings["language"] = code
            self._lang_rev += 1
            settings.save(self.settings)
        self.tray.refresh_language()

    def _on_engine_change(self, state: dict) -> None:
        self.tray.update(state)

    # ------------------------------------------------------------------ #
    #  Arayüz                                                             #
    # ------------------------------------------------------------------ #

    def ui_state(self) -> dict:
        state = self.engine.snapshot()
        state["lang_rev"] = self._lang_rev
        return state

    def ui_init(self) -> dict:
        return {
            "version": __version__,
            "lang": i18n.language(),
            "lang_rev": self._lang_rev,
            "texts": dict(i18n.texts()),
            "prefs": {
                "minutes": self.settings["duration_minutes"],
                "infinite": self.settings["infinite"],
                "sound": self.settings["sound_enabled"],
                "monitor_off": self.settings["monitor_off"],
            },
            "visibility": self._visibility,
            "startup": startup.is_enabled(),
            "languages": [{"code": code, "name": name} for code, name in i18n.LANGUAGE_NAMES.items()],
            "hibernate": self.power.hibernate_available(),
            "limits": {"min": settings.MIN_MINUTES, "max": settings.MAX_MINUTES},
            "state": self.ui_state(),
        }

    def ui_start(self, request) -> dict:
        if not isinstance(request, dict):
            return {"ok": False, "error": "bad_request", "state": self.ui_state()}
        result = self.engine.start_session(
            minutes=request.get("minutes"),
            infinite=request.get("infinite"),
            action=request.get("action"),
            sound=request.get("sound"),
            monitor_off=request.get("monitor_off"),
        ) or {"ok": False, "error": "timeout"}
        if result.get("ok"):
            self.remember(request)
        result["state"] = self.ui_state()
        return result

    def remember(self, prefs) -> None:
        """Arayüzdeki seçimleri saklar. Geçersiz değerler eski değeri bozmaz."""
        if not isinstance(prefs, dict):
            return
        with self._lock:
            if settings.valid_minutes(prefs.get("minutes")):
                self.settings["duration_minutes"] = prefs["minutes"]
            for source, target in (("infinite", "infinite"), ("sound", "sound_enabled"), ("monitor_off", "monitor_off")):
                if isinstance(prefs.get(source), bool):
                    self.settings[target] = prefs[source]
            settings.save(self.settings)

    # ------------------------------------------------------------------ #
    #  Kayıt (yalnız INSOMNIA_DEBUG=1 iken)                               #
    # ------------------------------------------------------------------ #

    def log(self, message: str) -> None:
        if os.environ.get("INSOMNIA_DEBUG") != "1":
            return
        try:
            os.makedirs(_local_dir(), exist_ok=True)
            with open(os.path.join(_local_dir(), "insomnia.log"), "a", encoding="utf-8") as f:
                f.write(message + "\n")
        except OSError:
            pass
