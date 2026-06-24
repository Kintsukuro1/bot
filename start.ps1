# Script para iniciar el bot desde PowerShell
Write-Host "Iniciando bot de Discord..." -ForegroundColor Cyan

# Verificar si Python está instalado
if (!(Get-Command python -ErrorAction SilentlyContinue)) {
    Write-Host "ERROR: Python no está instalado o no se encuentra en el PATH" -ForegroundColor Red
    Write-Host "Descarga e instala Python desde: https://www.python.org/downloads/" -ForegroundColor Yellow
    exit 1
}

# Mostrar versión de Python
Write-Host "Usando:" -NoNewline
python --version

# Instalar dependencias si existe requirements.txt
if (Test-Path -Path "requirements.txt") {
    Write-Host "Verificando dependencias..." -ForegroundColor Cyan
    python -m pip install -r requirements.txt
} else {
    Write-Host "ADVERTENCIA: No se encontró requirements.txt. Iniciando sin instalar dependencias..." -ForegroundColor Yellow
}

# Iniciar el bot
try {
    Write-Host "`nIniciando bot de Discord..." -ForegroundColor Green
    python run_bot.py
}
catch {
    Write-Host "Error al iniciar el bot: $_" -ForegroundColor Red
}
