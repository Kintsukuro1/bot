import discord
import asyncio
import random
from src.db import get_balance, set_balance, registrar_transaccion
from .energia import consumir_energia, get_energia
from .niveles_trabajo import get_nivel_trabajo, add_experiencia_trabajo, get_energia_trabajo, get_recompensa_trabajo, get_job_header, TIPOS_TRABAJO
from .job_fx import tal_vez_cliente_especial

# Reactivos posibles y sus pesos (impacto en la inestabilidad)
REACTIVOS = {
    "Extracto Carmesí 🔴": {"inestabilidad": 20, "afinidad": ["Agua Destilada 💧", "Polvo Estelar ✨"]},
    "Líquido Fluorescente 🟢": {"inestabilidad": 35, "afinidad": ["Polvo Estelar ✨"]},
    "Isótopo Volátil 🟣": {"inestabilidad": 50, "afinidad": []},
    "Agua Destilada 💧": {"inestabilidad": 5, "afinidad": ["Extracto Carmesí 🔴"]},
    "Polvo Estelar ✨": {"inestabilidad": 15, "afinidad": ["Líquido Fluorescente 🟢", "Extracto Carmesí 🔴"]},
    "Cristal Neutro ⚪": {"inestabilidad": 10, "afinidad": ["Isótopo Volátil 🟣"]} # El cristal ayuda a mitigar isótopos
}

class CientificoGame:
    def __init__(self, user_id, nivel):
        self.user_id = user_id
        self.nivel = nivel
        self.tiene_analizador = nivel >= 5
        self.tiene_estabilizador = nivel >= 8
        self.rondas_totales = 4 if nivel >= 3 else 3
        
        self.ronda_actual = 1
        self.inestabilidad = 0
        self.reactivo_anterior = None
        self.estabilizador_usado = False
        self.analizador_usado = False
        
        self.status = "Jugando" # Jugando, Ganado, Explotado, Timeout
        
    def aplicar_reactivo(self, nombre_reactivo):
        datos = REACTIVOS[nombre_reactivo]
        base_instability = datos["inestabilidad"]
        
        # Calcular sinergias
        if self.reactivo_anterior and self.reactivo_anterior in datos["afinidad"]:
            base_instability = max(0, base_instability - 10) # Sinergia reduce inestabilidad añadida
            
        # El Isótopo Volátil explota casi seguro si se mezcla con otro Isótopo
        if self.reactivo_anterior == "Isótopo Volátil 🟣" and nombre_reactivo == "Isótopo Volátil 🟣":
            base_instability = 100
            
        self.inestabilidad += base_instability
        self.reactivo_anterior = nombre_reactivo
        
        if self.inestabilidad >= 100:
            self.status = "Explotado"
        elif self.ronda_actual >= self.rondas_totales:
            self.status = "Ganado"
        else:
            self.ronda_actual += 1

class CientificoView(discord.ui.View):
    def __init__(self, game: CientificoGame):
        super().__init__(timeout=30)
        self.game = game
        self.accion_realizada = False
        self.generar_botones()
        
    def generar_botones(self):
        self.clear_items()
        
        # Elegir 3 reactivos al azar para esta ronda
        opciones_ronda = random.sample(list(REACTIVOS.keys()), 3)
        
        for r in opciones_ronda:
            btn = discord.ui.Button(label=r, style=discord.ButtonStyle.primary)
            btn.callback = self.crear_callback_reactivo(r)
            self.add_item(btn)
            
        if self.game.tiene_estabilizador and not self.game.estabilizador_usado:
            btn_est = discord.ui.Button(label="❄️ Estabilizar Térmicamente", style=discord.ButtonStyle.success, row=1)
            btn_est.callback = self.estabilizar_callback
            self.add_item(btn_est)
            
        if self.game.tiene_analizador and not self.game.analizador_usado:
            btn_ana = discord.ui.Button(label="🔍 Analizar Sinergia", style=discord.ButtonStyle.secondary, row=1)
            btn_ana.callback = self.analizar_callback
            self.add_item(btn_ana)

    def crear_callback_reactivo(self, reactivo):
        async def callback(interaction: discord.Interaction):
            if interaction.user.id != self.game.user_id:
                await interaction.response.send_message("❌ Este no es tu laboratorio.", ephemeral=True)
                return
                
            if self.accion_realizada: return
            self.accion_realizada = True
            await interaction.response.defer()
            
            self.game.aplicar_reactivo(reactivo)
            self.stop()
        return callback
        
    async def estabilizar_callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.game.user_id:
            return
            
        if self.accion_realizada: return
        self.accion_realizada = True
        await interaction.response.defer()
        
        self.game.estabilizador_usado = True
        self.game.inestabilidad = max(0, self.game.inestabilidad - 30)
        self.stop()
        
    async def analizar_callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.game.user_id:
            return
            
        if self.accion_realizada: return
        # No avanza la ronda, solo da información y refresca la vista sin el botón
        self.game.analizador_usado = True
        
        afinidad = "Ninguna conocida"
        if self.game.reactivo_anterior:
            # Buscar qué reactivos tienen afinidad con el anterior
            afines = [r for r, d in REACTIVOS.items() if self.game.reactivo_anterior in d["afinidad"]]
            if afines:
                afinidad = ", ".join(afines)
        else:
            afinidad = "Comienza con Agua Destilada para ir seguro."
            
        await interaction.response.send_message(f"🧠 **Análisis de Sinergia:** Si el reactivo anterior fue {self.game.reactivo_anterior or 'NADA'}, los reactivos seguros son: {afinidad}", ephemeral=True)
        
        self.generar_botones()
        await interaction.edit_original_response(view=self)
        self.accion_realizada = False

    async def on_timeout(self):
        if not self.accion_realizada:
            self.game.status = "Timeout"
            self.stop()

