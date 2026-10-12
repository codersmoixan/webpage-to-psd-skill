"""Read local Windows monitor dimensions; no UI interaction or third-party packages."""
import argparse
import ctypes as c
from ctypes import wintypes as w
import json
from pathlib import Path
import sys


def read_displays():
    if sys.platform != 'win32':
        raise RuntimeError('Native display discovery currently supports Windows only.')
    user = c.WinDLL('user32', use_last_error=True)
    kernel = c.WinDLL('kernel32', use_last_error=True)
    class Info(c.Structure):
        _fields_ = [('size', w.DWORD), ('monitor', w.RECT), ('work', w.RECT),
                    ('flags', w.DWORD), ('device', w.WCHAR * 32)]
    user.SetThreadDpiAwarenessContext.argtypes = [c.c_void_p]
    user.SetThreadDpiAwarenessContext.restype = c.c_void_p
    user.GetForegroundWindow.restype = w.HWND
    user.MonitorFromWindow.argtypes = [w.HWND, w.DWORD]
    user.MonitorFromWindow.restype = w.HANDLE
    user.GetMonitorInfoW.argtypes = [w.HANDLE, c.POINTER(Info)]
    user.GetWindowThreadProcessId.argtypes = [w.HWND, c.POINTER(w.DWORD)]
    kernel.OpenProcess.argtypes = [w.DWORD, w.BOOL, w.DWORD]
    kernel.OpenProcess.restype = w.HANDLE
    kernel.QueryFullProcessImageNameW.argtypes = [w.HANDLE, w.DWORD, w.LPWSTR, c.POINTER(w.DWORD)]
    kernel.CloseHandle.argtypes = [w.HANDLE]
    old = user.SetThreadDpiAwarenessContext(c.c_void_p(-4))
    if not old:
        raise c.WinError(c.get_last_error())
    try:
        window = user.GetForegroundWindow()
        selected = user.MonitorFromWindow(window, 2) if window else None
        process_name = None
        if window:
            pid = w.DWORD()
            user.GetWindowThreadProcessId(window, c.byref(pid))
            process = kernel.OpenProcess(0x1000, False, pid.value)
            if process:
                try:
                    name, length = c.create_unicode_buffer(32768), w.DWORD(32768)
                    if kernel.QueryFullProcessImageNameW(process, 0, name, c.byref(length)):
                        process_name = Path(name.value).name
                finally:
                    kernel.CloseHandle(process)
        result = []
        errors = []
        callback_type = c.WINFUNCTYPE(w.BOOL, w.HANDLE, w.HDC, c.POINTER(w.RECT), w.LPARAM)
        def collect(handle, dc, rect, data):
            info = Info()
            info.size = c.sizeof(info)
            if not user.GetMonitorInfoW(handle, c.byref(info)):
                errors.append(c.get_last_error())
                return False
            scale = None
            try:
                shcore = c.WinDLL('shcore')
                shcore.GetScaleFactorForMonitor.argtypes = [w.HANDLE, c.POINTER(c.c_int)]
                factor = c.c_int()
                if shcore.GetScaleFactorForMonitor(handle, c.byref(factor)) == 0:
                    scale = factor.value / 100
            except (OSError, AttributeError):
                pass
            r = info.monitor
            result.append(dict(device=info.device, physicalWidth=r.right-r.left,
                               physicalHeight=r.bottom-r.top, osScale=scale,
                               primary=bool(info.flags & 1), foreground=handle == selected))
            return True
        callback = callback_type(collect)
        user.EnumDisplayMonitors.argtypes = [w.HDC, c.POINTER(w.RECT), callback_type, w.LPARAM]
        if not user.EnumDisplayMonitors(None, None, callback, 0) or errors:
            raise RuntimeError(f'Monitor enumeration failed: {errors}')
        if not result:
            raise RuntimeError('No displays reported.')
        return dict(source='Windows native monitor rectangles, per-monitor DPI-aware thread',
                    foregroundProcess=process_name, displays=result)
    finally:
        user.SetThreadDpiAwarenessContext(old)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path)
    parser.add_argument('--monitor', help='Exact device name from a previous discovery result')
    args = parser.parse_args()
    try:
        data = read_displays()
        candidates = [d for d in data['displays'] if d['device'] == args.monitor] if args.monitor else [d for d in data['displays'] if d['foreground']]
        if not candidates and not args.monitor and len(data['displays']) == 1:
            candidates = data['displays']
            data['selectionReason'] = 'Only one attached display; foreground window unavailable'
        if len(candidates) != 1:
            raise RuntimeError('Cannot identify one monitor; choose an exact reported device name.')
        data['selected'] = candidates[0]
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf8')
        print(json.dumps(data, ensure_ascii=False))
    except (RuntimeError, OSError) as error:
        print(json.dumps(dict(available=False, error=str(error))))
        raise SystemExit(1)


if __name__ == '__main__':
    main()
