"""
Extractor de Datos de Facturas / Compras a Consignación de Sigo, S.A
Convierte facturas en PDF a archivos JSON limpios y estructurados.
Normaliza códigos de barra a estándares de 12 y 8 dígitos y extrae todos los precios (Bs. y USD).
"""

import os
import sys
import glob
import re
import json
import argparse
from pathlib import Path
import pymupdf


def parsear_monto_ve(valor_str):
    """
    Convierte montos monetarios en formato venezolano / europeo a float.
    Ejemplo: '2.492,94 Bs.' -> 2492.94, '26,64 $' -> 26.64
    """
    if valor_str is None:
        return 0.0
    # Eliminar símbolos como Bs., $, espacios
    limpio = re.sub(r'[^\d,\.-]', '', str(valor_str)).strip()
    if not limpio:
        return 0.0
    # En formato venezolano el punto es separador de miles y la coma es decimal
    limpio = limpio.replace('.', '').replace(',', '.')
    try:
        return round(float(limpio), 2)
    except ValueError:
        return 0.0


def parsear_cantidad(valor_str):
    """
    Convierte la cantidad a entero si es un numero entero (ej: '5,00' -> 5 en vez de 5.0).
    Si tuviese decimales reales (ej: '5,50' -> 5.5), conserva los decimales necesarios.
    """
    num = parsear_monto_ve(valor_str)
    if num.is_integer():
        return int(num)
    return num


def parsear_tasa_cambio(tasa_str):
    """
    Convierte la tasa de cambio a float (soporta formato con punto o con coma decimal).
    Ejemplo: '$ / 842.2100' -> 842.21, '$ / 849,56' -> 849.56, '285.4000' -> 285.4
    """
    if not tasa_str:
        return 0.0
    tasa_str = str(tasa_str).strip()
    if ',' in tasa_str and '.' in tasa_str:
        limpio = tasa_str.replace('.', '').replace(',', '.')
    elif ',' in tasa_str:
        limpio = tasa_str.replace(',', '.')
    else:
        limpio = tasa_str
    limpio = re.sub(r'[^\d\.]', '', limpio).strip()
    try:
        return round(float(limpio), 4)
    except ValueError:
        return 0.0


def normalizar_codigo_barra(codigo_raw):
    """
    Normaliza el código de barra para que quede estrictamente en 12 u 8 dígitos.
    
    Reglas aplicadas:
    - 8 dígitos (UPC-E / EAN-8): se conserva tal cual.
    - 12 dígitos (UPC-A estándar): se conserva tal cual.
    - 11 dígitos (falta cero inicial del fabricante, ej: 41570015902): se rellena con un cero inicial -> 12 dígitos.
    - 13 dígitos o más:
      * Si tiene 5 o más ceros a la izquierda (ej: 0000003466603, 0000002206705):
        corresponde a un código de 8 dígitos inflado con ceros. Se remueven ceros sobrantes -> 8 dígitos.
      * Si tiene 1 o 2 ceros a la izquierda (ej: 0022000021243, 0686464472005):
        corresponde a un código UPC-A (12 dígitos) empaquetado en formato EAN-13. Se extraen los 12 dígitos significativos.
    """
    codigo = str(codigo_raw).strip()
    if not re.match(r'^\d+$', codigo):
        return codigo, len(codigo), "desconocido"
    
    longitud = len(codigo)
    
    if longitud == 8:
        return codigo, 8, "UPC-E / EAN-8"
    
    if longitud == 12:
        return codigo, 12, "UPC-A"
    
    if longitud == 11:
        # Falta el cero inicial
        codigo_norm = codigo.zfill(12)
        return codigo_norm, 12, "UPC-A (completado con 0 inicial)"
    
    if longitud >= 13:
        if codigo.startswith("00000"):
            # Caso de códigos de 8 dígitos inflados con múltiples ceros
            sin_ceros = codigo.lstrip("0")
            codigo_norm = sin_ceros.zfill(8)
            return codigo_norm, 8, "UPC-E / EAN-8 (ceros excedentes removidos)"
        else:
            # Caso de códigos de 12 dígitos con ceros iniciales de prefijo EAN
            codigo_norm = codigo[-12:]
            return codigo_norm, 12, "UPC-A (ceros excedentes removidos)"
    
    # En caso de longitud atípica < 8 o entre 9 y 10:
    if longitud < 8:
        return codigo.zfill(8), 8, "8_digitos_relleno"
    else:
        return codigo.zfill(12), 12, "12_digitos_relleno"


