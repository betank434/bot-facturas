"""
Script utilitario para gestionar el ciclo de versiones, commits, push y publicación
automática de Releases (Finales y Beta) en GitHub para Facturador Saint.
Maneja transiciones automáticas:
- Versión actual: ej. 2.62
- Betas: 2.62.1-beta, 2.62.2-beta, etc.
- Final siguiente: 2.63
- Commit automático + Push a GitHub + Creación del Release y subida del instalador .exe en 1 clic.
"""

import os
import sys
import re
import json
import glob
import base64
import shutil
import ssl
import subprocess
import urllib.request
import urllib.parse
import urllib.error
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent
UPDATER_PY = ROOT_DIR / "updater.py"
INSTALADOR_ISS = ROOT_DIR / "instalador.iss"
GITHUB_OWNER = "betank434"
GITHUB_REPO = "bot-facturas"


def _get_ssl_context():
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


def get_github_token() -> str:
    """
    Obtiene automáticamente el token de GitHub desde variables de entorno o desde el
    Administrador de Credenciales de Windows (GitHub Desktop / Git Credential Manager)
    usando la API nativa Win32 (CredReadW) sin abrir ventanas emergentes ni bloquear.
    """
    for env_key in ("GITHUB_TOKEN", "GH_TOKEN"):
        val = os.environ.get(env_key, "").strip()
        if val:
            return val

    if os.name != "nt":
        return ""

    try:
        import ctypes
        import ctypes.wintypes

        class CREDENTIAL(ctypes.Structure):
            _fields_ = [
                ("Flags", ctypes.wintypes.DWORD),
                ("Type", ctypes.wintypes.DWORD),
                ("TargetName", ctypes.wintypes.LPWSTR),
                ("Comment", ctypes.wintypes.LPWSTR),
                ("LastWritten", ctypes.wintypes.FILETIME),
                ("CredentialBlobSize", ctypes.wintypes.DWORD),
                ("CredentialBlob", ctypes.POINTER(ctypes.c_char)),
                ("Persist", ctypes.wintypes.DWORD),
                ("AttributeCount", ctypes.wintypes.DWORD),
                ("Attributes", ctypes.c_void_p),
                ("TargetAlias", ctypes.wintypes.LPWSTR),
                ("UserName", ctypes.wintypes.LPWSTR),
            ]

        advapi32 = ctypes.windll.advapi32
        advapi32.CredReadW.argtypes = [
            ctypes.wintypes.LPCWSTR,
            ctypes.wintypes.DWORD,
            ctypes.wintypes.DWORD,
            ctypes.POINTER(ctypes.POINTER(CREDENTIAL)),
        ]
        advapi32.CredReadW.restype = ctypes.wintypes.BOOL

        targets = [
            f"GitHub - https://api.github.com/{GITHUB_OWNER}",
            "git:https://github.com",
            "git:https://github.com/",
        ]
        for target in targets:
            pcred = ctypes.POINTER(CREDENTIAL)()
            if advapi32.CredReadW(target, 1, 0, ctypes.byref(pcred)):
                try:
                    cred = pcred.contents
                    raw = ctypes.string_at(cred.CredentialBlob, cred.CredentialBlobSize)
                    for enc in ("utf-8", "utf-16-le"):
                        try:
                            s = raw.decode(enc).strip("\x00").strip()
                            if len(s) >= 25 and s.isprintable() and " " not in s:
                                return s
                        except Exception:
                            pass
                finally:
                    advapi32.CredFree(pcred)
    except Exception:
        pass

    return ""


def get_current_version() -> str:
    content = UPDATER_PY.read_text(encoding="utf-8")
    m = re.search(r'CURRENT_VERSION\s*=\s*"([^"]+)"', content)
    if m:
        return m.group(1).strip()
    return "2.62"


def _version_sort_key(v_str: str) -> tuple:
    raw = str(v_str or "").strip().lower().lstrip("v")
    is_beta = "beta" in raw
    base_part = re.split(r"[-_]?(?:beta|alpha|rc|preview|test)", raw)[0]
    nums = [int(n) for n in re.findall(r"\d+", base_part)] if base_part else [0]
    while len(nums) < 3:
        nums.append(0)
    # (major, minor, is_final_or_has_beta, patch)
    return (nums[0], nums[1], nums[2], 0 if is_beta else 1)


