"""
flask_app.py — Relay сервер для зберігання кодів підключення.
Розгортається на pythonanywhere.com (безкоштовно).

Ендпоінти:
  POST /register  — зареєструвати сесію, отримати код
  GET  /get?code= — отримати адресу за кодом
  POST /unregister — видалити сесію
  GET  /ping      — перевірка
"""

from flask import Flask, request, jsonify
import time
import random
import string
import threading

app = Flask(__name__)

# Зберігання сесій: { "482-156": {"host":..., "port":..., "screen_port":..., "ts":...} }
_sessions = {}
_lock = threading.Lock()
SESSION_TTL = 3600  # 1 година


def _cleanup():
    while True:
        time.sleep(120)
        now = time.time()
        with _lock:
            expired = [k for k, v in _sessions.items() if now - v["ts"] > SESSION_TTL]
            for k in expired:
                del _sessions[k]


threading.Thread(target=_cleanup, daemon=True).start()


def _gen_code() -> str:
    while True:
        d = "".join(random.choices(string.digits, k=6))
        code = f"{d[:3]}-{d[3:]}"
        if code not in _sessions:
            return code


@app.route("/ping")
def ping():
    return jsonify({"status": "ok", "sessions": len(_sessions)})


@app.route("/register", methods=["POST"])
def register():
    data = request.get_json(silent=True) or {}
    host = data.get("host", "")
    port = int(data.get("port", 9999))
    screen_port = int(data.get("screen_port", 9998))
    password = data.get("password", "")

    if not host:
        return jsonify({"error": "host обов'язковий"}), 400

    code = _gen_code()
    with _lock:
        _sessions[code] = {
            "host":        host,
            "port":        port,
            "screen_port": screen_port,
            "password":    password,
            "ts":          time.time(),
        }
    print(f"[relay] Нова сесія: {code} → {host}:{port}")
    return jsonify({"code": code})


@app.route("/get")
def get_session():
    code = request.args.get("code", "").strip()
    # Нормалізуємо
    clean = code.replace("-", "")
    if len(clean) == 6:
        code = f"{clean[:3]}-{clean[3:]}"

    with _lock:
        session = _sessions.get(code)

    if not session:
        return jsonify({"error": "Код не знайдено"}), 404

    return jsonify(session)


@app.route("/unregister", methods=["POST"])
def unregister():
    data = request.get_json(silent=True) or {}
    code = data.get("code", "")
    with _lock:
        _sessions.pop(code, None)
    return jsonify({"status": "ok"})


if __name__ == "__main__":
    app.run(debug=True)
