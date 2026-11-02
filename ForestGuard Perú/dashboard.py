import json
import sqlite3
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, font, messagebox, ttk
from PIL import Image, ImageTk


BACKGROUND = "#08120e"
HEADER = "#0d2117"
GREEN = "#2ba76b"
TEXT = "#edf5ef"
MUTED = "#9aada1"
BORDER = "#20352a"
DATA_FILE = Path(__file__).with_name("forestguard_data.json")
DATABASE_FILE = Path(__file__).with_name("forestguard.db")

DEFAULT_DATA = {
    "metrics": {"areas": 128, "alerts": 12, "transports": 46, "reviewed": 35},
    "reports": [],
    "transport_records": [],
    "vulnerable_zones": [],
}


class ForestGuardDashboard:
    def __init__(self, root):
        self.root = root
        self.root.title("ForestGuard Perú | Sistema de vigilancia forestal")
        self.root.geometry("1080x780")
        self.root.minsize(820, 680)
        self.root.configure(bg=BACKGROUND)

        self.title_font = font.Font(family="Segoe UI", size=20, weight="bold")
        self.subtitle_font = font.Font(family="Segoe UI", size=10)
        self.metric_font = font.Font(family="Segoe UI", size=24, weight="bold")
        self.label_font = font.Font(family="Segoe UI", size=11)
        self.module_font = font.Font(family="Segoe UI", size=14, weight="bold")
        self.data = self._load_data()
        self.metric_values = {}

        self.content = tk.Frame(root, bg=BACKGROUND, padx=28, pady=20)
        self.content.pack(fill="both", expand=True)

        self._build_header()
        self._build_metrics()
        self._build_modules()
        self._build_footer()

    def _load_data(self):
        connection = None
        try:
            connection = sqlite3.connect(DATABASE_FILE)
            with connection:
                connection.executescript(
                    """
                    CREATE TABLE IF NOT EXISTS metrics (
                        name TEXT PRIMARY KEY,
                        value INTEGER NOT NULL
                    );
                    CREATE TABLE IF NOT EXISTS reports (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        location TEXT NOT NULL,
                        type TEXT NOT NULL,
                        description TEXT NOT NULL,
                        created_at TEXT NOT NULL,
                        status TEXT NOT NULL
                    );
                    CREATE TABLE IF NOT EXISTS transport_records (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        guide TEXT NOT NULL,
                        plate TEXT NOT NULL,
                        origin TEXT NOT NULL,
                        destination TEXT NOT NULL,
                        created_at TEXT NOT NULL
                    );
                    CREATE TABLE IF NOT EXISTS metadata (
                        name TEXT PRIMARY KEY,
                        value TEXT NOT NULL
                    );
                    CREATE TABLE IF NOT EXISTS vulnerable_zones (
                        name TEXT PRIMARY KEY,
                        vulnerable INTEGER NOT NULL CHECK (vulnerable IN (0, 1))
                    );
                    """
                )
                imported = connection.execute(
                    "SELECT value FROM metadata WHERE name = 'legacy_json_imported'"
                ).fetchone()
                if imported is None:
                    self._write_data(connection, self._read_legacy_data())
                    connection.execute(
                        "INSERT INTO metadata (name, value) VALUES (?, ?)",
                        ("legacy_json_imported", "true"),
                    )

                metrics = dict(connection.execute(
                    "SELECT name, value FROM metrics"
                ).fetchall())
                reports = [
                    dict(zip(
                        ("location", "type", "description", "created_at", "status"),
                        row,
                    ))
                    for row in connection.execute(
                        "SELECT location, type, description, created_at, status "
                        "FROM reports ORDER BY id"
                    ).fetchall()
                ]
                transport_records = [
                    dict(zip(
                        ("guide", "plate", "origin", "destination", "created_at"),
                        row,
                    ))
                    for row in connection.execute(
                        "SELECT guide, plate, origin, destination, created_at "
                        "FROM transport_records ORDER BY id"
                    ).fetchall()
                ]
                vulnerable_zones = [
                    row[0] for row in connection.execute(
                        "SELECT name FROM vulnerable_zones "
                        "WHERE vulnerable = 1 ORDER BY name"
                    ).fetchall()
                ]
            return {
                "metrics": metrics,
                "reports": reports,
                "transport_records": transport_records,
                "vulnerable_zones": vulnerable_zones,
            }
        except (OSError, sqlite3.Error, KeyError, TypeError, ValueError) as error:
            messagebox.showerror(
                "No se pudieron cargar los registros",
                f"Revisa la base de datos {DATABASE_FILE}.\n\nDetalle: {error}",
            )
            return json.loads(json.dumps(DEFAULT_DATA))
        finally:
            if connection is not None:
                connection.close()

    def _read_legacy_data(self):
        if not DATA_FILE.exists():
            return json.loads(json.dumps(DEFAULT_DATA))
        try:
            with DATA_FILE.open("r", encoding="utf-8") as data_file:
                data = json.load(data_file)
            for key in ("areas", "alerts", "transports", "reviewed"):
                if not isinstance(data["metrics"][key], int):
                    raise ValueError(f"El contador «{key}» no es un número entero.")
            if not isinstance(data["reports"], list) or not isinstance(
                data["transport_records"], list
            ):
                raise ValueError("Los registros guardados tienen un formato incorrecto.")
            if any(
                not isinstance(report, dict)
                or not {
                    "status", "type", "location", "description", "created_at"
                }.issubset(report)
                for report in data["reports"]
            ):
                raise ValueError("Una denuncia guardada está incompleta.")
            if any(
                not isinstance(record, dict)
                or not {"guide", "plate", "origin", "destination", "created_at"}
                .issubset(record)
                for record in data["transport_records"]
            ):
                raise ValueError("Un transporte guardado está incompleto.")
            return data
        except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError) as error:
            messagebox.showerror(
                "No se pudieron cargar los registros",
                f"Revisa el archivo {DATA_FILE}.\n\nDetalle: {error}",
            )
            return json.loads(json.dumps(DEFAULT_DATA))

    def _write_data(self, connection, data):
        connection.execute("DELETE FROM metrics")
        connection.executemany(
            "INSERT INTO metrics (name, value) VALUES (?, ?)",
            data["metrics"].items(),
        )
        connection.execute("DELETE FROM reports")
        connection.executemany(
            "INSERT INTO reports "
            "(location, type, description, created_at, status) "
            "VALUES (:location, :type, :description, :created_at, :status)",
            data["reports"],
        )
        connection.execute("DELETE FROM transport_records")
        connection.executemany(
            "INSERT INTO transport_records "
            "(guide, plate, origin, destination, created_at) "
            "VALUES (:guide, :plate, :origin, :destination, :created_at)",
            data["transport_records"],
        )
        connection.execute("DELETE FROM vulnerable_zones")
        connection.executemany(
            "INSERT INTO vulnerable_zones (name, vulnerable) VALUES (?, 1)",
            ((name,) for name in data.get("vulnerable_zones", [])),
        )

    def _save_data(self, updated_data):
        connection = None
        try:
            connection = sqlite3.connect(DATABASE_FILE)
            with connection:
                self._write_data(connection, updated_data)
        except (OSError, sqlite3.Error, KeyError, TypeError, ValueError) as error:
            messagebox.showerror(
                "No se pudieron guardar los cambios",
                f"Revisa la base de datos {DATABASE_FILE}.\n\nDetalle: {error}",
            )
            return False
        finally:
            if connection is not None:
                connection.close()
        self.data = updated_data
        self._refresh_metrics()
        return True

    def _build_header(self):
        header = tk.Frame(self.content, bg=BACKGROUND, height=70)
        header.pack(fill="x", pady=(0, 22))
        header.pack_propagate(False)

        tk.Label(
            header, text="FG", bg=GREEN, fg=TEXT,
            font=("Segoe UI", 13, "bold"), padx=11, pady=7
        ).pack(side="left", padx=(0, 12))

        title_box = tk.Frame(header, bg=BACKGROUND)
        title_box.pack(side="left", expand=True, fill="y", pady=11)
        tk.Label(
            title_box, text="ForestGuard", bg=BACKGROUND, fg=TEXT,
            font=("Segoe UI", 16, "bold")
        ).pack(anchor="w")
        tk.Label(
            title_box, text="CENTRO DE VIGILANCIA FORESTAL · PERÚ",
            bg=BACKGROUND, fg=MUTED, font=("Segoe UI", 8, "bold")
        ).pack(anchor="w")

        tk.Label(
            header, text="●  SISTEMA ACTIVO", bg=BACKGROUND, fg="#78d99f",
            font=("Segoe UI", 9, "bold")
        ).pack(side="right", padx=(12, 4))
        tk.Button(
            header, text="Alertas", command=self.show_alerts,
            bg="#14271c", fg=TEXT, activebackground="#203a2a",
            activeforeground=TEXT, relief="flat", cursor="hand2",
            font=("Segoe UI", 10, "bold"), padx=15, pady=9
        ).pack(side="right", padx=(8, 0))
        tk.Button(
            header, text="Registros", command=self.show_saved_records,
            bg="#14271c", fg=TEXT, activebackground="#203a2a",
            activeforeground=TEXT, relief="flat", cursor="hand2",
            font=("Segoe UI", 10, "bold"), padx=15, pady=9
        ).pack(side="right", padx=(8, 0))

        hero = tk.Frame(
            self.content, bg="#10271b", highlightthickness=1,
            highlightbackground="#1d4930", padx=26, pady=22
        )
        hero.pack(fill="x", pady=(0, 20))
        hero.grid_columnconfigure(0, weight=1)
        tk.Label(
            hero, text="Protegiendo los bosques del Perú",
            bg="#10271b", fg=TEXT, font=("Segoe UI", 22, "bold")
        ).grid(row=0, column=0, sticky="w")
        tk.Label(
            hero,
            text="Monitorea alertas, registra incidencias y consulta la actividad "
                 "desde un solo lugar.",
            bg="#10271b", fg="#b4c9ba", font=self.subtitle_font
        ).grid(row=1, column=0, sticky="w", pady=(6, 0))
        tk.Button(
            hero, text="+  Nueva denuncia", command=self.open_report_form,
            bg=GREEN, fg=TEXT, activebackground="#238b58",
            activeforeground=TEXT, relief="flat", cursor="hand2",
            font=("Segoe UI", 10, "bold"), padx=16, pady=10
        ).grid(row=0, column=1, rowspan=2, sticky="e", padx=(18, 0))

    def _build_metrics(self):
        metrics = tk.Frame(self.content, bg=BACKGROUND)
        metrics.pack(fill="x", pady=(0, 22))
        metrics.grid_columnconfigure((0, 1, 2, 3), weight=1, uniform="metric")

        items = (
            ("01", "areas", "ÁREAS MONITOREADAS", "#50c987"),
            ("02", "alerts", "ALERTAS PENDIENTES", "#f0bd55"),
            ("03", "transports", "TRANSPORTES", "#6ab7e8"),
            ("04", "reviewed", "REPORTES REVISADOS", "#a78bfa"),
        )
        for column, (icon, key, label, color) in enumerate(items):
            cell = tk.Frame(
                metrics, bg="#101d16", highlightthickness=1,
                highlightbackground="#1d3024", padx=16, pady=14
            )
            cell.grid(
                row=0, column=column, sticky="nsew",
                padx=(0, 10) if column < 3 else (0, 0)
            )
            tk.Label(
                cell, text=icon, bg="#101d16", fg=color,
                font=("Segoe UI", 9, "bold")
            ).pack(anchor="w")
            value = tk.Label(
                cell, text="", bg="#101d16", fg=TEXT, font=self.metric_font
            )
            value.pack(anchor="w", pady=(5, 1))
            self.metric_values[key] = value
            tk.Label(
                cell, text=label, bg="#101d16", fg=MUTED,
                font=("Segoe UI", 8, "bold")
            ).pack(anchor="w")
        self._refresh_metrics()

    def _refresh_metrics(self):
        for key, label in self.metric_values.items():
            label.configure(text=str(self.data["metrics"][key]))

    def _build_modules(self):
        section_header = tk.Frame(self.content, bg=BACKGROUND)
        section_header.pack(fill="x", pady=(0, 12))
        tk.Label(
            section_header, text="Herramientas de gestión",
            bg=BACKGROUND, fg=TEXT, font=self.module_font
        ).pack(side="left")
        tk.Label(
            section_header, text="ACCESO RÁPIDO",
            bg=BACKGROUND, fg=MUTED, font=("Segoe UI", 8, "bold")
        ).pack(side="right")

        modules = tk.Frame(self.content, bg=BACKGROUND)
        modules.pack(fill="both", expand=True)
        modules.grid_columnconfigure((0, 1), weight=1, uniform="module")
        modules.grid_rowconfigure((0, 1), weight=1, uniform="module")

        items = (
            ("01  ·  DETECCIÓN", "Analizar fotografía",
             "Adjunta una imagen para registrar una alerta de revisión.",
             self.open_photo_review),
            ("02  ·  MONITOREO", "Mapa forestal",
             "Consulta las zonas ilustrativas y su estado de monitoreo.",
             self.show_map),
            ("03  ·  INCIDENCIAS", "Registrar denuncia",
             "Documenta un incidente forestal con sus detalles.",
             self.open_report_form),
            ("04  ·  TRAZABILIDAD", "Control de madera",
             "Registra guías, vehículos y rutas de transporte.",
             self.open_transport_form),
        )
        for index, (eyebrow, title, description, action) in enumerate(items):
            row, column = divmod(index, 2)
            card = tk.Frame(
                modules, bg="#101d16", highlightthickness=1,
                highlightbackground="#1d3024", padx=18, pady=14
            )
            card.grid(
                row=row, column=column, sticky="nsew",
                padx=(0, 10) if column == 0 else (0, 0),
                pady=(0, 10) if row == 0 else (0, 0)
            )
            tk.Label(
                card, text=eyebrow, bg="#101d16", fg="#70c993",
                font=("Segoe UI", 8, "bold")
            ).pack(anchor="w")
            tk.Button(
                card, text=f"{title}   →", command=action,
                bg="#101d16", fg=TEXT, activebackground="#172b1e",
                activeforeground=TEXT, relief="flat", cursor="hand2",
                font=("Segoe UI", 13, "bold"), anchor="w",
                padx=0, pady=6
            ).pack(anchor="w", fill="x")
            tk.Label(
                card, text=description, bg="#101d16", fg=MUTED,
                font=self.subtitle_font, anchor="w", justify="left",
                wraplength=430
            ).pack(anchor="w", fill="x")
            card.bind(
                "<Enter>", lambda _event, frame=card: frame.configure(
                    highlightbackground="#39744e"
                )
            )
            card.bind(
                "<Leave>", lambda _event, frame=card: frame.configure(
                    highlightbackground="#1d3024"
                )
            )

    def _build_footer(self):
        footer = tk.Frame(
            self.content, bg=BACKGROUND, highlightthickness=1,
            highlightbackground="#1d3024", pady=10
        )
        footer.pack(fill="x", pady=(12, 0))
        tk.Label(
            footer, text="FORESTGUARD PERÚ   ·   PROTOTIPO LOCAL",
            bg=BACKGROUND, fg=MUTED, font=("Segoe UI", 8, "bold")
        ).pack(side="left", padx=12)
        tk.Label(
            footer, text="Revisión de fotografías realizada por una persona",
            bg=BACKGROUND, fg=MUTED, font=("Segoe UI", 8)
        ).pack(side="right", padx=12)

    def _new_window(self, title, size="540x440"):
        window = tk.Toplevel(self.root)
        window.title(title)
        window.geometry(size)
        window.minsize(420, 320)
        window.configure(bg=BACKGROUND)
        window.transient(self.root)
        window.grab_set()
        return window

    def _form_field(self, parent, label, row, initial=""):
        tk.Label(
            parent, text=label, bg=BACKGROUND, fg=TEXT,
            font=self.label_font
        ).grid(row=row, column=0, sticky="w", padx=18, pady=(10, 3))
        entry = tk.Entry(
            parent, bg="#151515", fg=TEXT, insertbackground=TEXT,
            relief="solid", bd=1, font=self.label_font
        )
        entry.insert(0, initial)
        entry.grid(row=row + 1, column=0, sticky="ew", padx=18, pady=(0, 5))
        return entry

    def _save_report(self, location, report_type, description):
        updated = json.loads(json.dumps(self.data))
        updated["reports"].append({
            "location": location,
            "type": report_type,
            "description": description,
            "created_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "status": "Pendiente",
        })
        updated["metrics"]["alerts"] += 1
        return self._save_data(updated)

    def open_report_form(self):
        window = self._new_window("Registrar denuncia")
        window.grid_columnconfigure(0, weight=1)
        tk.Label(
            window, text="Registrar denuncia", bg=BACKGROUND, fg=TEXT,
            font=self.title_font
        ).grid(row=0, column=0, sticky="w", padx=18, pady=(18, 4))
        tk.Label(
            window, text="Completa los datos del incidente. Los campos son obligatorios.",
            bg=BACKGROUND, fg=MUTED, font=self.subtitle_font
        ).grid(row=1, column=0, sticky="w", padx=18, pady=(0, 6))

        location = self._form_field(window, "Lugar o zona", 2)
        report_type = self._form_field(window, "Tipo de incidente", 4)
        description = self._form_field(window, "Descripción", 6)

        def submit():
            values = (location.get().strip(), report_type.get().strip(),
                      description.get().strip())
            if not all(values):
                messagebox.showwarning(
                    "Faltan datos", "Completa los tres campos.", parent=window
                )
                return
            if self._save_report(*values):
                messagebox.showinfo(
                    "Denuncia registrada", "El incidente quedó guardado como pendiente.",
                    parent=window
                )
                window.destroy()

        tk.Button(
            window, text="Guardar denuncia", command=submit,
            bg=GREEN, fg=TEXT, activebackground="#16834f",
            activeforeground=TEXT, relief="flat", cursor="hand2",
            font=self.label_font, padx=14, pady=8
        ).grid(row=8, column=0, sticky="e", padx=18, pady=18)

    def open_transport_form(self):
        window = self._new_window("Control de madera")
        window.grid_columnconfigure(0, weight=1)
        tk.Label(
            window, text="Registrar transporte de madera", bg=BACKGROUND, fg=TEXT,
            font=self.title_font
        ).grid(row=0, column=0, sticky="w", padx=18, pady=(18, 8))
        guide = self._form_field(window, "Número de guía", 1)
        plate = self._form_field(window, "Placa del vehículo", 3)
        origin = self._form_field(window, "Origen", 5)
        destination = self._form_field(window, "Destino", 7)

        def submit():
            values = [field.get().strip() for field in
                      (guide, plate, origin, destination)]
            if not all(values):
                messagebox.showwarning(
                    "Faltan datos", "Completa todos los campos.", parent=window
                )
                return
            updated = json.loads(json.dumps(self.data))
            updated["transport_records"].append({
                "guide": values[0],
                "plate": values[1],
                "origin": values[2],
                "destination": values[3],
                "created_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
            })
            updated["metrics"]["transports"] += 1
            if self._save_data(updated):
                messagebox.showinfo(
                    "Transporte registrado", "La guía quedó guardada.",
                    parent=window
                )
                window.destroy()

        tk.Button(
            window, text="Guardar transporte", command=submit,
            bg=GREEN, fg=TEXT, activebackground="#16834f",
            activeforeground=TEXT, relief="flat", cursor="hand2",
            font=self.label_font, padx=14, pady=8
        ).grid(row=9, column=0, sticky="e", padx=18, pady=14)

    def _analyze_photo(self, path):
        with Image.open(path) as source:
            image = source.convert("RGB")
            dimensions = image.size
            image.thumbnail((512, 512))
            pixels = list(image.getdata())

        green_pixels = 0
        soil_pixels = 0
        brightness_total = 0
        for red, green, blue in pixels:
            lowest = min(red, green, blue)
            brightness_total += (red + green + blue) / 3
            if green > red * 1.08 and green > blue * 1.05 and green - lowest >= 15:
                green_pixels += 1
            if red > green * 1.06 and green >= blue * 0.85 and red - blue >= 20:
                soil_pixels += 1

        pixel_count = len(pixels)
        green_percent = green_pixels * 100 / pixel_count
        soil_percent = soil_pixels * 100 / pixel_count
        brightness = brightness_total / pixel_count
        if green_percent < 30 and soil_percent >= 20:
            finding = "Posibles indicios de tala o pérdida de cobertura forestal"
            observation = (
                "La combinación de vegetación visible reducida y tonos de suelo "
                "elevados amerita una revisión del área."
            )
        elif green_percent >= 35 and soil_percent < 20:
            finding = "Sin indicios claros de tala en el análisis por color"
            observation = (
                "Los colores analizados no muestran señales claras; esto no "
                "descarta tala ni reemplaza una inspección."
            )
        else:
            finding = "Resultado no concluyente; se recomienda revisión"
            observation = (
                "Los indicadores de color son mixtos y no permiten una "
                "clasificación clara."
            )
        return {
            "dimensions": dimensions,
            "green_percent": green_percent,
            "soil_percent": soil_percent,
            "brightness": brightness,
            "finding": finding,
            "observation": observation,
        }

    def open_photo_review(self):
        window = self._new_window("Análisis visual de fotografía", "940x680")
        window.minsize(760, 560)
        window.grid_columnconfigure(0, weight=3)
        window.grid_columnconfigure(1, weight=2)
        window.grid_rowconfigure(1, weight=1)

        tk.Label(
            window, text="Análisis visual de fotografía", bg=BACKGROUND, fg=TEXT,
            font=self.title_font
        ).grid(row=0, column=0, columnspan=2, sticky="w", padx=22, pady=(20, 4))
        tk.Label(
            window,
            text="Indicadores locales de color. La imagen no se envía por internet.",
            bg=BACKGROUND, fg=MUTED, font=self.subtitle_font
        ).grid(row=0, column=0, columnspan=2, sticky="w", padx=22, pady=(58, 12))

        preview_panel = tk.Frame(
            window, bg="#101d16", highlightthickness=1,
            highlightbackground="#20352a"
        )
        preview_panel.grid(
            row=1, column=0, sticky="nsew", padx=(22, 10), pady=(0, 18)
        )
        preview_panel.grid_columnconfigure(0, weight=1)
        preview_panel.grid_rowconfigure(0, weight=1)
        preview = tk.Label(
            preview_panel, text="Selecciona una fotografía para comenzar",
            bg="#101d16", fg=MUTED, font=self.subtitle_font
        )
        preview.grid(row=0, column=0, sticky="nsew", padx=12, pady=12)
        path_label = tk.Label(
            preview_panel, text="", bg="#101d16", fg=MUTED,
            font=("Segoe UI", 9), wraplength=480, justify="left"
        )
        path_label.grid(row=1, column=0, sticky="ew", padx=14, pady=(0, 12))

        result_panel = tk.Frame(
            window, bg="#101d16", highlightthickness=1,
            highlightbackground="#20352a", padx=18, pady=16
        )
        result_panel.grid(
            row=1, column=1, sticky="nsew", padx=(10, 22), pady=(0, 18)
        )
        tk.Label(
            result_panel, text="RESULTADOS", bg="#101d16", fg="#70c993",
            font=("Segoe UI", 9, "bold")
        ).pack(anchor="w")
        analysis_var = tk.StringVar(
            value="Elige una imagen para calcular sus indicadores visuales."
        )
        tk.Label(
            result_panel, textvariable=analysis_var, bg="#101d16", fg=TEXT,
            font=self.label_font, justify="left", wraplength=270
        ).pack(anchor="w", pady=(14, 18))
        tk.Label(
            result_panel,
            text="El resultado es orientativo y se basa solo en colores, no en "
                 "un modelo entrenado. Una fotografía no confirma que la tala "
                 "sea ilegal: eso requiere verificar permisos y contexto con "
                 "las autoridades. La luz, estación y terreno pueden afectar "
                 "el análisis.",
            bg="#101d16", fg=MUTED, font=("Segoe UI", 9),
            justify="left", wraplength=270
        ).pack(anchor="w", pady=(0, 16))

        current = {"path": None, "analysis": None, "preview_image": None}

        def select_photo():
            path = filedialog.askopenfilename(
                parent=window,
                title="Seleccionar fotografía",
                filetypes=(("Imágenes", "*.png *.jpg *.jpeg *.bmp *.gif *.tif *.tiff"),
                           ("Todos los archivos", "*.*")),
            )
            if not path:
                return
            try:
                analysis = self._analyze_photo(path)
                with Image.open(path) as source:
                    image = source.convert("RGB")
                    image.thumbnail((620, 440))
                    photo_image = ImageTk.PhotoImage(image)
            except (OSError, ValueError) as error:
                messagebox.showerror(
                    "No se pudo analizar la imagen",
                    f"Selecciona una imagen válida.\n\nDetalle: {error}",
                    parent=window,
                )
                return

            current["path"] = path
            current["analysis"] = analysis
            current["preview_image"] = photo_image
            preview.configure(image=photo_image, text="")
            path_label.configure(text=path)
            analysis_var.set(
                f"RESULTADO PRELIMINAR\n{analysis['finding']}\n\n"
                f"{analysis['observation']}\n\n"
                f"Resolución: {analysis['dimensions'][0]} × "
                f"{analysis['dimensions'][1]} px\n\n"
                f"Tonos verdes: {analysis['green_percent']:.1f}%\n\n"
                f"Tonos tierra: {analysis['soil_percent']:.1f}%\n\n"
                f"Brillo medio: {analysis['brightness']:.0f} / 255"
            )
            save_button.configure(state="normal")

        def save_analysis():
            path = current["path"]
            analysis = current["analysis"]
            if not path or not analysis:
                return
            description = (
                f"Resultado preliminar: {analysis['finding']}. "
                f"{analysis['observation']} "
                f"Imagen: {path}; tonos verdes: {analysis['green_percent']:.1f}%; "
                f"tonos tierra: {analysis['soil_percent']:.1f}%; "
                f"brillo medio: {analysis['brightness']:.0f}/255. "
                "Resultado orientativo por color; no determina legalidad y "
                "requiere verificación humana."
            )
            if self._save_report(
                "Por verificar", analysis["finding"], description
            ):
                messagebox.showinfo(
                    "Análisis guardado",
                    "El resultado se guardó como alerta pendiente de revisión.",
                    parent=window,
                )
                window.destroy()

        controls = tk.Frame(window, bg=BACKGROUND)
        controls.grid(row=2, column=0, columnspan=2, sticky="e", padx=22, pady=(0, 18))
        tk.Button(
            controls, text="Elegir fotografía", command=select_photo,
            bg="#17271d", fg=TEXT, activebackground="#25372c",
            activeforeground=TEXT, relief="flat", cursor="hand2",
            font=self.label_font, padx=14, pady=9
        ).pack(side="left", padx=(0, 10))
        save_button = tk.Button(
            controls, text="Guardar resultado para revisión", command=save_analysis,
            state="disabled", bg=GREEN, fg=TEXT, activebackground="#16834f",
            activeforeground=TEXT, disabledforeground=MUTED,
            relief="flat", cursor="hand2", font=self.label_font,
            padx=14, pady=9
        )
        save_button.pack(side="left")

    def show_alerts(self):
        window = self._new_window("Alertas pendientes", "680x460")
        window.grid_rowconfigure(1, weight=1)
        window.grid_columnconfigure(0, weight=1)
        tk.Label(
            window, text="Alertas y denuncias", bg=BACKGROUND, fg=TEXT,
            font=self.title_font
        ).grid(row=0, column=0, sticky="w", padx=16, pady=14)

        columns = ("status", "type", "location", "date")
        table = ttk.Treeview(window, columns=columns, show="headings")
        style = ttk.Style(window)
        style.theme_use("clam")
        style.configure(
            "Treeview", background="#111111", foreground=TEXT,
            fieldbackground="#111111", rowheight=28
        )
        style.configure(
            "Treeview.Heading", background="#193d2e", foreground=TEXT
        )
        for column, heading, width in (
            ("status", "Estado", 90), ("type", "Tipo", 210),
            ("location", "Lugar", 170), ("date", "Fecha", 130)
        ):
            table.heading(column, text=heading)
            table.column(column, width=width, anchor="w")
        table.grid(row=1, column=0, sticky="nsew", padx=16)

        for index, report in enumerate(self.data["reports"]):
            table.insert(
                "", "end", iid=str(index),
                values=(report["status"], report["type"], report["location"],
                        report["created_at"])
            )

        controls = tk.Frame(window, bg=BACKGROUND)
        controls.grid(row=2, column=0, sticky="ew", padx=16, pady=14)

        def mark_reviewed():
            selection = table.selection()
            if not selection:
                messagebox.showwarning(
                    "Selecciona una alerta",
                    "Selecciona un registro pendiente de la lista.",
                    parent=window,
                )
                return
            index = int(selection[0])
            if self.data["reports"][index]["status"] != "Pendiente":
                messagebox.showinfo(
                    "Alerta ya revisada", "Ese registro ya figura como revisado.",
                    parent=window
                )
                return
            updated = json.loads(json.dumps(self.data))
            updated["reports"][index]["status"] = "Revisado"
            updated["metrics"]["alerts"] = max(0, updated["metrics"]["alerts"] - 1)
            updated["metrics"]["reviewed"] += 1
            if self._save_data(updated):
                table.item(
                    selection[0],
                    values=(
                        "Revisado", self.data["reports"][index]["type"],
                        self.data["reports"][index]["location"],
                        self.data["reports"][index]["created_at"],
                    ),
                )

        tk.Button(
            controls, text="Marcar como revisada", command=mark_reviewed,
            bg=GREEN, fg=TEXT, activebackground="#16834f",
            activeforeground=TEXT, relief="flat", cursor="hand2",
            font=self.label_font, padx=12, pady=7
        ).pack(side="right")
        if not self.data["reports"]:
            tk.Label(
                window, text="Aún no hay denuncias registradas.",
                bg=BACKGROUND, fg=MUTED, font=self.subtitle_font
            ).grid(row=3, column=0, sticky="w", padx=18, pady=(0, 14))

    def show_saved_records(self):
        window = self._new_window("Registros de la base SQL", "1000x560")
        window.minsize(680, 420)
        window.grid_rowconfigure(3, weight=1)
        window.grid_columnconfigure(0, weight=1)
        tk.Label(
            window, text="Registros guardados en SQLite", bg=BACKGROUND, fg=TEXT,
            font=self.title_font
        ).grid(row=0, column=0, sticky="w", padx=16, pady=(14, 2))
        tk.Label(
            window, text=f"Base de datos: {DATABASE_FILE}",
            bg=BACKGROUND, fg=MUTED, font=self.subtitle_font
        ).grid(row=1, column=0, sticky="w", padx=16, pady=(0, 8))

        filters = tk.Frame(window, bg=BACKGROUND)
        filters.grid(row=2, column=0, columnspan=2, sticky="ew", padx=16, pady=(0, 4))
        tk.Label(
            filters, text="Tipo:", bg=BACKGROUND, fg=TEXT, font=self.subtitle_font
        ).grid(row=0, column=0, sticky="w", padx=(0, 6))
        category_filter = ttk.Combobox(
            filters, state="readonly", width=14,
            values=("Todos", "Denuncia", "Transporte"),
        )
        category_filter.set("Todos")
        category_filter.grid(row=0, column=1, sticky="w", padx=(0, 16))
        tk.Label(
            filters, text="Buscar:", bg=BACKGROUND, fg=TEXT, font=self.subtitle_font
        ).grid(row=0, column=2, sticky="w", padx=(0, 6))
        search_var = tk.StringVar()
        search_entry = tk.Entry(
            filters, textvariable=search_var, bg="#151515", fg=TEXT,
            insertbackground=TEXT, relief="solid", bd=1, font=self.subtitle_font
        )
        search_entry.grid(row=0, column=3, sticky="ew", padx=(0, 12))
        filters.grid_columnconfigure(3, weight=1)
        count_label = tk.Label(
            filters, text="", bg=BACKGROUND, fg=MUTED, font=self.subtitle_font
        )
        count_label.grid(row=0, column=4, sticky="e", padx=(0, 12))

        columns = ("category", "summary", "details", "status", "date")
        table = ttk.Treeview(window, columns=columns, show="headings")
        style = ttk.Style(window)
        style.theme_use("clam")
        style.configure(
            "Treeview", background="#111111", foreground=TEXT,
            fieldbackground="#111111", rowheight=31,
            font=("Segoe UI", 10)
        )
        style.configure(
            "Treeview.Heading", background="#193d2e", foreground=TEXT,
            font=("Segoe UI", 10, "bold")
        )
        for column, heading, width in (
            ("category", "Tipo", 115), ("summary", "Registro", 200),
            ("details", "Detalle", 390), ("status", "Estado", 115),
            ("date", "Fecha", 155),
        ):
            table.column(
                column, width=width, minwidth=90 if column != "details" else 180,
                anchor="w", stretch=column == "details",
            )
        table.grid(row=3, column=0, sticky="nsew", padx=(16, 0), pady=(4, 0))
        scrollbar = ttk.Scrollbar(window, orient="vertical", command=table.yview)
        scrollbar.grid(row=3, column=1, sticky="ns", padx=(0, 16), pady=(4, 0))
        table.configure(yscrollcommand=scrollbar.set)
        horizontal_scrollbar = ttk.Scrollbar(
            window, orient="horizontal", command=table.xview
        )
        horizontal_scrollbar.grid(
            row=4, column=0, sticky="ew", padx=16, pady=(0, 8)
        )
        table.configure(xscrollcommand=horizontal_scrollbar.set)

        table.tag_configure("odd", background="#161a18")
        table.tag_configure("even", background="#101210")
        table.tag_configure("pending", foreground="#f0c05a")
        table.tag_configure("reviewed", foreground="#67d594")
        rows = []
        sort_state = {"column": "date", "descending": True}

        def load_records():
            connection = None
            try:
                connection = sqlite3.connect(DATABASE_FILE)
                records = connection.execute(
                    """
                    SELECT category, summary, details, status, created_at
                    FROM (
                        SELECT id AS record_id, 'Denuncia' AS category,
                               type AS summary,
                               location || ' — ' || description AS details,
                               status, created_at
                        FROM reports
                        UNION ALL
                        SELECT id AS record_id, 'Transporte' AS category,
                               guide AS summary,
                               'Placa: ' || plate || ' | ' || origin || ' → '
                                   || destination AS details,
                               'Registrado' AS status, created_at
                        FROM transport_records
                    )
                    ORDER BY created_at DESC, record_id DESC
                    """
                ).fetchall()
            except sqlite3.Error as error:
                messagebox.showerror(
                    "No se pudieron consultar los registros",
                    f"Consulta la base de datos {DATABASE_FILE}.\n\nDetalle: {error}",
                    parent=window,
                )
                return
            finally:
                if connection is not None:
                    connection.close()
            rows[:] = records
            update_table()

        def update_table(*_args):
            table.delete(*table.get_children())
            category = category_filter.get()
            search_text = search_var.get().strip().casefold()
            visible_rows = [
                row for row in rows
                if (category == "Todos" or row[0] == category)
                and (not search_text or search_text in " ".join(row).casefold())
            ]
            column_index = columns.index(sort_state["column"])
            visible_rows.sort(
                key=lambda row: row[column_index].casefold(),
                reverse=sort_state["descending"],
            )
            for index, row in enumerate(visible_rows):
                tags = ["odd" if index % 2 else "even"]
                if row[3] == "Pendiente":
                    tags.append("pending")
                elif row[3] == "Revisado":
                    tags.append("reviewed")
                table.insert("", "end", values=row, tags=tuple(tags))
            count_label.configure(
                text=(
                    f"{len(visible_rows)} de {len(rows)} registros"
                    if visible_rows else "Sin registros coincidentes"
                )
            )

        def show_record_details(_event=None):
            selection = table.selection()
            if not selection:
                if _event is None:
                    messagebox.showwarning(
                        "Selecciona un registro",
                        "Selecciona un registro de la lista para ver sus detalles.",
                        parent=window,
                    )
                return

            category, summary, details, status, created_at = table.item(
                selection[0], "values"
            )
            detail_window = self._new_window(
                f"Detalle del registro · {category}", "680x480"
            )
            detail_window.minsize(520, 380)
            detail_window.grid_columnconfigure(0, weight=1)
            detail_window.grid_rowconfigure(3, weight=1)
            tk.Label(
                detail_window, text=summary, bg=BACKGROUND, fg=TEXT,
                font=self.title_font, wraplength=620, justify="left"
            ).grid(row=0, column=0, sticky="w", padx=20, pady=(18, 12))

            metadata = tk.Frame(detail_window, bg=BACKGROUND)
            metadata.grid(row=1, column=0, sticky="ew", padx=20)
            for row, (label, value) in enumerate((
                ("Tipo", category),
                ("Estado", status),
                ("Fecha", created_at),
            )):
                tk.Label(
                    metadata, text=f"{label}:", bg=BACKGROUND, fg=MUTED,
                    font=self.subtitle_font
                ).grid(row=row, column=0, sticky="nw", padx=(0, 10), pady=3)
                tk.Label(
                    metadata, text=value, bg=BACKGROUND, fg=TEXT,
                    font=self.subtitle_font, wraplength=500, justify="left"
                ).grid(row=row, column=1, sticky="w", pady=3)

            tk.Label(
                detail_window, text="Descripción e información",
                bg=BACKGROUND, fg=TEXT, font=self.label_font
            ).grid(row=2, column=0, sticky="w", padx=20, pady=(16, 6))
            description = tk.Text(
                detail_window, wrap="word", height=8, bg="#111111", fg=TEXT,
                insertbackground=TEXT, relief="solid", bd=1,
                font=self.subtitle_font, padx=10, pady=8
            )
            description.grid(
                row=3, column=0, sticky="nsew", padx=20, pady=(0, 12)
            )
            description.insert("1.0", details)
            description.configure(state="disabled")
            tk.Button(
                detail_window, text="Cerrar", command=detail_window.destroy,
                bg="#17271d", fg=TEXT, activebackground="#25372c",
                activeforeground=TEXT, relief="flat", cursor="hand2",
                font=self.label_font, padx=14, pady=7
            ).grid(row=4, column=0, sticky="e", padx=20, pady=(0, 16))

        def update_sort_headings():
            for key, heading in (
                ("category", "Tipo"), ("summary", "Registro"),
                ("details", "Detalle"), ("status", "Estado"), ("date", "Fecha"),
            ):
                arrow = (
                    " ▼" if sort_state["descending"] else " ▲"
                ) if key == sort_state["column"] else ""
                table.heading(
                    key, text=heading + arrow, command=lambda c=key: sort_by(c)
                )

        def sort_by(column):
            if sort_state["column"] == column:
                sort_state["descending"] = not sort_state["descending"]
            else:
                sort_state["column"] = column
                sort_state["descending"] = False
            update_sort_headings()
            update_table()

        update_sort_headings()
        category_filter.bind("<<ComboboxSelected>>", update_table)
        search_var.trace_add("write", update_table)
        table.bind("<Double-1>", show_record_details)
        tk.Button(
            filters, text="Actualizar", command=load_records,
            bg=GREEN, fg=TEXT, activebackground="#16834f",
            activeforeground=TEXT, relief="flat", cursor="hand2",
            font=self.subtitle_font, padx=10, pady=3
        ).grid(row=0, column=5, sticky="e")
        controls = tk.Frame(window, bg=BACKGROUND)
        controls.grid(row=5, column=0, columnspan=2, sticky="ew", padx=16, pady=10)
        tk.Label(
            controls, text="Doble clic en un registro para ver sus detalles.",
            bg=BACKGROUND, fg=MUTED, font=self.subtitle_font
        ).pack(side="left")
        tk.Button(
            controls, text="Ver registro seleccionado",
            command=show_record_details, bg=GREEN, fg=TEXT,
            activebackground="#16834f", activeforeground=TEXT,
            relief="flat", cursor="hand2", font=self.label_font,
            padx=12, pady=7
        ).pack(side="right")
        load_records()

    def show_map(self):
        window = self._new_window("Mapa forestal 3D", "720x560")
        window.minsize(560, 460)
        tk.Label(
            window, text="Mapa forestal 3D", bg=BACKGROUND, fg=TEXT,
            font=self.title_font
        ).pack(anchor="w", padx=18, pady=(16, 4))
        tk.Label(
            window,
            text="Vista isométrica ilustrativa; las zonas no representan ubicaciones geográficas reales.",
            bg=BACKGROUND, fg=MUTED, font=self.subtitle_font
        ).pack(anchor="w", padx=18, pady=(0, 10))

        map_canvas = tk.Canvas(
            window, bg="#0b1810", highlightthickness=1,
            highlightbackground=BORDER
        )
        map_canvas.pack(fill="both", expand=True, padx=18, pady=(0, 10))
        zones = [
            (0, 0, 0.5, 0.5, "Zona Norte", GREEN, "Monitoreo activo", "#1c593a"),
            (0.5, 0, 1, 0.5, "Zona Este", "#d3a33d", "Alerta pendiente", "#765722"),
            (0, 0.5, 0.5, 1, "Zona Sur", GREEN, "Monitoreo activo", "#174a32"),
            (0.5, 0.5, 1, 1, "Zona Oeste", "#d3a33d", "Alerta pendiente", "#624b25"),
        ]

        def draw_map(_event=None):
            map_canvas.delete("all")
            width = max(map_canvas.winfo_width(), 1)
            height = max(map_canvas.winfo_height(), 1)
            radius_x = min(width * 0.37, height * 0.72)
            radius_y = min(height * 0.32, width * 0.22)
            center_x = width / 2
            center_y = height / 2
            depth = min(30, height * 0.11)

            def point(u, v, lower=False):
                return (
                    center_x + (u - v) * radius_x,
                    center_y + (u + v - 1) * radius_y + (depth if lower else 0),
                )

            def polygon(points, fill, outline, line_width=1):
                coordinates = [
                    coordinate
                    for u, v, lower in points
                    for coordinate in point(u, v, lower)
                ]
                map_canvas.create_polygon(
                    *coordinates, fill=fill, outline=outline, width=line_width,
                    joinstyle="round",
                )

            # Draw the extruded edges first so the zone surfaces sit on top.
            polygon(
                [(1, 0, False), (1, 1, False), (1, 1, True), (1, 0, True)],
                "#10291d", "#254330",
            )
            polygon(
                [(1, 1, False), (0, 1, False), (0, 1, True), (1, 1, True)],
                "#0c2118", "#254330",
            )
            polygon(
                [(0, 0, False), (1, 0, False), (1, 1, False), (0, 1, False)],
                "#183c29", "#41644a", 2,
            )

            for u1, v1, u2, v2, name, color, status, fill in zones:
                is_vulnerable = name in self.data["vulnerable_zones"]
                zone_color = "#ff6868" if is_vulnerable else color
                zone_fill = "#713533" if is_vulnerable else fill
                polygon(
                    [(u1, v1, False), (u2, v1, False),
                     (u2, v2, False), (u1, v2, False)],
                    zone_fill, zone_color, 3 if is_vulnerable else 2,
                )
                label_x, label_y = point((u1 + u2) / 2, (v1 + v2) / 2)
                map_canvas.create_text(
                    label_x, label_y + 13,
                    text=name, fill=TEXT, font=self.label_font, justify="center"
                )
                map_canvas.create_text(
                    label_x, label_y + 31,
                    text=(
                        "● Área vulnerable" if is_vulnerable else "● " + status
                    ),
                    fill=zone_color,
                    font=self.subtitle_font, justify="center",
                )

                tree_positions = (
                    (u1 + 0.14 * (u2 - u1), v1 + 0.28 * (v2 - v1)),
                    (u1 + 0.78 * (u2 - u1), v1 + 0.20 * (v2 - v1)),
                    (u1 + 0.22 * (u2 - u1), v1 + 0.75 * (v2 - v1)),
                    (u1 + 0.82 * (u2 - u1), v1 + 0.76 * (v2 - v1)),
                )
                for tree_index, (u, v) in enumerate(tree_positions):
                    tree_x, tree_y = point(u, v)
                    tree_height = max(11, min(19, height * 0.055))
                    tree_width = tree_height * 0.7
                    canopy = "#61b779" if tree_index % 2 == 0 else "#388d59"
                    map_canvas.create_polygon(
                        tree_x, tree_y - tree_height,
                        tree_x - tree_width / 2, tree_y - tree_height * 0.28,
                        tree_x + tree_width / 2, tree_y - tree_height * 0.28,
                        fill=canopy, outline="#83c991", width=1,
                    )
                    map_canvas.create_rectangle(
                        tree_x - 1.5, tree_y - tree_height * 0.3,
                        tree_x + 1.5, tree_y,
                        fill="#725333", outline="#725333",
                    )

        def zone_details(event):
            width = max(map_canvas.winfo_width(), 1)
            height = max(map_canvas.winfo_height(), 1)
            radius_x = min(width * 0.37, height * 0.72)
            radius_y = min(height * 0.32, width * 0.22)
            if radius_x <= 0 or radius_y <= 0:
                return
            offset_x = (event.x - width / 2) / radius_x
            offset_y = (event.y - height / 2) / radius_y
            u = (offset_x + offset_y + 1) / 2
            v = (offset_y - offset_x + 1) / 2
            for u1, v1, u2, v2, name, _color, status, _fill in zones:
                if u1 <= u <= u2 and v1 <= v <= v2:
                    detail_window = self._new_window(
                        f"Monitoreo · {name}", "440x300"
                    )
                    detail_window.minsize(400, 260)
                    is_vulnerable = name in self.data["vulnerable_zones"]
                    tk.Label(
                        detail_window, text=name, bg=BACKGROUND, fg=TEXT,
                        font=self.title_font
                    ).pack(anchor="w", padx=20, pady=(20, 8))
                    tk.Label(
                        detail_window,
                        text="Estado de monitoreo: "
                             + ("Área vulnerable" if is_vulnerable else status),
                        bg=BACKGROUND,
                        fg="#ff7777" if is_vulnerable else MUTED,
                        font=self.label_font, wraplength=380, justify="left",
                    ).pack(anchor="w", padx=20, pady=(0, 18))

                    def toggle_vulnerability(zone_name=name):
                        updated_data = json.loads(json.dumps(self.data))
                        vulnerable_zones = set(updated_data["vulnerable_zones"])
                        if zone_name in vulnerable_zones:
                            vulnerable_zones.remove(zone_name)
                        else:
                            vulnerable_zones.add(zone_name)
                        updated_data["vulnerable_zones"] = sorted(vulnerable_zones)
                        if self._save_data(updated_data):
                            draw_map()
                            detail_window.destroy()

                    tk.Label(
                        detail_window,
                        text="Marca esta zona si requiere atención prioritaria.",
                        bg=BACKGROUND, fg=MUTED, font=self.subtitle_font,
                        wraplength=380, justify="left",
                    ).pack(anchor="w", padx=20, pady=(0, 18))
                    controls = tk.Frame(detail_window, bg=BACKGROUND)
                    controls.pack(fill="x", padx=20, pady=(0, 18))
                    tk.Button(
                        controls,
                        text=(
                            "Quitar marca de área vulnerable"
                            if is_vulnerable else "Marcar como área vulnerable"
                        ),
                        command=toggle_vulnerability,
                        bg="#9b4141" if is_vulnerable else GREEN,
                        fg=TEXT, activebackground="#813535" if is_vulnerable
                        else "#16834f",
                        activeforeground=TEXT, relief="flat", cursor="hand2",
                        font=self.label_font, padx=12, pady=8,
                    ).pack(side="left")
                    tk.Button(
                        controls, text="Cerrar", command=detail_window.destroy,
                        bg="#17271d", fg=TEXT, activebackground="#25372c",
                        activeforeground=TEXT, relief="flat", cursor="hand2",
                        font=self.label_font, padx=12, pady=8,
                    ).pack(side="right")
                    return

        map_canvas.bind("<Configure>", draw_map)
        map_canvas.bind("<Button-1>", zone_details)
        map_canvas.configure(cursor="hand2")
        tk.Label(
            window,
            text="Verde: monitoreo activo     Amarillo: alerta pendiente"
                 "     Rojo: área vulnerable. Haz clic en una zona para gestionarla.",
            bg=BACKGROUND, fg=MUTED, font=self.subtitle_font
        ).pack(anchor="w", padx=18, pady=(0, 14))


if __name__ == "__main__":
    root = tk.Tk()
    ForestGuardDashboard(root)
    root.mainloop()
