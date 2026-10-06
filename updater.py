"""
MÓDULO DE ACTUALIZACIONES AUTOMÁTICAS (1-CLIC) VÍA GITHUB RELEASES
Compatible con Windows, PyInstaller e Inno Setup.
"""

import os
import sys
import re
import json
import tempfile
import threading
import subprocess
from pathlib import Path
import ssl
import urllib.request
import urllib.error
import tkinter as tk
from tkinter import ttk, messagebox

# Configuración por defecto del repositorio
CURRENT_VERSION = "2.61"
GITHUB_OWNER = "betank434"
GITHUB_REPO = "bot-facturas"
USER_AGENT = f"FacturadorSaint-Updater/{CURRENT_VERSION}"


def _get_ssl_context():
    """
    Crea un contexto SSL universal compatible con Windows 10, Windows 11 y ejecutables PyInstaller.
    Soluciona el error [SSL: CERTIFICATE_VERIFY_FAILED] cuando faltan certificados raíz locales.
    """
    try:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        return ctx
    except Exception:
        try:
            return ssl._create_unverified_context()
        except Exception:
            return None


def parse_version(v_str: str) -> tuple:
    """
    Convierte un string de versión (ej: 'v2.5', '2.4.1', '2.5-beta') en una tupla de enteros
    para comparaciones seguras (2, 5) > (2, 4).
    """
    if not v_str:
        return (0,)
    # Extraer parte base antes de -beta si existe
    base_part = re.split(r"[-_]?(?:beta|alpha|rc|preview|test)", str(v_str).lower())[0]
    nums = re.findall(r"\d+", base_part) if base_part else re.findall(r"\d+", str(v_str))
    if not nums:
        return (0,)
    return tuple(int(n) for n in nums)


def is_version_newer(latest_ver: str, current_ver: str = CURRENT_VERSION) -> bool:
    """Devuelve True si latest_ver es estrictamente superior a current_ver."""
    return parse_version(latest_ver) > parse_version(current_ver)


def is_beta_release(release_data: dict) -> bool:
    """Devuelve True si el release de GitHub es una versión beta, pre-lanzamiento o de prueba."""
    if release_data.get("prerelease", False):
        return True
    tag = str(release_data.get("tag_name", "")).lower()
    name = str(release_data.get("name", "")).lower()
    for kw in ("beta", "alpha", "rc", "preview", "test"):
        if kw in tag or kw in name:
            return True
    return False


def parse_version_details(v_str: str) -> dict:
    """
    Parsea una cadena de versión extrayendo números de versión base y detalles de la versión beta.
    Ejemplos:
      'v2.61'        -> base: (2, 61), is_beta: False, beta_num: 0
      'v2.61-beta'   -> base: (2, 61), is_beta: True, beta_num: 0
      'v2.61-beta2'  -> base: (2, 61), is_beta: True, beta_num: 2
      'v2.62-beta'   -> base: (2, 62), is_beta: True, beta_num: 0
    """
    raw = str(v_str or "").strip().lower()
    is_beta = any(kw in raw for kw in ("beta", "alpha", "rc", "preview", "test"))
    
    # Extraer la parte numérica antes del indicador beta
    base_part = re.split(r"[-_]?(?:beta|alpha|rc|preview|test)", raw)[0]
    nums = [int(n) for n in re.findall(r"\d+", base_part)] if base_part else []
    if not nums:
        all_nums = [int(n) for n in re.findall(r"\d+", raw)]
        nums = all_nums[:2] if all_nums else [0]

    beta_num = 0
    if is_beta:
        b_match = re.search(r"(?:beta|alpha|rc|preview|test)[-_\.]?(\d+)", raw)
        if b_match:
            try:
                beta_num = int(b_match.group(1))
            except Exception:
                beta_num = 0

    return {
        "raw": v_str,
        "base": tuple(nums),
        "is_beta": is_beta,
        "beta_num": beta_num
    }


