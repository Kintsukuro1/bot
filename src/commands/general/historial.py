import discord
from discord.ext import commands
from discord import app_commands
import asyncio
from src.db import ensure_user, db_cursor

class Historial(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="historial", description="Muestra el historial de transacciones recientes de un usuario.")
    @app_commands.describe(usuario="Usuario a consultar (opcional)")
    async def historial(self, interaction: discord.Interaction, usuario: discord.Member = None):
        target_user = usuario or interaction.user
        
        # Asegurar que el usuario existe en un hilo de trabajo
        await asyncio.to_thread(ensure_user, target_user.id, target_user.name)
        
        try:
            # Consultar en un hilo de trabajo para no bloquear
            def query_txs():
                with db_cursor() as cursor:
                    cursor.execute("""
                        SELECT Amount, TransactionType, Date 
                        FROM Transactions 
                        WHERE UserID = %s 
                        ORDER BY Date DESC 
                        LIMIT 10
                    """, (target_user.id,))
                    return cursor.fetchall()
                    
            rows = await asyncio.to_thread(query_txs)
            
            embed = discord.Embed(
                title=f"📜 Historial de {target_user.display_name}",
                color=discord.Color.blue()
            )
            
            # Avatar del usuario consultado
            embed.set_thumbnail(url=target_user.display_avatar.url)
            
            if not rows:
                embed.description = "ℹ️ No se encontraron transacciones recientes en el historial."
            else:
                desc_lines = []
                for amount, tx_type, date in rows:
                    sign = "+" if amount >= 0 else ""
                    # Formatear la fecha
                    date_str = date.strftime("%d/%m/%Y %H:%M")
                    # Crear formato de lista detallada
                    desc_lines.append(f"⏱️ `{date_str}` | **{tx_type}**\n🪙 **{sign}{amount:,}** monedas")
                
                embed.description = "\n\n".join(desc_lines)
                
            embed.set_footer(text=f"Solicitado por {interaction.user.display_name}")
            await interaction.response.send_message(embed=embed)
            
        except Exception as e:
            print(f"Error al obtener historial: {e}")
            await interaction.response.send_message("❌ Ocurrió un error al obtener el historial de transacciones.", ephemeral=True)

            raise
async def setup(bot):
    await bot.add_cog(Historial(bot))
    print("Historial cog loaded successfully.")
