"""资料抽取工作界面。

先选择或拖入提资文件，确认后打开表单，核对后再写出 design_case.json。
"""

from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from extraction.fields import SPECS, FieldSpec, averaging_choices
from extraction.parsers.collection_sheet import (
    AmbiguousCollectionSheet,
    CollectionSheetNotFound,
    find_collection_sheet,
    read_collection_sheet,
)
from extraction.paths import design_case_path
from extraction.tools.design_case import (
    assign,
    blank_case,
    build_parameters,
    lookup,
    project_id_from_name,
    validate_design_case,
    write_design_case,
)

_FONT = ("Microsoft YaHei UI", 10)
_FONT_SMALL = ("Microsoft YaHei UI", 8)
_FONT_BOLD = ("Microsoft YaHei UI", 11, "bold")
_FONT_TITLE = ("Microsoft YaHei UI", 13, "bold")
_EMPTY_BG = "#fff4d6"
_FIELD_BG = "#ffffff"
_DROP_BG = "#f4f7fb"
_PAGE = "#e7edf3"
_PAPER = "#ffffff"
_HEAD = "#1f4e79"
_LINE = "#d5dde6"
_LABEL = "#1c2833"
_MUTED = "#5c6b7a"
_INVALID_PATH = '<>:"/\\|?*'
_SPEC_BY_KEY = {spec.key: spec for spec in SPECS}


def main() -> int:
    root, drag_enabled = _make_root()
    root.title("资料抽取")
    root.geometry("760x560")
    root.minsize(640, 480)
    IntakeWindow(root, drag_enabled)
    root.mainloop()
    return 0


def _make_root() -> tuple[tk.Tk, bool]:
    try:
        from tkinterdnd2 import TkinterDnD

        return TkinterDnD.Tk(), True
    except Exception:
        return tk.Tk(), False


class IntakeWindow:
    """选择提资文件。拖入和按钮是同一条路径。"""

    def __init__(self, root: tk.Tk, drag_enabled: bool) -> None:
        self.root = root
        self.paths: list[Path] = []
        root.option_add("*Font", _FONT)

        frame = ttk.Frame(root, padding=16)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text="资料抽取", font=_FONT_BOLD).pack(anchor="w")
        ttk.Label(
            frame,
            text="选择客户提资文件。确认后会查找 Design Data Collection Sheet，并打开核对表单。",
        ).pack(anchor="w", pady=(4, 12))

        hint = "将提资文件拖到这里" if drag_enabled else "拖放组件未装好，请使用选择文件"
        self.drop = tk.Label(
            frame,
            text=hint,
            bg=_DROP_BG,
            relief="groove",
            bd=2,
            padx=12,
            pady=28,
            font=_FONT,
        )
        self.drop.pack(fill="x")
        if drag_enabled:
            self._enable_drop()

        buttons = ttk.Frame(frame)
        buttons.pack(fill="x", pady=10)
        ttk.Button(buttons, text="选择文件", command=self.choose_files).pack(side="left")
        ttk.Button(buttons, text="移除选中", command=self.remove_selected).pack(side="left", padx=8)
        ttk.Button(buttons, text="清空", command=self.clear).pack(side="left")

        list_frame = ttk.Frame(frame)
        list_frame.pack(fill="both", expand=True)
        self.files = tk.Listbox(list_frame, activestyle="dotbox", font=_FONT)
        scroll = ttk.Scrollbar(list_frame, orient="vertical", command=self.files.yview)
        self.files.configure(yscrollcommand=scroll.set)
        self.files.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")

        ttk.Button(frame, text="确认", command=self.confirm).pack(anchor="e", pady=(12, 0))

    def _enable_drop(self) -> None:
        from tkinterdnd2 import DND_FILES

        self.drop.drop_target_register(DND_FILES)
        self.drop.dnd_bind("<<Drop>>", self._on_drop)

    def _on_drop(self, event: tk.Event) -> None:
        self.add_paths(self.root.tk.splitlist(event.data))

    def choose_files(self) -> None:
        selected = filedialog.askopenfilenames(
            title="选择提资文件",
            filetypes=[
                ("提资文件", "*.pdf *.xlsx *.xls *.docx *.doc *.dwg"),
                ("PDF", "*.pdf"),
                ("全部文件", "*.*"),
            ],
        )
        self.add_paths(selected)

    def add_paths(self, raw_paths: tuple[str, ...] | list[str]) -> None:
        known = {path.resolve() for path in self.paths}
        for raw in raw_paths:
            path = Path(raw)
            if not path.exists():
                continue
            resolved = path.resolve()
            if resolved in known:
                continue
            known.add(resolved)
            self.paths.append(path)
            self.files.insert("end", str(path))

    def remove_selected(self) -> None:
        indexes = list(self.files.curselection())
        for index in reversed(indexes):
            del self.paths[index]
            self.files.delete(index)

    def clear(self) -> None:
        self.paths.clear()
        self.files.delete(0, "end")

    def confirm(self) -> None:
        if not self.paths:
            messagebox.showwarning("还没有文件", "请先选择或拖入提资文件。", parent=self.root)
            return
        try:
            sheet = find_collection_sheet(self.paths)
            parsed = read_collection_sheet(sheet)
        except (CollectionSheetNotFound, AmbiguousCollectionSheet) as exc:
            messagebox.showerror("没有定位到资料表", str(exc), parent=self.root)
            return
        except Exception as exc:
            messagebox.showerror("读取资料表失败", str(exc), parent=self.root)
            return
        ReviewWindow(self.root, parsed)


