# Screenshot Window (No Focus Required)

## Method: PrintWindow via win32 (flag=2)
Works on Chrome-based and most Win32 windows without bringing them to foreground.

## Code
import win32gui, win32ui
from ctypes import windll
from PIL import Image

def screenshot_window_by_title(title_keyword, save_path):
    result_hwnd = []
    def cb(hwnd, _):
        if win32gui.IsWindowVisible(hwnd):
            t = win32gui.GetWindowText(hwnd)
            if title_keyword.lower() in t.lower():
                result_hwnd.append(hwnd)
    win32gui.EnumWindows(cb, None)
    if not result_hwnd:
        print('Window not found.')
        return
    hwnd = result_hwnd[0]
    left, top, right, bot = win32gui.GetWindowRect(hwnd)
    w, h = right - left, bot - top
    hwndDC = win32gui.GetWindowDC(hwnd)
    mfcDC  = win32ui.CreateDCFromHandle(hwndDC)
    saveDC = mfcDC.CreateCompatibleDC()
    saveBitMap = win32ui.CreateBitmap()
    saveBitMap.CreateCompatibleBitmap(mfcDC, w, h)
    saveDC.SelectObject(saveBitMap)
    windll.user32.PrintWindow(hwnd, saveDC.GetSafeHdc(), 2)
    bmpinfo = saveBitMap.GetInfo()
    bmpstr  = saveBitMap.GetBitmapBits(True)
    img = Image.frombuffer('RGB', (bmpinfo['bmWidth'], bmpinfo['bmHeight']), bmpstr, 'raw', 'BGRX', 0, 1)
    win32gui.DeleteObject(saveBitMap.GetHandle())
    saveDC.DeleteDC()
    mfcDC.DeleteDC()
    win32gui.ReleaseDC(hwnd, hwndDC)
    img.save(save_path)

## Notes
- Flag 2 = full window, best for Chrome tabs
- Result == 1 means success
- Does NOT require SetForegroundWindow
- Old pyautogui.screenshot after focus method was unreliable — avoid

## If Window Not Found
- If the target window is not open, launch it first before screenshotting.
- For WhatsApp: webbrowser.open('https://web.whatsapp.com')
- For any Chrome URL: webbrowser.open(url)
- After launching, add time.sleep(3) to let the page load before calling PrintWindow.
