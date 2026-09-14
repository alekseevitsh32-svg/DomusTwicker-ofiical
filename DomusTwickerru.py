import os
import sys
import subprocess
import threading
import tkinter as tk
from tkinter import ttk, messagebox
from pathlib import Path
import winreg

try:
    import psutil
except ImportError:
    psutil = None

# --- Реестр: ярлыки ---
REG_PATH = r"SOFTWARE\Microsoft\Windows\CurrentVersion\Explorer"
VALUE_NAME = "link"
REMOVE_VALUE = b'\x00\x00\x00\x00'
RESTORE_VALUE = b'\x1e\x00\x00\x00'

# --- Реестр: бесполезная функция ---
DRAG_REG_PATH = r"Control Panel\Desktop"
DRAG_VALUE_NAME = "DragFullWindows"

# --- Реестр: автозагрузка ---
RUN_REG_PATH = r"Software\Microsoft\Windows\CurrentVersion\Run"
RUN_VALUE_NAME = "DomusTwicker"


# ==================== ПЕРЕЗАГРУЗКА ====================

def ask_reboot():
    answer = messagebox.askyesno(
        "Требуется перезагрузка",
        "Настройка применена.\n\n"
        "Перезагрузить компьютер сейчас, чтобы применить изменения?\n\n"
        "• Да — перезагрузка через 10 секунд (можно отменить командой «shutdown /a»)\n"
        "• Нет — изменения вступят в силу при следующей перезагрузке вручную"
    )
    if answer:
        do_reboot()
    else:
        messagebox.showinfo(
            "Отложено",
            "Хорошо. Не забудьте перезагрузить компьютер позже."
        )


def do_reboot():
    try:
        subprocess.Popen(
            ['shutdown', '/r', '/t', '10',
             '/c', 'DomusTwicker: перезагрузка для применения настроек'],
            shell=False
        )
        messagebox.showinfo(
            "Перезагрузка",
            "Компьютер будет перезагружен через 10 секунд.\n\n"
            "Отмена: shutdown /a"
        )
    except Exception as e:
        messagebox.showerror("Ошибка", f"Не удалось запустить перезагрузку:\n{e}")


# ==================== ЯРЛЫКИ ====================

def set_link_value(value: bytes):
    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, REG_PATH, 0, winreg.KEY_SET_VALUE
        ) as key:
            winreg.SetValueEx(key, VALUE_NAME, 0, winreg.REG_BINARY, value)
        messagebox.showinfo(
            "Готово",
            "Настройка применена для НОВЫХ ярлыков."
        )
    except Exception as e:
        messagebox.showerror("Ошибка", f"Не удалось изменить реестр:\n{e}")


def rename_all_shortcuts(dry_run=False):
    folders = [
        Path.home() / "Desktop",
        Path(os.getenv('APPDATA', '')) / "Microsoft" / "Windows" / "Start Menu" / "Programs",
        Path(os.getenv('PROGRAMDATA', '')) / "Microsoft" / "Windows" / "Start Menu" / "Programs",
    ]
    suffixes = [" - Ярлык", " - Shortcut"]
    renamed, skipped, errors = 0, 0, 0

    for folder in folders:
        if not folder.exists():
            continue
        for lnk in folder.rglob("*.lnk"):
            name_no_ext = lnk.stem
            for suffix in suffixes:
                if name_no_ext.endswith(suffix):
                    new_name = name_no_ext[:-len(suffix)] + lnk.suffix
                    new_path = lnk.with_name(new_name)
                    try:
                        lnk.rename(new_path)
                        renamed += 1
                    except Exception:
                        errors += 1
                    break
            else:
                skipped += 1

    return renamed, skipped, errors


def on_rename_all():
    if not messagebox.askyesno(
        "Подтверждение",
        "Убрать текст «- Ярлык» у ВСЕХ существующих ярлыков?"
    ):
        return

    btn_rename_all.config(state=tk.DISABLED, text="Обработка...")

    def worker():
        renamed, skipped, errors = rename_all_shortcuts()
        root.after(0, lambda: finish_rename(renamed, skipped, errors))

    threading.Thread(target=worker, daemon=True).start()


