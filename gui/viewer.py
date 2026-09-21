import tkinter as tk
from tkinter import ttk
from models import Sheet, PlacedPart
from utils.constants import COLORS
from typing import List

class SheetViewer(tk.Toplevel):
    """Окно крупного просмотра одного листа раскроя."""

    def __init__(self, master, sheets, sheet_w, sheet_h, start_index=0):
        super().__init__(master)
        self.title("Просмотр листа")
        self.geometry("1100x750")

        self.sheets = sheets
        self.sheet_w = sheet_w
        self.sheet_h = sheet_h
        self.current = start_index

        self._build_ui()
        self._render()

    def _build_ui(self):
        # Верхняя панель — навигация
        top = ttk.Frame(self, padding=8)
        top.pack(side=tk.TOP, fill=tk.X)

        ttk.Button(top, text="◀ Назад",
                   command=self.prev_sheet).pack(side=tk.LEFT)
        self.lbl_title = ttk.Label(top, text="", font=("Arial", 11, "bold"))
        self.lbl_title.pack(side=tk.LEFT, padx=12)
        ttk.Button(top, text="Вперёд ▶",
                   command=self.next_sheet).pack(side=tk.LEFT)

        # Справа — размеры
        self.lbl_info = ttk.Label(top, text="", font=("Arial", 9))
        self.lbl_info.pack(side=tk.RIGHT)

        # Основная область: слева canvas, справа список
        main = ttk.Frame(self)
        main.pack(side=tk.TOP, fill=tk.BOTH, expand=True)

        # Canvas со скроллами
        canvas_frame = ttk.Frame(main)
        canvas_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        v_scroll = ttk.Scrollbar(canvas_frame, orient=tk.VERTICAL)
        v_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        h_scroll = ttk.Scrollbar(canvas_frame, orient=tk.HORIZONTAL)
        h_scroll.pack(side=tk.BOTTOM, fill=tk.X)

        self.canvas = tk.Canvas(canvas_frame, bg="white",
                                yscrollcommand=v_scroll.set,
                                xscrollcommand=h_scroll.set)
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        v_scroll.config(command=self.canvas.yview)
        h_scroll.config(command=self.canvas.xview)

        # Список деталей справа
        right = ttk.Frame(main, padding=6, width=260)
        right.pack(side=tk.RIGHT, fill=tk.Y)
        right.pack_propagate(False)

        ttk.Label(right, text="Детали на листе",
                  font=("Arial", 10, "bold")).pack(anchor=tk.W)

        self.tree = ttk.Treeview(right,
                                 columns=("name", "size", "pos"),
                                 show="headings", height=25)
        self.tree.heading("name", text="Название")
        self.tree.heading("size", text="Размер")
        self.tree.heading("pos", text="Позиция")
        self.tree.column("name", width=110)
        self.tree.column("size", width=80, anchor=tk.E)
        self.tree.column("pos", width=60, anchor=tk.E)
        self.tree.pack(fill=tk.BOTH, expand=True, pady=4)

        # Нижняя панель — заполнение
        self.lbl_fill = ttk.Label(right, text="", font=("Arial", 9))
        self.lbl_fill.pack(anchor=tk.W)

        # Горячие клавиши
        self.bind("<Left>", lambda e: self.prev_sheet())
        self.bind("<Right>", lambda e: self.next_sheet())
        self.bind("<Escape>", lambda e: self.destroy())

    def prev_sheet(self):
        if self.current > 0:
            self.current -= 1
            self._render()

    def next_sheet(self):
        if self.current < len(self.sheets) - 1:
            self.current += 1
            self._render()

    def _render(self):
        """Перерисовать текущий лист крупно."""
        self.canvas.delete("all")
        if not self.sheets:
            return

        sheet = self.sheets[self.current]
        self.lbl_title.config(
            text=f"Лист {self.current + 1} из {len(self.sheets)}"
        )
        self.lbl_info.config(
            text=f"{self.sheet_w}×{self.sheet_h} мм"
        )
        self.lbl_fill.config(
            text=f"Заполнение: {sheet.fill_percent:.1f}%  "
                 f"({sheet.used_area / 1e6:.3f} / "
                 f"{sheet.total_area / 1e6:.3f} м²)"
        )

        cw = self.canvas.winfo_width() or 800
        ch = self.canvas.winfo_height() or 600

        pad = 40
        avail_w = max(cw - 2 * pad, 200)
        avail_h = max(ch - 2 * pad, 200)

        scale_x = avail_w / self.sheet_w
        scale_y = avail_h / self.sheet_h
        scale = min(scale_x, scale_y)
        scale = min(scale, 0.5)

        draw_w = self.sheet_w * scale
        draw_h = self.sheet_h * scale

        ox = (cw - draw_w) / 2
        oy = (ch - draw_h) / 2

        # Рамка листа
        self.canvas.create_rectangle(ox, oy, ox + draw_w, oy + draw_h,
                                     outline="black", width=2)

        # Размеры листа
        self.canvas.create_text(ox + draw_w / 2, oy - 15,
                                text=f"{self.sheet_w} мм",
                                anchor=tk.CENTER, font=("Arial", 9, "bold"))
        self.canvas.create_text(ox - 15, oy + draw_h / 2,
                                text=f"{self.sheet_h} мм",
                                anchor=tk.CENTER, font=("Arial", 9, "bold"),
                                angle=90)

        self.tree.delete(*self.tree.get_children())

        colors = ["#FFB3BA", "#FFDFBA", "#FFFFBA", "#BAFFC9", "#BAE1FF",
                  "#E0BBE4", "#FEC8D8", "#D4F0F0", "#FFDAC1", "#B5EAD7",
                  "#F1C0E8", "#CFBAF0", "#A3C4F3", "#90DBF4", "#8EECF5",
                  "#98F5E1", "#B9FBC0", "#FDE4CF"]

        for j, part in enumerate(sheet.placed):
            px = ox + part.x * scale
            py = oy + part.y * scale
            pw = part.w * scale
            ph = part.h * scale

            color = colors[j % len(colors)]
            self.canvas.create_rectangle(px, py, px + pw, py + ph,
                                         fill=color, outline="black")

            # Подбираем шрифт в зависимости от размера прямоугольника
            min_side = min(pw, ph)
            if min_side > 55:
                font_size = 11
            elif min_side > 35:
                font_size = 9
            elif min_side > 22:
                font_size = 7
            else:
                font_size = 6

            # Многострочная подпись: номер, название, размер
            lines = []
            if pw > 40 and ph > 30:
                lines.append(f"{j + 1}. {part.name}")
            elif pw > 25 and ph > 18:
                lines.append(str(j + 1))

            if pw > 45 and ph > 35:
                lines.append(f"{part.w}×{part.h}")
                if part.rotated:
                    lines.append("(повёрнута)")

            if lines:
                self.canvas.create_text(
                    px + pw / 2, py + ph / 2,
                    text="\n".join(lines),
                    font=("Arial", font_size),
                    justify=tk.CENTER,
                )

            # Подпись в списке справа
            rot = " ⟳" if part.rotated else ""
            self.tree.insert(
                "", tk.END,
                values=(f"{j + 1}. {part.name}{rot}",
                        f"{part.w}×{part.h}",
                        f"({part.x}, {part.y})")
            )


        # Обновляем scrollregion
        self.canvas.config(scrollregion=(0, 0, cw, ch))