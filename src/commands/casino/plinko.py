import discord
from discord.ext import commands
from discord import app_commands
import asyncio
import math
from src.db import get_balance, deduct_balance, add_balance, ensure_user, registrar_transaccion, record_game_result, get_provably_fair_seeds, advance_provably_fair_nonce
from src.utils.provably_fair import get_uniform_float

# Definición de multiplicadores según riesgo (bajo, medio, alto) y filas (8 a 16)
# Por simplicidad, definiremos 3 perfiles genéricos de pagos para 8, 12 y 16 filas.
PLINKO_PAYOUTS = {
    8: {
        "Bajo": [5.6, 2.1, 1.1, 1.0, 0.5, 1.0, 1.1, 2.1, 5.6],
        "Medio": [13, 3, 1.3, 0.7, 0.4, 0.7, 1.3, 3, 13],
        "Alto": [29, 4, 1.5, 0.3, 0.2, 0.3, 1.5, 4, 29]
    },
    12: {
        "Bajo": [10, 3, 1.6, 1.4, 1.1, 1, 0.5, 1, 1.1, 1.4, 1.6, 3, 10],
        "Medio": [33, 11, 4, 2, 1.1, 0.6, 0.3, 0.6, 1.1, 2, 4, 11, 33],
        "Alto": [170, 24, 8.1, 2, 0.7, 0.2, 0.2, 0.2, 0.7, 2, 8.1, 24, 170]
    },
    16: {
        "Bajo": [16, 9, 2, 1.4, 1.4, 1.2, 1.1, 1, 0.5, 1, 1.1, 1.2, 1.4, 1.4, 2, 9, 16],
        "Medio": [110, 41, 10, 5, 3, 1.5, 1, 0.5, 0.3, 0.5, 1, 1.5, 3, 5, 10, 41, 110],
        "Alto": [1000, 130, 26, 9, 4, 2, 0.2, 0.2, 0.2, 0.2, 0.2, 2, 4, 9, 26, 130, 1000]
    }
}

class PlinkoSettings(discord.ui.Modal, title="Configurar Plinko"):
    def __init__(self, view):
        super().__init__()
        self.view = view
        
    monto = discord.ui.TextInput(
        label="Monto a apostar",
        placeholder="Ej: 500",
        required=True,
        max_length=10
    )
    
    filas = discord.ui.TextInput(
        label="Número de filas (8, 12, 16)",
        placeholder="Ej: 8",
        default="8",
        required=True,
        max_length=2
    )

    async def on_submit(self, interaction: discord.Interaction):
        try:
            apuesta = int(self.monto.value)
            if apuesta <= 0:
                raise ValueError
        except ValueError:
            await interaction.response.send_message("❌ Monto inválido.", ephemeral=True)
            raise
            
        try:
            filas_num = int(self.filas.value)
            if filas_num not in [8, 12, 16]:
                await interaction.response.send_message("❌ Las filas deben ser 8, 12 o 16.", ephemeral=True)
                return
        except ValueError:
            await interaction.response.send_message("❌ Filas inválidas.", ephemeral=True)
            raise

        saldo = await asyncio.to_thread(get_balance, interaction.user.id)
        if saldo < apuesta:
            await interaction.response.send_message("❌ Saldo insuficiente.", ephemeral=True)
            return

        self.view.apuesta = apuesta
        self.view.filas = filas_num
        self.view.configurado = True
        
        await self.view.actualizar_menu(interaction)