def parsear_bloque_producto(texto_bloque):
    """
    Parsea el bloque de texto correspondiente a una fila de producto en la factura.
    Soporta:
    1. Formato Órdenes de Compra (ODC) de Sigo (6 montos al final, Total Uds. como cantidad).
    2. Formato Reportes de Facturas de Consignación (FTC) de Sigo (10 valores al final).
    """
    lineas = [linea.strip() for linea in texto_bloque.split('\n') if linea.strip()]
    if len(lineas) < 6 or not re.match(r'^\d+$', lineas[0]):
        return None
    
    codigo_raw = lineas[0]
    
    # -------------------------------------------------------------
    # FORMATO 1: Órdenes de Compra (ODC)
    # Contiene 6 valores monetarios consecutivos al final de la fila:
    # Costo emp. Bs., Costo emp. $, Costo ud. Bs., Costo ud. $, Costo total Bs., Costo total $
    # -------------------------------------------------------------
    money_indices = [i for i, l in enumerate(lineas) if '$' in l]
    if len(money_indices) == 6 and money_indices == list(range(money_indices[0], money_indices[0] + 6)):
        m0 = money_indices[0]
        mid = lineas[1:m0]
        if len(mid) >= 3:
            tot_uds_str = mid[-1]
            m_qty = re.search(r'(\d+[\.,]\d{2})$', tot_uds_str)
            if m_qty:
                tot_uds = float(m_qty.group(1).replace(',', '.'))
                cant = int(tot_uds) if tot_uds.is_integer() else tot_uds
                
                # mid[:-3] contiene la descripción y posiblemente la ref. de proveedor
                prefix = mid[:-3]
                if prefix and (re.match(r'^\d{3,}$', prefix[-1]) or (len(prefix[-1]) <= 6 and not any(c in prefix[-1].upper() for c in ['G', 'KG', 'ML', 'UND', 'UN']))):
                    prefix = prefix[:-1]
                
                descripcion = " ".join(prefix).strip().replace("\ufffd", "'")
                costo_ud_bs = parsear_monto_ve(lineas[m0 + 2])
                costo_ud_usd = parsear_monto_ve(lineas[m0 + 3])
                total_bs = parsear_monto_ve(lineas[m0 + 4])
                total_usd = parsear_monto_ve(lineas[m0 + 5])
                
                codigo_norm, long_norm, tipo_norm = normalizar_codigo_barra(codigo_raw)
                return {
                    "codigo_barra": codigo_norm,
                    "codigo_barra_original": codigo_raw,
                    "longitud_codigo": long_norm,
                    "tipo_codigo": tipo_norm,
                    "descripcion": descripcion,
                    "cantidad": cant,
                    "costo_unitario_bs": costo_ud_bs,
                    "costo_unitario_usd": costo_ud_usd,
                    "subtotal_bs": total_bs,
                    "subtotal_usd": total_usd,
                    "factor_neto": 1.0,
                    "costo_neto_bs": costo_ud_bs,
                    "costo_neto_usd": costo_ud_usd,
                    "total_bs": total_bs,
                    "total_usd": total_usd
                }

    # -------------------------------------------------------------
    # FORMATO 2: Reporte de Facturas de Consignación (FTC)
    # -------------------------------------------------------------
    idx_cant = None
    for i in range(1, len(lineas)):
        if re.match(r'^\d+[\.,]\d{2}$', lineas[i]):
            idx_cant = i
            break
            
    if idx_cant is None:
        return None
        
    descripcion = " ".join(lineas[1:idx_cant]).replace("\ufffd", "'")
    valores = lineas[idx_cant:]
    
    if len(valores) < 10:
        return None
        
    codigo_norm, long_norm, tipo_norm = normalizar_codigo_barra(codigo_raw)
    
    return {
        "codigo_barra": codigo_norm,
        "codigo_barra_original": codigo_raw,
        "longitud_codigo": long_norm,
        "tipo_codigo": tipo_norm,
        "descripcion": descripcion,
        "cantidad": parsear_cantidad(valores[0]),
        "costo_unitario_bs": parsear_monto_ve(valores[1]),
        "costo_unitario_usd": parsear_monto_ve(valores[2]),
        "subtotal_bs": parsear_monto_ve(valores[3]),
        "subtotal_usd": parsear_monto_ve(valores[4]),
        "factor_neto": parsear_monto_ve(valores[5]),
        "costo_neto_bs": parsear_monto_ve(valores[6]),
        "costo_neto_usd": parsear_monto_ve(valores[7]),
        "total_bs": parsear_monto_ve(valores[8]),
        "total_usd": parsear_monto_ve(valores[9])
    }


