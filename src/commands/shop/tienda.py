import discord
from discord.ext import commands
from discord import app_commands
import asyncio
from datetime import datetime, timedelta
from src.db import (
    get_balance, set_balance, ensure_user, registrar_transaccion, 
    agregar_item_usuario, usuario_tiene_item, get_user_items, usar_item_usuario,
    get_energia, set_energia,     check_and_register_energy_use, comprar_item_tienda
)
from src.utils.cooldowns import ECONOMY_COOLDOWN

TIENDA = [
    {"id": 3, "nombre": "Bebida Energética 🥤", "precio": 500, "descripcion": "Recupera +50 de energía de inmediato. Úsala con `/usar 3`.", "caracteristica": "positiva"},
    {"id": 4, "nombre": "Poción de Enfoque 🧪", "precio": 1000, "descripcion": "Tu siguiente trabajo da +50% de XP. Se consume automáticamente al trabajar.", "caracteristica": "positiva"},
    {"id": 5, "nombre": "Ticket de Suerte Slots 🎟️", "precio": 1500, "descripcion": "Duplica premio al ganar (con debuff 35% de protección). Se consume al ganar. Límite diario de 3 escudos.", "caracteristica": "positiva"},
    {"id": 6, "nombre": "Ticket de Suerte Crash 🎫", "precio": 2000, "descripcion": "Seguro de crash. Reembolsa si explota <x1.50 (apuestas hasta 5k). Consumo al inicio. Límite diario de 3 escudos.", "caracteristica": "positiva"},
    {"id": 7, "nombre": "Amuleto de Protección 🪬", "precio": 1200, "descripcion": "Evita derrumbe/rotura en minería/pesca (1 uso). Se consume al fallar. Límite diario de 3 escudos.", "caracteristica": "positiva"},
    {"id": 11, "nombre": "Special Mute 🔇", "precio": 3000, "descripcion": "Usa el comando `/specialmute` una vez. Permite silenciar temporalmente a un miembro.", "caracteristica": "neutral"},
    {"id": 12, "nombre": "Escudo Anti-Mute 🛡️", "precio": 1000, "descripcion": "Te protege automáticamente del próximo `/specialmute` lanzado en tu contra (1 uso). Se consume al activarse.", "caracteristica": "positiva"},
]

def _get_inventory_db(user_id, user_name):
    ensure_user(user_id, user_name)
    return get_user_items(user_id)

def _comprar_articulo_db(user_id, user_name, item):
    ensure_user(user_id, user_name)
    expiry_date = datetime.now() + timedelta(days=3650)
    result = comprar_item_tienda(user_id, item["id"], item["precio"], expiry_date)
    if result == "no_balance":
        return "no_balance"
    registrar_transaccion(user_id, -item["precio"], f"Compra: {item['nombre']}")
    return "ok"

def _usar_articulo_db(user_id, user_name, articulo_id):
    ensure_user(user_id, user_name)

    if not usuario_tiene_item(user_id, articulo_id):
        return "missing", None

    if articulo_id == 3:
        energia_actual = get_energia(user_id)
        if energia_actual >= 100:
            return "energy_full", energia_actual

        # Verificar límites de uso diario de energía (máximo 5 al día)
        status, time_remaining = check_and_register_energy_use(user_id, 3)
        if status == 'blocked':
            return "blocked", time_remaining
        elif status == 'blocked_start':
            return "blocked_start", time_remaining

        nueva_energia = min(100, energia_actual + 50)
        set_energia(user_id, nueva_energia)
        usar_item_usuario(user_id, 3)
        return "energy_used", nueva_energia

    if articulo_id == 4:
        return "focus_auto", None

    if articulo_id in [5, 6, 7, 12]:
        return "auto_item", None

    return "unsupported", None

