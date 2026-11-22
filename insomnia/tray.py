"""Saatin yanındaki simge ve menüsü.

Menü metinleri her açılışta o anki dilden okunur (çağrılabilir metin), bu
yüzden dil değişince menüyü yeniden kurmak gerekmez ve eski dilde kalmaz.
"""

import pystray

from . import APP_NAME, i18n, icons, startup
from .engine import IDLE, WARNING

QUICK = (("q30", 30), ("q60", 60), ("q120", 120), ("qinf", 0))


class Tray:
    def __init__(self, on_toggle_window, on_quick_start, on_stop, on_language, on_exit, is_running):
        self._on_toggle_window = on_toggle_window
        self._on_quick_start = on_quick_start
        self._on_stop = on_stop
        self._on_language = on_language
        self._on_exit = on_exit
        self._is_running = is_running
        self._look = None
        self._state = None
        self.icon = pystray.Icon(APP_NAME, icons.moon(icons.GRAY), i18n.t("tip_ready"), self._menu())

    def _text(self, key):
        return lambda _item: i18n.t(key)

    def _menu(self):
        quick = pystray.Menu(
            *[
                pystray.MenuItem(self._text(key), (lambda m: lambda _i, _it: self._on_quick_start(m))(minutes))
                for key, minutes in QUICK
            ]
        )
        langs = pystray.Menu(
            *[
                pystray.MenuItem(
                    name,
                    (lambda c: lambda _i, _it: self._on_language(c))(code),
                    checked=(lambda c: lambda _item: i18n.language() == c)(code),
                    radio=True,
                )
                for code, name in i18n.LANGUAGE_NAMES.items()
            ]
        )
        return pystray.Menu(
            pystray.MenuItem(self._text("tray_show"), lambda _i, _it: self._on_toggle_window(), default=True),
            pystray.MenuItem(self._text("tray_quick"), quick),
            pystray.MenuItem(
                self._text("tray_stop"), lambda _i, _it: self._on_stop(), enabled=lambda _item: self._is_running()
            ),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(
                self._text("tray_startup"),
                lambda _i, _it: startup.toggle(),
                checked=lambda _item: startup.is_enabled(),
            ),
            pystray.MenuItem(self._text("tray_lang"), langs),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(self._text("tray_exit"), lambda _i, _it: self._on_exit()),
        )

    # -- durum --------------------------------------------------------------

    def update(self, state: dict | None = None) -> None:
        """Simgeyi ve ipucu yazısını oturum durumuna göre günceller."""
        if state is not None:
            self._state = state
        state = self._state
        if state is None:
            return
        step = None  # None: halkasız ay (boşta)
        if state["phase"] == IDLE:
            color, tip = icons.GRAY, i18n.t("tip_ready")
        elif state["phase"] == WARNING:
            color, tip = icons.ACTION_COLORS.get(state["action"], icons.GOLD), i18n.t("tip_warn")
            step = 0
        else:
            step = icons.ring_step(state["remaining"], state["total"], state["infinite"])
            color = icons.ACTION_COLORS.get(state["action"], icons.GOLD) if state["ending"] else icons.GOLD
            if state["infinite"]:
                tip = i18n.t("tip_inf")
            else:
                tip = i18n.t("tip_left", m=-(-state["remaining"] // 60))
        try:
            if (color, step) != self._look:
                self._look = (color, step)
                self.icon.icon = icons.moon(color) if step is None else icons.ring_moon(color, step)
            if self.icon.title != tip:
                self.icon.title = tip
        except Exception:
            pass

    def refresh_language(self) -> None:
        try:
            self.icon.update_menu()
        except Exception:
            pass
        self.update()

    def notify(self, message: str) -> None:
        try:
            self.icon.notify(message, APP_NAME)
        except Exception:
            pass

    # -- yaşam döngüsü ------------------------------------------------------

    def start(self, visible: bool = True) -> None:
        def setup(icon):
            icon.visible = visible

        self.icon.run_detached(setup)

    def set_visible(self, visible: bool) -> None:
        try:
            self.icon.visible = visible
        except Exception:
            pass

    def stop(self) -> None:
        try:
            self.icon.stop()
        except Exception:
            pass
