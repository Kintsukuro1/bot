import time
import discord
from discord.ext import commands
from discord import app_commands
import pyodbc
from typing import Optional

# Importación usando rutas absolutas
from src.db import ensure_user, conn_str

def init_energia_db():
    """Inicializar tabla de energía en SQL Server."""
    conn = pyodbc.connect(conn_str)
    cursor = conn.cursor()
    
    try:
        # Verificar si las columnas ya existen en la tabla Users
        cursor.execute("""
            SELECT COLUMN_NAME 
            FROM INFORMATION_SCHEMA.COLUMNS 
            WHERE TABLE_NAME = 'Users'
        """)
        columns = [row[0] for row in cursor.fetchall()]
        
        # Agregar columnas solo si no existen
        if 'Energia' not in columns:
            cursor.execute("ALTER TABLE Users ADD Energia INT DEFAULT 100")
            print("✅ Columna 'Energia' agregada")
            
        if 'UltimaRecarga' not in columns:
            cursor.execute("ALTER TABLE Users ADD UltimaRecarga BIGINT DEFAULT 0")
            print("✅ Columna 'UltimaRecarga' agregada")
            
        conn.commit()
        print("✅ Inicialización de energía completada")
            
    except pyodbc.Error as e:
        print(f"⚠️ Error en init_energia_db: {e}")
    
    # Inicializar energía para usuarios existentes que no la tengan
    try:
        tiempo_actual = int(time.time())
        cursor.execute("""
            UPDATE Users 
            SET Energia = 100, UltimaRecarga = ? 
            WHERE Energia IS NULL OR UltimaRecarga IS NULL
        """, (tiempo_actual,))
        
        affected = cursor.rowcount
        if affected > 0:
            print(f"✅ Energía inicializada para {affected} usuarios")
        
        conn.commit()
        
    except pyodbc.Error as e:
        print(f"⚠️ Error inicializando energía de usuarios: {e}")
    
    finally:
        conn.close()

def get_energia(user_id: int) -> int:
    """Obtener la energía actual del usuario, aplicando recarga automática."""
    conn = pyodbc.connect(conn_str)
    cursor = conn.cursor()
    
    try:
        # Obtener datos actuales del usuario
        cursor.execute("""
            SELECT Energia, UltimaRecarga 
            FROM Users 
            WHERE UserID = ?
        """, (user_id,))
        
        result = cursor.fetchone()
        
        if not result:
            # Usuario no existe, crearlo con energía completa
            ensure_user(user_id)  # No establecemos nombre para evitar sobrescribir
            tiempo_actual = int(time.time())
            cursor.execute("""
                UPDATE Users 
                SET Energia = 100, UltimaRecarga = ? 
                WHERE UserID = ?
            """, (tiempo_actual, user_id))
            conn.commit()
            return 100
        
        energia_actual, ultima_recarga = result
        
        # Si la energía es None, inicializar
        if energia_actual is None:
            energia_actual = 100
            ultima_recarga = int(time.time())
            cursor.execute("""
                UPDATE Users 
                SET Energia = ?, UltimaRecarga = ? 
                WHERE UserID = ?
            """, (energia_actual, ultima_recarga, user_id))
            conn.commit()
            return energia_actual
        
        # Si ultima_recarga es None, inicializar
        if ultima_recarga is None:
            ultima_recarga = int(time.time())
            cursor.execute("""
                UPDATE Users 
                SET UltimaRecarga = ? 
                WHERE UserID = ?
            """, (ultima_recarga, user_id))
            conn.commit()
            return energia_actual
        
        # Calcular recarga automática si no está al máximo
        if energia_actual < 100:
            tiempo_actual = int(time.time())
            tiempo_transcurrido = tiempo_actual - ultima_recarga
            
            # Recargar 1 punto cada 3 minutos (180 segundos)
            puntos_recarga = tiempo_transcurrido // 180
            
            if puntos_recarga > 0:
                nueva_energia = min(100, energia_actual + puntos_recarga)
                nuevo_tiempo_recarga = ultima_recarga + (puntos_recarga * 180)
                
                cursor.execute("""
                    UPDATE Users 
                    SET Energia = ?, UltimaRecarga = ? 
                    WHERE UserID = ?
                """, (nueva_energia, nuevo_tiempo_recarga, user_id))
                conn.commit()
                
                return nueva_energia
        
        return energia_actual
        
    except pyodbc.Error as e:
        print(f"Error en get_energia: {e}")
        return 100  # Valor por defecto en caso de error
    
    finally:
        conn.close()

