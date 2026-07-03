import discord
import asyncio
import random
from src.db import get_balance, set_balance, registrar_transaccion
from .energia import consumir_energia, get_energia
from .niveles_trabajo import get_nivel_trabajo, add_experiencia_trabajo, get_energia_trabajo, get_recompensa_trabajo, get_job_header
from .job_fx import fase_previa_trabajo

EVENTOS_PILOTO = [
    {
        "nombre": "🌩️ Tormenta Eléctrica Severa",
        "descripcion": "¡Los relámpagos amenazan los sistemas de navegación!",
        "correcto": "radar",
        "botones": [
            ("Activar Radar", "radar", discord.ButtonStyle.primary),
            ("Apagar Motores", "motores", discord.ButtonStyle.danger),
            ("Maniobra Evasiva", "evadir", discord.ButtonStyle.secondary)
        ]
    },
    {
        "nombre": "🛩️ Intercepción de Cazas",
        "descripcion": "¡Jets desconocidos se acercan a toda velocidad!",
        "correcto": "evadir",
        "botones": [
            ("Contactar Torre", "torre", discord.ButtonStyle.primary),
            ("Maniobra Evasiva", "evadir", discord.ButtonStyle.danger),
            ("Activar Radar", "radar", discord.ButtonStyle.secondary)
        ]
    },
    {
        "nombre": "🔥 Falla de Motor Crítica",
        "descripcion": "¡El motor derecho está en llamas!",
        "correcto": "motores",
        "botones": [
            ("Maniobra Evasiva", "evadir", discord.ButtonStyle.secondary),
            ("Activar Radar", "radar", discord.ButtonStyle.primary),
            ("Extintor / Reiniciar", "motores", discord.ButtonStyle.danger)
        ]
    },
    {
        "nombre": "📉 Caída de Altitud",
        "descripcion": "¡Entramos en una bolsa de aire masiva, estamos cayendo!",
        "correcto": "altitud",
        "botones": [
            ("Subir Altitud", "altitud", discord.ButtonStyle.danger),
            ("Activar Radar", "radar", discord.ButtonStyle.secondary),
            ("Contactar Torre", "torre", discord.ButtonStyle.primary)
        ]
    }
]

RUTAS_VUELO = {
    "corta": {
        "nombre": "Ruta Corta (Directa)",
        "num_eventos": 2,
        "multiplicador": 0.8,
        "descripcion": "Menos emergencias en el aire, pero el pago es menor."
    },
    "larga": {
        "nombre": "Ruta Larga (Rentable)",
        "num_eventos": 4,
        "multiplicador": 1.35,
        "descripcion": "Cruzas zonas de mayor tráfico y clima inestable, pero pagan mucho mejor."
    }
}

class RutaVueloView(discord.ui.View):
    """Selección de plan de vuelo antes de despegar: define cuántas
    emergencias enfrentarás y cuánto multiplica el pago final."""

    def __init__(self, user_id: int):
        super().__init__(timeout=20.0)
        self.user_id = user_id
        self.ruta = None
        self.resuelto = False

        select = discord.ui.Select(
            placeholder="Elige tu plan de vuelo...",
            min_values=1,
            max_values=1,
            options=[
                discord.SelectOption(
                    label=RUTAS_VUELO["corta"]["nombre"],
                    value="corta",
                    emoji="🛬",
                    description="2 emergencias en vuelo. Pago x0.8"
                ),
                discord.SelectOption(
                    label=RUTAS_VUELO["larga"]["nombre"],
                    value="larga",
                    emoji="🌍",
                    description="4 emergencias en vuelo. Pago x1.35"
                ),
            ]
        )
        select.callback = self._callback
        self.add_item(select)

    async def _callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ No es tu vuelo.", ephemeral=True)
            return
        if self.resuelto:
            await interaction.response.defer()
            return
        self.resuelto = True
        self.ruta = interaction.data["values"][0]
        for item in self.children:
            item.disabled = True
        await interaction.response.defer()
        self.stop()

    async def on_timeout(self):
        if not self.resuelto:
            self.resuelto = True
            self.ruta = "corta"  # opción segura por defecto si no decide a tiempo
            for item in self.children:
                item.disabled = True

class EventoPilotoView(discord.ui.View):
    def __init__(self, user_id, evento, tiempo_limite=7.0):
        super().__init__(timeout=tiempo_limite)
        self.user_id = user_id
        self.evento = evento
        self.resultado = None # True si acierta, False si falla, None si timeout
        self.clicked = False

        # Mezclar botones aleatoriamente
        botones = evento["botones"].copy()
        random.shuffle(botones)

        for label, custom_id, style in botones:
            btn = discord.ui.Button(label=label, style=style, custom_id=custom_id)
            btn.callback = self.crear_callback(custom_id)
            self.add_item(btn)

    def crear_callback(self, custom_id):
        async def callback(interaction: discord.Interaction):
            if interaction.user.id != self.user_id:
                await interaction.response.send_message("❌ No es tu vuelo.", ephemeral=True)
                return
            
            if self.clicked:
                return

            self.clicked = True
            self.resultado = (custom_id == self.evento["correcto"])
            
            # Deshabilitar botones
            for item in self.children:
                item.disabled = True
            
            await interaction.response.edit_message(view=self)
            self.stop()
            
        return callback

    async def on_timeout(self):
        self.clicked = True
        self.resultado = False # Timeout = Falla
        for item in self.children:
            item.disabled = True

