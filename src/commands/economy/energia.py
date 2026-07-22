import time
import asyncio
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
    get_energia_info,
    db_cursor
)

def consumir_energia(user_id: int, cantidad: int) -> bool:
    """Consume una cantidad específica de energía del usuario de forma atómica.
    Retorna True si fue exitoso, False si no tenía suficiente energía.

    IMPORTANTE: el valor de retorno SIEMPRE debe revisarse en el trabajo que
    llama a esta función. Si da False, el trabajo no debe continuar, porque
    significa que otro trabajo en paralelo ya consumió esa energía primero."""
    from src.db import consumir_energia as _consumir_energia_db
    return _consumir_energia_db(user_id, cantidad)

class Energia(commands.Cog):
    """Cog para utilidades de energía (unificado en /trabajo)."""

    def __init__(self, bot):
        self.bot = bot

    async def get_energia_embed(self, user: discord.Member) -> discord.Embed:
        user_id = user.id
        from src.services import UserService
        await UserService.ensure_user(user_id, user.name)
        info = await asyncio.to_thread(get_energia_info, user_id)

        porcentaje = info['energia_actual'] / 100
        barra_energia = '🟩' * int(porcentaje * 10) + '⬜' * (10 - int(porcentaje * 10))

        if info['tiempo_recarga_completa'] > 0:
            horas = info['tiempo_recarga_completa'] // 60
            minutos = info['tiempo_recarga_completa'] % 60
            tiempo_texto = f"{horas}h {minutos}m" if horas > 0 else f"{minutos}m"
            recarga_info = f"⏱️ **Recarga completa en:** {tiempo_texto}"
        else:
            recarga_info = "✅ **¡Energía al máximo!**"

        color = discord.Color.green() if info['energia_actual'] > 70 else (discord.Color.yellow() if info['energia_actual'] > 30 else discord.Color.red())

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
        return embed

async def setup(bot):
    await bot.add_cog(Energia(bot))

