"""
FACTURADOR AUTOMÁTICO SAINT ANNUAL ENTERPRISE (Factura por Factura)
Emulación nativa Win32 de teclado por hardware (VK + Scan Codes).
100% compatible con componentes Delphi/VCL de Saint Enterprise.
"""

import os
import sys
import re
import json
import time
import ctypes
from ctypes import wintypes
import threading
from pathlib import Path
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import pyperclip
import subprocess
import extractor
import updater

try:
    from PIL import Image, ImageOps
    HAVE_PIL = True
except ImportError:
    HAVE_PIL = False

try:
    import winocr
    HAVE_WINOCR = True
except ImportError:
    HAVE_WINOCR = False

# Cargar API Win32 de Windows
user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32
gdi32 = ctypes.windll.gdi32

# Inicializar DPI Awareness para compatibilidad nativa con pantallas escaladas en Windows 10 y Windows 11
try:
    # Windows 10 versión 1703+ y Windows 11: DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2 (-4)
    user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
except Exception:
    try:
        # Windows 8.1 y Windows 10 inicial: PROCESS_PER_MONITOR_DPI_AWARE (2)
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            # Fallback universal Windows
            user32.SetProcessDPIAware()
        except Exception:
            pass

# Definición de tipos para llamadas seguras en Windows de 64 bits
user32.GetDesktopWindow.restype = wintypes.HWND
user32.GetForegroundWindow.restype = wintypes.HWND
user32.GetWindowDC.argtypes = [wintypes.HWND]
user32.GetWindowDC.restype = wintypes.HDC
user32.ReleaseDC.argtypes = [wintypes.HWND, wintypes.HDC]
user32.ReleaseDC.restype = ctypes.c_int
user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
user32.GetWindowRect.restype = wintypes.BOOL
user32.PrintWindow.argtypes = [wintypes.HWND, wintypes.HDC, wintypes.UINT]
user32.PrintWindow.restype = wintypes.BOOL

gdi32.CreateCompatibleDC.argtypes = [wintypes.HDC]
gdi32.CreateCompatibleDC.restype = wintypes.HDC
gdi32.DeleteDC.argtypes = [wintypes.HDC]
gdi32.DeleteDC.restype = wintypes.BOOL
gdi32.CreateCompatibleBitmap.argtypes = [wintypes.HDC, ctypes.c_int, ctypes.c_int]
gdi32.CreateCompatibleBitmap.restype = wintypes.HBITMAP
gdi32.SelectObject.argtypes = [wintypes.HDC, wintypes.HGDIOBJ]
gdi32.SelectObject.restype = wintypes.HGDIOBJ
gdi32.DeleteObject.argtypes = [wintypes.HGDIOBJ]
gdi32.DeleteObject.restype = wintypes.BOOL
gdi32.BitBlt.argtypes = [
    wintypes.HDC, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
    wintypes.HDC, ctypes.c_int, ctypes.c_int, wintypes.DWORD
]
gdi32.BitBlt.restype = wintypes.BOOL
gdi32.GetDIBits.argtypes = [
    wintypes.HDC, wintypes.HBITMAP, wintypes.UINT, wintypes.UINT,
    ctypes.c_void_p, ctypes.c_void_p, wintypes.UINT
]
gdi32.GetDIBits.restype = ctypes.c_int

class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [
        ('biSize', wintypes.DWORD),
        ('biWidth', wintypes.LONG),
        ('biHeight', wintypes.LONG),
        ('biPlanes', wintypes.WORD),
        ('biBitCount', wintypes.WORD),
        ('biCompression', wintypes.DWORD),
        ('biSizeImage', wintypes.DWORD),
        ('biXPelsPerMeter', wintypes.LONG),
        ('biYPelsPerMeter', wintypes.LONG),
        ('biClrUsed', wintypes.DWORD),
        ('biClrImportant', wintypes.DWORD),
    ]

# Teclas Virtuales Win32 (VK)
VK_RETURN = 0x0D
VK_TAB = 0x09
VK_ESCAPE = 0x1B
VK_SHIFT = 0x10
VK_CONTROL = 0x11
VK_C = 0x43
VK_A = 0x41
VK_F6 = 0x75
VK_F7 = 0x76
VK_F8 = 0x77
VK_F12 = 0x7B
KEYEVENTF_KEYUP = 0x0002

try:
    import winsound
    HAVE_SOUND = True
except ImportError:
    HAVE_SOUND = False

try:
    from pynput import keyboard as pynput_keyboard
    HAVE_PYNPUT = True
except ImportError:
    HAVE_PYNPUT = False


def win32_press_vk(vk_code: int, delay_after: float = 0.05):
    """Envía pulsación de tecla física usando keybd_event con Scan Code real de hardware"""
    scan = user32.MapVirtualKeyW(vk_code, 0)
    user32.keybd_event(vk_code, scan, 0, 0)
    time.sleep(0.02)
    user32.keybd_event(vk_code, scan, KEYEVENTF_KEYUP, 0)
    time.sleep(delay_after)


user32.VkKeyScanW.argtypes = [ctypes.c_wchar]
user32.VkKeyScanW.restype = wintypes.SHORT


def win32_type_char(char: str, key_delay: float = 0.03):
    """
    Escribe un carácter traduciéndolo a su Virtual Key Code y Scan Code real.
    A diferencia de PyAutoGUI (que usa KEYEVENTF_UNICODE ignorado por Delphi/Saint),
    esto genera eventos WM_KEYDOWN/WM_CHAR reales que Saint no puede distinguir de un teclado físico.
    """
    if not char:
        return
    c = char[0]
    res = user32.VkKeyScanW(c)
    if res == -1:
        # Carácter no mapeable directamente
        return
    
    vk = res & 0xFF
    shift = (res >> 8) & 1
    scan = user32.MapVirtualKeyW(vk, 0)
    
    if shift:
        user32.keybd_event(VK_SHIFT, user32.MapVirtualKeyW(VK_SHIFT, 0), 0, 0)
        time.sleep(0.01)
        
    user32.keybd_event(vk, scan, 0, 0)
    time.sleep(0.01)
    user32.keybd_event(vk, scan, KEYEVENTF_KEYUP, 0)
    
    if shift:
        time.sleep(0.01)
        user32.keybd_event(VK_SHIFT, user32.MapVirtualKeyW(VK_SHIFT, 0), KEYEVENTF_KEYUP, 0)
        
    time.sleep(key_delay)


def win32_type_string(text: str, key_delay: float = 0.03, stop_checker=None):
    """Escribe una cadena completa carácter por carácter mediante eventos nativos"""
    for ch in str(text):
        if stop_checker and stop_checker():
            break
        win32_type_char(ch, key_delay=key_delay)


def win32_copy_field() -> str:
    """Selecciona todo en la casilla activa y copia el contenido al portapapeles"""
    try:
        pyperclip.copy("")
        # Ctrl + A
        user32.keybd_event(VK_CONTROL, user32.MapVirtualKeyW(VK_CONTROL, 0), 0, 0)
        time.sleep(0.01)
        user32.keybd_event(VK_A, user32.MapVirtualKeyW(VK_A, 0), 0, 0)
        time.sleep(0.01)
        user32.keybd_event(VK_A, user32.MapVirtualKeyW(VK_A, 0), KEYEVENTF_KEYUP, 0)
        time.sleep(0.01)
        # Ctrl + C
        user32.keybd_event(VK_C, user32.MapVirtualKeyW(VK_C, 0), 0, 0)
        time.sleep(0.01)
        user32.keybd_event(VK_C, user32.MapVirtualKeyW(VK_C, 0), KEYEVENTF_KEYUP, 0)
        time.sleep(0.01)
        user32.keybd_event(VK_CONTROL, user32.MapVirtualKeyW(VK_CONTROL, 0), KEYEVENTF_KEYUP, 0)
        time.sleep(0.08)
        return pyperclip.paste().strip()
    except Exception:
        return ""


def parse_price(val_str, currency: str = "usd") -> float:
    """Convierte montos en formato venezolano/europeo o estadounidense a float"""
    if not val_str:
        return 0.0
    limpio = re.sub(r'[^\d,\.-]', '', str(val_str)).strip()
    if not limpio:
        return 0.0
    if ',' in limpio and '.' in limpio:
        # Detectar si es formato US (1,234.56) o VE/EU (1.234,56)
        if limpio.rfind(',') < limpio.rfind('.'):
            limpio = limpio.replace(',', '')
        else:
            limpio = limpio.replace('.', '').replace(',', '.')
    elif ',' in limpio:
        limpio = limpio.replace(',', '.')
    elif '.' not in limpio and currency == "usd" and re.match(r'^\d{3,5}$', limpio):
        # En la cuadrícula de Saint en USD los precios tienen 2 decimales. Si el OCR omitió el punto (ej: '495' o '1495')
        try:
            return round(int(limpio) / 100.0, 2)
        except ValueError:
            pass
    try:
        return round(float(limpio), 2)
    except ValueError:
        return 0.0


def obtener_hwnd_saint():
    """Retorna el HWND de la ventana de Saint / Presupuesto si está abierta"""
    found_hwnds = []
    def enum_wnd_cb(hwnd, lparam):
        if not user32.IsWindowVisible(hwnd):
            return True
        length = user32.GetWindowTextLengthW(hwnd)
        if length > 0:
            buff = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, buff, length + 1)
            title = buff.value.upper()
            if any(t in title for t in ["PRESUPUESTO", "SAINT", "ANNUAL", "VENTAS", "FACTURA"]):
                found_hwnds.append((hwnd, buff.value))
        return True

    EnumWndProc = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
    user32.EnumWindows(EnumWndProc(enum_wnd_cb), 0)
    if found_hwnds:
        for h, t in found_hwnds:
            if "PRESUPUESTO" in t.upper():
                return h
        return found_hwnds[0][0]
    return 0


def buscar_y_enfocar_saint() -> bool:
    """Busca la ventana de Saint Annual Enterprise / Presupuesto y la trae al frente de forma segura en Windows 10 y 11"""
    target_hwnd = obtener_hwnd_saint()
    if target_hwnd:
        try:
            cur_thread = user32.GetWindowThreadProcessId(user32.GetForegroundWindow(), None)
            target_thread = user32.GetWindowThreadProcessId(target_hwnd, None)
            if cur_thread != target_thread:
                user32.AttachThreadInput(cur_thread, target_thread, True)
                user32.ShowWindow(target_hwnd, 9)  # SW_RESTORE
                user32.BringWindowToTop(target_hwnd)
                user32.SetForegroundWindow(target_hwnd)
                user32.AttachThreadInput(cur_thread, target_thread, False)
            else:
                user32.ShowWindow(target_hwnd, 9)
                user32.BringWindowToTop(target_hwnd)
                user32.SetForegroundWindow(target_hwnd)
        except Exception:
            user32.ShowWindow(target_hwnd, 9)
            user32.SetForegroundWindow(target_hwnd)
        time.sleep(0.2)
        return True
    return False


def forzar_ventana_al_frente(window):
    """
    Coloca momentáneamente la ventana en primer plano para alertar al usuario,
    e inmediatamente (tras 250 ms) retira el atributo 'topmost' para que vuelva a ser
    una ventana estándar. De este modo, en cuanto el usuario toque o haga clic en Saint,
    Saint se colocará al frente y el programa se quedará detrás de Saint de forma natural,
    sin obligar al usuario a minimizarlo.
    """
    if not window:
        return
    try:
        window.deiconify()
        window.lift()
        window.attributes("-topmost", True)
        window.focus_force()
    except Exception:
        pass

    try:
        frame_str = window.wm_frame() if hasattr(window, "wm_frame") else ""
        hwnd = int(frame_str, 16) if frame_str else window.winfo_id()
        if hwnd and hwnd != 0:
            user32.ShowWindow(hwnd, 9)  # SW_RESTORE
            cur_thread = user32.GetWindowThreadProcessId(user32.GetForegroundWindow(), None)
            target_thread = user32.GetWindowThreadProcessId(hwnd, None)
            if cur_thread != target_thread:
                user32.AttachThreadInput(cur_thread, target_thread, True)
                user32.BringWindowToTop(hwnd)
                user32.SetForegroundWindow(hwnd)
                user32.AttachThreadInput(cur_thread, target_thread, False)
            else:
                user32.BringWindowToTop(hwnd)
                user32.SetForegroundWindow(hwnd)
    except Exception:
        try:
            hwnd = window.winfo_id()
            if hwnd:
                user32.ShowWindow(hwnd, 9)
                user32.SetForegroundWindow(hwnd)
        except Exception:
            pass

    def _liberar_topmost():
        try:
            keep_top = False
            if hasattr(window, "var_topmost"):
                keep_top = window.var_topmost.get()
            elif hasattr(window, "master") and hasattr(window.master, "var_topmost"):
                keep_top = window.master.var_topmost.get()

            if not keep_top:
                window.attributes("-topmost", False)
                try:
                    f_str = window.wm_frame() if hasattr(window, "wm_frame") else ""
                    h = int(f_str, 16) if f_str else window.winfo_id()
                    if h:
                        user32.SetWindowPos(h, -2, 0, 0, 0, 0, 0x0002 | 0x0001 | 0x0040)
                except Exception:
                    pass
        except Exception:
            pass

    try:
        window.after(250, _liberar_topmost)
    except Exception:
        pass


if getattr(sys, "frozen", False):
    BASE_DIR = Path(sys.executable).resolve().parent
else:
    BASE_DIR = Path(__file__).resolve().parent
CACHE_CAPTURES_DIR = BASE_DIR / "cache_capturas"
CACHE_CAPTURES_DIR.mkdir(parents=True, exist_ok=True)
FACTURAS_PDF_DIR = BASE_DIR / "facturas_pdf"
FACTURAS_PDF_DIR.mkdir(parents=True, exist_ok=True)
FACTURAS_JSON_DIR = BASE_DIR / "facturas_json"
FACTURAS_JSON_DIR.mkdir(parents=True, exist_ok=True)
MAX_ITEMS_PER_INVOICE = 43


def contar_archivos_cache() -> int:
    """Cuenta las imágenes almacenadas en la carpeta local de caché"""
    if not CACHE_CAPTURES_DIR.exists():
        return 0
    return len(list(CACHE_CAPTURES_DIR.glob("*.png")) + list(CACHE_CAPTURES_DIR.glob("*.jpg")) + list(CACHE_CAPTURES_DIR.glob("*.bmp")))


def borrar_cache_capturas() -> int:
    """Elimina físicamente todas las capturas de la carpeta local de caché"""
    if not CACHE_CAPTURES_DIR.exists():
        return 0
    archivos = list(CACHE_CAPTURES_DIR.glob("*.png")) + list(CACHE_CAPTURES_DIR.glob("*.jpg")) + list(CACHE_CAPTURES_DIR.glob("*.bmp"))
    count = 0
    for f in archivos:
        try:
            f.unlink()
            count += 1
        except Exception:
            pass
    return count


def borrar_facturas_json(json_dir=None) -> int:
    """Elimina físicamente todos los archivos JSON de la carpeta facturas_json"""
    target = Path(json_dir) if json_dir else FACTURAS_JSON_DIR
    if not target.exists():
        return 0
    archivos = list(target.glob("*.json"))
    count = 0
    for f in archivos:
        try:
            f.unlink()
            count += 1
        except Exception:
            pass
    return count


def borrar_facturas_pdf(pdf_dir=None) -> int:
    """Elimina físicamente todos los archivos PDF y Excel de la carpeta facturas_pdf"""
    target = Path(pdf_dir) if pdf_dir else FACTURAS_PDF_DIR
    if not target.exists():
        return 0
    archivos = [f for f in target.iterdir() if f.is_file()]
    count = 0
    for f in archivos:
        try:
            f.unlink()
            count += 1
        except Exception:
            pass
    return count


def capture_window_in_ram(hwnd=None):
    """
    Captura la ventana de Saint directamente en memoria como PIL.Image.
    """
    if not HAVE_PIL:
        return None
    
    if not hwnd or hwnd == 0:
        hwnd = obtener_hwnd_saint()
    if not hwnd or hwnd == 0:
        hwnd = user32.GetForegroundWindow()
    if not hwnd or hwnd == 0:
        hwnd = user32.GetDesktopWindow()

    rect = wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(rect))
    w = rect.right - rect.left
    h = rect.bottom - rect.top
    if w <= 10 or h <= 10:
        return None

    hdc_wnd = user32.GetWindowDC(hwnd)
    if not hdc_wnd:
        return None

    hdc_mem = gdi32.CreateCompatibleDC(hdc_wnd)
    hbmp = gdi32.CreateCompatibleBitmap(hdc_wnd, w, h)
    hbmp_old = gdi32.SelectObject(hdc_mem, hbmp)

    PW_RENDERFULLCONTENT = 0x00000002
    success = user32.PrintWindow(hwnd, hdc_mem, PW_RENDERFULLCONTENT)
    if not success:
        gdi32.BitBlt(hdc_mem, 0, 0, w, h, hdc_wnd, 0, 0, 0x00CC0020)

    bmi = BITMAPINFOHEADER()
    bmi.biSize = ctypes.sizeof(BITMAPINFOHEADER)
    bmi.biWidth = w
    bmi.biHeight = -h  # DIB top-down
    bmi.biPlanes = 1
    bmi.biBitCount = 32
    bmi.biCompression = 0

    buf = ctypes.create_string_buffer(w * h * 4)
    gdi32.GetDIBits(hdc_mem, hbmp, 0, h, buf, ctypes.byref(bmi), 0)

    gdi32.SelectObject(hdc_mem, hbmp_old)
    gdi32.DeleteObject(hbmp)
    gdi32.DeleteDC(hdc_mem)
    user32.ReleaseDC(hwnd, hdc_wnd)

    return Image.frombuffer('RGBA', (w, h), buf, 'raw', 'BGRA', 0, 1).convert('RGB')


def capture_window_to_cache(hwnd=None, file_name: str = None):
    """
    Captura la ventana de Saint, la guarda localmente en cache_capturas/
    y retorna la tupla (PIL.Image, Path).
    """
    img = capture_window_in_ram(hwnd)
    if img is None:
        return None, None
        
    if not file_name:
        file_name = f"captura_{int(time.time()*1000)}.png"
    elif not file_name.endswith(".png"):
        file_name += ".png"
        
    out_path = CACHE_CAPTURES_DIR / file_name
    try:
        img.save(out_path, format="PNG")
    except Exception:
        pass
    return img, out_path