def is_beta_newer(beta_ver_str: str, current_ver_str: str = CURRENT_VERSION) -> bool:
    """
    Determina si una versión beta es más reciente o apta para actualización sobre la versión actual.
    """
    b = parse_version_details(beta_ver_str)
    c = parse_version_details(current_ver_str)
    
    # 1. Si la versión base del beta es mayor (ej: 2.62-beta > 2.61)
    if b["base"] > c["base"]:
        return True
    
    # 2. Si la versión base del beta es menor (ej: 2.59-beta vs 2.61)
    if b["base"] < c["base"]:
        return False
        
    # 3. Misma base numérica (ej: 2.61 vs 2.61):
    if c["is_beta"]:
        # Ambas son beta: solo si el número de sub-beta es superior (ej: beta2 > beta1)
        return b["beta_num"] > c["beta_num"]
    else:
        # La versión actual es estable/final (ej: 2.61 final). Si el usuario pulsa explícitamente
        # "Descargar Beta" y existe un release beta para probar de esa versión o desarrollo, se permite.
        return True


def check_for_updates(
    current_version: str = CURRENT_VERSION,
    owner: str = GITHUB_OWNER,
    repo: str = GITHUB_REPO,
    timeout: int = 8,
    include_beta: bool = False
) -> dict:
    """
    Consulta la API pública de GitHub Releases para obtener la última versión FINAL publicada.
    Por defecto omite versiones beta para no interrumpir el flujo normal ni mostrar ventanas al inicio.
    """
    api_url = f"https://api.github.com/repos/{owner}/{repo}/releases/latest"
    req = urllib.request.Request(
        api_url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/vnd.github.v3+json"
        }
    )

    try:
        with urllib.request.urlopen(req, timeout=timeout, context=_get_ssl_context()) as resp:
            if resp.status != 200:
                return {
                    "success": False,
                    "has_update": False,
                    "error": f"Respuesta HTTP {resp.status}"
                }
            data = json.loads(resp.read().decode("utf-8"))

        tag_name = data.get("tag_name", "").strip()
        release_name = data.get("name", tag_name)
        release_body = data.get("body", "Sin notas de versión disponibles.")
        published_at = data.get("published_at", "")
        html_url = data.get("html_url", "")

        # Si el release de GitHub es una versión beta y no estamos en modo beta, ignorarla
        if not include_beta and is_beta_release(data):
            return {
                "success": True,
                "has_update": False,
                "latest_version": current_version,
                "current_version": current_version,
                "is_beta": True,
                "message": "La versión disponible es una versión Beta. Para instalarla utiliza el botón 'Descargar Beta'."
            }

        # Verificar si la versión es superior
        has_update = is_version_newer(tag_name, current_version)

        # Buscar el archivo ejecutable / instalador en los assets
        assets = data.get("assets", [])
        installer_asset = None

        # Priorizar assets que sean instaladores .exe
        for asset in assets:
            name = asset.get("name", "").lower()
            if name.endswith(".exe"):
                if "instalador" in name or "setup" in name or "facturador" in name:
                    installer_asset = asset
                    break
                elif not installer_asset:
                    installer_asset = asset

        download_url = installer_asset.get("browser_download_url") if installer_asset else None
        asset_name = installer_asset.get("name") if installer_asset else None
        asset_size = installer_asset.get("size", 0) if installer_asset else 0

        return {
            "success": True,
            "has_update": has_update,
            "is_beta": False,
            "latest_version": tag_name,
            "current_version": current_version,
            "release_name": release_name,
            "release_notes": release_body,
            "published_at": published_at,
            "html_url": html_url,
            "download_url": download_url,
            "asset_name": asset_name,
            "asset_size": asset_size,
            "has_installer": bool(download_url)
        }

    except urllib.error.HTTPError as e:
        if e.code == 404:
            return {
                "success": True,
                "has_update": False,
                "is_beta": False,
                "latest_version": current_version,
                "current_version": current_version,
                "message": "No hay versiones publicadas aún en el repositorio de GitHub."
            }
        return {
            "success": False,
            "has_update": False,
            "is_beta": False,
            "error": f"Error de GitHub HTTP {e.code}: {e.reason}"
        }
    except urllib.error.URLError as e:
        return {
            "success": False,
            "has_update": False,
            "is_beta": False,
            "error": f"Error de conexión: {e.reason}"
        }
    except Exception as e:
        return {
            "success": False,
            "has_update": False,
            "is_beta": False,
            "error": str(e)
        }


