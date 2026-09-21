import tkinter as tk
from tkinter import ttk, messagebox
from typing import List, Optional
from models import Part, Sheet, PlacedPart, FreeRect, ManualPart
from packing import pack_parts

###
# ============================================================
#  РУЧНОЙ РЕДАКТОР РАСКРОЯ
# ============================================================




class ManualSheetEditor(tk.Toplevel):
    """Окно ручного раскроя.
    Слева — список неразмещённых деталей. Справа — лист.
    Перетаскивай детали мышкой. Снап к краям и другим деталям."""

    SNAP_PX = 8         # радиус прилипания на экране (в пикселях)
    GRID = 1            # сетка (мм), 1 = без сетки

    def __init__(self, master, parts_list, sheet_w, sheet_h, kerf,
                 callback_on_apply=None):
        super().__init__(master)
        self.title("Ручной раскрой — перетаскивай детали на лист")
        self.geometry("1400x900")

        self.show_free_areas = tk.BooleanVar(value=True)

        self.sheet_w = sheet_w
        self.sheet_h = sheet_h
        self.kerf = kerf
        self.callback_on_apply = callback_on_apply

        # Все детали — плоский список (ManualPart с уникальными id)
        self.all_parts: List[ManualPart] = []
        pid = 0
        for p in parts_list:
            for k in range(p.qty):
                self.all_parts.append(
                    ManualPart(id=pid, name=p.name, w=p.w, h=p.h)
                )
                pid += 1

        # Листы: список списков ManualPart (по одной на каждый лист)
        # Первый лист уже создан пустым.
        self.sheets_parts: List[List[ManualPart]] = [[]]

        # Индекс активного листа
        self.current_sheet_index = 0

        # Состояние перетаскивания
        self.drag_part_id: Optional[int] = None
        self.drag_offset_x = 0
        self.drag_offset_y = 0
        self.drag_from_list = False
        self.selected_part_id: Optional[int] = None

        # Сортировка
        self.sort_mode = tk.StringVar(value="По порядку")
        self._sorted_unplaced: List[ManualPart] = []

        # Масштаб: px на мм (пересчитывается при resize)
        self.scale = 0.25
        # Отступы от края Canvas до листа
        self.origin_x = 40
        self.origin_y = 40

        self._build_ui()
        self._refresh_list()
        self._redraw()

    # ---------- Интерфейс ----------

    def _build_ui(self):
        # Верхняя панель с кнопками
        top = ttk.Frame(self, padding=6)
        top.pack(side=tk.TOP, fill=tk.X)

        ttk.Button(top, text="⟳ Рассчитать автоматически",
                   command=self.auto_layout).pack(side=tk.LEFT, padx=2)
        ttk.Button(top, text="🗑 Очистить лист",
                   command=self.clear_sheet).pack(side=tk.LEFT, padx=2)
        ttk.Button(top, text="↺ Вернуть все детали",
                   command=self.reset_all).pack(side=tk.LEFT, padx=2)

        ttk.Checkbutton(top, text="Показывать свободные зоны",
                        variable=self.show_free_areas,
                        command=self._redraw
                        ).pack(side=tk.LEFT, padx=8)

        ttk.Separator(top, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y,
                                                     padx=8)

        # --- Навигация по листам ---
        self.btn_prev = ttk.Button(top, text="◀", command=self.prev_sheet)
        self.btn_prev.pack(side=tk.LEFT, padx=2)

        self.lbl_sheet = ttk.Label(top, text="Лист 1 из 1",
                                   font=("Arial", 10, "bold"))
        self.lbl_sheet.pack(side=tk.LEFT, padx=6)

        self.btn_next = ttk.Button(top, text="▶", command=self.next_sheet)
        self.btn_next.pack(side=tk.LEFT, padx=2)

        ttk.Button(top, text="+ Добавить лист",
                   command=self.add_sheet).pack(side=tk.LEFT, padx=6)
        ttk.Button(top, text="✕ Удалить лист",
                   command=self.delete_sheet).pack(side=tk.LEFT, padx=2)

        ttk.Separator(top, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y,
                                                     padx=8)

        self.lbl_status = ttk.Label(top, text="", font=("Arial", 10))
        self.lbl_status.pack(side=tk.LEFT, padx=8)

        ttk.Button(top, text="✓ Применить раскрой",
                   command=self.apply_layout).pack(side=tk.RIGHT, padx=2)
        ttk.Button(top, text="Отмена",
                   command=self.destroy).pack(side=tk.RIGHT, padx=2)

        # Основная область — слева список, справа canvas
        main = ttk.Frame(self)
        main.pack(side=tk.TOP, fill=tk.BOTH, expand=True)

        # Левая панель со списком
        left = ttk.Frame(main, padding=6, width=280)
        left.pack(side=tk.LEFT, fill=tk.Y)
        left.pack_propagate(False)

        ttk.Label(left, text="Не размещённые детали",
                  font=("Arial", 10, "bold")).pack(anchor=tk.W)
        ttk.Label(left, text="Перетащи на лист →",
                  font=("Arial", 8), foreground="#666").pack(anchor=tk.W)
###
        # Выпадающий список сортировки
        sort_row = ttk.Frame(left)
        sort_row.pack(fill=tk.X, pady=(4, 0))
        ttk.Label(sort_row, text="Сортировка:",
                  font=("Arial", 8)).pack(side=tk.LEFT)
        sort_values = [
            "По порядку",
            "Площадь ↑",
            "Площадь ↓",
            "Длинная сторона ↑",
            "Длинная сторона ↓",
            "Короткая сторона ↑",
            "Короткая сторона ↓",
            "Название A→Я",
            "Название Я→А",
        ]
        self.sort_combo = ttk.Combobox(
            sort_row, textvariable=self.sort_mode,
            values=sort_values, state="readonly", width=18,
            font=("Arial", 8)
        )
        self.sort_combo.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=2)
        self.sort_combo.bind("<<ComboboxSelected>>",
                             lambda e: self._refresh_list())
