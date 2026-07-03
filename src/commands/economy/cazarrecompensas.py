import discord
import asyncio
import random
from src.db import get_balance, set_balance, registrar_transaccion
from .energia import consumir_energia, get_energia
from .niveles_trabajo import get_nivel_trabajo, add_experiencia_trabajo, get_energia_trabajo, get_recompensa_trabajo, get_job_header, TIPOS_TRABAJO
from .job_fx import tal_vez_cliente_especial

def generar_pistas(r, c):
    pistas = []
    
    # Pistas de fila
    pistas.append(f"El fugitivo fue visto en la fila {r+1}.")
    pistas.append(f"Estamos seguros de que NO está en la fila {(r+1)%3+1}.")
    
    # Pistas de columna
    pistas.append(f"Las cámaras lo ubicaron en la columna {c+1}.")
    pistas.append(f"No hay rastros de él en la columna {(c+1)%3+1}.")
    
    # Pistas de posición
    esquinas = [(0,0), (0,2), (2,0), (2,2)]
    bordes = [(0,1), (1,0), (1,2), (2,1)]
    centro = (1,1)
    
    if (r, c) in esquinas:
        pistas.append("Acorralado en una de las 4 esquinas de la zona.")
    elif (r, c) in bordes:
        pistas.append("Se esconde en uno de los bordes del mapa, pero no en una esquina.")
    elif (r, c) == centro:
        pistas.append("Está justo en el centro de la zona de búsqueda.")
        
    if (r, c) != centro:
        pistas.append("Sabemos que no está en el centro.")
        
    random.shuffle(pistas)
    return pistas[:2]

