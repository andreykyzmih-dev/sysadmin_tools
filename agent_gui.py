#!/usr/bin/env python3
"""
agent_gui.py — GUI-панель для владельца компьютера (друга).

Запускает Remote Shell сервер и показывает:
- Кто подключён
- Все команды которые вводит администратор
- Кнопки: заблокировать / выгнать / остановить сервер
"""

import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext, simpledialog
import threading
import datetime
import sys
import os
import socket

# Импортируем серверную логику из remote_shell.py
sys.path.insert(0, os.path.dirname(__file__))
import remote_shell as rs

# Импортируем сервер трансляции (если доступен)
try:
    import screen_server as ss
    SCREEN_AVAILABLE = True
except ImportError:
    SCREEN_AVAILABLE = False


class AgentGUI:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("🖥️  Remote Shell — Панель управления")
        self.root.geometry("980x580")
        self.root.minsize(900, 500)
        self.root.configure(bg="#1e1e2e")

        self.server_thread = None
        self.is_running    = False
        self.connected_ip  = None

        self._build_ui()
        self._register_callback()

        # Автозапуск если передан пароль через аргументы
        if len(sys.argv) > 1:
            self._auto_start()

    # ── Построение интерфейса ────────────────────────────────────────────────

    def _build_ui(self):
        BG   = "#1e1e2e"
        BG2  = "#2a2a3e"
        FG   = "#cdd6f4"
        ACCENT = "#89b4fa"
        RED  = "#f38ba8"
        GREEN = "#a6e3a1"
        YELLOW = "#f9e2af"

        self.root.configure(bg=BG)

        # ── Заголовок ──
        hdr = tk.Frame(self.root, bg="#181825", pady=10)
        hdr.pack(fill=tk.X)
        tk.Label(hdr, text="🖥️  Remote Shell — Панель агента",
                 font=("Segoe UI", 14, "bold"), bg="#181825", fg=ACCENT).pack()
        tk.Label(hdr, text="Вы видите все действия администратора и можете контролировать доступ",
                 font=("Segoe UI", 9), bg="#181825", fg="#6c7086").pack()

        # ── Статус-панель ──
        status_frame = tk.Frame(self.root, bg=BG2, pady=8, padx=15)
        status_frame.pack(fill=tk.X, padx=10, pady=(8, 0))

        tk.Label(status_frame, text="Статус:", font=("Segoe UI", 10),
                 bg=BG2, fg=FG).grid(row=0, column=0, sticky="w")
        self.lbl_status = tk.Label(status_frame, text="⏸ Остановлен",
                                   font=("Segoe UI", 10, "bold"), bg=BG2, fg=YELLOW)
        self.lbl_status.grid(row=0, column=1, sticky="w", padx=8)

        tk.Label(status_frame, text="Подключён:", font=("Segoe UI", 10),
                 bg=BG2, fg=FG).grid(row=0, column=2, sticky="w", padx=(20, 0))
        self.lbl_client = tk.Label(status_frame, text="никто",
                                   font=("Segoe UI", 10, "bold"), bg=BG2, fg="#6c7086")
        self.lbl_client.grid(row=0, column=3, sticky="w", padx=8)

        tk.Label(status_frame, text="Мой IP:", font=("Segoe UI", 10),
                 bg=BG2, fg=FG).grid(row=0, column=4, sticky="w", padx=(20, 0))
        self.lbl_ip = tk.Label(status_frame, text=self._get_local_ip(),
                               font=("Segoe UI", 10, "bold"), bg=BG2, fg=ACCENT)
        self.lbl_ip.grid(row=0, column=5, sticky="w", padx=8)

        # ── Лог команд ──
        log_frame = tk.Frame(self.root, bg=BG)
        log_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=8)

        tk.Label(log_frame, text="📋 Журнал активности",
                 font=("Segoe UI", 10, "bold"), bg=BG, fg=ACCENT).pack(anchor="w")

        self.log_box = scrolledtext.ScrolledText(
            log_frame,
            font=("Consolas", 10),
            bg="#11111b", fg=FG,
            insertbackground=FG,
            selectbackground="#313244",
            relief=tk.FLAT, bd=0,
            state=tk.DISABLED,
            height=18,
        )
        self.log_box.pack(fill=tk.BOTH, expand=True, pady=(4, 0))

        # Теги цветов для лога
        self.log_box.tag_configure("time",    foreground="#6c7086")
        self.log_box.tag_configure("connect", foreground=GREEN)
        self.log_box.tag_configure("cmd",     foreground=FG)
        self.log_box.tag_configure("blocked", foreground=YELLOW)
        self.log_box.tag_configure("kick",    foreground=RED)
        self.log_box.tag_configure("info",    foreground=ACCENT)
        self.log_box.tag_configure("danger",  foreground=RED)
        self.log_box.tag_configure("server",  foreground="#cba6f7")

        # ── Панель кнопок управления ──
        btn_frame = tk.Frame(self.root, bg=BG, pady=8)
        btn_frame.pack(fill=tk.X, padx=10)

        btn_cfg = {"font": ("Segoe UI", 9), "relief": tk.FLAT,
                   "cursor": "hand2", "padx": 8, "pady": 6}

        self.btn_start = tk.Button(
            btn_frame, text="▶ Запустить",
            bg=GREEN, fg="#1e1e2e",
            command=self._start_server, **btn_cfg
        )
        self.btn_start.pack(side=tk.LEFT, padx=(0, 4))

        self.btn_block = tk.Button(
            btn_frame, text="🔒 Блокировать",
            bg=YELLOW, fg="#1e1e2e",
            command=self._toggle_block, **btn_cfg,
            state=tk.DISABLED
        )
        self.btn_block.pack(side=tk.LEFT, padx=4)

        self.btn_kick = tk.Button(
            btn_frame, text="⛔ Выгнать",
            bg=RED, fg="#1e1e2e",
            command=self._kick_client, **btn_cfg,
            state=tk.DISABLED
        )
        self.btn_kick.pack(side=tk.LEFT, padx=4)

        self.btn_stop = tk.Button(
            btn_frame, text="■ Стоп",
            bg="#45475a", fg=FG,
            command=self._stop_server, **btn_cfg,
            state=tk.DISABLED
        )
        self.btn_stop.pack(side=tk.LEFT, padx=4)

        self.btn_screen = tk.Button(
            btn_frame, text="🖥️ Трансляция",
            bg="#cba6f7", fg="#1e1e2e",
            command=self._toggle_screen, **btn_cfg,
            state=tk.DISABLED
        )
        self.btn_screen.pack(side=tk.LEFT, padx=4)

        tk.Button(
            btn_frame, text="🗑  Очистить лог",
            bg="#313244", fg=FG,
            command=self._clear_log, **btn_cfg
        ).pack(side=tk.RIGHT)

        # ── Строка подсказки ──
        hint = tk.Label(
            self.root,
            text="💡  Нажмите «Запустить сервер» — появится пароль и IP для администратора",
            font=("Segoe UI", 9), bg=BG, fg="#6c7086"
        )
        hint.pack(pady=(0, 6))
        self.hint_lbl = hint

    # ── Вспомогательные ─────────────────────────────────────────────────────

    def _get_local_ip(self) -> str:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except Exception:
            return "127.0.0.1"

    def _register_callback(self):
        """Регистрируем себя как получателя событий сервера."""
        rs._server_state["notify_cb"] = self._on_server_event

    def _log(self, text: str, tag: str = "info"):
        ts = datetime.datetime.now().strftime("%H:%M:%S")
        self.log_box.configure(state=tk.NORMAL)
        self.log_box.insert(tk.END, f"[{ts}] ", "time")
        self.log_box.insert(tk.END, text + "\n", tag)
        self.log_box.see(tk.END)
        self.log_box.configure(state=tk.DISABLED)

    def _safe(self, fn):
        """Запустить fn в главном потоке Tk."""
        self.root.after(0, fn)

    # ── Callback от сервера (вызывается из потока) ───────────────────────────

    def _on_server_event(self, ev: dict):
        event = ev.get("event")

        if event == "connect":
            ip = ev.get("ip","?")
            self.connected_ip = ip
            self._safe(lambda: self._on_connect(ip))

        elif event == "auth_ok":
            ip = ev.get("ip","?")
            self._safe(lambda: self._log(f"✅ Аутентификация пройдена: {ip}", "connect"))

        elif event == "auth_fail":
            ip = ev.get("ip","?")
            self._safe(lambda: self._log(f"❌ Неверный пароль от {ip}", "danger"))

        elif event == "cmd":
            ip  = ev.get("ip","?")
            cmd = ev.get("cmd","")
            t   = ev.get("time","")
            self._safe(lambda: self._log(f"🖊  {ip} → {cmd}", "cmd"))

        elif event == "blocked_by_owner":
            cmd = ev.get("cmd","")
            self._safe(lambda: self._log(f"🔒 Заблокировано тобой: {cmd}", "blocked"))

        elif event == "blocked_danger":
            cmd = ev.get("cmd","")
            pat = ev.get("pattern","")
            self._safe(lambda: self._log(f"⚠️  Опасная команда заблокирована: {cmd}  (паттерн: {pat})", "danger"))

        elif event == "kicked":
            ip = ev.get("ip","?")
            self._safe(lambda: self._on_disconnect(ip, kicked=True))

        elif event == "disconnect":
            ip = ev.get("ip","?")
            self._safe(lambda: self._on_disconnect(ip))

    def _on_connect(self, ip: str):
        self.lbl_client.configure(text=ip, fg="#a6e3a1")
        self.btn_kick.configure(state=tk.NORMAL)
        self.btn_block.configure(state=tk.NORMAL)
        self._log(f"🔗 Подключился: {ip}", "connect")
        # Всплывающее уведомление
        self.root.bell()
        self.root.lift()
        self.root.attributes("-topmost", True)
        self.root.after(2000, lambda: self.root.attributes("-topmost", False))

    def _on_disconnect(self, ip: str, kicked=False):
        self.connected_ip = None
        self.lbl_client.configure(text="никто", fg="#6c7086")
        self.btn_kick.configure(state=tk.DISABLED)
        self.btn_block.configure(state=tk.DISABLED)
        if kicked:
            self._log(f"⛔ Клиент {ip} выгнан.", "kick")
        else:
            self._log(f"🔌 Клиент {ip} отключился.", "info")

    # ── Действия кнопок ──────────────────────────────────────────────────────

    def _start_server(self):
        password = simpledialog.askstring(
            "Пароль сервера",
            "Введите пароль для подключения администратора\n"
            "(минимум 4 символа, сообщите его администратору):",
            parent=self.root,
            show="*"
        )
        if not password:
            return
        if len(password) < 4:
            messagebox.showwarning("Слабый пароль", "Пароль должен быть не короче 4 символов.")
            return

        self._password = password  # сохраняем для screen_server
        port = rs.DEFAULT_PORT
        self.is_running = True

        self.server_thread = threading.Thread(
            target=rs.run_server,
            args=(port, password, True, True),
            daemon=True
        )
        self.server_thread.start()

        local_ip = self._get_local_ip()
        self.lbl_status.configure(text="▶ Запущен", fg="#a6e3a1")
        self.btn_start.configure(state=tk.DISABLED)
        self.btn_stop.configure(state=tk.NORMAL)
        self.btn_screen.configure(state=tk.NORMAL)
        self.hint_lbl.configure(
            text=f"📡  Скажи администратору: IP = {local_ip}  |  Порт = {port}  |  Пароль = {password}"
        )

        self._log(f"🚀 Сервер запущен. IP: {local_ip}:{port}", "server")
        self._log(f"🔑 Пароль: {password}", "server")
        self._log("⏳ Ожидание подключения...", "info")

        # Показываем пароль и IP во всплывающем окне
        messagebox.showinfo(
            "Сервер запущен!",
            f"Передай администратору эти данные:\n\n"
            f"  IP-адрес : {local_ip}\n"
            f"  Порт     : {port}\n"
            f"  Пароль   : {password}\n\n"
            f"Команда для подключения:\n"
            f"python remote_shell.py --client --host {local_ip} --password {password}"
        )

    def _toggle_screen(self):
        if not SCREEN_AVAILABLE:
            messagebox.showwarning(
                "Нет модуля",
                "Установи зависимости для трансляции экрана:\n\n"
                "pip install mss Pillow pynput"
            )
            return

        if not hasattr(self, "_screen_running") or not self._screen_running:
            # Запускаем трансляцию
            pw = getattr(self, "_password", "")
            if not pw:
                messagebox.showwarning("Нет пароля", "Сначала запусти основной сервер.")
                return
            self._screen_running = True
            ss._running = True
            self._screen_thread = threading.Thread(
                target=ss.run_screen_server,
                args=(9998, pw, self._on_server_event),
                daemon=True
            )
            self._screen_thread.start()
            self.btn_screen.configure(text="⏹  Остановить трансляцию", bg="#f38ba8")
            self._log("🖥️  Трансляция экрана запущена (порт 9998)", "server")
            local_ip = self._get_local_ip()
            messagebox.showinfo(
                "Трансляция запущена",
                f"Администратор подключается командой:\n\n"
                f"python screen_client.py --host {local_ip} --password ПАРОЛЬ"
            )
        else:
            # Останавливаем
            self._screen_running = False
            ss.stop_server()
            self.btn_screen.configure(text="🖥️  Трансляция экрана", bg="#cba6f7")
            self._log("⏹  Трансляция экрана остановлена.", "server")

    def _toggle_block(self):
        rs._server_state["blocked"] = not rs._server_state["blocked"]
        is_blocked = rs._server_state["blocked"]
        if is_blocked:
            self.btn_block.configure(text="🔓  Разблокировать команды", bg="#f38ba8")
            self._log("🔒 Выполнение команд ЗАБЛОКИРОВАНО.", "blocked")
        else:
            self.btn_block.configure(text="🔒  Заблокировать команды", bg="#f9e2af")
            self._log("🔓 Выполнение команд разблокировано.", "connect")

    def _kick_client(self):
        if not self.connected_ip:
            return
        if messagebox.askyesno("Выгнать клиента",
                               f"Выгнать {self.connected_ip}?"):
            rs._server_state["kick"] = True
            self._log(f"⛔ Команда выгнать {self.connected_ip} отправлена.", "kick")

    def _stop_server(self):
        if messagebox.askyesno("Остановить сервер",
                               "Остановить сервер? Текущее подключение будет разорвано."):
            rs._server_state["kick"] = True
            self.is_running = False
            self.lbl_status.configure(text="⏸ Остановлен", fg="#f9e2af")
            self.lbl_client.configure(text="никто", fg="#6c7086")
            self.btn_start.configure(state=tk.NORMAL)
            self.btn_stop.configure(state=tk.DISABLED)
            self.btn_kick.configure(state=tk.DISABLED)
            self.btn_block.configure(state=tk.DISABLED)
            self._log("■ Сервер остановлен.", "server")

    def _clear_log(self):
        self.log_box.configure(state=tk.NORMAL)
        self.log_box.delete("1.0", tk.END)
        self.log_box.configure(state=tk.DISABLED)

    def _auto_start(self):
        """Автостарт с паролем из аргументов командной строки (для install_agent.ps1)."""
        import argparse
        p = argparse.ArgumentParser()
        p.add_argument("--password", default="")
        args, _ = p.parse_known_args()
        if args.password:
            self.root.after(500, lambda: self._auto_start_with(args.password))

    def _auto_start_with(self, password: str):
        port     = rs.DEFAULT_PORT
        local_ip = self._get_local_ip()
        self.is_running = True
        threading.Thread(
            target=rs.run_server,
            args=(port, password, True, True),
            daemon=True
        ).start()
        self.lbl_status.configure(text="▶ Запущен", fg="#a6e3a1")
        self.btn_start.configure(state=tk.DISABLED)
        self.btn_stop.configure(state=tk.NORMAL)
        self.hint_lbl.configure(
            text=f"📡  IP = {local_ip}  |  Порт = {port}  |  Пароль = {password}"
        )
        self._log(f"🚀 Автозапуск. IP: {local_ip}:{port}", "server")


def main():
    root = tk.Tk()
    app  = AgentGUI(root)
    root.protocol("WM_DELETE_WINDOW", lambda: (
        messagebox.showwarning("Внимание", "Закрытие остановит сервер!"),
        root.destroy()
    ))
    root.mainloop()


if __name__ == "__main__":
    main()
