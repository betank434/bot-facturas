"""
Pruebas automatizadas para el Bot Facturador de Saint Enterprise
"""

import os
import json
import glob
from pathlib import Path
from saint_keyboard_engine import KeyboardBotEngine
import saint_keyboard_engine


def test_json_files():
    print("--- 1. Probando carga de archivos JSON en facturas_json ---")
    json_dir = Path("facturas_json")
    files = list(json_dir.glob("*.json"))
    assert len(files) > 0, "No se encontraron archivos JSON"
    
    total_items = 0
    for f in sorted(files):
        with open(f, "r", encoding="utf-8") as fp:
            data = json.load(fp)
        factura = data.get("factura", "N/A")
        prods = data.get("productos", [])
        total_items += len(prods)
        print(f" [OK] {f.name:<26} | Factura: {factura:<20} | {len(prods)} productos")
        
        for p in prods:
            assert "codigo_barra" in p, f"Falta codigo_barra en {f.name}"
            assert "cantidad" in p, f"Falta cantidad en {f.name}"

    print(f"-> Total facturas verificadas: {len(files)} con {total_items} productos en total.\n")


def test_engine_config_and_dryrun():
    print("--- 2. Probando configuracion y ejecucion simulada del motor ---")
    engine = KeyboardBotEngine()
    
    engine.config["countdown_seconds"] = 1
    engine.config["delay_between_items"] = 0.01
    engine.config["delay_after_barcode"] = 0.01
    engine.config["delay_after_qty"] = 0.01
    engine.config["test_mode"] = True
    
    sample_items = [
        {"codigo_barra": "686464613002", "cantidad": 5, "descripcion": "PRODUCTO DE PRUEBA 1"},
        {"codigo_barra": "03484803", "cantidad": 2, "descripcion": "PRODUCTO DE PRUEBA 2"}
    ]
    
    logs = []
    engine.on_log = lambda msg: logs.append(msg)
    
    started_items = []
    finished_items = []
    engine.on_item_started = lambda idx, item: started_items.append(idx)
    engine.on_item_finished = lambda idx, item, succ: finished_items.append(idx)
    
    # Interceptar llamadas Win32 para no emitir teclas durante pruebas
    typed_events = []
    saint_keyboard_engine.win32_type_string = lambda text, key_delay=0.03, stop_checker=None: typed_events.append(("STR", str(text)))
    saint_keyboard_engine.win32_press_vk = lambda vk, delay_after=0.05: typed_events.append(("VK", vk))
    
    engine._run_typing_loop(sample_items)
    
    assert len(started_items) == 2, f"Expected 2 started items, got {len(started_items)}"
    assert len(finished_items) == 2, f"Expected 2 finished items, got {len(finished_items)}"
    assert any("686464613002" in str(x) for x in typed_events), "No se registro tipeo simulado de item 1"
    assert any("03484803" in str(x) for x in typed_events), "No se registro tipeo simulado de item 2"
    
    print(" [OK] Simulación de eventos nativos completada.")
    print(" [OK] Eventos de inicio/fin de ítems recibidos correctamente.")
    print("-> Pruebas del motor pasaron al 100%.\n")


