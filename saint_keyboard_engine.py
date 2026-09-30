"""
Motor de Teclado Virtual para Saint Annual Enterprise.
Emulación nativa Win32 (Virtual Keys y Scan Codes de hardware) para compatibilidad
total con Delphi/VCL de Saint Enterprise.
"""

import time
import threading
import sys
import ctypes
from ctypes import wintypes
from typing import Callable, Dict, List, Optional

# Cargar Win32 API
user32 = ctypes.windll.user32
VK_RETURN = 0x0D
VK_TAB = 0x09
VK_SHIFT = 0x10
VK_F5 = 0x74
VK_F7 = 0x76
VK_F8 = 0x77
VK_F12 = 0x7B
VK_ESCAPE = 0x1B
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
    scan = user32.MapVirtualKeyW(vk_code, 0)
    user32.keybd_event(vk_code, scan, 0, 0)
    time.sleep(0.02)
    user32.keybd_event(vk_code, scan, KEYEVENTF_KEYUP, 0)
    time.sleep(delay_after)


user32.VkKeyScanW.argtypes = [ctypes.c_wchar]
user32.VkKeyScanW.restype = wintypes.SHORT


def win32_type_char(char: str, key_delay: float = 0.03):
    if not char:
        return
    c = char[0]
    res = user32.VkKeyScanW(c)
    if res == -1:
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
    for ch in str(text):
        if stop_checker and stop_checker():
            break
        win32_type_char(ch, key_delay=key_delay)


def enfocar_saint() -> bool:
    found_hwnds = []
    def enum_cb(hwnd, lparam):
        if not user32.IsWindowVisible(hwnd):
            return True
        length = user32.GetWindowTextLengthW(hwnd)
        if length > 0:
            buff = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, buff, length + 1)
            title = buff.value.upper()
            if any(t in title for t in ["PRESUPUESTO", "SAINT", "ANNUAL", "VENTAS"]):
                found_hwnds.append((hwnd, buff.value))
        return True

    EnumWndProc = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
    user32.EnumWindows(EnumWndProc(enum_cb), 0)
    if found_hwnds:
        target_hwnd = found_hwnds[0][0]
        for h, t in found_hwnds:
            if "PRESUPUESTO" in t.upper():
                target_hwnd = h
                break
        user32.ShowWindow(target_hwnd, 9)
        user32.SetForegroundWindow(target_hwnd)
        time.sleep(0.2)
        return True
    return False