def check_for_beta_updates(
    current_version: str = CURRENT_VERSION,
    owner: str = GITHUB_OWNER,
    repo: str = GITHUB_REPO,
    timeout: int = 10
) -> dict:
    """
    Consulta la API pública de GitHub Releases para buscar la versión BETA más reciente disponible.
    Filtra únicamente versiones beta (prerelease o etiqueta beta) y busca un instalador .exe adjunto.
    """
    api_url = f"https://api.github.com/repos/{owner}/{repo}/releases?per_page=20"
    req = urllib.request.Request(
        api_url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/vnd.github.v3+json"
        }
    )

    try:
        with urllib.request.urlopen(req, timeout=timeout, context=_get_ssl_context()) as resp:
            if resp.status != 200:
                return {
                    "success": False,
                    "has_update": False,
                    "is_beta": True,
                    "error": f"Respuesta HTTP {resp.status}"
                }
            releases = json.loads(resp.read().decode("utf-8"))

        if not isinstance(releases, list):
            return {
                "success": False,
                "has_update": False,
                "is_beta": True,
                "error": "Respuesta no válida del servidor."
            }

        candidate_beta = None
        for rel in releases:
            if not is_beta_release(rel):
                continue
            
            tag_name = rel.get("tag_name", "").strip()
            if is_beta_newer(tag_name, current_version):
                assets = rel.get("assets", [])
                inst_asset = None
                for asset in assets:
                    name = asset.get("name", "").lower()
                    if name.endswith(".exe"):
                        if "instalador" in name or "setup" in name or "facturador" in name:
                            inst_asset = asset
                            break
                        elif not inst_asset:
                            inst_asset = asset
                
                if inst_asset:
                    candidate_beta = (rel, inst_asset)
                    break

        if not candidate_beta:
            return {
                "success": True,
                "has_update": False,
                "is_beta": True,
                "latest_version": current_version,
                "current_version": current_version,
                "message": f"No hay versiones Beta disponibles en este momento.\nTu versión actual es la v{current_version}."
            }

        rel, installer_asset = candidate_beta
        tag_name = rel.get("tag_name", "").strip()
        release_name = rel.get("name", tag_name)
        release_body = rel.get("body", "Versión Beta de prueba en desarrollo.")
        published_at = rel.get("published_at", "")
        html_url = rel.get("html_url", "")
        download_url = installer_asset.get("browser_download_url")
        asset_name = installer_asset.get("name")
        asset_size = installer_asset.get("size", 0)

        return {
            "success": True,
            "has_update": True,
            "is_beta": True,
            "latest_version": tag_name,
            "current_version": current_version,
            "release_name": release_name,
            "release_notes": release_body,
            "published_at": published_at,
            "html_url": html_url,
            "download_url": download_url,
            "asset_name": asset_name,
            "asset_size": asset_size,
            "has_installer": bool(download_url)
        }

    except urllib.error.HTTPError as e:
        if e.code == 404:
            return {
                "success": True,
                "has_update": False,
                "is_beta": True,
                "latest_version": current_version,
                "current_version": current_version,
                "message": "No se encontraron releases en el repositorio de GitHub."
            }
        return {
            "success": False,
            "has_update": False,
            "is_beta": True,
            "error": f"Error de GitHub HTTP {e.code}: {e.reason}"
        }
    except urllib.error.URLError as e:
        return {
            "success": False,
            "has_update": False,
            "is_beta": True,
            "error": f"Error de conexión: {e.reason}"
        }
    except Exception as e:
        return {
            "success": False,
            "has_update": False,
            "is_beta": True,
            "error": str(e)
        }