def extraer_orden_compra_guuao(doc, ruta_pdf):
    """
    Extrae órdenes de compra en Bolívares (Guuao / The Kids World).
    Prioridad de extracción:
      1. Nombre/Descripción del producto
      2. Código de barra normalizado (UPC-A / UPC-E / EAN)
      3. Cantidad exacta
      4. Precios en Bs. (costo unitario y total en Bs.)
    Al ser un formato con precios en Bs., el costo unitario en USD se define en 0.0
    para que Saint tome los precios directamente de su catálogo (Precio 3) sin generar
    alertas de diferencias en USD.
    """
    nombre_archivo = os.path.basename(ruta_pdf)
    p0_texto = doc[0].get_text("text")

    # Número de orden/factura: ej. "Orden de compra #P10283" -> "P10283"
    f_match = re.search(r'Orden de compra\s*#?([A-Za-z0-9_-]+)', p0_texto, re.IGNORECASE)
    numero_factura = f_match.group(1).strip() if f_match else Path(ruta_pdf).stem

    # Fecha de orden
    fecha_match = re.search(r'Fecha de la orden:\s*([^\n]+)', p0_texto, re.IGNORECASE)
    fecha_corte = fecha_match.group(1).strip() if fecha_match else None

    # Destino / Almacén
    envio_match = re.search(r'Direcci[óo]n de env[íi]o\s*\n+([^\n]+)', p0_texto, re.IGNORECASE)
    almacen = envio_match.group(1).strip() if envio_match else "Almacen Principal"

    proveedor = "THE KIDS WORLD 2018, C.A."
    rif = "J-412297244"
    cliente = "GUUAO, C.A." if "GUUAO" in p0_texto.upper() else "Cliente"
    rif_cliente = "J-402385471" if "GUUAO" in p0_texto.upper() else ""

    productos = []
    for page_idx, page in enumerate(doc):
        lines = [l.strip() for l in page.get_text("text").split("\n") if l.strip()]
        i = 0
        while i < len(lines):
            line = lines[i]
            # Patrón de inicio de producto: [CM3645] Nombre del producto...
            m_item = re.match(r'^\[([A-Za-z0-9_-]+)\]\s*(.*)', line)
            if m_item:
                cm_code = m_item.group(1)
                desc_p1 = m_item.group(2).strip()
                desc_parts = [desc_p1] if desc_p1 else []
                i += 1

                barcode = None
                while i < len(lines):
                    cur = lines[i]
                    if re.match(r'^\d{8,14}$', cur):
                        barcode = cur
                        i += 1
                        break
                    elif re.match(r'^\[([A-Za-z0-9_-]+)\]', cur) or "Compra mejor" in cur or "Página" in cur:
                        break
                    else:
                        desc_parts.append(cur)
                        i += 1

                if not barcode:
                    continue

                raw_desc = " ".join(desc_parts).strip().replace("\ufffd", "'")

                # Cantidad (ej. "36,00")
                cant = 1
                if i < len(lines) and re.match(r'^\d+[\.,]\d+$', lines[i]):
                    cant = parsear_cantidad(lines[i])
                    i += 1

                # Unidad de medida (UND, UN, etc.)
                if i < len(lines) and lines[i].upper() in ['UND', 'UN', 'KG', 'G', 'PZA']:
                    i += 1

                # Precio unitario en Bs. (ej. "2.727,712")
                pu_bs = 0.0
                if i < len(lines) and re.match(r'^[\d\.,]+$', lines[i]):
                    pu_bs = parsear_monto_ve(lines[i])
                    i += 1

                # Descuento (ej. "0,00%")
                if i < len(lines) and '%' in lines[i]:
                    i += 1

                # Impuestos (Exento, Compras, etc.)
                while i < len(lines) and any(w in lines[i] for w in ['Exento', 'Compras', 'IVA', '(', ')']):
                    i += 1

                # Importe / Subtotal en Bs. (ej. "98.197,63 Bs")
                tot_bs = 0.0
                if i < len(lines) and ('Bs' in lines[i] or re.match(r'^[\d\.,]+$', lines[i])):
                    tot_bs = parsear_monto_ve(lines[i])
                    i += 1

                norm_code, code_len, code_type = normalizar_codigo_barra(barcode)

                productos.append({
                    "codigo_barra": norm_code,
                    "codigo_barra_original": barcode,
                    "longitud_codigo": code_len,
                    "tipo_codigo": code_type,
                    "descripcion": raw_desc,
                    "cantidad": cant,
                    "costo_unitario_bs": pu_bs,
                    "costo_unitario_usd": 0.0,
                    "subtotal_bs": tot_bs,
                    "subtotal_usd": 0.0,
                    "factor_neto": 1.0,
                    "costo_neto_bs": pu_bs,
                    "costo_neto_usd": 0.0,
                    "total_bs": tot_bs,
                    "total_usd": 0.0,
                    "codigo_interno": cm_code
                })
            else:
                i += 1

    # Extraer totales del pie de la última página
    last_text = doc[-1].get_text("text")
    subtotal_bs = 0.0
    total_bs = 0.0

    sub_m = re.search(r'Subtotal\s*\n+([\d\.,]+)\s*Bs', last_text, re.IGNORECASE)
    if sub_m:
        subtotal_bs = parsear_monto_ve(sub_m.group(1))

    tot_m = re.search(r'Total\s*\n+([\d\.,]+)\s*Bs', last_text, re.IGNORECASE)
    if tot_m:
        total_bs = parsear_monto_ve(tot_m.group(1))

    if total_bs == 0.0 and productos:
        total_bs = round(sum(p["total_bs"] for p in productos), 2)
    if subtotal_bs == 0.0:
        subtotal_bs = total_bs

    doc.close()

    return {
        "factura": numero_factura,
        "archivo_origen": nombre_archivo,
        "proveedor": proveedor,
        "rif_proveedor": rif,
        "cliente": cliente,
        "rif_cliente": rif_cliente,
        "almacen": almacen,
        "fecha_corte": fecha_corte,
        "dias_corte": None,
        "tasa_cambio": 0.0,
        "moneda": "VES",
        "totales": {
            "subtotal_bs": subtotal_bs,
            "subtotal_usd": 0.0,
            "total_bs": total_bs,
            "total_usd": 0.0,
            "nro_items_factura": len(productos),
            "total_items_extraidos": len(productos)
        },
        "productos": productos
    }


