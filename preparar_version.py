"""
Script utilitario para gestionar el ciclo de versiones de Facturador Saint.
Maneja transiciones automáticas:
- Versión actual: 2.61
- Betas: 2.61.1-beta, 2.61.2-beta, etc.
- Final siguiente: 2.62
"""

import sys
import re
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent
UPDATER_PY = ROOT_DIR / "updater.py"
INSTALADOR_ISS = ROOT_DIR / "instalador.iss"


def get_current_version() -> str:
    content = UPDATER_PY.read_text(encoding="utf-8")
    m = re.search(r'CURRENT_VERSION\s*=\s*"([^"]+)"', content)
    if m:
        return m.group(1).strip()
    return "2.61"


def calculate_next_beta(cur: str) -> str:
    # Si cur es '2.61', patch es 0 -> '2.61.1-beta'
    # Si cur es '2.61.1-beta', patch es 1 -> '2.61.2-beta'
    m = re.match(r"^(\d+\.\d+)(?:\.(\d+))?(?:-beta.*)?$", cur.strip())
    if m:
        base = m.group(1)
        patch = int(m.group(2) or 0)
        return f"{base}.{patch + 1}-beta"
    return f"{cur}.1-beta"


def calculate_next_final(cur: str) -> str:
    # Si cur es '2.61' o '2.61.X-beta' -> '2.62'
    m = re.match(r"^(\d+)\.(\d+)", cur.strip())
    if m:
        major = int(m.group(1))
        minor = int(m.group(2))
        return f"{major}.{minor + 1}"
    return "2.62"


def update_version_in_files(new_ver: str):
    # 1. Actualizar updater.py
    u_content = UPDATER_PY.read_text(encoding="utf-8")
    u_new = re.sub(r'CURRENT_VERSION\s*=\s*"[^"]+"', f'CURRENT_VERSION = "{new_ver}"', u_content)
    UPDATER_PY.write_text(u_new, encoding="utf-8")

    # 2. Actualizar instalador.iss
    i_content = INSTALADOR_ISS.read_text(encoding="utf-8")
    i_new = re.sub(r'#define\s+MyAppVersion\s+"[^"]+"', f'#define MyAppVersion "{new_ver}"', i_content)
    INSTALADOR_ISS.write_text(i_new, encoding="utf-8")


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

    print(f"Versión actual: {cur}")
    print(f"Siguiente Beta sugerida:  {next_beta}")
    print(f"Siguiente Final sugerida: {next_final}")


if __name__ == "__main__":
    main()
