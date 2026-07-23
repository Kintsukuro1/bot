import discord
from discord.ext import commands
from discord import app_commands
from src.db import get_provably_fair_seeds, rotate_provably_fair_seeds
from src.utils.provably_fair import hash_server_seed

class ProvablyFair(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def provably_fair_cmd(self, interaction: discord.Interaction):

        seeds = get_provably_fair_seeds(interaction.user.id)
        
        server_hash = hash_server_seed(seeds["server_seed"])
        client_seed = seeds["client_seed"]
        nonce = seeds["nonce"]
        
        embed = discord.Embed(
            title="🛡️ Imparcialidad Verificable (Provably Fair)",
            description=(
                "Todos nuestros juegos de casino usan criptografía para garantizar resultados 100% justos y auditables.\n\n"
                "El resultado de un juego se calcula usando:\n"
                "`HMAC-SHA512(ServerSeed, ClientSeed : Nonce : Cursor)`"
            ),
            color=discord.Color.blue()
        )

        embed.add_field(
            name="🔒 Semillas Actuales (Activas)",
            value=(
                f"**Hash del Servidor (Oculto):**\n`{server_hash}`\n"
                f"**Tu Semilla de Cliente:**\n`{client_seed}`\n"
                f"**Nonce (Jugadas):** `{nonce}`"
            ),
            inline=False
        )

        embed.add_field(
            name="⚖️ Sistema de Dificultad Dinámica",
            value=(
                "Además de la generación criptográfica del resultado, el casino ajusta tus probabilidades base "
                "según tu historial reciente (rachas, tasa de victorias, ganancias acumuladas). Esto es independiente "
                "de la tirada en sí: una vez fijadas tus probabilidades, el resultado sigue siendo 100% verificable con "
                "el esquema de semillas arriba.\n\n"
                "Usa `/stats` para ver tu nivel de ajuste actual."
            ),
            inline=False
        )
        
        embed.set_footer(text="Usa los botones para rotar tus semillas o auditar partidas pasadas.")
        
        view = ProvablyFairView(interaction.user.id)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

class ProvablyFairView(discord.ui.View):
    def __init__(self, user_id):
        super().__init__(timeout=120)
        self.user_id = user_id
        
    @discord.ui.button(label="🔄 Rotar Semilla de Servidor", style=discord.ButtonStyle.primary)
    async def rotate_seed(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ No puedes usar este botón.", ephemeral=True)
            return
            
        await interaction.response.defer()
        
        new_seeds = rotate_provably_fair_seeds(self.user_id)
        server_hash = hash_server_seed(new_seeds["server_seed"])
        
        embed = discord.Embed(
            title="🔄 Semilla Rotada Exitosamente",
            description=(
                f"Tu semilla de servidor anterior ahora puede ser revelada para que audites tus partidas pasadas.\n\n"
                f"**Semilla de Servidor Anterior (¡Revelada!):**\n`{new_seeds['past_server_seed']}`\n\n"
                f"**NUEVO Hash de Servidor:**\n`{server_hash}`\n"
                f"**Tu Semilla de Cliente:**\n`{new_seeds['client_seed']}`\n"
                f"**Nonce:** `0`"
            ),
            color=discord.Color.green()
        )
        
        await interaction.edit_original_response(embed=embed, view=self)

async def setup(bot):
    await bot.add_cog(ProvablyFair(bot))