def extraer_orden_compra_norkut(doc, ruta_pdf):
    """
    Extrae órdenes de compra del sistema Norkut Cloud (ej. Sigo Boca del Río):
    - Documento: #ODC00002047
    - Proveedor: THE KIDS WORLD 2018, C.A / RIF J-412297244
    - Destino: Almacen Sigo+4 Boca del Rio / Cliente: SIGO, S.A.
    - Columnas: Productos | Barra | Cantidad | Costo unitario (VES) | Des
    - Resumen de costos: Total costos, Subtotal y Total en VES y USD
    - Convierte costos unitarios a USD usando la tasa de la orden
    """
    nombre_archivo = os.path.basename(ruta_pdf)
    p0_texto = doc[0].get_text("text")

    # Documento (ej. "ODC00002047")
    doc_m = re.search(r'Documento:\s*#?([A-Za-z0-9_-]+)', p0_texto)
    numero_factura = doc_m.group(1) if doc_m else Path(ruta_pdf).stem

    # Fecha
    fecha_m = re.search(r'Fecha:\s*(\d{1,2}/\d{1,2}/\d{4})', p0_texto)
    fecha_corte = fecha_m.group(1) if fecha_m else None

    # Proveedor
    proveedor = "THE KIDS WORLD 2018, C.A"
    rif_proveedor = "J-412297244"
    prov_m = re.search(r'Proveedor\s*\n+([^\n]+)', p0_texto)
    if prov_m:
        proveedor = prov_m.group(1).strip()

    # Destino / Almacén / Cliente
    almacen = "Almacen Sigo+4 Boca del Rio"
    alm_m = re.search(r'Tienda\s*\n+([^\n]+)', p0_texto)
    if alm_m:
        almacen = alm_m.group(1).strip()

    cliente = "SIGO, S.A."
    rif_cliente = "J-080030486"

    # Totales y Tasa de cambio desde el resumen de costos (última página)
    last_text = doc[-1].get_text("text")
    total_bs = 0.0
    total_usd = 0.0
    subtotal_bs = 0.0
    subtotal_usd = 0.0

    tot_m = re.search(r'Total\s*\n+([\d\.,]+)\s*VES\s*\n+([\d\.,]+)\s*USD', last_text, re.IGNORECASE)
    if tot_m:
        total_bs = parsear_monto_ve(tot_m.group(1))
        total_usd = parsear_monto_ve(tot_m.group(2))

    costos_m = re.search(r'Total costos\s*\n+([\d\.,]+)\s*VES\s*\n+([\d\.,]+)\s*USD', last_text, re.IGNORECASE)
    if costos_m:
        subtotal_bs = parsear_monto_ve(costos_m.group(1))
        subtotal_usd = parsear_monto_ve(costos_m.group(2))
    else:
        sub_m = re.search(r'Subtotal\s*\n+([\d\.,]+)\s*VES\s*\n+([\d\.,]+)\s*USD', last_text, re.IGNORECASE)
        if sub_m:
            subtotal_bs = parsear_monto_ve(sub_m.group(1))
            subtotal_usd = parsear_monto_ve(sub_m.group(2))

    tasa = round(total_bs / total_usd, 4) if total_usd > 0 else 0.0

    productos = []
    for page in doc:
        lines = [l.strip() for l in page.get_text("text").splitlines() if l.strip()]
        i = 0
        while i < len(lines):
            if lines[i] in ("Des", "Des."):
                i += 1
                break
            i += 1

        while i < len(lines):
            if lines[i] in ("Total unidades", "RESUMEN DE COSTOS") or "core.norkut-cloud" in lines[i]:
                break

            desc = lines[i]
            i += 1
            if i >= len(lines):
                break

            barcode_raw = lines[i]
            if not re.match(r'^\d+$', barcode_raw):
                desc += " " + barcode_raw
                i += 1
                if i >= len(lines):
                    break
                barcode_raw = lines[i]

            i += 1
            if i >= len(lines):
                break

            qty_str = lines[i]
            i += 1
            if i >= len(lines):
                break

            cost_str = lines[i]
            i += 1

            if i < len(lines) and lines[i].endswith("%"):
                i += 1

            try:
                cant = int(qty_str)
            except ValueError:
                try:
                    cant = int(float(qty_str.replace(",", ".")))
                except ValueError:
                    cant = 1

            pu_bs = parsear_monto_ve(cost_str)
            pu_usd = round(pu_bs / tasa, 2) if tasa > 0 else 0.0

            tot_item_bs = round(cant * pu_bs, 2)
            tot_item_usd = round(cant * pu_usd, 2)

            norm_code, code_len, code_type = normalizar_codigo_barra(barcode_raw)

            productos.append({
                "codigo_barra": norm_code,
                "codigo_barra_original": barcode_raw,
                "longitud_codigo": code_len,
                "tipo_codigo": code_type,
                "descripcion": desc,
                "cantidad": cant,
                "costo_unitario_bs": pu_bs,
                "costo_unitario_usd": pu_usd,
                "subtotal_bs": tot_item_bs,
                "subtotal_usd": tot_item_usd,
                "factor_neto": 1.0,
                "costo_neto_bs": pu_bs,
                "costo_neto_usd": pu_usd,
                "total_bs": tot_item_bs,
                "total_usd": tot_item_usd
            })

    if total_bs == 0.0 and productos:
        total_bs = round(sum(p["total_bs"] for p in productos), 2)
    if total_usd == 0.0 and productos:
        total_usd = round(sum(p["total_usd"] for p in productos), 2)
    if subtotal_bs == 0.0:
        subtotal_bs = total_bs
    if subtotal_usd == 0.0:
        subtotal_usd = total_usd

    doc.close()

    return {
        "factura": numero_factura,
        "archivo_origen": nombre_archivo,
        "proveedor": proveedor,
        "rif_proveedor": rif_proveedor,
        "cliente": cliente,
        "rif_cliente": rif_cliente,
        "almacen": almacen,
        "fecha_corte": fecha_corte,
        "dias_corte": None,
        "tasa_cambio": tasa,
        "moneda": "USD/VES",
        "totales": {
            "subtotal_bs": subtotal_bs,
            "subtotal_usd": subtotal_usd,
            "total_bs": total_bs,
            "total_usd": total_usd,
            "nro_items_factura": len(productos),
            "total_items_extraidos": len(productos)
        },
        "productos": productos
    }


