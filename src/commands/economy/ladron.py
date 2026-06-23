import discord
import asyncio
import random
from src.db import get_balance, set_balance, registrar_transaccion
from .energia import consumir_energia, get_energia
from .niveles_trabajo import get_nivel_trabajo, add_experiencia_trabajo, get_energia_trabajo, get_recompensa_trabajo

class LadronModal(discord.ui.Modal, title="Hackeo de Bóveda"):
    codigo_input = discord.ui.TextInput(
        label="Introduce el PIN que viste",
        style=discord.TextStyle.short,
        placeholder="Ej: 12345",
        required=True,
        max_length=10
    )

    def __init__(self, view_parent):
        super().__init__()
        self.view_parent = view_parent

    async def on_submit(self, interaction: discord.Interaction):
        self.view_parent.input_recibido = self.codigo_input.value.strip()
        await interaction.response.defer()
        self.view_parent.stop()

class LadronView(discord.ui.View):
    def __init__(self, user_id):
        super().__init__(timeout=20)
        self.user_id = user_id
        self.input_recibido = None

    @discord.ui.button(label="Introducir PIN", style=discord.ButtonStyle.primary, emoji="🔓")
    async def btn_pin(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ No es tu atraco.", ephemeral=True)
            return
        
        # Abrir modal
        await interaction.response.send_modal(LadronModal(self))

    async def on_timeout(self):
        self.input_recibido = ""

async def iniciar_trabajo_ladron(interaction: discord.Interaction):
    user_id = interaction.user.id
    tipo_trabajo = "ladron"

    nivel_info = get_nivel_trabajo(user_id, tipo_trabajo)
    nivel = nivel_info["nivel"]

    energia_req = get_energia_trabajo(tipo_trabajo, user_id)
    energia_actual = get_energia(user_id)

    if energia_actual < energia_req:
        await interaction.response.send_message(
            f"❌ **No tienes suficiente energía.** Necesitas {energia_req} ⚡, pero tienes {energia_actual} ⚡.",
            ephemeral=True
        )
        return

    await interaction.response.defer()
    consumir_energia(user_id, energia_req)

    # Nivel 8 acorta el pin
    len_pin = 4 if nivel >= 8 else 5
    pin_secreto = "".join([str(random.randint(0, 9)) for _ in range(len_pin)])

    embed = discord.Embed(
        title="🥷 Asalto al Banco Central",
        description=f"Has llegado a la bóveda principal.\nMemoriza este PIN para desactivar la alarma:\n\n# **{pin_secreto}**",
        color=discord.Color.dark_theme()
    )
    embed.set_footer(text="El PIN desaparecerá en 3 segundos...")
    
    msg = await interaction.followup.send(embed=embed, wait=True)
    await asyncio.sleep(3)
    
    embed_oculto = discord.Embed(
        title="🥷 Asalto al Banco Central",
        description="¡El panel se ha bloqueado! Tienes 20 segundos para presionar el botón e introducir el PIN de memoria.",
        color=discord.Color.orange()
    )
    
    view = LadronView(user_id)
    await msg.edit(embed=embed_oculto, view=view)
    
    await view.wait()
    
    # Validar resultado
    if view.input_recibido == pin_secreto:
        # Éxito
        recompensa_base = get_recompensa_trabajo(tipo_trabajo, user_id)
        recompensa = int(recompensa_base * random.uniform(1.0, 1.5)) # Alta recompensa
        
        saldo_actual = get_balance(user_id)
        set_balance(user_id, saldo_actual + recompensa)
        registrar_transaccion(user_id, recompensa, "Trabajo: Ladrón de Bancos (Éxito)")
        
        xp_ganada = 20
        resultado_xp = add_experiencia_trabajo(user_id, tipo_trabajo, xp_ganada)
        
        embed_final = discord.Embed(
            title="💰 ¡Bóveda Saqueada!",
            description="Introdujiste el PIN correcto y escapaste con el botín antes de que llegara la policía.",
            color=discord.Color.green()
        )
        embed_final.add_field(name="💰 Botín Obtenido", value=f"**{recompensa}** monedas")
        
        xp_msg = f"+{resultado_xp['xp_ganada_final']} XP"
        if resultado_xp['pocion_usada']:
            xp_msg += " (🧪 x1.5)"
        embed_final.add_field(name="✨ Experiencia", value=xp_msg)
        
        if resultado_xp['subio_nivel']:
            embed_final.add_field(
                name="🎉 ¡SUBISTE DE NIVEL!", 
                value=f"Ahora eres nivel **{resultado_xp['nivel_nuevo']}** de Ladrón.",
                inline=False
            )

        await msg.edit(embed=embed_final, view=None)
    else:
        # Fallo
        multa = 150
        tiene_ganzua = nivel >= 5
        
        if tiene_ganzua:
            embed_fail = discord.Embed(
                title="🚨 ¡Alarma Activada!",
                description=f"PIN incorrecto (era {pin_secreto}). La policía ha llegado, pero usaste tu Ganzúa Electrónica para escapar sin pagar multa. Sin embargo, no consigues botín.",
                color=discord.Color.orange()
            )
            await msg.edit(embed=embed_fail, view=None)
            add_experiencia_trabajo(user_id, tipo_trabajo, 5)
        else:
            saldo_actual = get_balance(user_id)
            if saldo_actual >= multa:
                set_balance(user_id, saldo_actual - multa)
                registrar_transaccion(user_id, -multa, "Multa por atraco fallido")
                multa_txt = f"Has pagado una fianza de **{multa}** monedas."
            else:
                set_balance(user_id, 0)
                registrar_transaccion(user_id, -saldo_actual, "Embargo por atraco fallido")
                multa_txt = "Han embargado todo el dinero que tenías."
                
            embed_fail = discord.Embed(
                title="🚓 ¡ARRESTADO!",
                description=f"Introdujiste el PIN incorrecto (era {pin_secreto}). La policía te ha capturado.\n\n{multa_txt}",
                color=discord.Color.red()
            )
            await msg.edit(embed=embed_fail, view=None)
            add_experiencia_trabajo(user_id, tipo_trabajo, 2)