def generar_embed(game: CientificoGame):
    header = get_job_header(game.user_id, "cientifico")
    color = discord.Color.blue()
    
    if game.inestabilidad > 70:
        color = discord.Color.orange()
    if game.inestabilidad >= 100:
        color = discord.Color.red()
        
    embed = discord.Embed(
        title="🔬 Laboratorio Químico",
        description=f"{header}\nMezcla reactivos para completar el experimento sin que la inestabilidad llegue al 100%.",
        color=color
    )
    
    barra = "🟥" * (game.inestabilidad // 10) + "⬜" * (10 - (game.inestabilidad // 10))
    
    embed.add_field(name="Ronda", value=f"{game.ronda_actual} / {game.rondas_totales}", inline=True)
    embed.add_field(name="Último Reactivo", value=game.reactivo_anterior or "Ninguno", inline=True)
    embed.add_field(name="Inestabilidad", value=f"{game.inestabilidad}%\n{barra}", inline=False)
    
    return embed

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
    if not consumir_energia(user_id, energia_req):
        await interaction.followup.send(
            "❌ **Tu energía cambió justo antes de entrar al laboratorio.** Puede que otro trabajo la haya consumido primero. Revisa `/energia` e inténtalo de nuevo.",
            ephemeral=True
        )
        return

    await tal_vez_cliente_especial(interaction, user_id, tipo_trabajo)
    
    game = CientificoGame(user_id, nivel)
    
    while game.status == "Jugando":
        embed = generar_embed(game)
        view = CientificoView(game)
        
        try:
            await interaction.edit_original_response(embed=embed, view=view)
        except:
            break
            
        await view.wait()
        
        if game.status != "Jugando":
            break
            
    # Resolución del juego
    embed = generar_embed(game)
    view = discord.ui.View() # Empty view
    
    if game.status == "Ganado":
        recompensa = get_recompensa_trabajo(tipo_trabajo, user_id)
        xp_ganada = TIPOS_TRABAJO[tipo_trabajo].get('xp_por_trabajo', 10)
        
        if game.inestabilidad == 0:
            recompensa = int(recompensa * 1.5) # Bono por perfección
            embed.description = "🌟 **¡SÍNTESIS PERFECTA!** Lograste una mezcla con 0% de inestabilidad."
        else:
            embed.description = "✅ **Experimento Exitoso.** Has logrado sintetizar la fórmula."
            
        set_balance(user_id, get_balance(user_id) + recompensa)
        registrar_transaccion(user_id, recompensa, "Sueldo Científico")
        add_experiencia_trabajo(user_id, tipo_trabajo, xp_ganada)
        
        embed.color = discord.Color.green()
        embed.add_field(name="Ganancia", value=f"💰 {recompensa} monedas\n📈 {xp_ganada} XP", inline=False)
        
    elif game.status == "Explotado":
        embed.description = "💥 **¡BOOOM!** El nivel de inestabilidad superó el límite."
        embed.color = discord.Color.red()
        
        # Recompensa parcial si pasó de la ronda 1
        if game.ronda_actual > 1:
            recompensa = get_recompensa_trabajo(tipo_trabajo, user_id)
            xp_ganada = TIPOS_TRABAJO[tipo_trabajo].get('xp_por_trabajo', 10)
            recompensa_parcial = int(recompensa * 0.3 * (game.ronda_actual - 1))
            xp_parcial = max(1, int(xp_ganada * 0.3))
            
            set_balance(user_id, get_balance(user_id) + recompensa_parcial)
            registrar_transaccion(user_id, recompensa_parcial, "Salvamento Científico")
            add_experiencia_trabajo(user_id, tipo_trabajo, xp_parcial)
            
            embed.add_field(name="Salvamento de Datos", value=f"Lograste rescatar algo de la investigación.\n💰 {recompensa_parcial} monedas\n📈 {xp_parcial} XP", inline=False)
        else:
            embed.add_field(name="Fracaso Total", value="No se salvó nada de la explosión.", inline=False)
            
    elif game.status == "Timeout":
        embed.description = "⏳ **El experimento se arruinó por exposición prolongada al aire.**"
        embed.color = discord.Color.dark_grey()
        
    try:
        await interaction.edit_original_response(embed=embed, view=view)
    except:
        pass