def test_facturador_saint_price_realtime():
    print("--- 3. Probando detección de diferencias de precio en tiempo real (Opción 2) ---")
    import facturador_saint
    
    # 3.1 Parser de precios (soporta VE/EU y US con miles y decimales)
    assert facturador_saint.parse_price("2.492,94") == 2492.94
    assert facturador_saint.parse_price("2,492.94") == 2492.94
    assert facturador_saint.parse_price("4,825.11") == 4825.11
    assert facturador_saint.parse_price("4.825,11") == 4825.11
    assert facturador_saint.parse_price("2,96") == 2.96
    assert facturador_saint.parse_price("$ 2.96") == 2.96
    assert facturador_saint.parse_price("Bs. 1.776.574,62") == 1776574.62
    assert facturador_saint.parse_price("5.70") == 5.70
    print(" [OK] parse_price soporta formatos VE/EU (coma) y US (punto).")

    # 3.2 Diferencia detectada -> Sobrescribir (overwrite en Modo Precio 0)
    engine = facturador_saint.FacturadorSaintEngine()
    engine.config.update({
        "test_mode": True, "countdown_seconds": 0, "delay_after_client": 0.001,
        "delay_after_barcode": 0.001, "delay_after_qty": 0.001, "delay_between_items": 0.001,
        "price_list_mode": "precio_0", "check_price_realtime": True, "price_alert_mode": "instant",
        "price_currency": "usd", "price_nav_mode": "enter", "mock_price_str": "3.50"
    })
    typed_log = []
    facturador_saint.win32_type_string = lambda text, **kw: typed_log.append(("STR", str(text)))
    facturador_saint.win32_press_vk = lambda vk, **kw: typed_log.append(("VK", vk))

    diff_calls = []
    engine.on_price_difference = lambda it, s, e, c: (diff_calls.append((s, e, c)), "overwrite")[1]

    item = {"codigo_barra": "686464613002", "cantidad": 2, "costo_unitario_usd": 2.96, "descripcion": "CHUPETA KIDSMANIA"}
    engine._run_loop([item])

    assert len(diff_calls) == 1, "Debió activarse la alerta de diferencia"
    assert diff_calls[0] == (3.50, 2.96, "$"), f"Parámetros incorrectos: {diff_calls[0]}"
    assert any("2.96" in str(x) for x in typed_log), "Debió escribirse el precio corregido 2.96"
    print(" [OK] Alerta activada y sobrescritura de precio correcta en Modo Precio 0.")

    # 3.3 Precio coincidente -> Sin alerta
    engine.config["mock_price_str"] = "2.96"
    diff_calls.clear()
    engine._run_loop([item])
    assert len(diff_calls) == 0, "No debió activarse alerta si los precios coinciden"
    print(" [OK] Precio coincidente verificado sin interrupciones.")

    # 3.4 Modo Resumen al final en Precio 0
    engine.config.update({
        "mock_price_str": "3.50",
        "price_alert_mode": "summary",
        "press_f6_at_end": True
    })
    typed_log.clear()
    diff_calls.clear()
    fin_calls = []
    engine.on_invoice_finished = lambda succ, diffs=None: fin_calls.append((succ, diffs))
    engine._run_loop([item])
    assert len(diff_calls) == 0, "En modo resumen NO debe interrumpir con preguntas por ítem"
    assert len(engine.price_differences) == 1, "Debió registrar la diferencia para el resumen"
    assert not any(v == facturador_saint.VK_F6 for (t, v) in typed_log), "NO debió presionar F6 por haber diferencias"
    print(" [OK] Modo Resumen al final funciona correctamente (no interrumpe y previene F6 accidental).")
    print("-> Pruebas de la Opción 2 completadas al 100%.\n")


