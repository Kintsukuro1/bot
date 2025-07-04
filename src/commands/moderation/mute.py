from discord.ext import commands
import discord

class Mute(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @discord.app_commands.command()
    @commands.has_permissions(manage_roles=True)
    async def mute(self, ctx, member: discord.Member, *, reason: str = "Sin motivo"):
        """Silencia a un usuario en el servidor."""
        guild = ctx.guild
        muted_role = discord.utils.get(guild.roles, name="Muted")

        # Si no existe el rol, créalo y ajusta permisos
        if not muted_role:
            muted_role = await guild.create_role(name="Muted", reason="Rol para silenciar usuarios")
            for channel in guild.channels:
                await channel.set_permissions(muted_role, speak=False, send_messages=False, add_reactions=False)

        await member.add_roles(muted_role, reason=reason)
        await ctx.send(f"🔇 {member.mention} ha sido silenciado. Motivo: {reason}")

    @mute.error
    async def mute_error(self, ctx, error):
        if isinstance(error, commands.MissingPermissions):
            await ctx.send("No tienes permisos para usar este comando.")
        elif isinstance(error, commands.BadArgument):
            await ctx.send("Debes mencionar a un usuario válido.")
        else:
            await ctx.send("Ocurrió un error al intentar silenciar al usuario.")

async def setup(bot):
    await bot.add_cog(Mute(bot))