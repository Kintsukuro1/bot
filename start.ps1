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
pyodbc
python-dotenv
"@ | Out-File -FilePath "requirements.txt" -Encoding utf8
}

Write-Host "Verificando dependencias..." -ForegroundColor Cyan
python -m pip install -r requirements.txt

# Verificar si Java está instalado (necesario para Lavalink)
Write-Host "Verificando Java..." -ForegroundColor Cyan
if (!(Get-Command java -ErrorAction SilentlyContinue)) {
    Write-Host "ADVERTENCIA: Java no está instalado o no se encuentra en el PATH" -ForegroundColor Yellow
    Write-Host "Las funciones de música no estarán disponibles sin Java 11 o superior." -ForegroundColor Yellow
    Write-Host "Descarga Java desde: https://adoptium.net/" -ForegroundColor Cyan
    
    $continuar = Read-Host "¿Continuar sin soporte de música? (s/n)"
    if ($continuar -ne "s") {
        exit
    }
}
else {
    Write-Host "Java detectado: " -NoNewline
    java -version
}

# Iniciar el bot (ahora con soporte para Lavalink)
try {
    Write-Host "`nIniciando bot con soporte de música..." -ForegroundColor Green
    python run_bot.py
}
catch {
    Write-Host "Error al iniciar el bot: $_" -ForegroundColor Red
}
