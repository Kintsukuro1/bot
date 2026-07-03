import discord
import asyncio
import random
import time
from src.db import get_balance, set_balance, registrar_transaccion, deduct_balance
from .energia import consumir_energia, get_energia
from .niveles_trabajo import get_nivel_trabajo, add_experiencia_trabajo, get_energia_trabajo, get_recompensa_trabajo, get_job_header
from .job_fx import tal_vez_cliente_especial

class LadronModal(discord.ui.Modal, title="Hackeo de Bóveda"):
    codigo_input = discord.ui.TextInput(
        label="Introduce el PIN",
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
        self.view_parent.tiempo_submit = time.time()
        self.view_parent.last_interaction = interaction
        await interaction.response.defer()
        self.view_parent.stop()

class LadronHackView(discord.ui.View):
    def __init__(self, user_id, tiempo_limite):
        super().__init__(timeout=tiempo_limite)
        self.user_id = user_id
        self.input_recibido = None
        self.tiempo_submit = 0
        self.last_interaction = None

    @discord.ui.button(label="Introducir PIN", style=discord.ButtonStyle.primary, emoji="🔓")
    async def btn_pin(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ No es tu atraco.", ephemeral=True)
            return
        await interaction.response.send_modal(LadronModal(self))

    async def on_timeout(self):
        self.input_recibido = ""

class LadronGanzuaView(discord.ui.View):
    def __init__(self, user_id):
        super().__init__(timeout=15)
        self.user_id = user_id
        self.usar_ganzua = False
        self.last_interaction = None

    @discord.ui.button(label="Usar Ganzúa Electrónica", style=discord.ButtonStyle.success, emoji="🛠️")
    async def btn_ganzua(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            return
        self.usar_ganzua = True
        self.last_interaction = interaction
        await interaction.response.defer()
        self.stop()
        
    @discord.ui.button(label="Rendirse", style=discord.ButtonStyle.danger, emoji="🏳️")
    async def btn_rendirse(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            return
        self.usar_ganzua = False
        self.last_interaction = interaction
        await interaction.response.defer()
        self.stop()

class LadronRutaView(discord.ui.View):
    def __init__(self, user_id):
        super().__init__(timeout=30)
        self.user_id = user_id
        self.ruta = None
        self.last_interaction = None

    @discord.ui.button(label="Ruta Sigilosa", style=discord.ButtonStyle.primary, emoji="🥷")
    async def btn_sigilo(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            return
        self.ruta = "sigilo"
        self.last_interaction = interaction
        await interaction.response.defer()
        self.stop()

    @discord.ui.button(label="Fuerza Bruta", style=discord.ButtonStyle.danger, emoji="💥")
    async def btn_fuerza(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            return
        self.ruta = "fuerza"
        self.last_interaction = interaction
        await interaction.response.defer()
        self.stop()

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

    tiene_ganzua = nivel >= 5
    tiene_penetracion = nivel >= 8
    
    header = get_job_header(user_id, tipo_trabajo)
    
    ruta_view = LadronRutaView(user_id)
    embed_ruta = discord.Embed(
        title="🏦 Asalto al Banco Central",
        description=f"{header}Elige tu método de infiltración:\n\n🥷 **Sigilo:** Tienes tiempo para memorizar el PIN, pero si fallas irás a la cárcel.\n💥 **Fuerza Bruta:** Escribe el PIN al revés lo más rápido posible. Máximo riesgo, máxima ganancia.",
        color=discord.Color.dark_theme()
    )
    await interaction.response.send_message(embed=embed_ruta, view=ruta_view)
    await ruta_view.wait()
    
    latest_interaction = interaction
    if ruta_view.last_interaction:
        latest_interaction = ruta_view.last_interaction

    if ruta_view.ruta is None:
        await latest_interaction.edit_original_response(content="⏳ Tardaste mucho en decidir. Abortando atraco.", embed=None, view=None)
        return
        
    if not consumir_energia(user_id, energia_req):
        await latest_interaction.edit_original_response(
            content="❌ Tu energía cambió justo antes de entrar. Puede que otro trabajo la haya consumido primero.",
            embed=None, view=None
        )
        return

    await tal_vez_cliente_especial(latest_interaction, user_id, tipo_trabajo)
    
    len_pin = 4 if tiene_penetracion else 5
    pin_secreto = "".join([str(random.randint(0, 9)) for _ in range(len_pin)])
    
    if ruta_view.ruta == "sigilo":
        embed_juego = discord.Embed(
            title="🥷 Infiltración Sigilosa",
            description=f"Memoriza este PIN para desactivar la alarma:\n\n# **{pin_secreto}**",
            color=discord.Color.blue()
        )
        tiempo_mostrar = 5 if tiene_penetracion else 3
        embed_juego.set_footer(text=f"El PIN desaparecerá en {tiempo_mostrar} segundos...")
        await latest_interaction.edit_original_response(embed=embed_juego, view=None)
        
        await asyncio.sleep(tiempo_mostrar)
        
        embed_oculto = discord.Embed(
            title="🥷 Panel Bloqueado",
            description="¡Introduce el PIN de memoria!",
            color=discord.Color.orange()
        )
        hack_view = LadronHackView(user_id, 20)
        await latest_interaction.edit_original_response(embed=embed_oculto, view=hack_view)
        
        await hack_view.wait()
        if hack_view.last_interaction:
            latest_interaction = hack_view.last_interaction
        respuesta_correcta = pin_secreto
        multiplicador_pago = random.uniform(1.0, 1.3)
        
    else: # Fuerza Bruta
        pin_inverso = pin_secreto[::-1]
        embed_juego = discord.Embed(
            title="💥 Fuerza Bruta",
            description=f"¡RÁPIDO! Escribe este PIN **AL REVÉS** antes de que suene la alarma:\n\n# **{pin_secreto}**",
            color=discord.Color.red()
        )
        embed_juego.set_footer(text="Tienes exactamente 10 segundos desde AHORA.")
        
        hack_view = LadronHackView(user_id, 10)
        start_time = time.time()
        await latest_interaction.edit_original_response(embed=embed_juego, view=hack_view)
        
        await hack_view.wait()
        if hack_view.last_interaction:
            latest_interaction = hack_view.last_interaction
            
        # Validación extra de tiempo para Fuerza Bruta
        if hack_view.input_recibido and (hack_view.tiempo_submit - start_time) > 10.5:
            hack_view.input_recibido = "" # Tardó mucho
            
        respuesta_correcta = pin_inverso
        multiplicador_pago = random.uniform(1.5, 2.0)

    # Evaluación de resultados
    from .niveles_trabajo import TIPOS_TRABAJO
    recompensa_base = get_recompensa_trabajo(tipo_trabajo, user_id)
    xp_ganada = TIPOS_TRABAJO[tipo_trabajo].get('xp_por_trabajo', 10)
    
    if hack_view.input_recibido == respuesta_correcta:
        # ÉXITO
        recompensa = int(recompensa_base * multiplicador_pago)
        set_balance(user_id, get_balance(user_id) + recompensa)
        registrar_transaccion(user_id, recompensa, "Atraco al Banco (Éxito)")
        add_experiencia_trabajo(user_id, tipo_trabajo, xp_ganada)
        
        embed_final = discord.Embed(
            title="✅ Atraco Exitoso",
            description=f"Lograste abrir la bóveda y escapar con el botín.\n\n💰 **Ganancia:** {recompensa} monedas\n📈 **XP:** {xp_ganada}",
            color=discord.Color.green()
        )
        await latest_interaction.edit_original_response(embed=embed_final, view=None)
        
    else:
        # FALLO
        if tiene_ganzua:
            embed_fallo = discord.Embed(
                title="🚨 ¡Alarma Activada!",
                description="Te equivocaste de PIN o tardaste demasiado.\nTienes una **Ganzúa Electrónica**, ¿quieres usarla para escapar sin pagar multa?",
                color=discord.Color.orange()
            )
            ganzua_view = LadronGanzuaView(user_id)
            await latest_interaction.edit_original_response(embed=embed_fallo, view=ganzua_view)
            await ganzua_view.wait()
            if ganzua_view.last_interaction:
                latest_interaction = ganzua_view.last_interaction
            
            if ganzua_view.usar_ganzua:
                embed_escapo = discord.Embed(
                    title="🏃 Escape Exitoso",
                    description="Usaste tu Ganzúa Electrónica para forzar una salida. No ganaste nada, pero tampoco pagaste multa.",
                    color=discord.Color.dark_gray()
                )
                add_experiencia_trabajo(user_id, tipo_trabajo, int(xp_ganada * 0.2))
                await latest_interaction.edit_original_response(embed=embed_escapo, view=None)
                return
                
        # Arrestado
        multa = int(recompensa_base * 0.5)
        saldo = get_balance(user_id)
        if saldo < multa:
            multa = saldo
        deduct_balance(user_id, multa)
        registrar_transaccion(user_id, -multa, "Multa por Arresto")
        
        embed_arresto = discord.Embed(
            title="👮 ¡Arrestado!",
            description=f"Fallaste el atraco. La policía te atrapó.\n\n💸 **Multa Pagada:** {multa} monedas.",
            color=discord.Color.red()
        )
        await latest_interaction.edit_original_response(embed=embed_arresto, view=None)
