import discord
from discord.ext import commands
import wavelink

class MusicPlaylist(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="playlist", aliases=["queue", "q"], help="Muestra la lista de reproducción actual.")
    async def playlist(self, ctx):
        # Obtener el player del servidor actual
        node = wavelink.Pool.get_node()
        if not node:
            await ctx.send("❌ No hay nodos de Lavalink disponibles.")
            return
            
        player = node.get_player(ctx.guild)
        if not player or not player.is_connected():
            await ctx.send("❌ No estoy conectado a ningún canal de voz.")
            return
        
        # Verificar si hay una canción reproduciéndose actualmente
        if not player.current:
            await ctx.send("❌ No hay ninguna canción reproduciéndose.")
            return
        
        # Crear un embed para mostrar la cola de reproducción
        embed = discord.Embed(
            title="🎵 Cola de Reproducción",
            color=discord.Color.blue()
        )
        
        # Mostrar la canción actual
        embed.add_field(
            name="▶️ Reproduciendo ahora:",
            value=f"[{player.current.title}]({player.current.uri}) - {self.format_duration(player.current.length)}",
            inline=False
        )
        
        # Mostrar las próximas canciones en la cola
        queue_text = ""
        if hasattr(player, 'queue') and player.queue:
            for i, track in enumerate(player.queue, start=1):
                # Limitar a 10 canciones para no sobrecargar el embed
                if i > 10:
                    queue_text += f"\n... y {len(player.queue) - 10} más"
                    break
                queue_text += f"{i}. [{track.title}]({track.uri}) - {self.format_duration(track.length)}\n"
        
        if queue_text:
            embed.add_field(
                name="📋 Próximas canciones:",
                value=queue_text,
                inline=False
            )
        else:
            embed.add_field(
                name="📋 Próximas canciones:",
                value="No hay más canciones en la cola.",
                inline=False
            )
        
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
    await bot.add_cog(MusicPlaylist(bot))
    print("MusicPlaylist cog loaded successfully.")
