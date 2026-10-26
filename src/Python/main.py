from __future__ import annotations

import json
import os
import random
import time
import tkinter as tk
import tkinter.font as tkfont
from pathlib import Path

MAX_EXERCISES = 6  # групп параметров (и вариантов в Excersize count)
PER_ROW = 3  # групп в ряду: таблица 3 столбца x 2 строки
VISIBLE_CHARS = 20  # ширина поля ввода в символах
CONTENT_WIDTH = 760  # максимальная ширина центрированной колонки
WINDOW_SIZE = "800x900"  # размер окна по умолчанию

# (ключ, подпись, значение по умолчанию, числовое поле)
FIELDS = [
    ("min", "Min. reps", "2", True),
    ("max", "Max. reps", "14", True),
    ("length", "Round count", "13", True),
    ("total", "Total (optional)", "", True),
    ("exercise", "Exercise", "", False),
]

# PARAMS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "params.json")
PARAMS_FILE = os.path.join(Path.home(), "params.json")

def random_list(
    min_val: int, max_val: int, length: int, total: int | None = None
) -> list[int]:
    """Список из `length` случайных целых в [min_val, max_val].

    Если `total` задан, сумма элементов равна `total`.
    Если `total` равен None, значения ничем, кроме min/max, не ограничены.
    """
    if length <= 0:
        raise ValueError("Length of list must be positive")
    if min_val > max_val:
        raise ValueError("Min cannot be greater than max")

    if total is None:
        return [random.randint(min_val, max_val) for _ in range(length)]

    if not (length * min_val <= total <= length * max_val):
        raise ValueError(
            f"Impossible: sum must be in range "
            f"[{length * min_val}, {length * max_val}]"
        )

    result = []
    remaining = total

    for i in range(length):
        left = length - i - 1  # сколько элементов ещё предстоит заполнить

        low = max(min_val, remaining - left * max_val)
        high = min(max_val, remaining - left * min_val)

        value = random.randint(low, high)
        result.append(value)
        remaining -= value

    random.shuffle(result)
    return result


def format_time(seconds: float) -> str:
    seconds = int(seconds)
    h, rest = divmod(seconds, 3600)
    m, s = divmod(rest, 60)
    return f"{h:02d}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


def is_numeric_text(text: str) -> bool:
    """Допустимый ввод для числовых полей: только цифры и минус."""
    return all(c.isdigit() or c == "-" for c in text)


class WorkoutApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        root.title("Deck Of Cards Workout")
        root.geometry(WINDOW_SIZE)

        self.count = 1
        self.lists: list[list[int]] = []
        self.positions: list[int] = []  # сколько элементов уже выведено из каждого списка
        self.max_rounds = 0
        self.round_index = 0
        self.start_time = 0.0  # начало тренировки
        self.round_start = 0.0  # начало текущего раунда
        self.timer_job = None

        base = tkfont.nametofont("TkDefaultFont")
        self.small_font = base.copy()
        self.small_font.configure(size=9)
        self.bold_font = base.copy()
        self.bold_font.configure(size=9, weight="bold")
        self.info_font = base.copy()
        self.info_font.configure(size=16)
        self.round_font = base.copy()
        self.round_font.configure(size=22, weight="bold")
        self.timer_font = base.copy()
        self.timer_font.configure(size=18, weight="bold")

        self.numeric_check = (root.register(is_numeric_text), "%P")
        self.wrap_labels: list[tk.Label] = []

        # ============ Колонка с элементами: по центру, прижата к верху ============
        self.content = tk.Frame(root)
        self.content.place(relx=0.5, y=30, anchor="n", width=CONTENT_WIDTH)

        # --- Раздел настроек: фиксированная высота = 50% высоты окна ---
        self.settings = tk.Frame(self.content, height=300)
        self.settings.pack(fill="x")
        self.settings.pack_propagate(True)

        # Exercise count: radiobutton 1..6
        count_row = tk.Frame(self.settings)
        count_row.pack(pady=(0, 10))
        tk.Label(count_row, text="Exercise count").pack(side="left", padx=(0, 10))
        self.count_var = tk.IntVar(value=1)
        self.radios: list[tk.Radiobutton] = []
        for n in range(1, MAX_EXERCISES + 1):
            radio = tk.Radiobutton(
                count_row,
                text=str(n),
                value=n,
                variable=self.count_var,
                command=self.on_radio,
            )
            radio.pack(side="left", padx=4)
            self.radios.append(radio)

        # Группы полей: таблица 3 столбца x 2 строки
        self.groups_box = tk.Frame(self.settings)
        self.groups_box.pack(fill="x")
        for col in range(PER_ROW):
            self.groups_box.columnconfigure(col, weight=1, uniform="groups")
        self.groups = [self.build_group(i) for i in range(MAX_EXERCISES)]

        # --- Нижняя часть колонки ---
        self.generate_btn = tk.Button(
            self.content, text="Generate", command=self.generate
        )
        self.generate_btn.pack(fill="x", pady=(10, 5), ipady=8)

        self.result_label = self.make_label(font=self.info_font)  # ошибки
        
        
        
        self.round_label = self.make_label(font=self.round_font)  # значение + упражнение
        self.counter_label = self.make_label(font=self.round_font)  # Раунд i/N

        timers = tk.Frame(self.content)
        timers.pack(fill="x", pady=15)
        timers.columnconfigure(0, weight=1, uniform="timers")
        timers.columnconfigure(1, weight=1, uniform="timers")
        self.timer_label = tk.Label(timers, text="Total time: 00:00", font=self.timer_font)
        self.timer_label.grid(row=0, column=0)
        self.round_timer_label = tk.Label(
            timers, text="Round time: 00:00", font=self.timer_font
        )
        self.round_timer_label.grid(row=0, column=1)

        
        self.shown_label = self.make_label(font=self.info_font)  # сумма по всем спискам  
        self.sum_label = self.make_label(font=self.info_font)  # суммы по упражнениям

        # ============ Кнопки тренировки: прижаты к нижнему краю окна ============
        self.buttons = tk.Frame(root)
        self.buttons.place(relx=0.5, rely=1.0, y=-15, anchor="s", width=CONTENT_WIDTH)
        self.start_btn = tk.Button(
            self.buttons, text="Start Workout", command=self.start_workout
        )
        self.next_btn = tk.Button(
            self.buttons, text="Next Round", command=self.next_round
        )
        self.stop_btn = tk.Button(
            self.buttons, text="Stop Workout", command=self.stop_workout
        )
        self.show_idle_buttons()

        self.set_count(1)
        root.bind("<Configure>", self.on_resize)
        root.protocol("WM_DELETE_WINDOW", self.on_close)

    # ---------- построение интерфейса ----------
    def make_label(self, font) -> tk.Label:
        """Подпись по центру колонки; перенос строк по ширине колонки."""
        label = tk.Label(
            self.content, text="", font=font, justify="center", wraplength=CONTENT_WIDTH
        )
        label.pack(pady=2)
        self.wrap_labels.append(label)
        return label

    def build_group(self, index: int) -> dict:
        frame = tk.Frame(self.groups_box)
        tk.Label(frame, text=f"Exercise {index + 1}", font=self.bold_font).grid(
            row=0, column=0, columnspan=2, pady=(0, 3)
        )

        inputs = {}
        for row, (key, title, default, numeric) in enumerate(FIELDS, start=1):
            tk.Label(
                frame, text=title, font=self.small_font, width=16, anchor="center"
            ).grid(row=row, column=0, padx=(0, 4), pady=1)

            var = tk.StringVar(value=default)
            entry = tk.Entry(
                frame, textvariable=var, width=VISIBLE_CHARS, font=self.small_font
            )
            if numeric:
                entry.configure(validate="key", validatecommand=self.numeric_check)
            entry.grid(row=row, column=1, pady=1)
            inputs[key] = var

        return {"frame": frame, "inputs": inputs}

    def on_resize(self, event):
        if event.widget is not self.root:
            return
        column_width = max(0, min(event.width - 30, CONTENT_WIDTH))
        self.content.place_configure(width=column_width)
        self.buttons.place_configure(width=column_width)
        self.settings.configure(height=int(event.height * 0.5))
        for label in self.wrap_labels:
            label.configure(wraplength=column_width)

    # ---------- выбор количества упражнений ----------
    def on_radio(self):
        self.set_count(self.count_var.get())

    def set_count(self, n: int):
        self.count = n
        for i, group in enumerate(self.groups):
            if i < n:
                group["frame"].grid(
                    row=i // PER_ROW,
                    column=i % PER_ROW,
                    padx=8,
                    pady=6,
                    sticky="n",
                )
            else:
                group["frame"].grid_remove()

        # сгенерированные списки относились к прежнему количеству упражнений
        self.lists = []
        self.result_label.configure(text="")
        self.counter_label.configure(text="")
        self.shown_label.configure(text="")
        self.round_label.configure(text="")
        self.sum_label.configure(text="")

    # ---------- сохранение и загрузка параметров ----------
    def load_params(self, path: str):
        """Подставить в поля ввода параметры, сохранённые при прошлом запуске."""
        try:
            print("Read " + path)
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, ValueError):
            print("Read error")
            return  # файла нет или он повреждён: остаются значения по умолчанию

        if not isinstance(data, dict):
            return

        groups_data = data.get("groups")
        if not isinstance(groups_data, list):
            groups_data = [data]  # старый формат: одна группа полей без вложенности

        shared_length = data.get("length")  # файл прежней версии: одна длина на все
        for group, saved in zip(self.groups, groups_data):
            if not isinstance(saved, dict):
                continue
            for key, var in group["inputs"].items():
                value = saved.get(key)
                if value is None and key == "length":
                    value = shared_length
                if isinstance(value, str):
                    var.set(value)

        count = data.get("count")
        if isinstance(count, int) and 1 <= count <= MAX_EXERCISES:
            self.count_var.set(count)
            self.set_count(count)

    def save_params(self, path: str):
        """Записать текущее содержимое полей ввода в файл."""
        data = {
            "count": self.count,
            "groups": [
                {key: var.get() for key, var in group["inputs"].items()}
                for group in self.groups
            ],
        }
        try:
            print("Write " + path)
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except OSError:
            print("Write error")
            pass  # не удалось записать: не мешаем закрытию программы

    def on_close(self):
        self.save_params(PARAMS_FILE)
        if self.timer_job is not None:
            self.root.after_cancel(self.timer_job)
        self.root.destroy()

    # ---------- переключение кнопок ----------
    def show_idle_buttons(self):
        self.next_btn.pack_forget()
        self.stop_btn.pack_forget()
        self.start_btn.pack(fill="x", ipady=10)

    def show_workout_buttons(self):
        self.start_btn.pack_forget()
        self.next_btn.pack(side="left", fill="x", expand=True, padx=(0, 5), ipady=10)
        self.stop_btn.pack(side="left", fill="x", expand=True, padx=(5, 0), ipady=10)

    def set_settings_locked(self, locked: bool):
        state = "disabled" if locked else "normal"
        self.generate_btn.configure(state=state)
        for radio in self.radios:
            radio.configure(state=state)

    # ---------- генерация ----------
    def generate(self):
        new_lists = []
        for k in range(self.count):
            inputs = self.groups[k]["inputs"]
            prefix = f"Упражнение {k + 1}: " if self.count > 1 else ""

            try:
                min_val = int(inputs["min"].get())
                max_val = int(inputs["max"].get())
                length = int(inputs["length"].get())
                total_text = inputs["total"].get().strip()
                total = int(total_text) if total_text else None
            except ValueError:
                self.result_label.configure(
                    text=f"{prefix}Error: all fields must contain integers"
                )
                return

            try:
                new_lists.append(random_list(min_val, max_val, length, total))
            except ValueError as e:
                self.result_label.configure(text=f"{prefix}Error: {e}")
                return

        self.lists = new_lists
        # списки не показываем, только очищаем прошлую ошибку и надписи тренировки
        self.result_label.configure(text="")
        self.round_label.configure(text="")
        self.counter_label.configure(text="")
        self.shown_label.configure(text="")
        self.sum_label.configure(text="")

    # ---------- тренировка ----------
    def exercise_name(self, k: int) -> str:
        return self.groups[k]["inputs"]["exercise"].get().strip() or f"№{k + 1}"

    def sums_text(self) -> str:
        sums = [sum(lst[:pos]) for lst, pos in zip(self.lists, self.positions)]
        if len(sums) == 1:
            return f"Sum of reps: {sums[0]}"

        parts = [f"{self.exercise_name(k)}-{s}" for k, s in enumerate(sums)]
        return "Sum of reps: " + ", ".join(parts)

    def shown_text(self) -> str:
        """Sum of all values, displayed up to this point, across all lists together."""
        total = sum(sum(lst[:pos]) for lst, pos in zip(self.lists, self.positions))
        return f"Total reps(all exercises): {total}"

    def start_workout(self):
        if not self.lists:
            self.round_label.configure(text="First, click Generate")
            return

        self.max_rounds = sum(len(lst) for lst in self.lists)  # по раунду на элемент
        self.positions = [0] * len(self.lists)
        self.round_index = 0
        self.start_time = self.round_start = time.monotonic()
        self.update_timer()
        self.counter_label.configure(text=f"Round 0/{self.max_rounds}")
        self.shown_label.configure(text=self.shown_text())
        self.round_label.configure(text="Click Next Round")
        self.sum_label.configure(text=self.sums_text())
        self.next_btn.configure(state="normal")
        self.set_settings_locked(True)  # менять настройки во время тренировки нельзя
        self.show_workout_buttons()

        self.timer_job = self.root.after(200, self.tick)

    def tick(self):
        self.update_timer()
        self.timer_job = self.root.after(200, self.tick)

    def update_timer(self):
        now = time.monotonic()
        self.timer_label.configure(text=f"Total time: {format_time(now - self.start_time)}")
        self.round_timer_label.configure(
            text=f"Round time: {format_time(now - self.round_start)}"
        )

    def next_round(self):
        if self.round_index >= self.max_rounds:
            return

        # выбираем случайный список, в котором ещё остались невыведенные значения
        candidates = [
            k for k, lst in enumerate(self.lists) if self.positions[k] < len(lst)
        ]
        k = random.choice(candidates)

        value = self.lists[k][self.positions[k]]
        self.positions[k] += 1
        self.round_index += 1
        self.round_start = time.monotonic()  # таймер раунда начинается заново
        self.update_timer()

        exercise = self.groups[k]["inputs"]["exercise"].get().strip()
        self.round_label.configure(text=f"{value} {exercise}".strip())
        self.counter_label.configure(text=f"Round {self.round_index}/{self.max_rounds}")
        self.shown_label.configure(text=self.shown_text())
        self.sum_label.configure(text=self.sums_text())

        if self.round_index >= self.max_rounds:
            self.next_btn.configure(state="disabled")  # раунды закончились

    def stop_workout(self):
        if self.timer_job is not None:
            self.root.after_cancel(self.timer_job)
            self.timer_job = None
        self.update_timer()  # зафиксировать итоговое время
        if self.lists and self.round_index >= self.max_rounds:
            self.round_label.configure(text="Workout completed!")
        self.set_settings_locked(False)
        self.show_idle_buttons()


def main():
    root = tk.Tk()
    app = WorkoutApp(root)
    app.load_params(PARAMS_FILE)
    root.mainloop()


if __name__ == "__main__":
    main()
