"""Windows güç işlemleri.

Önemli: SetThreadExecutionState çağrıyı yapan iş parçacığına bağlıdır; o iş
parçacığı biterse istek de düşer. Bu yüzden keep_awake/release yalnızca
zamanlayıcının kendi (kalıcı) iş parçacığından çağrılır.

INSOMNIA_DRY_RUN=1 ortam değişkeni varken kapatma, yeniden başlatma, hazırda
bekletme ve ekran kapatma gerçekten yapılmaz; yalnızca kaydedilir (deneme için).
"""

import ctypes
import os
import subprocess
import threading
from ctypes import wintypes

ES_CONTINUOUS = 0x80000000
ES_SYSTEM_REQUIRED = 0x00000001
ES_DISPLAY_REQUIRED = 0x00000002

HWND_BROADCAST = 0xFFFF
WM_SYSCOMMAND = 0x0112
SC_MONITORPOWER = 0xF170
MONITOR_OFF = 2
MOUSEEVENTF_MOVE = 0x0001

ACTIONS = ("none", "shutdown", "restart", "hibernate")

_SHUTDOWN_ARGS = {
    "shutdown": ["/s", "/f", "/t", "0"],
    "restart": ["/r", "/f", "/t", "0"],
    "hibernate": ["/h"],
}

_kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
_user32 = ctypes.WinDLL("user32", use_last_error=True)

_kernel32.SetThreadExecutionState.argtypes = [wintypes.DWORD]
_kernel32.SetThreadExecutionState.restype = wintypes.DWORD
_user32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
_user32.PostMessageW.restype = wintypes.BOOL
_user32.mouse_event.argtypes = [wintypes.DWORD, wintypes.DWORD, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p]
_user32.mouse_event.restype = None


def dry_run() -> bool:
    return os.environ.get("INSOMNIA_DRY_RUN") == "1"


class Power:
    def __init__(self):
        self.log: list[str] = []  # deneme kipinde yapılacak işlemler buraya yazılır

    # -- uyanık tutma (yalnız zamanlayıcı iş parçacığından) ------------------

    def keep_awake(self, keep_display: bool) -> None:
        flags = ES_CONTINUOUS | ES_SYSTEM_REQUIRED
        if keep_display:
            flags |= ES_DISPLAY_REQUIRED
        _kernel32.SetThreadExecutionState(flags)

    def release(self) -> None:
        _kernel32.SetThreadExecutionState(ES_CONTINUOUS)

    # -- ekran --------------------------------------------------------------

    def turn_off_screen(self) -> None:
        if dry_run():
            self.log.append("screen_off")
            return
        _user32.PostMessageW(HWND_BROADCAST, WM_SYSCOMMAND, SC_MONITORPOWER, MONITOR_OFF)

    def wake_screen(self) -> None:
        """Kapalı ekranı açar: fareyi bir piksel oynatıp geri alır."""
        if dry_run():
            self.log.append("screen_wake")
            return
        _user32.mouse_event(MOUSEEVENTF_MOVE, 1, 0, 0, None)
        _user32.mouse_event(MOUSEEVENTF_MOVE, 0xFFFFFFFF, 0, 0, None)  # -1

    # -- ses ----------------------------------------------------------------

    def beep(self) -> None:
        if dry_run():
            self.log.append("beep")
            return

        def _play():
            try:
                import winsound

                for _ in range(2):
                    winsound.Beep(1500, 200)
                    threading.Event().wait(0.1)
            except Exception:
                pass

        threading.Thread(target=_play, daemon=True).start()

    # -- bitiş işlemleri ----------------------------------------------------

    def hibernate_available(self) -> bool:
        try:
            return bool(ctypes.WinDLL("powrprof").IsPwrHibernateAllowed())
        except OSError:
            return False

    def run_action(self, action: str) -> bool:
        """Bitiş işlemini uygular. Başarılıysa True döner."""
        args = _SHUTDOWN_ARGS.get(action)
        if args is None:
            return action == "none"
        if dry_run():
            self.log.append(action)
            return True
        exe = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32", "shutdown.exe")
        try:
            done = subprocess.run(
                [exe, *args],
                creationflags=subprocess.CREATE_NO_WINDOW,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=30,
            )
            return done.returncode == 0
        except (OSError, subprocess.SubprocessError):
            return False