def extraer_factura_pdf(ruta_pdf):
    """
    Extrae toda la información de una factura en PDF:
    - Cabecera y metadatos generales
    - Lista de productos con códigos de barra y precios
    - Totales de la factura
    """
    doc = pymupdf.open(ruta_pdf)
    nombre_archivo = os.path.basename(ruta_pdf)
    
    # Extraer texto de cabecera de la página 1
    p0_texto = doc[0].get_text("text")
    
    # Formatos existentes: Órdenes de Compra (ODC) y Facturas de Consignación (FTC) de Sigo
    factura_match = re.search(r'((?:FTC|ODC)-[\w-]+)', p0_texto)
    if not factura_match:
        # Detectar Formato Norkut Cloud / Sigo Boca del Río (#ODC... o core.norkut-cloud)
        last_page_text = doc[-1].get_text("text") if len(doc) > 0 else ""
        if "norkut-cloud" in p0_texto.lower() or "norkut-cloud" in last_page_text.lower() or re.search(r'Documento:\s*#?ODC\d+', p0_texto, re.IGNORECASE):
            return extraer_orden_compra_norkut(doc, ruta_pdf)

        # Detectar Formato 3: Órdenes de Compra en Bolívares (Guuao / The Kids World)
        if re.search(r'Orden de compra\s*#?[A-Za-z0-9_-]+', p0_texto, re.IGNORECASE) or "GUUAO" in p0_texto.upper() or re.search(r'\[[A-Za-z0-9_-]+\]', p0_texto):
            return extraer_orden_compra_guuao(doc, ruta_pdf)

    numero_factura = factura_match.group(1) if factura_match else Path(ruta_pdf).stem
    
    tasa_match = re.search(r'\$\s*/\s*([\d\.,]+)', p0_texto)
    tasa_cambio = parsear_tasa_cambio(tasa_match.group(1)) if tasa_match else 0.0
    
    corte_match = re.search(r'Fecha corte de venta:\s*([^\n]+)', p0_texto)
    fecha_corte = corte_match.group(1).strip() if corte_match else None
    if not fecha_corte:
        aut_match = re.search(r'Fecha autorizada:\s*\n*([^\n]+)', p0_texto)
        if aut_match:
            fecha_corte = aut_match.group(1).strip()
        else:
            f_match = re.search(r'(\d{1,2}/\d{1,2}/\d{4})', p0_texto)
            fecha_corte = f_match.group(1).strip() if f_match else None
    
    dias_corte_match = re.search(r'D[ií]as de corte:\s*(\d+)', p0_texto)
    dias_corte = int(dias_corte_match.group(1)) if dias_corte_match else None
    
    # Proveedor y RIF
    proveedor = "THE KIDS WORLD 2018, C.A"
    rif = "J-412297244"
    prov_match = re.search(r'Proveedor\s*\n+([^\n]+)\s*\n+(\d+)', p0_texto)
    if prov_match:
        proveedor = prov_match.group(1).strip()
        rif = prov_match.group(2).strip()
    
    # Extraer todos los productos en todas las páginas
    productos = []
    for num_pagina, pagina in enumerate(doc):
        bloques = pagina.get_text("blocks")
        for bloque in bloques:
            texto = bloque[4]
            # Identificar si es bloque de producto
            if ('Bs.' in texto or '$' in texto) and len(texto.split('\n')) >= 6:
                prod = parsear_bloque_producto(texto)
                if prod:
                    productos.append(prod)
    
    # Extraer totales del pie de la última página
    ultima_pag = doc[-1]
    last_text = ultima_pag.get_text("text")
    
    subtotal_bs = 0.0
    subtotal_usd = 0.0
    total_bs = 0.0
    total_usd = 0.0
    
    # Intentar búsqueda directa de montos de orden (ej. 'Total orden\n... 2.595.983,50 Bs. / 3.055,68 $')
    tot_m = re.search(r'([\d\.,]+)\s*Bs\.\s*/\s*([\d\.,]+)\s*\$', last_text)
    if tot_m:
        total_bs = parsear_monto_ve(tot_m.group(1))
        total_usd = parsear_monto_ve(tot_m.group(2))
        subtotal_bs = total_bs
        subtotal_usd = total_usd
    else:
        # Buscar bloques numéricos en la sección de totales (y > 680) de FTC
        for b in ultima_pag.get_text("blocks"):
            if b[1] > 680:
                # Subtotales
                if 80 <= b[0] <= 90 and 710 <= b[1] <= 725:
                    partes = b[4].strip().split('\n')
                    if len(partes) >= 2:
                        subtotal_bs = parsear_monto_ve(partes[0])
                        subtotal_usd = parsear_monto_ve(partes[1])
                # Total Bs.
                elif 80 <= b[0] <= 90 and 785 <= b[1] <= 798:
                    total_bs = parsear_monto_ve(b[4])
                # Total USD
                elif 265 <= b[0] <= 275 and 785 <= b[1] <= 798:
                    total_usd = parsear_monto_ve(b[4])
                
    # Nro de ítems reportado en el documento
    nro_items_match = re.search(r'Nro de [^\n]*tems:\s*(\d+)', last_text, re.IGNORECASE)
    nro_items_doc = int(nro_items_match.group(1)) if nro_items_match else len(productos)
    
    # Si por algún motivo no se extrajeron los totales del pie, sumar los ítems directamente
    if total_bs == 0.0 and productos:
        total_bs = round(sum(p["total_bs"] for p in productos), 2)
    if total_usd == 0.0 and productos:
        total_usd = round(sum(p["total_usd"] for p in productos), 2)
    if subtotal_bs == 0.0:
        subtotal_bs = total_bs
    if subtotal_usd == 0.0:
        subtotal_usd = total_usd

    doc.close()
    
    return {
        "factura": numero_factura,
        "archivo_origen": nombre_archivo,
        "proveedor": proveedor,
        "rif_proveedor": rif,
        "almacen": "Almacen Principal",
        "fecha_corte": fecha_corte,
        "dias_corte": dias_corte,
        "tasa_cambio": tasa_cambio,
        "moneda": "USD/VES",
        "totales": {
            "subtotal_bs": subtotal_bs,
            "subtotal_usd": subtotal_usd,
            "total_bs": total_bs,
            "total_usd": total_usd,
            "nro_items_factura": nro_items_doc,
            "total_items_extraidos": len(productos)
        },
        "productos": productos
    }