class ReviewWindow(tk.Toplevel):
    """按资料表版式核对字段。确认后写出 design_case.json。"""

    def __init__(self, master: tk.Tk, parsed: dict) -> None:
        super().__init__(master)
        self.parsed = parsed
        self.extracted = dict(parsed.get("values", {}))
        self.title("核对设计案例")
        self.geometry("1100x820")
        self.minsize(960, 640)
        self.configure(bg=_PAGE)
        self.transient(master)

        name = self.extracted.get("site.project_name")
        self.project_id = tk.StringVar(value=project_id_from_name(name if isinstance(name, str) else None))
        self.revision = tk.StringVar(value="r0")
        self.product_family = tk.StringVar(value="fixed_tilt")
        self.variables: dict[str, tk.StringVar] = {}
        self.inputs: dict[str, tk.Widget] = {}

        shell = tk.Frame(self, bg=_PAGE)
        shell.pack(fill="both", expand=True)

        footer = tk.Frame(shell, bg="#d9e2ec", padx=12, pady=8)
        footer.pack(side="bottom", fill="x")
        self.pending = tk.Label(footer, text="", bg="#d9e2ec", fg=_LABEL, anchor="w")
        self.pending.pack(side="left", fill="x", expand=True)
        self.confirm_button = tk.Button(
            footer,
            text="确认",
            command=self.save,
            font=_FONT_BOLD,
            bg=_HEAD,
            fg="white",
            activebackground="#163a5c",
            activeforeground="white",
            relief="flat",
            padx=28,
            pady=6,
            cursor="hand2",
        )
        self.confirm_button.pack(side="right")

        canvas = tk.Canvas(shell, bg=_PAGE, highlightthickness=0)
        scroll = ttk.Scrollbar(shell, orient="vertical", command=canvas.yview)
        self.form = tk.Frame(canvas, bg=_PAGE)
        self.form.bind("<Configure>", lambda _event: canvas.configure(scrollregion=canvas.bbox("all")))
        window = canvas.create_window((0, 0), window=self.form, anchor="nw")
        canvas.configure(yscrollcommand=scroll.set)
        canvas.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        canvas.bind("<Configure>", lambda event: canvas.itemconfigure(window, width=event.width))

        def wheel(event: tk.Event) -> None:
            canvas.yview_scroll(int(-event.delta / 120), "units")

        canvas.bind("<Enter>", lambda _event: canvas.bind_all("<MouseWheel>", wheel))
        canvas.bind("<Leave>", lambda _event: canvas.unbind_all("<MouseWheel>"))
        self.bind("<Destroy>", lambda event: canvas.unbind_all("<MouseWheel>") if event.widget is self else None)

        self._build_sheet()
        missing = {spec.key for spec in SPECS} - set(self.variables)
        if missing:
            raise RuntimeError("表单缺少字段：" + ", ".join(sorted(missing)))
        for variable in (self.project_id, self.revision):
            variable.trace_add("write", lambda *_args: self._refresh_pending())
        self._refresh_pending()
        self.grab_set()

    def _build_sheet(self) -> None:
        paper = tk.Frame(self.form, bg=_PAPER, padx=18, pady=14, highlightbackground=_LINE, highlightthickness=1)
        paper.pack(fill="both", expand=True, padx=16, pady=12)
        tk.Label(
            paper,
            text="TECHNICAL DATA COLLECTION FOR FIXED TILT STRUCTURE",
            bg=_PAPER,
            fg=_HEAD,
            font=_FONT_TITLE,
        ).pack(anchor="w")
        tk.Label(
            paper,
            text=self.parsed.get("source_name", ""),
            bg=_PAPER,
            fg=_MUTED,
            font=_FONT,
        ).pack(anchor="w", pady=(2, 8))
        warnings = self.parsed.get("warnings") or []
        if warnings:
            tk.Label(paper, text="\n".join(warnings), bg=_PAPER, fg="#8a5a00", justify="left").pack(anchor="w")

        identity = tk.Frame(paper, bg="#f4f7fb", padx=8, pady=6)
        identity.pack(fill="x", pady=(0, 8))
        self._identity_field(identity, "项目编号", self.project_id, 18)
        self._identity_field(identity, "修订", self.revision, 8)
        self._identity_field(identity, "产品族", self.product_family, 16)

        grid = tk.Frame(paper, bg=_PAPER)
        grid.pack(fill="both", expand=True)
        grid.columnconfigure(0, weight=1, uniform="sheet")
        grid.columnconfigure(1, weight=1, uniform="sheet")

        self._general().grid(in_=grid, row=0, column=0, sticky="nsew", padx=(0, 6), pady=4)
        self._site().grid(in_=grid, row=0, column=1, sticky="nsew", padx=(6, 0), pady=4)
        self._module().grid(in_=grid, row=1, column=0, sticky="nsew", padx=(0, 6), pady=4)
        self._design().grid(in_=grid, row=1, column=1, sticky="nsew", padx=(6, 0), pady=4)
        self._foundation().grid(in_=grid, row=2, column=0, columnspan=2, sticky="nsew", pady=4)
        self._geology().grid(in_=grid, row=3, column=0, columnspan=2, sticky="nsew", pady=4)
        self._corrosion().grid(in_=grid, row=4, column=0, columnspan=2, sticky="nsew", pady=4)
        self._documents().grid(in_=grid, row=5, column=0, columnspan=2, sticky="nsew", pady=4)
        self._remarks().grid(in_=grid, row=6, column=0, columnspan=2, sticky="nsew", pady=4)

    def _block(self, title: str) -> tuple[tk.Frame, tk.Frame]:
        block = tk.Frame(self.form, bg=_PAPER, highlightbackground=_LINE, highlightthickness=1)
        tk.Label(block, text=title, bg=_HEAD, fg="white", anchor="w", font=_FONT_BOLD, padx=8, pady=4).pack(fill="x")
        body = tk.Frame(block, bg=_PAPER, padx=8, pady=6)
        body.pack(fill="both", expand=True)
        return block, body

    def _field_var(self, key: str) -> tk.StringVar:
        spec = _SPEC_BY_KEY[key]
        variable = tk.StringVar(value=_display(spec, self.extracted.get(key)))
        self.variables[key] = variable
        variable.trace_add("write", lambda *_args: self._refresh_pending())
        return variable

    def _identity_field(self, parent: tk.Frame, caption: str, variable: tk.StringVar, width: int) -> None:
        tk.Label(parent, text=caption, bg="#f4f7fb", fg=_LABEL).pack(side="left")
        tk.Entry(parent, textvariable=variable, width=width, font=_FONT, relief="solid", bd=1).pack(side="left", padx=(4, 14))

    def _label(self, parent: tk.Widget, text: str) -> tk.Label:
        return tk.Label(parent, text=text, bg=_PAPER, fg=_LABEL, anchor="w")

    def _entry(self, parent: tk.Widget, key: str, width: int = 14) -> tk.Entry:
        variable = self._field_var(key)
        entry = tk.Entry(parent, textvariable=variable, width=width, font=_FONT, relief="solid", bd=1)
        self.inputs[key] = entry
        variable.trace_add("write", lambda *_args, widget=entry, source=variable: _paint(widget, source))
        _paint(entry, variable)
        return entry

    def _combo(self, parent: tk.Widget, key: str, width: int = 22) -> ttk.Combobox:
        spec = _SPEC_BY_KEY[key]
        variable = self._field_var(key)
        box = ttk.Combobox(parent, textvariable=variable, values=("", *spec.choices), state="readonly", width=width, font=_FONT)
        self.inputs[key] = box
        return box

    def _general(self) -> tk.Frame:
        block, body = self._block("1. General Information")
        body.columnconfigure(1, weight=1)
        rows = (
            ("Client Name", "site.client_name", None),
            ("Project Name", "site.project_name", None),
            ("Country", "site.country", None),
        )
        for row, (caption, key, _unit) in enumerate(rows):
            self._label(body, caption).grid(row=row, column=0, sticky="w", pady=3, padx=(0, 8))
            self._entry(body, key, 28).grid(row=row, column=1, sticky="ew", pady=3)
        self._label(body, "Capacity").grid(row=3, column=0, sticky="w", pady=3, padx=(0, 8))
        capacity = tk.Frame(body, bg=_PAPER)
        capacity.grid(row=3, column=1, sticky="ew", pady=3)
        self._entry(capacity, "site.capacity_mw_dc", 12).pack(side="left")
        self._label(capacity, "MW(DC)").pack(side="left", padx=6)
        return block

    def _site(self) -> tk.Frame:
        block, body = self._block("2. Project Site Information")
        body.columnconfigure(1, weight=1)
        self._label(body, "Longitude").grid(row=0, column=0, sticky="w", pady=3, padx=(0, 8))
        longitude = tk.Frame(body, bg=_PAPER)
        longitude.grid(row=0, column=1, sticky="ew", pady=3)
        self._entry(longitude, "site.longitude", 16).pack(side="left")
        self._combo(longitude, "site.longitude_hemisphere", 4).pack(side="left", padx=6)
        self._label(body, "Latitude").grid(row=1, column=0, sticky="w", pady=3, padx=(0, 8))
        latitude = tk.Frame(body, bg=_PAPER)
        latitude.grid(row=1, column=1, sticky="ew", pady=3)
        self._entry(latitude, "site.latitude", 16).pack(side="left")
        self._combo(latitude, "site.latitude_hemisphere", 4).pack(side="left", padx=6)
        self._label(body, "Altitude").grid(row=2, column=0, sticky="w", pady=3, padx=(0, 8))
        altitude = tk.Frame(body, bg=_PAPER)
        altitude.grid(row=2, column=1, sticky="w", pady=3)
        self._entry(altitude, "site.altitude_m", 10).pack(side="left")
        self._label(altitude, "m").pack(side="left", padx=6)
        self._label(body, "Mounting Type").grid(row=3, column=0, sticky="w", pady=3, padx=(0, 8))
        self._combo(body, "geometry.mounting_type", 16).grid(row=3, column=1, sticky="w", pady=3)
        return block

    def _module(self) -> tk.Frame:
        block, body = self._block("3. Module Information")
        size = tk.Frame(body, bg=_PAPER)
        size.pack(fill="x", pady=3)
        self._label(size, "L*W*H").pack(side="left")
        self._entry(size, "geometry.module_length_mm", 7).pack(side="left", padx=(8, 2))
        self._label(size, "*").pack(side="left")
        self._entry(size, "geometry.module_width_mm", 7).pack(side="left", padx=2)
        self._label(size, "*").pack(side="left")
        self._entry(size, "geometry.module_thickness_mm", 6).pack(side="left", padx=2)
        self._label(size, "mm").pack(side="left", padx=4)

        measures = tk.Frame(body, bg=_PAPER)
        measures.pack(fill="x", pady=3)
        self._label(measures, "Weight").pack(side="left")
        self._entry(measures, "geometry.module_weight_kg", 8).pack(side="left", padx=(8, 2))
        self._label(measures, "kg").pack(side="left", padx=(0, 12))
        self._label(measures, "Module Power").pack(side="left")
        self._entry(measures, "geometry.module_power_wp", 8).pack(side="left", padx=(8, 2))
        self._label(measures, "Wp").pack(side="left")

        per_string = tk.Frame(body, bg=_PAPER)
        per_string.pack(fill="x", pady=3)
        self._label(per_string, "Modules per String").pack(side="left")
        self._entry(per_string, "geometry.modules_per_string", 8).pack(side="left", padx=8)

        kind = tk.Frame(body, bg=_PAPER)
        kind.pack(fill="x", pady=3)
        self._label(kind, "Module Type").pack(side="left")
        self._combo(kind, "geometry.module_type", 14).pack(side="left", padx=8)

        orientation = tk.Frame(body, bg=_PAPER)
        orientation.pack(fill="x", pady=3)
        self._label(orientation, "Orientation").pack(side="left")
        facing = self._field_var("geometry.module_orientation")
        for value in ("Portrait", "Landscape"):
            tk.Radiobutton(
                orientation,
                text=value,
                variable=facing,
                value=value,
                bg=_PAPER,
                activebackground=_PAPER,
                font=_FONT,
            ).pack(side="left", padx=6)

        arrangement = tk.Frame(body, bg=_PAPER)
        arrangement.pack(fill="x", pady=3)
        self._label(arrangement, "Row").pack(side="left")
        self._entry(arrangement, "geometry.arrangement_rows", 6).pack(side="left", padx=(8, 2))
        self._label(arrangement, "*  Column").pack(side="left")
        self._entry(arrangement, "geometry.arrangement_columns", 8).pack(side="left", padx=6)
        return block

    def _design(self) -> tk.Frame:
        block, body = self._block("4. Design Information")
        code = tk.Frame(body, bg=_PAPER)
        code.pack(fill="x", pady=3)
        self._label(code, "Design Code").pack(side="left")
        self._combo(code, "site.design_code", 24).pack(side="left", padx=8)
        self._value_unit(body, "Wind Speed", "site.wind_speed", "site.wind_speed_unit")
        self._averaging_period(body)
        self._value_unit(body, "Snow Load", "site.snow_load", "site.snow_load_unit")
        self._value_unit(body, "Seismic Load", "site.seismic_load", "site.seismic_load_unit")
        temperature = tk.Frame(body, bg=_PAPER)
        temperature.pack(fill="x", pady=3)
        self._label(temperature, "Temperature").pack(side="left")
        self._entry(temperature, "site.temperature_low_c", 6).pack(side="left", padx=(8, 2))
        self._label(temperature, "~").pack(side="left")
        self._entry(temperature, "site.temperature_high_c", 6).pack(side="left", padx=2)
        self._label(temperature, "°C").pack(side="left", padx=4)
        risk = tk.Frame(body, bg=_PAPER)
        risk.pack(fill="x", pady=3)
        self._label(risk, "Risk Category").pack(side="left")
        self._combo(risk, "site.risk_category", 8).pack(side="left", padx=8)
        return block

    def _averaging_period(self, parent: tk.Frame) -> None:
        row = tk.Frame(parent, bg=_PAPER)
        row.pack(fill="x", pady=3)
        self._label(row, "Averaging Period").pack(side="left")
        variable = self._field_var("site.wind_speed_averaging")
        box = ttk.Combobox(row, textvariable=variable, state="readonly", width=16, font=_FONT)
        box.pack(side="left", padx=8)
        self.inputs["site.wind_speed_averaging"] = box
        hint = tk.Label(row, text="", bg=_PAPER, fg=_MUTED, font=_FONT_SMALL)
        hint.pack(side="left")

        def refresh(*_args: object) -> None:
            code = self.variables["site.design_code"].get().strip()
            choices = averaging_choices(code or None)
            box.configure(values=("", *choices))
            if variable.get() not in ("", *choices):
                variable.set("")
            hint.configure(text=f"基本风速：{choices[0]}" if choices else "请先选择设计规范")

        self.variables["site.design_code"].trace_add("write", refresh)
        refresh()

    def _value_unit(self, parent: tk.Frame, caption: str, value_key: str, unit_key: str) -> None:
        row = tk.Frame(parent, bg=_PAPER)
        row.pack(fill="x", pady=3)
        self._label(row, caption).pack(side="left")
        self._entry(row, value_key, 8).pack(side="left", padx=8)
        self._combo(row, unit_key, 8).pack(side="left")

    def _foundation(self) -> tk.Frame:
        block, body = self._block("5. Pile And Foundation Design Information")
        top = tk.Frame(body, bg=_PAPER)
        top.pack(fill="x", pady=3)
        self._label(top, "Foundation Type").pack(side="left")
        self._combo(top, "geometry.foundation_type", 16).pack(side="left", padx=(8, 18))
        self._label(top, "Pile Embedment Depth").pack(side="left")
        self._entry(top, "geometry.pile_embedment_depth_mm", 8).pack(side="left", padx=8)
        self._label(top, "mm").pack(side="left")
        bottom = tk.Frame(body, bg=_PAPER)
        bottom.pack(fill="x", pady=3)
        self._label(bottom, "Tilt Angle").pack(side="left")
        self._entry(bottom, "geometry.tilt_angle_deg", 6).pack(side="left", padx=(8, 2))
        self._label(bottom, "°").pack(side="left", padx=(0, 18))
        self._label(bottom, "Clearance").pack(side="left")
        self._entry(bottom, "geometry.ground_clearance_mm", 8).pack(side="left", padx=8)
        self._label(bottom, "mm").pack(side="left")
        return block

    def _geology(self) -> tk.Frame:
        block, body = self._block("6. Site Geological Type")
        variable = self._field_var("site.geological_type")
        cards = (
            ("Type 1", "Offshore seas and islands,\ncoasts, lake shores"),
            ("Type 2", "Flat site with few obstacles"),
            ("Type 3", "Urban areas with\ndense buildings"),
            ("Type 4", "Urban areas with dense\nbuildings and high housing"),
        )
        for column, (value, text) in enumerate(cards):
            body.columnconfigure(column, weight=1)
            card = tk.Frame(body, bg=_PAPER)
            card.grid(row=0, column=column, sticky="nsew", padx=4)
            tk.Radiobutton(
                card, text=value, variable=variable, value=value, bg=_PAPER, activebackground=_PAPER, anchor="w", font=_FONT
            ).pack(anchor="w")
            tk.Label(card, text=text, bg=_PAPER, fg=_MUTED, justify="left", font=_FONT_SMALL).pack(anchor="w")
        return block

    def _corrosion(self) -> tk.Frame:
        block, body = self._block("7. Atmospheric Corrosion Category (ISO 9223)")
        variable = self._field_var("materials.corrosion_category")
        for value in ("C1", "C2", "C3", "C4", "C5"):
            tk.Radiobutton(
                body, text=value, variable=variable, value=value, bg=_PAPER, activebackground=_PAPER, font=_FONT
            ).pack(side="left", padx=12)
        return block

    def _documents(self) -> tk.Frame:
        block, body = self._block("8. Other Documents Input")
        items = (
            ("site.documents.module_datasheet", "Module Datasheet"),
            ("site.documents.layout", "Layout"),
            ("site.documents.site_geological_plan", "Site Geological Plan"),
            ("site.documents.pull_out_test_report", "Pull Out Test Report"),
            ("site.documents.topographic_drawing", "Topographic Drawing"),
            ("site.documents.cable_route_plan", "Cable Route Plan"),
        )
        for index, (key, caption) in enumerate(items):
            variable = self._field_var(key)
            checked = tk.IntVar(value=1 if variable.get() == "已提供" else 0)

            def toggle(source: tk.StringVar = variable, flag: tk.IntVar = checked) -> None:
                source.set("已提供" if flag.get() else "未提供")

            tk.Checkbutton(
                body,
                text=caption,
                variable=checked,
                command=toggle,
                bg=_PAPER,
                activebackground=_PAPER,
                font=_FONT,
            ).grid(row=index // 3, column=index % 3, sticky="w", padx=8, pady=3)
        return block

    def _remarks(self) -> tk.Frame:
        block, body = self._block("9. Remarks")
        variable = self._field_var("site.remarks")
        text = tk.Text(body, height=3, font=_FONT, wrap="word", relief="solid", bd=1)
        text.pack(fill="x")
        text.insert("1.0", variable.get())

        def pull(_event: tk.Event | None = None) -> None:
            variable.set(text.get("1.0", "end").strip())

        text.bind("<KeyRelease>", pull)
        text.bind("<<Paste>>", lambda _event: text.after_idle(pull))
        text.bind("<FocusOut>", pull)
        self.inputs["site.remarks"] = text
        _paint_text(text, variable.get())
        variable.trace_add("write", lambda *_args: _paint_text(text, variable.get()))
        return block

    def _refresh_pending(self) -> None:
        if len(self.variables) < len(SPECS):
            return
        missing = sum(1 for spec in SPECS if not self.variables[spec.key].get().strip())
        target = design_case_path(self.project_id.get().strip() or "…", self.revision.get().strip() or "…")
        self.pending.configure(text=f"未填 {missing} 项    确认后写入 {target}")

    def save(self) -> None:
        try:
            case = self._collect_case()
        except ValueError as exc:
            messagebox.showerror("还有问题", str(exc), parent=self)
            return
        missing = sum(1 for spec in SPECS if lookup(case, spec.key) is None)
        if missing:
            proceed = messagebox.askokcancel(
                "还有未填项",
                f"还有 {missing} 项是空的，这些项会以 null 写入。\n仍要确认并生成吗？",
                parent=self,
            )
            if not proceed:
                return
        output = design_case_path(case["project_id"], case["revision"])
        try:
            write_design_case(case, output, self.parsed)
        except ValueError as exc:
            messagebox.showerror("不符合设计案例格式", str(exc), parent=self)
            return
        except OSError as exc:
            messagebox.showerror("无法写入文件", str(exc), parent=self)
            return
        messagebox.showinfo("已生成", f"已写入\n{output}", parent=self)
        self.destroy()

    def _collect_case(self) -> dict:
        project_id = self.project_id.get().strip()
        revision = self.revision.get().strip()
        product_family = self.product_family.get().strip()
        problems: list[str] = []
        if not project_id:
            problems.append("请填写项目编号。")
        elif any(char in project_id for char in _INVALID_PATH):
            problems.append("项目编号不能包含 \\ / : * ? \" < > |。")
        if not revision:
            problems.append("请填写修订。")
        if not product_family:
            problems.append("请填写产品族。")

        case = blank_case(project_id or "PROJECT", revision or "r0", "confirmed", product_family or "fixed_tilt")
        for spec in SPECS:
            raw = self.variables[spec.key].get().strip()
            try:
                assign(case, spec.key, _coerce(spec, raw))
            except ValueError as exc:
                problems.append(str(exc))
        case["code_pack"] = case["site"]["design_code"]
        period = case["site"]["wind_speed_averaging"]
        code = case["site"]["design_code"]
        if period is not None and period not in averaging_choices(code):
            if code:
                problems.append("风速时距不在该设计规范的可选范围内。")
            else:
                problems.append("请先选择设计规范，再选择风速时距。")
        if problems:
            raise ValueError("\n".join(problems))
        case["parameters"] = build_parameters(case, self.extracted, self.parsed.get("source_name", ""))
        validate_design_case(case)
        return case


def _display(spec: FieldSpec, value: object) -> str:
    if value is None:
        return ""
    if spec.kind == "bool":
        return "已提供" if value else "未提供"
    return str(value)


def _coerce(spec: FieldSpec, raw: str) -> object:
    if spec.kind == "bool":
        if raw == "":
            return None
        if raw == "已提供":
            return True
        if raw == "未提供":
            return False
        raise ValueError(f"{spec.label} 请选择已提供、未提供，或留空。")
    if spec.kind in {"enum", "radio"}:
        if raw == "":
            return None
        if raw not in spec.choices:
            raise ValueError(f"{spec.label} 不在可选范围内。")
        return raw
    if spec.kind == "number":
        if raw == "":
            return None
        try:
            number = float(raw.replace(",", ""))
        except ValueError as exc:
            raise ValueError(f"{spec.label} 需要填写数字。") from exc
        if number.is_integer():
            return int(number)
        return number
    return raw or None


def _paint(widget: tk.Entry, variable: tk.StringVar) -> None:
    widget.configure(bg=_EMPTY_BG if not variable.get().strip() else _FIELD_BG)


def _paint_text(widget: tk.Text, value: str) -> None:
    widget.configure(bg=_EMPTY_BG if not value.strip() else _FIELD_BG)