class CapturaQTEView(discord.ui.View):
    def __init__(self, user_id):
        super().__init__(timeout=4.0) # 4 segundos para reaccionar
        self.user_id = user_id
        self.capturado = False
        self.last_interaction = None

    @discord.ui.button(label="¡ATRAPAR!", style=discord.ButtonStyle.danger, emoji="🕸️")
    async def btn_atrapar(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            return
        
        self.capturado = True
        self.last_interaction = interaction
        await interaction.response.defer()
        self.stop()

class PerfiladoGridView(discord.ui.View):
    def __init__(self, user_id, intentos, target_r, target_c):
        super().__init__(timeout=45)
        self.user_id = user_id
        self.intentos = intentos
        self.max_intentos = intentos
        self.target_r = target_r
        self.target_c = target_c
        self.estado = "Jugando" # Jugando, Encontrado, Fallado, Timeout
        self.last_interaction = None
        
        for row in range(3):
            for col in range(3):
                custom_id = f"grid_{row}_{col}"
                btn = discord.ui.Button(label="?", style=discord.ButtonStyle.secondary, custom_id=custom_id, row=row)
                btn.callback = self.crear_callback(row, col, btn)
                self.add_item(btn)

    def crear_callback(self, row, col, button: discord.ui.Button):
        async def callback(interaction: discord.Interaction):
            if interaction.user.id != self.user_id:
                await interaction.response.send_message("❌ Esta no es tu misión.", ephemeral=True)
                return

            button.disabled = True
            
            if row == self.target_r and col == self.target_c:
                button.style = discord.ButtonStyle.success
                button.label = "¡AQUÍ!"
                button.emoji = "🎯"
                self.estado = "Encontrado"
                
                for item in self.children:
                    item.disabled = True
                    
                self.last_interaction = interaction
                await interaction.response.defer()
                self.stop()
            else:
                self.intentos -= 1
                button.style = discord.ButtonStyle.danger
                button.label = "Vacío"
                
                if self.intentos <= 0:
                    self.estado = "Fallado"
                    for item in self.children:
                        item.disabled = True
                    self.last_interaction = interaction
                    await interaction.response.defer()
                    self.stop()
                else:
                    await interaction.response.edit_message(content=f"**Intentos restantes:** {self.intentos}/{self.max_intentos}", view=self)
                    
        return callback

    async def on_timeout(self):
        if self.estado == "Jugando":
            self.estado = "Timeout"
            for item in self.children:
                item.disabled = True

async def iniciar_trabajo_cazarrecompensas(interaction: discord.Interaction):
    user_id = interaction.user.id
    tipo_trabajo = "cazarrecompensas"

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
            "❌ **Tu energía cambió justo antes de salir a la caza.** Puede que otro trabajo la haya consumido primero. Revisa `/energia` e inténtalo de nuevo.",
            ephemeral=True
        )
        return

    await tal_vez_cliente_especial(interaction, user_id, tipo_trabajo)

    tiene_infrarrojos = nivel >= 5
    tiene_red = nivel >= 8
    
    intentos = 2 if not tiene_infrarrojos else 3
    
    target_r = random.randint(0, 2)
    target_c = random.randint(0, 2)
    
    pistas = generar_pistas(target_r, target_c)
    pistas_str = "\n".join([f"🔎 {p}" for p in pistas])
    
    header = get_job_header(user_id, tipo_trabajo)
    embed_perfilado = discord.Embed(
        title="🕵️ Caza de Recompensas: Fase de Perfilado",
        description=f"{header}\nAnaliza los informes de inteligencia para deducir en qué cuadrante está escondido el fugitivo:\n\n{pistas_str}",
        color=discord.Color.dark_blue()
    )
    
    grid_view = PerfiladoGridView(user_id, intentos, target_r, target_c)
    msg = await interaction.followup.send(content=f"**Intentos restantes:** {intentos}/{intentos}", embed=embed_perfilado, view=grid_view, wait=True)
    
    await grid_view.wait()
    
    recompensa_base = get_recompensa_trabajo(tipo_trabajo, user_id)
    xp_ganada = TIPOS_TRABAJO[tipo_trabajo].get('xp_por_trabajo', 10)
    
    if grid_view.estado == "Encontrado":
        # Fase 2: QTE
        embed_qte = discord.Embed(
            title="🏃‍♂️ ¡FUGITIVO A LA VISTA!",
            description="Lo acorralaste, pero está intentando escapar.\n**¡Reacciona rápido y presiona el botón para atraparlo!**",
            color=discord.Color.red()
        )
        embed_qte.set_footer(text="Tienes menos de 4 segundos...")
        
        qte_view = CapturaQTEView(user_id)
        if grid_view.last_interaction:
            await grid_view.last_interaction.edit_original_response(content=None, embed=embed_qte, view=qte_view)
        else:
            await msg.edit(content=None, embed=embed_qte, view=qte_view)
        
        await qte_view.wait()
        
        if qte_view.capturado:
            # Recompensa completa
            multiplicador = 1.5 if tiene_red else 1.2
            recompensa = int(recompensa_base * multiplicador)
            
            set_balance(user_id, get_balance(user_id) + recompensa)
            registrar_transaccion(user_id, recompensa, "Cazarrecompensas (Captura Viva)")
            add_experiencia_trabajo(user_id, tipo_trabajo, xp_ganada)
            
            embed_final = discord.Embed(
                title="🎯 ¡Captura Exitosa!",
                description=f"Lograste someter al objetivo y entregarlo a las autoridades.\n\n💰 **Ganancia:** {recompensa} monedas\n📈 **XP:** {xp_ganada}",
                color=discord.Color.green()
            )
            if qte_view.last_interaction:
                await qte_view.last_interaction.edit_original_response(embed=embed_final, view=None)
            else:
                await msg.edit(embed=embed_final, view=None)
        else:
            # Se escapó en el QTE, recompensa parcial
            recompensa_parcial = int(recompensa_base * 0.4)
            xp_parcial = int(xp_ganada * 0.5)
            
            set_balance(user_id, get_balance(user_id) + recompensa_parcial)
            registrar_transaccion(user_id, recompensa_parcial, "Cazarrecompensas (Venta de Información)")
            add_experiencia_trabajo(user_id, tipo_trabajo, xp_parcial)
            
            embed_final = discord.Embed(
                title="💨 El objetivo escapó",
                description=f"Fuiste demasiado lento y huyó de la escena. Sin embargo, vendiste la información de su paradero.\n\n💰 **Ganancia:** {recompensa_parcial} monedas\n📈 **XP:** {xp_parcial}",
                color=discord.Color.orange()
            )
            if qte_view.last_interaction:
                await qte_view.last_interaction.edit_original_response(embed=embed_final, view=None)
            else:
                await msg.edit(embed=embed_final, view=None)
            
    elif grid_view.estado == "Fallado":
        embed_fallo = discord.Embed(
            title="❌ Perdiste el Rastro",
            description="Revisaste las zonas equivocadas y el fugitivo ya abandonó la ciudad. Misión fallida.",
            color=discord.Color.red()
        )
        if grid_view.last_interaction:
            await grid_view.last_interaction.edit_original_response(content=None, embed=embed_fallo, view=None)
        else:
            await msg.edit(content=None, embed=embed_fallo, view=None)
        
    elif grid_view.estado == "Timeout":
        embed_fallo = discord.Embed(
            title="⌛ Tiempo Agotado",
            description="Tardaste mucho analizando las pistas y perdiste tu ventana de oportunidad.",
            color=discord.Color.dark_gray()
        )
        if grid_view.last_interaction:
            await grid_view.last_interaction.edit_original_response(content=None, embed=embed_fallo, view=None)
        else:
            await msg.edit(content=None, embed=embed_fallo, view=None)