def set_energia(user_id: int, nueva_energia: int):
    """Establecer la energía del usuario."""
    conn = pyodbc.connect(conn_str)
    cursor = conn.cursor()
    
    try:
        # Asegurar que el usuario existe
        ensure_user(user_id)  # No establecemos nombre para evitar sobrescribir
        
        # Validar rango de energía
        nueva_energia = max(0, min(100, nueva_energia))
        tiempo_actual = int(time.time())
        
        cursor.execute("""
            UPDATE Users 
            SET Energia = ?, UltimaRecarga = ? 
            WHERE UserID = ?
        """, (nueva_energia, tiempo_actual, user_id))
        
        conn.commit()
        
    except pyodbc.Error as e:
        print(f"Error en set_energia: {e}")
    
    finally:
        conn.close()

def tiempo_hasta_recarga_completa(user_id: int) -> int:
    """Calcular minutos hasta que la energía esté completamente recargada."""
    energia_actual = get_energia(user_id)
    
    if energia_actual >= 100:
        return 0
    
    puntos_faltantes = 100 - energia_actual
    # 1 punto cada 3 minutos
    minutos_faltantes = puntos_faltantes * 3
    
    return minutos_faltantes

def get_energia_info(user_id: int) -> dict:
    """Obtener información completa sobre la energía del usuario."""
    energia_actual = get_energia(user_id)
    tiempo_recarga = tiempo_hasta_recarga_completa(user_id)
    
    return {
        'energia_actual': energia_actual,
        'energia_maxima': 100,
        'tiempo_recarga_completa': tiempo_recarga,
        'porcentaje': energia_actual,
        'puede_trabajar': energia_actual >= 15  # Mínimo para el trabajo más barato
    }

def fix_timestamps_energia():
    """Arreglar timestamps de energía que puedan estar en el futuro o ser inválidos."""
    conn = pyodbc.connect(conn_str)
    cursor = conn.cursor()
    
    try:
        tiempo_actual = int(time.time())
        
        # Arreglar timestamps futuros o muy antiguos
        cursor.execute("""
            UPDATE Users 
            SET UltimaRecarga = ? 
            WHERE UltimaRecarga > ? OR UltimaRecarga < ?
        """, (tiempo_actual, tiempo_actual, tiempo_actual - 86400 * 30))  # 30 días atrás
        
        affected = cursor.rowcount
        conn.commit()
        
        print(f"✅ Timestamps arreglados para {affected} usuarios")
        
    except pyodbc.Error as e:
        print(f"❌ Error arreglando timestamps: {e}")
    
    finally:
        conn.close()