def finish_rename(renamed, skipped, errors):
    btn_rename_all.config(state=tk.NORMAL, text="Убрать текст у всех ярлыков")
    messagebox.showinfo(
        "Готово",
        f"Переименовано: {renamed}\n"
        f"Без изменений: {skipped}\n"
        f"Ошибок: {errors}\n\n"
        "Нажмите F5 на рабочем столе."
    )


# ==================== БЕСПОЛЕЗНОЕ ====================

def get_drag_full_windows() -> int:
    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, DRAG_REG_PATH, 0, winreg.KEY_READ
        ) as key:
            value, _ = winreg.QueryValueEx(key, DRAG_VALUE_NAME)
            return int(value)
    except FileNotFoundError:
        return 1


def set_drag_full_windows(value: int):
    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, DRAG_REG_PATH, 0, winreg.KEY_SET_VALUE
        ) as key:
            winreg.SetValueEx(key, DRAG_VALUE_NAME, 0, winreg.REG_SZ, str(value))
    except Exception as e:
        messagebox.showerror("Ошибка", f"Не удалось изменить реестр:\n{e}")
        return False
    return True


def toggle_drag_windows():
    current = get_drag_full_windows()
    if current == 1:
        if not set_drag_full_windows(0):
            return
        messagebox.showinfo("🪟 Включено", "При перетаскивании видно только контур окна.")
    else:
        if not set_drag_full_windows(1):
            return
        messagebox.showinfo("✅ Выключено", "Окна снова видны целиком.")
    update_drag_button()
    ask_reboot()


def update_drag_button():
    current = get_drag_full_windows()
    if current == 1:
        btn_drag.config(text="Включить невидимые окна при перетаскивании")
    else:
        btn_drag.config(text="Выключить невидимые окна при перетаскивании")


# ==================== АВТОЗАГРУЗКА ====================

def get_exe_path() -> str:
    """Возвращает путь к текущему .exe (или .py, если запущено как скрипт)."""
    if getattr(sys, 'frozen', False):
        # Собрано PyInstaller'ом
        return sys.executable
    # Запущено как .py — сохраняем и путь к питону, и путь к скрипту
    return f'"{sys.executable}" "{os.path.abspath(sys.argv[0])}"'


def is_in_autostart() -> bool:
    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, RUN_REG_PATH, 0, winreg.KEY_READ
        ) as key:
            winreg.QueryValueEx(key, RUN_VALUE_NAME)
            return True
    except FileNotFoundError:
        return False


def add_to_autostart():
    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, RUN_REG_PATH, 0, winreg.KEY_SET_VALUE
        ) as key:
            winreg.SetValueEx(key, RUN_VALUE_NAME, 0, winreg.REG_SZ, get_exe_path())
        messagebox.showinfo(
            "Автозагрузка",
            "DomusTwicker добавлен в автозагрузку текущего пользователя.\n\n"
            "Он будет запускаться при входе в систему."
        )
    except Exception as e:
        messagebox.showerror("Ошибка", f"Не удалось добавить в автозагрузку:\n{e}")
    update_autostart_button()


def remove_from_autostart():
    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, RUN_REG_PATH, 0, winreg.KEY_SET_VALUE
        ) as key:
            winreg.DeleteValue(key, RUN_VALUE_NAME)
        messagebox.showinfo("Автозагрузка", "DomusTwicker удалён из автозагрузки.")
    except FileNotFoundError:
        messagebox.showinfo("Автозагрузка", "Запись и так отсутствует.")
    except Exception as e:
        messagebox.showerror("Ошибка", f"Не удалось удалить из автозагрузки:\n{e}")
    update_autostart_button()


def toggle_autostart():
    if is_in_autostart():
        remove_from_autostart()
    else:
        add_to_autostart()