def get_effective_version() -> str:
    """
    Obtiene la versión actual comparando updater.py con el último release publicado en GitHub
    para garantizar que jamás se repita una versión ya publicada.
    """
    local_ver = get_current_version()
    try:
        url = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/releases?per_page=5"
        headers = {"User-Agent": "FacturadorSaint-VersionCheck"}
        tok = get_github_token()
        if tok:
            headers["Authorization"] = f"token {tok}"
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, context=_get_ssl_context(), timeout=4) as resp:
            releases = json.loads(resp.read().decode("utf-8"))
            if isinstance(releases, list) and releases:
                best_ver = local_ver
                for rel in releases:
                    tag = str(rel.get("tag_name", "")).strip().lstrip("v")
                    if tag and _version_sort_key(tag) > _version_sort_key(best_ver):
                        best_ver = tag
                return best_ver
    except Exception:
        pass
    return local_ver


def calculate_next_beta(cur: str) -> str:
    # Si cur es '2.62', patch es 0 -> '2.62.1-beta'
    # Si cur es '2.62.1-beta', patch es 1 -> '2.62.2-beta'
    m = re.match(r"^(\d+\.\d+)(?:\.(\d+))?(?:-beta.*)?$", cur.strip().lstrip("v"))
    if m:
        base = m.group(1)
        patch = int(m.group(2) or 0)
        return f"{base}.{patch + 1}-beta"
    return f"{cur}.1-beta"


def calculate_next_final(cur: str) -> str:
    # Si cur es '2.62' o '2.62.X-beta' -> '2.63'
    m = re.match(r"^(\d+)\.(\d+)", cur.strip().lstrip("v"))
    if m:
        major = int(m.group(1))
        minor = int(m.group(2))
        return f"{major}.{minor + 1}"
    return "2.63"


def update_version_in_files(new_ver: str):
    # 1. Actualizar updater.py
    u_content = UPDATER_PY.read_text(encoding="utf-8")
    u_new = re.sub(r'CURRENT_VERSION\s*=\s*"[^"]+"', f'CURRENT_VERSION = "{new_ver}"', u_content)
    UPDATER_PY.write_text(u_new, encoding="utf-8")

    # 2. Actualizar instalador.iss
    i_content = INSTALADOR_ISS.read_text(encoding="utf-8")
    i_new = re.sub(r'#define\s+MyAppVersion\s+"[^"]+"', f'#define MyAppVersion "{new_ver}"', i_content)
    INSTALADOR_ISS.write_text(i_new, encoding="utf-8")


def find_git_executable() -> str:
    """Busca git.exe en PATH o en la instalación local de GitHub Desktop."""
    git_path = shutil.which("git")
    if git_path:
        return git_path
    local_app_data = os.environ.get("LOCALAPPDATA", "")
    if local_app_data:
        pattern = os.path.join(local_app_data, "GitHubDesktop", "app-*", "resources", "app", "git", "cmd", "git.exe")
        matches = sorted(glob.glob(pattern))
        if matches:
            return matches[-1]
    return "git"


def create_git_commit(new_ver: str) -> bool:
    """
    Agrega los archivos modificados (updater.py, instalador.iss, app_icon.ico y código fuente)
    y genera automáticamente el commit local.
    """
    git_exe = find_git_executable()
    try:
        res_name = subprocess.run([git_exe, "config", "user.name"], cwd=ROOT_DIR, capture_output=True, text=True)
        if res_name.returncode != 0 or not res_name.stdout.strip():
            subprocess.run([git_exe, "config", "user.name", GITHUB_OWNER], cwd=ROOT_DIR, check=False)

        res_email = subprocess.run([git_exe, "config", "user.email"], cwd=ROOT_DIR, capture_output=True, text=True)
        if res_email.returncode != 0 or not res_email.stdout.strip():
            subprocess.run([git_exe, "config", "user.email", "betank01@gmail.com"], cwd=ROOT_DIR, check=False)

        subprocess.run([git_exe, "add", "-A"], cwd=ROOT_DIR, check=True)

        status_res = subprocess.run([git_exe, "status", "--porcelain"], cwd=ROOT_DIR, capture_output=True, text=True)
        if not status_res.stdout.strip():
            print(f"[GIT] El repositorio local ya está confirmado para v{new_ver}.")
            return True

        is_beta = "beta" in new_ver.lower()
        commit_msg = (
            f"Release Beta v{new_ver}: Compilacion y actualizacion automatica de version"
            if is_beta
            else f"Release v{new_ver}: Compilacion y actualizacion automatica de version"
        )
        commit_res = subprocess.run(
            [git_exe, "commit", "-m", commit_msg],
            cwd=ROOT_DIR,
            capture_output=True,
            text=True
        )
        if commit_res.returncode == 0:
            print(f"[GIT] Commit generado exitosamente: \"{commit_msg}\"")
            return True
        else:
            err_txt = commit_res.stderr.strip() or commit_res.stdout.strip()
            print(f"[GIT] Aviso al crear commit: {err_txt}")
            return False
    except Exception as ex:
        print(f"[GIT] Error al generar commit automático: {ex}")
        return False