def test_precio_3_batch_ocr():
    print("--- 4. Probando Modo Precio 3: Capturas por lote (8 productos) + OCR Local + Borrado de Caché ---")
    import facturador_saint

    # 4.1 Verificación de detección de cuadrícula Saint
    from PIL import Image
    sample_img = Image.new("RGB", (1024, 600), color=(255, 255, 255))
    grid_info = facturador_saint.find_saint_grid_region(sample_img)
    assert "grid_top" in grid_info and "grid_bottom" in grid_info
    assert "precio_x1" in grid_info and "precio_x2" in grid_info
    assert grid_info["row_height"] == 49.0
    print(" [OK] find_saint_grid_region detecta geometría de cuadrícula y altura fija de fila (49px).")

    # 4.2 Verificación de tipeo directo en Precio 3 y lotes cada 8 productos
    engine = facturador_saint.FacturadorSaintEngine()
    engine.config.update({
        "test_mode": True, "countdown_seconds": 0, "delay_after_client": 0.001,
        "delay_after_barcode": 0.001, "delay_after_qty": 0.001, "delay_between_items": 0.001,
        "price_list_mode": "precio_3", "verify_price_by_ocr": True, "press_f6_at_end": True,
        "batch_size": 8
    })
    typed_log = []
    facturador_saint.win32_type_string = lambda text, **kw: typed_log.append(("STR", str(text)))
    facturador_saint.win32_press_vk = lambda vk, **kw: typed_log.append(("VK", vk))

    # Simular una factura de 40 productos (con lotes a los ítems 8, 16, 24, 32 y lote final 40)
    sample_40 = []
    for i in range(1, 41):
        sample_40.append({
            "codigo_barra": f"7591000{i:04d}",
            "cantidad": 1,
            "costo_unitario_usd": 2.50 if i != 15 and i != 38 else 3.00,
            "descripcion": f"PRODUCTO NUMERO {i}"
        })

    # Simular que en Saint todos los productos tienen precio 2.50
    # Por lo tanto los ítems 15 (en lote 2: 9-16) y 38 (en lote 5: 33-40) tendrán diferencia
    engine.config["mock_price_str"] = "2.50"

    ocr_rows_alerted = []
    engine.on_ocr_diff_row = lambda d: ocr_rows_alerted.append(d["row"])

    finished_calls = []
    engine.on_invoice_finished = lambda succ, diffs=None: finished_calls.append((succ, diffs))

    cache_events = []
    engine.on_cache_updated = lambda: cache_events.append(True)

    engine._run_loop(sample_40)

    # Validar que los ítems 15 y 38 fueron detectados con diferencia
    assert len(finished_calls) == 1, "Debió finalizar la factura"
    succ, diffs = finished_calls[0]
    assert succ is True
    diff_list = diffs.get("price_differences", diffs) if isinstance(diffs, dict) else diffs
    diff_rows = [d["row"] for d in diff_list]
    assert 15 in diff_rows, f"Falta ítem 15 en diferencias: {diff_rows}"
    assert 38 in diff_rows, f"Falta ítem 38 en diferencias: {diff_rows}"
    print(f" [OK] Diferencias detectadas en lotes de 8 productos: Filas {diff_rows}")

    # Validar que al haber diferencias NO se presionó la tecla F6
    assert not any(v == facturador_saint.VK_F6 for (t, v) in typed_log), "NO debió presionar F6 por haber diferencias"
    print(" [OK] Bloqueo automático de guardado F6 ante diferencias de precio verificado.")

    # 4.3 Verificación de la carpeta local cache_capturas y botón/función de borrado de caché
    # Limpiar primero por si había algo previo
    facturador_saint.borrar_cache_capturas()
    assert facturador_saint.contar_archivos_cache() == 0, "El caché debió quedar en 0"

    # Crear capturas de prueba en cache_capturas/
    test_img = Image.new("RGB", (300, 200), color=(100, 150, 200))
    test_file_1 = facturador_saint.CACHE_CAPTURES_DIR / "captura_test_lote_1.png"
    test_file_2 = facturador_saint.CACHE_CAPTURES_DIR / "captura_test_lote_2.png"
    test_img.save(test_file_1)
    test_img.save(test_file_2)

    assert facturador_saint.contar_archivos_cache() == 2, f"Debió contar 2 capturas, contó {facturador_saint.contar_archivos_cache()}"
    print(f" [OK] Almacenamiento local en cache_capturas/ verificado: {facturador_saint.contar_archivos_cache()} archivos.")

    # Ejecutar borrado de caché (simulando clic en botón '🧹 Borrar Caché')
    borrados = facturador_saint.borrar_cache_capturas()
    assert borrados == 2, f"Debió borrar 2 archivos, borró {borrados}"
    assert facturador_saint.contar_archivos_cache() == 0, "El caché debe estar vacío tras el borrado"
    print(" [OK] Función borrar_cache_capturas() probada exitosamente: caché limpio a 0.")

    # Validar que ningún archivo temporal quedó en la raíz del proyecto
    temp_root_images = list(Path(".").glob("*.png")) + list(Path(".").glob("*.jpg")) + list(Path(".").glob("*.bmp"))
    assert len(temp_root_images) == 0, f"Se encontraron imágenes temporales en raíz: {temp_root_images}"
    print(" [OK] Raíz del proyecto completamente limpia de archivos temporales.")
    print("-> Pruebas del Modo Precio 3, Lotes de 8 y Caché Local completadas al 100%.\n")


