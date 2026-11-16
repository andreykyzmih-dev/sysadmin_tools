# ============================================================
#  SysAdmin Tools — Встановлення клієнта (адміністратор)
#
#  Одна команда:
#  irm https://raw.githubusercontent.com/andreykyzmih-dev/sysadmin_tools/main/install_client.ps1 | iex
# ============================================================

$ErrorActionPreference = "Stop"
$GITHUB_USER   = "andreykyzmih-dev"
$GITHUB_REPO   = "sysadmin_tools"
$GITHUB_BRANCH = "main"
$BASE_URL      = "https://raw.githubusercontent.com/$GITHUB_USER/$GITHUB_REPO/$GITHUB_BRANCH"
$INSTALL_DIR   = "$env:LOCALAPPDATA\RemoteShellClient"

function Test-PythonWorks($exe) {
    if (-not (Test-Path $exe)) { return $false }
    try { $out = & $exe --version 2>&1; return ($out -match "Python 3") } catch { return $false }
}

function Find-Python312 {
    $candidates = @(
        "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe",
        "C:\Python312\python.exe"
    )
    foreach ($c in $candidates) { if (Test-PythonWorks $c) { return $c } }
    return $null
}

function Write-Step($msg) { Write-Host "`n  >> $msg" -ForegroundColor Cyan }
function Write-OK($msg)   { Write-Host "  [OK] $msg" -ForegroundColor Green }
function Write-Warn($msg) { Write-Host "  [!]  $msg" -ForegroundColor Yellow }
function Write-Err($msg)  { Write-Host "  [ERR] $msg" -ForegroundColor Red }

Clear-Host
Write-Host ""
Write-Host "  ╔══════════════════════════════════════════════════╗" -ForegroundColor Blue
Write-Host "  ║   SysAdmin Tools — Встановлення клієнта         ║" -ForegroundColor Blue
Write-Host "  ╠══════════════════════════════════════════════════╣" -ForegroundColor Blue
Write-Host "  ║  Цей клієнт дозволяє підключатись до агента,    ║" -ForegroundColor White
Write-Host "  ║  переглядати екран та керувати комп'ютером.     ║" -ForegroundColor White
Write-Host "  ╚══════════════════════════════════════════════════╝" -ForegroundColor Blue
Write-Host ""

Write-Host "  Встановити SysAdmin Tools Client? (Y/N)" -ForegroundColor Yellow
$confirm = Read-Host "  Ваш вибір"
if ($confirm -notmatch "^[Yy]$") { Write-Host "  Скасовано." -ForegroundColor Red; exit 0 }

# Директорія
Write-Step "Створення папки: $INSTALL_DIR"
New-Item -ItemType Directory -Force -Path $INSTALL_DIR | Out-Null
Write-OK "Готово."

# Python 3.12
Write-Step "Пошук Python 3.12..."
$PY_EXE = Find-Python312

if (-not $PY_EXE) {
    Write-Warn "Python 3.12 не знайдено. Встановлюємо..."
    $installer = "$env:TEMP\python312.exe"
    $pyUrl = "https://www.python.org/ftp/python/3.12.10/python-3.12.10-amd64.exe"
    Write-Host "  Завантаження (~25 МБ)..." -ForegroundColor Gray
    try {
        Invoke-WebRequest -Uri $pyUrl -OutFile $installer -UseBasicParsing
        Start-Process -FilePath $installer -ArgumentList "/quiet InstallAllUsers=0 PrependPath=0" -Wait
        Remove-Item $installer -ErrorAction SilentlyContinue
        $PY_EXE = "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe"
        Write-OK "Python 3.12 встановлено."
    } catch {
        Write-Err "Не вдалось встановити Python: $_"
        Read-Host "Натисніть Enter для виходу"; exit 1
    }
} else {
    $ver = & $PY_EXE --version 2>&1
    Write-OK "Знайдено: $ver"
}

$PY_EXE = [string]($PY_EXE | Select-Object -First 1)

# Залежності
Write-Step "Встановлення залежностей..."
& $PY_EXE -m pip install psutil mss Pillow pynput --quiet --disable-pip-version-check
Write-OK "Залежності встановлено."

# Завантаження файлів
Write-Step "Завантаження файлів з GitHub..."
$files = @("remote_shell.py", "screen_client.py", "connect.py", "ngrok_tunnel.py", "admin_gui.py")
foreach ($f in $files) {
    Write-Host "  Завантаження $f..." -ForegroundColor Gray
    try {
        Invoke-WebRequest -Uri "$BASE_URL/$f" -OutFile "$INSTALL_DIR\$f" -UseBasicParsing
        Write-OK "Завантажено: $f"
    } catch {
        Write-Warn "Не вдалось завантажити $f"
    }
}

# Ярлик на робочому столі
Write-Step "Створення ярлика на робочому столі..."
try {
    $wsh = New-Object -ComObject WScript.Shell
    $sc = $wsh.CreateShortcut("$env:USERPROFILE\Desktop\SysAdmin Client.lnk")
    $sc.TargetPath = $PY_EXE
    $sc.Arguments = "`"$INSTALL_DIR\admin_gui.py`""
    $sc.WorkingDirectory = [string]$INSTALL_DIR
    $sc.Description = "SysAdmin Tools Client"
    $sc.Save()
    Write-OK "Ярлик створено."
} catch {
    Write-Warn "Не вдалось створити ярлик: $_"
}

# Результат
Write-Host ""
Write-Host "  ══════════════════════════════════════════════════" -ForegroundColor Green
Write-Host "  Встановлення завершено!" -ForegroundColor Green
Write-Host "  ══════════════════════════════════════════════════" -ForegroundColor Green
Write-Host ""
Write-Host "  Як підключитись:" -ForegroundColor White
Write-Host "  1. Отримай код від друга (наприклад 482-156)" -ForegroundColor Gray
Write-Host "  2. Запусти:" -ForegroundColor Gray
Write-Host "     & `"$PY_EXE`" `"$INSTALL_DIR\connect.py`"" -ForegroundColor Cyan
Write-Host ""
Write-Host "  Запуск панелі адміністратора..." -ForegroundColor Green
Start-Process -FilePath $PY_EXE -ArgumentList "`"$INSTALL_DIR\admin_gui.py`"" -WorkingDirectory $INSTALL_DIR