def push_to_github() -> bool:
    """
    Sube los commits locales a origin/main en GitHub de forma 100% desatendida
    utilizando el token de Windows Credential Manager sin colgarse en ventanas emergentes.
    """
    git_exe = find_git_executable()
    tok = get_github_token()
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0", "GCM_INTERACTIVE": "never"}

    try:
        if tok:
            auth_b64 = base64.b64encode(f"{GITHUB_OWNER}:{tok}".encode("utf-8")).decode("ascii")
            cmd = [
                git_exe,
                "-c", "credential.helper=",
                "-c", f"http.extraheader=AUTHORIZATION: basic {auth_b64}",
                "push", "origin", "main"
            ]
        else:
            cmd = [git_exe, "push", "origin", "main"]

        print("[GITHUB] Subiendo cambios (git push origin main)...")
        res = subprocess.run(cmd, cwd=ROOT_DIR, env=env, capture_output=True, text=True, timeout=60)
        if res.returncode == 0:
            print("[GITHUB] Push a origin/main completado con éxito.")
            return True
        else:
            err = res.stderr.strip() or res.stdout.strip()
            print(f"[GITHUB] Aviso en git push: {err}")
            return False
    except Exception as ex:
        print(f"[GITHUB] Error al hacer push a GitHub: {ex}")
        return False


def publish_github_release(new_ver: str) -> bool:
    """
    Crea el Release en GitHub (Final o Beta pre-release) y sube automáticamente
    el instalador dist_installer/Instalador_Facturador_Saint_v{new_ver}.exe.
    """
    clean_ver = new_ver.strip().lstrip("v")
    tag_name = f"v{clean_ver}"
    is_beta = "beta" in clean_ver.lower()

    # 1. Crear commit local y hacer push a GitHub
    create_git_commit(clean_ver)
    push_to_github()

    # 2. Verificar archivo instalador
    installer_path = ROOT_DIR / "dist_installer" / f"Instalador_Facturador_Saint_v{clean_ver}.exe"
    if not installer_path.exists():
        print(f"[ERROR] No se encontró el instalador compilado en: {installer_path}")
        return False

    tok = get_github_token()
    if not tok:
        print("[AVISO] No se encontró token de GitHub en Windows Credential Manager.")
        print("        Por favor inicia sesión en GitHub Desktop o sube el instalador manualmente.")
        return False

    ctx = _get_ssl_context()
    headers = {
        "Authorization": f"token {tok}",
        "Accept": "application/vnd.github+json",
        "Content-Type": "application/json; charset=utf-8",
        "User-Agent": f"FacturadorSaint-Publisher/{clean_ver}",
    }

    release_title = f"Facturador Saint {tag_name} Beta" if is_beta else f"Facturador Saint {tag_name}"
    release_body = (
        f"🧪 **Versión Beta de Prueba ({tag_name}) - Facturador Saint Enterprise**\n\n"
        f"- Instalador: `{installer_path.name}`\n"
        f"- Disponible desde el botón **🧪 Descargar Beta** dentro de la aplicación (no genera avisos emergentes al inicio)."
        if is_beta
        else f"🚀 **Release Oficial ({tag_name}) - Facturador Saint Enterprise**\n\n"
             f"- Instalador oficial: `{installer_path.name}`\n"
             f"- Actualización automática en 1 clic habilitada para todos los clientes."
    )

    payload = json.dumps({
        "tag_name": tag_name,
        "target_commitish": "main",
        "name": release_title,
        "body": release_body,
        "draft": False,
        "prerelease": is_beta,
    }).encode("utf-8")

    release_data = None
    create_url = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/releases"
    print(f"[GITHUB] Creando {'Release BETA (pre-release)' if is_beta else 'Release OFICIAL'} {tag_name} en GitHub...")

    try:
        req = urllib.request.Request(create_url, data=payload, headers=headers, method="POST")
        with urllib.request.urlopen(req, context=ctx, timeout=30) as resp:
            release_data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as he:
        if he.code == 422:
            # El tag/release ya existe: obtener el release existente y actualizarlo
            print(f"[GITHUB] El release {tag_name} ya existe, actualizando release existente...")
            tag_url = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/releases/tags/{tag_name}"
            req_get = urllib.request.Request(tag_url, headers=headers, method="GET")
            with urllib.request.urlopen(req_get, context=ctx, timeout=20) as resp_get:
                release_data = json.loads(resp_get.read().decode("utf-8"))
        else:
            err_body = he.read().decode("utf-8", errors="ignore")
            print(f"[ERROR] Error HTTP {he.code} al crear release en GitHub: {err_body}")
            return False
    except Exception as ex:
        print(f"[ERROR] No se pudo crear el release en GitHub: {ex}")
        return False

    if not release_data or "id" not in release_data:
        print("[ERROR] Respuesta inválida de GitHub API al crear el release.")
        return False

    release_id = release_data["id"]
    html_url = release_data.get("html_url", f"https://github.com/{GITHUB_OWNER}/{GITHUB_REPO}/releases/tag/{tag_name}")

    # Eliminar asset previo con el mismo nombre si existía
    for asset in release_data.get("assets", []):
        if asset.get("name") == installer_path.name:
            del_url = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/releases/assets/{asset['id']}"
            try:
                req_del = urllib.request.Request(del_url, headers=headers, method="DELETE")
                with urllib.request.urlopen(req_del, context=ctx, timeout=20):
                    pass
            except Exception:
                pass

    # 3. Subir el archivo .exe a GitHub Releases
    size_mb = installer_path.stat().st_size / (1024 * 1024)
    print(f"[GITHUB] Subiendo instalador {installer_path.name} ({size_mb:.2f} MB) a GitHub Releases...")
    upload_url = (
        f"https://uploads.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/releases/{release_id}/assets"
        f"?name={urllib.parse.quote(installer_path.name)}"
    )
    exe_bytes = installer_path.read_bytes()
    upload_headers = {
        "Authorization": f"token {tok}",
        "Accept": "application/vnd.github+json",
        "Content-Type": "application/vnd.microsoft.portable-executable",
        "Content-Length": str(len(exe_bytes)),
        "User-Agent": f"FacturadorSaint-Publisher/{clean_ver}",
    }

    try:
        req_up = urllib.request.Request(upload_url, data=exe_bytes, headers=upload_headers, method="POST")
        with urllib.request.urlopen(req_up, context=ctx, timeout=300) as resp_up:
            asset_data = json.loads(resp_up.read().decode("utf-8"))
            dl_url = asset_data.get("browser_download_url", "")
            print(f"[GITHUB] ¡Instalador subido exitosamente!")
            print(f"[GITHUB] URL del Release:  {html_url}")
            if dl_url:
                print(f"[GITHUB] Descarga directa: {dl_url}")
            return True
    except Exception as ex:
        print(f"[ERROR] Falló la subida del instalador .exe a GitHub Releases: {ex}")
        return False


