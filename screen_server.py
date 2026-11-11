#!/usr/bin/env python3
"""
screen_server.py — Сервер трансляции экрана.
Запускается на компьютере друга (агента).
Захватывает экран и принимает команды мыши/клавиатуры.

Запуск: python screen_server.py --password ПАРОЛЬ
"""

import socket
import threading
import struct
import time
import hashlib
import argparse
import sys
import io

try:
    import mss
    import mss.tools
except ImportError:
    print("[!] Установи mss: pip install mss")
    sys.exit(1)

try:
    from PIL import Image
except ImportError:
    print("[!] Установи Pillow: pip install Pillow")
    sys.exit(1)

try:
    import pynput.mouse as pmouse
    import pynput.keyboard as pkeyboard
except ImportError:
    print("[!] Установи pynput: pip install pynput")
    sys.exit(1)

DEFAULT_PORT  = 9998
QUALITY       = 30    # JPEG качество (1-95), меньше = быстрее
FPS           = 15    # кадров в секунду
ENCODING      = "utf-8"

# Глобальный флаг — владелец может остановить трансляцию
_running = True
_mouse_ctrl    = pmouse.Controller()
_keyboard_ctrl = pkeyboard.Controller()

# Специальные клавиши
SPECIAL_KEYS = {
    "enter":     pkeyboard.Key.enter,
    "escape":    pkeyboard.Key.esc,
    "backspace": pkeyboard.Key.backspace,
    "tab":       pkeyboard.Key.tab,
    "space":     pkeyboard.Key.space,
    "ctrl":      pkeyboard.Key.ctrl,
    "alt":       pkeyboard.Key.alt,
    "shift":     pkeyboard.Key.shift,
    "win":       pkeyboard.Key.cmd,
    "delete":    pkeyboard.Key.delete,
    "up":        pkeyboard.Key.up,
    "down":      pkeyboard.Key.down,
    "left":      pkeyboard.Key.left,
    "right":     pkeyboard.Key.right,
    "f1":        pkeyboard.Key.f1,
    "f2":        pkeyboard.Key.f2,
    "f3":        pkeyboard.Key.f3,
    "f4":        pkeyboard.Key.f4,
    "f5":        pkeyboard.Key.f5,
}


def hash_pw(pw: str) -> str:
    return hashlib.sha256(pw.encode()).hexdigest()


def send_msg(sock: socket.socket, data: bytes):
    """Отправляет сообщение с 4-байтовым заголовком длины."""
    length = struct.pack(">I", len(data))
    sock.sendall(length + data)


def recv_msg(sock: socket.socket) -> bytes | None:
    """Получает сообщение с 4-байтовым заголовком длины."""
    try:
        raw_len = _recv_exact(sock, 4)
        if not raw_len:
            return None
        length = struct.unpack(">I", raw_len)[0]
        if length > 10 * 1024 * 1024:  # защита от огромных пакетов
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