async def iniciar_trabajo_piloto(interaction: discord.Interaction):
    user_id = interaction.user.id
    tipo_trabajo = "piloto"

    # Verificar nivel
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

    # Iniciar minijuego
    await interaction.response.defer()
    
    # Consumir energía (atómico: si otro trabajo en paralelo ya la gastó, esto falla)
    if not consumir_energia(user_id, energia_req):
        await interaction.followup.send(
            "❌ **Tu energía cambió justo antes de despegar.** Puede que otro trabajo la haya consumido primero. Revisa `/energia` e inténtalo de nuevo.",
            ephemeral=True
        )
        return

    # Evento opcional: un pasajero VIP puede aparecer antes del despegue
    await fase_previa_trabajo(interaction, user_id, tipo_trabajo)

    # Elegir plan de vuelo: define cuántas emergencias habrá y el multiplicador de pago
    ruta_view = RutaVueloView(user_id)
    embed_ruta = discord.Embed(
        title="🗺️ Plan de Vuelo",
        description="Antes de despegar, define la ruta:\n\n"
                     f"🛬 **{RUTAS_VUELO['corta']['nombre']}:** {RUTAS_VUELO['corta']['descripcion']}\n"
                     f"🌍 **{RUTAS_VUELO['larga']['nombre']}:** {RUTAS_VUELO['larga']['descripcion']}",
        color=discord.Color.blue()
    )
    msg_ruta = await interaction.followup.send(embed=embed_ruta, view=ruta_view, wait=True)
    await ruta_view.wait()

    ruta_elegida = RUTAS_VUELO[ruta_view.ruta]
    num_eventos = ruta_elegida["num_eventos"]
    multiplicador_ruta = ruta_elegida["multiplicador"]

    # Seleccionar los eventos aleatorios según la ruta
    eventos_vuelo = random.sample(EVENTOS_PILOTO, min(num_eventos, len(EVENTOS_PILOTO)))
    
    # Bonificaciones por nivel
    tiene_radar = nivel >= 5
    tiempo_limite = 8.0 if nivel >= 8 else 6.0

    header = get_job_header(user_id, tipo_trabajo)
    embed_principal = discord.Embed(
        title="🛫 Vuelo Comercial 909",
        description=f"{header}Elegiste la **{ruta_elegida['nombre']}**. El avión ha despegado. ¡Mantente alerta a los paneles de control!",
        color=discord.Color.blue()
    )
    msg = await msg_ruta.edit(embed=embed_principal, view=None)
    await asyncio.sleep(2)

    for i, evento in enumerate(eventos_vuelo):
        # Si tiene la bonificación de Radar y es Tormenta, la evita automáticamente (1 vez)
        if tiene_radar and evento["nombre"] == "🌩️ Tormenta Eléctrica Severa":
            embed = discord.Embed(
                title="📡 ¡Radar Meteorológico Activado!",
                description="Gracias a tu equipo avanzado, detectaste la tormenta y la evadiste automáticamente.",
                color=discord.Color.green()
            )
            await msg.edit(embed=embed, view=None)
            tiene_radar = False # Se usa 1 vez por vuelo
            await asyncio.sleep(2)
            continue

        embed = discord.Embed(
            title=f"⚠️ EMERGENCIA {i+1}/{len(eventos_vuelo)}: {evento['nombre']}",
            description=f"{evento['descripcion']}\n\n⏳ Tienes {tiempo_limite} segundos para reaccionar.",
            color=discord.Color.red()
        )
        
        view = EventoPilotoView(user_id, evento, tiempo_limite)
        await msg.edit(embed=embed, view=view)
        
        # Esperar resultado
        await view.wait()
        
        if not view.resultado:
            # Falló o timeout
            embed_fail = discord.Embed(
                title="💥 ¡EL AVIÓN SE HA ESTRELLADO!",
                description="Tomaste la decisión equivocada o fuiste muy lento. La misión ha fallado.",
                color=discord.Color.dark_red()
            )
            await msg.edit(embed=embed_fail, view=None)
            
            # Dar un poquito de XP por intento fallido
            add_experiencia_trabajo(user_id, tipo_trabajo, 5)
            return

        # Éxito en este evento
        embed_success = discord.Embed(
            title="✅ ¡Peligro Evadido!",
            description="Reaccionaste a tiempo. El vuelo continúa...",
            color=discord.Color.green()
        )
        await msg.edit(embed=embed_success, view=None)
        await asyncio.sleep(2)

    # Si llega aquí, completó los eventos de la ruta elegida con éxito
    recompensa_base = get_recompensa_trabajo(tipo_trabajo, user_id)
    # Variación aleatoria de ±15%, ajustada por el multiplicador de la ruta elegida
    recompensa = int(recompensa_base * random.uniform(0.85, 1.15) * multiplicador_ruta)
    
    saldo_actual = get_balance(user_id)
    set_balance(user_id, saldo_actual + recompensa)
    registrar_transaccion(user_id, recompensa, "Trabajo: Piloto")
    
    xp_ganada = 25
    resultado_xp = add_experiencia_trabajo(user_id, tipo_trabajo, xp_ganada)
    
    embed_final = discord.Embed(
        title="🛬 ¡Aterrizaje Exitoso!",
        description="Has completado el vuelo y entregado la carga a salvo.",
        color=discord.Color.gold()
    )
    embed_final.add_field(name="🗺️ Ruta", value=ruta_elegida['nombre'])
    embed_final.add_field(name="💰 Pago Recibido", value=f"**{recompensa}** monedas")
    
    xp_msg = f"+{resultado_xp['xp_ganada_final']} XP"
    if resultado_xp['pocion_usada']:
        xp_msg += " (🧪 x1.5)"
    embed_final.add_field(name="✨ Experiencia", value=xp_msg)
    
    if resultado_xp['subio_nivel']:
        embed_final.add_field(
            name="🎉 ¡SUBISTE DE NIVEL!", 
            value=f"Ahora eres nivel **{resultado_xp['nivel_nuevo']}** de Piloto.",
            inline=False
        )

    await msg.edit(embed=embed_final, view=None)
