from discord.ext import commands
import discord

class Unmute(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @discord.app_commands.command()
    @commands.has_permissions(manage_roles=True)
    async def unmute(self, ctx, member: discord.Member):
        """Quita el silencio a un usuario en el servidor."""
        guild = ctx.guild
        muted_role = discord.utils.get(guild.roles, name="Muted")

        if muted_role in member.roles:
            await member.remove_roles(muted_role, reason="Unmute solicitado por moderador")
            await ctx.send(f"🔊 {member.mention} ya puede hablar y escribir de nuevo.")
        else:
            await ctx.send(f"{member.mention} no está silenciado.")

    @unmute.error
    async def unmute_error(self, ctx, error):
        if isinstance(error, commands.MissingPermissions):
            await ctx.send("No tienes permisos para usar este comando.")
        elif isinstance(error, commands.BadArgument):
            await ctx.send("Debes mencionar a un usuario válido.")
        else:
            await ctx.send("Ocurrió un error al intentar quitar el silencio al usuario.")

async def setup(bot):
    await bot.add_cog(Unmute(bot))