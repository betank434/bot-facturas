"""
Generador de app_icon.ico para Facturador Saint
Crea un icono profesional con resoluciones 16x16, 32x32, 48x48, 64x64, 128x128, 256x256.
"""

from PIL import Image, ImageDraw

def generar_icono(salida_ico="app_icon.ico"):
    size = 256
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Fondo redondeado azul oscuro / tecnológico
    bg_color = (15, 23, 42, 255)       # #0f172a
    border_color = (56, 189, 248, 255) # #38bdf8 (cyan)
    
    # Dibujar cuadro redondeado de fondo
    margin = 12
    draw.rounded_rectangle(
        [margin, margin, size - margin, size - margin],
        radius=48,
        fill=bg_color,
        outline=border_color,
        width=8
    )

    # Dibujar silueta de hoja de factura
    sheet_left = 60
    sheet_top = 45
    sheet_right = 196
    sheet_bottom = 215
    draw.rounded_rectangle(
        [sheet_left, sheet_top, sheet_right, sheet_bottom],
        radius=14,
        fill=(30, 41, 59, 255),       # #1e293b
        outline=(148, 163, 184, 255), # #94a3b8
        width=4
    )

    # Líneas de factura en la hoja
    for y in [75, 95, 115]:
        draw.line([(80, y), (176, y)], fill=(100, 116, 139, 255), width=4)

    # Rayo estilizado moderno en el centro / frente
    rayo_pts = [
        (145, 100),
        (105, 155),
        (130, 155),
        (110, 205),
        (165, 140),
        (138, 140),
        (158, 100)
    ]
    # Sombra del rayo
    sombra_pts = [(x + 2, y + 2) for (x, y) in rayo_pts]
    draw.polygon(sombra_pts, fill=(2, 132, 199, 200))
    # Relleno del rayo
    draw.polygon(rayo_pts, fill=(250, 204, 21, 255), outline=(255, 255, 255, 255))

    # Guardar en archivo .ico con todos los tamaños estándar de Windows
    tamanos = [(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
    img.save(salida_ico, format="ICO", sizes=tamanos)
    print(f"[OK] Icono generado exitosamente: {salida_ico}")

if __name__ == "__main__":
    generar_icono()
