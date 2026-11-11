#!/usr/bin/env python3
"""
screen_client.py — Клиент просмотра экрана и удалённого управления.
Запускается у администратора (тебя).

Запуск: python screen_client.py --host IP --password ПАРОЛЬ
"""

import socket
import struct
import threading
import argparse
import sys
import io
import time
import tkinter as tk
from tkinter import messagebox, ttk

try:
    from PIL import Image, ImageTk
except ImportError:
    print("[!] Установи Pillow: pip install Pillow")
    sys.exit(1)

DEFAULT_PORT = 9998
ENCODING     = "utf-8"


def send_msg(sock: socket.socket, data: bytes):
    length = struct.pack(">I", len(data))
    sock.sendall(length + data)


def recv_msg(sock: socket.socket) -> bytes | None:
    try:
        raw_len = _recv_exact(sock, 4)
        if not raw_len:
            return None
        length = struct.unpack(">I", raw_len)[0]
        if length > 20 * 1024 * 1024:
            return None
        return _recv_exact(sock, length)
    except Exception:
        return None


def _recv_exact(sock: socket.socket, n: int) -> bytes | None:
    buf = b""
    while len(buf) < n:
        try:
            chunk = sock.recv(n - len(buf))
            if not chunk:
                return None
            buf += chunk
        except Exception:
            return None
    return buf