###

        list_frame = ttk.Frame(left)
        list_frame.pack(fill=tk.BOTH, expand=True, pady=4)

        # Вертикальный скроллбар
        v_scroll = ttk.Scrollbar(list_frame, orient=tk.VERTICAL)
        v_scroll.pack(side=tk.RIGHT, fill=tk.Y)

        # Горизонтальный скроллбар
        h_scroll = ttk.Scrollbar(list_frame, orient=tk.HORIZONTAL)
        h_scroll.pack(side=tk.BOTTOM, fill=tk.X)

        self.listbox = tk.Listbox(list_frame,
                                  yscrollcommand=v_scroll.set,
                                  xscrollcommand=h_scroll.set,
                                  font=("Consolas", 9),
                                  selectmode=tk.SINGLE,
                                  activestyle="none",
                                  width=30)
        self.listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        v_scroll.config(command=self.listbox.yview)
        h_scroll.config(command=self.listbox.xview)

        # Привязки для перетаскивания из списка
        self.listbox.bind("<ButtonPress-1>", self._on_list_press)
        self.listbox.bind("<B1-Motion>", self._on_list_drag)
        self.listbox.bind("<ButtonRelease-1>", self._on_list_release)

###
        # Shift + колёсико = горизонтальная прокрутка
        self.listbox.bind("<Shift-MouseWheel>",
                          lambda e: self.listbox.xview_scroll(
                              -1 if e.delta > 0 else 1, "units"))
        # Alt + колёсико = тоже горизонтальная (некоторые мыши)
        self.listbox.bind("<Alt-MouseWheel>",
                          lambda e: self.listbox.xview_scroll(
                              -1 if e.delta > 0 else 1, "units"))
###

        # Кнопки внизу списка
        btn_box = ttk.Frame(left)
        btn_box.pack(fill=tk.X, pady=4)
        ttk.Button(btn_box, text="Разместить на лист",
                   command=self._place_selected_from_list
                   ).pack(fill=tk.X, pady=1)
        ttk.Button(btn_box, text="⟳ Повернуть выделенную",
                   command=self._rotate_selected
                   ).pack(fill=tk.X, pady=1)

        ttk.Label(left, text="Подсказки:",
                  font=("Arial", 9, "bold")).pack(anchor=tk.W, pady=(8, 2))
        tips = (
            "• Тяни деталь мышкой из списка на лист\n"
            "• Внутри листа — перетаскивай\n"
            "• Двойной клик — повернуть на 90°\n"
            "• Правый клик — удалить с листа\n"
            "• Delete — удалить выделенную\n"
            "• R — повернуть выделенную\n"
            "• Детали прилипают к краям и друг к другу"
        )
        ttk.Label(left, text=tips, font=("Arial", 8),
                  foreground="#444", justify=tk.LEFT).pack(anchor=tk.W)

        # Правая панель — Canvas
        right = ttk.Frame(main)
        right.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)

        canvas_frame = ttk.Frame(right)
        canvas_frame.pack(fill=tk.BOTH, expand=True)

        h_scroll = ttk.Scrollbar(canvas_frame, orient=tk.HORIZONTAL)
        h_scroll.pack(side=tk.BOTTOM, fill=tk.X)
        v_canvas = ttk.Scrollbar(canvas_frame, orient=tk.VERTICAL)
        v_canvas.pack(side=tk.RIGHT, fill=tk.Y)

        self.canvas = tk.Canvas(canvas_frame, bg="#f0f0f0",
                                xscrollcommand=h_scroll.set,
                                yscrollcommand=v_canvas.set)
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        h_scroll.config(command=self.canvas.xview)
        v_canvas.config(command=self.canvas.yview)

        # Привязки для canvas
        self.canvas.bind("<ButtonPress-1>", self._on_canvas_press)
        self.canvas.bind("<B1-Motion>", self._on_canvas_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_canvas_release)
        self.canvas.bind("<Double-Button-1>", self._on_canvas_double_click)
        self.canvas.bind("<ButtonPress-3>", self._on_canvas_right_click)
        self.canvas.bind("<Configure>", lambda e: self._on_canvas_resize())

        # Горячие клавиши
        self.bind("<Delete>", lambda e: self._delete_selected())
        self.bind("<r>", lambda e: self._rotate_selected())
        self.bind("<R>", lambda e: self._rotate_selected())
        self.bind("<Escape>", lambda e: self._deselect())

        self.bind("<Prior>", lambda e: self.prev_sheet())   # PageUp
        self.bind("<Next>", lambda e: self.next_sheet())    # PageDown
        self.bind("<Control-n>", lambda e: self.add_sheet())  # Ctrl+N

###

