import discord
from discord.ext import commands
from discord import app_commands
from typing import Optional

class Mensaje(commands.Cog):
    """Cog para enviar mensajes como el bot (solo para el owner)."""
    
    def __init__(self, bot):
        self.bot = bot
        # Reemplaza este ID con tu Discord User ID
        self.OWNER_ID = 287396390747766795  # <-- CAMBIA ESTE ID POR EL TUYO
    
    @app_commands.command(name="mensaje", description="Envía un mensaje como el bot (solo owner)")
    @app_commands.describe(
        contenido="El contenido del mensaje que quieres enviar",
        canal="Canal donde enviar el mensaje (opcional, por defecto el actual)"
    )
    async def mensaje(
        self, 
        interaction: discord.Interaction, 
        contenido: str, 
        canal: Optional[discord.TextChannel] = None
    ):
        # Verificar que solo tú puedas usar el comando
        if interaction.user.id != self.OWNER_ID:
            await interaction.response.send_message("❌ Solo el propietario del bot puede usar este comando.", ephemeral=True)
            return
        
        # Si no se especifica canal, usar el canal actual
        target_channel = canal or interaction.channel
        
        # Verificar permisos del bot en el canal objetivo
        if not target_channel.permissions_for(interaction.guild.me).send_messages:
            await interaction.response.send_message(
                f"❌ No tengo permisos para enviar mensajes en {target_channel.mention}", 
                ephemeral=True
            )
            return
        
        try:
            # Enviar el mensaje como el bot
            await target_channel.send(contenido)
            
            # Confirmar al usuario que se envió
            if canal and canal != interaction.channel:
                await interaction.response.send_message(
                    f"✅ Mensaje enviado en {target_channel.mention}", 
                    ephemeral=True
                )
            else:
                await interaction.response.send_message(
                    "✅ Mensaje enviado", 
                    ephemeral=True
                )
                
        except discord.HTTPException as e:
            await interaction.response.send_message(
                f"❌ Error al enviar el mensaje: {str(e)}", 
                ephemeral=True
            )
        except Exception as e:
            await interaction.response.send_message(
                f"❌ Error inesperado: {str(e)}", 
                ephemeral=True
            )

    @app_commands.command(name="embed", description="Envía un embed como el bot (solo owner)")
    @app_commands.describe(
        titulo="Título del embed",
        descripcion="Descripción del embed",
        color="Color del embed (hex, ej: #ff0000 para rojo)",
        canal="Canal donde enviar el embed (opcional, por defecto el actual)"
    )
    async def embed(
        self, 
        interaction: discord.Interaction, 
        titulo: str,
        descripcion: str,
        color: Optional[str] = None,
        canal: Optional[discord.TextChannel] = None
    ):
        # Verificar que solo tú puedas usar el comando
        if interaction.user.id != self.OWNER_ID:
            await interaction.response.send_message("❌ Solo el propietario del bot puede usar este comando.", ephemeral=True)
            return
        
        # Si no se especifica canal, usar el canal actual
        target_channel = canal or interaction.channel
        
        # Verificar permisos del bot en el canal objetivo
        if not target_channel.permissions_for(interaction.guild.me).send_messages:
            await interaction.response.send_message(
                f"❌ No tengo permisos para enviar mensajes en {target_channel.mention}", 
                ephemeral=True
            )
            return
        
        try:
            # Procesar color
            embed_color = discord.Color.blue()  # Color por defecto
            if color:
                try:
                    # Convertir color hex a entero
                    if color.startswith('#'):
                        color = color[1:]
                    embed_color = discord.Color(int(color, 16))
                except ValueError:
                    embed_color = discord.Color.blue()
            
            # Crear embed
            embed = discord.Embed(
                title=titulo,
                description=descripcion,
                color=embed_color
            )
            embed.set_footer(text=f"Enviado por {interaction.user.display_name}")
            
            # Enviar el embed
            await target_channel.send(embed=embed)
            
            # Confirmar al usuario que se envió
            if canal and canal != interaction.channel:
                await interaction.response.send_message(
                    f"✅ Embed enviado en {target_channel.mention}", 
                    ephemeral=True
                )
            else:
                await interaction.response.send_message(
                    "✅ Embed enviado", 
                    ephemeral=True
                )
                
        except discord.HTTPException as e:
            await interaction.response.send_message(
                f"❌ Error al enviar el embed: {str(e)}", 
                ephemeral=True
            )
        except Exception as e:
            await interaction.response.send_message(
                f"❌ Error inesperado: {str(e)}", 
                ephemeral=True
            )

async def setup(bot):
    await bot.add_cog(Mensaje(bot))
    print("Mensaje cog loaded successfully.")