def test_factura_split_43_items():
    print("--- 5. Probando División Automática de Facturas (Máximo 43 Productos) ---")
    import facturador_saint
    import tkinter as tk

    root = tk.Tk()
    root.withdraw()
    app = facturador_saint.FacturadorApp(root)

    # 5.1 Factura de 40 productos (<= 43) -> 1 sola parte
    prods_40 = [{"codigo_barra": f"7591000{i:04d}", "cantidad": 1, "costo_unitario_usd": 10.0, "subtotal_usd": 10.0} for i in range(1, 41)]
    parts_40 = app._split_into_parts(prods_40, tasa=840.0)
    assert len(parts_40) == 1, f"Expected 1 part for 40 items, got {len(parts_40)}"
    assert parts_40[0]["count"] == 40
    assert parts_40[0]["start_idx"] == 1 and parts_40[0]["end_idx"] == 40
    assert parts_40[0]["total_usd"] == 400.0
    print(" [OK] Factura <= 43 productos se mantiene como 1 sola factura.")

    # 5.2 Factura de 50 productos -> 2 partes: 43 y 7
    prods_50 = [{"codigo_barra": f"7591000{i:04d}", "cantidad": 2, "costo_unitario_usd": 5.0, "subtotal_usd": 10.0} for i in range(1, 51)]
    parts_50 = app._split_into_parts(prods_50, tasa=840.0)
    assert len(parts_50) == 2, f"Expected 2 parts for 50 items, got {len(parts_50)}"
    assert parts_50[0]["count"] == 43
    assert parts_50[0]["start_idx"] == 1 and parts_50[0]["end_idx"] == 43
    assert parts_50[0]["total_usd"] == 430.0
    assert parts_50[1]["count"] == 7
    assert parts_50[1]["start_idx"] == 44 and parts_50[1]["end_idx"] == 50
    assert parts_50[1]["total_usd"] == 70.0
    print(" [OK] Factura de 50 productos dividida exactamente en Parte 1 (43) y Parte 2 (7).")

    # 5.3 Factura de 95 productos -> 3 partes: 43, 43 y 9
    prods_95 = [{"codigo_barra": f"7591000{i:04d}", "cantidad": 1, "costo_unitario_usd": 2.0, "subtotal_usd": 2.0} for i in range(1, 96)]
    parts_95 = app._split_into_parts(prods_95, tasa=840.0)
    assert len(parts_95) == 3, f"Expected 3 parts for 95 items, got {len(parts_95)}"
    assert parts_95[0]["count"] == 43
    assert parts_95[1]["count"] == 43
    assert parts_95[2]["count"] == 9
    sum_usd = sum(p["total_usd"] for p in parts_95)
    assert sum_usd == 190.0, f"Expected total $190.0, got {sum_usd}"
    print(" [OK] Factura de 95 productos dividida exactamente en Parte 1 (43), Parte 2 (43) y Parte 3 (9).")

    # 5.4 Límite de seguridad en el motor: si recibe > 43 productos, limita a 43
    engine = facturador_saint.FacturadorSaintEngine()
    engine.config.update({"test_mode": True, "countdown_seconds": 0, "max_items_per_invoice": 43})
    items_typed = []
    engine.on_item_started = lambda idx, it: items_typed.append(idx)
    facturador_saint.win32_type_string = lambda text, **kw: None
    facturador_saint.win32_press_vk = lambda vk, **kw: None
    engine._run_loop(prods_50)  # Le pasamos 50 ítems directamente
    assert len(items_typed) == 43, f"Engine should have capped at 43 items, got {len(items_typed)}"
    print(" [OK] FacturadorSaintEngine respeta estrictamente el límite de 43 productos por factura.")

    root.destroy()
    print("-> Pruebas de División de Facturas completadas al 100%.\n")