class KeyboardBotEngine:
    """Controlador de eventos de teclado virtual nativo para Saint Enterprise"""
    def __init__(self):
        self.running = False
        self.paused = False
        self._stop_requested = False
        self._thread: Optional[threading.Thread] = None
        self._listener: Optional[pynput_keyboard.Listener] = None
        
        self.on_item_started: Optional[Callable[[int, dict], None]] = None
        self.on_item_finished: Optional[Callable[[int, dict, bool], None]] = None
        self.on_log: Optional[Callable[[str], None]] = None
        self.on_state_change: Optional[Callable[[str], None]] = None
        self.on_countdown: Optional[Callable[[int], None]] = None
        
        self.config = {
            "countdown_seconds": 3,
            "delay_after_barcode": 0.50,
            "delay_after_qty": 0.40,
            "delay_between_items": 0.35,
            "delay_key_press": 0.025,
            "enters_after_code": 1,
            "enters_after_qty": 1,
            "include_price": False,
            "price_key": "costo_unitario_usd",
            "enters_after_price": 1,
            "key_confirm": "enter",
            "test_mode": False
        }

    def log(self, message: str):
        if self.on_log:
            self.on_log(message)
        else:
            print(f"[BOT] {message}")

    def emit_beep(self, frequency=1000, duration=150):
        if HAVE_SOUND:
            try:
                winsound.Beep(frequency, duration)
            except Exception:
                pass

    def start_hotkey_listener(self, on_f8=None, on_f7=None, on_f12=None):
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
        except Exception:
            pass

    def stop_hotkey_listener(self):
        if self._listener:
            try:
                self._listener.stop()
            except Exception:
                pass
            self._listener = None

    def start_process(self, items: List[dict]):
        if self.running:
            return
        self.running = True
        self.paused = False
        self._stop_requested = False
        self._thread = threading.Thread(target=self._run_typing_loop, args=(items,), daemon=True)
        self._thread.start()

    def pause(self):
        if not self.running:
            return
        self.paused = not self.paused
        st = "PAUSADO" if self.paused else "REANUDADO"
        self.log(f"Bot {st}. (Pulsa F7 para continuar o F12 para cancelar).")
        if self.on_state_change:
            self.on_state_change(st)
        self.emit_beep(750, 200)

    def stop(self):
        if not self.running:
            return
        self._stop_requested = True
        self.paused = False
        self.running = False
        self.log("Detención solicitada. Abortando escritura...")
        if self.on_state_change:
            self.on_state_change("DETENIDO")
        self.emit_beep(450, 400)

    def _sleep_check(self, seconds: float) -> bool:
        step = 0.05
        elapsed = 0.0
        while elapsed < seconds:
            if self._stop_requested:
                return False
            while self.paused:
                time.sleep(0.1)
                if self._stop_requested:
                    return False
            time.sleep(step)
            elapsed += step
        return True

    def _run_typing_loop(self, items: List[dict]):
        try:
            if self.on_state_change:
                self.on_state_change("CUENTA_REGRESIVA")

            countdown = self.config.get("countdown_seconds", 3)
            self.log(f"Iniciando en {countdown}s... ¡Haz clic en el campo de Saint!")
            
            for c in range(countdown, 0, -1):
                if self._stop_requested:
                    return
                if self.on_countdown:
                    self.on_countdown(c)
                self.emit_beep(880, 100)
                if not self._sleep_check(1.0):
                    return

            if not self.config.get("test_mode", False):
                enfocar_saint()

            self.emit_beep(1320, 250)
            if self.on_state_change:
                self.on_state_change("ESCRIBIENDO")

            total = len(items)
            vk_confirm = VK_RETURN if self.config.get("key_confirm", "enter") == "enter" else VK_TAB

            for idx, item in enumerate(items, 1):
                if self._stop_requested:
                    break

                if self.on_item_started:
                    self.on_item_started(idx - 1, item)

                codigo = str(item.get("codigo_barra", "")).strip()
                cantidad = str(item.get("cantidad", "1")).strip()
                desc = item.get("descripcion", "")[:28]

                self.log(f"[{idx}/{total}] Referencia: {codigo} | Cant: {cantidad} ({desc})")

                # Escribir código con Win32 nativo
                win32_type_string(codigo, key_delay=self.config.get("delay_key_press", 0.025),
                                  stop_checker=lambda: self._stop_requested)
                
                for _ in range(self.config.get("enters_after_code", 1)):
                    win32_press_vk(vk_confirm, delay_after=0.04)

                if not self._sleep_check(self.config.get("delay_after_barcode", 0.50)):
                    break

                # Escribir cantidad con Win32 nativo
                win32_type_string(cantidad, key_delay=self.config.get("delay_key_press", 0.025),
                                  stop_checker=lambda: self._stop_requested)
                
                for _ in range(self.config.get("enters_after_qty", 1)):
                    win32_press_vk(vk_confirm, delay_after=0.04)

                if not self._sleep_check(self.config.get("delay_between_items", 0.35)):
                    break

                if self.on_item_finished:
                    self.on_item_finished(idx - 1, item, True)

            if not self._stop_requested:
                self.log(f"¡Carga completada! {total} productos procesados.")
                self.emit_beep(1760, 300)
                if self.on_state_change:
                    self.on_state_change("COMPLETADO")
            else:
                if self.on_state_change:
                    self.on_state_change("DETENIDO")

        except Exception as ex:
            self.log(f"Error inesperado: {ex}")
            if self.on_state_change:
                self.on_state_change("ERROR")
        finally:
            self.running = False
            self.paused = False
            self._stop_requested = False