class ScreenViewer:
    def __init__(self, root: tk.Tk, host: str, port: int, password: str):
        self.root     = root
        self.host     = host
        self.port     = port
        self.password = password
        self.sock     = None
        self.running  = False
        self.screen_w = 1920
        self.screen_h = 1080
        self.scale_x  = 1.0
        self.scale_y  = 1.0
        self.dragging = False
        self.last_frame_time = 0
        self.fps_counter = 0
        self.fps_display = 0

        self._build_ui()
        self._connect()

    def _build_ui(self):
        self.root.title("🖥️  Удалённый рабочий стол")
        self.root.configure(bg="#1e1e2e")

        # Панель инструментов
        toolbar = tk.Frame(self.root, bg="#181825", pady=4)
        toolbar.pack(fill=tk.X)

        tk.Label(toolbar, text=f"  🖥️  {self.host}:{self.port}",
                 font=("Segoe UI", 10, "bold"), bg="#181825", fg="#89b4fa").pack(side=tk.LEFT)

        self.lbl_fps = tk.Label(toolbar, text="FPS: --",
                                font=("Segoe UI", 9), bg="#181825", fg="#6c7086")
        self.lbl_fps.pack(side=tk.LEFT, padx=20)

        self.lbl_status = tk.Label(toolbar, text="⏳ Подключение...",
                                   font=("Segoe UI", 9), bg="#181825", fg="#f9e2af")
        self.lbl_status.pack(side=tk.LEFT, padx=10)

        # Кнопки управления
        btn_cfg = {"font": ("Segoe UI", 9), "relief": tk.FLAT,
                   "cursor": "hand2", "padx": 10, "pady": 4}

        tk.Button(toolbar, text="Ctrl+Alt+Del",
                  bg="#313244", fg="#cdd6f4",
                  command=lambda: self._send_combo("ctrl+alt+delete"),
                  **btn_cfg).pack(side=tk.RIGHT, padx=2)

        tk.Button(toolbar, text="Ctrl+C",
                  bg="#313244", fg="#cdd6f4",
                  command=lambda: self._send_combo("ctrl+c"),
                  **btn_cfg).pack(side=tk.RIGHT, padx=2)

        tk.Button(toolbar, text="Ctrl+V",
                  bg="#313244", fg="#cdd6f4",
                  command=lambda: self._send_combo("ctrl+v"),
                  **btn_cfg).pack(side=tk.RIGHT, padx=2)

        tk.Button(toolbar, text="⛔ Отключиться",
                  bg="#f38ba8", fg="#1e1e2e",
                  command=self._disconnect,
                  **btn_cfg).pack(side=tk.RIGHT, padx=4)

        # Canvas для отображения экрана
        self.canvas = tk.Canvas(
            self.root, bg="#11111b",
            cursor="crosshair",
            highlightthickness=0
        )
        self.canvas.pack(fill=tk.BOTH, expand=True)

        # Статусная строка
        statusbar = tk.Frame(self.root, bg="#181825", pady=2)
        statusbar.pack(fill=tk.X, side=tk.BOTTOM)
        self.lbl_pos = tk.Label(statusbar, text="X: 0  Y: 0",
                                font=("Consolas", 9), bg="#181825", fg="#6c7086")
        self.lbl_pos.pack(side=tk.LEFT, padx=8)
        self.lbl_res = tk.Label(statusbar, text="",
                                font=("Consolas", 9), bg="#181825", fg="#6c7086")
        self.lbl_res.pack(side=tk.RIGHT, padx=8)

        # Привязка событий мыши
        self.canvas.bind("<Motion>",          self._on_mouse_move)
        self.canvas.bind("<ButtonPress-1>",   self._on_mouse_down_left)
        self.canvas.bind("<ButtonRelease-1>", self._on_mouse_up_left)
        self.canvas.bind("<ButtonPress-3>",   self._on_mouse_right)
        self.canvas.bind("<Double-Button-1>", self._on_double_click)
        self.canvas.bind("<MouseWheel>",      self._on_scroll)

        # Привязка клавиатуры
        self.root.bind("<Key>", self._on_key)
        self.root.bind("<Configure>", self._on_resize)

        self.root.geometry("1280x760")
        self.root.minsize(640, 400)

    def _connect(self):
        def do_connect():
            try:
                self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                self.sock.settimeout(10)
                self.sock.connect((self.host, self.port))
                self.sock.settimeout(None)

                # Аутентификация
                msg = recv_msg(self.sock)
                if not msg or msg != b"AUTH":
                    raise Exception("Ошибка протокола")

                send_msg(self.sock, self.password.encode(ENCODING))
                resp = recv_msg(self.sock)
                if resp != b"AUTH_OK":
                    raise Exception("Неверный пароль")

                # Получаем размер экрана
                size_data = recv_msg(self.sock)
                self.screen_w, self.screen_h = map(int, size_data.decode().split(","))

                self.running = True
                self.root.after(0, lambda: self._on_connected())

                # Запускаем приём кадров
                self._recv_frames()

            except Exception as e:
                self.root.after(0, lambda: self._on_error(str(e)))

        threading.Thread(target=do_connect, daemon=True).start()

    def _on_connected(self):
        self.lbl_status.configure(text="✅ Подключено", fg="#a6e3a1")
        self.lbl_res.configure(text=f"Экран: {self.screen_w}×{self.screen_h}")

    def _on_error(self, msg: str):
        self.lbl_status.configure(text=f"❌ {msg}", fg="#f38ba8")
        messagebox.showerror("Ошибка подключения", msg)

    def _recv_frames(self):
        """Принимает кадры и обновляет canvas."""
        while self.running:
            data = recv_msg(self.sock)
            if not data:
                self.running = False
                self.root.after(0, lambda: self.lbl_status.configure(
                    text="🔌 Соединение разорвано", fg="#f38ba8"))
                break

            if data.startswith(b"FRAME:"):
                frame_data = data[6:]
                try:
                    img = Image.open(io.BytesIO(frame_data))
                    self.root.after(0, lambda i=img: self._update_canvas(i))
                    # FPS
                    now = time.time()
                    self.fps_counter += 1
                    if now - self.last_frame_time >= 1.0:
                        self.fps_display = self.fps_counter
                        self.fps_counter = 0
                        self.last_frame_time = now
                        self.root.after(0, lambda fps=self.fps_display:
                                        self.lbl_fps.configure(text=f"FPS: {fps}"))
                except Exception:
                    pass

    def _update_canvas(self, img: Image.Image):
        """Обновляет картинку на canvas с масштабированием."""
        cw = self.canvas.winfo_width()
        ch = self.canvas.winfo_height()
        if cw < 10 or ch < 10:
            return

        # Масштабируем с сохранением пропорций
        img_ratio    = img.width / img.height
        canvas_ratio = cw / ch
        if img_ratio > canvas_ratio:
            new_w = cw
            new_h = int(cw / img_ratio)
        else:
            new_h = ch
            new_w = int(ch * img_ratio)

        img = img.resize((new_w, new_h), Image.LANCZOS)
        self.scale_x = self.screen_w / new_w
        self.scale_y = self.screen_h / new_h
        self._canvas_offset_x = (cw - new_w) // 2
        self._canvas_offset_y = (ch - new_h) // 2

        photo = ImageTk.PhotoImage(img)
        self.canvas.delete("all")
        self.canvas.create_image(
            self._canvas_offset_x, self._canvas_offset_y,
            anchor=tk.NW, image=photo
        )
        self.canvas._photo = photo  # предотвращаем GC

    def _canvas_to_screen(self, cx: int, cy: int):
        """Переводит координаты canvas в координаты экрана (0.0-1.0)."""
        ox = getattr(self, "_canvas_offset_x", 0)
        oy = getattr(self, "_canvas_offset_y", 0)
        rx = (cx - ox) * self.scale_x / self.screen_w
        ry = (cy - oy) * self.scale_y / self.screen_h
        rx = max(0.0, min(1.0, rx))
        ry = max(0.0, min(1.0, ry))
        return rx, ry

    def _send_input(self, data: str):
        if self.running and self.sock:
            try:
                send_msg(self.sock, data.encode(ENCODING))
            except Exception:
                pass

    def _send_combo(self, combo: str):
        self._send_input(f"KEY_COMBO:{combo}")

    # ── Обработчики мыши ────────────────────────────────────────────────────

    def _on_mouse_move(self, e):
        rx, ry = self._canvas_to_screen(e.x, e.y)
        # Показываем реальные координаты
        real_x = int(rx * self.screen_w)
        real_y = int(ry * self.screen_h)
        self.lbl_pos.configure(text=f"X: {real_x}  Y: {real_y}")
        self._send_input(f"MOUSE_MOVE:{rx:.4f},{ry:.4f}")

    def _on_mouse_down_left(self, e):
        rx, ry = self._canvas_to_screen(e.x, e.y)
        self._send_input(f"MOUSE_MOVE:{rx:.4f},{ry:.4f}")
        self._send_input("MOUSE_DOWN:left")
        self.dragging = True

    def _on_mouse_up_left(self, e):
        rx, ry = self._canvas_to_screen(e.x, e.y)
        self._send_input(f"MOUSE_MOVE:{rx:.4f},{ry:.4f}")
        self._send_input("MOUSE_UP:left")
        self.dragging = False

    def _on_mouse_right(self, e):
        rx, ry = self._canvas_to_screen(e.x, e.y)
        self._send_input(f"MOUSE_MOVE:{rx:.4f},{ry:.4f}")
        self._send_input("MOUSE_CLICK:right")

    def _on_double_click(self, e):
        rx, ry = self._canvas_to_screen(e.x, e.y)
        self._send_input(f"MOUSE_MOVE:{rx:.4f},{ry:.4f}")
        self._send_input("MOUSE_CLICK:double")

    def _on_scroll(self, e):
        dy = 1 if e.delta > 0 else -1
        self._send_input(f"MOUSE_SCROLL:0,{dy}")

    # ── Обработчик клавиатуры ───────────────────────────────────────────────

    def _on_key(self, e):
        # Не перехватываем системные shortcuts окна
        if e.state & 0x4:  # Ctrl зажат
            key = e.keysym.lower()
            if key in ("c","v","x","z","a","s"):
                self._send_combo(f"ctrl+{key}")
                return
        
        sym = e.keysym.lower()
        special_map = {
            "return": "enter", "escape": "escape",
            "backspace": "backspace", "tab": "tab",
            "space": "space", "delete": "delete",
            "up": "up", "down": "down",
            "left": "left", "right": "right",
            "f1":"f1","f2":"f2","f3":"f3","f4":"f4","f5":"f5",
        }
        if sym in special_map:
            self._send_input(f"KEY_PRESS:{special_map[sym]}")
        elif e.char and e.char.isprintable():
            self._send_input(f"KEY_TYPE:{e.char}")

    def _on_resize(self, e):
        pass  # canvas перерисуется при следующем кадре

    def _disconnect(self):
        self.running = False
        if self.sock:
            try:
                send_msg(self.sock, b"STOP")
                self.sock.close()
            except Exception:
                pass
        self.root.destroy()


def main():
    p = argparse.ArgumentParser(description="Клиент удалённого рабочего стола")
    p.add_argument("--host",     required=True, help="IP адрес сервера")
    p.add_argument("--port",     type=int, default=DEFAULT_PORT)
    p.add_argument("--password", required=True, help="Пароль")
    args = p.parse_args()

    root = tk.Tk()
    app  = ScreenViewer(root, args.host, args.port, args.password)
    root.mainloop()


if __name__ == "__main__":
    main()
