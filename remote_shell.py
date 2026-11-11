#!/usr/bin/env python3
"""
remote_shell.py — Удалённое управление компьютером.

Друг запускает: python remote_shell.py --server --password ПАРОЛЬ
Ты подключаешься: python remote_shell.py --client --host IP --password ПАРОЛЬ

Протокол: JSON-сообщения через TCP.
Каждое сообщение — {"type": "...", "data": "..."}
"""

import socket, threading, subprocess, platform, datetime
import argparse, hashlib, json, sys, os

DEFAULT_PORT  = 9999
BUFFER_SIZE   = 65536
ENCODING      = "utf-8"
LOG_FILE      = "remote_shell.log"
TIMEOUT_AUTH  = 30
TIMEOUT_CMD   = 60
IS_WINDOWS    = platform.system().lower() == "windows"

DANGEROUS_PATTERNS = [
    "format ", "mkfs", "dd if=",
    "del /s", "del /f", "rmdir /s",
    "rm -rf", "rm -r /",
    "reg delete", "net user /delete",
    "shutdown", "restart-computer", "stop-computer",
    "invoke-expression", "iex ",
]

# ── Глобальное состояние сервера ──────────────────────────────────────────────
# Сюда GUI агента может писать команды управления
_server_state = {
    "blocked":    False,   # True = все команды блокируются
    "kick":       False,   # True = выгнать текущего клиента
    "notify_cb":  None,    # callback(event_dict) для GUI
}

def notify(event: dict):
    """Отправить событие в GUI (если подключён)."""
    cb = _server_state.get("notify_cb")
    if cb:
        try:
            cb(event)
        except Exception:
            pass

# ── Утилиты ──────────────────────────────────────────────────────────────────

def hash_pw(pw: str) -> str:
    return hashlib.sha256(pw.encode()).hexdigest()

def log(msg: str, to_file=False):
    ts   = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    if to_file:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")

def danger_check(cmd: str):
    lo = cmd.lower()
    for p in DANGEROUS_PATTERNS:
        if p.lower() in lo:
            return p
    return None

def run_cmd(cmd: str) -> str:
    if not cmd.strip():
        return ""
    try:
        if IS_WINDOWS:
            r = subprocess.run(
                ["powershell", "-NoProfile", "-NonInteractive", "-Command", cmd],
                capture_output=True, text=True, timeout=TIMEOUT_CMD,
                encoding="utf-8", errors="replace"
            )
        else:
            r = subprocess.run(
                cmd, shell=True, capture_output=True, text=True,
                timeout=TIMEOUT_CMD, errors="replace"
            )
        out = r.stdout or ""
        if r.stderr:
            out += f"\n[stderr]\n{r.stderr}"
        return out or "(нет вывода)"
    except subprocess.TimeoutExpired:
        return f"[ТАЙМАУТ] Команда выполнялась дольше {TIMEOUT_CMD} сек."
    except Exception as e:
        return f"[ОШИБКА] {e}"

def get_prompt() -> str:
    user = os.getenv("USERNAME") or os.getenv("USER", "user")
    host = platform.node()
    cwd  = os.getcwd()
    if len(cwd) > 40:
        parts = cwd.split(os.sep)
        cwd = "..." + os.sep + os.sep.join(parts[-2:])
    return f"{user}@{host}:{cwd}$ "

# ── JSON-транспорт ────────────────────────────────────────────────────────────

def jsend(sock: socket.socket, msg_type: str, data: str):
    payload = json.dumps({"type": msg_type, "data": data}) + "\n"
    try:
        sock.sendall(payload.encode(ENCODING))
    except Exception:
        pass

def jrecv(sock: socket.socket) -> dict | None:
    buf = b""
    try:
        while True:
            chunk = sock.recv(BUFFER_SIZE)
            if not chunk:
                return None
            buf += chunk
            if b"\n" in buf:
                line, _ = buf.split(b"\n", 1)
                return json.loads(line.decode(ENCODING, errors="replace"))
    except Exception:
        return None

