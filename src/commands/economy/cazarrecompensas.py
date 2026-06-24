import discord
import asyncio
import random
from src.db import get_balance, set_balance, registrar_transaccion
from .energia import consumir_energia, get_energia
from .niveles_trabajo import get_nivel_trabajo, add_experiencia_trabajo, get_energia_trabajo, get_recompensa_trabajo, get_job_header

class GridBountyView(discord.ui.View):
    def __init__(self, user_id, intentos, tiene_infrarrojos):
        super().__init__(timeout=30)
        self.user_id = user_id
        self.intentos = intentos
        self.max_intentos = intentos
        self.resultado = None # True si gana, False si pierde
        
        # Grid 3x3: (row, col) -> (0..2, 0..2)
        self.target_row = random.randint(0, 2)
        self.target_col = random.randint(0, 2)
        
        # Infrarrojos revela un cuadro vacío al inicio
        pos_revelada = None
        if tiene_infrarrojos:
            while True:
                r = random.randint(0, 2)
                c = random.randint(0, 2)
                if r != self.target_row or c != self.target_col:
                    pos_revelada = (r, c)
                    break

        for r in range(3):
            for c in range(3):
                custom_id = f"bounty_{r}_{c}"
                btn = discord.ui.Button(label="?", style=discord.ButtonStyle.secondary, custom_id=custom_id, row=r)
                
                if pos_revelada and pos_revelada == (r, c):
                    btn.disabled = True
                    btn.label = "Vacío"
                    btn.style = discord.ButtonStyle.dark_gray
                    
                btn.callback = self.crear_callback(r, c, btn)
                self.add_item(btn)

    def crear_callback(self, row, col, button: discord.ui.Button):
        async def callback(interaction: discord.Interaction):
            if interaction.user.id != self.user_id:
                await interaction.response.send_message("❌ Esta no es tu misión.", ephemeral=True)
                return

            button.disabled = True
            
            if row == self.target_row and col == self.target_col:
                # Acertó
                button.style = discord.ButtonStyle.success
                button.label = "¡ATRAPADO!"
                button.emoji = "🎯"
                self.resultado = True
                
                for item in self.children:
                    item.disabled = True
                    
                await interaction.response.edit_message(content="**¡Encontraste al fugitivo!**", view=self)
                self.stop()
            else:
                # Falló
                self.intentos -= 1
                distancia = abs(self.target_row - row) + abs(self.target_col - col)
                
                if distancia == 1:
                    pista = "🔥 Caliente"
                    button.style = discord.ButtonStyle.danger
                elif distancia == 2:
                    pista = "☀️ Tibio"
                    button.style = discord.ButtonStyle.primary
                else:
                    pista = "❄️ Frío"
                    button.style = discord.ButtonStyle.secondary
                    
                button.label = pista
                
                if self.intentos <= 0:
                    self.resultado = False
                    for item in self.children:
                        item.disabled = True
                        # Mostrar dónde estaba
                        if getattr(item, "custom_id", "") == f"bounty_{self.target_row}_{self.target_col}":
                            item.style = discord.ButtonStyle.success
                            item.label = "Escapó"
                            item.emoji = "🏃"
                    await interaction.response.edit_message(content=f"**¡El fugitivo ha escapado!**", view=self)
                    self.stop()
                else:
                    await interaction.response.edit_message(content=f"**Intentos restantes:** {self.intentos}/{self.max_intentos}", view=self)
                    
        return callback

    async def on_timeout(self):
        self.resultado = False
        for item in self.children:
            item.disabled = True

async def iniciar_trabajo_cazarrecompensas(interaction: discord.Interaction):
    user_id = interaction.user.id
    tipo_trabajo = "cazarrecompensas"

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

    await interaction.response.defer()
    consumir_energia(user_id, energia_req)

    intentos = 4 if nivel >= 8 else 3
    tiene_infrarrojos = nivel >= 5

    view = GridBountyView(user_id, intentos, tiene_infrarrojos)
    
    header = get_job_header(user_id, tipo_trabajo)
    embed = discord.Embed(
        title="🗡️ Cacería de Recompensas",
        description=f"{header}Se busca un fugitivo peligroso en este sector.\nTienes un radar y debes encontrarlo buscando en la cuadrícula.",
        color=discord.Color.dark_red()
    )
    embed.add_field(name="Intentos", value=f"{intentos}", inline=True)
    if tiene_infrarrojos:
        embed.add_field(name="Ventaja", value="Gafas Infrarrojas (1 zona revelada)", inline=True)
        
    msg = await interaction.followup.send(content=f"**Intentos restantes:** {intentos}/{intentos}", embed=embed, view=view, wait=True)
    
    await view.wait()

    if not view.resultado:
        embed_fail = discord.Embed(
            title="💨 Misión Fallida",
            description="El objetivo logró escapar de la ciudad. No recibes recompensa.",
            color=discord.Color.dark_grey()
        )
        await msg.edit(embed=embed_fail, view=None)
        add_experiencia_trabajo(user_id, tipo_trabajo, 5)
        return

    # Éxito
    recompensa_base = get_recompensa_trabajo(tipo_trabajo, user_id)
    recompensa = int(recompensa_base * random.uniform(0.9, 1.2))
    
    saldo_actual = get_balance(user_id)
    set_balance(user_id, saldo_actual + recompensa)
    registrar_transaccion(user_id, recompensa, "Trabajo: Cazarrecompensas")
    
    xp_ganada = 22
    resultado_xp = add_experiencia_trabajo(user_id, tipo_trabajo, xp_ganada)
    
    embed_final = discord.Embed(
        title="🎯 ¡Objetivo Eliminado/Capturado!",
        description="Has entregado al fugitivo a las autoridades.",
        color=discord.Color.green()
    )
    embed_final.add_field(name="💰 Recompensa Cobrada", value=f"**{recompensa}** monedas")
    
    xp_msg = f"+{resultado_xp['xp_ganada_final']} XP"
    if resultado_xp['pocion_usada']:
        xp_msg += " (🧪 x1.5)"
    embed_final.add_field(name="✨ Experiencia", value=xp_msg)
    
    if resultado_xp['subio_nivel']:
        embed_final.add_field(
            name="🎉 ¡SUBISTE DE NIVEL!", 
            value=f"Ahora eres nivel **{resultado_xp['nivel_nuevo']}** de Cazarrecompensas.",
            inline=False
        )

    await msg.edit(embed=embed_final, view=None)