###

    # ---------- Вспомогательные ----------

    def _to_canvas(self, mm_x, mm_y):
        """мм → пиксели canvas (с учётом прокрутки — не нужно, координаты относительны листа)."""
        return (self.origin_x + mm_x * self.scale,
                self.origin_y + mm_y * self.scale)

    def _to_mm(self, px, py):
        """пиксели canvas → мм листа."""
        return ((px - self.origin_x) / self.scale,
                (py - self.origin_y) / self.scale)

    def _find_part_at(self, mm_x, mm_y):
        """Деталь под точкой (в мм) на активном листе, или None."""
        # Ищем сверху вниз — последняя добавленная поверх
        for part in reversed(self.current_parts()):
            if (part.x <= mm_x <= part.x + part.w and
                    part.y <= mm_y <= part.y + part.h):
                return part
        return None


    def _update_status(self):
        placed = self.placed_parts()
        unplaced = self.unplaced_parts()
        used = sum(p.w * p.h for p in placed)
        total = self.sheet_w * self.sheet_h * len(self.sheets_parts)
        pct = used / total * 100 if total else 0
        self.lbl_status.config(
            text=f"Размещено: {len(placed)} | "
                 f"Осталось: {len(unplaced)} | "
                 f"Заполнение: {pct:.1f}%"
        )
        self._update_sheet_label()

    # ---------- Работа с листами ----------

    def current_parts(self):
        """Список ManualPart на активном листе."""
        return self.sheets_parts[self.current_sheet_index]

    def placed_parts(self):
        """Все размещённые детали на всех листах."""
        result = []
        for lst in self.sheets_parts:
            result.extend(lst)
        return result

    def unplaced_parts(self):
        """Детали, которых нет ни на одном листе."""
        placed_ids = {p.id for p in self.placed_parts()}
        return [p for p in self.all_parts if p.id not in placed_ids]

    def prev_sheet(self):
        if self.current_sheet_index > 0:
            self.current_sheet_index -= 1
            self.selected_part_id = None
            self._refresh_list()
            self._redraw()
            self._update_sheet_label()
            self._update_status()

    def next_sheet(self):
        if self.current_sheet_index < len(self.sheets_parts) - 1:
            self.current_sheet_index += 1
            self.selected_part_id = None
            self._refresh_list()
            self._redraw()
            self._update_sheet_label()
            self._update_status()
        # Если это последний лист — ничего не делаем

    def add_sheet(self):
        self.sheets_parts.append([])
        self.current_sheet_index = len(self.sheets_parts) - 1
        self.selected_part_id = None
        self._refresh_list()
        self._redraw()
        self._update_sheet_label()
        self._update_status()

    def delete_sheet(self):
        if len(self.sheets_parts) <= 1:
            messagebox.showinfo("Нельзя",
                                "Нельзя удалить последний лист")
            return

        idx = self.current_sheet_index
        cnt = len(self.sheets_parts[idx])
        if cnt > 0:
            if not messagebox.askyesno(
                "Удалить лист?",
                f"На листе {idx + 1} размещено {cnt} деталей.\n"
                "Они вернутся в список неразмещённых.\n"
                "Удалить лист?"
            ):
                return

        # Убираем лист из списка
        del self.sheets_parts[idx]

        # Корректируем активный индекс
        if self.current_sheet_index >= len(self.sheets_parts):
            self.current_sheet_index = len(self.sheets_parts) - 1

        self.selected_part_id = None
        self._refresh_list()
        self._redraw()
        self._update_sheet_label()
        self._update_status()

    def _update_sheet_label(self):
        self.lbl_sheet.config(
            text=f"Лист {self.current_sheet_index + 1} "
                 f"из {len(self.sheets_parts)}"
        )
        # Отключаем кнопки на краях, если дальше некуда
        if hasattr(self, "btn_prev") and hasattr(self, "btn_next"):
            if self.current_sheet_index <= 0:
                self.btn_prev.state(["disabled"])
            else:
                self.btn_prev.state(["!disabled"])
            if self.current_sheet_index >= len(self.sheets_parts) - 1:
                self.btn_next.state(["disabled"])
            else:
                self.btn_next.state(["!disabled"])

    def _placed_parts(self):
        """Совместимость со старым кодом — детали на активном листе."""
        return self.current_parts()

    def _unplaced_parts(self):
        """Совместимость со старым кодом — детали вне листов."""
        return self.unplaced_parts()


    # ---------- Перетаскивание из списка ----------

    def _on_list_press(self, event):
        idx = self.listbox.nearest(event.y)
        if idx < 0 or idx >= self.listbox.size():
            return
        self.listbox.selection_clear(0, tk.END)
        self.listbox.selection_set(idx)
        self.listbox.activate(idx)

        unplaced = getattr(self, "_sorted_unplaced", self.unplaced_parts())
        if idx >= len(unplaced):
            return
        part = unplaced[idx]

        self.drag_part_id = part.id
        self.drag_from_list = True
        self.drag_offset_x = 0
        self.drag_offset_y = 0

    def _on_list_drag(self, event):
        """Перетаскивание из списка — рисуем "призрак" детали на canvas."""
        if self.drag_part_id is None or not self.drag_from_list:
            return

        # Показываем призрак над canvas — конвертируем координаты
        # события из listbox в координаты canvas
        canvas_x = event.x_root - self.canvas.winfo_rootx()
        canvas_y = event.y_root - self.canvas.winfo_rooty()

        # Если курсор над canvas — рисуем призрак
        if 0 <= canvas_x <= self.canvas.winfo_width() and \
           0 <= canvas_y <= self.canvas.winfo_height():
            self._redraw()
            self._draw_ghost(canvas_x, canvas_y)

    def _on_list_release(self, event):
        if self.drag_part_id is None or not self.drag_from_list:
            self._redraw()
            return

        part = next((p for p in self.all_parts if p.id == self.drag_part_id),
                    None)
        self.drag_part_id = None
        self.drag_from_list = False

        if part is None:
            self._redraw()
            return

        canvas_x = event.x_root - self.canvas.winfo_rootx()
        canvas_y = event.y_root - self.canvas.winfo_rooty()

        if not (0 <= canvas_x <= self.canvas.winfo_width() and
                0 <= canvas_y <= self.canvas.winfo_height()):
            self._redraw()
            return

        real_x = self.canvas.canvasx(canvas_x)
        real_y = self.canvas.canvasy(canvas_y)
        mm_x, mm_y = self._to_mm(real_x, real_y)

        px = mm_x - part.w / 2
        py = mm_y - part.h / 2

        px, py = self._snap_to_edges(part, px, py)
        px, py = self._snap_to_parts(part, px, py)

        # Проверяем только границы листа — коллизии разрешаем
        # (деталь встанет красной, если пересекается)
        px = max(-part.w + 5, min(px, self.sheet_w - 5))
        py = max(-part.h + 5, min(py, self.sheet_h - 5))

        part.x = int(round(px))
        part.y = int(round(py))

        # Добавляем в текущий лист
        current = self.current_parts()
        if not any(p.id == part.id for p in current):
            current.append(part)

        self.selected_part_id = part.id
        self._refresh_list()
        self._redraw()
        self._update_status()

    def _place_selected_from_list(self):
        """Кнопка — разместить выделенную деталь в свободное место."""
        sel = self.listbox.curselection()
        if not sel:
            return
        unplaced = getattr(self, "_sorted_unplaced", self.unplaced_parts())
        idx = sel[0]
        if idx >= len(unplaced):
            return
        part = unplaced[idx]
        pos = self._find_free_spot(part)
        if pos is None:
            messagebox.showwarning("Не помещается",
                                   "Не удалось найти место для детали")
            return
        part.x, part.y = pos

        # Добавляем в текущий лист
        current = self.current_parts()
        if not any(p.id == part.id for p in current):
            current.append(part)

        self.selected_part_id = part.id
        self._refresh_list()
        self._redraw()
        self._update_status()

    # ---------- Перетаскивание внутри canvas ----------

    def _on_canvas_press(self, event):
        cx = self.canvas.canvasx(event.x)
        cy = self.canvas.canvasy(event.y)
        mm_x, mm_y = self._to_mm(cx, cy)

        part = self._find_part_at(mm_x, mm_y)
        if part is None:
            self._deselect()
            self._redraw()
            return

        self.selected_part_id = part.id
        self.drag_part_id = part.id
        self.drag_from_list = False
        self.drag_offset_x = mm_x - part.x
        self.drag_offset_y = mm_y - part.y
        self._redraw()

    def _on_canvas_drag(self, event):
        """Перетаскивание детали внутри листа."""
        if self.drag_part_id is None or self.drag_from_list:
            return

        part = next((p for p in self.all_parts if p.id == self.drag_part_id),
                    None)
        if part is None:
            return

        cx = self.canvas.canvasx(event.x)
        cy = self.canvas.canvasy(event.y)
        mm_x, mm_y = self._to_mm(cx, cy)

        new_x = mm_x - self.drag_offset_x
        new_y = mm_y - self.drag_offset_y

        # Снап к краям
        new_x, new_y = self._snap_to_edges(part, new_x, new_y)
        # Снап к другим деталям
        new_x, new_y = self._snap_to_parts(part, new_x, new_y)

        # Обновляем позицию (даже если невалидна — деталь будет красной)
        part.x = int(round(new_x))
        part.y = int(round(new_y))

        self._redraw()



    def _on_canvas_release(self, event):
        """Отпустили мышку — деталь остаётся там, где её отпустили.
        Если позиция невалидна — она подсветится красным, и её можно
        будет перетащить в другое место."""
        if self.drag_part_id is None:
            return

        part = next((p for p in self.all_parts if p.id == self.drag_part_id),
                    None)
        self.drag_part_id = None
        if part is None:
            self._redraw()
            return

        # Если деталь не помещается — просто оставляем, но зафиксируем
        # в границах canvas (чтобы не улетела далеко за пределы)
        # Не ограничиваем жёстко листом — пользователь сам найдёт место.
        self._redraw()
        self._update_status()

    # ---------- Снап и коллизии ----------

    def _snap_to_edges(self, part, x, y):
        """Прилипание к краям листа."""
        snap_mm = self.SNAP_PX / self.scale  # порог в мм

        # Левый край
        if abs(x) < snap_mm:
            x = 0
        # Правый край
        if abs((x + part.w) - self.sheet_w) < snap_mm:
            x = self.sheet_w - part.w
        # Верхний
        if abs(y) < snap_mm:
            y = 0
        # Нижний
        if abs((y + part.h) - self.sheet_h) < snap_mm:
            y = self.sheet_h - part.h

        return x, y

    def _snap_to_parts(self, part, x, y):
        """Прилипание к другим деталям с учётом толщины пила.
        Между деталями всегда остаётся зазор kerf мм."""
        snap_mm = self.SNAP_PX / self.scale
        kerf = self.kerf

        my_left, my_right = x, x + part.w
        my_top, my_bottom = y, y + part.h

        best_dx = None  # (расстояние, целевое x)
        best_dy = None  # (расстояние, целевое y)

        for other in self.current_parts():
            if other.id == part.id:
                continue
            o_left, o_right = other.x, other.x + other.w
            o_top, o_bottom = other.y, other.y + other.h

            # Пересекаются ли по вертикали (для горизонтального снапа)?
            overlap_v = not (my_bottom <= o_top or my_top >= o_bottom)
            # Пересекаются ли по горизонтали (для вертикального снапа)?
            overlap_h = not (my_right <= o_left or my_left >= o_right)

            # --- Горизонтальный снап ---
            if overlap_v:
                # Моя деталь СЛЕВА от чужой: правый край + kerf = левый чужой
                target_x = o_left - kerf - part.w
                d = abs(my_left - target_x)
                if d < snap_mm and (best_dx is None or d < best_dx[0]):
                    best_dx = (d, target_x)

                # Моя деталь СПРАВА от чужой: левый край = правый чужой + kerf
                target_x = o_right + kerf
                d = abs(my_left - target_x)
                if d < snap_mm and (best_dx is None or d < best_dx[0]):
                    best_dx = (d, target_x)

            # --- Вертикальный снап ---
            if overlap_h:
                # Моя деталь СВЕРХУ от чужой: нижний + kerf = верхний чужой
                target_y = o_top - kerf - part.h
                d = abs(my_top - target_y)
                if d < snap_mm and (best_dy is None or d < best_dy[0]):
                    best_dy = (d, target_y)

                # Моя деталь СНИЗУ от чужой: верхний = нижний чужой + kerf
                target_y = o_bottom + kerf
                d = abs(my_top - target_y)
                if d < snap_mm and (best_dy is None or d < best_dy[0]):
                    best_dy = (d, target_y)

        if best_dx is not None:
            x = best_dx[1]
        if best_dy is not None:
            y = best_dy[1]

        return x, y

    def _fits_on_sheet(self, part, x, y):
        """Проверка, что деталь целиком внутри листа."""
        return (x >= -0.5 and y >= -0.5 and
                x + part.w <= self.sheet_w + 0.5 and
                y + part.h <= self.sheet_h + 0.5)

    def _collides(self, part, x, y, ignore_id=None):
        """Проверка пересечения с другими размещёнными деталями
        с учётом толщины пила."""
        kerf = self.kerf
        # Границы с зазором на пила
        a_left = x - kerf
        a_right = x + part.w + kerf
        a_top = y - kerf
        a_bottom = y + part.h + kerf

        for other in self.current_parts():
            if other.id == part.id:
                continue
            if ignore_id is not None and other.id == ignore_id:
                continue

            b_left = other.x
            b_right = other.x + other.w
            b_top = other.y
            b_bottom = other.y + other.h

            # Пересечение?
            if not (a_right <= b_left or a_left >= b_right or
                    a_bottom <= b_top or a_top >= b_bottom):
                return True
        return False

    def _clamp_to_sheet(self, part):
        """Попытаться впихнуть деталь в лист, не двигая её относительно
        других деталей. Ищем ближайшую валидную позицию."""
        # Сначала — просто прижать к листу
        x = max(0, min(part.x, self.sheet_w - part.w))
        y = max(0, min(part.y, self.sheet_h - part.h))

        if not self._collides(part, x, y):
            return int(x), int(y)

        # Простой перебор: попробуем сдвигать на 10 мм
        for step in range(10, 500, 10):
            for dx, dy in [(step, 0), (-step, 0), (0, step), (0, -step)]:
                nx = max(0, min(part.x + dx, self.sheet_w - part.w))
                ny = max(0, min(part.y + dy, self.sheet_h - part.h))
                if not self._collides(part, nx, ny):
                    return int(nx), int(ny)
        return None

    def _find_free_spot(self, part):
        """Найти свободное место для детали (поиск сверху-вниз,
        слева-направо с шагом 10 мм)."""
        step = 10
        y = 0
        while y + part.h <= self.sheet_h:
            x = 0
            while x + part.w <= self.sheet_w:
                if not self._collides(part, x, y):
                    return (x, y)
                x += step
            y += step
        return None

    def _compute_free_rects(self):
        """Считает свободные прямоугольники на текущем листе
        через гильотинное разбиение. Возвращает список FreeRect."""
        free = [FreeRect(0, 0, self.sheet_w, self.sheet_h)]
        kerf = self.kerf

        # Проходим по всем размещённым деталям и делим пространство
        for part in self.current_parts():
            # Пропускаем невалидные (пересекающиеся) детали —
            # они не должны учитываться при разбиении
            if not (self._fits_on_sheet(part, part.x, part.y) and
                    not self._collides(part, part.x, part.y,
                                        ignore_id=part.id)):
                continue

            new_free = []
            px, py = part.x, part.y
            pw, ph = part.w, part.h
            rx = px + pw + kerf
            by = py + ph + kerf

            for rect in free:
                fx, fy, fw, fh = rect.x, rect.y, rect.w, rect.h

                # Не пересекается с деталью?
                if (rx <= fx or px >= fx + fw or
                        by <= fy or py >= fy + fh):
                    new_free.append(rect)
                    continue

                # Пересекается — делим на два прямоугольника
                # Справа от детали — на всю высоту
                if rx < fx + fw:
                    new_free.append(FreeRect(rx, fy, fx + fw - rx, fh))
                # Снизу от детали — на ширину детали + пила
                if by < fy + fh:
                    w2 = min(fw, pw + kerf)
                    new_free.append(FreeRect(fx, by, w2, fy + fh - by))

            free = new_free

        # Убираем нулевые и слишком мелкие (< 100×100 мм)
        MIN = 100
        free = [r for r in free if r.w >= MIN and r.h >= MIN]
        return free


    # ---------- Отрисовка ----------

    def _on_canvas_resize(self):
        """При изменении размера окна — пересчитать масштаб."""
        cw = self.canvas.winfo_width()
        ch = self.canvas.winfo_height()
        if cw < 50 or ch < 50:
            return

        # Отступы 40 px с каждой стороны
        avail_w = max(cw - 80, 100)
        avail_h = max(ch - 80, 100)

        scale_x = avail_w / self.sheet_w
        scale_y = avail_h / self.sheet_h
        new_scale = min(scale_x, scale_y)
        # Ограничим: не больше 1 px/мм (чтобы не разрасталось)
        new_scale = min(new_scale, 1.0)

        if abs(new_scale - self.scale) > 0.001:
            self.scale = new_scale
            self._redraw()

    def _redraw(self):
        self.canvas.delete("all")

        lx0, ly0 = self._to_canvas(0, 0)
        lx1, ly1 = self._to_canvas(self.sheet_w, self.sheet_h)

        self.canvas.create_rectangle(lx0, ly0, lx1, ly1,
                                     fill="#ffffff", outline="#000000",
                                     width=2)

        step = 100
        for gx in range(step, self.sheet_w, step):
            px, _ = self._to_canvas(gx, 0)
            self.canvas.create_line(px, ly0, px, ly1,
                                    fill="#eeeeee", width=1)
        for gy in range(step, self.sheet_h, step):
            _, py = self._to_canvas(0, gy)
            self.canvas.create_line(lx0, py, lx1, py,
                                    fill="#eeeeee", width=1)

        self.canvas.create_text((lx0 + lx1) / 2, ly0 - 14,
                                text=f"{self.sheet_w} мм",
                                font=("Arial", 9, "bold"))
        self.canvas.create_text(lx0 - 14, (ly0 + ly1) / 2,
                                text=f"{self.sheet_h} мм",
                                font=("Arial", 9, "bold"), angle=90)

        # Заголовок листа
        self.canvas.create_text(
            (lx0 + lx1) / 2, ly0 - 30,
            text=f"Лист {self.current_sheet_index + 1} "
                 f"из {len(self.sheets_parts)}",
            font=("Arial", 11, "bold")
        )

        colors = ["#FFB3BA", "#FFDFBA", "#FFFFBA", "#BAFFC9", "#BAE1FF",
                  "#E0BBE4", "#FEC8D8", "#D4F0F0", "#FFDAC1", "#B5EAD7",
                  "#F1C0E8", "#CFBAF0", "#A3C4F3", "#90DBF4", "#8EECF5",
                  "#98F5E1", "#B9FBC0", "#FDE4CF"]

        # Свободные зоны — только если включён тумблер
        if self.show_free_areas.get():
            for rect in self._compute_free_rects():
                fx0, fy0 = self._to_canvas(rect.x, rect.y)
                fx1, fy1 = self._to_canvas(rect.x + rect.w, rect.y + rect.h)

                self.canvas.create_rectangle(
                    fx0, fy0, fx1, fy1,
                    fill="#eaffea",
                    outline="#88cc88",
                    width=1,
                    dash=(4, 3),
                    tags=("free_rect",)
                )

                # Подпись с размером — только если прямоугольник достаточно большой
                rw = fx1 - fx0
                rh = fy1 - fy0
                if rw > 45 and rh > 22:
                    font_size = 10 if min(rw, rh) > 60 else 8
                    self.canvas.create_text(
                        (fx0 + fx1) / 2, (fy0 + fy1) / 2,
                        text=f"{rect.w}×{rect.h}",
                        font=("Arial", font_size),
                        fill="#2a7a2a",
                        justify=tk.CENTER,
                        tags=("free_rect",)
                    )

        for i, part in enumerate(self.current_parts()):
            self._draw_part(part, colors[i % len(colors)],
                            selected=(part.id == self.selected_part_id))

        self.canvas.config(scrollregion=(0, 0, lx1 + 40, ly1 + 40))

    def _draw_part(self, part, color, selected=False):
        """Рисует одну деталь. На мелких деталях — только размер в центре."""
        x0, y0 = self._to_canvas(part.x, part.y)
        x1, y1 = self._to_canvas(part.x + part.w, part.y + part.h)

        valid = (self._fits_on_sheet(part, part.x, part.y) and
                 not self._collides(part, part.x, part.y, ignore_id=part.id))

        if not valid:
            fill_color = "#ff9999"
            outline = "#cc0000"
            width = 3
        else:
            fill_color = color
            if selected:
                outline = "#ff0000"
                width = 3
            else:
                outline = "#333333"
                width = 1

        self.canvas.create_rectangle(x0, y0, x1, y1,
                                     fill=fill_color, outline=outline,
                                     width=width,
                                     tags=("part", f"part_{part.id}"))

        pw = x1 - x0
        ph = y1 - y0
        min_side = min(pw, ph)
        max_side = max(pw, ph)

        # Подбираем шрифт
        if min_side > 60:
            font_size = 11
        elif min_side > 40:
            font_size = 9
        elif min_side > 25:
            font_size = 7
        elif min_side > 12:
            font_size = 6
        else:
            font_size = 5

        cx = (x0 + x1) / 2
        cy = (y0 + y1) / 2

        # --- Определяем, что поместится ---
        # "Большая" деталь — по обеим сторонам не меньше 30 px
        is_big = pw >= 40 and ph >= 30
        # "Средняя" — влезет хотя бы размер + имя
        is_medium = pw >= 25 and ph >= 18
        # "Крошка" — рисуем только размер, если влезает хотя бы одна
        # осмысленная строка

        vertical_size = part.h > part.w

        size_txt = f"{part.w}×{part.h}"

        # ---------- Крошка: только размер по центру ----------
        if not is_medium:
            # Пробуем подобрать минимальный шрифт
            small_font = 5
            # Если даже размер не влезает в ширину — попробуем
            # только ширину или только высоту (без «×»)
            # Сначала пробуем полный размер
            est_w_full = len(size_txt) * small_font * 0.55
            est_h_full = small_font * 1.2

            if est_w_full <= pw - 2 and est_h_full <= ph - 2:
                self.canvas.create_text(
                    cx, cy,
                    text=size_txt,
                    font=("Arial", small_font),
                    justify=tk.CENTER,
                    tags=("part_label", f"label_{part.id}")
                )
            else:
                # Пробуем вертикально (для высоких и узких)
                if ph > pw:
                    est_w_v = small_font * 1.2
                    est_h_v = len(size_txt) * small_font * 0.55
                    if est_w_v <= pw - 2 and est_h_v <= ph - 2:
                        self.canvas.create_text(
                            cx, cy,
                            text=size_txt,
                            font=("Arial", small_font),
                            angle=90,
                            justify=tk.CENTER,
                            tags=("part_label", f"label_{part.id}")
                        )
                        return
                # Пробуем только одну сторону (наибольшую)
                single = f"{part.w}" if part.w >= part.h else f"{part.h}"
                est_w = len(single) * small_font * 0.55
                if est_w <= pw - 2 and small_font * 1.2 <= ph - 2:
                    self.canvas.create_text(
                        cx, cy,
                        text=single,
                        font=("Arial", small_font),
                        justify=tk.CENTER,
                        tags=("part_label", f"label_{part.id}")
                    )
            return  # на крошках ничего больше не рисуем

        # ---------- Средняя и большая — название + размер ----------
        # Порог «большой» для разных частей
        show_name = pw >= 40 and ph >= 30
        show_size = pw >= 25 and ph >= 18

        # Вертикальный текст, если деталь выше, чем шире
        use_angle = vertical_size and pw < 45

        # Позиционируем название и размер по вертикали
        # Если показываем оба — делим пополам
        if show_name and show_size:
            name_y = cy - ph * 0.15
            size_y = cy + ph * 0.15
        elif show_size:
            name_y = None
            size_y = cy
        else:
            name_y = cy
            size_y = None

        if show_name:
            name_text = part.name
            angle = 90 if use_angle else 0
            self.canvas.create_text(
                cx, name_y,
                text=name_text,
                font=("Arial", font_size),
                justify=tk.CENTER,
                angle=angle,
                tags=("part_label", f"name_{part.id}")
            )

        if show_size:
            size_with_rot = size_txt
            if part.rotated:
                size_with_rot += " ⟳"
            angle = 90 if use_angle else 0
            self.canvas.create_text(
                cx, size_y,
                text=size_with_rot,
                font=("Arial", font_size),
                justify=tk.CENTER,
                angle=angle,
                tags=("part_label", f"size_{part.id}")
            )

        # ---------- Дополнительные размеры по сторонам ----------
        # Только для больших деталей и сторон >= 500 мм
        dim_font = ("Arial", max(5, font_size - 2))

        # Длина сверху и снизу
        if part.w >= 500 and pw > 55:
            self.canvas.create_text(
                cx, y0 + 8,
                text=f"{part.w}",
                font=dim_font,
                fill="#333333",
                anchor=tk.N,
                tags=("dim", f"dim_top_{part.id}")
            )
            self.canvas.create_text(
                cx, y1 - 8,
                text=f"{part.w}",
                font=dim_font,
                fill="#333333",
                anchor=tk.S,
                tags=("dim", f"dim_bottom_{part.id}")
            )

        # Высота слева и справа
        if part.h >= 500 and ph > 55:
            self.canvas.create_text(
                x0 + 8, cy,
                text=f"{part.h}",
                font=dim_font,
                fill="#333333",
                anchor=tk.W,
                angle=90,
                tags=("dim", f"dim_left_{part.id}")
            )
            self.canvas.create_text(
                x1 - 8, cy,
                text=f"{part.h}",
                font=dim_font,
                fill="#333333",
                anchor=tk.E,
                angle=90,
                tags=("dim", f"dim_right_{part.id}")
            )

        # ---------- Предупреждение «нет места» ----------
        if not valid and pw > 20 and ph > 15:
            self.canvas.create_text(
                cx, y1 - 12,
                text="⚠",
                font=("Arial", max(6, font_size - 2)),
                fill="#cc0000",
                justify=tk.CENTER,
                tags=("part_label", f"warn_{part.id}")
            )

    def _draw_ghost(self, canvas_x, canvas_y):
        if self.drag_part_id is None:
            return
        part = next((p for p in self.all_parts if p.id == self.drag_part_id),
                    None)
        if part is None:
            return

        cx = self.canvas.canvasx(canvas_x)
        cy = self.canvas.canvasy(canvas_y)
        mm_x, mm_y = self._to_mm(cx, cy)

        px = mm_x - part.w / 2
        py = mm_y - part.h / 2
        px, py = self._snap_to_edges(part, px, py)
        px, py = self._snap_to_parts(part, px, py)

        x0, y0 = self._to_canvas(px, py)
        x1, y1 = self._to_canvas(px + part.w, py + part.h)

        valid = self._fits_on_sheet(part, px, py) and \
                not self._collides(part, px, py)

        color = "#88cc88" if valid else "#cc8888"

        self.canvas.create_rectangle(x0, y0, x1, y1,
                                     fill=color, outline="#333333",
                                     width=2, dash=(4, 2),
                                     stipple="gray50")

    # ---------- Повороты и удаление ----------

    def _on_canvas_double_click(self, event):
        """Двойной клик по детали — повернуть её."""
        cx = self.canvas.canvasx(event.x)
        cy = self.canvas.canvasy(event.y)
        mm_x, mm_y = self._to_mm(cx, cy)

        part = self._find_part_at(mm_x, mm_y)
        if part is None:
            return

        self.selected_part_id = part.id
        self._rotate_part(part)
        self._redraw()
        self._update_status()

    def _on_canvas_right_click(self, event):
        cx = self.canvas.canvasx(event.x)
        cy = self.canvas.canvasy(event.y)
        mm_x, mm_y = self._to_mm(cx, cy)

        part = self._find_part_at(mm_x, mm_y)
        if part is None:
            return

        # Удаляем из текущего листа
        current = self.current_parts()
        if part in current:
            current.remove(part)

        if self.selected_part_id == part.id:
            self.selected_part_id = None
        self._refresh_list()
        self._redraw()
        self._update_status()

    def _rotate_part(self, part):
        """Повернуть деталь на 90°. Невалидные позиции остаются
        (деталь подсветится красной)."""
        part.w, part.h = part.h, part.w
        part.rotated = not part.rotated

        # Прижимаем к границам листа
        part.x = max(0, min(part.x, self.sheet_w - part.w))
        part.y = max(0, min(part.y, self.sheet_h - part.h))

        self._refresh_list()
        self._redraw()
        self._update_status()

    def _rotate_selected(self):
        if self.selected_part_id is None:
            return
        part = next((p for p in self.all_parts
                     if p.id == self.selected_part_id), None)
        if part is None:
            return
        # Работает и для размещённых, и для неразмещённых
        self._rotate_part(part)

    def _delete_selected(self):
        if self.selected_part_id is None:
            return
        part = next((p for p in self.all_parts
                     if p.id == self.selected_part_id), None)
        if part is None:
            return
        current = self.current_parts()
        if part in current:
            current.remove(part)
            self._refresh_list()
            self._redraw()
            self._update_status()

    def _deselect(self):
        self.selected_part_id = None
        self._redraw()

    # ---------- Список ----------

    def _refresh_list(self):
        """Обновляет список неразмещённых деталей, с учётом сортировки."""
        self.listbox.delete(0, tk.END)

        unplaced = self.unplaced_parts()
        mode = self.sort_mode.get() if hasattr(self, "sort_mode") else "По порядку"

        if mode == "Площадь ↑":
            unplaced.sort(key=lambda p: p.w * p.h)
        elif mode == "Площадь ↓":
            unplaced.sort(key=lambda p: p.w * p.h, reverse=True)
        elif mode == "Длинная сторона ↑":
            unplaced.sort(key=lambda p: max(p.w, p.h))
        elif mode == "Длинная сторона ↓":
            unplaced.sort(key=lambda p: max(p.w, p.h), reverse=True)
        elif mode == "Короткая сторона ↑":
            unplaced.sort(key=lambda p: min(p.w, p.h))
        elif mode == "Короткая сторона ↓":
            unplaced.sort(key=lambda p: min(p.w, p.h), reverse=True)
        elif mode == "Название A→Я":
            unplaced.sort(key=lambda p: p.name.lower())
        elif mode == "Название Я→А":
            unplaced.sort(key=lambda p: p.name.lower(), reverse=True)

        self._sorted_unplaced = unplaced

        for part in unplaced:
            rot = " ⟳" if part.rotated else ""
            self.listbox.insert(tk.END, f"{part.name}  {part.w}×{part.h}{rot}")

        self._update_status()

    # ---------- Служебные ----------

    def auto_layout(self):
        """Автораскрой всех деталей, распределяя по листам."""
        part_dict = {}
        for mp in self.all_parts:
            key = (mp.name, mp.w, mp.h)
            part_dict[key] = part_dict.get(key, 0) + 1

        parts_for_auto = [Part(name, w, h, qty)
                          for (name, w, h), qty in part_dict.items()]

        from_auto = pack_parts(parts_for_auto, self.sheet_w, self.sheet_h,
                                self.kerf, allow_rotation=True,
                                multi_start=False)

        if not from_auto:
            messagebox.showwarning("Не удалось", "Автораскрой не удался")
            return

        # Сбрасываем всё
        self.sheets_parts = [[] for _ in from_auto]
        self.current_sheet_index = 0

        # Сопоставляем ManualPart ↔ PlacedPart
        used = set()
        for sheet_idx, auto_sheet in enumerate(from_auto):
            for placed in auto_sheet.placed:
                found = None
                for mp in self.all_parts:
                    if mp.id in used:
                        continue
                    if placed.rotated:
                        if (mp.name == placed.name and
                                mp.h == placed.w and mp.w == placed.h):
                            mp.w, mp.h = placed.w, placed.h
                            mp.rotated = True
                            found = mp
                            break
                    else:
                        if (mp.name == placed.name and
                                mp.w == placed.w and mp.h == placed.h):
                            mp.rotated = False
                            found = mp
                            break
                if found is None:
                    continue
                found.x = placed.x
                found.y = placed.y
                used.add(found.id)
                self.sheets_parts[sheet_idx].append(found)

        self.selected_part_id = None
        self._refresh_list()
        self._redraw()
        self._update_status()

        leftover = len(self.unplaced_parts())
        if leftover:
            messagebox.showinfo(
                "Автораскрой",
                f"Разложено по {len(from_auto)} листам.\n"
                f"Не поместилось деталей: {leftover}\n"
                "Можно добавить ещё лист кнопкой «+ Добавить лист»."
            )

    def clear_sheet(self):
        if not messagebox.askyesno("Очистить лист",
                                   f"Убрать все детали с листа "
                                   f"{self.current_sheet_index + 1}?"):
            return
        self.sheets_parts[self.current_sheet_index] = []
        self.selected_part_id = None
        self._refresh_list()
        self._redraw()
        self._update_status()

    def reset_all(self):
        if not messagebox.askyesno(
            "Сброс",
            "Вернуть все детали и оставить один лист?"
        ):
            return
        self.sheets_parts = [[]]
        self.current_sheet_index = 0
        self.selected_part_id = None
        self._refresh_list()
        self._redraw()
        self._update_status()

    # ---------- Применение ----------

    def apply_layout(self):
        """Применить раскрой (все листы) к основной программе."""
        all_placed = self.placed_parts()
        if not all_placed:
            messagebox.showinfo("Пусто", "Ни одной детали не размещено")
            return

        # Собираем валидные листы
        result_sheets = []
        total_invalid = []

        for sheet_parts in self.sheets_parts:
            if not sheet_parts:
                continue
            sheet = Sheet(self.sheet_w, self.sheet_h)
            for part in sheet_parts:
                valid = (self._fits_on_sheet(part, part.x, part.y) and
                         not self._collides_among(
                             part, sheet_parts, ignore_id=part.id))
                if not valid:
                    total_invalid.append(part)
                    continue
                sheet.placed.append(PlacedPart(
                    name=part.name,
                    x=part.x, y=part.y,
                    w=part.w, h=part.h,
                    rotated=part.rotated
                ))
            if sheet.placed:
                result_sheets.append(sheet)

        if not result_sheets:
            messagebox.showwarning("Пусто", "Нет валидных деталей")
            return

        if total_invalid:
            names = "\n".join(f"  • {p.name} {p.w}×{p.h}"
                              for p in total_invalid[:10])
            more = ""
            if len(total_invalid) > 10:
                more = f"\n  …и ещё {len(total_invalid) - 10}"
            if not messagebox.askyesno(
                "Есть невалидные детали",
                f"Пересекаются или выходят за лист:\n{names}{more}\n\n"
                "Продолжить? Невалидные детали будут выброшены."
            ):
                return

        if self.callback_on_apply:
            self.callback_on_apply(result_sheets)
        self.destroy()

    def _collides_among(self, part, parts_list, ignore_id=None):
        """Проверка коллизии внутри произвольного списка деталей."""
        kerf = self.kerf
        a_left = part.x - kerf
        a_right = part.x + part.w + kerf
        a_top = part.y - kerf
        a_bottom = part.y + part.h + kerf

        for other in parts_list:
            if other.id == part.id:
                continue
            if ignore_id is not None and other.id == ignore_id:
                continue
            b_left = other.x
            b_right = other.x + other.w
            b_top = other.y
            b_bottom = other.y + other.h
            if not (a_right <= b_left or a_left >= b_right or
                    a_bottom <= b_top or a_top >= b_bottom):
                return True
        return False

###