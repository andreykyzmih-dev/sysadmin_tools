#!/usr/bin/env python3
"""
proxy_server.py — Мультиплексор на одному порті.
Перший байт від клієнта визначає тип з'єднання:
  b'S' → Remote Shell (порт 9999)
  b'V' → Screen Share (порт 9998)

Це дозволяє використовувати ОДИН публічний туннель для обох сервісів.
"""

import socket
import threading
import sys

PROXY_PORT  = 9999   # публічний порт (туннель)
SHELL_PORT  = 19999  # локальний порт shell сервера
SCREEN_PORT = 19998  # локальний порт screen сервера
BUFFER_SIZE = 65536


def forward(src: socket.socket, dst: socket.socket):
    """Пересилає дані між двома сокетами."""
    try:
        while True:
            data = src.recv(BUFFER_SIZE)
            if not data:
                break
            dst.sendall(data)
    except Exception:
        pass
    finally:
        try: src.close()
        except Exception: pass
        try: dst.close()
        except Exception: pass


def handle_client(conn: socket.socket, addr):
    """Читає перший байт і перенаправляє до потрібного сервісу."""
    try:
        # Читаємо перший байт — тип з'єднання
        first_byte = conn.recv(1)
        if not first_byte:
            conn.close()
            return

        if first_byte == b'V':
            target_port = SCREEN_PORT
        else:
            # За замовчуванням — shell
            target_port = SHELL_PORT

        # Підключаємось до локального сервісу
        target = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        target.connect(("127.0.0.1", target_port))

        # Пересилаємо перший байт далі (якщо потрібно)
        # Shell і screen сервери не очікують цього байту тому просто починаємо forwarding

        # Два потоки: client→target і target→client
        t1 = threading.Thread(target=forward, args=(conn, target), daemon=True)
        t2 = threading.Thread(target=forward, args=(target, conn), daemon=True)
        t1.start()
        t2.start()
        t1.join()

    except Exception as e:
        print(f"[proxy] Помилка: {e}")
        try: conn.close()
        except Exception: pass


def run_proxy(port=PROXY_PORT):
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("0.0.0.0", port))
    srv.listen(10)
    print(f"[proxy] Запущено на порту {port}")
    print(f"[proxy] Shell → 127.0.0.1:{SHELL_PORT}")
    print(f"[proxy] Screen → 127.0.0.1:{SCREEN_PORT}")

    try:
        while True:
            conn, addr = srv.accept()
            threading.Thread(target=handle_client, args=(conn, addr), daemon=True).start()
    except KeyboardInterrupt:
        pass
    finally:
        srv.close()


if __name__ == "__main__":
    run_proxy()
