# -*- coding: utf-8 -*-
"""Windows で、フローティングのパネルが C4D のメインウィンドウの裏に隠れないようにする。

C4D 2027 の Python の非同期ダイアログ（DLG_TYPE_ASYNC）は、Windows では所有者のない独立した
トップレベルウィンドウとして作られる。そのためメインウィンドウをクリックすると裏に回る。
窓の所有者をメインウィンドウにすると、常にメインウィンドウより前に表示される
（ほかのアプリより前に出る「最前面」にはしない）。macOS などでは何もしない。
"""
import sys

if sys.platform == "win32":
    import ctypes
    from ctypes import wintypes

    _user32 = ctypes.WinDLL("user32", use_last_error=True)
    _kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

    _WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    _user32.EnumWindows.argtypes = [_WNDENUMPROC, wintypes.LPARAM]
    _user32.EnumWindows.restype = wintypes.BOOL
    _user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    _user32.GetWindowThreadProcessId.restype = wintypes.DWORD
    _user32.IsWindowVisible.argtypes = [wintypes.HWND]
    _user32.IsWindowVisible.restype = wintypes.BOOL
    _user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    _user32.GetWindowTextW.restype = ctypes.c_int
    _user32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    _user32.GetClassNameW.restype = ctypes.c_int
    _user32.GetWindow.argtypes = [wintypes.HWND, wintypes.UINT]
    _user32.GetWindow.restype = wintypes.HWND
    _user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
    _user32.GetWindowRect.restype = wintypes.BOOL
    _user32.SetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_ssize_t]
    _user32.SetWindowLongPtrW.restype = ctypes.c_ssize_t
    _user32.GetForegroundWindow.argtypes = []
    _user32.GetForegroundWindow.restype = wintypes.HWND

    _GW_OWNER = 4
    _GWLP_HWNDPARENT = -8
    _C4D_WINDOW_CLASS = "C4DR_WIN"


def _process_windows():
    """この C4D プロセスの、表示中のトップレベルウィンドウ [(hwnd, title, class, owner, area)]。"""
    pid = _kernel32.GetCurrentProcessId()
    found = []

    def callback(hwnd, _lparam):
        owner_pid = wintypes.DWORD()
        _user32.GetWindowThreadProcessId(hwnd, ctypes.byref(owner_pid))
        if owner_pid.value != pid or not _user32.IsWindowVisible(hwnd):
            return True
        title = ctypes.create_unicode_buffer(256)
        _user32.GetWindowTextW(hwnd, title, 256)
        cls = ctypes.create_unicode_buffer(256)
        _user32.GetClassNameW(hwnd, cls, 256)
        rect = wintypes.RECT()
        _user32.GetWindowRect(hwnd, ctypes.byref(rect))
        area = max(0, rect.right - rect.left) * max(0, rect.bottom - rect.top)
        owner = _user32.GetWindow(hwnd, _GW_OWNER)
        found.append((hwnd, title.value, cls.value, owner, area))
        return True

    _user32.EnumWindows(_WNDENUMPROC(callback), 0)
    return found


def is_foreground(title):
    """いま前面（キーボードの入力先）の窓の題名が title か。Windows 以外では False。"""
    if sys.platform != "win32":
        return False
    try:
        hwnd = _user32.GetForegroundWindow()
        if not hwnd:
            return False
        buf = ctypes.create_unicode_buffer(256)
        _user32.GetWindowTextW(hwnd, buf, 256)
        return buf.value == title
    except Exception:
        return False


def keep_above_main(title):
    """題名が title の C4D の窓（フローティングのパネル）の所有者を、メインウィンドウにする。

    ドッキング中は独立した窓が無いので何もしない。設定し直した窓の数を返す。
    """
    if sys.platform != "win32":
        return 0
    try:
        windows = [w for w in _process_windows() if w[2].startswith(_C4D_WINDOW_CLASS)]
        ours = [w for w in windows if w[1] == title]
        if not ours:
            return 0
        candidates = [w for w in windows if w[1] != title and not w[3]]
        if not candidates:
            return 0
        main = max(candidates, key=lambda w: w[4])[0]
        changed = 0
        for hwnd, _t, _c, owner, _a in ours:
            if owner != main:
                _user32.SetWindowLongPtrW(hwnd, _GWLP_HWNDPARENT, main)
                changed += 1
        return changed
    except Exception:  # 窓の操作に失敗してもパネル自体は使えるようにする
        return 0
