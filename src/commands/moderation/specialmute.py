import discord
from discord.ext import commands
import random
import datetime
from src.db import usuario_tiene_item, usar_item_usuario

LOG_CHANNEL_ID = 1361556360000573622
ID_AUTORIZADO = 287396390747766795
SPECIAL_MUTE_ITEM_ID = 11  # ID del item Special Mute en la tienda

# Opciones para administradores
ADMIN_MUTE_OPTIONS = [
    ("5 minutos", 5),
    ("10 minutos", 10),
    ("30 minutos", 30),
    ("1 hora", 60),
    ("1 día", 60*24),
    ("se salvó", 0)
]

# Opciones para usuarios con el item (más limitadas)
USER_MUTE_OPTIONS = [
    ("5 minutos", 5),
    ("10 minutos", 10), 
    ("30 minutos", 30),
    ("se salvó", 0)
]

# Registro de usuarios muteados para evitar spam
# Formato: {target_user_id: {muter_id: timestamp}}
mute_cooldown = {}

class SpecialMute(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @discord.app_commands.command(
        name="specialmute",
        description="Mutea a un usuario aleatoriamente (solo mención, no ID)."
    )
    @discord.app_commands.describe(
        miembro="Usuario a mutear (selecciónalo del menú o menciónalo)"
    )
    async def specialmute(self, interaction: discord.Interaction, miembro: discord.Member):
        user_id = interaction.user.id
        es_admin = user_id == ID_AUTORIZADO
        tiene_item = usuario_tiene_item(user_id, SPECIAL_MUTE_ITEM_ID)
        
        # Verificar permiso (admin o tiene item)
        if not es_admin and not tiene_item:
            await interaction.response.send_message("No tienes permiso para usar este comando. Puedes comprar el item Special Mute en la tienda para usarlo una vez.", ephemeral=True)
            return
            
        # Variable para controlar si debemos consumir el item
        debe_consumir_item = not es_admin
            
        # Evitar auto-mute
        if miembro.id == user_id:
            await interaction.response.send_message("No puedes mutearte a ti mismo con este comando.", ephemeral=True)
            # No consumir el item en este caso
            return
            
        # Verificar cooldown (solo para usuarios no admin)
        if not es_admin:
            # Comprobar si el usuario objetivo ya ha sido muteado hoy por este usuario
            now = datetime.datetime.now()
            if miembro.id in mute_cooldown and user_id in mute_cooldown[miembro.id]:
                last_mute_time = mute_cooldown[miembro.id][user_id]
                # Verificar si han pasado menos de 24 horas desde el último mute
                if (now - last_mute_time).total_seconds() < 86400:  # 24 horas en segundos
                    await interaction.response.send_message(f"No puedes usar Special Mute en {miembro.display_name} más de una vez por día.", ephemeral=True)
                    # No consumir el item si hay cooldown
                    return

        # Acceder al canal de log de forma segura
        log_channel = None
        if interaction.guild:
            log_channel = interaction.guild.get_channel(LOG_CHANNEL_ID)
            
        mention = miembro.mention
        
        # Usar diferentes opciones según sea admin o usuario con item
        options = ADMIN_MUTE_OPTIONS if es_admin else USER_MUTE_OPTIONS
        resultado, minutos = random.choice(options)
        
        # Primero consumir el item si es un usuario normal (no admin)
        # Esto asegura que se consuma SIEMPRE, independientemente del resultado del mute
        if debe_consumir_item:
            try:
                item_usado = usar_item_usuario(user_id, SPECIAL_MUTE_ITEM_ID)
                if item_usado:
                    mensaje_item = "\n⚠️ Has consumido tu item Special Mute. Necesitarás comprar otro si quieres volver a usar este comando."
                else:
                    # Esto no debería ocurrir si ya verificamos que tiene_item antes
                    mensaje_item = "\nℹ️ Error: No se encontró tu item Special Mute en el inventario."
            except Exception as e:
                # El comando funcionó pero hubo error al consumir el item
                print(f"Error al consumir Special Mute item: {e}")
                mensaje_item = "\nℹ️ Ha ocurrido un error al registrar el uso de tu item, pero el comando ha funcionado correctamente."
        else:
            mensaje_item = ""

        if minutos > 0:
            until = discord.utils.utcnow() + datetime.timedelta(minutes=minutos)
            try:
                await miembro.timeout(until, reason="Mute especial (timeout)")
                msg = f"🔇 {mention} Wena hablai puras weas y te ganaste {resultado} de silencio."
                
                # Registrar el uso del mute para el cooldown (solo para usuarios normales)
                if not es_admin:
                    if miembro.id not in mute_cooldown:
                        mute_cooldown[miembro.id] = {}
                    mute_cooldown[miembro.id][user_id] = datetime.datetime.now()
            except Exception as e:
                msg = f"No se pudo mutear a {mention}: {e}"
        else:
            msg = f"🟢 {mention} Te salvaste de pura suerte."
        
        # Añadir el mensaje sobre el item consumido
        msg += mensaje_item

        # Solo enviar al canal de logs si existe y es un canal de texto
        if log_channel and isinstance(log_channel, discord.TextChannel):
            await log_channel.send(msg)
        await interaction.response.send_message(msg, ephemeral=True)

async def setup(bot):
    await bot.add_cog(SpecialMute(bot))


