import discord
from discord.ext import commands
import wavelink
import logging
import traceback

# Configurar logger
logger = logging.getLogger('discord_bot')

class Music(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.logger = logger
        self.logger.info("[MUSIC] Inicializando módulo Music")
        
    async def cog_load(self):
        """Se ejecuta cuando el cog se carga"""
        try:
            # Verificar si Lavalink ya está conectado
            nodes = wavelink.Pool.nodes
            if not nodes:
                self.logger.info("[MUSIC] No hay nodos Lavalink conectados. Intentando conectar...")
                await self.start_nodes()
            else:
                self.logger.info(f"[MUSIC] Nodos Lavalink ya conectados: {len(nodes)}")
        except Exception as e:
            self.logger.error(f"[MUSIC] Error en cog_load: {e}")
    
    async def start_nodes(self):
        """Conecta a Lavalink si no está ya conectado"""
        try:
            # Crear y conectar al nodo Lavalink
            node = wavelink.Node(
                uri='http://localhost:2444',
                password='youshallnotpass'
            )
            await wavelink.Pool.connect(client=self.bot, nodes=[node])
            self.logger.info("[MUSIC] Nodo Lavalink conectado correctamente")
        except Exception as e:
            self.logger.error(f"[MUSIC] Error conectando a Lavalink: {e}")
            self.logger.debug(traceback.format_exc())

    @commands.hybrid_command(
        name="play",
        description="Reproduce una canción de YouTube, Spotify o SoundCloud"
    )
    @discord.app_commands.describe(
        search="Nombre de la canción o URL de YouTube/Spotify/SoundCloud"
    )
    async def play(self, ctx, *, search: str):
        """Reproduce una canción desde YouTube, Spotify o SoundCloud"""
        # Verificar si el usuario está en un canal de voz
        if not ctx.author.voice or not ctx.author.voice.channel:
            await ctx.send("❌ **Error:** Debes estar en un canal de voz.", ephemeral=True)
            return
            
        # Obtener el canal y el servidor
        channel = ctx.author.voice.channel
        guild = ctx.guild
        
        # Mensaje inicial
        msg = await ctx.send("🔄 **Conectando al servidor de música...**")
        
        # Variables para usar en el método
        node = None
        player = None
        tracks = []
        
        # 1. Intentar obtener un nodo disponible
        try:
            node = wavelink.Pool.get_node()
            if not node:
                self.logger.warning("[MUSIC] No se encontró ningún nodo Lavalink. Intentando conectar...")
                await self.start_nodes()
                node = wavelink.Pool.get_node()
        except Exception as e:
            self.logger.error(f"[MUSIC] Error obteniendo nodo Lavalink: {e}")
            await msg.edit(content="❌ **Error:** No se pudo conectar al servidor de música. Por favor, inténtalo de nuevo más tarde.")
            return
            
        # 2. Obtener o crear un reproductor para este servidor
        try:
            player = node.get_player(guild.id)
            if not player:
                player = await channel.connect(cls=wavelink.Player)
            elif not player.channel or player.channel.id != channel.id:
                await player.move_to(channel)
        except Exception as e:
            self.logger.error(f"[MUSIC] Error conectando al canal de voz: {e}")
            await msg.edit(content=f"❌ **Error:** No se pudo conectar al canal de voz: {str(e)}")
            return
            
        # 3. Actualizar mensaje
        await msg.edit(content="🔎 **Buscando canción...**")
        
        # 4. Buscar la pista según la plataforma
        try:
            if 'spotify.com' in search:
                tracks = await wavelink.Playable.search(search, source=wavelink.TrackSource.SPOTIFY)
            elif 'soundcloud.com' in search:
                tracks = await wavelink.Playable.search(search, source=wavelink.TrackSource.SOUNDCLOUD)
            else:
                tracks = await wavelink.Playable.search(search, source=wavelink.TrackSource.YOUTUBE)
                
            if not tracks:
                # Intento de fallback a YouTube si la búsqueda específica falló
                tracks = await wavelink.Playable.search(search)
        except Exception as e:
            self.logger.error(f"[MUSIC] Error buscando canción: {e}")
            await msg.edit(content=f"❌ **Error:** Ocurrió un problema al buscar la canción: {str(e)}")
            return
            
        # 5. Verificar si se encontró alguna canción
        if not tracks:
            await msg.edit(content="❌ **No se encontró ninguna canción con ese nombre o URL.**")
            return
            
        # 6. Tomar la primera canción encontrada
        track = tracks[0]
        # 7. Reproducir la canción
        try:
            await player.play(track)
            
            # 8. Crear embed con metadatos
            embed = discord.Embed(
                title=f"🎵 Reproduciendo: {track.title}",
                description=f"[Enlace]({track.uri})",
                color=discord.Color.blurple()
            )
            embed.add_field(name="Duración", value=self.format_duration(track.length), inline=True)
            embed.add_field(name="Autor", value=track.author, inline=True)
            embed.add_field(name="Plataforma", value=track.source.name.title(), inline=True)
            if track.artwork:
                embed.set_thumbnail(url=track.artwork)
            
            # 9. Enviar mensaje con información
            await msg.edit(content=None, embed=embed)
            
        except Exception as e:
            self.logger.error(f"[MUSIC] Error reproduciendo canción: {e}")
            await msg.edit(content=f"❌ **Error:** No se pudo reproducir la canción: {str(e)}")

    def format_duration(self, ms: int) -> str:
        """Formatea la duración de milisegundos a formato mm:ss o hh:mm:ss"""
        seconds = ms // 1000
        minutes, seconds = divmod(seconds, 60)
        hours, minutes = divmod(minutes, 60)
        if hours:
            return f"{hours}:{minutes:02}:{seconds:02}"
        else:
            return f"{minutes}:{seconds:02}"

async def setup(bot):
    """Función para registrar el cog en el bot"""
    try:
        music_cog = Music(bot)
        await bot.add_cog(music_cog)
        print("Music cog loaded successfully.")
        logger.info("[MUSIC] Music cog registrado correctamente")
        
        # Sincronizar los comandos slash si es necesario
        try:
            await bot.tree.sync()
            logger.info("[MUSIC] Comandos slash sincronizados")
        except Exception as e:
            logger.warning(f"[MUSIC] No se pudieron sincronizar los comandos slash: {e}")
    except Exception as e:
        print(f"Error loading music cog: {e}")
        logger.error(f"[MUSIC] Error registrando Music cog: {e}")