def test_no_client_and_direct_product_typing():
    print("--- 6. Probando inicio directo en cuadrícula sin escribir Cliente ni 2 ENTERs ---")
    import facturador_saint
    engine = facturador_saint.FacturadorSaintEngine()
    engine.config.update({"test_mode": True, "countdown_seconds": 0})
    
    typed_keys = []
    facturador_saint.win32_type_string = lambda text, **kw: typed_keys.append(("STR", text))
    facturador_saint.win32_press_vk = lambda vk, **kw: typed_keys.append(("VK", vk))

    sample_items = [
        {"codigo_barra": "75910000001", "cantidad": 2, "descripcion": "PRODUCTO 1"}
    ]
    engine._run_loop(sample_items)
    
    # Verificar que el primer string tipeado sea el código de barra del primer ítem
    first_str = next(val for (k, val) in typed_keys if k == "STR")
    assert first_str == "75910000001", f"El primer elemento tipeado debía ser el código de producto, pero fue: {first_str}"
    # Verificar que NO se tipea ningún RIF de cliente
    assert not any("J-080030486" in str(val) for (k, val) in typed_keys), "No se debió escribir RIF de cliente"
    print(" [OK] El motor no escribe Cliente ni emite los 2 ENTERs iniciales.")
    print(" [OK] El tipeo inicia directamente con el código de barra en la celda activa de Referencia.")
    print("-> Verificación de inicio directo completada al 100%.\n")


def test_extractor_button_and_json_refresh():
    print("--- 7. Probando Boton de Extractor y Refresco Automatico de JSONs ---")
    import facturador_saint
    import tkinter as tk

    root = tk.Tk()
    root.withdraw()
    app = facturador_saint.FacturadorApp(root)

    # 7.1 Verificar existencia y configuración del botón de extractor
    assert hasattr(app, "btn_extractor"), "El botón btn_extractor debe existir en FacturadorApp"
    assert "Extractor" in app.btn_extractor.cget("text"), f"Texto incorrecto en botón: {app.btn_extractor.cget('text')}"
    print(" [OK] Boton 'Ejecutar Extractor' integrado correctamente al lado de Examinar JSON.")

    # 7.2 Probar refresco con selección automática del archivo más reciente
    app._scan_json_files(select_latest=True)
    selected_name = app.cbo_facturas.get()
    assert selected_name != "", "Debe haber seleccionado un archivo JSON tras el refresco"
    assert len(app.items_list) > 0, "Debe haber cargado los productos del JSON seleccionado"
    print(f" [OK] Refresco automatico selecciono el JSON mas reciente: {selected_name} ({len(app.items_list)} productos).")

    root.destroy()
    print("-> Pruebas de Extractor y Refresco completadas al 100%.\n")


