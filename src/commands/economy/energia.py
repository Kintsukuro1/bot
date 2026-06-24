import time
import discord
from discord.ext import commands
from discord import app_commands
from typing import Optional

# Importar funciones de lógica y datos desde la capa central de base de datos
from src.db import (
    ensure_user,
    init_energia_db,
    get_energia,
    set_energia,
    tiempo_hasta_recarga_completa,
    get_energia_info,
    fix_timestamps_energia,
    db_cursor
)

def consumir_energia(user_id: int, cantidad: int) -> bool:
    """Consume una cantidad específica de energía del usuario.
    Retorna True si fue exitoso, False si no tenía suficiente energía."""
    energia_actual = get_energia(user_id)
    if energia_actual >= cantidad:
        set_energia(user_id, energia_actual - cantidad)
        return True
    return False

class Energia(commands.Cog):
    """Cog para comandos relacionados con energía."""
    
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="energia", description="Ver tu estado de energía actual")
    async def energia_command(self, interaction: discord.Interaction):
        """Comando para mostrar la energía del usuario."""
        user_id = interaction.user.id
        
        # Asegurar que el usuario existe de forma asíncrona
        from src.services import UserService
        await UserService.ensure_user(user_id, interaction.user.name)
        
        # Obtener información de energía en un hilo
        info = await asyncio.to_thread(get_energia_info, user_id)
        
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
        
        try:
            def fetch_debug():
                with db_cursor() as cursor:
                    cursor.execute("""
                        SELECT UserID, Username, Balance, Energia, UltimaRecarga
                        FROM Users 
                        WHERE UserID = %s
                    """, (user_id,))
                    return cursor.fetchone()
                
            result = await asyncio.to_thread(fetch_debug)
                
            if not result:
                estado = "❌ Usuario no encontrado en la base de datos"
            else:
                user_db_id, username, balance, energia, ultima_recarga = result
                tiempo_actual = int(time.time())
                
                energia_calc = await asyncio.to_thread(get_energia, user_id)
                estado = (
                    f"**UserID:** {user_db_id}\n"
                    f"**Username:** {username}\n"
                    f"**Balance:** {balance}\n"
                    f"**Energía (raw):** {energia}\n"
                    f"**UltimaRecarga (raw):** {ultima_recarga}\n"
                    f"**Tiempo actual:** {tiempo_actual}\n"
                    f"**Diferencia:** {tiempo_actual - (ultima_recarga or 0)} segundos\n"
                    f"**Energía calculada:** {energia_calc}"
                )
                
        except Exception as e:
            estado = f"❌ Error: {str(e)}"
        
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
