import discord
import asyncio
import random
from src.db import get_balance, set_balance, registrar_transaccion
from .energia import consumir_energia, get_energia
from .niveles_trabajo import get_nivel_trabajo, add_experiencia_trabajo, get_energia_trabajo, get_recompensa_trabajo

RECETAS_QUIMICAS = {
    "Naranja 🟠": ["rojo", "amarillo"],
    "Verde 🟢": ["azul", "amarillo"],
    "Morado 🟣": ["rojo", "azul"],
    "Gris ⚪": ["blanco", "negro"],
    "Rosa 🌸": ["rojo", "blanco"],
    "Celeste 🧊": ["azul", "blanco"]
}

COLORES_BASE = [
    discord.SelectOption(label="Rojo", emoji="🔴", value="rojo"),
    discord.SelectOption(label="Azul", emoji="🔵", value="azul"),
    discord.SelectOption(label="Amarillo", emoji="🟡", value="amarillo"),
    discord.SelectOption(label="Blanco", emoji="⚪", value="blanco"),
    discord.SelectOption(label="Negro", emoji="⚫", value="negro")
]

class QuimicoSelect(discord.ui.Select):
    def __init__(self, tiene_pipeta):
        # Nivel 5 remueve los colores blanco y negro si no son necesarios
        # Para hacerlo dinámico, simplemente entregamos la lista.
        # En este minijuego, la "Pipeta" simplificará las opciones.
        opciones = COLORES_BASE.copy()
        if tiene_pipeta:
            opciones = [o for o in opciones if o.value in ["rojo", "azul", "amarillo"]]
            
        super().__init__(
            placeholder="Selecciona EXACTAMENTE 2 químicos",
            min_values=2,
            max_values=2,
            options=opciones
        )

    async def callback(self, interaction: discord.Interaction):
        view: CientificoView = self.view
        if interaction.user.id != view.user_id:
            await interaction.response.send_message("❌ No es tu experimento.", ephemeral=True)
            return

        view.seleccion = self.values
        for item in view.children:
            item.disabled = True
            
        await interaction.response.edit_message(view=view)
        view.stop()

class CientificoView(discord.ui.View):
    def __init__(self, user_id, tiene_pipeta):
        super().__init__(timeout=20)
        self.user_id = user_id
        self.seleccion = None
        self.add_item(QuimicoSelect(tiene_pipeta))

    async def on_timeout(self):
        self.seleccion = None
        for item in self.children:
            item.disabled = True

async def iniciar_trabajo_cientifico(interaction: discord.Interaction):
    user_id = interaction.user.id
    tipo_trabajo = "cientifico"

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

    tiene_pipeta = nivel >= 5
    tiene_catalizador = nivel >= 8

    # Si tiene pipeta, solo le pediremos recetas que usen colores primarios
    recetas_disponibles = list(RECETAS_QUIMICAS.keys())
    if tiene_pipeta:
        recetas_disponibles = ["Naranja 🟠", "Verde 🟢", "Morado 🟣"]

    objetivo = random.choice(recetas_disponibles)
    ingredientes_correctos = RECETAS_QUIMICAS[objetivo]

    embed = discord.Embed(
        title="🔬 Laboratorio Químico",
        description=f"El supervisor necesita que crees una poción de color **{objetivo}**.\n\nSelecciona los 2 ingredientes primarios en el menú de abajo. Tienes 20 segundos.",
        color=discord.Color.green()
    )
    
    view = CientificoView(user_id, tiene_pipeta)
    msg = await interaction.followup.send(embed=embed, view=view, wait=True)
    
    await view.wait()
    
    if view.seleccion is None:
        embed_fail = discord.Embed(
            title="💥 ¡KABOOM!",
            description="Tardaste demasiado y la mezcla explotó.",
            color=discord.Color.red()
        )
        await msg.edit(embed=embed_fail, view=None)
        add_experiencia_trabajo(user_id, tipo_trabajo, 2)
        return

    # Comprobar si la selección es correcta (el orden no importa)
    es_correcto = set(view.seleccion) == set(ingredientes_correctos)

    if es_correcto:
        recompensa_base = get_recompensa_trabajo(tipo_trabajo, user_id)
        if tiene_catalizador:
            recompensa_base *= 2 # Catalizador dobla la recompensa
            
        recompensa = int(recompensa_base * random.uniform(0.9, 1.1))
        
        saldo_actual = get_balance(user_id)
        set_balance(user_id, saldo_actual + recompensa)
        registrar_transaccion(user_id, recompensa, "Trabajo: Científico")
        
        xp_ganada = 12
        resultado_xp = add_experiencia_trabajo(user_id, tipo_trabajo, xp_ganada)
        
        titulo_exito = "🧪 ¡Fórmula Exitosa!"
        if tiene_catalizador:
            titulo_exito = "🧪 ¡Fórmula Exitosa! (Catalizador: x2)"
            
        embed_final = discord.Embed(
            title=titulo_exito,
            description=f"Mezclaste correctamente {view.seleccion[0]} y {view.seleccion[1]} para crear {objetivo}.",
            color=discord.Color.green()
        )
        embed_final.add_field(name="💰 Pago de la Patente", value=f"**{recompensa}** monedas")
        
        xp_msg = f"+{resultado_xp['xp_ganada_final']} XP"
        if resultado_xp['pocion_usada']:
            xp_msg += " (🧪 x1.5)"
        embed_final.add_field(name="✨ Experiencia", value=xp_msg)
        
        if resultado_xp['subio_nivel']:
            embed_final.add_field(
                name="🎉 ¡SUBISTE DE NIVEL!", 
                value=f"Ahora eres nivel **{resultado_xp['nivel_nuevo']}** de Científico.",
                inline=False
            )

        await msg.edit(embed=embed_final, view=None)
    else:
        embed_fail = discord.Embed(
            title="🤢 Mezcla Tóxica",
            description=f"Mezclaste {view.seleccion[0]} y {view.seleccion[1]} y creaste un ácido inútil. El supervisor te ha regañado.",
            color=discord.Color.dark_green()
        )
        await msg.edit(embed=embed_fail, view=None)
        add_experiencia_trabajo(user_id, tipo_trabajo, 4)
