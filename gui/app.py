import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from utils.models import Part, Sheet
from utils.packing import pack_parts
from utils.importers import (
    parse_excel, parse_excel_map, parse_csv,
    create_excel_template, HAS_OPENPYXL,
)
from utils.exporters import build_print_html, export_to_txt, export_to_excel
from gui.viewer import SheetViewer
from gui.manual_editor import ManualSheetEditor
from utils.constants import COLORS
import csv
from typing import List


# ============================================================
#  ИНТЕРФЕЙС
# ============================================================

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Раскрой ЛДСП — оптимизированная версия")
        self.geometry("1280x800")

        self.parts: List[Part] = []
        self.sheets: List[Sheet] = []

        self.sheet_w = tk.IntVar(value=2750)
        self.sheet_h = tk.IntVar(value=1830)
        self.kerf = tk.IntVar(value=4)
        self.allow_rotation = tk.BooleanVar(value=True)
        self.multi_start = tk.BooleanVar(value=True)

        self._build_ui()

    def _build_ui(self):
        # Главная раскладка:
        #   строка 0 — статус-бар (фиксированная высота, на всю ширину)
        #   строка 1 — контент (левая панель + правая панель)
        #   столбец 0 — левая панель (фиксированный)
        #   столбец 1 — правая панель (растягивается)
        self.grid_rowconfigure(0, weight=0)  # статус-бар — фикс
        self.grid_rowconfigure(1, weight=1)  # контент — растягивается
        self.grid_columnconfigure(0, weight=0)  # левая — фикс
        self.grid_columnconfigure(1, weight=1)  # правая — растягивается

        # ============ ЛЕВАЯ ПАНЕЛЬ (управление) ============
        left = ttk.Frame(self, padding=10)
        left.grid(row=1, column=0, sticky="ns")

        ttk.Label(left, text="Размер листа (мм)").pack(anchor=tk.W)
        row = ttk.Frame(left);
        row.pack(fill=tk.X, pady=2)
        ttk.Label(row, text="Ш:").pack(side=tk.LEFT)
        ttk.Entry(row, textvariable=self.sheet_w, width=6).pack(side=tk.LEFT)
        ttk.Label(row, text=" В:").pack(side=tk.LEFT)
        ttk.Entry(row, textvariable=self.sheet_h, width=6).pack(side=tk.LEFT)

        row = ttk.Frame(left);
        row.pack(fill=tk.X, pady=2)
        ttk.Label(row, text="Толщина пила (мм):").pack(side=tk.LEFT)
        ttk.Entry(row, textvariable=self.kerf, width=5).pack(side=tk.LEFT)

        opts = ttk.LabelFrame(left, text="Параметры раскроя", padding=5)
        opts.pack(fill=tk.X, pady=6)
        ttk.Checkbutton(opts, text="Разрешить поворот деталей",
                        variable=self.allow_rotation).pack(anchor=tk.W)
        ttk.Checkbutton(opts, text="Multi-start (поиск лучшего варианта)",
                        variable=self.multi_start).pack(anchor=tk.W)

        ttk.Separator(left, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=6)

        import_frame = ttk.LabelFrame(left, text="Импорт деталей", padding=5)
        import_frame.pack(fill=tk.X, pady=4)
        ttk.Button(import_frame, text="Импорт из Excel (.xlsx)",
                   command=self.import_excel).pack(fill=tk.X, pady=2)
        ttk.Button(import_frame, text="Импорт из CSV",
                   command=self.import_csv).pack(fill=tk.X, pady=2)
        ttk.Button(import_frame, text="Шаблон Excel",
                   command=self.save_template).pack(fill=tk.X, pady=2)
        ttk.Button(import_frame, text="Шаблон CSV",
                   command=self.save_csv_template).pack(fill=tk.X, pady=2)

        ttk.Separator(left, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=6)

        ttk.Label(left, text="Детали").pack(anchor=tk.W)
        self.tree = ttk.Treeview(left, columns=("name", "w", "h", "qty"),
                                 show="headings", height=12)
        self.tree.heading("name", text="Название")
        self.tree.heading("w", text="Ширина")
        self.tree.heading("h", text="Высота")
        self.tree.heading("qty", text="Кол-во")
        self.tree.column("name", width=120)
        self.tree.column("w", width=60, anchor=tk.E)
        self.tree.column("h", width=60, anchor=tk.E)
        self.tree.column("qty", width=50, anchor=tk.E)
        self.tree.pack(fill=tk.X, pady=4)

        add = ttk.LabelFrame(left, text="Добавить деталь", padding=5)
        add.pack(fill=tk.X, pady=4)

        # Все поля — в одну строку
        r = ttk.Frame(add);
        r.pack(fill=tk.X)

        # Название — самое широкое поле
        self.e_name = tk.Entry(r, width=14, fg="gray")
        self.e_name.grid(row=0, column=0, padx=2, pady=2, sticky="ew")
        self._add_placeholder(self.e_name, "Название")

        # Ширина
        self.e_w = tk.Entry(r, width=6, fg="gray")
        self.e_w.grid(row=0, column=1, padx=2, pady=2, sticky="ew")
        self._add_placeholder(self.e_w, "Ширина")

        # Высота
        self.e_h = tk.Entry(r, width=6, fg="gray")
        self.e_h.grid(row=0, column=2, padx=2, pady=2, sticky="ew")
        self._add_placeholder(self.e_h, "Высота")

        # Количество — с предзаполнением "1"
        self.e_qty = tk.Entry(r, width=5)
        self.e_qty.insert(0, "1")
        self.e_qty.grid(row=0, column=3, padx=2, pady=2, sticky="ew")

        # Кнопка «Добавить» — там же, справа
        ttk.Button(r, text="Добавить", width=9,
                   command=self.add_part).grid(row=0, column=4, padx=4, pady=2)

        # Настраиваем растягивание: Название растягивается, остальные — фикс.
        r.grid_columnconfigure(0, weight=1)  # Название
        r.grid_columnconfigure(1, weight=0)  # Ширина
        r.grid_columnconfigure(2, weight=0)  # Высота
        r.grid_columnconfigure(3, weight=0)  # Кол-во
        r.grid_columnconfigure(4, weight=0)  # Кнопка

        btn_row = ttk.Frame(left);
        btn_row.pack(fill=tk.X, pady=4)
        ttk.Button(btn_row, text="Удалить",
                   command=self.del_part).pack(side=tk.LEFT)
        ttk.Button(btn_row, text="Очистить",
                   command=self.clear_parts).pack(side=tk.LEFT, padx=4)

        ttk.Button(left, text="РАССЧИТАТЬ РАСКРОЙ",
                   command=self.calc).pack(fill=tk.X, pady=8)
        ttk.Button(left, text="Сохранить отчёт",
                   command=self.save_report).pack(fill=tk.X, pady=2)
        ttk.Button(left, text="Экспорт карты в Excel",
                   command=self.export_excel_map).pack(fill=tk.X, pady=2)
        ttk.Button(left, text="🔍 Просмотр листов",
                   command=self.open_viewer).pack(fill=tk.X, pady=2)
        ttk.Button(left, text="✏️ Ручной раскрой",
                   command=self.open_manual_editor).pack(fill=tk.X, pady=2)
        ttk.Button(left, text="🖨️ Печать всех листов",
                   command=self.print_all_sheets).pack(fill=tk.X, pady=2)

        # ============ ПРАВАЯ ПАНЕЛЬ (Canvas) ============
        right = tk.Frame(self, bg="white")
        right.grid(row=1, column=1, sticky="nsew")

        v_scroll = ttk.Scrollbar(right, orient=tk.VERTICAL)
        v_scroll.pack(side=tk.RIGHT, fill=tk.Y)

        h_scroll = ttk.Scrollbar(right, orient=tk.HORIZONTAL)
        h_scroll.pack(side=tk.BOTTOM, fill=tk.X)

        self.canvas = tk.Canvas(
            right, bg="white", highlightthickness=0,
            yscrollcommand=v_scroll.set,
            xscrollcommand=h_scroll.set,
        )
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        v_scroll.config(command=self.canvas.yview)
        h_scroll.config(command=self.canvas.xview)

        # Прокрутка колёсиком мыши
        self.canvas.bind_all("<MouseWheel>", self._on_mousewheel)
        self.canvas.bind_all("<Shift-MouseWheel>", self._on_shift_mousewheel)

        # ============ СТАТУС-БАР (сверху) ============
        self.status = ttk.Label(self, text="Готово",
                                relief=tk.SUNKEN, anchor=tk.W,
                                padding=(5, 3))
        self.status.grid(row=0, column=0, columnspan=2, sticky="ew")

    def _add_placeholder(self, entry, text):
        """Добавляет placeholder в Entry: серый текст, исчезает при фокусе."""
        entry.insert(0, text)
        entry.config(fg="#999999")

        def on_focus_in(event):
            if entry.get() == text:
                entry.delete(0, tk.END)
                entry.config(fg="black")

        def on_focus_out(event):
            if entry.get() == "":
                entry.insert(0, text)
                entry.config(fg="gray")

        entry.bind("<FocusIn>", on_focus_in)
        entry.bind("<FocusOut>", on_focus_out)

    def _on_mousewheel(self, event):
        # Обычная прокрутка — вертикальная
        self.canvas.yview_scroll(int(-event.delta / 120), "units")

    def _on_shift_mousewheel(self, event):
        # Shift + колёсико — горизонтальная
        self.canvas.xview_scroll(int(-event.delta / 120), "units")


    # ---------- Работа с деталями ----------

    def add_part(self):
        try:
            # Название — если placeholder остался, значит пользователь не ввёл
            name_raw = self.e_name.get().strip()
            if not name_raw or name_raw == "Название":
                name = f"Деталь{len(self.parts)+1}"
            else:
                name = name_raw

            # Ширина и высота — тоже с проверкой placeholder
            w_raw = self.e_w.get().strip()
            h_raw = self.e_h.get().strip()
            if not w_raw or w_raw == "Ширина":
                raise ValueError
            if not h_raw or h_raw == "Высота":
                raise ValueError

            w = int(w_raw)
            h = int(h_raw)
            qty = int(self.e_qty.get())
            if w <= 0 or h <= 0 or qty <= 0:
                raise ValueError
        except ValueError:
            messagebox.showerror("Ошибка", "Проверь размеры и количество")
            return

        self.parts.append(Part(name, w, h, qty))
        self.refresh_tree()

        # Очистка полей
        self.e_name.delete(0, tk.END)
        self.e_w.delete(0, tk.END)
        self.e_h.delete(0, tk.END)
        self.e_qty.delete(0, tk.END)
        self.e_qty.insert(0, "1")

        # Возврат placeholder в пустые поля
        self._add_placeholder(self.e_name, "Название")
        self._add_placeholder(self.e_w, "Ширина")
        self._add_placeholder(self.e_h, "Высота")

        self.e_name.focus_set()

    def del_part(self):
        sel = self.tree.selection()
        if not sel:
            return
        idx = self.tree.index(sel[0])
        del self.parts[idx]
        self.refresh_tree()

    def clear_parts(self):
        self.parts.clear()
        self.refresh_tree()

    def refresh_tree(self):
        self.tree.delete(*self.tree.get_children())
        for p in self.parts:
            self.tree.insert("", tk.END, values=(p.name, p.w, p.h, p.qty))

    # ---------- Импорт ----------

    def import_excel(self):
        if not HAS_OPENPYXL:
            messagebox.showerror(
                "Нет библиотеки",
                "Не установлена библиотека openpyxl.\n\n"
                "Открой cmd и выполни:\n"
                "pip install openpyxl"
            )
            return
        path = filedialog.askopenfilename(
            title="Выбери файл Excel",
            filetypes=[("Excel", "*.xlsx *.xlsm"), ("Все файлы", "*.*")]
        )
        if not path:
            return

        # Сначала пробуем прочитать как КАРТУ РАСКРОЯ
        # (если в файле есть колонки X и Y)
        try:
            sheets, map_errors = parse_excel_map(path)
            self._apply_map_import(sheets, map_errors)
            return
        except ValueError as e:
            # Не карта — не страшно, пойдём в обычный импорт
            print(f"[DEBUG] parse_excel_map вернул ValueError: {e}")
        except Exception as e:
            # А вот это — реальная ошибка, её надо увидеть
            import traceback
            print("[DEBUG] parse_excel_map упал:")
            traceback.print_exc()
            messagebox.showerror("Ошибка чтения",
                                 f"Не удалось прочитать:\n{e}")
            return

        # Импорт как список деталей
        try:
            parts, errors = parse_excel(path)
        except Exception as e:
            messagebox.showerror("Ошибка чтения",
                                 f"Не удалось прочитать:\n{e}")
            return
        self._apply_import(parts, errors)

    def _apply_map_import(self, sheets, errors):
        """Применяет загруженную карту раскроя."""
        # Проверим — точно ли есть размещённые детали
        total = sum(len(s.placed) for s in sheets)
        if total == 0:
            messagebox.showwarning("Пусто", "В файле нет размещённых деталей")
            return

        # Подставим реальные размеры листа из полей окна
        sheet_w = self.sheet_w.get()
        sheet_h = self.sheet_h.get()
        for sheet in sheets:
            sheet.w = sheet_w
            sheet.h = sheet_h

        answer = messagebox.askyesno(
            "Загружена карта раскроя",
            f"В файле найдено размещённых деталей: {total}\n"
            f"Листов: {len(sheets)}\n\n"
            f"Загрузить как готовую карту?\n"
            f"(Размер листа возьмётся из полей: {sheet_w}×{sheet_h})"
        )
        if not answer:
            return

        self.sheets = sheets
        self.draw()

        total_parts = sum(len(s.placed) for s in self.sheets)
        avg_fill = sum(s.fill_percent for s in self.sheets) / len(self.sheets)
        self.status.config(
            text=f"Загружена карта | Листов: {len(self.sheets)} | "
                 f"Деталей: {total_parts} | "
                 f"Заполнение: {avg_fill:.1f}%"
        )

        msg = f"Загружена карта раскроя:\n" \
              f"  Листов: {len(sheets)}\n" \
              f"  Деталей: {total}"
        if errors:
            msg += f"\n\nПропущено строк: {len(errors)}"
            msg += "\n" + "\n".join(errors[:5])
        messagebox.showinfo("Импорт завершён", msg)

    def import_csv(self):
        path = filedialog.askopenfilename(
            title="Выбери CSV-файл",
            filetypes=[("CSV", "*.csv"), ("Текст", "*.txt"), ("Все файлы", "*.*")]
        )
        if not path:
            return
        try:
            parts, errors = parse_csv(path)
        except Exception as e:
            messagebox.showerror("Ошибка чтения", f"Не удалось прочитать:\n{e}")
            return
        self._apply_import(parts, errors)

    def _apply_import(self, parts, errors):
        if not parts:
            msg = "В файле не найдено ни одной детали с размерами."
            if errors:
                msg += "\n\nОшибки:\n" + "\n".join(errors[:10])
            messagebox.showwarning("Пусто", msg)
            return
        if self.parts:
            answer = messagebox.askyesnocancel(
                "Детали уже есть",
                f"В программе уже {len(self.parts)} позиций.\n\n"
                "Да — заменить\nНет — добавить\nОтмена — ничего"
            )
            if answer is None:
                return
            if answer:
                self.parts.clear()
        self.parts.extend(parts)
        self.refresh_tree()
        msg = f"Загружено позиций: {len(parts)}\n" \
              f"Всего деталей: {sum(p.qty for p in parts)}"
        if errors:
            msg += f"\n\nПропущено строк: {len(errors)}"
            msg += "\n" + "\n".join(errors[:5])
        messagebox.showinfo("Импорт завершён", msg)

    def save_template(self):
        if not HAS_OPENPYXL:
            messagebox.showerror(
                "Нет библиотеки",
                "Не установлена библиотека openpyxl.\n\n"
                "Открой cmd и выполни:\n"
                "pip install openpyxl"
            )
            return
        path = filedialog.asksaveasfilename(
            title="Сохранить шаблон",
            defaultextension=".xlsx",
            initialfile="шаблон_деталей.xlsx",
            filetypes=[("Excel", "*.xlsx")]
        )
        if not path:
            return
        try:
            create_excel_template(path)
            messagebox.showinfo("Готово", f"Шаблон сохранён:\n{path}")
        except Exception as e:
            messagebox.showerror("Ошибка", str(e))

    def save_csv_template(self):
        path = filedialog.asksaveasfilename(
            title="Сохранить шаблон CSV",
            defaultextension=".csv",
            initialfile="шаблон_деталей.csv",
            filetypes=[("CSV", "*.csv")]
        )
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8-sig", newline="") as f:
                writer = csv.writer(f, delimiter=";")
                writer.writerow(["Название", "Ширина", "Высота", "Кол-во"])
                writer.writerow(["Боковина", 550, 720, 2])
                writer.writerow(["Полка", 500, 550, 4])
                writer.writerow(["Фасад", 596, 716, 2])
                writer.writerow(["Дно", 500, 550, 1])
            messagebox.showinfo("Готово", f"Шаблон сохранён:\n{path}")
        except Exception as e:
            messagebox.showerror("Ошибка", str(e))

    # ---------- Расчёт ----------

    def calc(self):
        if not self.parts:
            messagebox.showinfo("Инфо", "Добавь хотя бы одну деталь")
            return
        self.status.config(text="Расчёт...")
        self.update_idletasks()
        try:
            self.sheets = pack_parts(
                self.parts,
                self.sheet_w.get(),
                self.sheet_h.get(),
                self.kerf.get(),
                allow_rotation=self.allow_rotation.get(),
                multi_start=self.multi_start.get(),
            )
        except Exception as e:
            messagebox.showerror("Ошибка расчёта", str(e))
            self.status.config(text="Ошибка")
            return
        if not self.sheets:
            messagebox.showerror("Ошибка", "Не удалось разложить детали")
            self.status.config(text="Ошибка")
            return
        # self.draw()
        total_parts = sum(len(s.placed) for s in self.sheets)
        avg_fill = sum(s.fill_percent for s in self.sheets) / len(self.sheets)
        self.status.config(
            text=f"Листов: {len(self.sheets)} | "
                 f"Деталей размещено: {total_parts} | "
                 f"Среднее заполнение: {avg_fill:.1f}%"
        )

        self.draw()

    # ---------- Визуализация ----------

    def draw(self):
        self.canvas.delete("all")
        if not self.sheets:
            return

        # Заливаем Canvas белым — убирает серые полосы вокруг листов
        cw_view = self.canvas.winfo_width() or 1000
        ch_view = self.canvas.winfo_height() or 800
        self.canvas.create_rectangle(0, 0, cw_view, ch_view,
                                     fill="white", outline="")

        pad = 20
        cw = self.canvas.winfo_width() or 1000
        cell_w = self.sheet_w.get() / 10
        cell_h = self.sheet_h.get() / 10
        cols = max(1, int((cw - pad) // (cell_w + pad)))



        max_x = 0
        max_y = 0

        for i, sheet in enumerate(self.sheets):
            row = i // cols
            col = i % cols
            ox = pad + col * (cell_w + pad)
            oy = pad + row * (cell_h + pad + 40)

            max_x = max(max_x, ox + cell_w + pad)
            max_y = max(max_y, oy + cell_h + pad)

            self.canvas.create_rectangle(ox, oy, ox + cell_w, oy + cell_h,
                                         outline="black", width=2)
            self.canvas.create_text(
                ox + 5, oy - 8,
                text=f"Лист {i+1}  ({sheet.fill_percent:.1f}%)",
                anchor=tk.W, font=("Arial", 9, "bold")
            )

            for j, part in enumerate(sheet.placed):
                px = ox + part.x / 10
                py = oy + part.y / 10
                pw = part.w / 10
                ph = part.h / 10
                color = COLORS[j % len(COLORS)]
                self.canvas.create_rectangle(px, py, px + pw, py + ph,
                                             fill=color, outline="black")
                if pw > 25 and ph > 15:
                    label = f"{part.name}\n{part.w}×{part.h}"
                    self.canvas.create_text(px + pw / 2, py + ph / 2,
                                            text=label, font=("Arial", 7),
                                            justify=tk.CENTER)

        self.canvas.config(scrollregion=(0, 0, max_x, max_y))

###
    def open_viewer(self, start_index=0):
        if not self.sheets:
            messagebox.showinfo("Инфо", "Сначала рассчитай раскрой")
            return
        SheetViewer(self, self.sheets,
                    self.sheet_w.get(), self.sheet_h.get(),
                    start_index=start_index)
    def open_manual_editor(self):
        """Открыть окно ручного раскроя."""
        if not self.parts:
            messagebox.showinfo("Инфо", "Сначала добавь детали "
                                        "(вручную или импортом)")
            return

        ManualSheetEditor(
            self,
            self.parts,
            self.sheet_w.get(),
            self.sheet_h.get(),
            self.kerf.get(),
            callback_on_apply=self._apply_manual_layout,
        )

    def _apply_manual_layout(self, sheets):
        """Применить раскрой из ручного редактора."""
        self.sheets = sheets
        self.draw()
        if self.sheets:
            avg_fill = sum(s.fill_percent for s in self.sheets) / len(self.sheets)
            self.status.config(
                text=f"Ручной раскрой | Листов: {len(self.sheets)} | "
                     f"Заполнение: {avg_fill:.1f}%"
            )
        messagebox.showinfo(
            "Готово",
            "Ручной раскрой применён.\n"
            "Теперь доступны: просмотр, отчёт, экспорт, печать."
        )

    def print_all_sheets(self):
        """Создаёт HTML-файл с картами всех листов и открывает его в браузере.
        Каждый лист — на отдельной печатной странице."""
        if not self.sheets:
            messagebox.showinfo("Инфо", "Сначала рассчитай раскрой")
            return

        path = filedialog.asksaveasfilename(
            title="Сохранить для печати",
            defaultextension=".html",
            initialfile="карта_раскроя.html",
            filetypes=[("HTML", "*.html")]
        )
        if not path:
            return

        try:
            html = build_print_html(
                self.sheets,
                self.sheet_w.get(),
                self.sheet_h.get(),
                self.kerf.get(),
                COLORS,
            )
            with open(path, "w", encoding="utf-8") as f:
                f.write(html)
        except Exception as e:
            messagebox.showerror("Ошибка", str(e))
            return

        # Открываем в браузере по умолчанию
        import webbrowser
        webbrowser.open("file:///" + path.replace("\\", "/"))

        messagebox.showinfo(
            "Готово",
            "Файл открыт в браузере.\n\n"
            "Нажми Ctrl+P и выбери печать.\n"
            "Каждый лист будет на отдельной странице."
        )


###



    # ---------- Отчёты ----------

    def save_report(self):
        if not self.sheets:
            messagebox.showinfo("Инфо", "Сначала рассчитай раскрой")
            return
        path = filedialog.asksaveasfilename(
            defaultextension=".txt",
            filetypes=[("Text", "*.txt")],
        )
        if not path:
            return
        try:
            export_to_txt(
                path,
                self.sheets,
                self.sheet_w.get(),
                self.sheet_h.get(),
                self.kerf.get(),
            )
            messagebox.showinfo("Ок", f"Отчёт сохранён:\n{path}")
        except Exception as e:
            messagebox.showerror("Ошибка", str(e))

    def export_excel_map(self):
        if not HAS_OPENPYXL:
            messagebox.showerror(
                "Нет библиотеки",
                "Не установлена библиотека openpyxl.\n\n"
                "Открой cmd и выполни:\n"
                "pip install openpyxl"
            )
            return
        if not self.sheets:
            messagebox.showinfo("Инфо", "Сначала рассчитай раскрой")
            return
        path = filedialog.asksaveasfilename(
            title="Сохранить карту раскроя",
            defaultextension=".xlsx",
            initialfile="карта_раскроя.xlsx",
            filetypes=[("Excel", "*.xlsx")]
        )
        if not path:
            return
        try:
            export_to_excel(
                path,
                self.sheets,
                self.sheet_w.get(),
                self.sheet_h.get(),
                self.kerf.get(),
            )
            messagebox.showinfo("Готово", f"Карта раскроя сохранена:\n{path}")
        except Exception as e:
            messagebox.showerror("Ошибка", str(e))

###