def main():
    cur = get_current_version()

    if len(sys.argv) > 1:
        arg = sys.argv[1].strip()
        if arg == "--next-beta":
            eff = get_effective_version()
            print(calculate_next_beta(eff))
            return
        elif arg == "--next-final":
            eff = get_effective_version()
            print(calculate_next_final(eff))
            return
        elif arg == "--current":
            print(cur)
            return
        elif arg == "--effective":
            print(get_effective_version())
            return
        elif arg == "--set-beta":
            eff = get_effective_version()
            target = sys.argv[2].strip() if len(sys.argv) > 2 else calculate_next_beta(eff)
            update_version_in_files(target)
            print(f"Versión actualizada a BETA: {target}")
            return
        elif arg == "--set-final":
            eff = get_effective_version()
            target = sys.argv[2].strip() if len(sys.argv) > 2 else calculate_next_final(eff)
            update_version_in_files(target)
            print(f"Versión actualizada a FINAL: {target}")
            return
        elif arg == "--set" and len(sys.argv) > 2:
            target = sys.argv[2].strip()
            update_version_in_files(target)
            print(f"Versión establecida a: {target}")
            return
        elif arg == "--git-commit":
            target = sys.argv[2].strip() if len(sys.argv) > 2 else cur
            create_git_commit(target)
            return
        elif arg == "--git-push":
            push_to_github()
            return
        elif arg == "--publish-release":
            target = sys.argv[2].strip() if len(sys.argv) > 2 else cur
            ok = publish_github_release(target)
            sys.exit(0 if ok else 1)

    eff = get_effective_version()
    print(f"Versión actual en archivos: {cur} (Efectiva en GitHub: {eff})")
    print(f"Siguiente Beta sugerida:    {calculate_next_beta(eff)}")
    print(f"Siguiente Final sugerida:   {calculate_next_final(eff)}")


if __name__ == "__main__":
    main()


