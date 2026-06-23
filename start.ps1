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

# Instalar dependencias si es necesario
if (!(Test-Path -Path "requirements.txt")) {
    Write-Host "Creando archivo requirements.txt..." -ForegroundColor Yellow
    @"
discord.py>=2.0.0
wavelink==2.6.2
psycopg2-binary
python-dotenv
"@ | Out-File -FilePath "requirements.txt" -Encoding utf8
}

Write-Host "Verificando dependencias..." -ForegroundColor Cyan
python -m pip install -r requirements.txt

# Iniciar el bot
try {
    Write-Host "`nIniciando bot de Discord..." -ForegroundColor Green
    python run_bot.py
}
catch {
    Write-Host "Error al iniciar el bot: $_" -ForegroundColor Red
}
