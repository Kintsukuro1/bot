import discord
from discord.ext import commands
import asyncio
from src.db import ensure_user, claim_daily

class Daily(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @discord.app_commands.command(name="daily", description="Reclama tu recompensa diaria.")
    async def daily(self, interaction: discord.Interaction):
        """Reclama tu recompensa diaria."""
        user_id = interaction.user.id
        user_name = interaction.user.name
        
        # Asegurar que el usuario existe en la base de datos
        await asyncio.to_thread(ensure_user, user_id, user_name)
        
        try:
            # Reclamar la recompensa en un hilo de trabajo para no bloquear el bot
            success, data, streak, balance = await asyncio.to_thread(claim_daily, user_id)
            
            if not success:
                # data contiene el timedelta restante
                hours = data.days * 24 + data.seconds // 3600
                minutes = (data.seconds % 3600) // 60
                seconds = data.seconds % 60
                embed = discord.Embed(
                    title="⏳ Ya has reclamado tu recompensa diaria hoy",
                    description=f"Vuelve en **{hours}h {minutes}m {seconds}s** para reclamar de nuevo.",
                    color=discord.Color.orange()
                )
                await interaction.response.send_message(embed=embed)
                return

            # Si success es True, data es el monto de la recompensa
            embed = discord.Embed(
                title="🎁 ¡Recompensa diaria reclamada!",
                description=f"Has recibido **{data}** monedas.\nRacha: **{streak}** días.\nSaldo actual: **{balance}**",
                color=discord.Color.green()
            )
            await interaction.response.send_message(embed=embed)
            
        except Exception as e:
            await interaction.response.send_message(f"Ocurrió un error al reclamar la recompensa diaria: {e}", ephemeral=True)

            raise
# Añadir el cog al bot
async def setup(bot):
    await bot.add_cog(Daily(bot))
    print("Daily cog cargado con éxito")