class PlinkoView(discord.ui.View):
    def __init__(self, user_id):
        super().__init__(timeout=120)
        self.user_id = user_id
        self.apuesta = 0
        self.filas = 8
        self.riesgo = "Bajo"
        self.configurado = False
        
    @discord.ui.button(label="⚙️ Configurar Apuesta", style=discord.ButtonStyle.secondary, row=0)
    async def config(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ Solo el creador puede usar esto.", ephemeral=True)
            return
        await interaction.response.send_modal(PlinkoSettings(self))
        
    @discord.ui.select(
        placeholder="Selecciona el Nivel de Riesgo...",
        options=[
            discord.SelectOption(label="🟢 Riesgo Bajo", value="Bajo"),
            discord.SelectOption(label="🟡 Riesgo Medio", value="Medio"),
            discord.SelectOption(label="🔴 Riesgo Alto", value="Alto"),
        ],
        row=1
    )
    async def select_riesgo(self, interaction: discord.Interaction, select: discord.ui.Select):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ Solo el creador puede usar esto.", ephemeral=True)
            return
        self.riesgo = select.values[0]
        await self.actualizar_menu(interaction)
        
    @discord.ui.button(label="🎾 Soltar Bola!", style=discord.ButtonStyle.success, row=2)
    async def play(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ Solo el creador puede jugar.", ephemeral=True)
            return
            
        if not self.configurado:
            await interaction.response.send_message("⚠️ Por favor configura tu apuesta primero.", ephemeral=True)
            return

        await asyncio.to_thread(ensure_user, self.user_id)

        # Descontar saldo
        success, nuevo_saldo = await asyncio.to_thread(deduct_balance, self.user_id, self.apuesta)
        if not success:
            await interaction.response.send_message("❌ Saldo insuficiente.", ephemeral=True)
            return
            
        # Iniciar juego (Provably Fair)
        self.clear_items()
        
        seeds = await asyncio.to_thread(get_provably_fair_seeds, self.user_id)
        nonce = await asyncio.to_thread(advance_provably_fair_nonce, self.user_id)
        
        # Calcular trayectoria usando Provably Fair
        path = []
        cursor = 0
        position = 0 # 0 es extrema izquierda, sumará 1 si cae a la derecha
        
        for i in range(self.filas):
            # Obtener 1 bit de entropía (0 = Izquierda, 1 = Derecha)
            val = get_uniform_float(seeds["server_seed"], seeds["client_seed"], nonce, cursor)
            cursor += 1
            direction = 1 if val >= 0.5 else 0
            path.append(direction)
            position += direction
            
        # El bucket final es la suma de los desplazamientos a la derecha
        multiplicador = PLINKO_PAYOUTS[self.filas][self.riesgo][position]
        pago_final = int(self.apuesta * multiplicador)
        profit = pago_final - self.apuesta
        
        if pago_final > 0:
            await asyncio.to_thread(add_balance, self.user_id, pago_final)
            await asyncio.to_thread(registrar_transaccion, self.user_id, profit, f"Plinko: x{multiplicador}")
        else:
            await asyncio.to_thread(registrar_transaccion, self.user_id, -self.apuesta, "Plinko: sin premio")

        saldo_final = nuevo_saldo + pago_final
        result_str = 'win' if profit > 0 else 'loss'
        await asyncio.to_thread(record_game_result, self.user_id, 'plinko', self.apuesta, result_str, max(0, profit), 0.0, saldo_final)
            
        # Animación de Plinko muy básica
        embed = discord.Embed(title="🎾 Plinko en progreso...", color=discord.Color.orange())
        await interaction.response.edit_message(embed=embed, view=None)
        
        # Generar animación textual simple
        msg = interaction.message
        anim_text = "⬇️ Cayendo...\n"
        current_pos = self.filas / 2.0
        
        for dir in path:
            current_pos += 0.5 if dir == 1 else -0.5
            # Simular dibujo
            spaces = " " * int(current_pos * 2)
            anim_text += f"{spaces}🔴\n"
            
            embed.description = f"```\n{anim_text}\n```"
            await asyncio.sleep(0.5)
            try:
                await interaction.edit_original_response(embed=embed)
            except:
                pass
                
        # Resultado final
        color = discord.Color.green() if multiplicador > 1 else discord.Color.red()
        embed = discord.Embed(
            title="🎾 Plinko Finalizado",
            description=(
                f"**Multiplicador:** {multiplicador}x\n"
                f"**Apuesta:** {self.apuesta}\n"
                f"**Pago Final:** {pago_final}\n\n"
                f"🔒 *Provably Fair Nonce:* `{nonce}`"
            ),
            color=color
        )
        await interaction.edit_original_response(embed=embed)

    async def actualizar_menu(self, interaction):
        embed = discord.Embed(
            title="🎯 Plinko",
            description=(
                f"**Apuesta:** {self.apuesta if self.configurado else 'No configurada'}\n"
                f"**Filas:** {self.filas}\n"
                f"**Riesgo:** {self.riesgo}\n\n"
                f"Configura tu apuesta y presiona Soltar Bola para jugar."
            ),
            color=discord.Color.blue()
        )
        
        # Mostrar el layout de multiplicadores abajo
        if self.configurado:
            payouts = PLINKO_PAYOUTS[self.filas][self.riesgo]
            payouts_str = " ".join([f"[{p}x]" for p in payouts])
            embed.add_field(name="Multiplicadores Base:", value=f"`{payouts_str}`", inline=False)
            
        try:
            await interaction.response.edit_message(embed=embed, view=self)
        except discord.InteractionResponded:
            await interaction.edit_original_response(embed=embed, view=self)
            raise

class PlinkoCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="plinko", description="Juega al clásico Plinko con multiplicadores variables.")
    async def plinko_cmd(self, interaction: discord.Interaction):
        view = PlinkoView(interaction.user.id)
        embed = discord.Embed(
            title="🎯 Plinko",
            description="Haz clic en Configurar Apuesta para empezar.",
            color=discord.Color.blue()
        )
        await interaction.response.send_message(embed=embed, view=view)

async def setup(bot):
    await bot.add_cog(PlinkoCog(bot))
    print("✅ Plinko command loaded.")
