# start_agent.ps1 — Запускает агент + ngrok и показывает команду для администратора
# Запуск: powershell -ExecutionPolicy Bypass -File start_agent.ps1

$INSTALL_DIR  = "$env:LOCALAPPDATA\RemoteShellAgent"
$NGROK_EXE    = "$INSTALL_DIR\ngrok.exe"
$NGROK_TOKEN  = "3M1AGY5xoO5LvMdSQIzjMcjuVlj_85vSFUG61hNk8mF5fUD7i"
$SHELL_PORT   = 9999
$SCREEN_PORT  = 9998

# Находим Python
$PY_EXE = (Get-ChildItem "$env:LOCALAPPDATA\Programs\Python" -Filter "python.exe" -Recurse -ErrorAction SilentlyContinue | Select-Object -First 1).FullName
if (-not $PY_EXE) {
    Write-Host "[!] Python не найден!" -ForegroundColor Red
    pause; exit 1
}

# Скачиваем ngrok если нет
if (-not (Test-Path $NGROK_EXE)) {
    Write-Host ">> Скачиваю ngrok..." -ForegroundColor Cyan
    $zip = "$env:TEMP\ngrok.zip"
    Invoke-WebRequest "https://bin.equinox.io/c/bNyj1mQVY4c/ngrok-v3-stable-windows-amd64.zip" -OutFile $zip -UseBasicParsing
    Expand-Archive $zip -DestinationPath $INSTALL_DIR -Force
    Remove-Item $zip
    Write-Host "[OK] ngrok скачан." -ForegroundColor Green
}

# Настраиваем токен
Write-Host ">> Настройка ngrok..." -ForegroundColor Cyan
& $NGROK_EXE config add-authtoken $NGROK_TOKEN | Out-Null

# Запускаем Python агент в фоне
Write-Host ">> Запуск агента..." -ForegroundColor Cyan
$password = Read-Host "  Введи пароль для подключения"
Start-Process -FilePath ([string]$PY_EXE) `
    -ArgumentList "`"$INSTALL_DIR\agent_gui.py`" --password `"$password`"" `
    -WorkingDirectory $INSTALL_DIR

# Запускаем ngrok туннель для терминала
Write-Host ">> Запуск ngrok туннеля (порт $SHELL_PORT)..." -ForegroundColor Cyan
$ngrokProc = Start-Process -FilePath $NGROK_EXE `
    -ArgumentList "tcp $SHELL_PORT" `
    -PassThru -WindowStyle Hidden
Start-Sleep -Seconds 3

# Запускаем ngrok туннель для экрана
$ngrokProc2 = Start-Process -FilePath $NGROK_EXE `
    -ArgumentList "tcp $SCREEN_PORT" `
    -PassThru -WindowStyle Hidden
Start-Sleep -Seconds 2

# Получаем публичные адреса из ngrok API
Write-Host ">> Получаю публичные адреса..." -ForegroundColor Cyan
$tunnels = $null
for ($i = 0; $i -lt 10; $i++) {
    try {
        $resp = Invoke-RestMethod "http://localhost:4040/api/tunnels" -ErrorAction Stop
        $tunnels = $resp.tunnels
        if ($tunnels.Count -ge 1) { break }
    } catch {}
    Start-Sleep -Seconds 1
}

if (-not $tunnels) {
    Write-Host "[!] Не удалось получить адрес ngrok." -ForegroundColor Red
    pause; exit 1
}

# Парсим адреса
$shellAddr  = ($tunnels | Where-Object { $_.config.addr -match $SHELL_PORT }  | Select-Object -First 1).public_url
$screenAddr = ($tunnels | Where-Object { $_.config.addr -match $SCREEN_PORT } | Select-Object -First 1).public_url

if (-not $shellAddr) { $shellAddr = $tunnels[0].public_url }

$shellHost = $shellAddr -replace "tcp://", "" -replace ":.*", ""
$shellPort = ($shellAddr -split ":")[-1]

$screenHost = if ($screenAddr) { $screenAddr -replace "tcp://", "" -replace ":.*", "" } else { $shellHost }
$screenPort = if ($screenAddr) { ($screenAddr -split ":")[-1] } else { "" }

# Показываем команды для администратора
Clear-Host
Write-Host ""
Write-Host "  ╔══════════════════════════════════════════════════════════════╗" -ForegroundColor Green
Write-Host "  ║   Агент запущен! Передай администратору эти команды:        ║" -ForegroundColor Green
Write-Host "  ╠══════════════════════════════════════════════════════════════╣" -ForegroundColor Green
Write-Host ""
Write-Host "  Пароль: $password" -ForegroundColor Yellow
Write-Host ""
Write-Host "  [Терминал]:" -ForegroundColor Cyan
$cmd1 = "python `"$INSTALL_DIR\remote_shell.py`" --client --host $shellHost --port $shellPort --password $password"
Write-Host "  $cmd1" -ForegroundColor White
Write-Host ""
if ($screenPort) {
    Write-Host "  [Экран]:" -ForegroundColor Cyan
    $cmd2 = "python `"$INSTALL_DIR\screen_client.py`" --host $screenHost --port $screenPort --password $password"
    Write-Host "  $cmd2" -ForegroundColor White
    Write-Host ""
}
Write-Host "  ╚══════════════════════════════════════════════════════════════╝" -ForegroundColor Green
Write-Host ""
Write-Host "  Нажми Ctrl+C для остановки." -ForegroundColor Gray

# Ждём пока не нажмут Ctrl+C
try {
    while ($true) { Start-Sleep -Seconds 60 }
} finally {
    $ngrokProc.Kill()
    $ngrokProc2.Kill()
    Write-Host "Агент остановлен." -ForegroundColor Yellow
}
