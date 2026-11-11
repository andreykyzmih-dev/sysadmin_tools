--this is my script for my school project 
# SysAdmin Tools

Набор утилит для системного администрирования и удалённого управления компьютером.
Школьный проект — IT колледж iStep.

---

## Установка зависимостей

```powershell
pip install psutil mss Pillow pynput
```

---

## Файлы проекта

| Файл | Описание |
|------|----------|
| `sysinfo.py` | Информация о системе |
| `diskmon.py` | Мониторинг дисков |
| `logcheck.py` | Анализ лог-файлов |
| `netcheck.py` | Проверка сети |
| `useraudit.py` | Аудит пользователей |
| `extra_tools.py` | Процессы, службы, автозапуск и др. |
| `remote_shell.py` | Удалённый терминал (сервер + клиент) |
| `agent_gui.py` | GUI-панель агента (для друга) |
| `screen_server.py` | Сервер трансляции экрана |
| `screen_client.py` | Клиент просмотра экрана |
| `install_agent.ps1` | Установщик агента одной командой |
| `run.bat` | Меню запуска всех утилит |

---

## Быстрый запуск — `run.bat`

Просто дважды кликни на `run.bat` — появится меню со всеми утилитами.

---

## Утилиты мониторинга

### sysinfo.py — Информация о системе
```powershell
python sysinfo.py
```

### diskmon.py — Мониторинг дисков
```powershell
# Разовая проверка
python diskmon.py

# Порог предупреждения 75%, критичный 90%
python diskmon.py -t 75 -c 90

# Непрерывный мониторинг каждые 60 сек с логом
python diskmon.py -i 60 --log
```

### logcheck.py — Анализ логов
```powershell
# Анализ файла
python logcheck.py C:\путь\к\файлу.log

# Последние 500 строк
python logcheck.py -t 500 app.log

# Поиск по паттерну
python logcheck.py -p "connection refused" app.log

# Уровень: CRITICAL / ERROR / WARNING / INFO
python logcheck.py -l ERROR app.log
```

### netcheck.py — Проверка сети
```powershell
# Проверить хосты по умолчанию
python netcheck.py

# Проверить конкретные хосты (ping)
python netcheck.py 192.168.1.1 google.com

# Проверить порт
python netcheck.py -p 443 google.com github.com

# HTTP-проверка
python netcheck.py --http google.com
```

### useraudit.py — Аудит пользователей
```powershell
# Список пользователей и сессий
python useraudit.py

# + топ процессов по CPU и памяти
python useraudit.py -p
```

---

## Дополнительные утилиты — extra_tools.py

### Процессы
```powershell
# Список всех процессов
python extra_tools.py proc

# Фильтр по имени
python extra_tools.py proc -f chrome

# Завершить процесс по PID
python extra_tools.py proc -k 1234
```

### Службы Windows
```powershell
# Список всех служб
python extra_tools.py svc

# Фильтр
python extra_tools.py svc -f nginx

# Запустить / остановить службу
python extra_tools.py svc --start Spooler
python extra_tools.py svc --stop Spooler
```

### Автозапуск
```powershell
python extra_tools.py auto
```

### Планировщик задач
```powershell
python extra_tools.py tasks
python extra_tools.py tasks -f backup
```

### Очистка временных файлов
```powershell
# Просмотр (ничего не удаляет)
python extra_tools.py clean

# Реальное удаление
python extra_tools.py clean --do-clean
```

### Установленные программы
```powershell
python extra_tools.py apps
python extra_tools.py apps -f office
```

### Сетевые соединения
```powershell
python extra_tools.py conn
python extra_tools.py conn -p 443
```

### Журнал событий Windows
```powershell
python extra_tools.py events
python extra_tools.py events -l Application -n 30 --level Warning
```

---

## Удалённое управление

### Шаг 1 — Установка агента на компьютере друга

Друг вводит одну команду в PowerShell:
```powershell
irm https://raw.githubusercontent.com/andreykyzmih-dev/sysadmin_tools/main/install_agent.ps1 | iex
```

Скрипт автоматически:
- Устанавливает Python (если нет)
- Устанавливает все зависимости
- Скачивает файлы агента с GitHub
- Запускает GUI-панель управления
- Показывает IP и пароль для передачи администратору

### Шаг 2 — Подключение к терминалу (Remote Shell)

```powershell
python remote_shell.py --client --host IP_ДРУГА --password ПАРОЛЬ
```

Теперь можно вводить любые PowerShell команды на компьютере друга.

Встроенные команды клиента:

| Команда | Действие |
|---------|----------|
| `exit` | Завершить сессию |
| `cd путь` | Сменить директорию |
| `info` | CPU и RAM сервера |
| `who` | Кто подключён |

### Шаг 3 — Запуск сервера вручную (альтернатива GUI)

На компьютере друга:
```powershell
python remote_shell.py --server --password ПАРОЛЬ --no-dangerous --log
```

| Флаг | Описание |
|------|----------|
| `--password` | Пароль для подключения |
| `--port` | Порт (по умолчанию 9999) |
| `--no-dangerous` | Блокировать опасные команды |
| `--log` | Писать лог в `remote_shell.log` |

---

## Трансляция экрана

### На компьютере друга (агент)

Друг нажимает кнопку **"🖥️ Трансляция экрана"** в своём GUI.

Или вручную:
```powershell
python screen_server.py --password ПАРОЛЬ --port 9998
```

### У администратора (ты)

```powershell
python screen_client.py --host IP_ДРУГА --password ПАРОЛЬ
```

Откроется окно с экраном друга. Управление:

| Действие | Как |
|----------|-----|
| Движение мыши | Просто перемещай мышь в окне |
| Клик левой кнопкой | Левый клик в окне |
| Клик правой кнопкой | Правый клик в окне |
| Двойной клик | Двойной клик |
| Скролл | Колесо мыши |
| Клавиатура | Просто печатай |
| Ctrl+C / Ctrl+V | Работают напрямую |
| Кнопки в тулбаре | Ctrl+Alt+Del, Ctrl+C, Ctrl+V |
| Отключиться | Кнопка "⛔ Отключиться" |

Друг видит активную трансляцию в своём GUI и может остановить её кнопкой **"⏹ Остановить трансляцию"**.

---

## Порты

| Порт | Используется |
|------|-------------|
| 9999 | Remote Shell (терминал) |
| 9998 | Screen Share (трансляция экрана) |

---

## Требования

- Python 3.9+
- Windows 10/11 (Linux частично поддерживается)
- Оба компьютера в одной сети (или настроен проброс портов)

```
pip install psutil mss Pillow pynput
```