def extraer_presupuesto_excel(ruta_excel):
    """
    Extrae la informacion de un presupuesto o catalogo en formato Excel (.xlsx / .xls):
    - Cliente, RIF, Fecha, Empresa
    - Lista de productos con codigos de barra normalizados (8 y 12 digitos), cantidades enteras y precios en USD
    - Totales generales
    """
    import openpyxl
    wb = openpyxl.load_workbook(ruta_excel, data_only=True)
    ws = wb.active
    nombre_archivo = os.path.basename(ruta_excel)
    nombre_doc = os.path.splitext(nombre_archivo)[0]

    empresa = ws.cell(1, 1).value or "THE KIDS WORLD 2018 C.A."
    tipo_doc = ws.cell(2, 1).value or "Presupuesto"
    cliente = ws.cell(4, 2).value or ""
    fecha = ws.cell(4, 5).value or ""
    rif_cliente = ws.cell(5, 2).value or ""

    # Buscar fila de encabezados
    header_row = 7
    for r in range(1, 15):
        val = str(ws.cell(r, 2).value or "")
        if "Producto" in val:
            header_row = r
            break

    productos = []
    total_usd = 0.0
    total_uds = 0

    for r in range(header_row + 1, ws.max_row + 1):
        col1 = str(ws.cell(r, 1).value or "").strip()
        if "TOTAL" in col1.upper():
            total_uds = ws.cell(r, 4).value
            total_usd = ws.cell(r, 6).value
            break

        prod_desc = ws.cell(r, 2).value
        cb_val = ws.cell(r, 3).value
        cant_val = ws.cell(r, 4).value
        pu_val = ws.cell(r, 5).value
        sub_val = ws.cell(r, 6).value

        if not prod_desc or cb_val is None:
            continue

        clean_desc = " ".join(str(prod_desc).split())
        cb_raw = str(cb_val).strip()
        cb_norm, cb_len, cb_tipo = normalizar_codigo_barra(cb_raw)

        cant = int(cant_val) if isinstance(cant_val, (int, float)) and float(cant_val).is_integer() else cant_val
        pu = round(float(pu_val), 2) if pu_val is not None else 0.0
        sub = round(float(sub_val), 2) if sub_val is not None else round(cant * pu, 2)

        productos.append({
            "codigo_barra": cb_norm,
            "codigo_barra_original": cb_raw,
            "longitud_codigo": cb_len,
            "tipo_codigo": cb_tipo,
            "descripcion": clean_desc,
            "cantidad": cant,
            "costo_unitario_usd": pu,
            "precio_unitario_usd": pu,
            "subtotal_usd": sub,
            "total_usd": sub
        })

    wb.close()

    total_usd_final = round(float(total_usd), 2) if total_usd else round(sum(p["total_usd"] for p in productos), 2)
    total_uds_final = int(total_uds) if total_uds else sum(p["cantidad"] for p in productos)

    return {
        "factura": nombre_doc,
        "archivo_origen": nombre_archivo,
        "tipo_documento": str(tipo_doc).strip(),
        "proveedor": str(empresa).strip(),
        "cliente": str(cliente).strip(),
        "rif_cliente": str(rif_cliente).strip(),
        "fecha": str(fecha).strip(),
        "moneda": "USD",
        "totales": {
            "total_usd": total_usd_final,
            "total_unidades": total_uds_final,
            "nro_items_factura": len(productos),
            "total_items_extraidos": len(productos)
        },
        "productos": productos
    }


