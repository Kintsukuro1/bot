import discord
import asyncio
import random
from src.db import get_balance, set_balance, registrar_transaccion
from .energia import consumir_energia, get_energia
from .niveles_trabajo import get_nivel_trabajo, add_experiencia_trabajo, get_energia_trabajo, get_recompensa_trabajo, get_job_header
from .job_fx import fase_previa_trabajo

HERRAMIENTAS = {
    "bisturi": {"nombre": "Bisturí", "emoji": "🔪"},
    "anestesia": {"nombre": "Anestesia", "emoji": "💉"},
    "vendaje": {"nombre": "Vendaje", "emoji": "🩹"},
    "desfibrilador": {"nombre": "Desfibrilador", "emoji": "⚡"}
}

SITUACIONES_MEDICAS = [
    {"desc": "El cirujano principal pide hacer la incisión inicial.", "herramienta": "bisturi"},
    {"desc": "El paciente muestra signos de dolor y se mueve.", "herramienta": "anestesia"},
    {"desc": "Hay una hemorragia leve en la zona superficial.", "herramienta": "vendaje"},
    {"desc": "¡El monitor muestra una línea plana! Paro cardíaco.", "herramienta": "desfibrilador"},
    {"desc": "Necesitamos extirpar el tumor expuesto.", "herramienta": "bisturi"},
    {"desc": "La operación va a durar más de lo esperado, los sedantes bajan.", "herramienta": "anestesia"}
]

class HerramientaMedicaView(discord.ui.View):
    def __init__(self, user_id, herramienta_correcta, tiempo_limite):
        super().__init__(timeout=tiempo_limite)
        self.user_id = user_id
        self.herramienta_correcta = herramienta_correcta
        self.resultado = None # True acierto, False fallo
        self.clicked = False

        for key, val in HERRAMIENTAS.items():
            btn = discord.ui.Button(label=val["nombre"], emoji=val["emoji"], style=discord.ButtonStyle.secondary, custom_id=key)
            btn.callback = self.crear_callback(key)
            self.add_item(btn)

    def crear_callback(self, custom_id):
        async def callback(interaction: discord.Interaction):
            if interaction.user.id != self.user_id:
                await interaction.response.send_message("❌ No eres parte del equipo médico.", ephemeral=True)
                return
            
            if self.clicked: return
            self.clicked = True
            
            self.resultado = (custom_id == self.herramienta_correcta)
            for item in self.children:
                item.disabled = True
                
            await interaction.response.edit_message(view=self)
            self.stop()
        return callback

    async def on_timeout(self):
        self.clicked = True
        self.resultado = False
        for item in self.children:
            item.disabled = True

