#!/usr/bin/env python3
"""
ngrok_tunnel.py — Публічний туннель через localhost.run (SSH, без реєстрації).

Схема:
  ssh -R PORT:localhost:PORT nokey@localhost.run
  → отримуємо публічний адрес → зберігаємо на relay → повертаємо код
"""

import subprocess
import threading
import time
import json
import os
import re
import urllib.request
import urllib.error

RELAY_URL   = "https://sysadmin-tools.onrender.com"
SHELL_PORT  = 9999
SCREEN_PORT = 9998


# ── Relay сервер ──────────────────────────────────────────────────────────────

def _register(host: str, port: int, screen_port: int, password: str = "") -> str | None:
    """Зберігає сесію на relay і повертає код."""
    try:
        data = json.dumps({
            "host": host, "port": port,
            "screen_port": screen_port,
            "password": password
        }).encode()
        req = urllib.request.Request(
            f"{RELAY_URL}/register", data=data,
            headers={"Content-Type": "application/json"}, method="POST"
        )
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.loads(r.read()).get("code")
    except Exception as e:
        print(f"[relay] Помилка реєстрації: {e}")
        return None


def _unregister(code: str):
    try:
        data = json.dumps({"code": code}).encode()
        req = urllib.request.Request(
            f"{RELAY_URL}/unregister", data=data,
            headers={"Content-Type": "application/json"}, method="POST"
        )
        urllib.request.urlopen(req, timeout=5)
    except Exception:
        pass


def resolve_code(code: str) -> dict | None:
    """Отримує дані підключення за кодом."""
    code = code.strip().replace(" ", "")
    if len(code) == 6 and "-" not in code:
        code = f"{code[:3]}-{code[3:]}"
    try:
        with urllib.request.urlopen(f"{RELAY_URL}/get?code={code}", timeout=10) as r:
            return json.loads(r.read())
    except Exception as e:
        print(f"[relay] Помилка отримання: {e}")
        return None


# ── localhost.run туннель ─────────────────────────────────────────────────────

def _start_tunnel(port: int) -> tuple[subprocess.Popen, str] | tuple[None, None]:
    """
    Запускає SSH туннель через localhost.run.
    Повертає (процес, публічний_адрес) або (None, None).
    """
    try:
        proc = subprocess.Popen(
            ["ssh", "-o", "StrictHostKeyChecking=no",
             "-o", "ServerAliveInterval=30",
             "-R", f"0:localhost:{port}",
             "nokey@localhost.run"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1
        )

        # Читаємо вивід поки не знайдемо адрес
        public_addr = None
        deadline = time.time() + 30  # 30 секунд на з'єднання

        for line in proc.stdout:
            line = line.strip()
            print(f"[ssh] {line}")

            # localhost.run показує: "tunneled with tls termination, https://xxx.lhr.life"
            # або connection id рядок з портом
            match = re.search(r'(\d+\.\d+\.\d+\.\d+:\d+)', line)
            if match:
                public_addr = match.group(1)
                break

            # Альтернативний формат
            match2 = re.search(r'lhrtunnel\.link:(\d+)', line)
            if match2:
                public_addr = f"lhrtunnel.link:{match2.group(1)}"
                break

            match3 = re.search(r'your connection id is\s+([\d.]+:\d+)', line)
            if match3:
                public_addr = match3.group(1)
                break

            if time.time() > deadline:
                break

        return proc, public_addr

    except FileNotFoundError:
        print("[ssh] SSH не знайдено. Встановіть OpenSSH.")
        return None, None
    except Exception as e:
        print(f"[tunnel] Помилка: {e}")
        return None, None


# ── Сесія ─────────────────────────────────────────────────────────────────────

class NgrokSession:
    """Управляє туннелем і кодом підключення."""

    def __init__(self):
        self.proc  = None
        self.code  = None
        self.host  = None
        self.port  = None

    def start(self, shell_port=SHELL_PORT, screen_port=SCREEN_PORT, password="") -> str | None:
        """Запускає ОДИН туннель і повертає код підключення."""
        print("[tunnel] Запуск туннелю через localhost.run...")
        proc, addr = _start_tunnel(shell_port)

        if not proc or not addr:
            print("[tunnel] Не вдалось запустити туннель.")
            return None

        self.proc = proc

        # Парсимо host:port
        if ":" in addr:
            parts = addr.rsplit(":", 1)
            self.host = parts[0]
            self.port = int(parts[1])
        else:
            print(f"[tunnel] Невірний формат адреси: {addr}")
            self.stop()
            return None

        print(f"[tunnel] Публічний адрес: {self.host}:{self.port}")

        # Реєструємо на relay — screen_port = той самий публічний порт
        # (screen_server слухає локально на 9998, але через туннель досяжний через shell_port)
        print("[relay] Зберігаю код...")
        self.code = _register(self.host, self.port, self.port, password)
        if not self.code:
            print("[relay] Не вдалось зареєструвати код.")
            self.stop()
            return None

        print(f"[tunnel] ✅ Код підключення: {self.code}")
        return self.code

    def stop(self):
        if self.code:
            _unregister(self.code)
        if self.proc:
            try: self.proc.terminate()
            except Exception: pass
        if hasattr(self, "proc2") and self.proc2:
            try: self.proc2.terminate()
            except Exception: pass
        self.code = None
        self.proc = None
