import discord
from discord.ext import commands
import wavelink

class MusicSong(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="song", aliases=["np", "nowplaying"], help="Muestra información sobre la canción actual.")
    async def song(self, ctx):
        # Obtener el player del servidor actual
        node = wavelink.Pool.get_node()
        if not node:
            await ctx.send("❌ No hay nodos de Lavalink disponibles.")
            return
            
        player = node.get_player(ctx.guild)
        if not player or not player.is_connected():
            await ctx.send("❌ No estoy conectado a ningún canal de voz.")
            return
        
        # Verificar si hay una canción reproduciéndose
        if not player.current:
            await ctx.send("❌ No hay ninguna canción reproduciéndose.")
            return
        
        # Obtener la canción actual
        track = player.current
        
        # Crear un embed con la información de la canción
        embed = discord.Embed(
            title=f"🎵 Reproduciendo: {track.title}",
            description=f"[Enlace]({track.uri})",
            color=discord.Color.blurple()
        )
        
        # Agregar detalles de la canción
        embed.add_field(name="Duración", value=self.format_duration(track.length), inline=True)
        embed.add_field(name="Autor", value=track.author, inline=True)
        embed.add_field(name="Plataforma", value=track.source.name.title(), inline=True)
        
        # Agregar imagen de la canción si está disponible
        if track.artwork:
            embed.set_thumbnail(url=track.artwork)
        
        await ctx.send(embed=embed)
    
    def format_duration(self, ms: int) -> str:
        seconds = ms // 1000
        minutes, seconds = divmod(seconds, 60)
        hours, minutes = divmod(minutes, 60)
        if hours:
            return f"{hours}:{minutes:02}:{seconds:02}"
        else:
            return f"{minutes}:{seconds:02}"

async def setup(bot):
    await bot.add_cog(MusicSong(bot))
    print("MusicSong cog loaded successfully.")