def update_autostart_button():
    if is_in_autostart():
        btn_autostart.config(text="Выключить автозагрузку DomusTwicker")
        lbl_autostart_status.config(text="Статус: ✅ включена", foreground="green")
    else:
        btn_autostart.config(text="Включить DomusTwicker в автозагрузку")
        lbl_autostart_status.config(text="Статус: ⛔ выключена", foreground="gray")


# ==================== ДИСПЕТЧЕР ====================

def refresh_processes():
    """Заполняет таблицу процессов (вызывается в фоновом потоке)."""
    if psutil is None:
        messagebox.showerror(
            "Нет psutil",
            "Библиотека psutil не установлена.\n\n"
            "Установите её командой:\n"
            "pip install psutil"
        )
        return

    btn_refresh.config(state=tk.DISABLED, text="Обновление...")

    def worker():
        # Первый проход — «прогрев», чтобы cpu_percent вернул осмысленные значения
        procs = []
        for p in psutil.process_iter(['pid', 'name', 'exe', 'memory_info']):
            try:
                p.cpu_percent(interval=None)
                procs.append(p)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue

        # Небольшая пауза, чтобы psutil успел замерить дельту CPU
        import time
        time.sleep(0.5)

        rows = []
        for p in procs:
            try:
                info = p.info
                cpu = p.cpu_percent(interval=None)
                mem = info['memory_info'].rss / (1024 * 1024) if info['memory_info'] else 0
                exe = info.get('exe') or "—"
                rows.append((info['pid'], info['name'] or "—", f"{cpu:.1f}", f"{mem:.1f}", exe))
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue

        # Сортировка по CPU (по убыванию)
        rows.sort(key=lambda r: float(r[2]), reverse=True)
        root.after(0, lambda: fill_process_table(rows))

    threading.Thread(target=worker, daemon=True).start()


def fill_process_table(rows):
    # Очищаем таблицу
    for item in tree.get_children():
        tree.delete(item)

    for pid, name, cpu, mem, exe in rows:
        tree.insert("", "end", values=(pid, name, cpu, mem, exe))

    btn_refresh.config(state=tk.NORMAL, text="Обновить список")
    lbl_proc_count.config(text=f"Процессов: {len(rows)}")


def open_process_folder():
    """Открывает проводник с выделенным файлом выбранного процесса."""
    selected = tree.selection()
    if not selected:
        messagebox.showinfo("Ничего не выбрано", "Выберите процесс в таблице.")
        return

    values = tree.item(selected[0], "values")
    exe_path = values[4]

    if exe_path == "—" or not exe_path:
        messagebox.showwarning(
            "Путь недоступен",
            "Для этого процесса система не отдала путь к файлу.\n\n"
            "Обычно так бывает для системных процессов — попробуйте "
            "запустить DomusTwicker от имени администратора."
        )
        return

    try:
        # explorer /select, "путь" — открывает папку с выделенным файлом
        subprocess.Popen(['explorer', '/select,', exe_path])
    except Exception as e:
        messagebox.showerror("Ошибка", f"Не удалось открыть папку:\n{e}")


# ==================== GUI ====================

root = tk.Tk()
root.title("DomusTwicker")
root.geometry("720x520")
root.minsize(640, 480)

style = ttk.Style()
style.theme_use("vista" if "vista" in style.theme_names() else "clam")

notebook = ttk.Notebook(root)
notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

# ---------- Вкладка 1: Ярлыки ----------
tab_shortcuts = ttk.Frame(notebook, padding=20)
notebook.add(tab_shortcuts, text="Ярлыки")

ttk.Label(tab_shortcuts, text="Настройки ярлыков", font=("Segoe UI", 12, "bold")).pack(anchor="w", pady=(0, 10))

ttk.Button(
    tab_shortcuts, text="Убрать текст у НОВЫХ ярлыков (реестр)",
    command=lambda: set_link_value(REMOVE_VALUE)
).pack(fill=tk.X, pady=4)

