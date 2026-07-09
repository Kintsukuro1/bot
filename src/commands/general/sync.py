from discord.ext import commands

class SyncCommand(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(
        name="sync",
        help="Sincroniza los comandos slash del bot."
    )
    @commands.guild_only()
    @commands.is_owner()
    async def sync(self, ctx: commands.Context, spec: str = None) -> None:
        """
        Sincroniza los comandos slash del bot.
        Modo de uso:
        !sync         -> Limpia comandos locales de la guild (evita duplicados) y sincroniza globales.
        !sync guild   -> Sincroniza comandos solo en el servidor actual.
        !sync clear   -> Elimina los comandos específicos de este servidor.
        !sync global  -> Sincroniza comandos globales únicamente.
        """
        try:
            if spec == "guild":
                await ctx.send("⏳ Sincronizando comandos slash localmente en este servidor...")
                synced = await ctx.bot.tree.sync(guild=ctx.guild)
                await ctx.send(f"✅ {len(synced)} comandos slash locales sincronizados.")
            elif spec == "clear":
                await ctx.send("⏳ Limpiando comandos locales de este servidor...")
                ctx.bot.tree.clear_commands(guild=ctx.guild)
                await ctx.bot.tree.sync(guild=ctx.guild)
                await ctx.send("🧹 Todos los comandos locales han sido eliminados de este servidor.")
            elif spec == "global":
                await ctx.send("⏳ Sincronizando comandos globales...")
                synced = await ctx.bot.tree.sync()
                await ctx.send(f"✅ {len(synced)} comandos slash globales sincronizados.")
            else:
                # Modo por defecto: SOLO guild (instantáneo). Primero copiamos y
                # sincronizamos el guild (mientras el árbol local global todavía
                # tiene los comandos), y RECIÉN DESPUÉS limpiamos el scope global
                # para no dejar duplicados. Si se limpia el global primero,
                # copy_global_to no tiene nada que copiar.
                await ctx.send("⏳ Sincronizando este servidor y limpiando comandos globales...")
                ctx.bot.tree.copy_global_to(guild=ctx.guild)
                synced = await ctx.bot.tree.sync(guild=ctx.guild)
                # Guardamos y restauramos los comandos globales locales para no perder la
                # definición en memoria que se usará en futuras copias/sincronizaciones
                global_cmds = ctx.bot.tree.get_commands(guild=None)
                ctx.bot.tree.clear_commands(guild=None)
                await ctx.bot.tree.sync()
                for cmd in global_cmds:
                    ctx.bot.tree.add_command(cmd)
                await ctx.send(f"✅ {len(synced)} comandos sincronizados en este servidor. Comandos globales limpiados.")
        except Exception as e:
            await ctx.send(f"❌ Error al sincronizar comandos: {str(e)}")
            raise

async def setup(bot):
    await bot.add_cog(SyncCommand(bot))
    print("SyncCommand cog loaded successfully.")