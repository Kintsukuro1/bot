import discord
from discord.ext import commands

class ServerInfo(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @discord.app_commands.command(name="serverinfo", description="Muestra información del servidor.")
    async def serverinfo(self, interaction: discord.Interaction):
        try:
            guild = interaction.guild

            # Intenta obtener el owner de forma asíncrona si es None
            owner = guild.owner
            if owner is None:
                try:
                    owner = await self.bot.fetch_user(guild.owner_id)
                except Exception:
                    owner = None

            owner_display = owner.mention if owner and hasattr(owner, "mention") else f"ID: {guild.owner_id}"

            embed = discord.Embed(
                title=f"Información de {guild.name}",
                color=discord.Color.green()
            )
            embed.set_thumbnail(url=guild.icon.url if guild.icon else discord.Embed.Empty)
            embed.add_field(name="ID", value=guild.id, inline=True)
            embed.add_field(name="Propietario", value=owner_display, inline=True)
            embed.add_field(name="Miembros", value=guild.member_count, inline=True)
            embed.add_field(name="Canales", value=len(guild.channels), inline=True)
            embed.add_field(name="Creado el", value=guild.created_at.strftime("%d/%m/%Y"), inline=True)
            await interaction.response.send_message(embed=embed)
        except Exception as e:
            await interaction.response.send_message(f"Ocurrió un error: {e}", ephemeral=True)

async def setup(bot):
    await bot.add_cog(ServerInfo(bot))