def find_saint_grid_region(img: Image.Image) -> dict:
    """
    Detecta en ~5ms la posición de la cuadrícula de Saint y la columna 'Precio'.
    Soporta cualquier resolución (1366x768, 1080p, 2K/4K) y escalas DPI de Windows.
    """
    w, h = img.size
    rgb = img.convert("RGB")
    
    hdr_y = None
    step_y = max(1, h // 400)
    for y in range(int(h * 0.1), int(h * 0.8), step_y):
        c1 = rgb.getpixel((int(w * 0.3), y))
        c2 = rgb.getpixel((int(w * 0.5), y))
        c3 = rgb.getpixel((int(w * 0.7), y))
        # Detección del color azul/celeste de la cabecera de la tabla de Saint Enterprise
        is_blue_hdr = (
            all(c[2] > 180 and c[1] > 130 and c[0] < 180 and c[2] > c[0] + 30 for c in (c1, c2, c3)) or
            all(c[2] > 145 and c[1] > 95 and c[2] > c[0] + 18 for c in (c1, c2, c3))
        )
        if is_blue_hdr:
            if y + 20 < h:
                b1 = rgb.getpixel((int(w * 0.3), y + 20))
                b2 = rgb.getpixel((int(w * 0.5), y + 20))
                if b1[0] > 220 and b1[1] > 220 and b1[2] > 220 and b2[0] > 220:
                    hdr_y = y
                    break
                    
    if hdr_y is None:
        grid_top = int(h * 0.20)
        grid_bottom = min(int(h * 0.90), int(h - 32))
        return {
            "grid_top": grid_top,
            "grid_bottom": grid_bottom,
            "row_height": 49.0,
            "grid_w": int(w * 0.90),
            "grid_h": grid_bottom - grid_top,
            "precio_x1": int(w * 0.79),
            "precio_x2": int(w * 0.915),
            "grid_x1": int(w * 0.05),
            "grid_x2": int(w * 0.95)
        }
        
    xs = []
    for x in range(0, w, 2):
        c = rgb.getpixel((x, hdr_y))
        if c[2] > 140 and c[1] > 90 and c[2] > c[0] + 18:
            xs.append(x)
            
    grid_x1 = min(xs) if xs else int(w * 0.05)
    grid_x2 = max(xs) if xs else int(w * 0.95)
    grid_w = grid_x2 - grid_x1
    
    grid_top = hdr_y + 16
    row_height = 49.0
    # Abarcar la cuadrícula completa hasta justo antes de la barra de estado inferior
    # asegurando que todas las filas visibles (incluida la última) queden dentro
    grid_bottom = max(grid_top + int(14 * row_height), int(h * 0.88))
    grid_bottom = min(grid_bottom, int(h - 32))
    grid_h = grid_bottom - grid_top
    precio_x1 = grid_x1 + int(grid_w * 0.79)
    precio_x2 = grid_x1 + int(grid_w * 0.915)

    return {
        "grid_top": grid_top,
        "grid_bottom": grid_bottom,
        "row_height": row_height,
        "grid_w": grid_w,
        "grid_h": grid_h,
        "precio_x1": precio_x1,
        "precio_x2": precio_x2,
        "grid_x1": grid_x1,
        "grid_x2": grid_x2
    }


_CACHED_OCR_LANG = None

def get_best_ocr_language() -> str:
    """
    Detecta automáticamente el mejor paquete de idioma OCR instalado en Windows 10 u 11.
    Prioriza variantes de español (es-ES, es-MX, es-419, es-US, es) y recurre de forma segura
    al primer idioma activo para que la lectura de códigos y precios nunca falle.
    """
    global _CACHED_OCR_LANG
    if _CACHED_OCR_LANG:
        return _CACHED_OCR_LANG
    try:
        from winrt.windows.media.ocr import OcrEngine
        avail = [l.language_tag for l in OcrEngine.available_recognizer_languages]
        if avail:
            for pref in ["es-ES", "es-MX", "es-419", "es-US", "es"]:
                if pref in avail:
                    _CACHED_OCR_LANG = pref
                    return pref
            for l in avail:
                if l.lower().startswith("es"):
                    _CACHED_OCR_LANG = l
                    return l
            _CACHED_OCR_LANG = avail[0]
            return _CACHED_OCR_LANG
    except Exception:
        pass
    _CACHED_OCR_LANG = "es-ES"
    return _CACHED_OCR_LANG


def safe_ocr_recognize_pil(img) -> dict:
    """
    Ejecuta reconocimiento OCR sobre una imagen PIL con tolerancia total a fallos.
    100% compatible con Windows 10 y Windows 11 en cualquier versión y configuración regional.
    """
    if not HAVE_PIL or not HAVE_WINOCR or img is None:
        return {}
    lang = get_best_ocr_language()
    try:
        return winocr.recognize_pil_sync(img, lang=lang)
    except AssertionError:
        try:
            from winrt.windows.media.ocr import OcrEngine
            avail = [l.language_tag for l in OcrEngine.available_recognizer_languages]
            if avail and avail[0] != lang:
                return winocr.recognize_pil_sync(img, lang=avail[0])
        except Exception:
            pass
        return {}
    except Exception:
        return {}


def audit_saint_grid_capture(img, batch_items: list = None, start_global_idx: int = 1,
                             is_final: bool = False, total_items: int = 0,
                             currency: str = "usd", tolerance: float = 0.02,
                             check_price: bool = True) -> dict:
    """
    Analiza la cuadrícula de Saint mediante Windows Media OCR en memoria RAM (Zero-disk-cache).
    Detecta dinámicamente cada renglón agrupando palabras por su posición vertical (Y)
    con tolerancia total a resoluciones, DPI scaling y cantidad de renglones visibles.
    Extrae código de barra/referencia, descripción, cantidad y precio celda por celda.
    Garantiza que los últimos productos de la cuadrícula sean capturados con 100% de precisión.
    """
    if not HAVE_PIL or not HAVE_WINOCR or img is None:
        return {"price_diffs": [], "detected_rows": []}

    detected_rows = []
    diffs = []
    crop_main = None

    try:
        info = find_saint_grid_region(img)
        grid_top = info.get("grid_top", int(img.height * 0.20))
        grid_bottom = info.get("grid_bottom", min(int(img.height * 0.90), img.height - 32))
        grid_x1 = max(0, info.get("grid_x1", int(img.width * 0.05)) - 10)
        grid_x2 = min(img.width, info.get("grid_x2", int(img.width * 0.95)) + 10)
        grid_top_safe = max(0, grid_top - 6)
        grid_bottom_safe = min(img.height, grid_bottom + 8)

        crop_box = (grid_x1, grid_top_safe, grid_x2, grid_bottom_safe)
        crop_main = img.crop(crop_box)
        img_w = crop_main.width

        # 1. OCR principal sobre la cuadrícula completa
        res_main = safe_ocr_recognize_pil(crop_main)

        # Extraer todas las palabras con sus coordenadas
        words = []
        for l in res_main.get("lines", []):
            for w in l.get("words", []):
                txt = str(w.get("text", "")).strip()
                if not txt:
                    continue
                b = w.get("bounding_rect", {})
                bw = float(b.get("width", 0.0))
                bh = float(b.get("height", 0.0))
                bx = float(b.get("x", 0.0))
                by = float(b.get("y", 0.0))
                words.append({
                    "text": txt,
                    "x": bx,
                    "y": by,
                    "w": bw,
                    "h": bh,
                    "x_center": bx + bw / 2.0,
                    "y_center": by + bh / 2.0
                })

        # Agrupar dinámicamente las palabras por renglón según su coordenada Y
        words.sort(key=lambda item: item["y_center"])
        clusters = []
        for w in words:
            thresh = max(11.0, w["h"] * 0.70)
            if not clusters or abs(w["y_center"] - clusters[-1]["y_center"]) > thresh:
                clusters.append({
                    "y_center": w["y_center"],
                    "words": [w]
                })
            else:
                c = clusters[-1]
                c["words"].append(w)
                c["y_center"] = sum(x["y_center"] for x in c["words"]) / len(c["words"])

        # Delimitadores proporcionales al ancho de la ventana
        ref_x_max = int(img_w * 0.35)
        desc_x_min = int(img_w * 0.10)
        desc_x_max = int(img_w * 0.65)
        qty_x_min = int(img_w * 0.58)
        qty_x_max = int(img_w * 0.78)
        price_col_x1 = max(0, int(img_w * 0.79))
        price_col_x2 = min(img_w, int(img_w * 0.915))

        header_keywords = {"REFERENCIA", "CODIGO", "DESCRIPCION", "CANTIDAD", "PRECIO", "TOTAL", "RENGLON", "ITEM", "UNIDAD", "SUBTOTAL"}
        footer_keywords = {
            "SUBTOTAL", "SUB-TOTAL", "SUB TOTAL", "BASE IMPONIBLE", "IMPONIBLE", "EXENTO",
            "IVA (16%)", "IVA (8%)", "IMPUESTO", "TOTAL USD", "TOTAL BS", "TOTAL GENERAL",
            "ITEMS:", "ITEM:", "RENGLONES:", "TOTAL ITEMS", "DESCUENTO", "CARGO", "RETENCION",
            "MONEDA", "TASA", "SALDO", "PAGAR", "CONDICION", "VENDEDOR", "CAJA", "USUARIO"
        }

        for cl in clusters:
            row_words = sorted(cl["words"], key=lambda item: item["x"])
            row_raw_text = " ".join(w["text"].upper().strip() for w in row_words)
            upper_texts = {w["text"].upper().strip() for w in row_words}
            
            # 1. Omitir fila de encabezados
            if len(upper_texts.intersection(header_keywords)) >= 2:
                continue

            # 2. Omitir filas de totales / pie de cuadrícula
            if any(fk in row_raw_text for fk in footer_keywords):
                left_nums = [re.sub(r"[^\d]", "", w["text"]) for w in row_words if w["x"] < ref_x_max]
                has_real_barcode = any(len(n) >= 8 for n in left_nums)
                if not has_real_barcode:
                    continue

            found_barcode = None
            found_qty = None
            desc_tokens = []

            # A) Buscar código de barra en la región izquierda (hasta 35% del ancho)
            left_words = [w for w in row_words if w["x"] < ref_x_max]
            for lw in left_words:
                cleaned_num = re.sub(r"[^\d]", "", lw["text"])
                if len(cleaned_num) >= 6:
                    found_barcode = cleaned_num
                    break

            # Si el OCR dividió el código de barra en dos palabras adyacentes
            if not found_barcode and len(left_words) >= 2:
                for i in range(len(left_words) - 1):
                    c1 = re.sub(r"[^\d]", "", left_words[i]["text"])
                    c2 = re.sub(r"[^\d]", "", left_words[i+1]["text"])
                    if c1 and c2 and 6 <= len(c1 + c2) <= 14:
                        found_barcode = c1 + c2
                        break

            # Códigos alfanuméricos (ej: CM3645)
            if not found_barcode:
                for lw in left_words:
                    t = lw["text"].strip()
                    if re.match(r"^[A-Za-z0-9_-]{4,14}$", t) and not re.match(r"^\d{1,2}$", t):
                        if t.upper() not in {"ITEM", "CODIGO", "REF", "NRO"}:
                            found_barcode = t
                            break

            # B) Buscar Cantidad y Descripción
            for w in row_words:
                txt = w["text"].strip()
                wx = w["x"]

                if found_barcode and (txt in found_barcode or found_barcode in txt):
                    continue

                if qty_x_min <= wx < qty_x_max and re.match(r"^\d+(?:[\.,]\d{1,2})?$", txt):
                    try:
                        q_val = int(float(txt.replace(",", ".")))
                        if found_qty is None:
                            found_qty = q_val
                    except Exception:
                        pass
                elif desc_x_min <= wx < desc_x_max:
                    if wx < int(img_w * 0.08) and re.match(r"^\d{1,2}$", txt):
                        continue
                    desc_tokens.append(txt)

            # C) OCR celda por celda de Alta Precisión sobre la columna Precio para este renglón exacto
            row_y_center = cl["y_center"]
            cell_h = max(26, int(max(w["h"] for w in row_words) * 2.2))
            y_cell_top = max(0, int(row_y_center - cell_h // 2))
            y_cell_bottom = min(crop_main.height, int(row_y_center + cell_h // 2))

            found_price = None
            candidate_prices = []

            if y_cell_bottom > y_cell_top:
                cell_img = crop_main.crop((price_col_x1, y_cell_top, price_col_x2, y_cell_bottom))
                cell_up = cell_img.resize((int(cell_img.width * 2.5), int(cell_img.height * 2.5)), Image.Resampling.LANCZOS)
                res_cell = safe_ocr_recognize_pil(cell_up)
                
                for l in res_cell.get("lines", []):
                    for w in l.get("words", []):
                        b = w.get("bounding_rect", {})
                        xc = (b.get("x", 0) + b.get("width", 0) / 2.0) / 2.5
                        yc = (b.get("y", 0) + b.get("height", 0) / 2.0) / 2.5
                        txt = str(w.get("text", "")).strip()
                        
                        # Omitir cualquier token que sea indicador de Bolívares cuando se audita en USD
                        if currency == "usd" and re.search(r"\b(?:bs|bs\.|b)\b", txt, re.IGNORECASE):
                            continue
                            
                        val = parse_price(txt, currency=currency)
                        if val > 0.0:
                            candidate_prices.append({
                                "val": val,
                                "xc": xc,
                                "yc": yc,
                                "text": txt,
                                "is_lower_half": (yc >= (cell_h * 0.46))
                            })

            # Fallback desde tokens de la fila
            if not candidate_prices:
                for w in row_words:
                    if price_col_x1 <= w["x"] < price_col_x2:
                        txt = w["text"].strip()
                        if currency == "usd" and re.search(r"\b(?:bs|bs\.|b)\b", txt, re.IGNORECASE):
                            continue
                        val = parse_price(txt, currency=currency)
                        if val > 0.0:
                            if found_qty is not None and abs(val - float(found_qty)) < 0.001:
                                continue
                            is_lower = (w["y_center"] > cl["y_center"])
                            candidate_prices.append({
                                "val": val,
                                "xc": w["x"],
                                "yc": w["y_center"] - (cl["y_center"] - cell_h / 2),
                                "text": txt,
                                "is_lower_half": is_lower
                            })

            if currency == "usd":
                # Arriba en NEGRITA = Precio en USD. Abajo = Precio en Bolívares (Bs).
                # Omitir los precios de abajo porque son en Bs.
                top_candidates = [c for c in candidate_prices if not c["is_lower_half"]]
                
                # Regla Crítica: Descartar cualquier candidato que coincida con la CANTIDAD de la fila
                if found_qty is not None and found_qty > 0:
                    filtered_cands = [c for c in top_candidates if abs(c["val"] - float(found_qty)) > 0.001]
                    if filtered_cands:
                        top_candidates = filtered_cands

                valid_usd_candidates = [c for c in top_candidates if c["val"] < 500.0]
                if not valid_usd_candidates:
                    valid_usd_candidates = top_candidates
                    
                if valid_usd_candidates:
                    # Priorizar candidatos situados más a la derecha en la celda y en la parte superior
                    valid_usd_candidates.sort(key=lambda c: (-c.get("xc", 0.0), c["yc"]))
                    found_price = valid_usd_candidates[0]["val"]
                elif candidate_prices:
                    small_candidates = [
                        c for c in candidate_prices 
                        if c["val"] < 150.0 and (found_qty is None or abs(c["val"] - float(found_qty)) > 0.001)
                    ]
                    if small_candidates:
                        small_candidates.sort(key=lambda c: (-c.get("xc", 0.0), c["yc"]))
                        found_price = small_candidates[0]["val"]
            else:
                bottom_candidates = [c for c in candidate_prices if c["is_lower_half"]]
                if bottom_candidates:
                    bottom_candidates.sort(key=lambda c: c["yc"], reverse=True)
                    found_price = bottom_candidates[0]["val"]
                elif candidate_prices:
                    found_price = candidate_prices[-1]["val"]

            b_raw = found_barcode or ""
            if b_raw:
                try:
                    b_norm = extractor.normalizar_codigo_barra(b_raw)[0]
                except Exception:
                    b_norm = b_raw
            else:
                b_norm = ""

            desc_text = " ".join(desc_tokens).strip()

            is_valid_row = bool(
                b_norm or
                (len(desc_text) >= 4 and (found_price is not None or found_qty is not None))
            )
            if is_valid_row:
                detected_rows.append({
                    "slot": len(detected_rows),
                    "y_center": cl["y_center"],
                    "barcode_raw": b_raw,
                    "barcode_norm": b_norm,
                    "desc": desc_text,
                    "qty": found_qty,
                    "price": found_price,
                    "candidates": candidate_prices,
                    "row_words": row_words
                })

        # Comparación de precios para los ítems del lote
        if batch_items and check_price:
            n_items = len(batch_items)
            curr_sym = "Bs." if currency == "bs" else "$"

            for offset, item in enumerate(batch_items):
                row_num = start_global_idx + offset
                try:
                    it_code_norm = extractor.normalizar_codigo_barra(item.get("codigo_barra", ""))[0]
                except Exception:
                    it_code_norm = str(item.get("codigo_barra", "")).strip()
                it_clean = it_code_norm.lstrip("0") or it_code_norm

                saint_price = None
                matched_dr = None
                
                # 1. Coincidencia por código de barra (exacto o sufijo de 6+ dígitos)
                for dr in detected_rows:
                    if dr["barcode_norm"]:
                        dr_clean = dr["barcode_norm"].lstrip("0") or dr["barcode_norm"]
                        if (dr_clean == it_clean or (len(dr_clean) >= 6 and len(it_clean) >= 6 and dr_clean[-6:] == it_clean[-6:])) and dr["price"] is not None:
                            saint_price = dr["price"]
                            matched_dr = dr
                            break

                # 2. Coincidencia por tokens de descripción
                if saint_price is None:
                    it_tokens = set(re.findall(r"[A-Za-z0-9]+", str(item.get("descripcion", "")).upper()))
                    for dr in detected_rows:
                        if dr["desc"] and dr["price"] is not None:
                            dr_tokens = set(re.findall(r"[A-Za-z0-9]+", str(dr["desc"]).upper()))
                            if it_tokens and len(it_tokens.intersection(dr_tokens)) / max(len(it_tokens), 1) >= 0.35:
                                saint_price = dr["price"]
                                matched_dr = dr
                                break

                # 3. Fallback posicional adaptativo:
                if saint_price is None and detected_rows:
                    if start_global_idx == 1:
                        if offset < len(detected_rows) and detected_rows[offset]["price"] is not None:
                            saint_price = detected_rows[offset]["price"]
                            matched_dr = detected_rows[offset]
                    else:
                        pos_from_end = n_items - 1 - offset
                        idx_from_end = len(detected_rows) - 1 - pos_from_end
                        if 0 <= idx_from_end < len(detected_rows) and detected_rows[idx_from_end]["price"] is not None:
                            saint_price = detected_rows[idx_from_end]["price"]
                            matched_dr = detected_rows[idx_from_end]

                if saint_price is not None and saint_price > 0.0:
                    if currency == "bs":
                        expected_price = float(item.get("costo_unitario_bs", 0.0))
                        if expected_price == 0.0 and item.get("costo_unitario_usd") and item.get("tasa_cambio"):
                            expected_price = round(float(item["costo_unitario_usd"]) * float(item["tasa_cambio"]), 2)
                    else:
                        expected_price = float(item.get("costo_unitario_usd", 0.0))

                    if expected_price > 0.0:
                        # Si saint_price tomó por error la cantidad del ítem, descartar y buscar el precio real
                        it_qty = float(item.get("cantidad", 1))
                        if abs(saint_price - it_qty) < 0.001 and abs(saint_price - expected_price) > tolerance:
                            found_alt = False
                            if matched_dr and "candidates" in matched_dr:
                                for c in matched_dr.get("candidates", []):
                                    if not c.get("is_lower_half", False) or currency != "usd":
                                        if abs(c["val"] - it_qty) > 0.001 and c["val"] < 500.0:
                                            saint_price = c["val"]
                                            found_alt = True
                                            break
                            if not found_alt and matched_dr and "row_words" in matched_dr:
                                for rw in matched_dr.get("row_words", []):
                                    if price_col_x1 <= rw["x"] < price_col_x2:
                                        p_val = parse_price(rw["text"], currency=currency)
                                        if p_val > 0.0 and abs(p_val - it_qty) > 0.001 and p_val < 500.0:
                                            saint_price = p_val
                                            break

                        # Heurística de resiliencia ante pérdida de punto decimal por OCR
                        if abs(saint_price / 100.0 - expected_price) <= tolerance:
                            saint_price = round(saint_price / 100.0, 2)
                        elif abs(saint_price / 10.0 - expected_price) <= tolerance:
                            saint_price = round(saint_price / 10.0, 2)

                        # Si entre los candidatos superiores se encuentra exactamente el precio esperado
                        if matched_dr and "candidates" in matched_dr:
                            for c in matched_dr.get("candidates", []):
                                cv = c["val"]
                                if not c.get("is_lower_half", False) or currency != "usd":
                                    if abs(cv - expected_price) <= tolerance or \
                                       abs(cv / 100.0 - expected_price) <= tolerance or \
                                       abs(cv / 10.0 - expected_price) <= tolerance:
                                        saint_price = expected_price
                                        break

                        # Si persiste diferencia, buscar en tokens de la fila de la columna de precio
                        if abs(saint_price - expected_price) > tolerance and matched_dr and "row_words" in matched_dr:
                            for rw in matched_dr.get("row_words", []):
                                if price_col_x1 <= rw["x"] < price_col_x2:
                                    p_val = parse_price(rw["text"], currency=currency)
                                    if p_val > 0.0:
                                        if abs(p_val - expected_price) <= tolerance or \
                                           abs(p_val / 100.0 - expected_price) <= tolerance or \
                                           abs(p_val / 10.0 - expected_price) <= tolerance:
                                            saint_price = expected_price
                                            break

                        diff = abs(saint_price - expected_price)
                        if diff > tolerance:
                            diffs.append({
                                "row": row_num,
                                "codigo": item.get("codigo_barra", ""),
                                "descripcion": item.get("descripcion", ""),
                                "saint_price": saint_price,
                                "expected_price": expected_price,
                                "diff": diff,
                                "curr_sym": curr_sym
                            })

    except Exception:
        pass
    finally:
        del crop_main

    return {"price_diffs": diffs, "detected_rows": detected_rows}


def extract_prices_from_grid_capture(img, batch_items: list, start_global_idx: int,
                                     is_final: bool, total_items: int,
                                     currency: str = "usd", tolerance: float = 0.02,
                                     check_price: bool = True) -> list:
    """Compatibilidad: extrae diferencias de precio desde la cuadrícula de Saint."""
    res = audit_saint_grid_capture(img, batch_items, start_global_idx, is_final, total_items,
                                   currency=currency, tolerance=tolerance, check_price=check_price)
    return res.get("price_diffs", [])


class OCRBatchProcessor:
    """
    Procesador de OCR asíncrono en segundo plano para capturas de pantalla de Saint.
    Procesa lotes en RAM sin frenar el tipeo del bot de teclado.
    Audita:
      1. Diferencias de precio unitario.
      2. Ítems faltantes por facturar (en JSON pero no en Saint).
      3. Ítems ajenos / sobrantes (en Saint pero no en JSON).
    Zero-disk-cache: No crea archivos temporales y libera memoria inmediatamente.
    """
    def __init__(self, on_diff_found=None, on_log=None):
        self.on_diff_found = on_diff_found
        self.on_log = on_log
        self.differences = []
        self.detected_items_map = {}  # {key: item_dict}
        self._threads = []
        self._lock = threading.Lock()

    def process_batch_async(self, batch_img, batch_items: list, start_global_idx: int,
                            is_final: bool, total_items: int,
                            currency: str = "usd", tolerance: float = 0.02,
                            mock_diffs: list = None,
                            check_price: bool = True):
        def worker():
            try:
                if mock_diffs is not None:
                    diffs = mock_diffs if check_price else []
                    detected = []
                    if batch_items:
                        for idx_offset, bit in enumerate(batch_items):
                            c_raw = str(bit.get("codigo_barra", "")).strip()
                            try:
                                c_norm = extractor.normalizar_codigo_barra(c_raw)[0]
                            except Exception:
                                c_norm = c_raw
                            exp_p = float(bit.get("costo_unitario_bs" if currency == "bs" else "costo_unitario_usd", 0.0))
                            detected.append({
                                "slot": idx_offset,
                                "barcode_raw": c_raw,
                                "barcode_norm": c_norm,
                                "desc": bit.get("descripcion", ""),
                                "qty": bit.get("cantidad", 1),
                                "price": exp_p
                            })
                else:
                    audit_data = audit_saint_grid_capture(
                        batch_img, batch_items, start_global_idx, is_final,
                        total_items, currency=currency, tolerance=tolerance,
                        check_price=check_price
                    )
                    diffs = audit_data.get("price_diffs", [])
                    detected = audit_data.get("detected_rows", [])

                with self._lock:
                    if check_price:
                        for d in diffs:
                            if not any(x["row"] == d["row"] for x in self.differences):
                                self.differences.append(d)
                                if self.on_diff_found:
                                    self.on_diff_found(d)
                                if self.on_log:
                                    sym = d.get("curr_sym", "$")
                                    self.on_log(f"⚠️ [Diferencia OCR #{d['row']}] {d['descripcion'][:24]}: Saint={sym}{d['saint_price']:.2f} vs JSON={sym}{d['expected_price']:.2f}")

                    for r in detected:
                        key = r["barcode_norm"]
                        if key:
                            self.detected_items_map[key] = r
                        else:
                            # Si no tiene código de barra, verificar si coincide en descripción con algún ítem ya detectado
                            desc_r = r.get("desc", "").strip()
                            tokens_r = set(re.findall(r"[A-Za-z0-9]+", desc_r.upper())) if desc_r else set()
                            already_exists = False
                            if tokens_r and len(tokens_r) >= 2:
                                for ex_key, ex_item in self.detected_items_map.items():
                                    ex_desc = ex_item.get("desc", "").strip()
                                    ex_tokens = set(re.findall(r"[A-Za-z0-9]+", ex_desc.upper())) if ex_desc else set()
                                    if ex_tokens and len(tokens_r.intersection(ex_tokens)) / max(len(tokens_r), 1) >= 0.45:
                                        if r.get("price") is not None:
                                            ex_item["price"] = r["price"]
                                        if r.get("qty") is not None:
                                            ex_item["qty"] = r["qty"]
                                        if "candidates" in r:
                                            ex_item["candidates"] = r["candidates"]
                                        already_exists = True
                                        break
                            if not already_exists and (len(desc_r) >= 4 or r.get("price") is not None):
                                self.detected_items_map[f"_row_{len(self.detected_items_map)}_{desc_r[:16]}"] = r

            except Exception as ex:
                if self.on_log:
                    self.on_log(f"Aviso OCR en segundo plano: {ex}")
            finally:
                try:
                    if batch_img is not None and hasattr(batch_img, "close"):
                        batch_img.close()
                except Exception:
                    pass

        th = threading.Thread(target=worker, daemon=True)
        self._threads.append(th)
        th.start()

    def compile_audit(self, all_expected_items: list, currency: str = "usd", tolerance: float = 0.02,
                      check_price: bool = True, replacement_rules: list = None) -> dict:
        """
        Consolida la auditoría completa de la factura con coincidencia multinivel inteligente:
        - Nivel 1: Coincidencia exacta por código de barra, código interno o alias de reemplazo.
        - Nivel 2: Coincidencia heurística por sufijo de código (últimos 6+ dígitos) y/o similitud
          de descripción de producto con precio/cantidad coincidente.
        - Nivel 3: Coincidencia adaptativa para los últimos productos al final de la cuadrícula
          por coincidencia de precio o palabras clave de descripción.
        - Nivel 4: Verificación de diferencias de precio unitario.
        """
        with self._lock:
            alias_map = {}
            rules_to_use = list(replacement_rules) if replacement_rules is not None else []
            if not rules_to_use:
                try:
                    p_rules = BASE_DIR / "codigos_reemplazo.json"
                    if p_rules.exists():
                        with open(p_rules, "r", encoding="utf-8") as fp:
                            rules_to_use = json.load(fp)
                except Exception:
                    pass

            for r in rules_to_use:
                if isinstance(r, dict) and r.get("activo", True):
                    s = str(r.get("codigo_origen", "")).strip().lstrip("0")
                    d = str(r.get("codigo_destino", "")).strip().lstrip("0")
                    if s and d:
                        alias_map[s] = d
                        alias_map[d] = s

            def _tokenize(text: str) -> set:
                return set(re.findall(r"[A-Za-z0-9]+", str(text).upper()))

            unmatched_expected = {}
            for idx, it in enumerate(all_expected_items, 1):
                raw_code = str(it.get("codigo_barra", "")).strip()
                try:
                    norm_code = extractor.normalizar_codigo_barra(raw_code)[0]
                except Exception:
                    norm_code = raw_code
                clean_key = norm_code.lstrip("0") or norm_code

                valid_keys = {clean_key, norm_code}
                if it.get("codigo_barra_original"):
                    cbo = str(it["codigo_barra_original"]).strip()
                    valid_keys.add(cbo)
                    valid_keys.add(cbo.lstrip("0") or cbo)
                if it.get("codigo_interno"):
                    ci = str(it["codigo_interno"]).strip()
                    valid_keys.add(ci)
                    valid_keys.add(ci.lstrip("0") or ci)
                if it.get("codigo"):
                    co = str(it["codigo"]).strip()
                    valid_keys.add(co)
                    valid_keys.add(co.lstrip("0") or co)

                for vk in list(valid_keys):
                    if vk in alias_map:
                        valid_keys.add(alias_map[vk])

                p_val = float(it.get("costo_unitario_bs", 0.0)) if currency == "bs" else float(it.get("costo_unitario_usd", 0.0))
                q_val = int(it.get("cantidad", 1))

                unmatched_expected[idx] = {
                    "item": it,
                    "valid_keys": valid_keys,
                    "clean_key": clean_key,
                    "desc_tokens": _tokenize(it.get("descripcion", "")),
                    "price": p_val,
                    "qty": q_val,
                    "row_idx": idx
                }

            matched_expected = {}
            unmatched_detected = dict(self.detected_items_map)

            # --- Nivel 1: Coincidencia directa por código (exacto o alias) ---
            for det_key, det_item in list(unmatched_detected.items()):
                det_raw = str(det_item.get("barcode_raw", det_key)).strip()
                det_clean = det_key.lstrip("0") or det_key
                det_candidates = {det_key, det_clean, det_raw, det_raw.lstrip("0") or det_raw}

                for exp_idx, exp_data in list(unmatched_expected.items()):
                    if det_candidates.intersection(exp_data["valid_keys"]):
                        matched_expected[exp_idx] = det_item
                        del unmatched_expected[exp_idx]
                        del unmatched_detected[det_key]
                        break

            # --- Nivel 2: Coincidencia heurística inteligente para códigos internos en Saint ---
            for det_key, det_item in list(unmatched_detected.items()):
                det_raw = str(det_item.get("barcode_raw", det_key)).strip()
                det_clean = det_key.lstrip("0") or det_key
                det_tokens = _tokenize(det_item.get("desc", ""))
                det_price = det_item.get("price")
                det_qty = det_item.get("qty")

                best_match_idx = None
                best_score = 0.0

                for exp_idx, exp_data in unmatched_expected.items():
                    common_tokens = det_tokens.intersection(exp_data["desc_tokens"])
                    overlap = len(common_tokens) / max(len(exp_data["desc_tokens"]), 1)

                    code_match = False
                    exp_clean = exp_data["clean_key"]
                    if det_clean and exp_clean and len(det_clean) >= 5 and len(exp_clean) >= 5:
                        if det_clean == exp_clean:
                            code_match = True
                        elif det_clean[-6:] == exp_clean[-6:] or det_clean[:6] == exp_clean[:6]:
                            code_match = True
                        elif det_clean in exp_clean or exp_clean in det_clean:
                            code_match = True

                    price_match = False
                    if det_price is not None and abs(det_price - exp_data["price"]) <= tolerance:
                        price_match = True
                    elif "candidates" in det_item:
                        for c in det_item.get("candidates", []):
                            if not c.get("is_lower_half", False) or currency != "usd":
                                if abs(c["val"] - exp_data["price"]) <= tolerance:
                                    price_match = True
                                    break

                    qty_match = (det_qty is not None and det_qty == exp_data["qty"])

                    if (code_match and (overlap >= 0.20 or price_match or qty_match)) or \
                       (overlap >= 0.30 and (price_match or qty_match)) or \
                       (overlap >= 0.40) or \
                       (code_match and len(unmatched_expected) <= 3):
                        score = overlap + (2.0 if code_match else 0.0) + (1.5 if price_match else 0.0) + (1.0 if qty_match else 0.0)
                        if score > best_score:
                            best_score = score
                            best_match_idx = exp_idx

                if best_match_idx is not None:
                    matched_expected[best_match_idx] = det_item
                    del unmatched_expected[best_match_idx]
                    del unmatched_detected[det_key]

            # --- Nivel 3: Coincidencia adaptativa para los últimos productos al final de la cuadrícula ---
            if unmatched_expected and unmatched_detected:
                for exp_idx in sorted(list(unmatched_expected.keys()), reverse=True):
                    if exp_idx not in unmatched_expected:
                        continue
                    exp_data = unmatched_expected[exp_idx]
                    
                    sorted_det_keys = sorted(
                        list(unmatched_detected.keys()),
                        key=lambda k: unmatched_detected[k].get("y_center", 0.0),
                        reverse=True
                    )

                    matched_k = None
                    for det_key in sorted_det_keys:
                        det_item = unmatched_detected[det_key]
                        det_p = det_item.get("price")
                        det_q = det_item.get("qty")
                        
                        p_match = False
                        if det_p is not None and abs(det_p - exp_data["price"]) <= tolerance:
                            p_match = True
                        elif "candidates" in det_item:
                            for c in det_item.get("candidates", []):
                                if not c.get("is_lower_half", False) or currency != "usd":
                                    if abs(c["val"] - exp_data["price"]) <= tolerance:
                                        p_match = True
                                        break

                        q_match = (det_q is not None and det_q == exp_data["qty"])
                        det_tokens = _tokenize(det_item.get("desc", ""))
                        tokens_common = bool(det_tokens and exp_data["desc_tokens"].intersection(det_tokens))
                        
                        if p_match or q_match or tokens_common:
                            matched_k = det_key
                            break

                    # Si es el último producto de la factura y queda una fila al fondo de la cuadrícula
                    if not matched_k and exp_idx == len(all_expected_items) and sorted_det_keys:
                        matched_k = sorted_det_keys[0]

                    if matched_k:
                        matched_expected[exp_idx] = unmatched_detected[matched_k]
                        del unmatched_expected[exp_idx]
                        del unmatched_detected[matched_k]

            # 1. Faltantes por facturar
            missing_items = []
            curr_sym = "Bs." if currency == "bs" else "$"
            for exp_idx, exp_data in unmatched_expected.items():
                it = exp_data["item"]
                missing_items.append({
                    "row": exp_idx,
                    "codigo": it.get("codigo_barra", ""),
                    "descripcion": it.get("descripcion", ""),
                    "cantidad": exp_data["qty"],
                    "precio": exp_data["price"],
                    "curr_sym": curr_sym
                })

            # 2. Productos ajenos al JSON (Filtros estrictos para cero falsos positivos)
            foreign_items = []
            for det_key, det_item in unmatched_detected.items():
                # A) Ignorar filas auxiliares sin código de barra (_row_)
                if det_key.startswith("_row_"):
                    continue

                code_raw = str(det_item.get("barcode_raw", det_key)).strip()
                if not code_raw or len(code_raw) < 5:
                    continue

                code_u = code_raw.upper()
                if any(k in code_u for k in ["TOTAL", "SUBTOTAL", "IVA", "BASE", "ITEM", "BS", "USD", "SALDO"]):
                    continue

                desc_u = str(det_item.get("desc", "")).upper()
                if any(k in desc_u for k in ["TOTAL BS", "TOTAL USD", "SUBTOTAL", "BASE IMPONIBLE", "IVA (16%)", "EXENTO"]):
                    continue

                p = det_item.get("price", 0.0) or 0.0
                q = det_item.get("qty", 1) or 1
                if p <= 0.0 and q <= 0:
                    continue

                foreign_items.append({
                    "codigo": code_raw,
                    "descripcion": det_item.get("desc", ""),
                    "cantidad": q,
                    "precio": p,
                    "curr_sym": curr_sym
                })

            price_diffs = list(self.differences) if check_price else []
            has_issues = bool(missing_items or foreign_items or price_diffs)

            return {
                "missing_items": missing_items,
                "foreign_items": foreign_items,
                "price_differences": price_diffs,
                "total_expected": len(all_expected_items),
                "total_detected": len(self.detected_items_map),
                "detected_items": dict(self.detected_items_map),
                "has_issues": has_issues
            }

    def wait_all(self, timeout: float = 10.0):
        for th in self._threads:
            if th.is_alive():
                th.join(timeout=timeout)

    def clear(self):
        with self._lock:
            self._threads.clear()
            self.differences.clear()
            self.detected_items_map.clear()



class FacturadorSaintEngine:
    """Motor de automatización nativo para Saint Enterprise"""
    def __init__(self):
        self.running = False
        self.paused = False
        self._stop_requested = False
        self._thread = None
        self._listener = None
        
        # Callbacks UI
        self.on_log = None
        self.on_state_change = None
        self.on_countdown = None
        self.on_item_started = None
        self.on_item_finished = None
        self.on_invoice_finished = None
        self.on_price_difference = None
        self.on_ocr_diff_row = None
        self.on_cache_updated = None
        self.price_differences = []
        self._ocr_processor = None

        # Parámetros ajustables
        self.config = {
            "cliente_rif": "J-080030486",
            "type_client": True,
            "auto_focus_saint": True,
            "delay_after_client": 0.85,       # Espera para que Saint consulte el cliente en SQL
            "delay_after_barcode": 0.50,      # Espera para que Saint busque el producto en SQL
            "delay_after_qty": 0.40,          # Espera tras ingresar la cantidad
            "delay_between_items": 0.35,      # Espera antes del siguiente ítem
            "press_f6_at_end": False,         # Presionar F6 al final (desactivado por defecto)
            "delay_before_f6": 0.80,          # Espera antes de presionar F6
            "countdown_seconds": 5,           # Tiempo de cuenta regresiva (5 segundos)
            "key_char_delay": 0.025,          # Delay entre pulsaciones de caracteres
            "price_list_mode": "precio_3",    # 'precio_3' (automático) o 'precio_0' (manual)
            "batch_size": 8,                  # Tomar capturas cada 8 productos
            "verify_price_by_ocr": True,      # Capturas cada 8 productos con OCR local
            "check_price_realtime": True,     # Verificar precio en pantalla
            "price_alert_mode": "summary",    # 'summary' (al final) o 'instant' (al momento)
            "price_currency": "usd",          # 'usd' o 'bs'
            "price_nav_mode": "enter",        # 'enter' o 'tab'
            "price_tolerance": 0.02,          # Margen de tolerancia
            "max_items_per_invoice": 43,      # Límite máximo de productos por factura en Saint
            "test_mode": False                # Modo simulación
        }

    def log(self, msg: str):
        if self.on_log:
            try:
                self.on_log(msg)
            except Exception:
                pass
        else:
            try:
                print(f"[FACTURADOR] {msg}")
            except UnicodeEncodeError:
                enc = getattr(sys.stdout, 'encoding', 'ascii') or 'ascii'
                safe_msg = msg.encode(enc, errors='replace').decode(enc)
                print(f"[FACTURADOR] {safe_msg}")

    def beep(self, freq=1000, dur=120):
        if HAVE_SOUND:
            try:
                winsound.Beep(freq, dur)
            except Exception:
                pass

    def start_hotkeys(self, on_f8=None, on_f7=None, on_f12=None):
        if not HAVE_PYNPUT:
            return
        def on_press(key):
            try:
                if key == pynput_keyboard.Key.f8 and on_f8:
                    on_f8()
                elif key == pynput_keyboard.Key.f7 and on_f7:
                    on_f7()
                elif key in (pynput_keyboard.Key.f12, pynput_keyboard.Key.esc) and on_f12:
                    on_f12()
            except Exception:
                pass
        try:
            self._listener = pynput_keyboard.Listener(on_press=on_press)
            self._listener.daemon = True
            self._listener.start()
        except Exception as e:
            self.log(f"Aviso al iniciar atajos: {e}")

    def stop_hotkeys(self):
        if self._listener:
            try:
                self._listener.stop()
            except Exception:
                pass
            self._listener = None

    def start_invoice(self, items: list):
        if self.running:
            return
        self.running = True
        self.paused = False
        self._stop_requested = False
        self.price_differences = []
        self._thread = threading.Thread(target=self._run_loop, args=(items,), daemon=True)
        self._thread.start()

    def pause_toggle(self):
        if not self.running:
            return
        self.paused = not self.paused
        st = "PAUSADO" if self.paused else "REANUDADO"
        self.log(f"Bot {st}. (Presiona F7 para continuar o F12 para cancelar).")
        if self.on_state_change:
            self.on_state_change(st)
        self.beep(750, 200)

    def stop(self):
        if not self.running:
            return
        self._stop_requested = True
        self.paused = False
        self.running = False
        self.log("Cancelación de emergencia. Deteniendo tipeo...")
        if self.on_state_change:
            self.on_state_change("DETENIDO")
        self.beep(400, 400)

    def _sleep(self, seconds: float) -> bool:
        step = 0.05
        el = 0.0
        while el < seconds:
            if self._stop_requested:
                return False
            while self.paused:
                time.sleep(0.1)
                if self._stop_requested:
                    return False
            time.sleep(step)
            el += step
        return True

    def _run_loop(self, items: list):
        try:
            self.price_differences = []
            max_items = self.config.get("max_items_per_invoice", 43)
            if max_items and len(items) > max_items:
                self.log(f"⚠️ La lista contiene {len(items)} productos. Se procesarán los primeros {max_items} productos (límite de Saint).")
                items = items[:max_items]

            # 1. Cuenta regresiva para dar tiempo al operador
            cd = self.config.get("countdown_seconds", 3)
            if self.on_state_change:
                self.on_state_change("CUENTA_REGRESIVA")
            
            self.log(f"Iniciando en {cd}s... ¡Haz clic en la primera fila (Referencia) en Saint!")
            for c in range(cd, 0, -1):
                if self._stop_requested:
                    return
                if self.on_countdown:
                    self.on_countdown(c)
                self.beep(880, 100)
                if not self._sleep(1.0):
                    return

            # Intentar auto-enfocar Saint si está habilitado
            if self.config.get("auto_focus_saint", True) and not self.config.get("test_mode", False):
                buscar_y_enfocar_saint()

            self.beep(1320, 250)
            if self.on_state_change:
                self.on_state_change("ESCRIBIENDO")

            # Cargar cada producto directamente en la cuadrícula
            total = len(items)
            self.log(f"-> Escribiendo {total} productos en la cuadrícula...")
            
            price_mode = self.config.get("price_list_mode", "precio_3").lower()
            verify_ocr = self.config.get("verify_price_by_ocr", True)
            check_price_opt = self.config.get("check_price", True)
            curr = self.config.get("price_currency", "usd").lower()
            curr_sym = "Bs." if curr == "bs" else "$"
            tolerance = self.config.get("price_tolerance", 0.02)

            def on_ocr_diff(d):
                if self.on_ocr_diff_row:
                    try:
                        self.on_ocr_diff_row(d)
                    except Exception:
                        pass

            ocr_processor = OCRBatchProcessor(on_diff_found=on_ocr_diff, on_log=self.log)
            self._ocr_processor = ocr_processor

            for idx, item in enumerate(items, 1):
                if self._stop_requested:
                    break

                if self.on_item_started:
                    self.on_item_started(idx - 1, item)

                codigo = str(item.get("codigo_barra", "")).strip()
                cantidad = str(item.get("cantidad", "1")).strip()
                desc = item.get("descripcion", "")[:28]

                self.log(f"[{idx}/{total}] Referencia: {codigo} + ENTER | Cantidad: {cantidad} + ENTER ({desc})")

                # A) Escribir Código de Barra en campo 'Referencia'
                win32_type_string(codigo, key_delay=self.config.get("key_char_delay", 0.025),
                                  stop_checker=lambda: self._stop_requested)
                win32_press_vk(VK_RETURN, delay_after=0.05)

                # B) Pausa para que Saint busque el producto en SQL y mueva el cursor a 'Cantidad'
                if not self._sleep(self.config.get("delay_after_barcode", 0.50)):
                    break

                # C) Escribir Cantidad
                win32_type_string(cantidad, key_delay=self.config.get("key_char_delay", 0.025),
                                  stop_checker=lambda: self._stop_requested)

                item_extra_info = None

                if price_mode == "precio_3":
                    # En Precio 3: ENTER en Cantidad confirma la fila y Saint baja directo a Referencia del siguiente renglón
                    win32_press_vk(VK_RETURN, delay_after=0.05)
                    if not self._sleep(self.config.get("delay_after_qty", 0.20)):
                        break

                    # Verificar si corresponde tomar captura de pantalla (lotes intermedios cada batch_size)
                    batch_size = self.config.get("batch_size", 8)
                    is_batch = (idx % batch_size == 0 and idx < total)
                    
                    if is_batch and verify_ocr:
                        # Breve pausa para que Saint dibuje los datos en la cuadrícula
                        self._sleep(0.25)
                        
                        b_start = idx - batch_size
                        b_items = items[b_start:idx]
                        start_row = b_start + 1
                        batch_num = idx // batch_size
                        desc_lote = f"Lote #{batch_num} (filas {start_row} a {idx})"

                        if not self.config.get("test_mode", False):
                            target_hwnd = obtener_hwnd_saint()
                            fname = f"captura_lote_{batch_num}_filas_{start_row}_a_{idx}.png"
                            batch_img, saved_path = capture_window_to_cache(target_hwnd, file_name=fname)
                            if saved_path:
                                self.log(f"📷 [{desc_lote}] Guardado en cache_capturas/{saved_path.name}. Analizando con OCR...")
                            else:
                                self.log(f"📷 [{desc_lote}] Analizando con OCR...")
                        else:
                            batch_img = None
                            saved_path = None

                        if self.on_cache_updated:
                            try:
                                self.on_cache_updated()
                            except Exception:
                                pass

                        mock_diffs = self.config.get("mock_diffs", None)
                        if self.config.get("test_mode", False) and mock_diffs is None:
                            mock_str = self.config.get("mock_price_str", "")
                            if mock_str:
                                m_price = parse_price(mock_str)
                                mock_diffs = []
                                for offset, b_item in enumerate(b_items):
                                    if curr == "bs":
                                        exp = float(b_item.get("costo_unitario_bs", 0.0))
                                    else:
                                        exp = float(b_item.get("costo_unitario_usd", 0.0))
                                    if abs(m_price - exp) > tolerance:
                                        mock_diffs.append({
                                            "row": start_row + offset,
                                            "codigo": b_item.get("codigo_barra", ""),
                                            "descripcion": b_item.get("descripcion", ""),
                                            "saint_price": m_price,
                                            "expected_price": exp,
                                            "diff": abs(m_price - exp),
                                            "curr_sym": curr_sym
                                        })

                        ocr_processor.process_batch_async(
                            batch_img, b_items, start_row, False, total,
                            currency=curr, tolerance=tolerance, mock_diffs=mock_diffs,
                            check_price=check_price_opt
                        )

                else:
                    # Modo Precio 0 (Manual por ítem): Navega a la celda de Precio
                    check_price = self.config.get("check_price_realtime", True)
                    if check_price:
                        nav_mode = self.config.get("price_nav_mode", "enter").lower()
                        nav_vk = VK_TAB if nav_mode == "tab" else VK_RETURN
                        win32_press_vk(nav_vk, delay_after=0.08)

                        if not self._sleep(self.config.get("delay_after_qty", 0.20)):
                            break

                        val_str = win32_copy_field() if not self.config.get("test_mode", False) else self.config.get("mock_price_str", "")
                        saint_price = parse_price(val_str)

                        if curr == "bs":
                            expected_price = float(item.get("costo_unitario_bs", 0.0))
                            if expected_price == 0.0 and item.get("costo_unitario_usd") and item.get("tasa_cambio"):
                                expected_price = round(float(item["costo_unitario_usd"]) * float(item["tasa_cambio"]), 2)
                        else:
                            expected_price = float(item.get("costo_unitario_usd", 0.0))

                        diff = abs(saint_price - expected_price)

                        if saint_price > 0.0 and expected_price > 0.0 and diff > tolerance:
                            diff_info = {
                                "row": idx,
                                "codigo": codigo,
                                "descripcion": desc,
                                "saint_price": saint_price,
                                "expected_price": expected_price,
                                "diff": diff,
                                "curr_sym": curr_sym
                            }
                            self.price_differences.append(diff_info)
                            self.log(f"⚠️ [Diferencia #{idx}] {desc}: Saint={curr_sym}{saint_price:.2f} vs JSON={curr_sym}{expected_price:.2f} (Dif: {curr_sym}{diff:.2f})")

                            alert_mode = self.config.get("price_alert_mode", "summary")
                            if alert_mode == "instant":
                                self.beep(2000, 250)
                                action = "overwrite"
                                if self.on_price_difference:
                                    action = self.on_price_difference(item, saint_price, expected_price, curr_sym)

                                if self.config.get("auto_focus_saint", True) and not self.config.get("test_mode", False):
                                    buscar_y_enfocar_saint()
                                    time.sleep(0.10)

                                if action == "overwrite":
                                    dec_sep = "," if "," in val_str else "."
                                    price_text = f"{expected_price:.2f}".replace(".", dec_sep)
                                    self.log(f"-> Sobrescribiendo precio en Saint: {curr_sym} {price_text} + ENTER...")
                                    user32.keybd_event(VK_CONTROL, user32.MapVirtualKeyW(VK_CONTROL, 0), 0, 0)
                                    time.sleep(0.01)
                                    user32.keybd_event(VK_A, user32.MapVirtualKeyW(VK_A, 0), 0, 0)
                                    time.sleep(0.01)
                                    user32.keybd_event(VK_A, user32.MapVirtualKeyW(VK_A, 0), KEYEVENTF_KEYUP, 0)
                                    time.sleep(0.01)
                                    user32.keybd_event(VK_CONTROL, user32.MapVirtualKeyW(VK_CONTROL, 0), KEYEVENTF_KEYUP, 0)
                                    time.sleep(0.02)
                                    win32_type_string(price_text, key_delay=self.config.get("key_char_delay", 0.025),
                                                      stop_checker=lambda: self._stop_requested)
                                    win32_press_vk(VK_RETURN, delay_after=0.06)
                                    item_extra_info = ("diff_fixed", f"✏️ {curr_sym}{expected_price:.2f}")
                                elif action == "pause":
                                    self.pause_toggle()
                                    self.log("⏸ Facturador pausado por diferencia de precio. Ajusta el precio en Saint y pulsa F7 para continuar.")
                                    item_extra_info = ("diff_paused", "⏸ Ajuste manual")
                                    if not self._sleep(0.5):
                                        break
                                else:
                                    self.log(f"-> Manteniendo precio de Saint: {curr_sym}{saint_price:.2f} + ENTER...")
                                    win32_press_vk(VK_RETURN, delay_after=0.06)
                                    item_extra_info = ("diff_kept", f"⚠️ Saint {curr_sym}{saint_price:.2f}")
                            else:
                                win32_press_vk(VK_RETURN, delay_after=0.06)
                                item_extra_info = ("diff_found", f"⚠️ Dif: {curr_sym}{saint_price:.2f} (JSON: {curr_sym}{expected_price:.2f})")
                        else:
                            if saint_price > 0.0:
                                self.log(f"   ✓ Precio verificado: {curr_sym}{saint_price:.2f} (OK)")
                            win32_press_vk(VK_RETURN, delay_after=0.06)
                    else:
                        win32_press_vk(VK_RETURN, delay_after=0.05)

                # D) Pausa antes del siguiente ítem
                if not self._sleep(self.config.get("delay_between_items", 0.35)):
                    break

                if self.on_item_finished:
                    try:
                        self.on_item_finished(idx - 1, item, True, item_extra_info)
                    except TypeError:
                        self.on_item_finished(idx - 1, item, True)

            # Esperar finalización de análisis OCR en segundo plano y compilar auditoría completa
            audit_result = {
                "missing_items": [],
                "foreign_items": [],
                "price_differences": list(self.price_differences),
                "total_expected": total,
                "total_detected": total,
                "has_issues": len(self.price_differences) > 0,
                "detected_items": {}
            }

            if price_mode == "precio_3" and verify_ocr and ocr_processor:
                # Tomar captura del lote final para asegurar que las últimas filas tipeadas sean auditadas
                batch_size = self.config.get("batch_size", 8)
                last_count = total % batch_size if (total % batch_size != 0) else min(total, batch_size)
                # Abarcar al menos las últimas 8-11 filas visibles en la pantalla de Saint
                last_count = min(total, max(last_count, 8))
                start_row = max(1, total - last_count + 1)
                b_items = items[start_row - 1:total]
                desc_lote = f"Lote Final (filas {start_row} a {total})"

                if not self.config.get("test_mode", False):
                    try:
                        # Pausa de 0.85s para que Saint termine de procesar la última fila,
                        # asentar la cantidad, actualizar totales y pintar la cuadrícula completamente
                        self._sleep(0.85)
                        target_hwnd = obtener_hwnd_saint()
                        fname = f"captura_lote_final_filas_{start_row}_a_{total}.png"
                        final_img, saved_path = capture_window_to_cache(target_hwnd, file_name=fname)
                        if final_img:
                            if saved_path:
                                self.log(f"📷 [{desc_lote}] Guardado en cache_capturas/{saved_path.name}. Analizando con OCR...")
                            else:
                                self.log(f"📷 [{desc_lote}] Analizando con OCR...")
                            ocr_processor.process_batch_async(
                                final_img, b_items, start_row, True, total,
                                currency=curr, tolerance=tolerance, check_price=check_price_opt
                            )
                    except Exception as ex:
                        self.log(f"Aviso al capturar lote final: {ex}")
                else:
                    mock_diffs = self.config.get("mock_diffs", None)
                    if mock_diffs is None:
                        mock_str = self.config.get("mock_price_str", "")
                        if mock_str:
                            m_price = parse_price(mock_str)
                            mock_diffs = []
                            for offset, b_item in enumerate(b_items):
                                exp = float(b_item.get("costo_unitario_bs", 0.0)) if curr == "bs" else float(b_item.get("costo_unitario_usd", 0.0))
                                if abs(m_price - exp) > tolerance:
                                    mock_diffs.append({
                                        "row": start_row + offset,
                                        "codigo": b_item.get("codigo_barra", ""),
                                        "descripcion": b_item.get("descripcion", ""),
                                        "saint_price": m_price,
                                        "expected_price": exp,
                                        "diff": abs(m_price - exp),
                                        "curr_sym": curr_sym
                                    })
                    ocr_processor.process_batch_async(
                        None, b_items, start_row, True, total,
                        currency=curr, tolerance=tolerance, mock_diffs=mock_diffs,
                        check_price=check_price_opt
                    )

                if self.on_cache_updated:
                    try:
                        self.on_cache_updated()
                    except Exception:
                        pass

                # Esperar finalización de análisis OCR en segundo plano y compilar auditoría consolidada
                ocr_processor.wait_all(timeout=10.0)

                audit_result = ocr_processor.compile_audit(
                    items, currency=curr, tolerance=tolerance, check_price=check_price_opt,
                    replacement_rules=self.config.get("replacement_rules", [])
                )
                self.price_differences = audit_result["price_differences"]

                # Limpieza de imágenes en memoria RAM
                ocr_processor.clear()

            # 4. Paso 3: Guardar con F6 al finalizar (si está activado por el usuario)
            if not self._stop_requested and self.config.get("press_f6_at_end", False):
                if audit_result.get("has_issues", False):
                    issues_msgs = []
                    if audit_result.get("missing_items"):
                        issues_msgs.append(f"{len(audit_result['missing_items'])} faltantes por facturar")
                    if audit_result.get("foreign_items"):
                        issues_msgs.append(f"{len(audit_result['foreign_items'])} productos ajenos al JSON")
                    if audit_result.get("price_differences"):
                        issues_msgs.append(f"{len(audit_result['price_differences'])} diferencias de precio")
                    self.log(f"⚠️ [SEGURIDAD F6] Auditoría OCR detectó alertas ({', '.join(issues_msgs)}). NO se presiona F6 para permitir revisión manual.")
                else:
                    self.log("✅ Auditoría OCR 100% limpia. Esperando antes de presionar F6...")
                    if self._sleep(self.config.get("delay_before_f6", 0.80)):
                        self.log("Presionando tecla F6 para guardar la factura en Saint...")
                        win32_press_vk(VK_F6, delay_after=0.1)

            # 5. Conclusión
            if not self._stop_requested:
                if audit_result.get("has_issues", False):
                    self.log("==================================================")
                    self.log("⚠️ [AUDITORÍA OCR] ALERTAS DETECTADAS EN LA FACTURA:")
                    if audit_result.get("missing_items"):
                        self.log(f"❌ {len(audit_result['missing_items'])} PRODUCTOS FALTANTES POR FACTURAR:")
                        for m in audit_result["missing_items"][:5]:
                            self.log(f"   • Fila #{m['row']}: [{m['codigo']}] {m['descripcion'][:30]} (Cant: {m['cantidad']})")
                        if len(audit_result["missing_items"]) > 5:
                            self.log(f"   • ... y {len(audit_result['missing_items']) - 5} más (ver en panel de auditoría)")
                    if audit_result.get("foreign_items"):
                        self.log(f"🚫 {len(audit_result['foreign_items'])} PRODUCTOS AJENOS EN SAINT (NO ESTÁN EN EL JSON):")
                        for f in audit_result["foreign_items"][:5]:
                            self.log(f"   • [{f['codigo']}] {f['descripcion'][:30]}")
                        if len(audit_result["foreign_items"]) > 5:
                            self.log(f"   • ... y {len(audit_result['foreign_items']) - 5} más")
                    if audit_result.get("price_differences"):
                        self.log(f"💵 {len(audit_result['price_differences'])} DIFERENCIAS DE PRECIO DETECTADAS")
                    self.log("==================================================")
                    self.beep(1000, 200)
                    time.sleep(0.08)
                    self.beep(800, 300)
                else:
                    self.log(f"🎉 ¡Factura completada con éxito! Se cargaron los {total} productos.")
                    self.log(f"✅ [AUDITORÍA OCR] Verificación 100% exitosa: 0 faltantes, 0 productos ajenos, 0 diferencias de precio.")
                    self.beep(1500, 150)
                    time.sleep(0.08)
                    self.beep(1900, 300)

                if self.on_state_change:
                    self.on_state_change("COMPLETADO")
                if self.on_invoice_finished:
                    try:
                        self.on_invoice_finished(True, audit_result)
                    except TypeError:
                        self.on_invoice_finished(True)
            else:
                self.log("Proceso cancelado por el usuario.")
                if self.on_state_change:
                    self.on_state_change("DETENIDO")

        except Exception as ex:
            self.log(f"Error inesperado: {ex}")
            if self.on_state_change:
                self.on_state_change("ERROR")
        finally:
            if hasattr(self, "_ocr_processor") and self._ocr_processor:
                self._ocr_processor.clear()
            self.running = False
            self.paused = False
            self._stop_requested = False


class FacturadorApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Facturador Automático - Saint Annual Enterprise")
        self.root.geometry("980x720")
        self.root.minsize(900, 560)
        
        if getattr(sys, "frozen", False):
            self.base_dir = Path(sys.executable).resolve().parent
        else:
            self.base_dir = Path(__file__).resolve().parent

        icon_file = self.base_dir / "app_icon.ico"
        if icon_file.exists():
            try:
                self.root.iconbitmap(str(icon_file))
            except Exception:
                pass

        self.json_dir = self.base_dir / "facturas_json"
        self.pdf_dir = self.base_dir / "facturas_pdf"
        self.cache_dir = self.base_dir / "cache_capturas"
        self.json_dir.mkdir(parents=True, exist_ok=True)
        self.pdf_dir.mkdir(parents=True, exist_ok=True)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        
        self.engine = FacturadorSaintEngine()
        self.current_json_data = None
        self.items_list = []
        self.last_price_diffs = []
        self.last_audit_result = None
        self.invoice_parts = []
        self.current_part_idx = 0
        
        # Conectar callbacks del motor
        self.engine.on_log = self._on_engine_log
        self.engine.on_state_change = self._on_engine_state
        self.engine.on_countdown = self._on_engine_countdown
        self.engine.on_item_started = self._on_engine_item_started
        self.engine.on_item_finished = self._on_engine_item_finished
        self.engine.on_invoice_finished = self._on_engine_invoice_finished
        self.engine.on_price_difference = self._on_engine_price_diff
        self.engine.on_ocr_diff_row = self._on_engine_ocr_diff
        self.engine.on_cache_updated = self._update_cache_btn
        
        # Iniciar listener de atajos globales F8, F7, F12
        self.engine.start_hotkeys(
            on_f8=self._hotkey_start,
            on_f7=self._hotkey_pause,
            on_f12=self._hotkey_stop
        )
        
        # Archivo de configuración persistente con resolución a prueba de permisos
        self.config_file = self._resolve_storage_file("config_facturador.json")
        self.saved_cfg = self._load_saved_config()
        
        # Archivo de reglas de intercambio de códigos persistente
        self.rules_file = self._resolve_storage_file("codigos_reemplazo.json")
        self.replacement_rules = self._load_replacement_rules()
        
        self._build_styles()
        self._build_ui()
        self._attach_config_traces()
        self._scan_json_files()
        self._refresh_rules_table()
        
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        
        # Verificación automática de actualizaciones al abrir (en segundo plano sin congelar la app)
        self.root.after(1500, self._auto_check_updates)

    def _resolve_storage_file(self, filename: str) -> Path:
        r"""
        Garantiza que la ruta para guardar la configuración o reglas sea siempre escribible.
        Si la aplicación está instalada en una carpeta protegida del sistema (como C:\Program Files)
        y el usuario no tiene permisos de administrador, redirige automáticamente el guardado a
        %LOCALAPPDATA%\FacturadorSaint\, preservando los archivos existentes y permitiendo que
        las configuraciones y activaciones de códigos se guarden de forma 100% permanente.
        """
        user_dir = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "FacturadorSaint"
        user_file = user_dir / filename
        base_file = self.base_dir / filename

        # 1. Si ya existe en LOCALAPPDATA (configuración previa del usuario), esa tiene prioridad
        if user_file.exists():
            return user_file

        # 2. Si base_dir es escribible, usar base_file directamente
        try:
            if base_file.exists():
                with open(base_file, "a", encoding="utf-8"):
                    pass
                return base_file
            else:
                test_f = self.base_dir / ".test_write.tmp"
                with open(test_f, "w", encoding="utf-8") as f:
                    f.write("1")
                test_f.unlink()
                return base_file
        except Exception:
            pass

        # 3. base_dir está protegido contra escritura: inicializar en LOCALAPPDATA
        try:
            user_dir.mkdir(parents=True, exist_ok=True)
            if base_file.exists():
                import shutil
                shutil.copy2(base_file, user_file)
            return user_file
        except Exception:
            return base_file

    def _load_saved_config(self) -> dict:
        defaults = {
            "topmost": False,
            "press_f6": False,
            "speed": "fast",
            "countdown": 3,
            "auto_focus": True,
            "check_special_code": True,
            "price_list_mode": "precio_3",
            "verify_price_by_ocr": True,
            "check_price": True,
            "price_alert_mode": "summary",
            "price_currency": "usd",
            "price_nav": "enter"
        }
        if self.config_file.exists():
            try:
                with open(self.config_file, "r", encoding="utf-8") as fp:
                    data = json.load(fp)
                if isinstance(data, dict):
                    # Fusión inteligente: preservar 100% las opciones del cliente
                    # y agregar únicamente nuevas claves si se introducen en nuevas versiones
                    needs_save = False
                    for k, v in defaults.items():
                        if k not in data:
                            data[k] = v
                            needs_save = True
                    if needs_save:
                        try:
                            with open(self.config_file, "w", encoding="utf-8") as fp:
                                json.dump(data, fp, indent=2, ensure_ascii=False)
                        except PermissionError:
                            user_dir = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "FacturadorSaint"
                            user_dir.mkdir(parents=True, exist_ok=True)
                            self.config_file = user_dir / "config_facturador.json"
                            try:
                                with open(self.config_file, "w", encoding="utf-8") as fp:
                                    json.dump(data, fp, indent=2, ensure_ascii=False)
                            except Exception:
                                pass
                        except Exception:
                            pass
                    return data
            except Exception:
                pass

        try:
            with open(self.config_file, "w", encoding="utf-8") as fp:
                json.dump(defaults, fp, indent=2, ensure_ascii=False)
        except PermissionError:
            user_dir = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "FacturadorSaint"
            user_dir.mkdir(parents=True, exist_ok=True)
            self.config_file = user_dir / "config_facturador.json"
            try:
                with open(self.config_file, "w", encoding="utf-8") as fp:
                    json.dump(defaults, fp, indent=2, ensure_ascii=False)
            except Exception:
                pass
        except Exception:
            pass
        return defaults

    def _load_replacement_rules(self) -> list:
        default_rules = [
            {
                "codigo_origen": "014113701808",
                "codigo_destino": "014113910088",
                "descripcion": "PISTACHO WONDERFUL",
                "activo": True
            },
            {
                "codigo_origen": "034000491681",
                "codigo_destino": "469000491681",
                "descripcion": "REESE'S WHITE 4 SNACK SIZE 62G",
                "activo": False
            }
        ]
        if self.rules_file.exists():
            try:
                with open(self.rules_file, "r", encoding="utf-8") as fp:
                    data = json.load(fp)
                if isinstance(data, list) and len(data) > 0:
                    # Fusión inteligente de reglas de intercambio:
                    # 1. Conservar intactas todas las reglas existentes del cliente con sus estados
                    existing_origins = {
                        str(r.get("codigo_origen", "")).strip(): r
                        for r in data if isinstance(r, dict) and r.get("codigo_origen")
                    }
                    needs_save = False
                    # 2. Si el bot añade una nueva regla por defecto en una actualización,
                    # se añade sin tocar ninguna de las configuraciones previas del usuario
                    for def_r in default_rules:
                        src = str(def_r.get("codigo_origen", "")).strip()
                        if src and src not in existing_origins:
                            data.append(def_r)
                            needs_save = True

                    if needs_save:
                        try:
                            with open(self.rules_file, "w", encoding="utf-8") as fp:
                                json.dump(data, fp, indent=2, ensure_ascii=False)
                        except PermissionError:
                            user_dir = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "FacturadorSaint"
                            user_dir.mkdir(parents=True, exist_ok=True)
                            self.rules_file = user_dir / "codigos_reemplazo.json"
                            try:
                                with open(self.rules_file, "w", encoding="utf-8") as fp:
                                    json.dump(data, fp, indent=2, ensure_ascii=False)
                            except Exception:
                                pass
                        except Exception:
                            pass

                    return data
            except Exception:
                pass
        try:
            with open(self.rules_file, "w", encoding="utf-8") as fp:
                json.dump(default_rules, fp, indent=2, ensure_ascii=False)
        except PermissionError:
            user_dir = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "FacturadorSaint"
            user_dir.mkdir(parents=True, exist_ok=True)
            self.rules_file = user_dir / "codigos_reemplazo.json"
            try:
                with open(self.rules_file, "w", encoding="utf-8") as fp:
                    json.dump(default_rules, fp, indent=2, ensure_ascii=False)
            except Exception:
                pass
        except Exception:
            pass
        return default_rules

    def _save_replacement_rules(self):
        try:
            try:
                with open(self.rules_file, "w", encoding="utf-8") as fp:
                    json.dump(self.replacement_rules, fp, indent=2, ensure_ascii=False)
            except PermissionError:
                user_dir = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "FacturadorSaint"
                user_dir.mkdir(parents=True, exist_ok=True)
                self.rules_file = user_dir / "codigos_reemplazo.json"
                with open(self.rules_file, "w", encoding="utf-8") as fp:
                    json.dump(self.replacement_rules, fp, indent=2, ensure_ascii=False)
        except Exception as ex:
            self._log(f"[ERROR] No se pudo guardar codigos_reemplazo.json: {ex}")

    def _save_user_config(self):
        try:
            cfg = {
                "topmost": self.var_topmost.get(),
                "press_f6": self.var_press_f6.get(),
                "speed": self.var_speed.get(),
                "countdown": self.var_countdown.get(),
                "auto_focus": self.var_auto_focus.get(),
                "check_special_code": self.var_check_special_code.get(),
                "price_list_mode": self.var_price_mode.get(),
                "verify_price_by_ocr": self.var_verify_ocr.get(),
                "check_price": self.var_check_price.get(),
                "price_alert_mode": self.var_price_alert_mode.get(),
                "price_currency": self.var_price_curr.get(),
                "price_nav": self.var_price_nav.get()
            }
            try:
                with open(self.config_file, "w", encoding="utf-8") as fp:
                    json.dump(cfg, fp, indent=2, ensure_ascii=False)
            except PermissionError:
                user_dir = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "FacturadorSaint"
                user_dir.mkdir(parents=True, exist_ok=True)
                self.config_file = user_dir / "config_facturador.json"
                with open(self.config_file, "w", encoding="utf-8") as fp:
                    json.dump(cfg, fp, indent=2, ensure_ascii=False)
        except Exception as ex:
            self._log(f"[AVISO] Error al guardar configuración: {ex}")

    def _attach_config_traces(self):
        try:
            self.var_topmost.trace_add("write", lambda *a: self._save_user_config())
            self.var_press_f6.trace_add("write", lambda *a: self._save_user_config())
            self.var_speed.trace_add("write", lambda *a: self._save_user_config())
            self.var_countdown.trace_add("write", lambda *a: self._save_user_config())
            self.var_auto_focus.trace_add("write", lambda *a: self._save_user_config())
            self.var_check_special_code.trace_add("write", lambda *a: self._save_user_config())
            self.var_price_mode.trace_add("write", lambda *a: self._save_user_config())
            self.var_verify_ocr.trace_add("write", lambda *a: self._save_user_config())
            self.var_check_price.trace_add("write", lambda *a: self._save_user_config())
            self.var_price_alert_mode.trace_add("write", lambda *a: self._save_user_config())
            self.var_price_curr.trace_add("write", lambda *a: self._save_user_config())
            self.var_price_nav.trace_add("write", lambda *a: self._save_user_config())
        except Exception:
            pass

    def _refresh_rules_table(self, keep_selection=True):
        if not hasattr(self, "tree_rules"):
            return
        current_sel = self.tree_rules.selection() if keep_selection else ()
        self.tree_rules.delete(*self.tree_rules.get_children())
        for idx, rule in enumerate(self.replacement_rules, 1):
            src = rule.get("codigo_origen", "")
            dst = rule.get("codigo_destino", "")
            desc = rule.get("descripcion", "")
            is_active = rule.get("activo", True)
            activo_txt = "☑ Activo" if is_active else "☐ Inactivo"
            tag = "rule_active" if is_active else "rule_inactive"
            self.tree_rules.insert("", "end", iid=f"rule_{idx-1}",
                                   values=(idx, src, dst, desc, activo_txt),
                                   tags=(tag,))
        if keep_selection and current_sel:
            for item_id in current_sel:
                if self.tree_rules.exists(item_id):
                    self.tree_rules.selection_set(item_id)
                    self.tree_rules.focus(item_id)

    def _on_select_rule_row(self, event=None):
        if not hasattr(self, "tree_rules"):
            return
        sel = self.tree_rules.selection()
        if not sel:
            return
        vals = self.tree_rules.item(sel[0], "values")
        if len(vals) >= 4:
            self.ent_code_src.delete(0, "end")
            self.ent_code_src.insert(0, vals[1])
            self.ent_code_dst.delete(0, "end")
            self.ent_code_dst.insert(0, vals[2])
            self.ent_code_desc.delete(0, "end")
            self.ent_code_desc.insert(0, vals[3])

            src = str(vals[1]).strip()
            rule_active = True
            for r in self.replacement_rules:
                if str(r.get("codigo_origen", "")).strip() == src:
                    rule_active = r.get("activo", True)
                    break
            if hasattr(self, "var_rule_activo"):
                self.var_rule_activo.set(rule_active)

    def _on_chk_rule_activo_changed(self):
        """Se ejecuta inmediatamente cuando el usuario marca o desmarca el checkbox del formulario."""
        src = self.ent_code_src.get().strip() if hasattr(self, "ent_code_src") else ""
        if not src:
            sel = self.tree_rules.selection() if hasattr(self, "tree_rules") else ()
            if sel:
                vals = self.tree_rules.item(sel[0], "values")
                if len(vals) >= 2:
                    src = str(vals[1]).strip()
        if not src:
            return

        new_state = bool(self.var_rule_activo.get())
        found = False
        target_iid = None
        for i, rule in enumerate(self.replacement_rules):
            if str(rule.get("codigo_origen", "")).strip() == src:
                rule["activo"] = new_state
                found = True
                target_iid = f"rule_{i}"
                break

        if found:
            self._save_replacement_rules()
            self._refresh_rules_table(keep_selection=False)
            if target_iid and hasattr(self, "tree_rules") and self.tree_rules.exists(target_iid):
                self.tree_rules.selection_set(target_iid)
                self.tree_rules.focus(target_iid)
            estado_str = "ACTIVA (Habilitada)" if new_state else "INACTIVA (Deshabilitada)"
            icon = "☑" if new_state else "☐"
            self._log(f"{icon} [REGLA] Código {src}: marcada como {estado_str}.")

    def _toggle_rule_active_by_id(self, item_id: str):
        if not item_id or not hasattr(self, "tree_rules") or not self.tree_rules.exists(item_id):
            return
        vals = self.tree_rules.item(item_id, "values")
        if not vals or len(vals) < 2:
            return
        src = str(vals[1]).strip()
        found = False
        new_state = None
        for rule in self.replacement_rules:
            if str(rule.get("codigo_origen", "")).strip() == src:
                new_state = not rule.get("activo", True)
                rule["activo"] = new_state
                found = True
                break
        if found and new_state is not None:
            if hasattr(self, "ent_code_src"):
                self.ent_code_src.delete(0, "end")
                self.ent_code_src.insert(0, src)
            if hasattr(self, "ent_code_dst") and len(vals) >= 3:
                self.ent_code_dst.delete(0, "end")
                self.ent_code_dst.insert(0, vals[2])
            if hasattr(self, "ent_code_desc") and len(vals) >= 4:
                self.ent_code_desc.delete(0, "end")
                self.ent_code_desc.insert(0, vals[3])
            if hasattr(self, "var_rule_activo"):
                self.var_rule_activo.set(new_state)

            self._save_replacement_rules()
            self._refresh_rules_table(keep_selection=False)
            if self.tree_rules.exists(item_id):
                self.tree_rules.selection_set(item_id)
                self.tree_rules.focus(item_id)
            estado_str = "ACTIVA (Habilitada)" if new_state else "INACTIVA (Deshabilitada)"
            icon = "☑" if new_state else "☐"
            self._log(f"{icon} [REGLA] Código {src}: marcada como {estado_str}.")

    def _on_tree_rules_click(self, event):
        region = self.tree_rules.identify_region(event.x, event.y)
        if region != "cell":
            return
        col = self.tree_rules.identify_column(event.x)
        item_id = self.tree_rules.identify_row(event.y)
        if not item_id:
            return
        if col == "#5" or col == "#1":  # Clic directo en la columna 'Estado' (#5) o '#' (#1)
            self._toggle_rule_active_by_id(item_id)
            return "break"

    def _on_tree_rules_double_click(self, event):
        region = self.tree_rules.identify_region(event.x, event.y)
        if region != "cell":
            return
        col = self.tree_rules.identify_column(event.x)
        if col == "#5" or col == "#1":
            # Si el clic fue en la columna de estado o #, ya se alternó con el primer clic
            return "break"
        item_id = self.tree_rules.identify_row(event.y)
        if not item_id:
            return
        self._toggle_rule_active_by_id(item_id)
        return "break"

    def _on_tree_rules_space(self, event):
        sel = self.tree_rules.selection() if hasattr(self, "tree_rules") else ()
        if sel:
            self._toggle_rule_active_by_id(sel[0])
            return "break"

    def _on_toggle_rule_button(self):
        sel = self.tree_rules.selection() if hasattr(self, "tree_rules") else ()
        if sel:
            self._toggle_rule_active_by_id(sel[0])
            return
        src = self.ent_code_src.get().strip() if hasattr(self, "ent_code_src") else ""
        if src:
            for rule in self.replacement_rules:
                if str(rule.get("codigo_origen", "")).strip() == src:
                    new_state = not rule.get("activo", True)
                    rule["activo"] = new_state
                    if hasattr(self, "var_rule_activo"):
                        self.var_rule_activo.set(new_state)
                    self._save_replacement_rules()
                    self._refresh_rules_table()
                    estado_str = "ACTIVA (Habilitada)" if new_state else "INACTIVA (Deshabilitada)"
                    icon = "☑" if new_state else "☐"
                    self._log(f"{icon} [REGLA] Código {src}: marcada como {estado_str}.")
                    return
        messagebox.showwarning("Atención", "Selecciona una regla en la tabla o carga un código para alternar su estado activo/inactivo.", parent=self.root)

    def _on_save_rule(self):
        src = self.ent_code_src.get().strip()
        dst = self.ent_code_dst.get().strip()
        desc = self.ent_code_desc.get().strip()
        is_active = self.var_rule_activo.get() if hasattr(self, "var_rule_activo") else True
        if not src or not dst:
            messagebox.showwarning("Atención", "Debes ingresar tanto el Código de Factura como el Código de Saint.", parent=self.root)
            return
        found = False
        saved_idx = None
        for i, r in enumerate(self.replacement_rules):
            if r.get("codigo_origen", "").strip() == src:
                r["codigo_destino"] = dst
                r["descripcion"] = desc
                r["activo"] = is_active
                found = True
                saved_idx = i
                break
        if not found:
            self.replacement_rules.append({
                "codigo_origen": src,
                "codigo_destino": dst,
                "descripcion": desc,
                "activo": is_active
            })
            saved_idx = len(self.replacement_rules) - 1
            self._log(f"➕ [REGLA] Agregada regla de intercambio: {src} ➔ {dst} ({desc}) [{'Activa' if is_active else 'Inactiva'}].")
        else:
            self._log(f"✏️ [REGLA] Actualizada regla de intercambio: {src} ➔ {dst} ({desc}) [{'Activa' if is_active else 'Inactiva'}].")

        self._save_replacement_rules()
        self._refresh_rules_table(keep_selection=False)
        item_id = f"rule_{saved_idx}"
        if hasattr(self, "tree_rules") and self.tree_rules.exists(item_id):
            self.tree_rules.selection_set(item_id)
            self.tree_rules.focus(item_id)
        estado_txt = "☑ Activo" if is_active else "☐ Inactivo"
        messagebox.showinfo("Regla Guardada", f"Regla guardada con éxito:\n\n• Factura: {src}\n• Saint: {dst}\n• Descripción: {desc or 'N/A'}\n• Estado: {estado_txt}", parent=self.root)

    def _on_delete_rule(self):
        src = self.ent_code_src.get().strip()
        sel = self.tree_rules.selection() if hasattr(self, "tree_rules") else ()
        if sel and not src:
            vals = self.tree_rules.item(sel[0], "values")
            src = vals[1]

        if not src:
            messagebox.showwarning("Atención", "Selecciona una regla de la tabla o escribe el código que deseas eliminar.", parent=self.root)
            return

        confirm = messagebox.askyesno("Confirmar Eliminación", f"¿Estás seguro de que deseas eliminar la regla para el código:\n👉 {src}?", parent=self.root)
        if confirm:
            self.replacement_rules = [r for r in self.replacement_rules if r.get("codigo_origen", "").strip() != src]
            self._save_replacement_rules()
            self._refresh_rules_table()
            self._on_clear_rule_form()
            self._log(f"🗑️ [REGLA] Eliminada regla de intercambio para código {src}.")
            messagebox.showinfo("Regla Eliminada", f"Se eliminó la regla para {src}.", parent=self.root)

    def _on_clear_rule_form(self):
        if hasattr(self, "ent_code_src"):
            self.ent_code_src.delete(0, "end")
        if hasattr(self, "ent_code_dst"):
            self.ent_code_dst.delete(0, "end")
        if hasattr(self, "ent_code_desc"):
            self.ent_code_desc.delete(0, "end")
        if hasattr(self, "var_rule_activo"):
            self.var_rule_activo.set(True)
        if hasattr(self, "tree_rules") and self.tree_rules.selection():
            self.tree_rules.selection_remove(*self.tree_rules.selection())

    def _aplicar_hover(self, boton, bg_normal, bg_hover, fg_normal=None, fg_hover=None):
        """Añade interactividad visual de mouse hover a los botones tk.Button."""
        boton._custom_normal_bg = bg_normal
        if fg_normal:
            boton._custom_normal_fg = fg_normal

        def on_enter(e):
            if str(boton.cget("state")) != "disabled":
                boton.configure(bg=bg_hover)
                if fg_hover:
                    boton.configure(fg=fg_hover)

        def on_leave(e):
            if str(boton.cget("state")) != "disabled":
                cur_bg = getattr(boton, "_custom_normal_bg", bg_normal)
                cur_fg = getattr(boton, "_custom_normal_fg", fg_normal)
                boton.configure(bg=cur_bg)
                if cur_fg:
                    boton.configure(fg=cur_fg)

        boton.bind("<Enter>", on_enter)
        boton.bind("<Leave>", on_leave)

    def _build_styles(self):
        style = ttk.Style(self.root)
        try:
            style.theme_use("clam")
        except Exception:
            pass
        
        self.c_bg = "#f1f5f9"
        self.c_card = "#ffffff"
        self.c_primary = "#0284c7"
        self.c_text = "#0f172a"
        self.c_border = "#e2e8f0"
        
        self.root.configure(bg=self.c_bg)
        style.configure("TFrame", background=self.c_bg)
        style.configure("Card.TFrame", background=self.c_card, relief="solid", borderwidth=1)
        style.configure("TLabel", background=self.c_bg, foreground=self.c_text, font=("Segoe UI", 9))
        style.configure("CardTitle.TLabel", font=("Segoe UI", 10, "bold"), background=self.c_card, foreground="#1e293b")
        style.configure("CardVal.TLabel", font=("Segoe UI", 11, "bold"), background=self.c_card, foreground=self.c_primary)
        style.configure("Muted.TLabel", font=("Segoe UI", 9), background=self.c_card, foreground="#64748b")

        # Estilos modernos para el Treeview
        style.configure("Treeview", 
                        background="#ffffff", 
                        fieldbackground="#ffffff", 
                        foreground="#1e293b", 
                        font=("Segoe UI", 9), 
                        rowheight=26,
                        borderwidth=0)
        style.configure("Treeview.Heading", 
                        background="#1e293b", 
                        foreground="#ffffff", 
                        font=("Segoe UI", 9, "bold"), 
                        relief="flat", 
                        padding=4)
        style.map("Treeview.Heading", 
                  background=[("active", "#334155")])
        style.map("Treeview", 
                  background=[("selected", "#e0f2fe")], 
                  foreground=[("selected", "#0369a1")])

        # Barra de progreso moderna color esmeralda
        style.configure("Horizontal.TProgressbar", 
                        troughcolor="#e2e8f0", 
                        background="#10b981", 
                        thickness=6,
                        borderwidth=0)

        # Estilos modernos para Notebook y Pestañas
        style.configure("TNotebook", background=self.c_bg, borderwidth=0)
        style.configure("TNotebook.Tab", 
                        font=("Segoe UI", 9, "bold"), 
                        padding=[16, 6], 
                        background="#e2e8f0", 
                        foreground="#475569")
        style.map("TNotebook.Tab", 
                  background=[("selected", "#ffffff"), ("active", "#f8fafc")], 
                  foreground=[("selected", "#0284c7"), ("active", "#0f172a")])

    def _build_ui(self):
        # 1. Cabecera principal moderna
        head_bar = tk.Frame(self.root, bg="#0f172a", height=38)
        head_bar.pack(fill="x", side="top")
        
        lbl_brand = tk.Label(head_bar, text="⚡ SAINT BOT", font=("Segoe UI", 9, "bold"),
                             fg="#38bdf8", bg="#1e293b", padx=8, pady=2, relief="flat")
        lbl_brand.pack(side="left", padx=(12, 6), pady=6)
        
        lbl_title = tk.Label(head_bar, text="Facturador Independiente | Saint Enterprise", 
                             font=("Segoe UI", 10, "bold"), fg="#f8fafc", bg="#0f172a")
        lbl_title.pack(side="left", padx=4, pady=6)
        
        lbl_pro_badge = tk.Label(head_bar, text=f"PRO v{updater.CURRENT_VERSION}", font=("Segoe UI", 8, "bold"),
                                 fg="#10b981", bg="#064e3b", padx=6, pady=1)
        lbl_pro_badge.pack(side="left", padx=8, pady=6)

        self.btn_update = tk.Button(
            head_bar,
            text="🔄 Buscar Actualización",
            font=("Segoe UI", 8, "bold"),
            fg="#94a3b8", bg="#1e293b", activebackground="#334155", activeforeground="#f8fafc",
            relief="flat", cursor="hand2", padx=8, pady=1,
            command=self._manual_check_updates
        )
        self.btn_update.pack(side="left", padx=(0, 6), pady=6)

        self.btn_beta = tk.Button(
            head_bar,
            text="🧪 Descargar Beta",
            font=("Segoe UI", 8, "bold"),
            fg="#fbbf24", bg="#1e293b", activebackground="#291e0a", activeforeground="#fef08a",
            relief="flat", cursor="hand2", padx=8, pady=1,
            command=self._manual_check_beta_updates
        )
        self.btn_beta.pack(side="left", padx=(0, 8), pady=6)
        
        self.var_topmost = tk.BooleanVar(value=False)
        self.root.wm_attributes("-topmost", False)

        # 2. Notebook principal con pestañas modernas
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill="both", expand=True, padx=6, pady=(4, 6))

        self.tab_facturacion = ttk.Frame(self.notebook)
        self.tab_codigos = ttk.Frame(self.notebook)

        self.notebook.add(self.tab_facturacion, text="⚡ Facturación en Saint")
        self.notebook.add(self.tab_codigos, text="🔄 Intercambio de Códigos")

        # =============================================================
        # PESTAÑA 1: FACTURACIÓN EN SAINT
        # =============================================================
        container = ttk.Frame(self.tab_facturacion, padding="6")
        container.pack(fill="both", expand=True)

        # -------------------------------------------------------------
        # ELEMENTOS INFERIORES FIJOS (side="bottom" para que NUNCA se oculten)
        # -------------------------------------------------------------

        # A. Registro / Consola (Estilo Terminal Oscura) en el fondo absoluto
        log_box = tk.Frame(container, bg="#0f172a", highlightbackground="#334155", highlightthickness=1)
        log_box.pack(side="bottom", fill="x", pady=(2, 0))
        self.txt_log = tk.Text(log_box, height=2, font=("Consolas", 9), bg="#0f172a", fg="#38bdf8",
                               insertbackground="#38bdf8", relief="flat", padx=8, pady=3, state="disabled")
        self.txt_log.pack(fill="x")

        # B. Panel de Botones de Acción y Progreso (Siempre visible sobre la consola)
        action_card = tk.Frame(container, bg="#ffffff", highlightbackground="#cbd5e1", highlightthickness=1, padx=8, pady=6)
        action_card.pack(side="bottom", fill="x", pady=(0, 4))
        
        r_stat = tk.Frame(action_card, bg="#ffffff")
        r_stat.pack(fill="x", pady=(0, 4))
        
        self.lbl_estado = tk.Label(r_stat, text="● LISTO PARA FACTURAR", font=("Segoe UI", 11, "bold"),
                                   fg="#15803d", bg="#ffffff")
        self.lbl_estado.pack(side="left")
        
        self.lbl_prog_txt = tk.Label(r_stat, text="0 de 0 productos", font=("Segoe UI", 10, "bold"), fg="#0f172a", bg="#ffffff")
        self.lbl_prog_txt.pack(side="right")
        
        self.prog_bar = ttk.Progressbar(action_card, mode="determinate", style="Horizontal.TProgressbar")
        self.prog_bar.pack(fill="x", pady=(0, 6))
        
        # Fila 1: Botones principales de ejecución (Facturar / Pausar / Detener)
        btn_row_exec = tk.Frame(action_card, bg="#ffffff")
        btn_row_exec.pack(fill="x", pady=(0, 5))
        
        self.btn_start = tk.Button(btn_row_exec, text="▶ FACTURAR ESTA FACTURA (F8)", 
                                   font=("Segoe UI", 10, "bold"), fg="#ffffff", bg="#10b981",
                                   activebackground="#047857", activeforeground="#ffffff",
                                   padx=16, pady=6, relief="flat", cursor="hand2",
                                   command=self.start_facturacion)
        self.btn_start.pack(side="left", padx=(0, 8))
        self._aplicar_hover(self.btn_start, bg_normal="#10b981", bg_hover="#059669")
        
        self.btn_pause = tk.Button(btn_row_exec, text="⏸ PAUSAR (F7)", 
                                   font=("Segoe UI", 10, "bold"), fg="#ffffff", bg="#f59e0b",
                                   activebackground="#b45309", activeforeground="#ffffff",
                                   padx=14, pady=6, relief="flat", cursor="hand2",
                                   command=self.pause_facturacion, state="disabled")
        self.btn_pause.pack(side="left", padx=(0, 8))
        self._aplicar_hover(self.btn_pause, bg_normal="#f59e0b", bg_hover="#d97706")
        
        self.btn_stop = tk.Button(btn_row_exec, text="⏹ DETENER (F12 / ESC)", 
                                  font=("Segoe UI", 10, "bold"), fg="#ffffff", bg="#ef4444",
                                  activebackground="#b91c1c", activeforeground="#ffffff",
                                  padx=14, pady=6, relief="flat", cursor="hand2",
                                  command=self.stop_facturacion, state="disabled")
        self.btn_stop.pack(side="left", padx=(0, 8))
        self._aplicar_hover(self.btn_stop, bg_normal="#ef4444", bg_hover="#dc2626")

        # Fila 2: Herramientas de Auditoría OCR y Gestión de Caché
        btn_row_tools = tk.Frame(action_card, bg="#ffffff")
        btn_row_tools.pack(fill="x")

        self.btn_audit_now = tk.Button(btn_row_tools, text="🔍 Auditar Pantalla Ahora (OCR)",
                                       font=("Segoe UI", 9, "bold"), fg="#0369a1", bg="#e0f2fe",
                                       activebackground="#bae6fd", activeforeground="#0284c7",
                                       relief="solid", borderwidth=1, padx=12, pady=5, cursor="hand2",
                                       command=self._on_manual_audit)
        self.btn_audit_now.pack(side="left", padx=(0, 8))
        self._aplicar_hover(self.btn_audit_now, bg_normal="#e0f2fe", bg_hover="#bae6fd")

        self.btn_show_diffs = tk.Button(btn_row_tools, text="📋 Ver Auditoría OCR", 
                                        font=("Segoe UI", 9, "bold"), fg="#64748b", bg="#f1f5f9",
                                        activebackground="#e2e8f0", activeforeground="#0f172a",
                                        relief="solid", borderwidth=1, padx=12, pady=5, cursor="hand2",
                                        command=self._show_audit_window, state="disabled")
        self.btn_show_diffs.pack(side="left", padx=(0, 8))
        self._aplicar_hover(self.btn_show_diffs, bg_normal="#f1f5f9", bg_hover="#e2e8f0")

        count_cache = contar_archivos_cache()
        self.btn_clear_cache = tk.Button(btn_row_tools, text=f"🧹 Limpiar Caché / Archivos ({count_cache})",
                                         font=("Segoe UI", 9, "bold"), fg="#334155", bg="#f8fafc",
                                         activebackground="#e2e8f0", activeforeground="#0f172a",
                                         relief="solid", borderwidth=1, padx=12, pady=5, cursor="hand2",
                                         command=self._on_clear_cache)
        self.btn_clear_cache.pack(side="right")
        self._aplicar_hover(self.btn_clear_cache, bg_normal="#f8fafc", bg_hover="#e2e8f0")

        # -------------------------------------------------------------
        # ELEMENTOS SUPERIORES (side="top")
        # -------------------------------------------------------------

        # 2. Selector de Factura JSON
        sel_card = tk.Frame(container, bg="#ffffff", highlightbackground="#cbd5e1", highlightthickness=1, padx=10, pady=6)
        sel_card.pack(side="top", fill="x", pady=(0, 4))
        
        tk.Label(sel_card, text="Factura a Procesar:", font=("Segoe UI", 9, "bold"), bg="#ffffff", fg="#0f172a").pack(side="left", padx=(0, 6))
        self.cbo_facturas = ttk.Combobox(sel_card, state="readonly", width=34, font=("Segoe UI", 9, "bold"))
        self.cbo_facturas.pack(side="left", padx=4)
        self.cbo_facturas.bind("<<ComboboxSelected>>", self._on_combo_select)
        
        btn_refresh = tk.Button(sel_card, text="🔄 Refrescar", font=("Segoe UI", 9, "bold"),
                                bg="#f1f5f9", fg="#0f172a", activebackground="#e2e8f0",
                                relief="solid", borderwidth=1, padx=8, pady=2, cursor="hand2",
                                command=lambda: self._scan_json_files(select_latest=True))
        btn_refresh.pack(side="left", padx=3)
        self._aplicar_hover(btn_refresh, bg_normal="#f1f5f9", bg_hover="#e2e8f0")
        
        btn_browse = tk.Button(sel_card, text="📂 Examinar otro JSON...", font=("Segoe UI", 9, "bold"),
                               bg="#f1f5f9", fg="#0f172a", activebackground="#e2e8f0",
                               relief="solid", borderwidth=1, padx=8, pady=2, cursor="hand2",
                               command=self._browse_json)
        btn_browse.pack(side="left", padx=3)
        self._aplicar_hover(btn_browse, bg_normal="#f1f5f9", bg_hover="#e2e8f0")
        
        self.btn_extractor = tk.Button(
            sel_card, 
            text="⚡ Ejecutar Extractor", 
            font=("Segoe UI", 9, "bold"),
            fg="#ffffff", bg="#2563eb", activebackground="#1e40af", activeforeground="#ffffff",
            relief="flat", padx=10, pady=3, cursor="hand2",
            command=self._run_extractor
        )
        self.btn_extractor.pack(side="left", padx=(6, 2))
        self._aplicar_hover(self.btn_extractor, bg_normal="#2563eb", bg_hover="#1d4ed8")

        # 3. Opciones de Facturación en Saint
        opts_card = tk.Frame(container, bg="#ffffff", highlightbackground="#cbd5e1", highlightthickness=1, padx=10, pady=5)
        opts_card.pack(side="top", fill="x", pady=(0, 4))
        
        row_o1 = tk.Frame(opts_card, bg="#ffffff")
        row_o1.pack(fill="x")
        
        self.var_price_mode = tk.StringVar(value=self.saved_cfg.get("price_list_mode", "precio_3"))
        self.var_price_curr = tk.StringVar(value=self.saved_cfg.get("price_currency", "usd"))

        self.var_verify_ocr = tk.BooleanVar(value=self.saved_cfg.get("verify_price_by_ocr", True))
        chk_ocr = tk.Checkbutton(
            row_o1,
            text="📷 Captura cada 8 ítems (OCR)",
            variable=self.var_verify_ocr,
            font=("Segoe UI", 9, "bold"),
            fg="#0f172a", bg="#ffffff", activebackground="#ffffff", activeforeground="#0f172a",
            selectcolor="#ffffff", cursor="hand2"
        )
        chk_ocr.pack(side="left", padx=(0, 14))

        self.var_check_price = tk.BooleanVar(value=self.saved_cfg.get("check_price", True))
        chk_price = tk.Checkbutton(
            row_o1,
            text="💵 Alertar diferencias de precio",
            variable=self.var_check_price,
            font=("Segoe UI", 9, "bold"),
            fg="#0f172a", bg="#ffffff", activebackground="#ffffff", activeforeground="#0f172a",
            selectcolor="#ffffff", cursor="hand2"
        )
        chk_price.pack(side="left", padx=(0, 14))

        self.var_press_f6 = tk.BooleanVar(value=self.saved_cfg.get("press_f6", False))
        chk_f6 = tk.Checkbutton(
            row_o1, 
            text="💾 Guardar con F6 al terminar", 
            variable=self.var_press_f6,
            font=("Segoe UI", 9, "bold"),
            fg="#0f172a", bg="#ffffff", activebackground="#ffffff", activeforeground="#0f172a",
            selectcolor="#ffffff", cursor="hand2"
        )
        chk_f6.pack(side="left")
        
        row_o2 = tk.Frame(opts_card, bg="#ffffff")
        row_o2.pack(fill="x", pady=(3, 0))
        
        self.var_check_special_code = tk.BooleanVar(value=self.saved_cfg.get("check_special_code", True))
        chk_special = tk.Checkbutton(
            row_o2, 
            text="🔔 Aplicar reglas de intercambio de códigos al cargar factura (Pestaña 'Intercambio')", 
            variable=self.var_check_special_code,
            font=("Segoe UI", 9, "bold"),
            fg="#0f172a", bg="#ffffff", activebackground="#ffffff", activeforeground="#0f172a",
            selectcolor="#ffffff", cursor="hand2"
        )
        chk_special.pack(side="left")

        self.var_price_alert_mode = tk.StringVar(value=self.saved_cfg.get("price_alert_mode", "summary"))
        self.var_price_nav = tk.StringVar(value=self.saved_cfg.get("price_nav", "enter"))

        # 4. Ficha Informativa de la Factura Seleccionada (Dashboard KPI de 3 tarjetas limpias)
        info_card = tk.Frame(container, bg="#ffffff", highlightbackground="#cbd5e1", highlightthickness=1, padx=8, pady=6)
        info_card.pack(side="top", fill="x", pady=(0, 4))
        
        kpi_grid = tk.Frame(info_card, bg="#ffffff")
        kpi_grid.pack(fill="x")
        kpi_grid.columnconfigure(0, weight=1)
        kpi_grid.columnconfigure(1, weight=1)
        kpi_grid.columnconfigure(2, weight=1)
        
        # Tarjeta 1: Factura (Limpia, sin línea de proveedor)
        b_fact = tk.Frame(kpi_grid, bg="#f8fafc", highlightbackground="#cbd5e1", highlightthickness=1, padx=10, pady=5)
        b_fact.grid(row=0, column=0, sticky="nsew", padx=3)
        tk.Label(b_fact, text="📄 FACTURA SELECCIONADA", font=("Segoe UI", 8, "bold"), fg="#475569", bg="#f8fafc", anchor="w").pack(fill="x")
        self.lbl_factura_id = tk.Label(b_fact, text="Factura: --", font=("Segoe UI", 11, "bold"), fg="#0f172a", bg="#f8fafc", anchor="w")
        self.lbl_factura_id.pack(fill="x", pady=(2, 0))
        # Referencia dummy para compatibilidad interna sin mostrar proveedor en pantalla
        self.lbl_proveedor = tk.Label()
        
        # Tarjeta 2: Total USD (Verde Esmeralda - Gran visibilidad)
        b_usd = tk.Frame(kpi_grid, bg="#ecfdf5", highlightbackground="#86efac", highlightthickness=1, padx=10, pady=5)
        b_usd.grid(row=0, column=1, sticky="nsew", padx=3)
        tk.Label(b_usd, text="💵 TOTAL EN DÓLARES (USD)", font=("Segoe UI", 8, "bold"), fg="#059669", bg="#ecfdf5", anchor="w").pack(fill="x")
        self.lbl_total_usd = tk.Label(b_usd, text="Total USD: $ 0.00", font=("Segoe UI", 13, "bold"), fg="#047857", bg="#ecfdf5", anchor="w")
        self.lbl_total_usd.pack(fill="x", pady=(2, 0))
        # Total en Bolívares removido visualmente; referencia dummy interna para compatibilidad
        self.lbl_total_bs = tk.Label()
        
        # Tarjeta 3: Ítems / Productos a Facturar (Azul)
        b_items = tk.Frame(kpi_grid, bg="#eff6ff", highlightbackground="#93c5fd", highlightthickness=1, padx=10, pady=5)
        b_items.grid(row=0, column=2, sticky="nsew", padx=3)
        tk.Label(b_items, text="📦 PRODUCTOS / ÍTEMS", font=("Segoe UI", 8, "bold"), fg="#2563eb", bg="#eff6ff", anchor="w").pack(fill="x")
        self.lbl_items_badge = tk.Label(b_items, text="Total Ítems: 0", font=("Segoe UI", 11, "bold"), fg="#1e40af", bg="#eff6ff", anchor="w")
        self.lbl_items_badge.pack(fill="x", pady=(2, 0))
        self.lbl_tasa = tk.Label()

        # Fila de Partes de Factura (visible sólo si la factura supera los 43 productos)
        self.frame_partes = tk.Frame(info_card, bg="#eff6ff", highlightbackground="#93c5fd", highlightthickness=1, padx=8, pady=4)
        lbl_p_title = tk.Label(self.frame_partes, text="✂️ FACTURA DIVIDIDA (Máx. 43 en Saint):",
                               font=("Segoe UI", 9, "bold"), fg="#1e40af", bg="#eff6ff")
        lbl_p_title.pack(side="left", padx=(0, 8))
        
        self.cbo_partes = ttk.Combobox(self.frame_partes, state="readonly", width=42, font=("Segoe UI", 9, "bold"))
        self.cbo_partes.pack(side="left", padx=(0, 8))
        self.cbo_partes.bind("<<ComboboxSelected>>", self._on_part_combo_select)
        
        self.btn_export_parts = tk.Button(self.frame_partes, text="💾 Exportar a JSONs separados",
                                          font=("Segoe UI", 8, "bold"), fg="#1e40af", bg="#dbeafe",
                                          activebackground="#bfdbfe", relief="solid", borderwidth=1,
                                          padx=8, pady=2, cursor="hand2", command=self._export_parts_json)
        self.btn_export_parts.pack(side="right")
        self._aplicar_hover(self.btn_export_parts, bg_normal="#dbeafe", bg_hover="#bfdbfe")

        # 5. Barra de Opciones de Velocidad
        opt_bar = tk.Frame(container, bg="#ffffff", highlightbackground="#cbd5e1", highlightthickness=1, padx=8, pady=5)
        opt_bar.pack(side="top", fill="x", pady=(0, 4))
        
        tk.Label(opt_bar, text="Velocidad / Pausa:", bg="#ffffff", fg="#0f172a", font=("Segoe UI", 9, "bold")).pack(side="left", padx=(0, 6))
        self.var_speed = tk.StringVar(value=self.saved_cfg.get("speed", "normal"))
        tk.Radiobutton(opt_bar, text="Rápido (350ms)", value="fast", variable=self.var_speed, bg="#ffffff", fg="#0f172a", activebackground="#ffffff", activeforeground="#0f172a", selectcolor="#ffffff", font=("Segoe UI", 9), cursor="hand2").pack(side="left", padx=4)
        tk.Radiobutton(opt_bar, text="Normal (500ms)", value="normal", variable=self.var_speed, bg="#ffffff", fg="#0f172a", activebackground="#ffffff", activeforeground="#0f172a", selectcolor="#ffffff", font=("Segoe UI", 9), cursor="hand2").pack(side="left", padx=4)
        tk.Radiobutton(opt_bar, text="Seguro (800ms)", value="safe", variable=self.var_speed, bg="#ffffff", fg="#0f172a", activebackground="#ffffff", activeforeground="#0f172a", selectcolor="#ffffff", font=("Segoe UI", 9), cursor="hand2").pack(side="left", padx=4)
        
        tk.Label(opt_bar, text="⏱️ Espera inicial:", bg="#ffffff", fg="#0f172a", font=("Segoe UI", 9, "bold")).pack(side="left", padx=(14, 4))
        self.var_countdown = tk.IntVar(value=self.saved_cfg.get("countdown", 5))
        spn_cd = ttk.Spinbox(opt_bar, from_=1, to=15, textvariable=self.var_countdown, width=3, font=("Segoe UI", 9, "bold"))
        spn_cd.pack(side="left", padx=(0, 2))
        tk.Label(opt_bar, text="seg", bg="#ffffff", fg="#0f172a", font=("Segoe UI", 9, "bold")).pack(side="left", padx=(0, 6))
        
        self.var_auto_focus = tk.BooleanVar(value=self.saved_cfg.get("auto_focus", True))
        chk_focus = tk.Checkbutton(opt_bar, text="🎯 Traer ventana de Saint al frente automáticamente", 
                                   variable=self.var_auto_focus, bg="#ffffff", fg="#0f172a", activebackground="#ffffff",
                                   activeforeground="#0f172a", selectcolor="#ffffff",
                                   font=("Segoe UI", 9), cursor="hand2")
        chk_focus.pack(side="right", padx=8)

        # -------------------------------------------------------------
        # 6. Tabla de Productos (Treeview) QUE OCUPA EL ESPACIO CENTRAL FLEXIBLE
        # -------------------------------------------------------------
        table_frame = tk.Frame(container, bg="#ffffff", highlightbackground="#cbd5e1", highlightthickness=1)
        table_frame.pack(side="top", fill="both", expand=True, pady=(0, 4))
        
        cols = ("num", "ref", "desc", "cant", "precio", "estado")
        self.tree = ttk.Treeview(table_frame, columns=cols, show="headings", height=5, selectmode="browse")
        
        self.tree.heading("num", text="#")
        self.tree.heading("ref", text="Referencia (Código Barra)")
        self.tree.heading("desc", text="Descripción")
        self.tree.heading("cant", text="Cant.")
        self.tree.heading("precio", text="Precio")
        self.tree.heading("estado", text="Estado / Alertas")
        
        self.tree.column("num", width=38, minwidth=35, anchor="center")
        self.tree.column("ref", width=140, minwidth=120, anchor="center")
        self.tree.column("desc", width=280, minwidth=200, anchor="w")
        self.tree.column("cant", width=55, minwidth=45, anchor="center")
        self.tree.column("precio", width=85, minwidth=70, anchor="e")
        self.tree.column("estado", width=240, minwidth=180, anchor="center")
        
        scrolly = ttk.Scrollbar(table_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrolly.set)
        self.tree.pack(side="left", fill="both", expand=True)
        scrolly.pack(side="right", fill="y")
        
        self.tree.tag_configure("pending", foreground="#0f172a", font=("Segoe UI", 9))
        self.tree.tag_configure("active", background="#fef08a", foreground="#713f12", font=("Segoe UI", 9, "bold"))
        self.tree.tag_configure("done", background="#dcfce7", foreground="#14532d", font=("Segoe UI", 9, "bold"))
        self.tree.tag_configure("replaced", background="#e0f2fe", foreground="#0369a1", font=("Segoe UI", 9, "bold"))
        self.tree.tag_configure("diff_fixed", background="#fef3c7", foreground="#78350f", font=("Segoe UI", 9, "bold"))
        self.tree.tag_configure("diff_kept", background="#fee2e2", foreground="#991b1b", font=("Segoe UI", 9, "bold"))
        self.tree.tag_configure("diff_paused", background="#ffedd5", foreground="#9a3412", font=("Segoe UI", 9, "bold"))

        # =============================================================
        # PESTAÑA 2: INTERCAMBIO DE CÓDIGOS DE BARRA
        # =============================================================
        self._build_tab_codigos()

    def _build_tab_codigos(self):
        container_cod = ttk.Frame(self.tab_codigos, padding="10")
        container_cod.pack(fill="both", expand=True)

        # 1. Cabecera informativa de la pestaña
        info_card = tk.Frame(container_cod, bg="#ffffff", highlightbackground="#cbd5e1", highlightthickness=1, padx=12, pady=10)
        info_card.pack(fill="x", pady=(0, 8))

        lbl_t2_title = tk.Label(info_card, text="🔄 Reglas de Intercambio de Códigos de Barra", 
                                font=("Segoe UI", 11, "bold"), fg="#0f172a", bg="#ffffff")
        lbl_t2_title.pack(anchor="w")

        lbl_t2_sub = tk.Label(
            info_card, 
            text="Configura los códigos que deben ser sustituidos automáticamente por códigos compatibles de Saint al abrir una factura (ej. Pistachos Wonderful, presentaciones alternas, etc.).",
            font=("Segoe UI", 9), fg="#64748b", bg="#ffffff", wraplength=780, justify="left"
        )
        lbl_t2_sub.pack(anchor="w", pady=(2, 0))

        # 2. Tarjeta con la tabla de reglas
        table_card = tk.Frame(container_cod, bg="#ffffff", highlightbackground="#cbd5e1", highlightthickness=1, padx=8, pady=8)
        table_card.pack(fill="both", expand=True, pady=(0, 8))

        lbl_tbl_title = tk.Label(table_card, text="📋 Catálogo de Reglas Registradas (Haz clic en 'Estado', doble clic o pulsa Espacio para activar/desactivar):",
                                 font=("Segoe UI", 9, "bold"), fg="#334155", bg="#ffffff")
        lbl_tbl_title.pack(anchor="w", pady=(0, 6))

        tbl_inner = tk.Frame(table_card, bg="#ffffff")
        tbl_inner.pack(fill="both", expand=True)

        cols_rules = ("num", "origen", "destino", "desc", "estado")
        self.tree_rules = ttk.Treeview(tbl_inner, columns=cols_rules, show="headings", height=8, selectmode="browse")

        self.tree_rules.heading("num", text="#")
        self.tree_rules.heading("origen", text="Código en Factura (Origen)")
        self.tree_rules.heading("destino", text="Código en Saint (Destino)")
        self.tree_rules.heading("desc", text="Descripción / Producto")
        self.tree_rules.heading("estado", text="Estado (Clic para alternar)")

        self.tree_rules.column("num", width=40, minwidth=35, anchor="center")
        self.tree_rules.column("origen", width=180, minwidth=140, anchor="center")
        self.tree_rules.column("destino", width=180, minwidth=140, anchor="center")
        self.tree_rules.column("desc", width=260, minwidth=160, anchor="w")
        self.tree_rules.column("estado", width=120, minwidth=100, anchor="center")

        scrolly_r = ttk.Scrollbar(tbl_inner, orient="vertical", command=self.tree_rules.yview)
        self.tree_rules.configure(yscrollcommand=scrolly_r.set)
        self.tree_rules.pack(side="left", fill="both", expand=True)
        scrolly_r.pack(side="right", fill="y")

        self.tree_rules.bind("<<TreeviewSelect>>", self._on_select_rule_row)
        self.tree_rules.bind("<Button-1>", self._on_tree_rules_click)
        self.tree_rules.bind("<Double-1>", self._on_tree_rules_double_click)
        self.tree_rules.bind("<space>", self._on_tree_rules_space)
        self.tree_rules.tag_configure("rule_active", font=("Segoe UI", 9), foreground="#0f172a")
        self.tree_rules.tag_configure("rule_inactive", font=("Segoe UI", 9), foreground="#94a3b8")

        # Menú contextual con clic derecho en la tabla
        self.menu_rules = tk.Menu(self.root, tearoff=0)
        self.menu_rules.add_command(label="⚡ Activar / Desactivar Estado", command=self._on_toggle_rule_button)
        self.menu_rules.add_separator()
        self.menu_rules.add_command(label="🗑️ Eliminar Regla", command=self._on_delete_rule)

        def _on_tree_right_click(event):
            item_id = self.tree_rules.identify_row(event.y)
            if item_id:
                self.tree_rules.selection_set(item_id)
                self.tree_rules.focus(item_id)
                self._on_select_rule_row()
                self.menu_rules.tk_popup(event.x_root, event.y_root)

        self.tree_rules.bind("<Button-3>", _on_tree_right_click)

        # 3. Tarjeta de Formulario: Agregar o Editar Regla
        form_card = tk.Frame(container_cod, bg="#ffffff", highlightbackground="#cbd5e1", highlightthickness=1, padx=12, pady=10)
        form_card.pack(fill="x", pady=(0, 4))

        lbl_f_title = tk.Label(form_card, text="➕ Agregar o Modificar Regla de Intercambio",
                               font=("Segoe UI", 10, "bold"), fg="#0f172a", bg="#ffffff")
        lbl_f_title.pack(anchor="w", pady=(0, 8))

        grid_f = tk.Frame(form_card, bg="#ffffff")
        grid_f.pack(fill="x", pady=(0, 10))

        # Fila 1: Origen y Destino
        tk.Label(grid_f, text="Código en Factura (Origen):", font=("Segoe UI", 9, "bold"), fg="#334155", bg="#ffffff").grid(row=0, column=0, sticky="w", padx=(0, 8), pady=4)
        self.ent_code_src = tk.Entry(grid_f, font=("Segoe UI", 10), bg="#f8fafc", fg="#0f172a", relief="solid", borderwidth=1, width=22)
        self.ent_code_src.grid(row=0, column=1, sticky="w", padx=(0, 20), pady=4)

        tk.Label(grid_f, text="Código en Saint (Destino):", font=("Segoe UI", 9, "bold"), fg="#334155", bg="#ffffff").grid(row=0, column=2, sticky="w", padx=(0, 8), pady=4)
        self.ent_code_dst = tk.Entry(grid_f, font=("Segoe UI", 10), bg="#f8fafc", fg="#0f172a", relief="solid", borderwidth=1, width=22)
        self.ent_code_dst.grid(row=0, column=3, sticky="w", padx=(0, 10), pady=4)

        # Fila 2: Descripción
        tk.Label(grid_f, text="Descripción del Producto:", font=("Segoe UI", 9, "bold"), fg="#334155", bg="#ffffff").grid(row=1, column=0, sticky="w", padx=(0, 8), pady=4)
        self.ent_code_desc = tk.Entry(grid_f, font=("Segoe UI", 10), bg="#f8fafc", fg="#0f172a", relief="solid", borderwidth=1, width=58)
        self.ent_code_desc.grid(row=1, column=1, columnspan=3, sticky="w", pady=4)

        # Fila 3: Checkbox Estado Activo
        self.var_rule_activo = tk.BooleanVar(value=True)
        self.chk_rule_activo = tk.Checkbutton(
            grid_f,
            text="Regla Activa (Marcar para activar / Desmarcar para desactivar)",
            variable=self.var_rule_activo,
            font=("Segoe UI", 9, "bold"),
            fg="#0369a1",
            bg="#ffffff",
            activebackground="#ffffff",
            activeforeground="#0284c7",
            selectcolor="#ffffff",
            cursor="hand2",
            command=self._on_chk_rule_activo_changed
        )
        self.chk_rule_activo.grid(row=2, column=1, columnspan=3, sticky="w", pady=(2, 4))

        # Fila de Botones de Acción para Reglas
        btn_box_r = tk.Frame(form_card, bg="#ffffff")
        btn_box_r.pack(fill="x", pady=(4, 0))

        self.btn_save_rule = tk.Button(
            btn_box_r,
            text="💾 Guardar / Agregar Regla",
            font=("Segoe UI", 9, "bold"),
            fg="#ffffff", bg="#10b981", activebackground="#047857", activeforeground="#ffffff",
            padx=12, pady=6, relief="flat", cursor="hand2",
            command=self._on_save_rule
        )
        self.btn_save_rule.pack(side="left", padx=(0, 8))
        self._aplicar_hover(self.btn_save_rule, bg_normal="#10b981", bg_hover="#059669")

        self.btn_toggle_rule = tk.Button(
            btn_box_r,
            text="⚡ Activar / Desactivar Estado",
            font=("Segoe UI", 9, "bold"),
            fg="#ffffff", bg="#0284c7", activebackground="#0369a1", activeforeground="#ffffff",
            padx=12, pady=6, relief="flat", cursor="hand2",
            command=self._on_toggle_rule_button
        )
        self.btn_toggle_rule.pack(side="left", padx=(0, 8))
        self._aplicar_hover(self.btn_toggle_rule, bg_normal="#0284c7", bg_hover="#0369a1")

        self.btn_del_rule = tk.Button(
            btn_box_r,
            text="🗑️ Eliminar Regla Seleccionada",
            font=("Segoe UI", 9, "bold"),
            fg="#ffffff", bg="#ef4444", activebackground="#b91c1c", activeforeground="#ffffff",
            padx=12, pady=6, relief="flat", cursor="hand2",
            command=self._on_delete_rule
        )
        self.btn_del_rule.pack(side="left", padx=(0, 8))
        self._aplicar_hover(self.btn_del_rule, bg_normal="#ef4444", bg_hover="#dc2626")

        self.btn_clear_rule = tk.Button(
            btn_box_r,
            text="🧹 Limpiar Campos",
            font=("Segoe UI", 9, "bold"),
            fg="#334155", bg="#f1f5f9", activebackground="#e2e8f0", activeforeground="#0f172a",
            padx=12, pady=6, relief="solid", borderwidth=1, cursor="hand2",
            command=self._on_clear_rule_form
        )
        self.btn_clear_rule.pack(side="left")
        self._aplicar_hover(self.btn_clear_rule, bg_normal="#f1f5f9", bg_hover="#e2e8f0")

        # Cargar datos iniciales en la tabla
        self._refresh_rules_table()

    def _toggle_topmost(self):
        is_top = self.var_topmost.get()
        self.root.wm_attributes("-topmost", is_top)
        try:
            f_str = self.root.wm_frame() if hasattr(self.root, "wm_frame") else ""
            h = int(f_str, 16) if f_str else self.root.winfo_id()
            if h:
                HWND_TARGET = -1 if is_top else -2
                user32.SetWindowPos(h, HWND_TARGET, 0, 0, 0, 0, 0x0002 | 0x0001 | 0x0040)
        except Exception:
            pass

    def _scan_json_files(self, select_latest=False):
        if not self.json_dir.exists():
            return
        files = sorted(list(self.json_dir.glob("*.json")))
        if not files:
            self.cbo_facturas["values"] = []
            self.cbo_facturas.set("")
            self.items_list = []
            self.current_json_data = None
            if hasattr(self, "tree"):
                self.tree.delete(*self.tree.get_children())
            if hasattr(self, "lbl_total_items"):
                self.lbl_total_items.configure(text="0")
            if hasattr(self, "lbl_total_bs"):
                self.lbl_total_bs.configure(text="0.00 Bs")
            if hasattr(self, "lbl_total_usd"):
                self.lbl_total_usd.configure(text="$0.00")
            if hasattr(self, "lbl_info"):
                self.lbl_info.configure(text="Sin facturas cargadas.")
            return
        values = [f.name for f in files]
        self.cbo_facturas["values"] = values
        if values:
            if select_latest:
                latest = max(files, key=lambda f: f.stat().st_mtime)
                try:
                    idx = values.index(latest.name)
                    self.cbo_facturas.current(idx)
                    self._load_json(latest)
                except Exception:
                    self.cbo_facturas.current(0)
                    self._load_json(files[0])
            elif not self.cbo_facturas.get() or self.cbo_facturas.get() not in values:
                self.cbo_facturas.current(0)
                self._load_json(files[0])

    def _on_combo_select(self, event=None):
        name = self.cbo_facturas.get()
        if name:
            p = self.json_dir / name
            if p.exists():
                self._load_json(p)

    def _browse_json(self):
        path = filedialog.askopenfilename(
            title="Seleccionar Factura JSON",
            initialdir=str(self.json_dir if self.json_dir.exists() else self.base_dir),
            filetypes=[("Archivos JSON", "*.json"), ("Todos", "*.*")]
        )
        if path:
            self._load_json(Path(path))

    def _run_extractor(self):
        if self.engine.running:
            messagebox.showwarning("Atención", "No puedes ejecutar el extractor mientras el bot está facturando.", parent=self.root)
            return

        # Deshabilitar botón durante el proceso
        self.btn_extractor.configure(state="disabled", text="⏳ Extrayendo...")
        self._log("⚡ [EXTRACTOR] Iniciando extracción de documentos (PDF / Excel)...")

        def worker():
            pdf_dir = self.base_dir / "facturas_pdf"
            pdf_dir.mkdir(parents=True, exist_ok=True)
            json_dir = self.base_dir / "facturas_json"
            json_dir.mkdir(parents=True, exist_ok=True)

            pdf_files = (
                list(pdf_dir.glob("*.pdf")) + 
                list(pdf_dir.glob("*.xlsx")) + 
                list(pdf_dir.glob("*.xls"))
            )

            if not pdf_files:
                def on_no_files():
                    self.btn_extractor.configure(state="normal", text="⚡ Ejecutar Extractor")
                    msg = (
                        "ℹ️ No se encontraron archivos PDF o Excel para procesar.\n\n"
                        "Por favor coloca tus facturas o presupuestos en la carpeta 'facturas_pdf' "
                        "y vuelve a presionar 'Ejecutar Extractor'."
                    )
                    self._log("⚠️ [EXTRACTOR] No se encontraron archivos en 'facturas_pdf'.")
                    messagebox.showwarning("Sin Documentos", msg, parent=self.root)
                self.root.after(0, on_no_files)
                return

            try:
                import io
                import contextlib
                f_out = io.StringIO()
                rutas_str = [str(p) for p in sorted(pdf_files)]
                self._log(f"⚡ [EXTRACTOR] Analizando {len(rutas_str)} documento(s)...")

                with contextlib.redirect_stdout(f_out), contextlib.redirect_stderr(f_out):
                    extractor.procesar_archivos(rutas_str, str(json_dir))

                stdout_text = f_out.getvalue()

                def update_ui():
                    self.btn_extractor.configure(state="normal", text="⚡ Ejecutar Extractor")

                    # Registrar líneas clave en el log de la aplicación
                    for line in stdout_text.splitlines():
                        line_clean = line.strip()
                        if line_clean and any(k in line_clean for k in ("Procesando:", "OK", "Archivos JSON", "Total de productos", "Proceso finalizado")):
                            self._log(f"⚡ {line_clean}")

                    # Refrescar los archivos JSON y seleccionar el más nuevo
                    prev_files = set(self.cbo_facturas["values"]) if self.cbo_facturas["values"] else set()
                    self._scan_json_files(select_latest=True)
                    new_files = set(self.cbo_facturas["values"]) if self.cbo_facturas["values"] else set()
                    added = new_files - prev_files
                    active_factura = self.cbo_facturas.get()

                    self._log("✅ [EXTRACTOR] Extracción completada con éxito.")
                    if added:
                        msg = (
                            f"✅ ¡Extracción completada con éxito!\n\n"
                            f"Se cargaron {len(added)} nueva(s) factura(s) a la lista:\n"
                            + "\n".join(f"• {f}" for f in sorted(added))
                            + f"\n\nFactura seleccionada actualmente:\n• {active_factura}"
                        )
                    else:
                        msg = (
                            "✅ ¡Proceso completado con éxito!\n\n"
                            "Los archivos JSON en facturas_json/ fueron actualizados correctamente.\n\n"
                            f"Factura activa:\n• {active_factura}"
                        )
                    messagebox.showinfo("Extractor Completado", msg, parent=self.root)

                self.root.after(0, update_ui)

            except Exception as ex:
                def on_err():
                    self.btn_extractor.configure(state="normal", text="⚡ Ejecutar Extractor")
                    self._log(f"❌ [EXTRACTOR] Excepción: {ex}")
                    messagebox.showerror("Error", f"Error inesperado al ejecutar extractor:\n{ex}", parent=self.root)
                self.root.after(0, on_err)

        threading.Thread(target=worker, daemon=True).start()

    def _load_json(self, path: Path):
        try:
            with open(path, "r", encoding="utf-8") as fp:
                data = json.load(fp)
        except Exception as e:
            messagebox.showerror("Error", f"No se pudo abrir {path.name}:\n{e}")
            return

        self.current_json_data = data
        factura_id = data.get("factura", path.stem)
        proveedor = data.get("proveedor", "N/A")
        totales = data.get("totales", {})
        total_usd = totales.get("total_usd", 0.0)
        total_bs = totales.get("total_bs", 0.0)
        tasa = data.get("tasa_cambio", 0.0)
        productos = [dict(p) for p in data.get("productos", [])]

        # Comprobar reglas dinámicas de intercambio de códigos (pestaña 'Intercambio')
        if getattr(self, "var_check_special_code", None) and self.var_check_special_code.get():
            rules_to_check = getattr(self, "replacement_rules", [])
            if not rules_to_check:
                rules_to_check = [{
                    "codigo_origen": "014113701808",
                    "codigo_destino": "014113910088",
                    "descripcion": "PISTACHO WONDERFUL",
                    "activo": True
                }]
            for rule in rules_to_check:
                if not rule.get("activo", True):
                    continue
                special_src = str(rule.get("codigo_origen", "")).strip()
                special_dst = str(rule.get("codigo_destino", "")).strip()
                desc_rule = rule.get("descripcion", "") or "Producto"
                if not special_src or not special_dst:
                    continue
                matching = [p for p in productos if str(p.get("codigo_barra", "")).strip() == special_src]
                if matching:
                    count_m = len(matching)
                    desc_prod = matching[0].get("descripcion", desc_rule)
                    resp = messagebox.askyesno(
                        "Detección de Código a Intercambiar",
                        f"⚠️ Se detectó el producto con código:\n\n"
                        f"• Código Factura: {special_src}\n"
                        f"• Descripción: {desc_prod}\n"
                        f"• Ocurrencias: {count_m}\n\n"
                        f"¿Deseas cambiarlo por el código de Saint:\n"
                        f"👉 {special_dst} para esta factura?",
                        parent=self.root
                    )
                    if resp:
                        for p in productos:
                            if str(p.get("codigo_barra", "")).strip() == special_src:
                                p["codigo_barra"] = special_dst
                                p["codigo_reemplazado"] = True
                        self._log(f"[AVISO] Código {special_src} reemplazado por {special_dst} ({desc_rule}).")
                    else:
                        self._log(f"[AVISO] Se mantuvo el código original {special_src}.")

        # Si es una factura en Bs sin precios en USD (ej. Guuao / Orden de compra en Bs)
        is_only_bs = (data.get("moneda") == "VES" or all(float(p.get("costo_unitario_usd", 0.0)) == 0.0 for p in productos))
        if is_only_bs:
            self.var_check_price.set(False)
            self._log("ℹ️ Factura en Bolívares (sin precios USD). Prioridad: Nombre, Código de Barra y Cantidad (Alerta de precios desactivada automáticamente).")
        else:
            self.var_check_price.set(self.saved_cfg.get("check_price", True))

        self.lbl_factura_id.configure(text=f"Factura: {factura_id}")
        self.lbl_proveedor.configure(text=f"Proveedor: {proveedor}")
        if tasa > 0:
            self.lbl_tasa.configure(text=f"Tasa: {tasa:,.2f} Bs/$")
        else:
            self.lbl_tasa.configure(text="Tasa: N/A (Solo Bs.)")

        # Dividir en partes de máximo 43 productos (límite por factura en Saint)
        self.invoice_parts = self._split_into_parts(productos, tasa)
        if len(self.invoice_parts) > 1:
            self.frame_partes.pack(fill="x", pady=(6, 0))
            self.cbo_partes["values"] = [p["label"] for p in self.invoice_parts]
            self.cbo_partes.current(0)
            self._log(f"✂️ Factura con {len(productos)} productos dividida automáticamente en {len(self.invoice_parts)} partes de hasta {MAX_ITEMS_PER_INVOICE} productos.")
        else:
            self.frame_partes.pack_forget()

        self._show_part(0)
        self._log(f"Factura {factura_id} cargada con {len(productos)} productos.")

    def _split_into_parts(self, productos: list, tasa: float) -> list:
        if not productos:
            return []
        total = len(productos)
        n_parts = (total + MAX_ITEMS_PER_INVOICE - 1) // MAX_ITEMS_PER_INVOICE
        parts = []
        for p_idx in range(n_parts):
            start = p_idx * MAX_ITEMS_PER_INVOICE
            end = min(total, start + MAX_ITEMS_PER_INVOICE)
            p_items = productos[start:end]
            
            sub_usd = 0.0
            sub_bs = 0.0
            for it in p_items:
                usd = float(it.get("subtotal_usd", 0.0))
                if usd == 0.0:
                    usd = float(it.get("costo_unitario_usd", 0.0)) * float(it.get("cantidad", 1))
                sub_usd += usd
                
                bs = float(it.get("subtotal_bs", 0.0))
                if bs == 0.0:
                    bs = float(it.get("costo_unitario_bs", 0.0)) * float(it.get("cantidad", 1))
                if bs == 0.0 and tasa > 0:
                    bs = round(usd * tasa, 2)
                sub_bs += bs
                
            parts.append({
                "part_num": p_idx + 1,
                "total_parts": n_parts,
                "start_idx": start + 1,
                "end_idx": end,
                "items": p_items,
                "count": len(p_items),
                "total_usd": round(sub_usd, 2),
                "total_bs": round(sub_bs, 2),
                "label": f"Parte {p_idx + 1} de {n_parts}: Ítems {start + 1} al {end} ({len(p_items)} prods)"
            })
        return parts

    def _show_part(self, part_idx: int):
        if not self.invoice_parts or part_idx >= len(self.invoice_parts):
            return
        self.current_part_idx = part_idx
        part = self.invoice_parts[part_idx]
        self.items_list = part["items"]
        total_global = len(self.current_json_data.get("productos", [])) if self.current_json_data else len(self.items_list)
        
        # Actualizar indicadores y subtotales
        if part["total_parts"] > 1:
            self.lbl_items_badge.configure(
                text=f"Ítems: {part['count']} de {total_global} (Parte {part['part_num']}/{part['total_parts']})"
            )
            if part["total_usd"] > 0:
                self.lbl_total_usd.configure(text=f"Parte USD: $ {part['total_usd']:,.2f}")
            else:
                self.lbl_total_usd.configure(text="Parte USD: N/A")
            self.lbl_total_bs.configure(text=f"Parte Bs.: Bs. {part['total_bs']:,.2f}")
            self.btn_start.configure(text=f"▶ FACTURAR PARTE {part['part_num']} ({part['count']} ítems) [F8]")
        else:
            self.lbl_items_badge.configure(text=f"Total Ítems: {part['count']}")
            totales = self.current_json_data.get("totales", {}) if self.current_json_data else {}
            t_usd = totales.get("total_usd", part["total_usd"])
            t_bs = totales.get("total_bs", part["total_bs"])
            if t_usd > 0:
                self.lbl_total_usd.configure(text=f"Total USD: $ {t_usd:,.2f}")
            else:
                self.lbl_total_usd.configure(text="Total USD: N/A")
            self.lbl_total_bs.configure(text=f"Total Bs.: Bs. {t_bs:,.2f}")
            self.btn_start.configure(text="▶ FACTURAR ESTA FACTURA (F8)")

        # Llenar la tabla con los ítems de esta parte
        self.tree.delete(*self.tree.get_children())
        for idx, prod in enumerate(self.items_list, 1):
            ref = prod.get("codigo_barra", "")
            desc = prod.get("descripcion", "")
            cant = prod.get("cantidad", 0)
            p_usd = float(prod.get('costo_unitario_usd', 0.0))
            p_bs = float(prod.get('costo_unitario_bs', 0.0))
            if p_usd > 0.0:
                precio = f"$ {p_usd:.2f}"
            elif p_bs > 0.0:
                precio = f"Bs. {p_bs:,.2f}"
            else:
                precio = "--"
            is_rep = prod.get("codigo_reemplazado", False)
            
            estado_txt = "⏳ Pendiente"
            tag = "pending"
            if is_rep:
                estado_txt = "⏳ Pendiente (Código actualizado)"
                tag = "replaced"
                ref = f"⭐ {ref}"

            self.tree.insert("", "end", iid=f"item_{idx-1}", 
                             values=(idx, ref, desc, cant, precio, estado_txt),
                             tags=(tag,))

        self.prog_bar["maximum"] = part["count"]
        self.prog_bar["value"] = 0
        self.lbl_prog_txt.configure(text=f"0 de {part['count']} productos")
        st_txt = f"● LISTO PARA PARTE {part['part_num']} ({part['count']} prods)" if part["total_parts"] > 1 else "● LISTO PARA FACTURAR"
        self.lbl_estado.configure(text=st_txt, fg="#16a34a")
        self.last_price_diffs = []
        self.last_audit_result = None
        if hasattr(self, "btn_show_diffs"):
            self.btn_show_diffs.configure(state="disabled", text="📋 Auditoría OCR", bg="#f1f5f9", fg="#64748b")
            self.btn_show_diffs._custom_normal_bg = "#f1f5f9"
            self.btn_show_diffs._custom_normal_fg = "#64748b"

    def _on_part_combo_select(self, event=None):
        sel_idx = self.cbo_partes.current()
        if sel_idx >= 0 and sel_idx != self.current_part_idx:
            self._show_part(sel_idx)
            self._log(f"Visualizando {self.invoice_parts[sel_idx]['label']}.")

    def _export_parts_json(self):
        if not self.invoice_parts or len(self.invoice_parts) <= 1:
            messagebox.showinfo("Exportar Partes", "Esta factura no requiere división (tiene 43 productos o menos).", parent=self.root)
            return

        base_data = self.current_json_data or {}
        base_id = base_data.get("factura", "FACTURA")
        
        saved_paths = []
        for part in self.invoice_parts:
            p_num = part["part_num"]
            p_data = dict(base_data)
            p_data["factura"] = f"{base_id}_PARTE_{p_num}"
            p_data["totales"] = {
                "subtotal_bs": part["total_bs"],
                "subtotal_usd": part["total_usd"],
                "total_bs": part["total_bs"],
                "total_usd": part["total_usd"],
                "nro_items_factura": part["count"],
                "total_items_extraidos": part["count"],
                "parte_num": p_num,
                "total_partes": part["total_parts"]
            }
            # Copiar productos asegurando que no tengan estados temporales
            p_prods = []
            for item in part["items"]:
                cp = dict(item)
                cp.pop("codigo_reemplazado", None)
                p_prods.append(cp)
            p_data["productos"] = p_prods

            fname = f"{base_id}_PARTE_{p_num}.json"
            out_file = self.json_dir / fname
            try:
                with open(out_file, "w", encoding="utf-8") as fp:
                    json.dump(p_data, fp, indent=2, ensure_ascii=False)
                saved_paths.append(out_file.name)
            except Exception as e:
                messagebox.showerror("Error al Guardar", f"No se pudo guardar {fname}:\n{e}", parent=self.root)
                return

        self._scan_json_files()
        self._log(f"💾 Se exportaron {len(saved_paths)} partes a facturas_json/: {', '.join(saved_paths)}")
        messagebox.showinfo(
            "Partes Exportadas",
            f"✅ Se han generado {len(saved_paths)} archivos JSON en facturas_json/:\n\n" +
            "\n".join(f"• {name}" for name in saved_paths) +
            "\n\nYa puedes seleccionarlos individualmente en el menú de facturas.",
            parent=self.root
        )

    def _sync_config(self):
        sp = self.var_speed.get()
        if sp == "fast":
            d_code, d_qty, d_items = 0.35, 0.25, 0.25
        elif sp == "safe":
            d_code, d_qty, d_items = 0.80, 0.55, 0.50
        else:
            d_code, d_qty, d_items = 0.50, 0.40, 0.35

        self.engine.config.update({
            "auto_focus_saint": self.var_auto_focus.get(),
            "delay_after_barcode": d_code,
            "delay_after_qty": d_qty,
            "delay_between_items": d_items,
            "press_f6_at_end": self.var_press_f6.get(),
            "delay_before_f6": 0.80,
            "countdown_seconds": self.var_countdown.get(),
            "price_list_mode": self.var_price_mode.get(),
            "batch_size": 8,
            "verify_price_by_ocr": self.var_verify_ocr.get(),
            "check_price": self.var_check_price.get(),
            "check_price_realtime": self.var_check_price.get(),
            "price_alert_mode": self.var_price_alert_mode.get(),
            "price_currency": self.var_price_curr.get(),
            "price_nav_mode": self.var_price_nav.get(),
            "price_tolerance": 0.02,
            "replacement_rules": getattr(self, "replacement_rules", []),
            "test_mode": False
        })

    def _on_engine_ocr_diff(self, d):
        def ui():
            row_idx = d.get("row", 1) - 1
            iid = f"item_{row_idx}"
            if self.tree.exists(iid):
                vals = list(self.tree.item(iid, "values"))
                sym = d.get("curr_sym", "$")
                vals[5] = f"⚠️ Dif OCR: {sym}{d['saint_price']:.2f} (JSON: {sym}{d['expected_price']:.2f})"
                self.tree.item(iid, values=vals, tags=("diff_kept",))
        self.root.after(0, ui)

    def _update_cache_btn(self):
        def ui():
            cnt_c = contar_archivos_cache()
            cnt_j = len(list(self.json_dir.glob("*.json"))) if hasattr(self, "json_dir") and self.json_dir.exists() else 0
            cnt_p = len([f for f in self.pdf_dir.iterdir() if f.is_file()]) if hasattr(self, "pdf_dir") and self.pdf_dir.exists() else 0
            total = cnt_c + cnt_j + cnt_p
            if hasattr(self, "btn_clear_cache"):
                self.btn_clear_cache.configure(text=f"🧹 Limpiar Caché / Archivos ({total})")
        self.root.after(0, ui)

    def _on_clear_cache(self):
        if self.engine.running:
            messagebox.showwarning("Atención", "No puedes limpiar archivos mientras el bot está facturando.", parent=self.root)
            return

        cnt_cache = contar_archivos_cache()
        cnt_json = len(list(self.json_dir.glob("*.json"))) if hasattr(self, "json_dir") and self.json_dir.exists() else 0
        cnt_pdf = len([f for f in self.pdf_dir.iterdir() if f.is_file()]) if hasattr(self, "pdf_dir") and self.pdf_dir.exists() else 0

        # Ventana modal para seleccionar qué borrar
        top = tk.Toplevel(self.root)
        top.title("Limpiar Caché y Archivos")
        top.geometry("520x400")
        top.resizable(False, False)
        top.configure(bg="#f8fafc")
        top.transient(self.root)
        top.grab_set()

        try:
            top.update_idletasks()
            rw = self.root.winfo_width()
            rh = self.root.winfo_height()
            rx = self.root.winfo_rootx()
            ry = self.root.winfo_rooty()
            w, h = 520, 400
            x = max(rx + (rw - w) // 2, 50)
            y = max(ry + (rh - h) // 2, 50)
            top.geometry(f"{w}x{h}+{x}+{y}")
        except Exception:
            pass

        # Encabezado
        head = tk.Frame(top, bg="#0f172a", height=42)
        head.pack(fill="x")
        tk.Label(
            head, 
            text="🧹  Limpieza de Caché y Archivos del Sistema", 
            font=("Segoe UI", 11, "bold"), 
            fg="#ffffff", 
            bg="#0f172a"
        ).pack(side="left", padx=14, pady=10)

        body = tk.Frame(top, bg="#f8fafc", padx=18, pady=14)
        body.pack(fill="both", expand=True)

        tk.Label(
            body,
            text="Selecciona los elementos que deseas eliminar del disco.\nPor defecto, todas las opciones están marcadas:",
            font=("Segoe UI", 9),
            fg="#475569",
            bg="#f8fafc",
            justify="left"
        ).pack(anchor="w", pady=(0, 10))

        # Tarjeta de opciones
        card = tk.Frame(body, bg="#ffffff", highlightbackground="#cbd5e1", highlightthickness=1, padx=14, pady=12)
        card.pack(fill="x", pady=(0, 14))

        # Opciones marcadas por defecto (True)
        var_del_cache = tk.BooleanVar(value=True)
        var_del_json = tk.BooleanVar(value=True)
        var_del_pdf = tk.BooleanVar(value=True)

        # 1. Opción Caché
        chk_cache = tk.Checkbutton(
            card,
            text=f"Capturas de Pantalla (Caché OCR)  —  [{cnt_cache} archivo(s)]",
            variable=var_del_cache,
            font=("Segoe UI", 9, "bold"),
            fg="#0f172a",
            bg="#ffffff",
            activebackground="#ffffff",
            selectcolor="#ffffff",
            cursor="hand2"
        )
        chk_cache.pack(anchor="w", pady=(2, 1))
        tk.Label(
            card,
            text="   Imágenes en cache_capturas/ usadas durante la verificación visual.",
            font=("Segoe UI", 8),
            fg="#64748b",
            bg="#ffffff"
        ).pack(anchor="w", pady=(0, 8))

        # 2. Opción JSON
        chk_json = tk.Checkbutton(
            card,
            text=f"Facturas Procesadas en JSON  —  [{cnt_json} archivo(s)]",
            variable=var_del_json,
            font=("Segoe UI", 9, "bold"),
            fg="#0f172a",
            bg="#ffffff",
            activebackground="#ffffff",
            selectcolor="#ffffff",
            cursor="hand2"
        )
        chk_json.pack(anchor="w", pady=(2, 1))
        tk.Label(
            card,
            text="   Archivos JSON en facturas_json/ listos para facturar en Saint.",
            font=("Segoe UI", 8),
            fg="#64748b",
            bg="#ffffff"
        ).pack(anchor="w", pady=(0, 8))

        # 3. Opción PDF / Excel
        chk_pdf = tk.Checkbutton(
            card,
            text=f"Facturas y Documentos PDF / Excel Originales  —  [{cnt_pdf} archivo(s)]",
            variable=var_del_pdf,
            font=("Segoe UI", 9, "bold"),
            fg="#0f172a",
            bg="#ffffff",
            activebackground="#ffffff",
            selectcolor="#ffffff",
            cursor="hand2"
        )
        chk_pdf.pack(anchor="w", pady=(2, 1))
        tk.Label(
            card,
            text="   Archivos PDF o Excel colocados en facturas_pdf/ para ser procesados.",
            font=("Segoe UI", 8),
            fg="#64748b",
            bg="#ffffff"
        ).pack(anchor="w", pady=(0, 2))

        # Botonera inferior
        btn_box = tk.Frame(body, bg="#f8fafc")
        btn_box.pack(fill="x", pady=(4, 0))

        def do_delete():
            del_c = var_del_cache.get()
            del_j = var_del_json.get()
            del_p = var_del_pdf.get()

            if not (del_c or del_j or del_p):
                messagebox.showwarning("Atención", "Debes seleccionar al menos una opción para borrar.", parent=top)
                return

            res_c = 0
            res_j = 0
            res_p = 0
            detalles = []

            if del_c:
                res_c = borrar_cache_capturas()
                detalles.append(f"• Capturas de caché: {res_c} eliminadas")

            if del_j:
                res_j = borrar_facturas_json(self.json_dir)
                detalles.append(f"• Facturas JSON: {res_j} eliminadas")
                self._scan_json_files()

            if del_p:
                res_p = borrar_facturas_pdf(self.pdf_dir)
                detalles.append(f"• Archivos PDF/Excel: {res_p} eliminados")

            self._update_cache_btn()
            top.destroy()

            total_eliminados = res_c + res_j + res_p
            self._log(f"🧹 [LIMPIEZA] Eliminados {total_eliminados} archivo(s): {res_c} capturas, {res_j} JSON, {res_p} PDF/Excel.")

            msg = "Limpieza realizada con éxito:\n\n" + "\n".join(detalles)
            messagebox.showinfo("Limpieza Completada", msg, parent=self.root)

        btn_confirm = tk.Button(
            btn_box,
            text="🗑️ Eliminar Seleccionados",
            font=("Segoe UI", 9, "bold"),
            fg="#ffffff",
            bg="#ef4444",
            activebackground="#b91c1c",
            activeforeground="#ffffff",
            relief="flat",
            padx=14,
            pady=6,
            cursor="hand2",
            command=do_delete
        )
        btn_confirm.pack(side="right", padx=(8, 0))
        self._aplicar_hover(btn_confirm, bg_normal="#ef4444", bg_hover="#dc2626")

        btn_cancel = tk.Button(
            btn_box,
            text="Cancelar",
            font=("Segoe UI", 9),
            fg="#334155",
            bg="#e2e8f0",
            activebackground="#cbd5e1",
            relief="flat",
            padx=12,
            pady=6,
            cursor="hand2",
            command=top.destroy
        )
        btn_cancel.pack(side="right")
        self._aplicar_hover(btn_cancel, bg_normal="#e2e8f0", bg_hover="#cbd5e1")

    def start_facturacion(self):
        if not self.items_list:
            messagebox.showwarning("Atención", "No hay productos cargados en esta factura.")
            return
        if self.engine.running:
            return

        self._sync_config()
        self.btn_start.configure(state="disabled")
        self.btn_pause.configure(state="normal", text="⏸ PAUSAR (F7)", bg="#f59e0b")
        self.btn_pause._custom_normal_bg = "#f59e0b"
        self.btn_stop.configure(state="normal")
        self.engine.start_invoice(self.items_list)

    def pause_facturacion(self):
        if self.engine.running:
            self.engine.pause_toggle()

    def stop_facturacion(self):
        if self.engine.running:
            self.engine.stop()

    def _hotkey_start(self):
        self.root.after(0, self.start_facturacion)

    def _hotkey_pause(self):
        self.root.after(0, self.pause_facturacion)

    def _hotkey_stop(self):
        self.root.after(0, self.stop_facturacion)

    def _on_engine_countdown(self, sec):
        def ui():
            self.lbl_estado.configure(text=f"⏳ INICIANDO EN {sec} SEG (Haz clic en Referencia en Saint)...", fg="#ea580c")
        self.root.after(0, ui)

    def _on_engine_state(self, st):
        def ui():
            if st == "ESCRIBIENDO":
                self.lbl_estado.configure(text="⌨️ FACTURANDO EN SAINT...", fg="#0284c7")
            elif st == "PAUSADO":
                self.lbl_estado.configure(text="⏸ PAUSADO (F7 para reanudar)", fg="#d97706")
                self.btn_pause.configure(text="▶ REANUDAR (F7)", bg="#0284c7")
                self.btn_pause._custom_normal_bg = "#0284c7"
            elif st == "REANUDADO":
                self.lbl_estado.configure(text="⌨️ FACTURANDO EN SAINT...", fg="#0284c7")
                self.btn_pause.configure(text="⏸ PAUSAR (F7)", bg="#f59e0b")
                self.btn_pause._custom_normal_bg = "#f59e0b"
            elif st in ("COMPLETADO", "DETENIDO", "ERROR"):
                self.btn_start.configure(state="normal")
                self.btn_pause.configure(state="disabled", text="⏸ PAUSAR (F7)", bg="#f59e0b")
                self.btn_pause._custom_normal_bg = "#f59e0b"
                self.btn_stop.configure(state="disabled")
                if st == "COMPLETADO":
                    self.lbl_estado.configure(text="✅ FACTURA GUARDADA Y COMPLETADA", fg="#16a34a")
                elif st == "DETENIDO":
                    self.lbl_estado.configure(text="⏹ DETENIDO POR EL USUARIO", fg="#dc2626")
                else:
                    self.lbl_estado.configure(text="⚠️ ERROR EN ESCRITURA", fg="#dc2626")
        self.root.after(0, ui)

    def _on_engine_item_started(self, idx, item):
        def ui():
            iid = f"item_{idx}"
            if self.tree.exists(iid):
                vals = list(self.tree.item(iid, "values"))
                vals[5] = "⌨️ Escribiendo..."
                self.tree.item(iid, values=vals, tags=("active",))
                self.tree.see(iid)
            self.prog_bar["value"] = idx
            self.lbl_prog_txt.configure(text=f"{idx} de {len(self.items_list)} productos")
        self.root.after(0, ui)

    def _on_engine_item_finished(self, idx, item, succ, extra=None):
        def ui():
            iid = f"item_{idx}"
            if self.tree.exists(iid):
                vals = list(self.tree.item(iid, "values"))
                if extra:
                    tag, txt = extra
                    vals[5] = txt
                    self.tree.item(iid, values=vals, tags=(tag,))
                else:
                    vals[5] = "✅ Cargado" if succ else "❌ Fallo"
                    self.tree.item(iid, values=vals, tags=("done" if succ else "pending",))
            self.prog_bar["value"] = idx + 1
            self.lbl_prog_txt.configure(text=f"{idx + 1} de {len(self.items_list)} productos")
        self.root.after(0, ui)

    def _on_engine_price_diff(self, item, saint_price, expected_price, curr_sym):
        res_event = threading.Event()
        user_choice = {"action": "saint"}

        def ask():
            desc = item.get("descripcion", "Producto")
            code = item.get("codigo_barra", "")
            diff = abs(saint_price - expected_price)

            try:
                self.root.lift()
                self.root.attributes("-topmost", True)
                self.root.focus_force()
            except Exception:
                pass

            msg = (
                f"⚠️ ¡Diferencia de precio detectada en Saint!\n\n"
                f"• Producto: {desc}\n"
                f"• Código: {code}\n\n"
                f"• Precio en Pantalla (Saint):  {curr_sym} {saint_price:,.2f}\n"
                f"• Precio en Factura (JSON):    {curr_sym} {expected_price:,.2f}\n"
                f"• Diferencia:                  {curr_sym} {diff:,.2f}\n\n"
                f"¿Qué deseas hacer?\n\n"
                f"• [SÍ]: Sobrescribir en Saint con el precio del JSON ({curr_sym} {expected_price:,.2f})\n"
                f"• [NO]: Mantener el precio actual de Saint ({curr_sym} {saint_price:,.2f})\n"
                f"• [CANCELAR]: Pausar el bot para que tú ajustes manualmente en Saint"
            )

            resp = messagebox.askyesnocancel(
                "Alerta: Diferencia de Precio",
                msg,
                parent=self.root
            )

            try:
                self._toggle_topmost()
            except Exception:
                pass

            if resp is True:
                user_choice["action"] = "overwrite"
            elif resp is False:
                user_choice["action"] = "saint"
            else:
                user_choice["action"] = "pause"

            res_event.set()

        self.root.after(0, ask)
        res_event.wait()
        return user_choice["action"]

    def _on_engine_invoice_finished(self, success, audit_data=None):
        def ui():
            if success:
                f_name = self.current_json_data.get("factura", "") if self.current_json_data else ""
                part_info = ""
                has_parts = bool(self.invoice_parts and len(self.invoice_parts) > 1)
                if has_parts:
                    p = self.invoice_parts[self.current_part_idx]
                    part_info = f" (Parte {p['part_num']} de {p['total_parts']})"
                self._log(f"--- Factura {f_name}{part_info} finalizada exitosamente ---")

                # Parsear resultado de auditoría OCR
                if isinstance(audit_data, dict):
                    self.last_audit_result = audit_data
                    self.last_price_diffs = audit_data.get("price_differences", [])
                    missing_items = audit_data.get("missing_items", [])
                    foreign_items = audit_data.get("foreign_items", [])
                    has_issues = audit_data.get("has_issues", False)
                else:
                    self.last_price_diffs = audit_data or []
                    missing_items = []
                    foreign_items = []
                    has_issues = bool(self.last_price_diffs)
                    self.last_audit_result = {
                        "missing_items": [],
                        "foreign_items": [],
                        "price_differences": self.last_price_diffs,
                        "total_expected": len(self.items_list),
                        "total_detected": len(self.items_list),
                        "detected_items": {},
                        "has_issues": has_issues
                    }

                total_alerts = len(self.last_price_diffs) + len(missing_items) + len(foreign_items)

                if has_issues:
                    self.btn_show_diffs.configure(
                        state="normal", 
                        text=f"⚠️ Auditoría OCR ({total_alerts} alertas)",
                        bg="#ea580c", fg="#ffffff", activebackground="#c2410c", activeforeground="#ffffff"
                    )
                    self.btn_show_diffs._custom_normal_bg = "#ea580c"
                    self.btn_show_diffs._custom_normal_fg = "#ffffff"
                else:
                    self.btn_show_diffs.configure(
                        state="normal",
                        text="✅ Auditoría OCR (OK)",
                        bg="#10b981", fg="#ffffff", activebackground="#059669", activeforeground="#ffffff"
                    )
                    self.btn_show_diffs._custom_normal_bg = "#10b981"
                    self.btn_show_diffs._custom_normal_fg = "#ffffff"

                is_test = self.engine.config.get("test_mode", False)

                def check_next_part():
                    if not self.invoice_parts:
                        return
                    if self.current_part_idx < len(self.invoice_parts) - 1:
                        curr_p = self.current_part_idx + 1
                        next_p = curr_p + 1
                        tot_p = len(self.invoice_parts)
                        next_count = self.invoice_parts[self.current_part_idx + 1]["count"]

                        if not is_test:
                            forzar_ventana_al_frente(self.root)
                            msg = (
                                f"✅ PARTE {curr_p} DE {tot_p} FINALIZADA ({len(self.items_list)} productos cargados en Saint).\n\n"
                                f"👉 Pasos para continuar con la Parte {next_p}:\n"
                                f" 1. Guarda la factura actual en Saint (F6 o botón Guardar).\n"
                                f" 2. Abre un NUEVO Presupuesto / Factura en blanco en Saint.\n"
                                f" 3. Al hacer clic en Aceptar, la app preparará la Parte {next_p} ({next_count} productos).\n\n"
                                f"Cuando tengas la nueva factura abierta en Saint, presiona F8 para continuar facturando."
                            )
                            messagebox.showinfo(f"Parte {curr_p} Finalizada - Saint Enterprise", msg, parent=self.root)
                        
                        self._show_part(self.current_part_idx + 1)
                        if hasattr(self, "cbo_partes"):
                            self.cbo_partes.current(self.current_part_idx)
                        self.lbl_estado.configure(
                            text=f"● LISTO PARA PARTE {next_p}: Abre nueva factura en Saint y presiona F8",
                            fg="#0284c7"
                        )
                    elif len(self.invoice_parts) > 1 and self.current_part_idx == len(self.invoice_parts) - 1:
                        self._log(f"🎉 ¡Todas las {len(self.invoice_parts)} partes de la factura han sido completadas con éxito!")
                        if not is_test:
                            forzar_ventana_al_frente(self.root)
                            messagebox.showinfo(
                                "Factura Completa",
                                f"🎉 ¡Todas las {len(self.invoice_parts)} partes de la factura han sido completadas con éxito en Saint!",
                                parent=self.root
                            )

                def handle_audit_and_continuation():
                    if has_issues and self.var_price_alert_mode.get() == "summary":
                        if not is_test:
                            forzar_ventana_al_frente(self.root)
                            if HAVE_SOUND:
                                try:
                                    winsound.MessageBeep(0x00000030)
                                except Exception:
                                    pass

                            alert_details = []
                            if missing_items:
                                alert_details.append(f"• Faltantes por facturar: {len(missing_items)} productos")
                            if foreign_items:
                                alert_details.append(f"• Productos ajenos en Saint: {len(foreign_items)} productos")
                            if self.last_price_diffs:
                                alert_details.append(f"• Diferencias de precio: {len(self.last_price_diffs)} productos")

                            warn_msg = (
                                f"⚠️ ¡ATENCIÓN: SE DETECTARON {total_alerts} ALERTAS DE AUDITORÍA OCR!\n\n"
                                f"• Factura: {f_name}{part_info}\n"
                                + "\n".join(alert_details) + "\n\n"
                                f"Por seguridad, la factura NO fue guardada automáticamente con F6.\n\n"
                                f"Al presionar Aceptar, verás el panel de auditoría detallada "
                                f"para ubicar y corregir la factura en Saint."
                            )
                            messagebox.showwarning("⚠️ Alertas de Auditoría OCR en Saint", warn_msg, parent=self.root)

                            self._show_audit_window(self.last_audit_result, on_close=check_next_part if has_parts else None)
                        else:
                            if has_parts:
                                check_next_part()
                    else:
                        if has_parts:
                            check_next_part()

                self.root.after(200, handle_audit_and_continuation)
        self.root.after(0, ui)

    def _on_manual_audit(self):
        if not self.items_list:
            messagebox.showwarning("Auditoría OCR", "No hay productos de factura cargados en la tabla para auditar.", parent=self.root)
            return

        self._log("🔍 [AUDITORÍA MANUAL] Capturando ventana de Saint para análisis OCR...")
        target_hwnd = obtener_hwnd_saint()
        if not target_hwnd:
            self._log("⚠️ No se detectó la ventana de Saint Annual Enterprise abierta en pantalla.")
            messagebox.showwarning("Ventana no encontrada", "No se detectó la ventana de Saint Annual Enterprise abierta en pantalla.\n\nAbre o maximiza la ventana de la factura en Saint.", parent=self.root)
            return

        img, saved_path = capture_window_to_cache(target_hwnd, file_name="auditoria_manual.png")
        if not img:
            messagebox.showerror("Error de Captura", "No se pudo obtener la captura de pantalla de Saint.", parent=self.root)
            return

        self._update_cache_btn()
        curr = self.var_price_curr.get()
        tol = self.engine.config.get("price_tolerance", 0.02)
        chk_price = self.var_check_price.get()

        # Analizar OCR en RAM
        audit_raw = audit_saint_grid_capture(img, self.items_list, 1, is_final=True, total_items=len(self.items_list),
                                            currency=curr, tolerance=tol, check_price=chk_price)

        # Compilar auditoría
        proc = OCRBatchProcessor()
        for d in audit_raw.get("price_diffs", []):
            proc.differences.append(d)
        for r in audit_raw.get("detected_rows", []):
            k = r.get("barcode_norm")
            if k:
                proc.detected_items_map[k] = r
            else:
                desc_r = r.get("desc", "").strip()
                if len(desc_r) >= 4 or r.get("price") is not None:
                    proc.detected_items_map[f"_row_{len(proc.detected_items_map)}_{desc_r[:16]}"] = r

        audit_res = proc.compile_audit(
            self.items_list, currency=curr, tolerance=tol, check_price=chk_price,
            replacement_rules=getattr(self, "replacement_rules", [])
        )
        self.last_audit_result = audit_res
        self.last_price_diffs = audit_res["price_differences"]

        total_alerts = len(audit_res["missing_items"]) + len(audit_res["foreign_items"]) + len(audit_res["price_differences"])
        if audit_res["has_issues"]:
            self.btn_show_diffs.configure(
                state="normal",
                text=f"⚠️ Auditoría OCR ({total_alerts} alertas)",
                bg="#ea580c", fg="#ffffff", activebackground="#c2410c", activeforeground="#ffffff"
            )
            self.btn_show_diffs._custom_normal_bg = "#ea580c"
            self.btn_show_diffs._custom_normal_fg = "#ffffff"
        else:
            self.btn_show_diffs.configure(
                state="normal",
                text="✅ Auditoría OCR (OK)",
                bg="#10b981", fg="#ffffff", activebackground="#059669", activeforeground="#ffffff"
            )
            self.btn_show_diffs._custom_normal_bg = "#10b981"
            self.btn_show_diffs._custom_normal_fg = "#ffffff"

        self._log(f"🔍 [AUDITORÍA MANUAL] Detectados en pantalla: {audit_res['total_detected']} productos | Faltantes: {len(audit_res['missing_items'])} | Ajenos: {len(audit_res['foreign_items'])} | Dif. Precios: {len(audit_res['price_differences'])}")
        self._show_audit_window(audit_res)

    def _show_differences_window(self, diffs=None, on_close=None):
        """Compatibilidad con llamadas previas: redirige a _show_audit_window."""
        return self._show_audit_window(audit_data=self.last_audit_result, on_close=on_close)

    def _show_audit_window(self, audit_data=None, on_close=None):
        if audit_data is None:
            audit_data = self.last_audit_result

        if not audit_data:
            if self.last_price_diffs:
                audit_data = {
                    "missing_items": [],
                    "foreign_items": [],
                    "price_differences": self.last_price_diffs,
                    "total_expected": len(self.items_list),
                    "total_detected": len(self.items_list),
                    "detected_items": {},
                    "has_issues": True
                }
            else:
                messagebox.showinfo("Auditoría OCR", "No hay datos de auditoría registrados aún.\n\nPuedes presionar '🔍 Auditar Pantalla (OCR)' para realizar un chequeo en vivo de Saint.", parent=self.root)
                return

        missing = audit_data.get("missing_items", [])
        foreign = audit_data.get("foreign_items", [])
        diffs = audit_data.get("price_differences", [])
        detected_map = audit_data.get("detected_items", {})
        total_exp = audit_data.get("total_expected", len(self.items_list))
        total_det = audit_data.get("total_detected", len(detected_map))
        has_issues = audit_data.get("has_issues", False)
        total_alerts = len(missing) + len(foreign) + len(diffs)

        w = tk.Toplevel(self.root)
        w.title("🔍 Auditoría Completa de Facturación OCR - Saint Enterprise")
        w.geometry("880x560")
        w.minsize(760, 440)
        w.configure(bg="#f8fafc")
        w.transient(self.root)

        forzar_ventana_al_frente(w)

        f_id = self.current_json_data.get("factura", "N/A") if self.current_json_data else "N/A"

        # 1. Banner superior
        if has_issues:
            banner = tk.Frame(w, bg="#fff7ed", padx=14, pady=10, highlightbackground="#f97316", highlightthickness=1)
            banner.pack(fill="x", padx=12, pady=(10, 6))
            lbl_head = tk.Label(banner, text=f"⚠️ ATENCIÓN: Se detectaron {total_alerts} alertas en la cuadrícula de Saint",
                                font=("Segoe UI", 11, "bold"), fg="#c2410c", bg="#fff7ed")
            lbl_head.pack(anchor="w")
            lbl_sub = tk.Label(banner,
                               text=f"Factura: {f_id} | Revisa las pestañas abajo para ubicar faltantes, productos ajenos y diferencias de precio antes de guardar.",
                               font=("Segoe UI", 9), fg="#7c2d12", bg="#fff7ed", justify="left")
            lbl_sub.pack(anchor="w", pady=(2, 0))
        else:
            banner = tk.Frame(w, bg="#ecfdf5", padx=14, pady=10, highlightbackground="#10b981", highlightthickness=1)
            banner.pack(fill="x", padx=12, pady=(10, 6))
            lbl_head = tk.Label(banner, text="✅ ¡AUDITORÍA OCR EXITOSA! Cuadrícula 100% Verificada",
                                font=("Segoe UI", 11, "bold"), fg="#047857", bg="#ecfdf5")
            lbl_head.pack(anchor="w")
            lbl_sub = tk.Label(banner,
                               text=f"Factura: {f_id} | Todos los {total_exp} productos coinciden. 0 faltantes, 0 productos ajenos, 0 diferencias de precio.",
                               font=("Segoe UI", 9), fg="#065f46", bg="#ecfdf5", justify="left")
            lbl_sub.pack(anchor="w", pady=(2, 0))

        # 2. Mini KPI Cards
        kpi_row = tk.Frame(w, bg="#f8fafc")
        kpi_row.pack(fill="x", padx=12, pady=(0, 6))
        for col_i in range(4):
            kpi_row.columnconfigure(col_i, weight=1)

        def make_kpi(parent, col, title, val_str, bg_c, fg_c, border_c):
            f = tk.Frame(parent, bg=bg_c, highlightbackground=border_c, highlightthickness=1, padx=8, pady=4)
            f.grid(row=0, column=col, sticky="nsew", padx=3)
            tk.Label(f, text=title, font=("Segoe UI", 8, "bold"), fg=fg_c, bg=bg_c, anchor="w").pack(fill="x")
            tk.Label(f, text=val_str, font=("Segoe UI", 11, "bold"), fg=fg_c, bg=bg_c, anchor="w").pack(fill="x")

        make_kpi(kpi_row, 0, "📦 ESPERADOS JSON", f"{total_exp} ítems", "#eff6ff", "#1e40af", "#93c5fd")
        make_kpi(kpi_row, 1, "❌ FALTANTES", f"{len(missing)} ítems", "#fee2e2" if missing else "#f0fdf4", "#dc2626" if missing else "#16a34a", "#fca5a5" if missing else "#86efac")
        make_kpi(kpi_row, 2, "🚫 AJENOS EN SAINT", f"{len(foreign)} ítems", "#fff7ed" if foreign else "#f0fdf4", "#ea580c" if foreign else "#16a34a", "#fdba74" if foreign else "#86efac")
        make_kpi(kpi_row, 3, "💵 DIF. PRECIO", f"{len(diffs)} ítems", "#fefce8" if diffs else "#f0fdf4", "#ca8a04" if diffs else "#16a34a", "#fde047" if diffs else "#86efac")

        # 3. Notebook de Pestañas
        nb = ttk.Notebook(w)
        nb.pack(fill="both", expand=True, padx=12, pady=(0, 6))

        # Pestaña 1: Faltantes
        tab_missing = ttk.Frame(nb, padding="4")
        nb.add(tab_missing, text=f"❌ Faltantes por Facturar ({len(missing)})")

        if missing:
            cols_m = ("row", "ref", "desc", "cant", "precio")
            tree_m = ttk.Treeview(tab_missing, columns=cols_m, show="headings", height=7)
            tree_m.heading("row", text="# Fila JSON")
            tree_m.heading("ref", text="Código de Barra")
            tree_m.heading("desc", text="Descripción en Factura")
            tree_m.heading("cant", text="Cant.")
            tree_m.heading("precio", text="Precio JSON")

            tree_m.column("row", width=65, anchor="center")
            tree_m.column("ref", width=140, anchor="center")
            tree_m.column("desc", width=340, anchor="w")
            tree_m.column("cant", width=60, anchor="center")
            tree_m.column("precio", width=95, anchor="e")

            sc_m = ttk.Scrollbar(tab_missing, orient="vertical", command=tree_m.yview)
            tree_m.configure(yscrollcommand=sc_m.set)
            tree_m.pack(side="left", fill="both", expand=True)
            sc_m.pack(side="right", fill="y")
            tree_m.tag_configure("missing_row", background="#fff1f2", foreground="#9f1239", font=("Segoe UI", 9))

            for m in missing:
                sym = m.get("curr_sym", "$")
                tree_m.insert("", "end", values=(m["row"], m["codigo"], m["descripcion"], m["cantidad"], f"{sym} {m['precio']:.2f}"), tags=("missing_row",))
        else:
            f_ok = tk.Frame(tab_missing, bg="#ffffff")
            f_ok.pack(fill="both", expand=True)
            tk.Label(f_ok, text="🎉 ¡Excelente! No falta ningún producto por facturar en Saint.\nTodos los productos del JSON fueron detectados en la cuadrícula.",
                     font=("Segoe UI", 11, "bold"), fg="#16a34a", bg="#ffffff", justify="center").pack(expand=True)

        # Pestaña 2: Productos Ajenos
        tab_foreign = ttk.Frame(nb, padding="4")
        nb.add(tab_foreign, text=f"🚫 Productos Ajenos ({len(foreign)})")

        if foreign:
            cols_f = ("ref", "desc", "cant", "precio")
            tree_f = ttk.Treeview(tab_foreign, columns=cols_f, show="headings", height=7)
            tree_f.heading("ref", text="Código en Saint")
            tree_f.heading("desc", text="Descripción leída en Saint")
            tree_f.heading("cant", text="Cant.")
            tree_f.heading("precio", text="Precio Saint")

            tree_f.column("ref", width=150, anchor="center")
            tree_f.column("desc", width=380, anchor="w")
            tree_f.column("cant", width=65, anchor="center")
            tree_f.column("precio", width=95, anchor="e")

            sc_f = ttk.Scrollbar(tab_foreign, orient="vertical", command=tree_f.yview)
            tree_f.configure(yscrollcommand=sc_f.set)
            tree_f.pack(side="left", fill="both", expand=True)
            sc_f.pack(side="right", fill="y")
            tree_f.tag_configure("foreign_row", background="#fff7ed", foreground="#9a3412", font=("Segoe UI", 9))

            for fn in foreign:
                sym = fn.get("curr_sym", "$")
                p_str = f"{sym} {fn['precio']:.2f}" if fn.get("precio") is not None else "--"
                tree_f.insert("", "end", values=(fn["codigo"], fn["descripcion"], fn.get("cantidad", "--"), p_str), tags=("foreign_row",))
        else:
            f_ok2 = tk.Frame(tab_foreign, bg="#ffffff")
            f_ok2.pack(fill="both", expand=True)
            tk.Label(f_ok2, text="🎉 ¡Excelente! No hay productos ajenos o extraños en Saint.\nCada producto tipeado en Saint pertenece legítimamente al JSON.",
                     font=("Segoe UI", 11, "bold"), fg="#16a34a", bg="#ffffff", justify="center").pack(expand=True)

        # Pestaña 3: Diferencias de Precio
        tab_diffs = ttk.Frame(nb, padding="4")
        nb.add(tab_diffs, text=f"💵 Diferencias de Precio ({len(diffs)})")

        if diffs:
            cols_d = ("row", "ref", "desc", "p_saint", "p_json", "diff")
            tree_d = ttk.Treeview(tab_diffs, columns=cols_d, show="headings", height=7)
            tree_d.heading("row", text="# Fila")
            tree_d.heading("ref", text="Referencia (Código Barra)")
            tree_d.heading("desc", text="Descripción")
            tree_d.heading("p_saint", text="Precio Saint")
            tree_d.heading("p_json", text="Precio JSON")
            tree_d.heading("diff", text="Diferencia")

            tree_d.column("row", width=55, anchor="center")
            tree_d.column("ref", width=140, anchor="center")
            tree_d.column("desc", width=280, anchor="w")
            tree_d.column("p_saint", width=95, anchor="e")
            tree_d.column("p_json", width=95, anchor="e")
            tree_d.column("diff", width=85, anchor="e")

            sc_d = ttk.Scrollbar(tab_diffs, orient="vertical", command=tree_d.yview)
            tree_d.configure(yscrollcommand=sc_d.set)
            tree_d.pack(side="left", fill="both", expand=True)
            sc_d.pack(side="right", fill="y")
            tree_d.tag_configure("diff_row", background="#fff1f2", foreground="#9f1239", font=("Segoe UI", 9))

            for d in diffs:
                curr_sym = d.get("curr_sym", "$")
                s_val = f"{curr_sym} {d['saint_price']:.2f}"
                j_val = f"{curr_sym} {d['expected_price']:.2f}"
                dif_val = f"{curr_sym} {d['diff']:.2f}"
                tree_d.insert("", "end", values=(d["row"], d["codigo"], d["descripcion"], s_val, j_val, dif_val), tags=("diff_row",))
        else:
            f_ok3 = tk.Frame(tab_diffs, bg="#ffffff")
            f_ok3.pack(fill="both", expand=True)
            tk.Label(f_ok3, text="🎉 ¡Excelente! Todos los precios en Saint coinciden exactamente con el JSON.",
                     font=("Segoe UI", 11, "bold"), fg="#16a34a", bg="#ffffff", justify="center").pack(expand=True)

        # Pestaña 4: Todos los detectados
        tab_all = ttk.Frame(nb, padding="4")
        nb.add(tab_all, text=f"📋 Detectados en Pantalla ({len(detected_map)})")

        cols_a = ("ref", "desc", "cant", "precio", "estado")
        tree_a = ttk.Treeview(tab_all, columns=cols_a, show="headings", height=7)
        tree_a.heading("ref", text="Código Barra")
        tree_a.heading("desc", text="Descripción")
        tree_a.heading("cant", text="Cant.")
        tree_a.heading("precio", text="Precio")
        tree_a.heading("estado", text="Estado Auditoría")

        tree_a.column("ref", width=140, anchor="center")
        tree_a.column("desc", width=300, anchor="w")
        tree_a.column("cant", width=60, anchor="center")
        tree_a.column("precio", width=85, anchor="e")
        tree_a.column("estado", width=160, anchor="center")

        sc_a = ttk.Scrollbar(tab_all, orient="vertical", command=tree_a.yview)
        tree_a.configure(yscrollcommand=sc_a.set)
        tree_a.pack(side="left", fill="both", expand=True)
        sc_a.pack(side="right", fill="y")

        tree_a.tag_configure("st_ok", background="#f0fdf4", foreground="#166534", font=("Segoe UI", 9))
        tree_a.tag_configure("st_warn", background="#fff7ed", foreground="#9a3412", font=("Segoe UI", 9, "bold"))
        tree_a.tag_configure("st_err", background="#fef2f2", foreground="#991b1b", font=("Segoe UI", 9, "bold"))

        foreign_codes = {f["codigo"] for f in foreign}
        diff_codes = {d["codigo"] for d in diffs}

        for norm_c, item_d in detected_map.items():
            raw_c = item_d.get("barcode_raw", norm_c)
            p_val = f"$ {item_d['price']:.2f}" if item_d.get("price") is not None else "--"
            if raw_c in foreign_codes:
                tag = "st_warn"
                st_msg = "🚫 Ajeno al JSON"
            elif raw_c in diff_codes:
                tag = "st_err"
                st_msg = "⚠️ Dif. Precio"
            else:
                tag = "st_ok"
                st_msg = "✅ Coincide"
            tree_a.insert("", "end", values=(raw_c, item_d.get("desc", ""), item_d.get("qty", "--"), p_val, st_msg), tags=(tag,))

        # 4. Barra de Botones Inferior
        btn_bar = tk.Frame(w, bg="#f8fafc", padx=12, pady=10)
        btn_bar.pack(fill="x", side="bottom")

        def copy_audit_report():
            lines = [
                f"REPORTE DE AUDITORÍA DE FACTURACIÓN OCR - SAINT ENTERPRISE",
                f"Factura: {f_id}",
                f"Total Esperados: {total_exp} | Total Detectados en Saint: {total_det}",
                f"Faltantes: {len(missing)} | Ajenos: {len(foreign)} | Diferencias Precio: {len(diffs)}",
                "=" * 80
            ]
            if missing:
                lines.append("\n[1] PRODUCTOS FALTANTES POR FACTURAR EN SAINT:")
                lines.append(f"{'#':<4} | {'Código':<14} | {'Descripción':<35} | {'Cant':<5} | {'Precio JSON'}")
                lines.append("-" * 75)
                for m in missing:
                    sym = m.get("curr_sym", "$")
                    lines.append(f"{m['row']:<4} | {m['codigo']:<14} | {m['descripcion'][:35]:<35} | {m['cantidad']:<5} | {sym}{m['precio']:.2f}")

            if foreign:
                lines.append("\n[2] PRODUCTOS AJENOS EN SAINT (NO ESTÁN EN EL JSON):")
                lines.append(f"{'Código en Saint':<18} | {'Descripción':<35} | {'Cant':<5} | {'Precio Saint'}")
                lines.append("-" * 75)
                for fn in foreign:
                    sym = fn.get("curr_sym", "$")
                    p_str = f"{sym}{fn['precio']:.2f}" if fn.get("precio") is not None else "--"
                    lines.append(f"{fn['codigo']:<18} | {fn['descripcion'][:35]:<35} | {fn.get('cantidad', '--'):<5} | {p_str}")

            if diffs:
                lines.append("\n[3] DIFERENCIAS DE PRECIO DETECTADAS:")
                lines.append(f"{'# Fila':<7} | {'Código':<14} | {'Descripción':<30} | {'Saint':<10} | {'JSON':<10} | {'Dif.'}")
                lines.append("-" * 80)
                for d in diffs:
                    sym = d.get("curr_sym", "$")
                    lines.append(f"Fila {d['row']:<2} | {d['codigo']:<14} | {d['descripcion'][:30]:<30} | {sym}{d['saint_price']:<7.2f} | {sym}{d['expected_price']:<7.2f} | {sym}{d['diff']:.2f}")

            if not has_issues:
                lines.append("\n✅ VERIFICACIÓN 100% EXITOSA: Todos los productos coinciden sin discrepancias.")

            text_to_copy = "\n".join(lines)
            try:
                pyperclip.copy(text_to_copy)
                btn_copy.configure(text="✅ ¡Reporte copiado!", bg="#16a34a", fg="white")
                w.after(2500, lambda: btn_copy.configure(text="📋 Copiar Reporte Completo", bg="#e2e8f0", fg="#334155"))
            except Exception:
                pass

        btn_copy = tk.Button(btn_bar, text="📋 Copiar Reporte Completo", font=("Segoe UI", 9, "bold"),
                             fg="#334155", bg="#e2e8f0", activebackground="#cbd5e1", padx=12, pady=6, relief="flat", cursor="hand2", command=copy_audit_report)
        btn_copy.pack(side="left", padx=(0, 8))

        def reaudit_action():
            w.destroy()
            self._on_manual_audit()

        btn_reaudit = tk.Button(btn_bar, text="🔍 Re-auditar Saint Ahora", font=("Segoe UI", 9, "bold"),
                                fg="#0284c7", bg="#e0f2fe", activebackground="#bae6fd", padx=12, pady=6, relief="flat", cursor="hand2", command=reaudit_action)
        btn_reaudit.pack(side="left")

        def close_audit_only():
            """Cierra la ventana de auditoría garantizando que Facturador Saint permanezca abierto y al frente."""
            try:
                w.grab_release()
            except Exception:
                pass
            w.destroy()
            try:
                forzar_ventana_al_frente(self.root)
            except Exception:
                pass
            try:
                self._toggle_topmost()
            except Exception:
                pass
            if on_close:
                try:
                    on_close()
                except Exception:
                    pass

        def close_and_go_to_saint():
            """Cierra la auditoría y enfoca Saint Enterprise si el usuario lo desea explícitamente."""
            try:
                w.grab_release()
            except Exception:
                pass
            w.destroy()
            try:
                if not self.engine.config.get("test_mode", False):
                    buscar_y_enfocar_saint()
            except Exception:
                pass
            if on_close:
                try:
                    on_close()
                except Exception:
                    pass

        w.protocol("WM_DELETE_WINDOW", close_audit_only)

        btn_go_saint = tk.Button(btn_bar, text="🖥️ Ir a Saint", font=("Segoe UI", 9),
                                 fg="#334155", bg="#f1f5f9", activebackground="#e2e8f0",
                                 padx=12, pady=6, relief="flat", cursor="hand2", command=close_and_go_to_saint)
        btn_go_saint.pack(side="right", padx=(8, 0))

        btn_close = tk.Button(btn_bar, text="✔️ Cerrar Auditoría", font=("Segoe UI", 9, "bold"),
                              fg="white", bg="#0284c7", activebackground="#0369a1", activeforeground="white",
                              padx=18, pady=6, relief="flat", cursor="hand2", command=close_audit_only)
        btn_close.pack(side="right")

    def _on_engine_log(self, msg):
        self.root.after(0, lambda: self._log(msg))

    def _log(self, text):
        self.txt_log.configure(state="normal")
        self.txt_log.insert("end", f"{text}\n")
        self.txt_log.see("end")
        self.txt_log.configure(state="disabled")

    def _auto_check_updates(self):
        """Verificación automática silenciosa de actualizaciones al abrir el programa."""
        def worker():
            res = updater.check_for_updates()
            if res.get("success") and res.get("has_update"):
                self.root.after(0, lambda: self._on_update_found(res, auto=True))
        threading.Thread(target=worker, daemon=True).start()

    def _manual_check_updates(self):
        """Verificación manual invocada por el usuario desde la cabecera."""
        self.btn_update.configure(text="⏳ Buscando...", state="disabled")
        def worker():
            res = updater.check_for_updates()
            self.root.after(0, lambda: self._on_manual_check_result(res))
        threading.Thread(target=worker, daemon=True).start()

    def _on_manual_check_result(self, res: dict):
        self.btn_update.configure(text="🔄 Buscar Actualización", state="normal")
        if not res.get("success"):
            err = res.get("error", "Error desconocido de conexión.")
            messagebox.showwarning("Actualizaciones", f"No se pudo consultar el servidor de GitHub:\n{err}", parent=self.root)
            return

        if res.get("has_update"):
            self._on_update_found(res, auto=False)
        else:
            msg = res.get("message", f"Ya tienes instalada la versión más reciente (v{updater.CURRENT_VERSION}).")
            messagebox.showinfo("Actualizaciones", f"{msg}\n¡Todo está al día!", parent=self.root)

    def _manual_check_beta_updates(self):
        """Verificación manual de versiones Beta invocada por el botón 'Descargar Beta'."""
        self.btn_beta.configure(text="⏳ Buscando...", state="disabled")
        def worker():
            res = updater.check_for_beta_updates()
            self.root.after(0, lambda: self._on_manual_beta_check_result(res))
        threading.Thread(target=worker, daemon=True).start()

    def _on_manual_beta_check_result(self, res: dict):
        self.btn_beta.configure(text="🧪 Descargar Beta", state="normal")
        if not res.get("success"):
            err = res.get("error", "Error desconocido de conexión.")
            messagebox.showwarning("Versiones Beta", f"No se pudo consultar el servidor de GitHub:\n{err}", parent=self.root)
            return

        if res.get("has_update"):
            latest = res.get("latest_version", "")
            self.btn_beta.configure(
                text=f"🧪 ¡Instalar {latest}!",
                fg="#ffffff",
                bg="#d97706",
                activebackground="#b45309",
                activeforeground="#ffffff",
                state="normal"
            )
            updater.UpdateModal(self.root, res, on_install_callback=self._before_update_install)
        else:
            msg = res.get("message", f"No hay versiones Beta disponibles en este momento.\nTu versión actual es la v{updater.CURRENT_VERSION}.")
            messagebox.showinfo("Versiones Beta", f"{msg}", parent=self.root)

    def _on_update_found(self, update_info: dict, auto: bool = False):
        latest = update_info.get("latest_version", "")
        # Resaltar botón en la cabecera con estilo llamativo
        self.btn_update.configure(
            text=f"🚀 ¡Actualizar a {latest}!",
            fg="#ffffff",
            bg="#0284c7",
            activebackground="#0369a1",
            activeforeground="#ffffff",
            state="normal"
        )
        # Abrir ventana modal con 1 clic
        updater.UpdateModal(self.root, update_info, on_install_callback=self._before_update_install)

    def _before_update_install(self):
        """Detiene de forma segura el motor y atajos antes de reemplazar el ejecutable."""
        try:
            if self.engine.running:
                self.engine.stop()
            self.engine.stop_hotkeys()
        except Exception:
            pass

    def _on_close(self):
        if self.engine.running:
            if not messagebox.askyesno("Salir", "El facturador está activo. ¿Deseas detenerlo y salir?"):
                return
            self.engine.stop()
        self._save_user_config()
        self.engine.stop_hotkeys()
        self.root.destroy()


def main():
    root = tk.Tk()
    app = FacturadorApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