def test_codigo_intercambio_tab():
    print("--- 8. Probando Pestaña de Intercambio de Códigos y Persistencia de Reglas ---")
    import facturador_saint
    import tkinter as tk

    root = tk.Tk()
    root.withdraw()
    app = facturador_saint.FacturadorApp(root)

    # 8.1 Verificar existencia del Notebook y componentes de ambas pestañas
    assert hasattr(app, "notebook"), "El widget notebook debe existir en FacturadorApp"
    assert hasattr(app, "tab_facturacion"), "Debe existir tab_facturacion"
    assert hasattr(app, "tab_codigos"), "Debe existir tab_codigos"
    assert hasattr(app, "tree_rules"), "Debe existir tree_rules"
    assert hasattr(app, "ent_code_src"), "Debe existir ent_code_src"
    assert hasattr(app, "ent_code_dst"), "Debe existir ent_code_dst"
    assert hasattr(app, "ent_code_desc"), "Debe existir ent_code_desc"
    assert hasattr(app, "btn_save_rule"), "Debe existir btn_save_rule"
    assert hasattr(app, "btn_toggle_rule"), "Debe existir btn_toggle_rule"
    assert hasattr(app, "chk_rule_activo"), "Debe existir chk_rule_activo"
    assert hasattr(app, "var_rule_activo"), "Debe existir var_rule_activo"
    assert hasattr(app, "btn_del_rule"), "Debe existir btn_del_rule"
    assert hasattr(app, "btn_clear_rule"), "Debe existir btn_clear_rule"
    print(" [OK] Pestaña 'Intercambio de Códigos', formulario y tabla integrados.")

    # 8.2 Verificar carga de reglas iniciales (incluyendo Pistacho Wonderful por defecto)
    assert len(app.replacement_rules) >= 1, "Debe tener al menos 1 regla cargada"
    assert any(r.get("codigo_origen") == "014113701808" for r in app.replacement_rules), "Falta regla por defecto Pistacho"
    print(f" [OK] Reglas iniciales cargadas correctamente ({len(app.replacement_rules)} regla(s)).")

    # 8.3 Probar alternar estado activo/inactivo (marcar y desmarcar)
    pistacho_item_id = "rule_0"
    assert app.tree_rules.exists(pistacho_item_id), "Debe existir rule_0 en el treeview"
    initial_active = app.replacement_rules[0].get("activo", True)
    
    # Alternar (desmarcar o marcar)
    app._toggle_rule_active_by_id(pistacho_item_id)
    assert app.replacement_rules[0].get("activo") == (not initial_active), "El estado activo debió cambiar"
    
    # Verificar persistencia en archivo
    with open(app.rules_file, "r", encoding="utf-8") as fp:
        saved_rules = json.load(fp)
    assert saved_rules[0].get("activo") == (not initial_active), "El estado cambiado debió guardarse en JSON"
    
    # Restaurar al estado inicial
    app._toggle_rule_active_by_id(pistacho_item_id)
    assert app.replacement_rules[0].get("activo") == initial_active, "El estado inicial debió restaurarse"
    print(" [OK] Alternado de estado (Activo/Inactivo) verificado y persistido correctamente.")

    # 8.4 Probar persistencia de regla nueva
    test_src = "TEST_SRC_9999"
    test_dst = "TEST_DST_8888"
    app.replacement_rules.append({
        "codigo_origen": test_src,
        "codigo_destino": test_dst,
        "descripcion": "PRODUCTO DE PRUEBA",
        "activo": True
    })
    app._save_replacement_rules()
    app._refresh_rules_table()

    with open(app.rules_file, "r", encoding="utf-8") as fp:
        saved_rules = json.load(fp)
    assert any(r.get("codigo_origen") == test_src for r in saved_rules), "La regla de prueba no se guardó en JSON"
    print(" [OK] Archivo codigos_reemplazo.json persistido y sincronizado con éxito.")

    # Limpiar regla de prueba para dejar el estado limpio
    app.replacement_rules = [r for r in app.replacement_rules if r.get("codigo_origen") != test_src]
    app._save_replacement_rules()
    app._refresh_rules_table()

    root.destroy()
    print("-> Pruebas de Intercambio de Códigos completadas al 100%.\n")


def test_norkut_odc_extraction():
    print("--- 9. Probando Extracción de Orden de Compra Norkut Cloud (Sigo Boca del Río) ---")
    import extractor
    pdf_path = Path("facturas_pdf/ODC- THE KIDS WORLD ALMACEN 29-09-2026.pdf")
    if not pdf_path.exists():
        print(" [OMITIDO] No se encontró el archivo de prueba en facturas_pdf.")
        return

    data = extractor.extraer_factura_pdf(str(pdf_path))
    assert data["factura"] == "ODC00002047", f"Factura incorrecta: {data['factura']}"
    assert len(data["productos"]) == 74, f"Se esperaban 74 productos, se obtuvieron {len(data['productos'])}"
    assert data["totales"]["subtotal_bs"] == 4821771.36
    assert data["totales"]["total_bs"] == 4825820.61
    assert data["totales"]["total_usd"] == 5625.24
    assert data["tasa_cambio"] > 800.0
    assert all(len(p["codigo_barra"]) in (8, 12, 13, 14) for p in data["productos"])
    print(f" [OK] ODC {data['factura']} extraída exitosamente: {len(data['productos'])} productos, Total Bs: {data['totales']['total_bs']:,.2f}, Total USD: ${data['totales']['total_usd']:,.2f}")
    print("-> Pruebas de Formato Norkut Cloud completadas al 100%.\n")


if __name__ == "__main__":
    test_json_files()
    test_engine_config_and_dryrun()
    test_facturador_saint_price_realtime()
    test_precio_3_batch_ocr()
    test_factura_split_43_items()
    test_no_client_and_direct_product_typing()
    test_extractor_button_and_json_refresh()
    test_codigo_intercambio_tab()
    test_norkut_odc_extraction()
    print("=== TODAS LAS PRUEBAS COMPLETADAS EXITOSAMENTE ===")



