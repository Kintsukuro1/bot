import discord
from discord.ext import commands
from discord import app_commands
import random
import asyncio
from datetime import timedelta
from src.db import get_all_minas, set_minas_canal

class Minas(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        # Diccionario para almacenar las minas activas por canal {channel_id: cantidad}
        # Cargamos desde la base de datos de manera sincrona al iniciar el cog
        try:
            self.minas_activas = get_all_minas()
        except Exception as e:
            print(f"Error cargando minas desde DB: {e}")
            self.minas_activas = {}

    @app_commands.command(name="poner_minas", description="Coloca minas explosivas ocultas en un canal específico.")
    @app_commands.describe(
        cantidad="Número de minas a colocar",
        canal="El canal donde se colocarán las minas"
    )
    @app_commands.default_permissions(administrator=True)
    async def poner_minas(self, interaction: discord.Interaction, cantidad: int, canal: discord.TextChannel):
        if cantidad <= 0:
            await interaction.response.send_message("❌ La cantidad de minas debe ser mayor a 0.", ephemeral=True)
            return

        if cantidad > 50:
            await interaction.response.send_message("❌ No puedes poner tantas minas, ¡el canal explotará! (Máximo 50).", ephemeral=True)
            return

        canal_id = canal.id
        # Sumar a las minas ya existentes o crear nuevo registro
        self.minas_activas[canal_id] = self.minas_activas.get(canal_id, 0) + cantidad

        # Guardar en base de datos (usando to_thread para no bloquear)
        asyncio.create_task(asyncio.to_thread(set_minas_canal, canal_id, self.minas_activas[canal_id]))

        embed = discord.Embed(
            title="💣 ¡Minas Colocadas!",
            description=f"Se han colocado **{cantidad}** minas en el canal {canal.mention}.\n¡Tengan cuidado por dónde pisan!",
            color=discord.Color.dark_red()
        )
        await interaction.response.send_message(embed=embed)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        # Ignorar mensajes de bots
        if message.author.bot:
            return

        canal_id = message.channel.id

        # Si no hay minas en el canal, no hacer nada
        if canal_id not in self.minas_activas or self.minas_activas[canal_id] <= 0:
            return

        # Probabilidad de que el mensaje active una mina (e.g. 15% por cada mensaje)
        # Puedes ajustar este valor si quieres que exploten más rápido o más lento
        probabilidad_explotar = 0.15 

        if random.random() < probabilidad_explotar:
            # Una mina fue activada
            self.minas_activas[canal_id] -= 1
            minas_restantes = self.minas_activas[canal_id]
            
            # Actualizar DB
            asyncio.create_task(asyncio.to_thread(set_minas_canal, canal_id, minas_restantes))
            
            # Limpiar diccionario si ya no quedan minas
            if minas_restantes <= 0:
                del self.minas_activas[canal_id]

            # 10% de probabilidad de que la mina falle (dud)
            mina_falla = random.random() < 0.10

            if mina_falla:
                embed_falla = discord.Embed(
                    title="💥 *Click...*",
                    description=f"{message.author.mention} pisó una mina...\n\n💨 **¡Qué alivio! La mina falló y no explotó.**",
                    color=discord.Color.light_grey()
                )
                if minas_restantes > 0:
                    embed_falla.set_footer(text=f"Aún quedan {minas_restantes} minas en el canal...")
                    
                await message.channel.send(embed=embed_falla)
            else:
                # La mina explotó
                try:
                    # Mute por 1 minuto (Timeout)
                    timeout_duration = timedelta(minutes=1)
                    await message.author.timeout(timeout_duration, reason="Pisó una mina explosiva.")
                    
                    embed_boom = discord.Embed(
                        title="💥 ¡BBOOOM!",
                        description=f"**¡{message.author.mention} activó una mina!**\nHa sido silenciado por 1 minuto tras la explosión. 🤕",
                        color=discord.Color.red()
                    )
                    if minas_restantes > 0:
                        embed_boom.set_footer(text=f"Aún quedan {minas_restantes} minas en el canal...")
                        
                    await message.channel.send(embed=embed_boom)
                except discord.Forbidden:
                    # Si el bot no tiene permisos o el usuario es admin/dueño
                    embed_error = discord.Embed(
                        title="💥 ¡BBOOOM!",
                        description=f"**¡{message.author.mention} activó una mina!**\nPero es demasiado poderoso(a) y sobrevivió a la explosión sin ser silenciado(a) (Faltan permisos/Es administrador).",
                        color=discord.Color.orange()
                    )
                    await message.channel.send(embed=embed_error)
                except Exception as e:
                    print(f"Error al mutear por mina: {e}")

    @app_commands.command(name="sacar_minas", description="Elimina todas las minas de un canal específico.")
    @app_commands.describe(
        canal="El canal donde se eliminarán las minas (opcional, por defecto el canal actual)"
    )
    @app_commands.default_permissions(administrator=True)
    async def sacar_minas(self, interaction: discord.Interaction, canal: discord.TextChannel = None):
        canal_obj = canal or interaction.channel
        canal_id = canal_obj.id

        if canal_id in self.minas_activas:
            del self.minas_activas[canal_id]
            await asyncio.to_thread(set_minas_canal, canal_id, 0)
            
            embed = discord.Embed(
                title="🧹 Minas Limpiadas",
                description=f"El escuadrón antibombas ha desactivado todas las minas en {canal_obj.mention}.",
                color=discord.Color.green()
            )
            await interaction.response.send_message(embed=embed)
        else:
            await interaction.response.send_message(f"✅ No hay minas en {canal_obj.mention}.", ephemeral=True)

    @app_commands.command(name="info_minas", description="Muestra la información de las minas en un canal específico.")
    @app_commands.describe(
        canal="El canal del que quieres ver la información (opcional, por defecto el canal actual)"
    )
    async def info_minas(self, interaction: discord.Interaction, canal: discord.TextChannel = None):
        canal_obj = canal or interaction.channel
        canal_id = canal_obj.id

        minas_restantes = self.minas_activas.get(canal_id, 0)
        prob_explosion = 15 # 15% hardcoded en on_message
        prob_falla = 10 # 10% de que sea defectuosa si explota

        if minas_restantes > 0:
            embed = discord.Embed(
                title="💣 Información de Minas",
                description=f"Estado de las minas en {canal_obj.mention}:",
                color=discord.Color.orange()
            )
            embed.add_field(name="Minas Activas", value=f"**{minas_restantes}**", inline=False)
            embed.add_field(name="Probabilidad de Activar", value=f"**{prob_explosion}%** por cada mensaje enviado.", inline=False)
            embed.add_field(name="Probabilidad de Fallo (Dud)", value=f"**{prob_falla}%** si se activa la mina.", inline=False)
            embed.set_footer(text="¡Ten mucho cuidado por dónde pisas!")
        else:
            embed = discord.Embed(
                title="✅ Área Segura",
                description=f"No hay minas activas en {canal_obj.mention}.",
                color=discord.Color.green()
            )

        await interaction.response.send_message(embed=embed)

async def setup(bot):
    await bot.add_cog(Minas(bot))
    print("Minas cog loaded successfully.")
