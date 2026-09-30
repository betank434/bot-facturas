"""
Bot de Teclado Virtual para Facturación en Saint Annual Enterprise.
Permite cargar automáticamente los ítems de las facturas JSON en Saint
simulando pulsaciones de teclado sin alterar el software ni la base de datos.
"""

import os
import sys
import json
import glob
from pathlib import Path
import tkinter as tk
from tkinter import ttk, messagebox, filedialog

from saint_keyboard_engine import KeyboardBotEngine


class BotFacturadorSaintApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Bot Teclado Virtual - Facturación Saint Annual Enterprise")
        self.root.geometry("920x680")
        self.root.minsize(800, 560)
        
        # Ruta base
        self.base_dir = Path(__file__).resolve().parent
        self.json_dir = self.base_dir / "facturas_json"
        
        # Estado y datos
        self.engine = KeyboardBotEngine()
        self.loaded_data = None
        self.current_json_path = None
        self.items_list = []
        
        # Configurar callbacks del motor
        self.engine.on_log = self._on_bot_log
        self.engine.on_state_change = self._on_bot_state_change
        self.engine.on_countdown = self._on_bot_countdown
        self.engine.on_item_started = self._on_bot_item_started
        self.engine.on_item_finished = self._on_bot_item_finished
        
        # Iniciar listener de atajos globales F8, F7, F12
        self.engine.start_hotkey_listener(
            on_f8=self._hotkey_start,
            on_f7=self._hotkey_pause,
            on_f12=self._hotkey_stop
        )
        
        # Construir Interfaz Gráfica
        self._setup_styles()
        self._build_ui()
        
        # Cargar lista inicial de facturas
        self._scan_json_files()

        # Protocolo de cierre
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    def _setup_styles(self):
        style = ttk.Style(self.root)
        style.theme_use("clam")
        
        # Colores
        self.c_bg = "#f4f6f9"
        self.c_card = "#ffffff"
        self.c_primary = "#1a56db"
        self.c_success = "#16a34a"
        self.c_warning = "#d97706"
        self.c_danger = "#dc2626"
        self.c_text = "#1f2937"
        
        self.root.configure(bg=self.c_bg)
        
        style.configure("TFrame", background=self.c_bg)
        style.configure("Card.TFrame", background=self.c_card, relief="solid", borderwidth=1)
        style.configure("TLabel", background=self.c_bg, foreground=self.c_text, font=("Segoe UI", 9))
        style.configure("Header.TLabel", font=("Segoe UI", 12, "bold"), foreground="#111827")
        style.configure("CardTitle.TLabel", font=("Segoe UI", 10, "bold"), background=self.c_card, foreground="#374151")
        style.configure("CardValue.TLabel", font=("Segoe UI", 11, "bold"), background=self.c_card, foreground=self.c_primary)
        style.configure("CardMuted.TLabel", font=("Segoe UI", 9), background=self.c_card, foreground="#6b7280")
        
        style.configure("TNotebook", background=self.c_bg)
        style.configure("TNotebook.Tab", font=("Segoe UI", 9, "bold"), padding=[12, 6])
        
        # Estilos para botones
        style.configure("Start.TButton", font=("Segoe UI", 10, "bold"), foreground="white", background=self.c_success)
        style.map("Start.TButton", background=[("active", "#15803d"), ("disabled", "#9ca3af")])
        
        style.configure("Pause.TButton", font=("Segoe UI", 10, "bold"), foreground="white", background=self.c_warning)
        style.map("Pause.TButton", background=[("active", "#b45309"), ("disabled", "#9ca3af")])
        
        style.configure("Stop.TButton", font=("Segoe UI", 10, "bold"), foreground="white", background=self.c_danger)
        style.map("Stop.TButton", background=[("active", "#b91c1c"), ("disabled", "#9ca3af")])

    def _build_ui(self):
        # 1. Barra Superior con Título y TopMost
        top_bar = tk.Frame(self.root, bg="#1e293b", height=45)
        top_bar.pack(fill="x", side="top")
        
        lbl_app = tk.Label(top_bar, text="⚡ BOT FACTURADOR SAINT | TECLADO VIRTUAL", 
                           font=("Segoe UI", 11, "bold"), fg="#38bdf8", bg="#1e293b")
        lbl_app.pack(side="left", padx=15, pady=8)
        
        self.var_topmost = tk.BooleanVar(value=False)
        self.root.wm_attributes("-topmost", False)
        chk_top = tk.Checkbutton(top_bar, text="📌 Mantener siempre visible (TopMost)", 
                                 variable=self.var_topmost, command=self._toggle_topmost,
                                 font=("Segoe UI", 9), fg="#e2e8f0", bg="#1e293b", selectcolor="#0f172a",
                                 activebackground="#1e293b", activeforeground="#ffffff")
        chk_top.pack(side="right", padx=15)

        # Contenedor Principal
        main_frame = ttk.Frame(self.root, padding="12")
        main_frame.pack(fill="both", expand=True)

        # 2. Panel Selector de Archivo JSON
        sel_card = ttk.Frame(main_frame, style="Card.TFrame", padding="10")
        sel_card.pack(fill="x", pady=(0, 10))
        
        lbl_sel = ttk.Label(sel_card, text="Factura JSON a procesar:", font=("Segoe UI", 9, "bold"), background=self.c_card)
        lbl_sel.pack(side="left", padx=(0, 8))
        
        self.cbo_facturas = ttk.Combobox(sel_card, state="readonly", width=42, font=("Segoe UI", 9))
        self.cbo_facturas.pack(side="left", padx=4)
        self.cbo_facturas.bind("<<ComboboxSelected>>", self._on_combo_selected)
        
        btn_refresh = ttk.Button(sel_card, text="🔄 Refrescar", command=self._scan_json_files)
        btn_refresh.pack(side="left", padx=4)
        
        btn_browse = ttk.Button(sel_card, text="📂 Examinar otro...", command=self._browse_json)
        btn_browse.pack(side="left", padx=4)

        # 3. Tarjeta Informativa de la Factura
        self.card_info = ttk.Frame(main_frame, style="Card.TFrame", padding="10")
        self.card_info.pack(fill="x", pady=(0, 10))
        
        row1 = ttk.Frame(self.card_info, style="Card.TFrame")
        row1.pack(fill="x")
        
        self.lbl_factura_num = ttk.Label(row1, text="Factura: --", style="CardTitle.TLabel")
        self.lbl_factura_num.pack(side="left", padx=(0, 20))
        
        self.lbl_proveedor = ttk.Label(row1, text="Proveedor/Cliente: --", style="CardMuted.TLabel")
        self.lbl_proveedor.pack(side="left", padx=(0, 20))
        
        self.lbl_items_count = ttk.Label(row1, text="Ítems: 0", style="CardTitle.TLabel")
        self.lbl_items_count.pack(side="right")

        row2 = ttk.Frame(self.card_info, style="Card.TFrame")
        row2.pack(fill="x", pady=(4, 0))
        
        self.lbl_monto_usd = ttk.Label(row2, text="Total USD: $ 0.00", style="CardValue.TLabel")
        self.lbl_monto_usd.pack(side="left", padx=(0, 25))
        
        self.lbl_monto_bs = ttk.Label(row2, text="Total Bs.: Bs. 0,00", style="CardTitle.TLabel")
        self.lbl_monto_bs.pack(side="left", padx=(0, 25))
        
        self.lbl_tasa = ttk.Label(row2, text="Tasa: --", style="CardMuted.TLabel")
        self.lbl_tasa.pack(side="left")

        # 4. Pestañas Centrales: Ítems y Configuración
        notebook = ttk.Notebook(main_frame)
        notebook.pack(fill="both", expand=True, pady=(0, 10))
        
        tab_items = ttk.Frame(notebook, padding="6")
        notebook.add(tab_items, text="📦 Lista de Productos")
        
        tab_config = ttk.Frame(notebook, padding="10")
        notebook.add(tab_config, text="⚙️ Configuración de Teclas (Saint)")

        # --- Contenido Pestaña 1: Tabla de Productos ---
        cols = ("num", "codigo", "descripcion", "cantidad", "costo_usd", "costo_bs", "estado")
        self.tree = ttk.Treeview(tab_items, columns=cols, show="headings", height=10)
        
        self.tree.heading("num", text="#")
        self.tree.heading("codigo", text="Código de Barra")
        self.tree.heading("descripcion", text="Descripción del Producto")
        self.tree.heading("cantidad", text="Cant.")
        self.tree.heading("costo_usd", text="Precio/Costo $")
        self.tree.heading("costo_bs", text="Precio/Costo Bs.")
        self.tree.heading("estado", text="Estado")
        
        self.tree.column("num", width=35, anchor="center")
        self.tree.column("codigo", width=120, anchor="center")
        self.tree.column("descripcion", width=320, anchor="w")
        self.tree.column("cantidad", width=55, anchor="center")
        self.tree.column("costo_usd", width=95, anchor="e")
        self.tree.column("costo_bs", width=110, anchor="e")
        self.tree.column("estado", width=100, anchor="center")
        
        tree_scroll = ttk.Scrollbar(tab_items, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=tree_scroll.set)
        self.tree.pack(side="left", fill="both", expand=True)
        tree_scroll.pack(side="right", fill="y")
        
        # Tags de colores para la tabla
        self.tree.tag_configure("pending", foreground="#374151")
        self.tree.tag_configure("active", background="#fef08a", foreground="#854d0e", font=("Segoe UI", 9, "bold"))
        self.tree.tag_configure("done", background="#dcfce7", foreground="#166534")
        self.tree.tag_configure("skip", background="#f3f4f6", foreground="#9ca3af")

        # --- Contenido Pestaña 2: Configuración de Teclas ---
        self._build_config_tab(tab_config)

        # 5. Panel de Control y Estado
        ctrl_card = ttk.Frame(main_frame, style="Card.TFrame", padding="10")
        ctrl_card.pack(fill="x", pady=(0, 6))
        
        ctrl_top = ttk.Frame(ctrl_card, style="Card.TFrame")
        ctrl_top.pack(fill="x", pady=(0, 6))
        
        self.lbl_estado = tk.Label(ctrl_top, text="● LISTO", font=("Segoe UI", 11, "bold"), 
                                   fg="#16a34a", bg=self.c_card)
        self.lbl_estado.pack(side="left")
        
        self.lbl_progress_txt = ttk.Label(ctrl_top, text="0 de 0 productos cargados", 
                                          style="CardMuted.TLabel")
        self.lbl_progress_txt.pack(side="right")
        
        self.progress_bar = ttk.Progressbar(ctrl_card, mode="determinate")
        self.progress_bar.pack(fill="x", pady=(0, 8))
        
        # Botones de Acción
        btn_frame = ttk.Frame(ctrl_card, style="Card.TFrame")
        btn_frame.pack(fill="x")
        
        self.btn_start = tk.Button(btn_frame, text="▶ INICIAR FACTURACIÓN (F8)", 
                                   font=("Segoe UI", 10, "bold"), fg="white", bg=self.c_success,
                                   activebackground="#15803d", activeforeground="white",
                                   padx=16, pady=6, relief="flat", cursor="hand2",
                                   command=self.start_typing)
        self.btn_start.pack(side="left", padx=(0, 8))
        
        self.btn_pause = tk.Button(btn_frame, text="⏸ PAUSAR / REANUDAR (F7)", 
                                   font=("Segoe UI", 10, "bold"), fg="white", bg=self.c_warning,
                                   activebackground="#b45309", activeforeground="white",
                                   padx=14, pady=6, relief="flat", cursor="hand2",
                                   command=self.pause_typing, state="disabled")
        self.btn_pause.pack(side="left", padx=(0, 8))
        
        self.btn_stop = tk.Button(btn_frame, text="⏹ DETENER (F12 / ESC)", 
                                  font=("Segoe UI", 10, "bold"), fg="white", bg=self.c_danger,
                                  activebackground="#b91c1c", activeforeground="white",
                                  padx=14, pady=6, relief="flat", cursor="hand2",
                                  command=self.stop_typing, state="disabled")
        self.btn_stop.pack(side="left", padx=(0, 8))

        # 6. Mini Consola de Registro (Log)
        log_frame = ttk.Frame(main_frame)
        log_frame.pack(fill="x")
        
        lbl_log = ttk.Label(log_frame, text="Registro de acciones:", font=("Segoe UI", 8))
        lbl_log.pack(anchor="w")
        
        self.txt_log = tk.Text(log_frame, height=3, font=("Consolas", 8), bg="#ffffff", fg="#374151",
                               relief="solid", borderwidth=1, state="disabled")
        self.txt_log.pack(fill="x")

    def _build_config_tab(self, parent):
        grid = ttk.Frame(parent)
        grid.pack(fill="both", expand=True)
        
        # Fila 0: Cuenta regresiva
        ttk.Label(grid, text="Tiempo de espera antes de comenzar (segundos):", font=("Segoe UI", 9, "bold")).grid(row=0, column=0, sticky="w", pady=4)
        self.var_countdown = tk.IntVar(value=3)
        spn_countdown = ttk.Spinbox(grid, from_=1, to=10, textvariable=self.var_countdown, width=5)
        spn_countdown.grid(row=0, column=1, sticky="w", pady=4, padx=10)
        ttk.Label(grid, text="(Tiempo para hacer clic dentro de la ventana de Saint)").grid(row=0, column=2, sticky="w", pady=4)

        # Fila 1: Tecla de confirmación
        ttk.Label(grid, text="Tecla para avanzar de campo:", font=("Segoe UI", 9, "bold")).grid(row=1, column=0, sticky="w", pady=4)
        self.var_key_confirm = tk.StringVar(value="enter")
        frame_key = ttk.Frame(grid)
        frame_key.grid(row=1, column=1, columnspan=2, sticky="w", pady=4, padx=10)
        ttk.Radiobutton(frame_key, text="ENTER (Estándar Saint)", value="enter", variable=self.var_key_confirm).pack(side="left", padx=(0, 15))
        ttk.Radiobutton(frame_key, text="TAB", value="tab", variable=self.var_key_confirm).pack(side="left")

        # Fila 2: Enters tras código de barra
        ttk.Label(grid, text="Confirmaciones tras Código de Barra:").grid(row=2, column=0, sticky="w", pady=4)
        self.var_enters_code = tk.IntVar(value=1)
        spn_enters_code = ttk.Spinbox(grid, from_=1, to=3, textvariable=self.var_enters_code, width=5)
        spn_enters_code.grid(row=2, column=1, sticky="w", pady=4, padx=10)
        ttk.Label(grid, text="pulsación(es)").grid(row=2, column=2, sticky="w", pady=4)

        # Fila 3: Enters tras cantidad
        ttk.Label(grid, text="Confirmaciones tras Cantidad:").grid(row=3, column=0, sticky="w", pady=4)
        self.var_enters_qty = tk.IntVar(value=1)
        spn_enters_qty = ttk.Spinbox(grid, from_=1, to=3, textvariable=self.var_enters_qty, width=5)
        spn_enters_qty.grid(row=3, column=1, sticky="w", pady=4, padx=10)
        ttk.Label(grid, text="pulsación(es)").grid(row=3, column=2, sticky="w", pady=4)

        # Fila 4: Incluir precio
        self.var_include_price = tk.BooleanVar(value=False)
        chk_price = ttk.Checkbutton(grid, text="¿Escribir Precio en Saint? (Por defecto Saint usa su propio precio de lista)", 
                                    variable=self.var_include_price)
        chk_price.grid(row=4, column=0, columnspan=3, sticky="w", pady=6)

        # Fila 5: Moneda del precio
        ttk.Label(grid, text="Si se escribe precio, usar:").grid(row=5, column=0, sticky="w", pady=4)
        self.var_price_moneda = tk.StringVar(value="costo_unitario_usd")
        frame_moneda = ttk.Frame(grid)
        frame_moneda.grid(row=5, column=1, columnspan=2, sticky="w", pady=4, padx=10)
        ttk.Radiobutton(frame_moneda, text="Precio USD ($)", value="costo_unitario_usd", variable=self.var_price_moneda).pack(side="left", padx=(0, 15))
        ttk.Radiobutton(frame_moneda, text="Precio Bs.", value="costo_unitario_bs", variable=self.var_price_moneda).pack(side="left")

        # Fila 6: Velocidad / Modo de espera
        ttk.Label(grid, text="Perfil de velocidad / respuesta:", font=("Segoe UI", 9, "bold")).grid(row=6, column=0, sticky="w", pady=6)
        self.var_speed = tk.StringVar(value="normal")
        frame_speed = ttk.Frame(grid)
        frame_speed.grid(row=6, column=1, columnspan=2, sticky="w", pady=6, padx=10)
        ttk.Radiobutton(frame_speed, text="Rápido (300ms)", value="fast", variable=self.var_speed).pack(side="left", padx=(0, 10))
        ttk.Radiobutton(frame_speed, text="Normal (500ms)", value="normal", variable=self.var_speed).pack(side="left", padx=(0, 10))
        ttk.Radiobutton(frame_speed, text="Seguro / Lento (800ms)", value="safe", variable=self.var_speed).pack(side="left")

        # Fila 7: Modo prueba / Bloc de notas
        self.var_test_mode = tk.BooleanVar(value=False)
        chk_test = ttk.Checkbutton(grid, text="🧪 Modo Simulación (Escribe en Bloc de Notas para probar sin tocar Saint)", 
                                   variable=self.var_test_mode)
        chk_test.grid(row=7, column=0, columnspan=3, sticky="w", pady=8)

    def _toggle_topmost(self):
        is_top = self.var_topmost.get()
        self.root.wm_attributes("-topmost", is_top)
        try:
            f_str = self.root.wm_frame() if hasattr(self.root, "wm_frame") else ""
            h = int(f_str, 16) if f_str else self.root.winfo_id()
            if h:
                HWND_TARGET = -1 if is_top else -2
                user32.SetWindowPos(h, HWND_TARGET, 0, 0, 0, 0, 0x0002 | 0x0001 | 0x0040)
        except Exception:
            pass

    def _scan_json_files(self):
        """Busca archivos JSON en la carpeta facturas_json"""
        if not self.json_dir.exists():
            self._log_msg(f"Carpeta {self.json_dir} no existe.")
            return

        json_files = sorted(list(self.json_dir.glob("*.json")))
        if not json_files:
            self._log_msg("No se encontraron facturas JSON en la carpeta.")
            self.cbo_facturas["values"] = []
            return

        values = [f.name for f in json_files]
        self.cbo_facturas["values"] = values
        
        # Seleccionar la primera por defecto si no hay nada seleccionado
        if values and not self.cbo_facturas.get():
            self.cbo_facturas.current(0)
            self._load_json_file(json_files[0])

    def _on_combo_selected(self, event=None):
        filename = self.cbo_facturas.get()
        if filename:
            path = self.json_dir / filename
            if path.exists():
                self._load_json_file(path)

    def _browse_json(self):
        filepath = filedialog.askopenfilename(
            title="Seleccionar factura JSON",
            initialdir=str(self.json_dir if self.json_dir.exists() else self.base_dir),
            filetypes=[("Archivos JSON", "*.json"), ("Todos los archivos", "*.*")]
        )
        if filepath:
            self._load_json_file(Path(filepath))

    def _load_json_file(self, path: Path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            messagebox.showerror("Error", f"No se pudo cargar el archivo JSON:\n{e}")
            return

        self.loaded_data = data
        self.current_json_path = path
        
        # Actualizar tarjeta de información
        factura_num = data.get("factura", path.stem)
        proveedor = data.get("proveedor", "N/A")
        totales = data.get("totales", {})
        total_usd = totales.get("total_usd", 0.0)
        total_bs = totales.get("total_bs", 0.0)
        tasa = data.get("tasa_cambio", 0.0)
        productos = data.get("productos", [])
        
        self.lbl_factura_num.configure(text=f"Factura: {factura_num}")
        self.lbl_proveedor.configure(text=f"Proveedor/Cliente: {proveedor}")
        self.lbl_items_count.configure(text=f"Ítems: {len(productos)}")
        self.lbl_monto_usd.configure(text=f"Total USD: $ {total_usd:,.2f}")
        self.lbl_monto_bs.configure(text=f"Total Bs.: Bs. {total_bs:,.2f}")
        self.lbl_tasa.configure(text=f"Tasa: {tasa:,.2f} Bs/$")
        
        # Cargar productos en la tabla
        self.items_list = productos
        self._populate_tree(productos)
        
        # Reiniciar barra de progreso
        self.progress_bar["maximum"] = len(productos)
        self.progress_bar["value"] = 0
        self.lbl_progress_txt.configure(text=f"0 de {len(productos)} productos cargados")
        self.lbl_estado.configure(text="● FACTURA LISTA PARA FACTURAR", fg="#16a34a")
        self._log_msg(f"Cargada factura {factura_num} con {len(productos)} productos.")

    def _populate_tree(self, productos):
        self.tree.delete(*self.tree.get_children())
        for idx, prod in enumerate(productos, 1):
            codigo = prod.get("codigo_barra", "")
            desc = prod.get("descripcion", "")
            cant = prod.get("cantidad", 0)
            c_usd = f"$ {prod.get('costo_unitario_usd', 0.0):.2f}"
            c_bs = f"Bs. {prod.get('costo_unitario_bs', 0.0):.2f}"
            estado = "⏳ Pendiente"
            
            item_id = f"item_{idx-1}"
            self.tree.insert("", "end", iid=item_id, values=(idx, codigo, desc, cant, c_usd, c_bs, estado),
                             tags=("pending",))

    def _apply_engine_config(self):
        """Aplica las opciones de la interfaz al motor del bot"""
        speed_profile = self.var_speed.get()
        if speed_profile == "fast":
            d_barcode, d_qty, d_items = 0.22, 0.15, 0.22
        elif speed_profile == "safe":
            d_barcode, d_qty, d_items = 0.60, 0.40, 0.50
        else: # normal
            d_barcode, d_qty, d_items = 0.35, 0.25, 0.35

        self.engine.config.update({
            "countdown_seconds": self.var_countdown.get(),
            "delay_after_barcode": d_barcode,
            "delay_after_qty": d_qty,
            "delay_between_items": d_items,
            "enters_after_code": self.var_enters_code.get(),
            "enters_after_qty": self.var_enters_qty.get(),
            "include_price": self.var_include_price.get(),
            "price_key": self.var_price_moneda.get(),
            "enters_after_price": 1,
            "key_confirm": self.var_key_confirm.get(),
            "test_mode": self.var_test_mode.get()
        })

    def start_typing(self):
        if not self.items_list:
            messagebox.showwarning("Atención", "No hay productos cargados para facturar.")
            return

        if self.engine.running:
            return

        self._apply_engine_config()

        # Actualizar UI
        self.btn_start.configure(state="disabled")
        self.btn_pause.configure(state="normal", text="⏸ PAUSAR (F7)", bg=self.c_warning)
        self.btn_stop.configure(state="normal")
        
        # Iniciar motor
        self.engine.start_process(self.items_list)

    def pause_typing(self):
        if self.engine.running:
            self.engine.pause()

    def stop_typing(self):
        if self.engine.running:
            self.engine.stop()

    def _hotkey_start(self):
        self.root.after(0, self.start_typing)

    def _hotkey_pause(self):
        self.root.after(0, self.pause_typing)

    def _hotkey_stop(self):
        self.root.after(0, self.stop_typing)

    def _on_bot_countdown(self, count):
        def update():
            self.lbl_estado.configure(text=f"⏳ COMENZANDO EN {count} SEG...", fg="#ea580c")
        self.root.after(0, update)

    def _on_bot_state_change(self, state):
        def update():
            if state == "ESCRIBIENDO":
                self.lbl_estado.configure(text="⌨️ ESCRIBIENDO EN SAINT...", fg="#2563eb")
            elif state == "PAUSADO":
                self.lbl_estado.configure(text="⏸ PAUSADO (Pulsa F7 para continuar)", fg="#d97706")
                self.btn_pause.configure(text="▶ REANUDAR (F7)", bg="#0284c7")
            elif state == "REANUDADO":
                self.lbl_estado.configure(text="⌨️ ESCRIBIENDO EN SAINT...", fg="#2563eb")
                self.btn_pause.configure(text="⏸ PAUSAR (F7)", bg=self.c_warning)
            elif state in ("COMPLETADO", "DETENIDO", "ERROR"):
                self.btn_start.configure(state="normal")
                self.btn_pause.configure(state="disabled", text="⏸ PAUSAR (F7)", bg=self.c_warning)
                self.btn_stop.configure(state="disabled")
                if state == "COMPLETADO":
                    self.lbl_estado.configure(text="✅ FACTURACIÓN COMPLETADA", fg="#16a34a")
                elif state == "DETENIDO":
                    self.lbl_estado.configure(text="⏹ CANCELADO POR EL USUARIO", fg="#dc2626")
                else:
                    self.lbl_estado.configure(text="⚠️ ERROR DURANTE LA ESCRITURA", fg="#dc2626")
        self.root.after(0, update)

    def _on_bot_item_started(self, idx, item):
        def update():
            item_id = f"item_{idx}"
            if self.tree.exists(item_id):
                vals = list(self.tree.item(item_id, "values"))
                vals[6] = "⌨️ Escribiendo..."
                self.tree.item(item_id, values=vals, tags=("active",))
                self.tree.see(item_id)
            
            self.progress_bar["value"] = idx
            self.lbl_progress_txt.configure(text=f"{idx} de {len(self.items_list)} productos")
        self.root.after(0, update)

    def _on_bot_item_finished(self, idx, item, success):
        def update():
            item_id = f"item_{idx}"
            if self.tree.exists(item_id):
                vals = list(self.tree.item(item_id, "values"))
                vals[6] = "✅ Cargado" if success else "❌ Fallo"
                self.tree.item(item_id, values=vals, tags=("done" if success else "pending",))
            
            self.progress_bar["value"] = idx + 1
            self.lbl_progress_txt.configure(text=f"{idx + 1} de {len(self.items_list)} productos")
        self.root.after(0, update)

    def _on_bot_log(self, message):
        self.root.after(0, lambda: self._log_msg(message))

    def _log_msg(self, text):
        self.txt_log.configure(state="normal")
        self.txt_log.insert("end", f"{text}\n")
        self.txt_log.see("end")
        self.txt_log.configure(state="disabled")

    def _on_close(self):
        if self.engine.running:
            if not messagebox.askyesno("Salir", "El bot está escribiendo datos. ¿Deseas detenerlo y salir?"):
                return
            self.engine.stop()
        self.engine.stop_hotkey_listener()
        self.root.destroy()


def main():
    root = tk.Tk()
    app = BotFacturadorSaintApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
