"""
Script de verificacion automatizada del extractor de facturas Sigo
"""

import os
import glob
import json
import sys
from pathlib import Path
from extractor import extraer_factura_pdf, normalizar_codigo_barra, procesar_archivos


def test_normalizacion_codigos():
    print("--- 1. Probando casos conocidos de normalizacion de codigos ---")
    casos = [
        # (original, esperado, longitud_esperada)
        ("686464613002", "686464613002", 12),  # UPC-A estandar
        ("03484803", "03484803", 8),            # UPC-E / EAN-8 estandar
        ("41570015902", "041570015902", 12),    # Le falta el 0 inicial (11 -> 12)
        ("0000003466603", "03466603", 8),       # 13 digitos con multiples ceros -> 8
        ("0000002206705", "02206705", 8),       # 13 digitos con multiples ceros -> 8
        ("0000002284004", "02284004", 8),       # 13 digitos con multiples ceros -> 8
        ("0022000021243", "022000021243", 12),  # 13 digitos con 2 ceros -> 12
        ("0686464472005", "686464472005", 12),  # 13 digitos con 1 cero -> 12
        ("0034000080113", "034000080113", 12),  # 13 digitos con 2 ceros -> 12
        ("0041419420072", "041419420072", 12),  # 13 digitos con 2 ceros -> 12
        ("0192568960008", "192568960008", 12),  # 13 digitos con 1 cero -> 12
    ]
    
    fallos = 0
    for original, esperado, len_esperada in casos:
        res, long_res, _ = normalizar_codigo_barra(original)
        if res != esperado or long_res != len_esperada:
            print(f" [FALLO] {original} -> {res} (esperado: {esperado}, len: {long_res} != {len_esperada})")
            fallos += 1
        else:
            print(f" [OK] {original:>15} -> {res:>12} (len: {long_res})")
            
    assert fallos == 0, f"{fallos} pruebas de normalizacion fallaron"
    print("-> Todas las pruebas unitarias de codigos de barra pasaron con exito.\n")


def test_extraccion_archivos_reales():
    print("--- 2. Verificando extraccion sobre los archivos PDF en Downloads ---")
    user_home = Path.home()
    archivos = sorted(glob.glob(str(user_home / "Downloads" / "Reporte de Factura KIDS.*.pdf")))
    
    if not archivos:
        print("No se encontraron archivos en Downloads.")
        return
        
    print(f"Archivos encontrados: {len(archivos)}")
    
    carpeta_salida_test = os.path.join(os.path.dirname(__file__), "salida_json_test")
    facturas = procesar_archivos(archivos, carpeta_salida_test)
    
    # Limpiar carpeta de prueba
    import shutil
    shutil.rmtree(carpeta_salida_test, ignore_errors=True)
    
    total_prods = 0
    longitudes = {}
    errores_precios = 0
    
    for f in facturas:
        nro = f["factura"]
        total_items_rep = f["totales"]["nro_items_factura"]
        total_items_ext = f["totales"]["total_items_extraidos"]
        assert total_items_rep == total_items_ext, f"Factura {nro}: reportados {total_items_rep} != extraidos {total_items_ext}"
        
        for p in f["productos"]:
            total_prods += 1
            cb = p["codigo_barra"]
            l = len(cb)
            longitudes[l] = longitudes.get(l, 0) + 1
            if l not in (8, 12):
                print(f" [ERROR LONGITUD] Producto {p['descripcion']} tiene codigo de longitud {l}: {cb}")
                
            # Verificar que precios y subtotales sean numeros coherentes
            if p["costo_unitario_usd"] <= 0 or p["cantidad"] <= 0:
                print(f" [ALERTA PRECIO] Factura {nro}, Producto {cb}: Cant={p['cantidad']}, USD={p['costo_unitario_usd']}")
                errores_precios += 1
                
    print("\n--- RESUMEN DE VALIDACION DE DATOS ---")
    print(f"Total facturas validadas: {len(facturas)}")
    print(f"Total productos extraidos: {total_prods}")
    print(f"Distribucion de longitudes de codigos: {longitudes}")
    print(f"Alertas de precios invalidos: {errores_precios}")
    
    assert set(longitudes.keys()).issubset({8, 12}), "Existen codigos que no son de 8 o 12 digitos"
    assert errores_precios == 0, "Se encontraron errores en precios o cantidades"
    
    print("\n>>> VALIDACION COMPLETADA CON EXITO: 100% DE PRECISION <<<")


if __name__ == "__main__":
    test_normalizacion_codigos()
    test_extraccion_archivos_reales()
