#!/usr/bin/env python3
"""
admin_gui.py — GUI панель адміністратора.
Підключення до агента за кодом, термінал, перегляд екрана.
"""

import tkinter as tk
from tkinter import messagebox, scrolledtext
import threading
import subprocess
import datetime
import sys
import os
import socket
import json
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

RELAY_URL = "https://sysadmin-tools.onrender.com"
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))


def find_python() -> str:
    candidates = [
        os.path.join(os.environ.get("LOCALAPPDATA",""),
                     "Programs","Python","Python312","python.exe"),
        os.path.join(os.environ.get("LOCALAPPDATA",""),
                     "Programs","Python","Python313","python.exe"),
        os.path.join(os.environ.get("LOCALAPPDATA",""),
                     "Programs","Python","Python314","python.exe"),
    ]
    for c in candidates:
        if os.path.exists(c):
            return c
    return sys.executable


def resolve_code(code: str) -> dict | None:
    code = code.strip().replace(" ","")
    if len(code) == 6 and "-" not in code:
        code = f"{code[:3]}-{code[3:]}"
    try:
        with urllib.request.urlopen(
            f"{RELAY_URL}/get?code={code}", timeout=10
        ) as r:
            return json.loads(r.read())
    except Exception as e:
        return None


class AdminGUI:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("👨‍💻  SysAdmin Tools — Панель адміністратора")
        self.root.geometry("980x620")
        self.root.minsize(900, 550)
        self.root.configure(bg="#1e1e2e")

        self.session = None  # {"host":..., "port":..., "screen_port":...}
        self.password = ""
        self.terminal_proc = None

        self._build_ui()

    def _build_ui(self):
        BG     = "#1e1e2e"
        BG2    = "#181825"
        BG3    = "#313244"
        FG     = "#cdd6f4"
        ACCENT = "#89b4fa"
        GREEN  = "#a6e3a1"
        YELLOW = "#f9e2af"
        RED    = "#f38ba8"
        PURPLE = "#cba6f7"

        # ── Заголовок ──
        hdr = tk.Frame(self.root, bg=BG2, pady=10)
        hdr.pack(fill=tk.X)
        tk.Label(hdr, text="👨‍💻  SysAdmin Tools — Панель адміністратора",
                 font=("Segoe UI", 13, "bold"), bg=BG2, fg=ACCENT).pack()
        tk.Label(hdr, text="Підключайся до агента за кодом та керуй комп'ютером",
                 font=("Segoe UI", 9), bg=BG2, fg="#6c7086").pack()

        # ── Статус ──
        status_frame = tk.Frame(self.root, bg=BG3, pady=6, padx=15)
        status_frame.pack(fill=tk.X, padx=10, pady=(8,0))

        tk.Label(status_frame, text="Статус:", font=("Segoe UI",10),
                 bg=BG3, fg=FG).grid(row=0, column=0, sticky="w")
        self.lbl_status = tk.Label(status_frame, text="⏸ Не підключено",
                                   font=("Segoe UI",10,"bold"), bg=BG3, fg=YELLOW)
        self.lbl_status.grid(row=0, column=1, sticky="w", padx=8)

        tk.Label(status_frame, text="Агент:", font=("Segoe UI",10),
                 bg=BG3, fg=FG).grid(row=0, column=2, sticky="w", padx=(20,0))
        self.lbl_host = tk.Label(status_frame, text="—",
                                 font=("Segoe UI",10,"bold"), bg=BG3, fg="#6c7086")
        self.lbl_host.grid(row=0, column=3, sticky="w", padx=8)

        # ── Введення коду ──
        code_frame = tk.Frame(self.root, bg=BG, pady=10, padx=10)
        code_frame.pack(fill=tk.X)

        tk.Label(code_frame, text="Код підключення:",
                 font=("Segoe UI",10), bg=BG, fg=FG).pack(side=tk.LEFT, padx=(0,8))

        self.code_entry = tk.Entry(
            code_frame, font=("Consolas",18), width=9,
            bg=BG3, fg=YELLOW, insertbackground=FG,
            relief=tk.FLAT, justify=tk.CENTER
        )
        self.code_entry.pack(side=tk.LEFT, padx=(0,8))
        self.code_entry.bind("<Return>", lambda e: self._connect())
        # Автоформат XXX-XXX
        self.code_entry.bind("<KeyRelease>", self._format_code)

        tk.Button(
            code_frame, text="🔌 Підключитись",
            bg=GREEN, fg="#1e1e2e",
            font=("Segoe UI",10,"bold"), relief=tk.FLAT,
            padx=14, pady=6, cursor="hand2",
            command=self._connect
        ).pack(side=tk.LEFT, padx=(0,8))

        tk.Button(
            code_frame, text="✖ Відключитись",
            bg=BG3, fg=FG,
            font=("Segoe UI",10), relief=tk.FLAT,
            padx=14, pady=6, cursor="hand2",
            command=self._disconnect
        ).pack(side=tk.LEFT)

        # ── Кнопки дій ──
        btn_frame = tk.Frame(self.root, bg=BG, pady=4, padx=10)
        btn_frame.pack(fill=tk.X)

        btn_cfg = {"font":("Segoe UI",9,"bold"), "relief":tk.FLAT,
                   "cursor":"hand2", "padx":12, "pady":7}

        self.btn_terminal = tk.Button(
            btn_frame, text="💻 Термінал",
            bg=ACCENT, fg="#1e1e2e",
            command=self._open_terminal, **btn_cfg, state=tk.DISABLED
        )
        self.btn_terminal.pack(side=tk.LEFT, padx=(0,6))

        self.btn_screen = tk.Button(
            btn_frame, text="🖥️ Переглянути екран",
            bg=PURPLE, fg="#1e1e2e",
            command=self._open_screen, **btn_cfg, state=tk.DISABLED
        )
        self.btn_screen.pack(side=tk.LEFT, padx=6)

        self.btn_both = tk.Button(
            btn_frame, text="⚡ Термінал + Екран",
            bg=YELLOW, fg="#1e1e2e",
            command=self._open_both, **btn_cfg, state=tk.DISABLED
        )
        self.btn_both.pack(side=tk.LEFT, padx=6)

        tk.Button(
            btn_frame, text="🗑 Очистити лог",
            bg=BG3, fg=FG,
            command=self._clear_log, **btn_cfg
        ).pack(side=tk.RIGHT)

        # ── Лог ──
        log_frame = tk.Frame(self.root, bg=BG)
        log_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=8)

        tk.Label(log_frame, text="📋 Журнал активності",
                 font=("Segoe UI",10,"bold"), bg=BG, fg=ACCENT).pack(anchor="w")

        self.log_box = scrolledtext.ScrolledText(
            log_frame, font=("Consolas",10),
            bg="#11111b", fg=FG, insertbackground=FG,
            selectbackground=BG3, relief=tk.FLAT, bd=0,
            state=tk.DISABLED, height=16
        )
        self.log_box.pack(fill=tk.BOTH, expand=True, pady=(4,0))
        self.log_box.tag_configure("time",    foreground="#6c7086")
        self.log_box.tag_configure("ok",      foreground=GREEN)
        self.log_box.tag_configure("err",     foreground=RED)
        self.log_box.tag_configure("info",    foreground=ACCENT)
        self.log_box.tag_configure("warn",    foreground=YELLOW)
        self.log_box.tag_configure("action",  foreground=PURPLE)

        # ── Підказка ──
        tk.Label(self.root,
                 text="💡 Введи код від агента → натисни Підключитись → вибери дію",
                 font=("Segoe UI",9), bg=BG, fg="#6c7086").pack(pady=(0,6))

        self._log("Готово. Введи код підключення від друга.", "info")

    # ── Утиліти ──────────────────────────────────────────────────────────────

    def _log(self, text: str, tag: str = "info"):
        ts = datetime.datetime.now().strftime("%H:%M:%S")
        self.log_box.configure(state=tk.NORMAL)
        self.log_box.insert(tk.END, f"[{ts}] ", "time")
        self.log_box.insert(tk.END, text + "\n", tag)
        self.log_box.see(tk.END)
        self.log_box.configure(state=tk.DISABLED)

    def _format_code(self, e=None):
        v = self.code_entry.get().replace("-","").replace(" ","")
        v = "".join(c for c in v if c.isdigit())[:6]
        if len(v) > 3:
            v = v[:3] + "-" + v[3:]
        cur = self.code_entry.get()
        if cur != v:
            self.code_entry.delete(0, tk.END)
            self.code_entry.insert(0, v)

    def _set_connected(self, host: str, port: int):
        self.lbl_status.configure(text="✅ Підключено", fg="#a6e3a1")
        self.lbl_host.configure(text=f"{host}:{port}", fg="#a6e3a1")
        self.btn_terminal.configure(state=tk.NORMAL)
        self.btn_screen.configure(state=tk.NORMAL)
        self.btn_both.configure(state=tk.NORMAL)

    def _set_disconnected(self):
        self.session = None
        self.password = ""
        self.lbl_status.configure(text="⏸ Не підключено", fg="#f9e2af")
        self.lbl_host.configure(text="—", fg="#6c7086")
        self.btn_terminal.configure(state=tk.DISABLED)
        self.btn_screen.configure(state=tk.DISABLED)
        self.btn_both.configure(state=tk.DISABLED)

    # ── Підключення ──────────────────────────────────────────────────────────

    def _connect(self):
        code = self.code_entry.get().strip()
        if not code or len(code.replace("-","")) < 6:
            messagebox.showwarning("Код", "Введи 6-значний код підключення.")
            return

        self._log(f"🔍 Пошук сесії за кодом {code}...", "info")

        def do_resolve():
            session = resolve_code(code)
            if not session:
                self.root.after(0, lambda: self._log(
                    f"❌ Код {code} не знайдено або застарів.", "err"))
                return

            self.session  = session
            self.password = session.get("password", "")
            host = session["host"]
            port = session["port"]

            self.root.after(0, lambda: self._log(
                f"✅ Знайдено: {host}:{port}", "ok"))
            self.root.after(0, lambda: self._set_connected(host, port))

        threading.Thread(target=do_resolve, daemon=True).start()

    def _disconnect(self):
        self._set_disconnected()
        self._log("🔌 Відключено.", "warn")

    # ── Дії ──────────────────────────────────────────────────────────────────

    def _open_terminal(self):
        if not self.session:
            return
        self._log("💻 Відкриваю термінал...", "action")
        py   = find_python()
        host = self.session["host"]
        port = self.session["port"]
        script = os.path.join(SCRIPT_DIR, "remote_shell.py")
        subprocess.Popen([
            "powershell", "-NoExit", "-Command",
            f'& "{py}" "{script}" --client --host {host} --port {port} --password {self.password}'
        ])
        self._log(f"💻 Термінал запущено → {host}:{port}", "ok")

    def _open_screen(self):
        if not self.session:
            return
        self._log("🖥️ Відкриваю перегляд екрана...", "action")
        py          = find_python()
        host        = self.session["host"]
        screen_port = self.session.get("screen_port", 9998)
        script      = os.path.join(SCRIPT_DIR, "screen_client.py")
        subprocess.Popen([
            py, script,
            "--host", host,
            "--port", str(screen_port),
            "--password", self.password
        ])
        self._log(f"🖥️ Перегляд екрана запущено → {host}:{screen_port}", "ok")

    def _open_both(self):
        self._open_terminal()
        import time; time.sleep(0.5)
        self._open_screen()

    def _clear_log(self):
        self.log_box.configure(state=tk.NORMAL)
        self.log_box.delete("1.0", tk.END)
        self.log_box.configure(state=tk.DISABLED)


def main():
    root = tk.Tk()
    app = AdminGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