# ── Обработчик клиента (серверная сторона) ────────────────────────────────────

def handle_client(conn: socket.socket, addr: tuple,
                  pw_hash: str, block_danger: bool, do_log: bool):
    ip = addr[0]
    log(f"Подключение от {ip}", do_log)
    notify({"event": "connect", "ip": ip,
            "time": datetime.datetime.now().strftime("%H:%M:%S")})

    try:
        # Аутентификация
        jsend(conn, "auth_request", "Введите пароль:")
        conn.settimeout(TIMEOUT_AUTH)
        msg = jrecv(conn)
        conn.settimeout(None)

        if not msg or hash_pw(msg.get("data","")) != pw_hash:
            jsend(conn, "auth_fail", "Неверный пароль. Соединение закрыто.")
            log(f"[AUTH FAIL] {ip}", do_log)
            notify({"event": "auth_fail", "ip": ip})
            return

        jsend(conn, "auth_ok", "Аутентификация успешна!")
        log(f"[AUTH OK] {ip}", do_log)
        notify({"event": "auth_ok", "ip": ip})

        # Приветствие
        jsend(conn, "banner", (
            f"Добро пожаловать на {platform.node()}\n"
            f"ОС: {platform.system()} {platform.release()}\n"
            f"Время: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
            f"Владелец этого компьютера видит все ваши команды и может\n"
            f"заблокировать доступ в любой момент.\n"
        ))
        jsend(conn, "prompt", get_prompt())

        # Основной цикл
        while True:
            # Проверяем не выгнал ли нас хозяин
            if _server_state["kick"]:
                _server_state["kick"] = False
                jsend(conn, "kicked", "Владелец компьютера завершил сессию.")
                log(f"[KICKED] {ip}", do_log)
                notify({"event": "kicked", "ip": ip})
                break

            msg = jrecv(conn)
            if not msg:
                break

            cmd = msg.get("data", "").strip()
            if not cmd:
                jsend(conn, "prompt", get_prompt())
                continue

            log(f"[CMD] {ip}: {cmd}", do_log)
            notify({"event": "cmd", "ip": ip, "cmd": cmd,
                    "time": datetime.datetime.now().strftime("%H:%M:%S")})

            # Выход
            if cmd.lower() in ("exit", "quit"):
                jsend(conn, "bye", "Сессия завершена.")
                break

            # Владелец заблокировал все команды
            if _server_state["blocked"]:
                jsend(conn, "blocked", "Владелец временно заблокировал выполнение команд.")
                log(f"[BLOCKED by owner] {ip}: {cmd}", do_log)
                notify({"event": "blocked_by_owner", "cmd": cmd})
                jsend(conn, "prompt", get_prompt())
                continue

            # cd
            if cmd.lower().startswith("cd "):
                path = cmd[3:].strip().strip('"\'')
                try:
                    os.chdir(path)
                    jsend(conn, "output", f"Перешёл в: {os.getcwd()}")
                except (FileNotFoundError, PermissionError) as e:
                    jsend(conn, "output", f"[Ошибка] {e}")
                jsend(conn, "prompt", get_prompt())
                continue

            # Опасные команды
            if block_danger:
                d = danger_check(cmd)
                if d:
                    jsend(conn, "blocked",
                          f"Команда заблокирована (опасный паттерн: '{d}')")
                    log(f"[BLOCKED danger] {ip}: {cmd}", do_log)
                    notify({"event": "blocked_danger", "cmd": cmd, "pattern": d})
                    jsend(conn, "prompt", get_prompt())
                    continue

            # Выполнение
            output = run_cmd(cmd)
            jsend(conn, "output", output)
            jsend(conn, "prompt", get_prompt())

    except (ConnectionResetError, BrokenPipeError):
        log(f"Клиент {ip} отключился.", do_log)
    except Exception as e:
        log(f"[ERR] {ip}: {e}", do_log)
    finally:
        conn.close()
        log(f"Соединение с {ip} закрыто.", do_log)
        notify({"event": "disconnect", "ip": ip,
                "time": datetime.datetime.now().strftime("%H:%M:%S")})