class Energia(commands.Cog):
    """Cog para comandos relacionados con energía."""
    
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="energia", description="Ver tu estado de energía actual")
    async def energia_command(self, interaction: discord.Interaction):
        """Comando para mostrar la energía del usuario."""
        user_id = interaction.user.id
        
        # Asegurar que el usuario existe
        ensure_user(user_id, interaction.user.name)
        
        # Obtener información de energía
        info = get_energia_info(user_id)
        
        # Crear barra de energía visual
        porcentaje = info['energia_actual'] / 100
        barra_energia = '🟩' * int(porcentaje * 10) + '⬜' * (10 - int(porcentaje * 10))
        
        # Información de recarga
        if info['tiempo_recarga_completa'] > 0:
            horas = info['tiempo_recarga_completa'] // 60
            minutos = info['tiempo_recarga_completa'] % 60
            tiempo_texto = f"{horas}h {minutos}m" if horas > 0 else f"{minutos}m"
            recarga_info = f"⏱️ **Recarga completa en:** {tiempo_texto}"
        else:
            recarga_info = "✅ **¡Energía al máximo!**"
        
        # Determinar color del embed
        if info['energia_actual'] > 70:
            color = discord.Color.green()
        elif info['energia_actual'] > 30:
            color = discord.Color.yellow()
        else:
            color = discord.Color.red()
        
        embed = discord.Embed(
            title="⚡ Estado de Energía",
            description=(
                f"🔋 **Energía actual:** {info['energia_actual']}/100\n"
                f"📊 {barra_energia} {info['energia_actual']}%\n\n"
                f"{recarga_info}\n"
                f"💡 *Recuperas 1 punto cada 3 minutos*"
            ),
            color=color
        )
        
        # Información sobre trabajos disponibles
        trabajos_disponibles = []
        if info['energia_actual'] >= 30:
            trabajos_disponibles.append("🔧 Mecánico (30)")
        if info['energia_actual'] >= 25:
            trabajos_disponibles.append("💻 Hacker (25)")
        if info['energia_actual'] >= 20:
            trabajos_disponibles.append("👨‍🍳 Chef (20)")
        if info['energia_actual'] >= 15:
            trabajos_disponibles.append("🎨 Artista (15)")
        
        if trabajos_disponibles:
            embed.add_field(
                name="🎯 Trabajos Disponibles",
                value="\n".join(trabajos_disponibles),
                inline=False
            )
        else:
            embed.add_field(
                name="😴 Necesitas Descansar",
                value="Espera a que tu energía se recargue para trabajar",
                inline=False
            )
        
        embed.set_footer(text="Usa /trabajo para empezar a trabajar")
        
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="energia_debug", description="Información de debug del sistema de energía")
    @app_commands.default_permissions(administrator=True)
    async def energia_debug(self, interaction: discord.Interaction, usuario: Optional[discord.Member] = None):
        """Comando de debug para administradores."""
        target_user = usuario or interaction.user
        user_id = target_user.id
        
        conn = pyodbc.connect(conn_str)
        cursor = conn.cursor()
        
        try:
            # Obtener datos raw de la base de datos
            cursor.execute("""
                SELECT UserID, Username, Balance, Energia, UltimaRecarga
                FROM Users 
                WHERE UserID = ?
            """, (user_id,))
            
            result = cursor.fetchone()
            
            if not result:
                estado = "❌ Usuario no encontrado en la base de datos"
            else:
                user_db_id, username, balance, energia, ultima_recarga = result
                tiempo_actual = int(time.time())
                
                estado = (
                    f"**UserID:** {user_db_id}\n"
                    f"**Username:** {username}\n"
                    f"**Balance:** {balance}\n"
                    f"**Energía (raw):** {energia}\n"
                    f"**UltimaRecarga (raw):** {ultima_recarga}\n"
                    f"**Tiempo actual:** {tiempo_actual}\n"
                    f"**Diferencia:** {tiempo_actual - (ultima_recarga or 0)} segundos\n"
                    f"**Energía calculada:** {get_energia(user_id)}"
                )
                
        except Exception as e:
            estado = f"❌ Error: {str(e)}"
        finally:
            conn.close()
        
        embed = discord.Embed(
            title=f"🔧 Debug: Energía de {target_user.display_name}",
            color=discord.Color.orange()
        )
        embed.add_field(
            name="📊 Estado del Sistema",
            value=estado,
            inline=False
        )
        
        embed.color = discord.Color.orange()
        embed.set_footer(text="💡 Esta información es para debugging del sistema de energía")
        
        await interaction.response.send_message(embed=embed, ephemeral=True)

async def setup(bot):
    await bot.add_cog(Energia(bot))
    print("✅ Energia command cog loaded successfully.")
