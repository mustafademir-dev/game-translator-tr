"""Win32 yardımcıları (ctypes). Ek kütüphane yok."""
from __future__ import annotations

import ctypes
from ctypes import wintypes

user32 = ctypes.WinDLL("user32", use_last_error=True)
dwmapi = ctypes.WinDLL("dwmapi")

GWL_EXSTYLE = -20
WS_EX_LAYERED = 0x00080000
WS_EX_TRANSPARENT = 0x00000020
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_NOACTIVATE = 0x08000000
WDA_NONE = 0x0
WDA_EXCLUDEFROMCAPTURE = 0x11
WM_HOTKEY = 0x0312
MOD_ALT, MOD_CONTROL, MOD_SHIFT, MOD_WIN, MOD_NOREPEAT = 0x1, 0x2, 0x4, 0x8, 0x4000
DWMWA_CLOAKED = 14
DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2 = ctypes.c_void_p(-4)

user32.GetWindowLongPtrW.restype = ctypes.c_ssize_t
user32.GetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int]
user32.SetWindowLongPtrW.restype = ctypes.c_ssize_t
user32.SetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_ssize_t]
user32.SetWindowDisplayAffinity.argtypes = [wintypes.HWND, wintypes.DWORD]
user32.GetWindowDisplayAffinity.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
user32.RegisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int, wintypes.UINT, wintypes.UINT]
user32.UnregisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int]
user32.GetClientRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
user32.ClientToScreen.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.POINT)]
user32.IsWindow.argtypes = [wintypes.HWND]
user32.IsIconic.argtypes = [wintypes.HWND]
user32.IsWindowVisible.argtypes = [wintypes.HWND]
user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]


def set_dpi_awareness() -> None:
    """Per-monitor DPI aware (v2). Qt oluşturulmadan önce çağrılır."""
    try:
        user32.SetProcessDpiAwarenessContext(DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2)
    except (AttributeError, OSError):
        pass


def window_title(hwnd: int) -> str:
    n = user32.GetWindowTextLengthW(hwnd)
    buf = ctypes.create_unicode_buffer(n + 1)
    user32.GetWindowTextW(hwnd, buf, n + 1)
    return buf.value


def _is_cloaked(hwnd: int) -> bool:
    val = ctypes.c_int(0)
    dwmapi.DwmGetWindowAttribute(wintypes.HWND(hwnd), DWMWA_CLOAKED, ctypes.byref(val), ctypes.sizeof(val))
    return val.value != 0


def list_windows(exclude_pid: int | None = None) -> list[tuple[int, str]]:
    """Görünür, başlıklı üst seviye pencereler: [(hwnd, başlık)]."""
    out: list[tuple[int, str]] = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def cb(hwnd, _):
        if not user32.IsWindowVisible(hwnd) or _is_cloaked(hwnd):
            return True
        if user32.GetWindowLongPtrW(hwnd, GWL_EXSTYLE) & WS_EX_TOOLWINDOW:
            return True
        title = window_title(hwnd)
        if not title:
            return True
        if exclude_pid is not None:
            pid = wintypes.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            if pid.value == exclude_pid:
                return True
        out.append((int(hwnd), title))
        return True

    user32.EnumWindows(cb, 0)
    return out


def find_window(title: str) -> int | None:
    for hwnd, t in list_windows():
        if t == title:
            return hwnd
    return None


def is_window(hwnd: int) -> bool:
    return bool(user32.IsWindow(hwnd))


def is_minimized(hwnd: int) -> bool:
    return bool(user32.IsIconic(hwnd))


def client_rect_screen(hwnd: int) -> tuple[int, int, int, int] | None:
    """Pencerenin istemci alanı, ekran fiziksel pikseli olarak (x, y, w, h)."""
    rc = wintypes.RECT()
    if not user32.GetClientRect(hwnd, ctypes.byref(rc)):
        return None
    pt = wintypes.POINT(0, 0)
    if not user32.ClientToScreen(hwnd, ctypes.byref(pt)):
        return None
    return pt.x, pt.y, rc.right - rc.left, rc.bottom - rc.top


def get_exstyle(hwnd: int) -> int:
    return user32.GetWindowLongPtrW(hwnd, GWL_EXSTYLE)


def set_click_through(hwnd: int, enabled: bool) -> None:
    style = get_exstyle(hwnd)
    if enabled:
        style |= WS_EX_TRANSPARENT | WS_EX_LAYERED
    else:
        style &= ~WS_EX_TRANSPARENT
    user32.SetWindowLongPtrW(hwnd, GWL_EXSTYLE, style)


def exclude_from_capture(hwnd: int) -> bool:
    return bool(user32.SetWindowDisplayAffinity(hwnd, WDA_EXCLUDEFROMCAPTURE))


def display_affinity(hwnd: int) -> int:
    val = wintypes.DWORD()
    user32.GetWindowDisplayAffinity(hwnd, ctypes.byref(val))
    return val.value


_KEYS = {
    **{chr(c): c for c in range(ord("A"), ord("Z") + 1)},
    **{str(d): 0x30 + d for d in range(10)},
    **{f"F{i}": 0x6F + i for i in range(1, 13)},
    "SPACE": 0x20, "TAB": 0x09, "ESC": 0x1B, "HOME": 0x24, "END": 0x23,
    "INSERT": 0x2D, "DELETE": 0x2E, "PAGEUP": 0x21, "PAGEDOWN": 0x22,
}
_MODS = {"CTRL": MOD_CONTROL, "CONTROL": MOD_CONTROL, "ALT": MOD_ALT, "SHIFT": MOD_SHIFT, "WIN": MOD_WIN}


def parse_hotkey(spec: str) -> tuple[int, int]:
    """'Ctrl+Alt+T' -> (modifiers, vk)."""
    mods, vk = 0, None
    for part in spec.replace(" ", "").upper().split("+"):
        if part in _MODS:
            mods |= _MODS[part]
        elif part in _KEYS:
            vk = _KEYS[part]
        else:
            raise ValueError(f"Bilinmeyen tuş: {part}")
    if vk is None:
        raise ValueError(f"Kısayolda tuş yok: {spec}")
    return mods, vk


def register_hotkey(hwnd: int, hk_id: int, spec: str) -> bool:
    mods, vk = parse_hotkey(spec)
    return bool(user32.RegisterHotKey(hwnd, hk_id, mods | MOD_NOREPEAT, vk))


def unregister_hotkey(hwnd: int, hk_id: int) -> None:
    user32.UnregisterHotKey(hwnd, hk_id)
