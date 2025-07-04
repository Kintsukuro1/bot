# Bot de Discord con funcionalidades múltiples

Este bot de Discord ofrece una variedad de comandos y funcionalidades, incluyendo un sistema de economía, casino, música y moderación.

## Requisitos previos

- Python 3.8 o superior
- Java 11 o superior (para el servidor de música Lavalink)
- SQL Server (para la base de datos)

## Instalación

1. Clona el repositorio o descarga los archivos del bot.
2. Instala las dependencias de Python:
   ```
   pip install -U discord.py wavelink pyodbc python-dotenv
   ```

## Configuración

1. Crea un archivo `.env` en la carpeta del proyecto con el siguiente contenido:
   ```
   DISCORD_TOKEN=tu_token_de_discord
   DISCORD_PREFIX=/
   DEBUG=True
   
   DB_SERVER=tu_servidor_sql
   DB_DATABASE=CasinoBot
   DB_USERNAME=tu_usuario
   DB_PASSWORD=tu_contraseña
   ```

2. Asegúrate de que el archivo `application.yml` en la carpeta `src/utils` esté configurado correctamente:
   ```yaml
   server:
     port: 2444
   lavalink:
     server:
       password: "youshallnotpass"
   ```

## Ejecución

### Método recomendado (Automático)

#### Para Windows

1. Ejecuta el script `start_bot.bat` para iniciar automáticamente el servidor Lavalink y luego el bot:
   ```
   start_bot.bat
   ```

## Solución de problemas

### El bot no se conecta a Discord

- Verifica que el token en el archivo `.env` sea válido y esté actualizado.
- Asegúrate de tener habilitados los Intents privilegiados (SERVER MEMBERS y MESSAGE CONTENT) en el [Portal de Desarrolladores de Discord](https://discord.com/developers/applications).


### Las funciones de música no funcionan

- Asegúrate de que el servidor Lavalink esté en ejecución.
- Verifica que el puerto configurado en `application.yml` coincida con el puerto al que se intenta conectar en `bot.py`.
- Comprueba que Java esté instalado y sea accesible desde la línea de comandos.

## Estructura del proyecto

- `src/` - Código fuente del bot
  - `commands/` - Comandos organizados por categorías
  - `utils/` - Utilidades y herramientas
  - `db.py` - Funciones de base de datos
  - `bot.py` - Archivo principal del bot
- `start_bot.bat` - Script para iniciar el bot y Lavalink automáticamente (Windows CMD)
- `stop_bot.bat` - Script para detener el bot y Lavalink (Windows CMD)
- `start_bot.ps1` - Script para iniciar el bot y Lavalink automáticamente (PowerShell)
- `stop_bot.ps1` - Script para detener el bot y Lavalink (PowerShell)
#
