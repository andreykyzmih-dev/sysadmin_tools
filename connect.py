#!/usr/bin/env python3
"""
connect.py — Подключение по коду (как в AnyDesk).

Использование:
  python connect.py                    # спросит код интерактивно
  python connect.py --code 482-156     # сразу подключиться
  python connect.py --code 482156 --screen  # подключиться к экрану
"""

import argparse
import sys
import os
import subprocess

sys.path.insert(0, os.path.dirname(__file__))

def find_python() -> str:
    import platform
    if platform.system().lower() == "windows":
        candidates = [
            os.path.join(os.environ.get("LOCALAPPDATA",""),
                         "Programs","Python","Python312","python.exe"),
            os.path.join(os.environ.get("LOCALAPPDATA",""),
                         "Programs","Python","Python314","python.exe"),
            os.path.join(os.environ.get("LOCALAPPDATA",""),
                         "Programs","Python","Python313","python.exe"),
        ]
        for c in candidates:
            if os.path.exists(c):
                return c
    return sys.executable


def main():
    p = argparse.ArgumentParser(description="Подключение по коду")
    p.add_argument("--code",     default="", help="Код подключения (например 482-156)")
    p.add_argument("--password", default="", help="Пароль (если не указан — спросит)")
    p.add_argument("--screen",   action="store_true", help="Подключиться к экрану")
    args = p.parse_args()

    print("\n" + "="*50)
    print("  Remote Shell — Подключение по коду")
    print("="*50)

    # Получаем код
    code = args.code.strip()
    if not code:
        print("\n  Введи код который показывает агент у друга.")
        code = input("  Код подключения: ").strip()

    if not code:
        print("  Код не введён.")
        sys.exit(1)

    # Нормализуем код
    clean = code.replace("-","").replace(" ","")
    if len(clean) == 6:
        code = f"{clean[:3]}-{clean[3:]}"

    print(f"\n  Поиск сессии по коду {code}...")

    # Получаем адрес с relay сервера
    try:
        import ngrok_tunnel as ng
        session = ng.resolve_code(code)
    except ImportError:
        print("  [!] ngrok_tunnel.py не найден.")
        sys.exit(1)

    if not session:
        print(f"\n  ❌ Код {code} не найден или устарел.")
        print("  Попроси друга создать новый код.")
        input("\n  Нажми Enter для выхода...")
        sys.exit(1)

    host        = session["host"]
    port        = session["port"]
    screen_port = session.get("screen_port", 9998)

    print(f"  ✅ Найдено: {host}:{port}")

    # Получаем пароль
    password = args.password
    if not password:
        import getpass
        password = getpass.getpass("  Пароль: ")

    py = find_python()
    script_dir = os.path.dirname(os.path.abspath(__file__))

    if args.screen:
        # Подключаемся к экрану
        script = os.path.join(script_dir, "screen_client.py")
        print(f"\n  Запуск просмотра экрана...")
        subprocess.run([py, script,
                        "--host", host,
                        "--port", str(screen_port),
                        "--password", password])
    else:
        # Показываем меню
        print(f"\n  Что хочешь сделать?")
        print(f"  [1] Подключиться к терминалу")
        print(f"  [2] Смотреть экран")
        print(f"  [3] Оба (терминал + экран)")
        choice = input("\n  Выбор (1/2/3): ").strip()

        shell_script  = os.path.join(script_dir, "remote_shell.py")
        screen_script = os.path.join(script_dir, "screen_client.py")

        if choice == "1" or choice == "":
            print("\n  Подключение к терминалу...")
            subprocess.run([py, shell_script,
                            "--client",
                            "--host", host,
                            "--port", str(port),
                            "--password", password])

        elif choice == "2":
            print("\n  Запуск просмотра экрана...")
            subprocess.run([py, screen_script,
                            "--host", host,
                            "--port", str(screen_port),
                            "--password", password])

        elif choice == "3":
            import threading
            print("\n  Запуск терминала и экрана...")
            t = threading.Thread(
                target=subprocess.run,
                args=([py, screen_script,
                       "--host", host,
                       "--port", str(screen_port),
                       "--password", password],),
                daemon=True
            )
            t.start()
            subprocess.run([py, shell_script,
                            "--client",
                            "--host", host,
                            "--port", str(port),
                            "--password", password])
        else:
            print("  Неверный выбор.")


if __name__ == "__main__":
    main()
