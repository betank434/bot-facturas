"""
Script de compilacion de Facturador Saint a ejecutable nativo de Windows (.exe)
Utiliza PyInstaller con empaquetado optimizado, icono oficial y sin consola.
"""

import sys
import shutil
from pathlib import Path
import PyInstaller.__main__

def compilar():
    base_dir = Path(__file__).resolve().parent
    main_script = base_dir / "facturador_saint.py"
    icon_path = base_dir / "app_icon.ico"
    dist_dir = base_dir / "dist"
    build_dir = base_dir / "build"

    print("==================================================")
    print("   COMPILANDO FACTURADOR SAINT A .EXE (WINDOWS)   ")
    print("==================================================")

    pyinstaller_args = [
        str(main_script),
        "--name=FacturadorSaint",
        "--onedir",
        "--noconsole",
        "--clean",
        f"--icon={str(icon_path)}",
        "--hidden-import=pymupdf",
        "--hidden-import=fitz",
        "--hidden-import=pyperclip",
        "--hidden-import=PIL",
        "--hidden-import=extractor",
        "--hidden-import=saint_keyboard_engine",
        "--hidden-import=winocr",
        f"--distpath={str(dist_dir)}",
        f"--workpath={str(build_dir)}",
        "--noconfirm",
    ]

    print("Ejecutando PyInstaller con los siguientes argumentos:")
    for arg in pyinstaller_args:
        print(f"  {arg}")

    PyInstaller.__main__.run(pyinstaller_args)

    # Copiar recursos iniciales y carpetas a la carpeta de distribucion
    app_dist_dir = dist_dir / "FacturadorSaint"
    if app_dist_dir.exists():
        print("\nCopiando archivos de configuracion y carpetas base a dist/FacturadorSaint/...")
        
        # Carpetas requeridas (deben crearse totalmente limpias y vacias para el usuario)
        for folder_name in ["facturas_pdf", "facturas_json", "cache_capturas"]:
            dst_f = app_dist_dir / folder_name
            dst_f.mkdir(parents=True, exist_ok=True)
            # Limpiar cualquier archivo residual
            for item in dst_f.glob("*"):
                if item.is_file():
                    try:
                        item.unlink()
                    except Exception:
                        pass

        # Archivos de configuracion e icono
        for fname in ["app_icon.ico", "codigos_reemplazo.json", "config_facturador.json"]:
            src_file = base_dir / fname
            if src_file.exists():
                shutil.copy2(src_file, app_dist_dir / fname)

        print("\n[OK] Compilacion completada con exito!")
        print(f"Ejecutable generado en: {app_dist_dir / 'FacturadorSaint.exe'}")
    else:
        print("\n[ERROR] No se encontro el directorio de salida de PyInstaller.")
        sys.exit(1)

if __name__ == "__main__":
    compilar()
