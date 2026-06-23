import discord
from discord.ext import commands
from discord import app_commands

class CasinoInfo(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="casino", description="Muestra la información de los juegos disponibles en el casino.")
    async def casino(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="🎰 ¡Bienvenido al Casino!",
            description="Aquí tienes la lista de los juegos disponibles y cómo funcionan. Recuerda que la casa usa un **sistema dinámico de dificultad**, por lo que jugar responsablemente y variar tus apuestas es la clave del éxito.",
            color=discord.Color.gold()
        )

        embed.add_field(
            name="🍒 /slots [apuesta]",
            value="El clásico tragamonedas. Intenta conseguir pares o tríos iguales para multiplicar tu apuesta. ¡El jackpot puede multiplicar tu apuesta hasta por 50x!",
            inline=False
        )

        embed.add_field(
            name="🃏 /blackjack [apuesta]",
            value="Juega contra el crupier (dealer) intentando acercarte a 21 sin pasarte. ¡Si sacas un As y una figura (J, Q, K) obtienes un Blackjack natural y ganas el 150% de tu apuesta!",
            inline=False
        )

        embed.add_field(
            name="🪙 /coinflip [apuesta] [cara/sello]",
            value="Apuesta todo a cara o sello. Tienes un 50% de probabilidad base de duplicar tu apuesta.",
            inline=False
        )

        embed.add_field(
            name="💥 /crash [apuesta]",
            value="El multiplicador empezará a subir desde x1.00. Tienes que retirarte antes de que la gráfica explote (Crash) para llevarte las ganancias acumuladas. ¡Puedes multiplicar tu apuesta hasta por 25x!",
            inline=False
        )

        embed.add_field(
            name="📈 /higher_lower [apuesta]",
            value="Una carta aparecerá sobre la mesa y deberás adivinar si la siguiente carta será de mayor o menor valor. Cuantos más aciertos consecutivos tengas, mayor será el multiplicador final.",
            inline=False
        )
        
        embed.set_footer(text="Usa los comandos para jugar y que la suerte esté de tu lado.")
        embed.set_thumbnail(url=interaction.guild.icon.url if interaction.guild and interaction.guild.icon else None)

        await interaction.response.send_message(embed=embed)

async def setup(bot):
    await bot.add_cog(CasinoInfo(bot))
    print("Casino Info cog loaded successfully.")
