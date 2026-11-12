# ============================================================
#  Remote Shell Agent — Установщик
#
#  Одна команда для друга (вставить в PowerShell):
#
#  irm https://raw.githubusercontent.com/andreykyzmih-dev/sysadmin_tools/main/install_agent.ps1 | iex
#
# ============================================================

$ErrorActionPreference = "Stop"

$GITHUB_USER   = "andreykyzmih-dev"
$GITHUB_REPO   = "sysadmin_tools"
$GITHUB_BRANCH = "main"

$BASE_URL    = "https://raw.githubusercontent.com/$GITHUB_USER/$GITHUB_REPO/$GITHUB_BRANCH"
$INSTALL_DIR = "$env:LOCALAPPDATA\RemoteShellAgent"

# ── Поиск Python в системе ───────────────────────────────────────────────────
function Test-PythonWorks($exe) {
    # Проверяем что python реально запускается (не заглушка Microsoft Store)
    if (-not (Test-Path $exe)) { return $false }
    try {
        $out = & $exe --version 2>&1
        return ($out -match "Python 3")
    } catch {
        return $false
    }
}

function Find-Python {
    # 1. Стандартные папки установки (сначала — надёжнее чем PATH)
    $candidates = @(
        "$env:LOCALAPPDATA\Programs\Python\Python314\python.exe",
        "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe",
        "$env:LOCALAPPDATA\Programs\Python\Python311\python.exe",
        "$env:LOCALAPPDATA\Programs\Python\Python310\python.exe",
        "$env:LOCALAPPDATA\Programs\Python\Python39\python.exe",
        "C:\Python312\python.exe",
        "C:\Python311\python.exe",
        "C:\Python310\python.exe",
        "C:\Python39\python.exe"
    )
    foreach ($c in $candidates) {
        if (Test-PythonWorks $c) { return $c }
    }

    # 2. Через реестр
    $regPaths = @(
        "HKCU:\Software\Python\PythonCore",
        "HKLM:\Software\Python\PythonCore",
        "HKLM:\Software\Wow6432Node\Python\PythonCore"
    )
    foreach ($rp in $regPaths) {
        if (Test-Path $rp) {
            Get-ChildItem $rp | ForEach-Object {
                $installKey = Join-Path $_.PSPath "InstallPath"
                if (Test-Path $installKey) {
                    $dir = (Get-ItemProperty $installKey)."(default)"
                    if ($dir) {
                        $exe = Join-Path $dir "python.exe"
                        if (Test-PythonWorks $exe) { return $exe }
                    }
                }
            }
        }
    }

    # 3. В PATH — последним, чтобы не поймать заглушку Store
    $p = Get-Command python -ErrorAction SilentlyContinue
    if ($p -and (Test-PythonWorks $p.Source)) { return $p.Source }

    return $null
}

function Write-Step($msg) { Write-Host "`n  >> $msg" -ForegroundColor Cyan }
function Write-OK($msg)   { Write-Host "  [OK] $msg" -ForegroundColor Green }
function Write-Warn($msg) { Write-Host "  [!]  $msg" -ForegroundColor Yellow }
function Write-Err($msg)  { Write-Host "  [ERR] $msg" -ForegroundColor Red }

# ── Шапка ────────────────────────────────────────────────────────────────────
Clear-Host
Write-Host ""
Write-Host "  ╔══════════════════════════════════════════════════╗" -ForegroundColor Cyan
Write-Host "  ║      Remote Shell Agent — Установка             ║" -ForegroundColor Cyan
Write-Host "  ╠══════════════════════════════════════════════════╣" -ForegroundColor Cyan
Write-Host "  ║  Этот агент позволит администратору подключаться ║" -ForegroundColor White
Write-Host "  ║  к этому компьютеру через защищённый терминал.  ║" -ForegroundColor White
Write-Host "  ║  Вы будете видеть ВСЕ действия и сможете        ║" -ForegroundColor White
Write-Host "  ║  заблокировать доступ в любой момент.           ║" -ForegroundColor White
Write-Host "  ╚══════════════════════════════════════════════════╝" -ForegroundColor Cyan
Write-Host ""

# ── Согласие ─────────────────────────────────────────────────────────────────
Write-Host "  Установить Remote Shell Agent? (Y/N)" -ForegroundColor Yellow
$confirm = Read-Host "  Ваш выбор"
if ($confirm -notmatch "^[Yy]$") {
    Write-Host "  Отменено." -ForegroundColor Red
    exit 0
}

# ── Директория ───────────────────────────────────────────────────────────────
Write-Step "Создание папки: $INSTALL_DIR"
New-Item -ItemType Directory -Force -Path $INSTALL_DIR | Out-Null
Write-OK "Готово."

# ── Python ───────────────────────────────────────────────────────────────────
Write-Step "Поиск Python..."
$PY_EXE = Find-Python