btn_rename_all = ttk.Button(
    tab_shortcuts, text="Убрать текст у всех ярлыков",
    command=on_rename_all
)
btn_rename_all.pack(fill=tk.X, pady=4)

ttk.Button(
    tab_shortcuts, text="Вернуть настройку реестра",
    command=lambda: set_link_value(RESTORE_VALUE)
).pack(fill=tk.X, pady=4)

# ---------- Вкладка 2: Автозагрузка ----------
tab_autostart = ttk.Frame(notebook, padding=20)
notebook.add(tab_autostart, text="Автозагрузка")

ttk.Label(tab_autostart, text="Автозагрузка DomusTwicker", font=("Segoe UI", 12, "bold")).pack(anchor="w", pady=(0, 10))

lbl_autostart_status = ttk.Label(tab_autostart, text="Статус: ...", font=("Segoe UI", 10))
lbl_autostart_status.pack(anchor="w", pady=(0, 15))

btn_autostart = ttk.Button(tab_autostart, text="...", command=toggle_autostart)
btn_autostart.pack(fill=tk.X, pady=4)

ttk.Label(
    tab_autostart,
    text="Запись создаётся в HKEY_CURRENT_USER\\...\\Run.\n"
         "Права администратора не нужны.",
    font=("Segoe UI", 8, "italic"), foreground="gray", justify="left"
).pack(anchor="w", pady=(15, 0))

# ---------- Вкладка 3: Диспетчер ----------
tab_taskmgr = ttk.Frame(notebook, padding=10)
notebook.add(tab_taskmgr, text="Диспетчер")

top_bar = ttk.Frame(tab_taskmgr)
top_bar.pack(fill=tk.X, pady=(0, 6))

btn_refresh = ttk.Button(top_bar, text="Обновить список", command=refresh_processes)
btn_refresh.pack(side=tk.LEFT)

lbl_proc_count = ttk.Label(top_bar, text="Процессов: —", font=("Segoe UI", 9))
lbl_proc_count.pack(side=tk.LEFT, padx=15)

btn_open_folder = ttk.Button(
    top_bar, text="Открыть папку с файлом", command=open_process_folder
)
btn_open_folder.pack(side=tk.RIGHT)

# Таблица процессов
columns = ("pid", "name", "cpu", "mem", "exe")
tree = ttk.Treeview(tab_taskmgr, columns=columns, show="headings", height=18)

tree.heading("pid", text="PID")
tree.heading("name", text="Имя")
tree.heading("cpu", text="CPU %")
tree.heading("mem", text="RAM (МБ)")
tree.heading("exe", text="Путь к файлу")

tree.column("pid", width=70, anchor="center", stretch=False)
tree.column("name", width=180, anchor="w", stretch=False)
tree.column("cpu", width=80, anchor="e", stretch=False)
tree.column("mem", width=100, anchor="e", stretch=False)
tree.column("exe", width=350, anchor="w", stretch=True)

scroll = ttk.Scrollbar(tab_taskmgr, orient="vertical", command=tree.yview)
tree.configure(yscrollcommand=scroll.set)

tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
scroll.pack(side=tk.RIGHT, fill=tk.Y)

# Двойной клик по строке = та же кнопка "Открыть папку"
tree.bind("<Double-1>", lambda e: open_process_folder())

# ---------- Вкладка 4: Бесполезное ----------
tab_useless = ttk.Frame(notebook, padding=20)
notebook.add(tab_useless, text="Бесполезное")

ttk.Label(tab_useless, text="Бесполезные настройки", font=("Segoe UI", 12, "bold")).pack(anchor="w", pady=(0, 10))

btn_drag = ttk.Button(tab_useless, text="...", command=toggle_drag_windows)
btn_drag.pack(fill=tk.X, pady=4)

ttk.Label(
    tab_useless,
    text="(применится после перезагрузки)",
    font=("Segoe UI", 8, "italic"), foreground="gray"
).pack(anchor="w")

# ---------- Инициализация ----------
update_drag_button()
update_autostart_button()

root.mainloop()
