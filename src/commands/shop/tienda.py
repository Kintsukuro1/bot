import discord
from discord.ext import commands
from discord import app_commands
import asyncio
from datetime import datetime, timedelta
from src.db import (
    get_balance, set_balance, ensure_user, registrar_transaccion, 
    agregar_item_usuario, usuario_tiene_item, get_user_items, usar_item_usuario,
    get_energia, set_energia, check_and_register_energy_use, comprar_item_tienda,
    get_user_prestige_level
)
from src.utils.cooldowns import ECONOMY_COOLDOWN
from src.services.shop_rotation_service import get_rotation_info, select_rotated_items, NORMAL_SHOP_ROTATION_SECONDS, get_stock_remaining, consume_stock

TIENDA_CATALOGO = [
    {"id": 3, "nombre": "Bebida Energética 🥤", "precio": 500, "descripcion": "Recupera +50 de energía de inmediato. Úsala con `/usar 3`.", "rarity_weight": 50, "prestige_required": 0},
    {"id": 4, "nombre": "Poción de Enfoque 🧪", "precio": 1000, "descripcion": "Tu siguiente trabajo da +50% de XP. Se consume automáticamente al trabajar.", "rarity_weight": 40, "prestige_required": 0},
    {"id": 7, "nombre": "Amuleto de Protección 🪬", "precio": 1200, "descripcion": "Evita derrumbe/rotura en minería/pesca (1 uso). Se consume al fallar.", "rarity_weight": 35, "prestige_required": 0},
    {"id": 14, "nombre": "Comida Gourmet 🥩", "precio": 1500, "descripcion": "Otorga +150 XP a una mascota y restaura su Lealtad al 100%. Úsala con `/usar 14`.", "rarity_weight": 40, "prestige_required": 0},
    {"id": 15, "nombre": "Lupa de Rastreo 🔍", "precio": 2000, "descripcion": "Permite ver el saldo exacto y cooldowns de robo de un objetivo (`/usar 15`).", "rarity_weight": 25, "prestige_required": 0},
    {"id": 16, "nombre": "Escudo de Robo Temporal 🛡️", "precio": 3500, "descripcion": "Otorga 30 minutos de inmunidad contra robos (`/usar 16`).", "rarity_weight": 20, "prestige_required": 0},
    {"id": 17, "nombre": "Poción de Vitalidad en Raid 🧪", "precio": 2500, "descripcion": "Restaura 25% de HP durante un combate de Raid (`/usar 17`).", "rarity_weight": 30, "prestige_required": 0},
    {"id": 18, "nombre": "Pase de Lotería Extra 🎫", "precio": 1000, "descripcion": "Participa con 1 boleto adicional en la lotería diaria del servidor.", "rarity_weight": 30, "prestige_required": 0},
    {"id": 20, "nombre": "Caja de Mascotas Sellada 📦", "precio": 50000, "descripcion": "Contiene una mascota aleatoria. Requiere 15,000 Balance para abrirse (`/abrir_caja`).", "rarity_weight": 15, "prestige_required": 0},
]

def get_current_shop_items():
    """Devuelve los ítems activos en la rotación actual de 30 min."""
    return select_rotated_items(TIENDA_CATALOGO, count=6, rotation_seconds=NORMAL_SHOP_ROTATION_SECONDS)

def _get_inventory_db(user_id, user_name):
    ensure_user(user_id, user_name)
    return get_user_items(user_id)

def _comprar_articulo_db(user_id, user_name, item):
    ensure_user(user_id, user_name)
    
    prestige_level = get_user_prestige_level(user_id)
    if item.get("prestige_required", 0) > prestige_level:
        return "prestige_required"

    # Intentar consumir 1 unidad del stock rotativo de la tienda
    has_stock = consume_stock("normal", item, NORMAL_SHOP_ROTATION_SECONDS)
    if not has_stock:
        return "out_of_stock"
        
    expiry_date = datetime.now() + timedelta(days=3650)

    prestige_discount = prestige_level >= 1
    precio_final = int(item["precio"] * 0.95) if prestige_discount else item["precio"]

    result = comprar_item_tienda(user_id, item["id"], precio_final, expiry_date)
    if result == "no_balance":
        return "no_balance"
    registrar_transaccion(user_id, -precio_final, f"Compra: {item['nombre']}")
    return "ok", precio_final, prestige_discount