def procesar_archivos(rutas_archivos, carpeta_salida):
    """
    Procesa una lista de rutas de archivos (PDF o Excel) y genera unicamente un archivo JSON por cada uno.
    Cada JSON incluye todos los productos del documento.
    """
    os.makedirs(carpeta_salida, exist_ok=True)
    
    facturas_procesadas = []
    total_archivos = len(rutas_archivos)
    print(f"\n=======================================================")
    print(f" Iniciando extraccion de {total_archivos} documentos (PDF / Excel)")
    print(f" Carpeta de salida: {os.path.abspath(carpeta_salida)}")
    print(f" (Se genera exactamente 1 archivo JSON por cada documento)")
    print(f"=======================================================\n")
    
    for idx, ruta in enumerate(rutas_archivos, 1):
        try:
            nombre = os.path.basename(ruta)
            ext = os.path.splitext(nombre)[1].lower()
            print(f"[{idx}/{total_archivos}] Procesando: {nombre} ...", end=" ")
            
            if ext in (".xlsx", ".xls"):
                datos_factura = extraer_presupuesto_excel(ruta)
            elif ext == ".pdf":
                datos_factura = extraer_factura_pdf(ruta)
            else:
                print("Omitido (formato no soportado)")
                continue

            if not datos_factura["productos"]:
                print("Omitido (sin productos / no es factura o presupuesto)")
                continue
                
            # Guardar JSON individual por cada archivo con el mismo nombre que el documento original
            base_nombre = Path(ruta).stem
            nombre_json = f"{base_nombre}.json"
            ruta_json = os.path.join(carpeta_salida, nombre_json)
            with open(ruta_json, "w", encoding="utf-8") as f:
                json.dump(datos_factura, f, indent=2, ensure_ascii=False)
                
            facturas_procesadas.append(datos_factura)
            print(f"OK ({len(datos_factura['productos'])} productos)")
            
        except Exception as e:
            print(f"ERROR: {str(e)}")
            
    print(f"\nProceso finalizado con exito:")
    print(f"- Archivos JSON generados: {len(facturas_procesadas)}")
    print(f"- Total de productos procesados: {sum(len(f['productos']) for f in facturas_procesadas)}")
    print(f"- Archivos guardados en: {os.path.abspath(carpeta_salida)}\n")
    
    return facturas_procesadas