class Tienda(commands.Cog):
    """Cog para la tienda de artículos consumibles de un solo uso."""
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="tienda", description="Muestra los artículos consumibles de un solo uso disponibles.")
    async def tienda(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="🛒 Tienda de Consumibles",
            description="¡Compra artículos de un solo uso para potenciar tus juegos y trabajos!",
            color=discord.Color.gold()
        )
        embed.set_thumbnail(url="https://cdn-icons-png.flaticon.com/512/263/263142.png")
        for item in TIENDA:
            embed.add_field(
                name=f"{item['nombre']} — {item['precio']} 🪙",
                value=f"`ID:` `{item['id']}`\n{item['descripcion']}",
                inline=False
            )
        embed.set_footer(text="Usa /comprar <ID> para adquirir un artículo. Usa /usar <ID> para consumir artículos.")
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="inventario", description="Muestra los artículos que posees.")
    async def inventario(self, interaction: discord.Interaction):
        user_id = interaction.user.id
        user_name = interaction.user.name
        items = await asyncio.to_thread(_get_inventory_db, user_id, user_name)
        
        embed = discord.Embed(
            title="🎒 Tu Inventario",
            description="Aquí están todos tus artículos y mejoras:",
            color=discord.Color.blue()
        )
        
        if not items:
            embed.description = "No tienes ningún artículo en tu inventario."
        else:
            consumibles_text = ""
            mejoras_text = ""
            
            for user_item in items:
                item_id = user_item['item_id']
                item_info = next((i for i in TIENDA if i["id"] == item_id), None)
                
                # También buscar en el Black Market si no está en la tienda
                if not item_info:
                    from src.commands.shop.black_market_items import BLACK_MARKET
                    # Las mejoras del Mercado Negro se guardan con ID = 1000 + BM_ID
                    bm_id = item_id - 1000 if item_id >= 1000 else item_id
                    item_info = next((i for i in BLACK_MARKET if i["id"] == bm_id), None)
                    is_permanent = item_id >= 1000
                else:
                    is_permanent = False
                
                if item_info:
                    nombre = item_info['nombre']
                    if is_permanent:
                        mejoras_text += f"• **{nombre}** (ID: `{item_id}`)\n"
                    else:
                        consumibles_text += f"• **{nombre}** - Cantidad: {user_item['quantity']} (ID: `{item_id}`)\n"
            
            if consumibles_text:
                embed.add_field(name="🛒 Consumibles (Tienda)", value=consumibles_text, inline=False)
            if mejoras_text:
                embed.add_field(name="🕶️ Mejoras Permanentes (Black Market)", value=mejoras_text, inline=False)
        
        embed.set_footer(text="Usa /usar <ID> para consumir artículos.")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="comprar", description="Compra un artículo de la tienda por su ID.")
    @app_commands.describe(articulo_id="ID del artículo a comprar")
    @ECONOMY_COOLDOWN
    async def comprar(self, interaction: discord.Interaction, articulo_id: int):
        user_id = interaction.user.id
        user_name = interaction.user.name
        item = next((i for i in TIENDA if i["id"] == articulo_id), None)
        
        if not item:
            await interaction.response.send_message("❌ Artículo no encontrado en la tienda de consumibles.", ephemeral=True)
            return

        status = await asyncio.to_thread(_comprar_articulo_db, user_id, user_name, item)

        if status == "no_balance":
            await interaction.response.send_message("❌ No tienes suficiente saldo para comprar este artículo.", ephemeral=True)
            return

        if status == "item_error":
            await interaction.response.send_message("❌ Error al agregar el artículo a tu inventario. Dinero reembolsado.", ephemeral=True)
            return
        
        if item["id"] == 3:
            msg = "🥤 ¡Has comprado una Bebida Energética! Puedes consumirla de inmediato usando `/usar 3` para obtener +50 de energía."
        elif item["id"] == 4:
            msg = "🧪 ¡Has comprado una Poción de Enfoque! Tu siguiente trabajo te dará +50% de XP de manera automática."
        elif item["id"] == 5:
            msg = (
                "🎟️ ¡Has comprado un Ticket de Suerte Slots!\n\n"
                "**Condiciones de uso:**\n"
                "• **Efecto:** Duplica tu premio en `/slots` al ganar.\n"
                "• **Debuff:** Aplica un debuff de -35% en las ganancias debido a la protección activa.\n"
                "• **Límite Diario:** Sujeto al límite diario de **3 usos de escudos/tickets** en total (compartido con minería/pesca/crash).\n"
                "• **Consumo:** Se consume automáticamente al ganar una ronda."
            )
        elif item["id"] == 6:
            msg = (
                "🎫 ¡Has comprado un Ticket de Suerte Crash!\n\n"
                "**Condiciones de uso:**\n"
                "• **Reembolso:** Si explotas antes de **x1.50** en `/crash`, recibirás el reembolso de tu apuesta.\n"
                "• **Límite de Apuesta:** Solo protege apuestas de **hasta 5,000 monedas** (inclusive).\n"
                "• **Límite Diario:** Sujeto al límite diario de **3 usos de escudos** en total (compartido con slots/minería/pesca).\n"
                "• **Consumo:** Se consume automáticamente al iniciar la ronda de crash."
            )
        elif item["id"] == 7:
            msg = (
                "🪬 ¡Has comprado un Amuleto de Protección!\n\n"
                "**Condiciones de uso:**\n"
                "• **Efecto:** Evita pérdidas o penalizaciones por derrumbes o roturas de línea en minería y pesca.\n"
                "• **Límite Diario:** Sujeto al límite diario de **3 usos de escudos** en total (compartido con slots/crash).\n"
                "• **Consumo:** Se consume automáticamente al fallar."
            )
        elif item["id"] == 11:
            msg = "🔇 ¡Has comprado un Special Mute! Puedes usar `/specialmute` una vez para silenciar a un miembro."
        elif item["id"] == 12:
            msg = "🛡️ ¡Has comprado un Escudo Anti-Mute! Te protegerá automáticamente del próximo `/specialmute` lanzado en tu contra."
        else:
            msg = "¡Compra realizada con éxito!"
            
        embed = discord.Embed(
            title="✅ Compra exitosa",
            description=msg,
            color=discord.Color.green()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="usar", description="Usa un artículo consumible de tu inventario por su ID.")
    @app_commands.describe(articulo_id="ID del artículo a usar")
    async def usar(self, interaction: discord.Interaction, articulo_id: int):
        user_id = interaction.user.id
        user_name = interaction.user.name

        status, data = await asyncio.to_thread(
            _usar_articulo_db, user_id, user_name, articulo_id
        )

        if status == "missing":
            await interaction.response.send_message("❌ No tienes este artículo en tu inventario o ya fue consumido.", ephemeral=True)
            return

        if status == "energy_full":
            await interaction.response.send_message("🔋 Tu energía ya está al máximo (100%). No necesitas usar la bebida ahora.", ephemeral=True)
            return

        if status in ["blocked", "blocked_start"]:
            hours = data // 3600
            minutes = (data % 3600) // 60
            await interaction.response.send_message(f"🤢 **Te sientes mal, es mejor esperar.**\n⏱️ Cooldown restante: **{hours}h {minutes:02d}m**", ephemeral=True)
            return

        if status == "energy_used":
            await interaction.response.send_message(f"🥤 **¡Consumiste una Bebida Energética!** Recuperaste +50 de energía. Energía actual: **{data}/100**", ephemeral=True)
            return

        if status == "focus_auto":
            await interaction.response.send_message("🧪 **La Poción de Enfoque se consume automáticamente** al finalizar tu próximo trabajo, aumentando tu XP en un 50%.", ephemeral=True)
            return

        if status == "auto_item":
            await interaction.response.send_message("🎟️ **Este artículo se consume automáticamente** cuando ocurre el evento correspondiente (jugar slots, perder en crash, fallar en minería/pesca o al recibir un specialmute).", ephemeral=True)
            return

        await interaction.response.send_message("❌ Este artículo no se puede usar directamente con este comando.", ephemeral=True)

# Helper para crear ítems estándar
def crear_item(id, nombre, precio, descripcion, caracteristica):
    return {
        "id": id,
        "nombre": nombre,
        "precio": precio,
        "descripcion": descripcion,
        "caracteristica": caracteristica
    }

async def setup(bot):
    await bot.add_cog(Tienda(bot))
    print("Tienda cog loaded successfully.")
