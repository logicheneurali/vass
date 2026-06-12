"""Win32 overlay for VASS — always-on-top colored rectangle."""

import ctypes
import ctypes.wintypes
import sys
import time

user32 = ctypes.windll.user32
gdi32 = ctypes.windll.gdi32
kernel32 = ctypes.windll.kernel32
hinst = kernel32.GetModuleHandleW(None)

# Register a simple window class
WNDPROC = ctypes.WINFUNCTYPE(
    ctypes.c_int,
    ctypes.wintypes.HWND, ctypes.wintypes.UINT,
    ctypes.wintypes.WPARAM, ctypes.wintypes.LPARAM,
)

_handle = None

def _create_overlay(x, y, w, h, duration):
    global _handle

    class_name = "VASS_HL_CLASS"

    def wndproc(hwnd, msg, wp, lp):
        if msg == 0x0002:  # WM_DESTROY
            user32.PostQuitMessage(0)
            return 0
        if msg == 0x000F:  # WM_PAINT
            ps = ctypes.wintypes.PAINTSTRUCT()
            dc = user32.BeginPaint(hwnd, ctypes.byref(ps))
            brush = gdi32.CreateSolidBrush(0x0000FF00)  # Green
            old = gdi32.SelectObject(dc, brush)
            pen = gdi32.CreatePen(0, 3, 0x000000FF)  # Red pen
            gdi32.SelectObject(dc, pen)
            gdi32.Rectangle(dc, 0, 0, w, h)
            gdi32.SelectObject(dc, old)
            gdi32.DeleteObject(brush)
            gdi32.DeleteObject(pen)
            user32.EndPaint(hwnd, ctypes.byref(ps))
            return 0
        return user32.DefWindowProcW(hwnd, msg, wp, lp)

    wc = ctypes.wintypes.WNDCLASSEX()
    wc.cbSize = ctypes.sizeof(wc)
    wc.style = 0
    wc.lpfnWndProc = WNDPROC(wndproc)
    wc.hInstance = hinst
    wc.lpszClassName = class_name
    wc.hbrBackground = 5  # HOLLOW_BRUSH

    atom = user32.RegisterClassExW(ctypes.byref(wc))

    # Use COLORREF magenta as color key
    COLORKEY = 0x00FF00FF  # BGR → magenta
    ALPHA = 200

    hwnd = user32.CreateWindowExW(
        0x80000 | 0x20,  # WS_EX_LAYERED | WS_EX_TRANSPARENT
        class_name, None,
        0x80000000,  # WS_POPUP
        x, y, w, h,
        None, None, hinst, None,
    )
    if not hwnd:
        return

    # Paint solid magenta first, then draw the colored rect via WM_PAINT
    # Set magenta as transparent color key
    user32.SetLayeredWindowAttributes(hwnd, COLORKEY, ALPHA, 0x01 | 0x02)
    user32.SetWindowPos(hwnd, -1, x, y, w, h, 0x0010 | 0x0020)
    user32.ShowWindow(hwnd, 1)
    user32.UpdateWindow(hwnd)

    _handle = hwnd

    msg = ctypes.wintypes.MSG()
    start = time.time()
    while time.time() - start < duration:
        while user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, 1):
            user32.TranslateMessage(msg)
            user32.DispatchMessageW(msg)
        time.sleep(0.01)

    user32.DestroyWindow(hwnd)
    if _handle == hwnd:
        _handle = None


def close_overlay():
    if _handle:
        user32.DestroyWindow(_handle)


if __name__ == "__main__":
    x = int(sys.argv[1]) if len(sys.argv) > 1 else 200
    y = int(sys.argv[2]) if len(sys.argv) > 2 else 200
    w = int(sys.argv[3]) if len(sys.argv) > 3 else 300
    h = int(sys.argv[4]) if len(sys.argv) > 4 else 100
    dur = float(sys.argv[5]) if len(sys.argv) > 5 else 5.0
    _create_overlay(x, y, w, h, dur)
