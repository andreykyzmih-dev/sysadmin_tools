#!/usr/bin/env python3
"""
ngrok_tunnel.py — Публичный туннель через ngrok + хранение кода на paste.rs.

Друг нажимает "Создать код" → ngrok создаёт туннель → 
код сохраняется на paste.rs → ты вводишь код → подключаешься.

paste.rs — бесплатный анонимный сервис, без регистрации.
"""

import subprocess
import time
import json
import os
import urllib.request
import urllib.error
import random
import string
import zipfile

NGROK_TOKEN   = "3M1AGY5xoO5LvMdSQIzjMcjuVlj_85vSFUG61hNk8mF5fUD7i"
NGROK_API     = "http://localhost:4040/api/tunnels"
NGROK_ZIP_URL = "https://bin.equinox.io/c/bNyj1mQVY4c/ngrok-v3-stable-windows-amd64.zip"
NGROK_EXE     = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ngrok.exe")
RELAY_URL     = "https://sysadmin-tools.onrender.com"


# ── ngrok ─────────────────────────────────────────────────────────────────────

def _get_ngrok_exe() -> str:
    if os.path.exists(NGROK_EXE):
        return NGROK_EXE
    print("[ngrok] Скачиваю ngrok...")
    zip_path = os.path.join(os.path.dirname(NGROK_EXE), "ngrok.zip")
    urllib.request.urlretrieve(NGROK_ZIP_URL, zip_path)
    with zipfile.ZipFile(zip_path, "r") as z:
        z.extractall(os.path.dirname(NGROK_EXE))
    os.remove(zip_path)
    print("[ngrok] Готов.")
    return NGROK_EXE


def _configure_token():
    exe = _get_ngrok_exe()
    subprocess.run([exe, "config", "add-authtoken", NGROK_TOKEN],
                   capture_output=True)


def _start_ngrok(port: int) -> subprocess.Popen:
    exe = _get_ngrok_exe()
    _configure_token()
    return subprocess.Popen(
        [exe, "tcp", str(port)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def _get_public_url(retries=30) -> str | None:
    for i in range(retries):
        try:
            with urllib.request.urlopen(NGROK_API, timeout=5) as r:
                data = json.loads(r.read())
                for t in data.get("tunnels", []):
                    url = t.get("public_url", "")
                    if url.startswith("tcp://"):
                        return url
        except Exception:
            pass
        print(f"[ngrok] Очікування туннелю... ({i+1}/{retries})")
        time.sleep(2)
    return None


# ── Relay сервер ─────────────────────────────────────────────────────────────

def _save_to_relay(host: str, port: int, screen_port: int) -> str | None:
    """Зберігає дані на relay сервері і повертає код."""
    data = json.dumps({
        "host":        host,
        "port":        port,
        "screen_port": screen_port,
    }).encode("utf-8")
    try:
        req = urllib.request.Request(
            f"{RELAY_URL}/register",
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=10) as r:
            result = json.loads(r.read())
            return result.get("code")
    except Exception as e:
        print(f"[relay] Помилка збереження: {e}")
        return None


def resolve_code(code: str) -> dict | None:
    """Отримує дані підключення за кодом."""
    code = code.strip().replace(" ", "")
    if len(code) == 6 and "-" not in code:
        code = f"{code[:3]}-{code[3:]}"
    try:
        url = f"{RELAY_URL}/get?code={code}"
        with urllib.request.urlopen(url, timeout=10) as r:
            return json.loads(r.read())
    except Exception as e:
        print(f"[relay] Помилка отримання коду: {e}")
        return None


# ── Сессия ────────────────────────────────────────────────────────────────────

class NgrokSession:
    def __init__(self):
        self.proc       = None
        self.code       = None
        self.host       = None
        self.port       = None

    def start(self, shell_port=9999, screen_port=9998) -> str | None:
        """Запускает туннель и возвращает код подключения."""
        try:
            print("[ngrok] Запускаю туннель...")
            self.proc = _start_ngrok(shell_port)
            print("[ngrok] Очікую запуску ngrok (5 сек)...")
            time.sleep(5)

            url = _get_public_url()
            if not url:
                print("[ngrok] Не удалось получить URL туннеля.")
                self.stop()
                return None

            # Парсим tcp://X.tcp.ngrok.io:12345
            addr = url.replace("tcp://", "")
            self.host, port_str = addr.rsplit(":", 1)
            self.port = int(port_str)

            print(f"[ngrok] Туннель: {self.host}:{self.port}")

            # Зберігаємо на relay сервері
            print("[ngrok] Зберігаю код на relay сервері...")
            code = _save_to_relay(self.host, self.port, screen_port)
            if not code:
                self.stop()
                return None

            self.code = code
            print(f"[ngrok] Код подключения: {self.code}")
            return self.code

        except Exception as e:
            print(f"[ngrok] Ошибка: {e}")
            self.stop()
            return None

    def stop(self):
        if self.proc:
            self.proc.terminate()
        self.code = None
        self.proc = None
