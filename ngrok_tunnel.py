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
PASTE_URL     = "https://paste.rs"


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


def _get_public_url(retries=15) -> str | None:
    for _ in range(retries):
        try:
            with urllib.request.urlopen(NGROK_API, timeout=3) as r:
                data = json.loads(r.read())
                for t in data.get("tunnels", []):
                    url = t.get("public_url", "")
                    if url.startswith("tcp://"):
                        return url
        except Exception:
            pass
        time.sleep(1)
    return None


# ── paste.rs хранилище кодов ──────────────────────────────────────────────────

def _save_to_paste(host: str, port: int, screen_port: int) -> str | None:
    """Сохраняет данные на paste.rs и возвращает ID (короткий код)."""
    data = json.dumps({
        "host":        host,
        "port":        port,
        "screen_port": screen_port,
    }).encode("utf-8")
    try:
        req = urllib.request.Request(
            PASTE_URL,
            data=data,
            headers={"Content-Type": "text/plain"},
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=10) as r:
            # paste.rs возвращает URL вида https://paste.rs/ABC
            result = r.read().decode("utf-8").strip()
            # Берём только ID — последняя часть URL
            paste_id = result.rstrip("/").split("/")[-1]
            return paste_id
    except Exception as e:
        print(f"[paste] Ошибка сохранения: {e}")
        return None


def resolve_code(code: str) -> dict | None:
    """Получает данные подключения по коду (paste ID)."""
    code = code.strip().replace(" ", "").replace("-", "")
    try:
        url = f"{PASTE_URL}/{code}"
        with urllib.request.urlopen(url, timeout=10) as r:
            data = json.loads(r.read().decode("utf-8"))
            return data
    except Exception as e:
        print(f"[paste] Ошибка получения кода: {e}")
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
            time.sleep(3)

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

            # Сохраняем на paste.rs
            print("[ngrok] Сохраняю код на paste.rs...")
            paste_id = _save_to_paste(self.host, self.port, screen_port)
            if not paste_id:
                self.stop()
                return None

            self.code = paste_id
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