class DiagnosticoView(discord.ui.View):
    """Variante sin pistas visuales: en vez de botones con el nombre de cada
    herramienta, el médico debe escribir en un Modal qué herramienta se
    necesita. Disponible desde nivel 6, reemplaza una de las 3 fases al azar."""

    def __init__(self, user_id, herramienta_correcta, tiempo_limite):
        super().__init__(timeout=tiempo_limite)
        self.user_id = user_id
        self.herramienta_correcta = herramienta_correcta
        self.resultado = None
        self.answered = False

    @discord.ui.button(label="🗣️ Dar Diagnóstico", style=discord.ButtonStyle.primary)
    async def diagnosticar(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ No eres parte del equipo médico.", ephemeral=True)
            return
        if self.answered:
            await interaction.response.defer()
            return
        await interaction.response.send_modal(DiagnosticoModal(self))

    async def on_timeout(self):
        if not self.answered:
            self.answered = True
            self.resultado = False
            for item in self.children:
                item.disabled = True


class DiagnosticoModal(discord.ui.Modal, title="Diagnóstico de Emergencia"):
    respuesta = discord.ui.TextInput(
        label="¿Qué herramienta se necesita?",
        placeholder="bisturí / anestesia / vendaje / desfibrilador",
        required=True,
        max_length=30
    )

    def __init__(self, view_padre: "DiagnosticoView"):
        super().__init__()
        self.view_padre = view_padre

    async def on_submit(self, interaction: discord.Interaction):
        texto = self.respuesta.value.strip().lower()
        self.view_padre.answered = True
        self.view_padre.resultado = self.view_padre.herramienta_correcta in texto
        for item in self.view_padre.children:
            item.disabled = True
        await interaction.response.edit_message(view=self.view_padre)
        self.view_padre.stop()

async def iniciar_trabajo_medico(interaction: discord.Interaction):
    user_id = interaction.user.id
    tipo_trabajo = "medico"

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
    if not consumir_energia(user_id, energia_req):
        await interaction.followup.send(
            "❌ **Tu energía cambió justo antes de entrar a quirófano.** Puede que otro trabajo la haya consumido primero. Revisa `/energia` e inténtalo de nuevo.",
            ephemeral=True
        )
        return

    await fase_previa_trabajo(interaction, user_id, tipo_trabajo)

    tiempo_limite = 15.0 if nivel >= 5 else 10.0
    fallos_permitidos = 1 if nivel >= 8 else 0

    situaciones = random.sample(SITUACIONES_MEDICAS, 3)

    usa_diagnostico_verbal = nivel >= 6
    indice_diagnostico_verbal = random.randint(0, 2) if usa_diagnostico_verbal else -1
    
    header = get_job_header(user_id, tipo_trabajo)
    embed_principal = discord.Embed(
        title="🏥 Quirófano Activo",
        description=f"{header}Lávate las manos, la operación está a punto de comenzar.",
        color=discord.Color.red()
    )
    msg = await interaction.followup.send(embed=embed_principal, wait=True)
    await asyncio.sleep(2)

    for i, sit in enumerate(situaciones):
        es_diagnostico_verbal = (i == indice_diagnostico_verbal)

        descripcion_fase = f"**Situación:** {sit['desc']}\n\nRápido, selecciona la herramienta correcta (Tienes {tiempo_limite}s)."
        if es_diagnostico_verbal:
            descripcion_fase = (
                f"**Situación:** {sit['desc']}\n\n"
                f"🗣️ **Diagnóstico verbal:** No hay botones con nombres esta vez. "
                f"Escribe qué herramienta se necesita (Tienes {tiempo_limite}s)."
            )

        embed = discord.Embed(
            title=f"⚕️ Fase {i+1}/3 de la Cirugía",
            description=descripcion_fase,
            color=discord.Color.blue()
        )

        if es_diagnostico_verbal:
            view = DiagnosticoView(user_id, sit["herramienta"], tiempo_limite)
        else:
            view = HerramientaMedicaView(user_id, sit["herramienta"], tiempo_limite)
        await msg.edit(embed=embed, view=view)
        await view.wait()
        
        if not view.resultado:
            if fallos_permitidos > 0:
                fallos_permitidos -= 1
                embed_salvado = discord.Embed(
                    title="⚠️ Error Médico",
                    description="Te equivocaste de herramienta, pero lograste estabilizarlo gracias a tu experiencia (Bisturí Láser).",
                    color=discord.Color.orange()
                )
                await msg.edit(embed=embed_salvado, view=None)
                await asyncio.sleep(2)
            else:
                embed_fail = discord.Embed(
                    title="💀 Negligencia Médica",
                    description="Usaste la herramienta equivocada o tardaste demasiado. El paciente ha fallecido.",
                    color=discord.Color.dark_grey()
                )
                await msg.edit(embed=embed_fail, view=None)
                add_experiencia_trabajo(user_id, tipo_trabajo, 4)
                return
        else:
            embed_success = discord.Embed(
                title="✅ Procedimiento Exitoso",
                description="Usaste la herramienta correcta a tiempo.",
                color=discord.Color.green()
            )
            await msg.edit(embed=embed_success, view=None)
            await asyncio.sleep(2)

    # Éxito
    recompensa_base = get_recompensa_trabajo(tipo_trabajo, user_id)
    recompensa = int(recompensa_base * random.uniform(0.9, 1.1))
    
    saldo_actual = get_balance(user_id)
    set_balance(user_id, saldo_actual + recompensa)
    registrar_transaccion(user_id, recompensa, "Trabajo: Médico")
    
    xp_ganada = 15
    resultado_xp = add_experiencia_trabajo(user_id, tipo_trabajo, xp_ganada)
    
    embed_final = discord.Embed(
        title="🏥 ¡Operación Completada!",
        description="El paciente está estable y en recuperación. ¡Buen trabajo, doc!",
        color=discord.Color.green()
    )
    embed_final.add_field(name="💰 Sueldo Cobrado", value=f"**{recompensa}** monedas")
    
    xp_msg = f"+{resultado_xp['xp_ganada_final']} XP"
    if resultado_xp['pocion_usada']:
        xp_msg += " (🧪 x1.5)"
    embed_final.add_field(name="✨ Experiencia", value=xp_msg)
    
    if resultado_xp['subio_nivel']:
        embed_final.add_field(
            name="🎉 ¡SUBISTE DE NIVEL!", 
            value=f"Ahora eres nivel **{resultado_xp['nivel_nuevo']}** de Médico.",
            inline=False
        )

    await msg.edit(embed=embed_final, view=None)
