#!/usr/bin/env python3
"""
ngrok_tunnel.py — Создаёт публичный туннель через ngrok и регистрирует код.

Используется agent_gui.py для создания публичного адреса.
"""

import subprocess
import threading
import time
import json
import sys
import os
import urllib.request
import urllib.error

NGROK_API      = "http://localhost:4040/api/tunnels"
NGROK_DOWNLOAD = "https://bin.equinox.io/c/bNyj1mQVY4c/ngrok-v3-stable-windows-amd64.zip"
NGROK_EXE      = os.path.join(os.path.dirname(__file__), "ngrok.exe")

# Relay сервер — публичный адрес где хранятся коды
# Используем бесплатный pythonanywhere или свой VPS
# Пока используем локальный для тестирования
RELAY_URL = "https://andreykyzmih.pythonanywhere.com"


def download_ngrok() -> bool:
    """Скачивает ngrok если не установлен."""
    if os.path.exists(NGROK_EXE):
        return True
    print("[ngrok] Скачиваю ngrok...")
    try:
        import zipfile
        import io
        zip_path = os.path.join(os.path.dirname(__file__), "ngrok.zip")
        urllib.request.urlretrieve(NGROK_DOWNLOAD, zip_path)
        with zipfile.ZipFile(zip_path, "r") as z:
            z.extractall(os.path.dirname(__file__))
        os.remove(zip_path)
        print("[ngrok] ngrok скачан.")
        return True
    except Exception as e:
        print(f"[ngrok] Ошибка скачивания: {e}")
        return False


def start_ngrok(port: int) -> subprocess.Popen | None:
    """Запускает ngrok туннель для порта."""
    if not os.path.exists(NGROK_EXE):
        if not download_ngrok():
            return None
    try:
        proc = subprocess.Popen(
            [NGROK_EXE, "tcp", str(port)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        time.sleep(2)  # ждём пока ngrok поднимется
        return proc
    except Exception as e:
        print(f"[ngrok] Ошибка запуска: {e}")
        return None


def get_ngrok_url(port: int, retries: int = 10) -> str | None:
    """Получает публичный URL туннеля через ngrok API."""
    for i in range(retries):
        try:
            with urllib.request.urlopen(NGROK_API, timeout=3) as r:
                data = json.loads(r.read())
                for tunnel in data.get("tunnels", []):
                    addr = tunnel.get("public_url", "")
                    if addr.startswith("tcp://"):
                        return addr  # tcp://0.tcp.ngrok.io:12345
        except Exception:
            pass
        time.sleep(1)
    return None


def register_code(host: str, port: int, screen_port: int) -> str | None:
    """Регистрирует сессию на relay сервере и получает код."""
    try:
        payload = json.dumps({
            "host":        host,
            "port":        port,
            "screen_port": screen_port,
        }).encode("utf-8")
        req = urllib.request.Request(
            f"{RELAY_URL}/register",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=10) as r:
            data = json.loads(r.read())
            return data.get("code")
    except Exception as e:
        print(f"[relay] Ошибка регистрации: {e}")
        return None


def unregister_code(code: str):
    """Удаляет сессию с relay сервера."""
    try:
        payload = json.dumps({"code": code}).encode("utf-8")
        req = urllib.request.Request(
            f"{RELAY_URL}/unregister",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        urllib.request.urlopen(req, timeout=5)
    except Exception:
        pass


def resolve_code(code: str) -> dict | None:
    """Получает адрес подключения по коду."""
    code = code.strip().replace(" ", "")
    # Добавляем дефис если нет
    if len(code) == 6 and "-" not in code:
        code = f"{code[:3]}-{code[3:]}"
    try:
        url = f"{RELAY_URL}/get?code={code}"
        with urllib.request.urlopen(url, timeout=10) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise
    except Exception as e:
        print(f"[relay] Ошибка получения кода: {e}")
        return None


class NgrokSession:
    """Управляет ngrok туннелем и кодом подключения."""

    def __init__(self):
        self.proc_shell  = None  # ngrok для Remote Shell (9999)
        self.proc_screen = None  # ngrok для Screen Share (9998)
        self.code        = None
        self.shell_host  = None
        self.shell_port  = None
        self.screen_port = None

    def start(self, shell_port=9999, screen_port=9998) -> str | None:
        """Запускает туннели и регистрирует код. Возвращает код."""
        print("[ngrok] Запуск туннеля для терминала...")
        self.proc_shell = start_ngrok(shell_port)
        if not self.proc_shell:
            return None

        url = get_ngrok_url(shell_port)
        if not url:
            print("[ngrok] Не удалось получить URL туннеля.")
            return None

        # Парсим tcp://0.tcp.ngrok.io:12345
        addr = url.replace("tcp://", "")
        host, port_str = addr.rsplit(":", 1)
        self.shell_host = host
        self.shell_port = int(port_str)

        print(f"[ngrok] Туннель: {host}:{self.shell_port}")

        # Регистрируем на relay
        self.code = register_code(host, self.shell_port, screen_port)
        if not self.code:
            print("[ngrok] Не удалось зарегистрировать код на relay сервере.")
            # Работаем без relay — показываем адрес напрямую
            return None

        print(f"[ngrok] Код подключения: {self.code}")
        return self.code

    def stop(self):
        """Останавливает туннели и удаляет код."""
        if self.code:
            unregister_code(self.code)
        if self.proc_shell:
            self.proc_shell.terminate()
        if self.proc_screen:
            self.proc_screen.terminate()
        self.code = None