def download_file(
    url: str,
    target_path: Path,
    progress_callback=None,
    cancel_event: threading.Event = None,
    chunk_size: int = 65536
):
    """
    Descarga un archivo por bloques con reporte de progreso y soporte de cancelación.
    """
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, context=_get_ssl_context()) as response:
        total_size = int(response.headers.get("Content-Length", 0))
        downloaded = 0

        temp_target = target_path.with_suffix(target_path.suffix + ".part")
        with open(temp_target, "wb") as f:
            while True:
                if cancel_event and cancel_event.is_set():
                    f.close()
                    if temp_target.exists():
                        try:
                            temp_target.unlink()
                        except Exception:
                            pass
                    raise Exception("Descarga cancelada por el usuario.")

                chunk = response.read(chunk_size)
                if not chunk:
                    break

                f.write(chunk)
                downloaded += len(chunk)

                if progress_callback and total_size > 0:
                    percent = int((downloaded / total_size) * 100)
                    progress_callback(downloaded, total_size, percent)

        # Renombrar archivo temporal al destino final
        if temp_target.exists():
            if target_path.exists():
                try:
                    target_path.unlink()
                except Exception:
                    pass
            temp_target.rename(target_path)


def launch_installer_and_exit(installer_path: Path, app_root: tk.Tk = None):
    """
    Lanza el instalador oficial de Inno Setup y cierra el programa actual
    para que la actualización sobrescriba los archivos sin bloqueos.
    """
    inst_str = str(installer_path.resolve())
    
    try:
        # En Windows utilizamos ShellExecute (vía os.startfile)
        # Esto maneja permisos de Administrador/UAC de forma nativa sin fallos
        os.startfile(inst_str, "open")
    except Exception:
        # Fallback usando subprocess
        subprocess.Popen([inst_str], shell=True)

    # Cerrar la aplicación actual limpiamente
    if app_root:
        try:
            app_root.destroy()
        except Exception:
            pass
    sys.exit(0)