def _usar_articulo_db(user_id, user_name, articulo_id):
    ensure_user(user_id, user_name)

    if not usuario_tiene_item(user_id, articulo_id):
        return "missing", None

    if articulo_id == 3:
        energia_actual = get_energia(user_id)
        if energia_actual >= 100:
            return "energy_full", energia_actual

        status, time_remaining = check_and_register_energy_use(user_id, 3)
        if status == 'blocked':
            return "blocked", time_remaining
        elif status == 'blocked_start':
            return "blocked_start", time_remaining
        elif status == 'error':
            return "db_error", None

        nueva_energia = min(100, energia_actual + 50)
        set_energia(user_id, nueva_energia)
        usar_item_usuario(user_id, 3)
        return "energy_used", nueva_energia

    if articulo_id == 4:
        return "focus_auto", None

    if articulo_id == 16:
        if usar_item_usuario(user_id, 16):
            from src.db import set_robar_shield
            set_robar_shield(user_id)
            return "shield_activated", None
        else:
            return "missing", None

    if articulo_id in [7, 18]:
        return "auto_item", None

    return "unsupported", None

class ShopHubView(discord.ui.View):
    """Vista del Panel Hub Efímero de Comercio y Mercado."""
    def __init__(self, user: discord.Member, cog):
        super().__init__(timeout=120)
        self.user = user
        self.cog = cog

    @discord.ui.button(label="🏪 Tienda Rotativa", style=discord.ButtonStyle.success, row=0)
    async def rotative_shop(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("❌ Esta interfaz no es tuya.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        active_items = get_current_shop_items()
        _, _, time_str = get_rotation_info(NORMAL_SHOP_ROTATION_SECONDS)
        prestige_level = await asyncio.to_thread(get_user_prestige_level, self.user.id)
        embed = discord.Embed(
            title="🛒 Tienda General — Stock Rotativo",
            description=f"¡Stock actualizado cada 30 minutos!\n⏱️ **Próxima rotación en:** `{time_str}`",
            color=discord.Color.gold()
        )
        for item in active_items:
            req = item.get("prestige_required", 0)
            if prestige_level >= req:
                stock_rem = await asyncio.to_thread(get_stock_remaining, "normal", item, NORMAL_SHOP_ROTATION_SECONDS)
                stock_tag = f" (Stock: **{stock_rem}**)" if stock_rem > 0 else " **(❌ AGOTADO)**"
                embed.add_field(
                    name=f"{item['nombre']} — {item['precio']:,} 🪙{stock_tag}",
                    value=f"`ID:` `{item['id']}`\n{item['descripcion']}",
                    inline=False
                )
        await interaction.followup.send(embed=embed, ephemeral=True)

    @discord.ui.button(label="🎒 Mi Inventario", style=discord.ButtonStyle.primary, row=0)
    async def inventory_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("❌ Esta interfaz no es tuya.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        items = await asyncio.to_thread(_get_inventory_db, self.user.id, self.user.name)
        embed = discord.Embed(title="🎒 Tu Inventario", color=discord.Color.blue())
        if not items:
            embed.description = "No tienes ningún artículo en tu inventario."
        else:
            lines = [f"📦 **Item ID {item.get('item_id')}** — Cantidad: {item.get('cantidad', 1)}" for item in items]
            embed.description = "\n".join(lines)
        await interaction.followup.send(embed=embed, ephemeral=True)

    @discord.ui.button(label="⬛ Mercado Negro", style=discord.ButtonStyle.secondary, row=0)
    async def blackmarket_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("❌ Esta interfaz no es tuya.", ephemeral=True)
            return
        embed = discord.Embed(
            title="⬛ Mercado Negro",
            description="Usa el comando `/blackmarket` para consultar las ofertas exclusivas de rotación de 3 horas.",
            color=discord.Color.dark_grey()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @discord.ui.button(label="🤝 Mercado P2P", style=discord.ButtonStyle.secondary, row=1)
    async def p2p_market_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("❌ Esta interfaz no es tuya.", ephemeral=True)
            return
        embed = discord.Embed(
            title="🤝 Mercado de Jugadores",
            description="Usa `/mercado` para ver ofertas públicas o `/vender_item`, `/vender_equipo`, `/vender_mascota` para comerciar.",
            color=discord.Color.purple()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @discord.ui.button(label="🔨 Subastas", style=discord.ButtonStyle.secondary, row=1)
    async def auctions_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("❌ Esta interfaz no es tuya.", ephemeral=True)
            return
        embed = discord.Embed(
            title="🔨 Casa de Subastas",
            description="Usa `/pujar` para ofrecer por una subasta o `/subastar_equipo`, `/subastar_mascota` para iniciar un remate.",
            color=discord.Color.dark_gold()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)


class Tienda(commands.Cog):
    """Cog para la tienda de artículos consumibles de un solo uso."""
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="tienda", description="Abre el Hub Central de Comercio, Mercado e Inventario (Panel Efímero Privado)")
    async def tienda(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        user_id = interaction.user.id
        balance = await asyncio.to_thread(get_balance, user_id)

        embed = discord.Embed(
            title="🛍️ Hub Central de Comercio y Mercado",
            description=(
                f"Bienvenido a la Plaza Comercial, **{interaction.user.display_name}**.\n\n"
                f"💰 **Tu Saldo:** **{balance:,}** monedas\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"Selecciona una sección comercial para explorar:"
            ),
            color=discord.Color.gold()
        )
        embed.set_thumbnail(url="https://cdn-icons-png.flaticon.com/512/263/263142.png")
        embed.set_footer(text="Panel Efímero Privado · Únicamente tú ves este menú")

        view = ShopHubView(interaction.user, self)
        await interaction.followup.send(embed=embed, view=view, ephemeral=True)


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
                item_info = next((i for i in TIENDA_CATALOGO if i["id"] == item_id), None)
                
                if not item_info:
                    from src.commands.shop.black_market_items import BLACK_MARKET
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
                embed.add_field(name="🕶️ Mejoras (Mercado Negro)", value=mejoras_text, inline=False)
        
        embed.set_footer(text="Usa /usar <ID> para consumir artículos.")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="comprar", description="Compra un artículo de la tienda por su ID.")
    @app_commands.describe(articulo_id="ID del artículo a comprar")
    @ECONOMY_COOLDOWN
    async def comprar(self, interaction: discord.Interaction, articulo_id: int):
        user_id = interaction.user.id
        user_name = interaction.user.name
        
        active_items = get_current_shop_items()
        item = next((i for i in active_items if i["id"] == articulo_id), None)
        
        if not item:
            await interaction.response.send_message("❌ Este artículo no está disponible en el stock rotativo actual o no existe.", ephemeral=True)
            return

        status = await asyncio.to_thread(_comprar_articulo_db, user_id, user_name, item)

        if status == "out_of_stock" or (isinstance(status, tuple) and status[0] == "out_of_stock"):
            await interaction.response.send_message("❌ Este artículo se ha **agotado** en la rotación actual.", ephemeral=True)
            return

        if status == "prestige_required" or (isinstance(status, tuple) and status[0] == "prestige_required"):
            await interaction.response.send_message("❌ No cumples con el nivel de Prestigio requerido para comprar este artículo.", ephemeral=True)
            return


        if status == "no_balance" or (isinstance(status, tuple) and status[0] == "no_balance"):
            await interaction.response.send_message("❌ No tienes suficiente saldo para comprar este artículo.", ephemeral=True)
            return

        if status == "item_error" or (isinstance(status, tuple) and status[0] == "item_error"):
            await interaction.response.send_message("❌ Error al agregar el artículo a tu inventario. Dinero reembolsado.", ephemeral=True)
            return

        precio_pagado = item["precio"]
        used_prestige_discount = False
        if isinstance(status, tuple) and status[0] == "ok":
            _, precio_pagado, used_prestige_discount = status
        
        msg = f"¡Has comprado **{item['nombre']}** exitosamente!"
            
        embed = discord.Embed(
            title="✅ Compra exitosa",
            description=msg,
            color=discord.Color.green()
        )
        embed.add_field(
            name="💰 Precio pagado",
            value=f"**{precio_pagado:,}** monedas" + (" *(🌟 -5% Descuento Prestigio aplicado)*" if used_prestige_discount else ""),
            inline=False
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

        if status == "db_error":
            await interaction.response.send_message("❌ Hubo un error de base de datos. Inténtalo de nuevo más tarde.", ephemeral=True)
            return

        if status == "energy_full":
            await interaction.response.send_message("🔋 Tu energía ya está al máximo (100%).", ephemeral=True)
            return

        if status in ["blocked", "blocked_start"]:
            hours = data // 3600
            minutes = (data % 3600) // 60
            await interaction.response.send_message(f"🤢 **Debes esperar antes de consumir esto.**\n⏱️ Cooldown: **{hours}h {minutes:02d}m**", ephemeral=True)
            return

        if status == "energy_used":
            await interaction.response.send_message(f"🥤 **¡Consumiste una Bebida Energética!** Recuperaste +50 de energía. Energía actual: **{data}/100**", ephemeral=True)
            return

        if status == "focus_auto":
            await interaction.response.send_message("🧪 **La Poción de Enfoque se consume automáticamente** en tu próximo trabajo (+50% XP).", ephemeral=True)
            return

        if status == "shield_activated":
            await interaction.response.send_message("🛡️ **¡Escudo de Robo activado!** Inmunidad por 30 minutos.", ephemeral=True)
            return

        if status == "auto_item":
            await interaction.response.send_message("🎟️ **Este artículo se consume automáticamente** al ocurrir el evento correspondiente.", ephemeral=True)
            return

        await interaction.response.send_message("❌ Este artículo no se puede usar directamente con este comando.", ephemeral=True)

async def setup(bot):
    await bot.add_cog(Tienda(bot))
    print("Tienda cog loaded successfully.")
