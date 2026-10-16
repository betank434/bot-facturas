"""
Script utilitario para gestionar el ciclo de versiones y commits de Facturador Saint.
Maneja transiciones automáticas:
- Versión actual: ej. 2.62
- Betas: 2.62.1-beta, 2.62.2-beta, etc.
- Final siguiente: 2.63
- Creación automática del commit en Git listo para 'Push origin' en GitHub Desktop.
"""

import os
import sys
import re
import glob
import shutil
import subprocess
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent
UPDATER_PY = ROOT_DIR / "updater.py"
INSTALADOR_ISS = ROOT_DIR / "instalador.iss"


def get_current_version() -> str:
    content = UPDATER_PY.read_text(encoding="utf-8")
    m = re.search(r'CURRENT_VERSION\s*=\s*"([^"]+)"', content)
    if m:
        return m.group(1).strip()
    return "2.62"


def calculate_next_beta(cur: str) -> str:
    # Si cur es '2.62', patch es 0 -> '2.62.1-beta'
    # Si cur es '2.62.1-beta', patch es 1 -> '2.62.2-beta'
    m = re.match(r"^(\d+\.\d+)(?:\.(\d+))?(?:-beta.*)?$", cur.strip())
    if m:
        base = m.group(1)
        patch = int(m.group(2) or 0)
        return f"{base}.{patch + 1}-beta"
    return f"{cur}.1-beta"


def calculate_next_final(cur: str) -> str:
    # Si cur es '2.62' o '2.62.X-beta' -> '2.63'
    m = re.match(r"^(\d+)\.(\d+)", cur.strip())
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
    y genera automáticamente el commit local listo para hacer 'Push origin' en GitHub Desktop.
    """
    git_exe = find_git_executable()
    try:
        # Asegurar identidad de autor en el repositorio local para evitar errores en PCs nuevas
        res_name = subprocess.run([git_exe, "config", "user.name"], cwd=ROOT_DIR, capture_output=True, text=True)
        if res_name.returncode != 0 or not res_name.stdout.strip():
            subprocess.run([git_exe, "config", "user.name", "betank434"], cwd=ROOT_DIR, check=False)

        res_email = subprocess.run([git_exe, "config", "user.email"], cwd=ROOT_DIR, capture_output=True, text=True)
        if res_email.returncode != 0 or not res_email.stdout.strip():
            subprocess.run([git_exe, "config", "user.email", "betank01@gmail.com"], cwd=ROOT_DIR, check=False)

        # Agregar todos los cambios del proyecto (respetando .gitignore)
        subprocess.run([git_exe, "add", "-A"], cwd=ROOT_DIR, check=True)

        # Verificar si hay cambios pendientes para confirmar
        status_res = subprocess.run([git_exe, "status", "--porcelain"], cwd=ROOT_DIR, capture_output=True, text=True)
        if not status_res.stdout.strip():
            print(f"[GIT] El repositorio ya está al día para v{new_ver}.")
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


def main():
    cur = get_current_version()
    next_beta = calculate_next_beta(cur)
    next_final = calculate_next_final(cur)

    if len(sys.argv) > 1:
        arg = sys.argv[1].strip()
        if arg == "--next-beta":
            print(next_beta)
            return
        elif arg == "--next-final":
            print(next_final)
            return
        elif arg == "--current":
            print(cur)
            return
        elif arg == "--set-beta":
            target = sys.argv[2].strip() if len(sys.argv) > 2 else next_beta
            update_version_in_files(target)
            print(f"Versión actualizada a BETA: {target}")
            return
        elif arg == "--set-final":
            target = sys.argv[2].strip() if len(sys.argv) > 2 else next_final
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

    print(f"Versión actual: {cur}")
    print(f"Siguiente Beta sugerida:  {next_beta}")
    print(f"Siguiente Final sugerida: {next_final}")


if __name__ == "__main__":
    main()