def capture_screen() -> bytes:
    """Захватывает экран и возвращает JPEG байты."""
    with mss.mss() as sct:
        monitor = sct.monitors[1]  # основной монитор
        screenshot = sct.grab(monitor)
        img = Image.frombytes("RGB", screenshot.size, screenshot.bgra, "raw", "BGRX")
        # Уменьшаем для скорости передачи
        w, h = img.size
        img = img.resize((w // 2, h // 2), Image.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=QUALITY)
        return buf.getvalue()


def handle_input(data: bytes, screen_w: int, screen_h: int):
    """Обрабатывает команду ввода от клиента."""
    try:
        msg = data.decode(ENCODING)
        parts = msg.split(":", 1)
        cmd = parts[0]
        args = parts[1] if len(parts) > 1 else ""

        if cmd == "MOUSE_MOVE":
            # args: "x,y" в процентах от размера экрана
            xp, yp = map(float, args.split(","))
            x = int(xp * screen_w)
            y = int(yp * screen_h)
            _mouse_ctrl.position = (x, y)

        elif cmd == "MOUSE_CLICK":
            # args: "left" или "right" или "double"
            btn = pmouse.Button.left if args == "left" else pmouse.Button.right
            if args == "double":
                _mouse_ctrl.click(pmouse.Button.left, 2)
            else:
                _mouse_ctrl.click(btn, 1)

        elif cmd == "MOUSE_DOWN":
            btn = pmouse.Button.left if args == "left" else pmouse.Button.right
            _mouse_ctrl.press(btn)

        elif cmd == "MOUSE_UP":
            btn = pmouse.Button.left if args == "left" else pmouse.Button.right
            _mouse_ctrl.release(btn)

        elif cmd == "MOUSE_SCROLL":
            dx, dy = map(int, args.split(","))
            _mouse_ctrl.scroll(dx, dy)

        elif cmd == "KEY_PRESS":
            key = args.lower()
            if key in SPECIAL_KEYS:
                _keyboard_ctrl.press(SPECIAL_KEYS[key])
                _keyboard_ctrl.release(SPECIAL_KEYS[key])
            elif len(key) == 1:
                _keyboard_ctrl.press(key)
                _keyboard_ctrl.release(key)

        elif cmd == "KEY_TYPE":
            # Ввод текста
            _keyboard_ctrl.type(args)

        elif cmd == "KEY_COMBO":
            # Комбинация клавиш: "ctrl+c", "ctrl+v" и т.д.
            keys = args.lower().split("+")
            pressed = []
            for k in keys:
                if k in SPECIAL_KEYS:
                    _keyboard_ctrl.press(SPECIAL_KEYS[k])
                    pressed.append(SPECIAL_KEYS[k])
                elif len(k) == 1:
                    _keyboard_ctrl.press(k)
                    pressed.append(k)
            for k in reversed(pressed):
                _keyboard_ctrl.release(k)

    except Exception as e:
        pass  # Игнорируем ошибки ввода


def handle_client(conn: socket.socket, addr: tuple, pw_hash: str, notify_cb=None):
    global _running
    ip = addr[0]
    print(f"[screen] Подключение от {ip}")

    if notify_cb:
        notify_cb({"event": "screen_connect", "ip": ip})

    try:
        # Аутентификация
        send_msg(conn, b"AUTH")
        pw_data = recv_msg(conn)
        if not pw_data or hash_pw(pw_data.decode(ENCODING, errors="replace")) != pw_hash:
            send_msg(conn, b"AUTH_FAIL")
            print(f"[screen] Неверный пароль от {ip}")
            return
        send_msg(conn, b"AUTH_OK")
        print(f"[screen] Аутентификация OK: {ip}")

        # Получаем размер экрана для нормализации координат
        with mss.mss() as sct:
            mon = sct.monitors[1]
            screen_w = mon["width"]
            screen_h = mon["height"]

        # Отправляем размер экрана клиенту
        send_msg(conn, f"{screen_w},{screen_h}".encode())

        # Запускаем поток приёма команд ввода
        input_running = [True]

        def recv_input():
            while input_running[0] and _running:
                data = recv_msg(conn)
                if not data:
                    input_running[0] = False
                    break
                if data == b"STOP":
                    input_running[0] = False
                    break
                handle_input(data, screen_w, screen_h)

        t = threading.Thread(target=recv_input, daemon=True)
        t.start()

        # Основной цикл — отправляем кадры
        frame_time = 1.0 / FPS
        while input_running[0] and _running:
            start = time.time()
            try:
                frame = capture_screen()
                send_msg(conn, b"FRAME:" + frame)
            except Exception as e:
                print(f"[screen] Ошибка захвата: {e}")
                break
            elapsed = time.time() - start
            sleep_time = frame_time - elapsed
            if sleep_time > 0:
                time.sleep(sleep_time)

    except (ConnectionResetError, BrokenPipeError):
        print(f"[screen] {ip} отключился")
    except Exception as e:
        print(f"[screen] Ошибка: {e}")
    finally:
        conn.close()
        print(f"[screen] Соединение с {ip} закрыто")
        if notify_cb:
            notify_cb({"event": "screen_disconnect", "ip": ip})


def run_screen_server(port: int, password: str, notify_cb=None):
    global _running
    pw_hash = hash_pw(password)
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("0.0.0.0", port))
    srv.listen(3)
    srv.settimeout(1.0)
    print(f"[screen] Сервер трансляции запущен на порту {port}")

    while _running:
        try:
            conn, addr = srv.accept()
            t = threading.Thread(
                target=handle_client,
                args=(conn, addr, pw_hash, notify_cb),
                daemon=True
            )
            t.start()
        except socket.timeout:
            continue
        except Exception:
            break
    srv.close()
    print("[screen] Сервер остановлен")


def stop_server():
    global _running
    _running = False


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Сервер трансляции экрана")
    p.add_argument("--password", required=True)
    p.add_argument("--port", type=int, default=DEFAULT_PORT)
    args = p.parse_args()
    run_screen_server(args.port, args.password)