if (-not $PY_EXE) {
    Write-Warn "Python не найден. Устанавливаем Python 3.12..."
    $installer = "$env:TEMP\python_installer.exe"
    $pyUrl = "https://www.python.org/ftp/python/3.12.10/python-3.12.10-amd64.exe"
    Write-Host "  Скачивание (~25 МБ)..." -ForegroundColor Gray
    try {
        Invoke-WebRequest -Uri $pyUrl -OutFile $installer -UseBasicParsing
        Write-Host "  Установка Python..." -ForegroundColor Gray
        Start-Process -FilePath $installer `
            -ArgumentList "/quiet InstallAllUsers=0 PrependPath=0 Include_launcher=1" `
            -Wait
        Remove-Item $installer -ErrorAction SilentlyContinue
        $PY_EXE = "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe"
        if (-not (Test-PythonWorks $PY_EXE)) {
            Write-Err "Python установлен но не запускается. Скачайте вручную: https://python.org/downloads"
            Read-Host "Нажмите Enter для выхода"
            exit 1
        }
        Write-OK "Python установлен: $PY_EXE"
    } catch {
        Write-Err "Не удалось установить Python: $_"
        Write-Host "  Скачайте вручную: https://python.org/downloads" -ForegroundColor Yellow
        Read-Host "  Нажмите Enter для выхода"
        exit 1
    }
} else {
    $ver = & $PY_EXE --version 2>&1
    Write-OK "Найден: $ver  ($PY_EXE)"
}

# ── psutil ───────────────────────────────────────────────────────────────────
Write-Step "Установка зависимостей..."
& $PY_EXE -m pip install psutil mss Pillow pynput --quiet --disable-pip-version-check
Write-OK "Зависимости установлены."

# ── Скачиваем скрипты с GitHub ───────────────────────────────────────────────
Write-Step "Скачивание файлов с GitHub..."
$files = @("remote_shell.py", "agent_gui.py", "screen_server.py")

foreach ($f in $files) {
    $url = "$BASE_URL/$f"
    $dst = "$INSTALL_DIR\$f"
    Write-Host "  Скачивание $f ..." -ForegroundColor Gray
    try {
        Invoke-WebRequest -Uri $url -OutFile $dst -UseBasicParsing
        Write-OK "Скачан: $f"
    } catch {
        Write-Err "Не удалось скачать $f : $_"
        Write-Host "  Убедись что файлы выложены на GitHub и ник/репо указаны верно в скрипте." -ForegroundColor Yellow
        Read-Host "  Нажмите Enter для выхода"
        exit 1
    }
}

# ── Пароль ───────────────────────────────────────────────────────────────────
Write-Host ""
Write-Host "  ══════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host "  Придумайте пароль для подключения администратора." -ForegroundColor White
Write-Host "  Сообщите этот пароль администратору." -ForegroundColor White
Write-Host "  ══════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host ""
$agentPass = Read-Host "  Пароль (минимум 4 символа)"
while ($agentPass.Length -lt 4) {
    Write-Warn "Слишком короткий. Минимум 4 символа."
    $agentPass = Read-Host "  Пароль"
}

# ── Ярлык на рабочем столе ───────────────────────────────────────────────────
Write-Step "Создание ярлыка на рабочем столе..."
try {
    $shortcutPath = "$env:USERPROFILE\Desktop\RemoteShell Agent.lnk"
    $wsh = New-Object -ComObject WScript.Shell
    $sc  = $wsh.CreateShortcut($shortcutPath)
    $sc.TargetPath       = [string]($PY_EXE | Select-Object -First 1)
    $sc.Arguments        = "`"$INSTALL_DIR\agent_gui.py`" --password `"$agentPass`""
    $sc.WorkingDirectory = [string]$INSTALL_DIR
    $sc.Description      = "Remote Shell Agent"
    $sc.Save()
    Write-OK "Ярлык создан."
} catch {
    Write-Warn "Не удалось создать ярлык: $_"
}

# ── Получаем IP ──────────────────────────────────────────────────────────────
try {
    $localIP = (Get-NetIPAddress -AddressFamily IPv4 | Where-Object {
        $_.InterfaceAlias -notmatch "Loopback" -and
        $_.IPAddress      -notmatch "^169"
    } | Sort-Object PrefixLength | Select-Object -First 1).IPAddress
} catch {
    $localIP = "127.0.0.1"
}

# ── Итог ─────────────────────────────────────────────────────────────────────
Write-Host ""
Write-Host "  ══════════════════════════════════════════════════" -ForegroundColor Green
Write-Host "  Установка завершена! Запускаем панель управления..." -ForegroundColor Green
Write-Host "  ══════════════════════════════════════════════════" -ForegroundColor Green
Write-Host ""
Write-Host "  Передай администратору эти данные:" -ForegroundColor White
Write-Host "    IP-адрес : $localIP" -ForegroundColor Cyan
Write-Host "    Порт     : 9999" -ForegroundColor Cyan
Write-Host "    Пароль   : $agentPass" -ForegroundColor Cyan
Write-Host ""

# ── Запуск GUI ───────────────────────────────────────────────────────────────
$pyExeStr = [string]($PY_EXE | Select-Object -First 1)
Start-Process -FilePath $pyExeStr `
    -ArgumentList "`"$INSTALL_DIR\agent_gui.py`" --password `"$agentPass`"" `
    -WorkingDirectory ([string]$INSTALL_DIR)