class UpdateModal:
    """
    Ventana emergente moderna para notificar y ejecutar la actualización con 1 clic.
    """
    def __init__(self, parent: tk.Tk, update_info: dict, on_install_callback=None):
        self.parent = parent
        self.update_info = update_info
        self.on_install_callback = on_install_callback
        self.cancel_event = threading.Event()
        self.is_downloading = False
        self.is_beta = bool(self.update_info.get("is_beta", False))

        self.win = tk.Toplevel(parent)
        modal_title = "Versión Beta | Facturador Saint" if self.is_beta else "Actualización de Facturador Saint"
        self.win.title(modal_title)
        self.win.geometry("540x440")
        self.win.resizable(False, False)
        self.win.configure(bg="#0f172a")

        # Centrar sobre la ventana padre
        self._center_window()
        self.win.transient(parent)
        self.win.grab_set()

        self._build_ui()
        self.win.protocol("WM_DELETE_WINDOW", self._on_close)

    def _center_window(self):
        self.win.update_idletasks()
        pw = self.parent.winfo_width()
        ph = self.parent.winfo_height()
        px = self.parent.winfo_rootx()
        py = self.parent.winfo_rooty()
        w = 540
        h = 440
        x = px + max(0, (pw - w) // 2)
        y = py + max(0, (ph - h) // 2)
        self.win.geometry(f"{w}x{h}+{x}+{y}")

    def _build_ui(self):
        # Cabecera moderna (ámbar oscuro para betas, azul para versiones estables)
        header_bg = "#271c10" if self.is_beta else "#1e293b"
        header = tk.Frame(self.win, bg=header_bg, padx=16, pady=12)
        header.pack(fill="x", side="top")

        icon_text = "🧪" if self.is_beta else "🚀"
        icon_fg = "#fbbf24" if self.is_beta else "#38bdf8"
        lbl_icon = tk.Label(header, text=icon_text, font=("Segoe UI Emoji", 20), bg=header_bg, fg=icon_fg)
        lbl_icon.pack(side="left", padx=(0, 10))

        title_frame = tk.Frame(header, bg=header_bg)
        title_frame.pack(side="left", fill="both", expand=True)

        title_prefix = "¡Nueva versión Beta disponible:" if self.is_beta else "¡Nueva versión disponible:"
        lbl_title = tk.Label(
            title_frame,
            text=f"{title_prefix} {self.update_info.get('latest_version')}!",
            font=("Segoe UI", 11, "bold"),
            fg="#f8fafc",
            bg=header_bg
        )
        lbl_title.pack(anchor="w")

        cur_v = self.update_info.get("current_version", CURRENT_VERSION)
        sub_text = (
            f"Versión de prueba (Beta). Tu versión actual es v{cur_v}."
            if self.is_beta else
            f"Tu versión actual es la v{cur_v}. Se recomienda actualizar."
        )
        lbl_sub = tk.Label(
            title_frame,
            text=sub_text,
            font=("Segoe UI", 9),
            fg="#e2e8f0" if self.is_beta else "#94a3b8",
            bg=header_bg
        )
        lbl_sub.pack(anchor="w")

        # Contenedor central
        body = tk.Frame(self.win, bg="#0f172a", padx=18, pady=12)
        body.pack(fill="both", expand=True)

        # Detalles del archivo
        size_bytes = self.update_info.get("asset_size", 0)
        size_mb = size_bytes / (1024 * 1024) if size_bytes else 0
        asset_name = self.update_info.get("asset_name", "Instalador_Facturador_Saint.exe")

        info_box = tk.Frame(body, bg="#1e293b", padx=10, pady=6)
        info_box.pack(fill="x", pady=(0, 8))

        pkg_prefix = "🧪 Paquete Beta:" if self.is_beta else "📦 Paquete:"
        pkg_fg = "#fbbf24" if self.is_beta else "#38bdf8"
        lbl_pkg = tk.Label(
            info_box,
            text=f"{pkg_prefix} {asset_name}  ({size_mb:.1f} MB)",
            font=("Segoe UI", 9, "bold"),
            fg=pkg_fg,
            bg="#1e293b"
        )
        lbl_pkg.pack(anchor="w")

        # Novedades / Changelog
        notes_title = "Novedades y cambios en esta versión Beta:" if self.is_beta else "Novedades y mejoras en esta versión:"
        lbl_notes = tk.Label(body, text=notes_title, font=("Segoe UI", 9, "bold"), fg="#e2e8f0", bg="#0f172a")
        lbl_notes.pack(anchor="w", pady=(0, 4))

        txt_frame = tk.Frame(body, bg="#1e293b")
        txt_frame.pack(fill="both", expand=True, pady=(0, 8))

        self.txt_notes = tk.Text(
            txt_frame,
            font=("Segoe UI", 8),
            bg="#1e293b",
            fg="#cbd5e1",
            relief="flat",
            wrap="word",
            height=6,
            padx=8,
            pady=6
        )
        sb = ttk.Scrollbar(txt_frame, orient="vertical", command=self.txt_notes.yview)
        self.txt_notes.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self.txt_notes.pack(side="left", fill="both", expand=True)

        notes_content = self.update_info.get("release_notes", "").strip()
        if not notes_content:
            notes_content = (
                "• Versión de pruebas con nuevas características y correcciones anticipadas."
                if self.is_beta else
                "• Mejoras generales de estabilidad, velocidad y rendimiento.\n• Corrección de errores menores."
            )
        self.txt_notes.insert("1.0", notes_content)
        self.txt_notes.configure(state="disabled")

        # Barra de progreso y estado
        self.p_frame = tk.Frame(body, bg="#0f172a")
        self.p_frame.pack(fill="x", pady=(2, 6))

        btn_action_name = "'Descargar e Instalar Beta'" if self.is_beta else "'Descargar e Instalar'"
        self.lbl_status = tk.Label(
            self.p_frame,
            text=f"Presiona {btn_action_name} para comenzar la actualización en 1 clic.",
            font=("Segoe UI", 8),
            fg="#94a3b8",
            bg="#0f172a"
        )
        self.lbl_status.pack(anchor="w", pady=(0, 4))

        self.progress = ttk.Progressbar(self.p_frame, orient="horizontal", mode="determinate")
        self.progress.pack(fill="x")

        # Barra de botones inferior
        bottom_bar = tk.Frame(self.win, bg="#1e293b", padx=16, pady=10)
        bottom_bar.pack(fill="x", side="bottom")

        self.btn_later = tk.Button(
            bottom_bar,
            text="Más tarde",
            font=("Segoe UI", 9),
            fg="#cbd5e1",
            bg="#334155",
            activebackground="#475569",
            activeforeground="#ffffff",
            relief="flat",
            padx=14,
            pady=5,
            cursor="hand2",
            command=self._on_close
        )
        self.btn_later.pack(side="left")

        btn_txt = "🧪 Descargar e Instalar Beta (1 Clic)" if self.is_beta else "⚡ Descargar e Instalar (1 Clic)"
        btn_bg = "#d97706" if self.is_beta else "#0284c7"
        btn_act_bg = "#b45309" if self.is_beta else "#0369a1"

        self.btn_update = tk.Button(
            bottom_bar,
            text=btn_txt,
            font=("Segoe UI", 9, "bold"),
            fg="#ffffff",
            bg=btn_bg,
            activebackground=btn_act_bg,
            activeforeground="#ffffff",
            relief="flat",
            padx=16,
            pady=5,
            cursor="hand2",
            command=self._start_download_thread
        )
        self.btn_update.pack(side="right")

    def _start_download_thread(self):
        if self.is_downloading:
            return

        download_url = self.update_info.get("download_url")
        if not download_url:
            messagebox.showerror(
                "Error de descarga",
                "Esta versión publicada en GitHub no tiene un archivo instalador .exe adjunto.",
                parent=self.win
            )
            return

        self.is_downloading = True
        self.btn_update.configure(state="disabled", text="Descargando...", bg="#475569")
        self.btn_later.configure(text="Cancelar descarga")
        self.lbl_status.configure(text="Conectando con GitHub y descargando actualización...", fg="#38bdf8")

        thread = threading.Thread(target=self._download_worker, daemon=True)
        thread.start()

    def _download_worker(self):
        download_url = self.update_info.get("download_url")
        asset_name = self.update_info.get("asset_name") or "Instalador_Facturador_Saint_Actualizacion.exe"
        temp_dir = Path(tempfile.gettempdir())
        target_path = temp_dir / asset_name

        def progress_cb(downloaded, total, percent):
            d_mb = downloaded / (1024 * 1024)
            t_mb = total / (1024 * 1024)
            self.win.after(0, lambda: self._update_ui_progress(percent, d_mb, t_mb))

        try:
            download_file(
                download_url,
                target_path,
                progress_callback=progress_cb,
                cancel_event=self.cancel_event
            )

            # Éxito: ejecutar instalador
            self.win.after(0, lambda: self._on_download_success(target_path))

        except Exception as e:
            if not self.cancel_event.is_set():
                err_msg = str(e)
                self.win.after(0, lambda: self._on_download_error(err_msg))

    def _update_ui_progress(self, percent: int, downloaded_mb: float, total_mb: float):
        if not self.win.winfo_exists():
            return
        self.progress["value"] = percent
        self.lbl_status.configure(
            text=f"Descargando: {percent}% ({downloaded_mb:.1f} MB / {total_mb:.1f} MB)...",
            fg="#38bdf8"
        )

    def _on_download_success(self, target_path: Path):
        if not self.win.winfo_exists():
            return
        self.progress["value"] = 100
        self.lbl_status.configure(
            text="✅ ¡Descarga completada con éxito! Iniciando instalador...",
            fg="#10b981"
        )
        self.btn_later.configure(state="disabled")

        if self.on_install_callback:
            try:
                self.on_install_callback()
            except Exception:
                pass

        # Pequeña pausa para que el usuario lea el mensaje y luego lanzar
        self.win.after(1200, lambda: launch_installer_and_exit(target_path, self.parent))

    def _on_download_error(self, err_msg: str):
        if not self.win.winfo_exists():
            return
        self.is_downloading = False
        self.progress["value"] = 0
        self.lbl_status.configure(text=f"❌ Error al descargar: {err_msg}", fg="#f87171")
        self.btn_update.configure(state="normal", text="Reintentar", bg="#0284c7")
        self.btn_later.configure(text="Cerrar")
        messagebox.showerror(
            "Error al actualizar",
            f"No se pudo completar la descarga:\n{err_msg}",
            parent=self.win
        )

    def _on_close(self):
        if self.is_downloading:
            if messagebox.askyesno("Cancelar Descarga", "¿Deseas cancelar la descarga de la actualización en curso?", parent=self.win):
                self.cancel_event.set()
                self.win.destroy()
        else:
            self.win.destroy()