def encontrar_pdfs_por_defecto():
    """
    Busca archivos PDF y Excel en carpetas comunes si el usuario no especifica ninguna:
    1. Carpeta 'facturas_pdf' (carpeta dedicada para colocar las facturas y presupuestos)
    2. Carpeta actual
    """
    exts = ("*.pdf", "*.xlsx", "*.xls")
    
    # 1. Carpeta dedicada 'facturas_pdf'
    carpeta_entrada = "facturas_pdf"
    os.makedirs(carpeta_entrada, exist_ok=True)
    archivos_entrada = []
    for ext in exts:
        archivos_entrada.extend(glob.glob(os.path.join(carpeta_entrada, ext)))
    if archivos_entrada:
        return sorted(archivos_entrada)

    # 2. Carpeta actual
    archivos_locales = []
    for ext in exts:
        archivos_locales.extend(glob.glob(ext))
    if archivos_locales:
        return sorted(archivos_locales)
        
    return []


def main():
    parser = argparse.ArgumentParser(
        description="Extractor de datos de facturas PDF y Excel a JSON con normalizacion de codigos de barra (12 y 8 digitos)."
    )
    parser.add_argument(
        "-i", "--input", 
        help="Ruta a un archivo o carpeta con archivos PDF/Excel (por defecto: 'facturas_pdf').",
        default=None
    )
    parser.add_argument(
        "-o", "--output", 
        help="Carpeta donde se guardaran los archivos JSON (por defecto: 'facturas_json').",
        default="facturas_json"
    )
    args = parser.parse_args()
    
    rutas_archivos = []
    if args.input:
        if os.path.isfile(args.input):
            rutas_archivos = [args.input]
        elif os.path.isdir(args.input):
            for ext in ("*.pdf", "*.xlsx", "*.xls"):
                rutas_archivos.extend(glob.glob(os.path.join(args.input, ext)))
            rutas_archivos = sorted(rutas_archivos)
        else:
            print(f"Error: La ruta especificada no existe: {args.input}")
            sys.exit(1)
    else:
        rutas_archivos = encontrar_pdfs_por_defecto()
        
    if not rutas_archivos:
        print("No se encontraron archivos PDF o Excel para procesar.")
        print("Por favor coloca tus archivos en la carpeta 'facturas_pdf' o especifica la ruta:")
        print("  python extractor.py --input <carpeta_o_archivo>")
        sys.exit(1)
        
    procesar_archivos(rutas_archivos, args.output)


if __name__ == "__main__":
    main()