# ── Сервер ────────────────────────────────────────────────────────────────────

def run_server(port, password, block_danger, do_log):
    pw_hash = hash_pw(password)
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        srv.bind(("0.0.0.0", port))
    except OSError as e:
        print(f"[ОШИБКА] Порт {port} занят: {e}")
        sys.exit(1)
    srv.listen(5)

    try:
        s2 = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s2.connect(("8.8.8.8", 80))
        local_ip = s2.getsockname()[0]
        s2.close()
    except Exception:
        local_ip = "127.0.0.1"

    print(f"{'='*52}")
    print(f"  Remote Shell Agent запущен")
    print(f"{'='*52}")
    print(f"  IP     : {local_ip}:{port}")
    print(f"  Пароль : {'установлен ✅' if password else '⚠ не задан!'}")
    print(f"  Защита : {'включена' if block_danger else 'выключена'}")
    print(f"\n  Команда для подключения:")
    print(f"  python remote_shell.py --client --host {local_ip} --password ПАРОЛЬ")
    print(f"{'='*52}\n")

    if do_log:
        log(f"Сервер запущен {local_ip}:{port}", do_log)

    try:
        while True:
            conn, addr = srv.accept()
            t = threading.Thread(
                target=handle_client,
                args=(conn, addr, pw_hash, block_danger, do_log),
                daemon=True
            )
            t.start()
    except KeyboardInterrupt:
        print("\nСервер остановлен.")
    finally:
        srv.close()

# ── Клиент ────────────────────────────────────────────────────────────────────

def run_client(host, port, password):
    print(f"Подключение к {host}:{port}...")
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(10)
        sock.connect((host, port))
        sock.settimeout(None)
    except Exception as e:
        print(f"[ОШИБКА] {e}")
        sys.exit(1)

    print("Подключено! Введи 'exit' для выхода.\n")

    def receive():
        while True:
            msg = jrecv(sock)
            if not msg:
                print("\n[Соединение закрыто]")
                os._exit(0)
            t = msg.get("type","")
            d = msg.get("data","")
            if t == "auth_request":
                pass  # обрабатывается ниже
            elif t == "prompt":
                print(f"\n{d}", end="", flush=True)
            elif t in ("auth_fail","kicked","bye"):
                print(f"\n{d}")
                os._exit(0)
            elif t == "blocked":
                print(f"\n[ЗАБЛОКИРОВАНО] {d}")
            else:
                print(f"\n{d}", end="")

    # Сначала авторизация
    msg = jrecv(sock)
    if msg and msg.get("type") == "auth_request":
        jsend(sock, "auth", password)

    t = threading.Thread(target=receive, daemon=True)
    t.start()

    try:
        while True:
            cmd = input()
            jsend(sock, "cmd", cmd)
            if cmd.lower() in ("exit","quit"):
                break
    except (KeyboardInterrupt, EOFError):
        pass
    finally:
        sock.close()

# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    p = argparse.ArgumentParser(description="Remote Shell")
    m = p.add_mutually_exclusive_group(required=True)
    m.add_argument("--server", action="store_true")
    m.add_argument("--client", action="store_true")
    p.add_argument("--host",         default="127.0.0.1")
    p.add_argument("--port",   type=int, default=DEFAULT_PORT)
    p.add_argument("--password",     default="")
    p.add_argument("--log",    action="store_true")
    p.add_argument("--no-dangerous", action="store_true")
    args = p.parse_args()

    if args.server:
        run_server(args.port, args.password, args.no_dangerous, args.log)
    else:
        run_client(args.host, args.port, args.password)

if __name__ == "__main__":
    main()
