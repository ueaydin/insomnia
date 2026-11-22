"""Tek kopya çalıştırma.

İlk kopya adlandırılmış bir mutex ve bir olay oluşturur. İkinci kez açılan
kopya olayı tetikleyip çıkar; ilk kopya da kendi penceresini gösterir.
Pencere başlığına göre arama yapılmaz, bu yüzden adı "Insomnia" olan başka
bir programın penceresi yanlışlıkla öne getirilmez.
"""

import ctypes
import threading
from ctypes import wintypes

_MUTEX = "Local\\Insomnia.Instance"
_EVENT = "Local\\Insomnia.ShowWindow"

ERROR_ALREADY_EXISTS = 183
EVENT_MODIFY_STATE = 0x0002
INFINITE = 0xFFFFFFFF
WAIT_OBJECT_0 = 0
ASFW_ANY = 0xFFFFFFFF

_k32 = ctypes.WinDLL("kernel32", use_last_error=True)
_k32.CreateMutexW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR]
_k32.CreateMutexW.restype = wintypes.HANDLE
_k32.CreateEventW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.BOOL, wintypes.LPCWSTR]
_k32.CreateEventW.restype = wintypes.HANDLE
_k32.OpenEventW.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.LPCWSTR]
_k32.OpenEventW.restype = wintypes.HANDLE
_k32.SetEvent.argtypes = [wintypes.HANDLE]
_k32.SetEvent.restype = wintypes.BOOL
_k32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
_k32.WaitForSingleObject.restype = wintypes.DWORD
_k32.CloseHandle.argtypes = [wintypes.HANDLE]
_k32.CloseHandle.restype = wintypes.BOOL

_handles = []  # program yaşadığı sürece açık kalmalı


def acquire() -> bool:
    """Bu kopya ilk kopyaysa True. Değilse çalışan kopyaya "pencereni göster" der."""
    mutex = _k32.CreateMutexW(None, False, _MUTEX)
    already = ctypes.get_last_error() == ERROR_ALREADY_EXISTS
    if mutex and not already:
        _handles.append(mutex)
        return True
    if mutex:
        _k32.CloseHandle(mutex)
    event = _k32.OpenEventW(EVENT_MODIFY_STATE, False, _EVENT)
    if event:
        try:  # çalışan kopyanın penceresini öne alabilmesi için izin ver
            ctypes.WinDLL("user32").AllowSetForegroundWindow(ASFW_ANY)
        except OSError:
            pass
        _k32.SetEvent(event)
        _k32.CloseHandle(event)
    return False


def listen(on_show) -> None:
    """Başka bir kopya açılmaya çalıştığında on_show çağrılır."""
    event = _k32.CreateEventW(None, False, False, _EVENT)
    if not event:
        return
    _handles.append(event)

    def _wait():
        while _k32.WaitForSingleObject(event, INFINITE) == WAIT_OBJECT_0:
            try:
                on_show()
            except Exception:
                pass

    threading.Thread(target=_wait, name="insomnia-instance", daemon=True).start()
