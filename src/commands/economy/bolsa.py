import discord
from discord.ext import commands, tasks
from discord import app_commands
import asyncio
import logging
from datetime import datetime, time
from typing import Optional

from src.services.market_service import MarketService, MARKET_ASSETS
from src.db import (
    db_cursor,
    get_balance,
    deduct_balance,
    add_balance,
    ensure_user,
    registrar_transaccion
)
from src.utils.cooldowns import ECONOMY_COOLDOWN

logger = logging.getLogger(__name__)

# Mapeo de emojis para cada activo
ASSET_EMOJIS = {
    "agrounion": "🚜",
    "banconova": "🏦",
    "tecnocorp": "💻",
    "obsidianchain": "🔗",
    "bytecoin": "🪙",
    "moontoken": "🌙"
}

def get_price_24h_ago(asset_key: str, default_price: float) -> float:
    """Obtiene el precio más cercano a hace 24 horas desde el historial."""
    try:
        with db_cursor() as cursor:
            cursor.execute("""
                SELECT Precio FROM MarketPriceHistory 
                WHERE AssetKey = %s AND Timestamp <= NOW() - INTERVAL '24 hours'
                ORDER BY Timestamp DESC 
                LIMIT 1
            """, (asset_key,))
            row = cursor.fetchone()
            if row:
                return float(row[0])
    except Exception as e:
        logger.error(f"[BolsaCog] Error obteniendo precio histórico para {asset_key}: {e}")
    return default_price

class BolsaCog(commands.Cog):
    """Cog de Bolsa de Valores: compra/venta de activos, portafolio y simulación de precios."""

    def __init__(self, bot):
        self.bot = bot
        # Cargar precios de la DB al inicializar
        MarketService.load_prices_from_db()
        # Iniciar las tareas en segundo plano
        self.market_tick_loop.start()
        self.market_persist_loop.start()
        self.market_dividend_loop.start()

    def cog_unload(self):
        # Cancelar tareas al descargar el Cog
        self.market_tick_loop.cancel()
        self.market_persist_loop.cancel()
        self.market_dividend_loop.cancel()

    # ──────────────────────────────────────────────
    # TAREAS PROGRAMADAS
    # ──────────────────────────────────────────────

    @tasks.loop(seconds=5)
    async def market_tick_loop(self):
        """Ejecuta un tick del motor de simulación de precios cada 5 segundos."""
        try:
            # Ejecutar de forma segura fuera del hilo principal
            await asyncio.to_thread(MarketService.tick)
        except Exception as e:
            logger.error(f"[BolsaCog] Error en bucle de ticks de bolsa: {e}")

    @market_tick_loop.before_loop
    async def before_market_tick_loop(self):
        await self.bot.wait_until_ready()

    @tasks.loop(seconds=120)
    async def market_persist_loop(self):
        """Persiste los precios actuales en memoria a la DB cada 2 minutos."""
        try:
            await asyncio.to_thread(MarketService.persist_prices)
        except Exception as e:
            logger.error(f"[BolsaCog] Error en bucle de persistencia de bolsa: {e}")

    @market_persist_loop.before_loop
    async def before_market_persist_loop(self):
        await self.bot.wait_until_ready()

    @tasks.loop(time=time(hour=5, minute=0, second=0))
    async def market_dividend_loop(self):
        """Paga dividendos diariamente a las 5:00 AM a todos los portafolios activos."""
        logger.info("[BolsaCog] Iniciando pago de dividendos diarios...")
        try:
            # Obtener todos los activos que pagan dividendos
            dividend_assets = {k: v for k, v in MARKET_ASSETS.items() if v["dividendo_pct"] > 0}
            if not dividend_assets:
                return

            with db_cursor() as cursor:
                # Obtener todas las posiciones de portafolio con cantidad positiva
                cursor.execute("""
                    SELECT UserID, AssetKey, Cantidad 
                    FROM UserPortfolio 
                    WHERE Cantidad > 0 AND AssetKey = ANY(%s)
                """, (list(dividend_assets.keys()),))
                rows = cursor.fetchall()

            if not rows:
                logger.info("[BolsaCog] No hay posiciones de portafolio elegibles para dividendos hoy.")
                return

            # Agrupar pagos por usuario para enviar un solo mensaje consolidado
            payments_by_user = {}  # {user_id: {asset_key: dividend_amount}}

            for user_id, asset_key, cantidad_db in rows:
                cantidad = float(cantidad_db)
                precio_actual = MarketService.get_price(asset_key)
                pct = dividend_assets[asset_key]["dividendo_pct"]
                
                # Calcular dividendo bruto
                dividendo = cantidad * precio_actual * pct
                dividendo_int = int(dividendo)
                
                if dividendo_int > 0:
                    if user_id not in payments_by_user:
                        payments_by_user[user_id] = {}
                    payments_by_user[user_id][asset_key] = dividendo_int

            # Acreditar saldos y enviar notificaciones
            for user_id, assets_divs in payments_by_user.items():
                total_dividendo = sum(assets_divs.values())
                
                # Acreditar de forma atómica en DB
                with db_cursor() as cursor:
                    add_balance(user_id, total_dividendo, cursor=cursor)
                    # Registrar transacciones individuales para el historial
                    for a_key, amt in assets_divs.items():
                        registrar_transaccion(user_id, amt, f"Dividendo Bolsa: {a_key}", cursor=cursor)

                # Intentar enviar notificación por DM consolidada
                user = self.bot.get_user(user_id)
                if not user:
                    try:
                        user = await self.bot.fetch_user(user_id)
                    except Exception:
                        pass
                
                if user:
                    try:
                        embed_dm = discord.Embed(
                            title="📈 ¡Dividendos de Bolsa Acreditados!",
                            description="Tus inversiones en el mercado de valores han generado beneficios hoy.",
                            color=discord.Color.green()
                        )
                        detail_text = ""
                        for a_key, amt in assets_divs.items():
                            emoji = ASSET_EMOJIS.get(a_key, "")
                            name = MARKET_ASSETS[a_key]["nombre"]
                            detail_text += f"{emoji} **{name}**: `+{amt:,}` monedas\n"
                        
                        embed_dm.add_field(name="Detalle de Dividendos", value=detail_text, inline=False)
                        embed_dm.add_field(name="Total Recibido", value=f"💰 **{total_dividendo:,}** monedas", inline=False)
                        embed_dm.set_footer(text="Bolsa Simulada v1 · Los dividendos se pagan automáticamente cada mañana.")
                        await user.send(embed=embed_dm)
                    except Exception as dm_err:
                        logger.warning(f"[BolsaCog] No se pudo enviar DM de dividendos al usuario {user_id}: {dm_err}")

            logger.info(f"[BolsaCog] Pago de dividendos completado para {len(payments_by_user)} usuarios.")
        except Exception as e:
            logger.error(f"[BolsaCog] Error en tarea de dividendos de bolsa: {e}")

    @market_dividend_loop.before_loop
    async def before_market_dividend_loop(self):
        await self.bot.wait_until_ready()

    # ──────────────────────────────────────────────
    # COMANDOS DISCORD
    # ──────────────────────────────────────────────

    @app_commands.command(
        name="bolsa",
        description="Muestra el estado actual del mercado de valores y criptomonedas."
    )
    async def bolsa(self, interaction: discord.Interaction):
        await interaction.response.defer()
        
        embed = discord.Embed(
            title="📈 Mercado de Bolsa Simulada",
            description="Precios de activos en tiempo real (se actualizan cada 5s).",
            color=discord.Color.dark_blue(),
            timestamp=discord.utils.utcnow() if hasattr(discord.utils, 'utcnow') else datetime.now()
        )
        
        # Categorías separadas para mayor legibilidad
        acciones_text = ""
        cripto_text = ""
        
        for key, data in MARKET_ASSETS.items():
            precio_actual = MarketService.get_price(key)
            precio_24h = await asyncio.to_thread(get_price_24h_ago, key, data["precio_inicial"])
            
            # Calcular variación
            variacion = 0.0
            if precio_24h > 0:
                variacion = ((precio_actual - precio_24h) / precio_24h) * 100
                
            emoji = ASSET_EMOJIS.get(key, "📦")
            nombre = data["nombre"]
            
            # Formatear la línea del activo
            if variacion > 0:
                var_str = f"📈 `+{variacion:.2f}%`"
            elif variacion < 0:
                var_str = f"📉 `{variacion:.2f}%`"
            else:
                var_str = f"🟰 `0.00%`"
                
            div_info = f" | Div: `{data['dividendo_pct']*100:.1f}%`" if data["dividendo_pct"] > 0 else ""
            linea = f"{emoji} **{nombre}** (`{key.upper()}`)\n└ Price: `{precio_actual:,.2f}` monedas | Var: {var_str}{div_info}\n\n"
            
            if data["categoria"] == "accion":
                acciones_text += linea
            else:
                cripto_text += linea
                
        embed.add_field(name="🚜 Acciones y Empresas", value=acciones_text or "No hay acciones disponibles.", inline=False)
        embed.add_field(name="🔗 Criptomonedas y Fichas", value=cripto_text or "No hay criptoactivos disponibles.", inline=False)
        
        embed.set_footer(text="Impuesto por transacción: 1.5% · Usa /bolsa_comprar y /bolsa_vender para operar.")
        await interaction.followup.send(embed=embed)

    @app_commands.command(
        name="bolsa_comprar",
        description="Compra unidades de un activo financiero especificando el dinero a gastar."
    )
    @app_commands.describe(
        activo="Activo financiero a comprar",
        monto="Cantidad de monedas que deseas gastar en la compra"
    )
    @app_commands.choices(activo=[
        app_commands.Choice(name="AgroUnión (agrounion)", value="agrounion"),
        app_commands.Choice(name="BancoNova (banconova)", value="banconova"),
        app_commands.Choice(name="TecnoCorp (tecnocorp)", value="tecnocorp"),
        app_commands.Choice(name="ObsidianChain (obsidianchain)", value="obsidianchain"),
        app_commands.Choice(name="ByteCoin (bytecoin)", value="bytecoin"),
        app_commands.Choice(name="MoonToken (moontoken)", value="moontoken"),
    ])
    @ECONOMY_COOLDOWN
    async def bolsa_comprar(self, interaction: discord.Interaction, activo: str, monto: int):
        if monto <= 0:
            await interaction.response.send_message("❌ El monto a comprar debe ser mayor a 0.", ephemeral=True)
            return

        await interaction.response.defer()
        user_id = interaction.user.id
        await asyncio.to_thread(ensure_user, user_id, interaction.user.name)
        
        # Validar activo
        if activo not in MARKET_ASSETS:
            await interaction.followup.send("❌ El activo seleccionado no es válido.", ephemeral=True)
            return

        # 1. Verificar balance del jugador
        balance = await asyncio.to_thread(get_balance, user_id)
        if balance < monto:
            embed = discord.Embed(
                title="❌ Compra Rechazada",
                description=f"No tienes suficientes monedas para realizar esta operación.\n💰 Tu saldo actual: `{balance:,}` monedas.",
                color=discord.Color.red()
            )
            await interaction.followup.send(embed=embed)
            return

        # 2. Descontar balance de forma segura
        success, nuevo_saldo = await asyncio.to_thread(deduct_balance, user_id, monto)
        if not success:
            embed = discord.Embed(
                title="❌ Compra Rechazada",
                description="Hubo un error procesando tu saldo. Inténtalo de nuevo.",
                color=discord.Color.red()
            )
            await interaction.followup.send(embed=embed)
            return

        # 3. Calcular cantidad e impuestos
        from src.utils.economy_config import TRANSACTION_TAX
        tax_pct = TRANSACTION_TAX.get("bolsa", 0.015)
        impuesto_int = int(monto * tax_pct)
        monto_neto_int = monto - impuesto_int
        
        precio_actual = MarketService.get_price(activo)
        cantidad_comprada = monto_neto_int / precio_actual

        # 4. Actualizar portafolio del jugador de forma atómica
        try:
            with db_cursor() as cursor:
                # Bloquear fila del portafolio para el usuario
                cursor.execute("""
                    SELECT Cantidad, CostoPromedio FROM UserPortfolio 
                    WHERE UserID = %s AND AssetKey = %s
                    FOR UPDATE
                """, (user_id, activo))
                row = cursor.fetchone()
                
                if row:
                    old_qty = float(row[0])
                    old_cost = float(row[1])
                    new_qty = old_qty + cantidad_comprada
                    # Actualizar costo promedio ponderado
                    new_cost = (old_qty * old_cost + cantidad_comprada * precio_actual) / new_qty
                    
                    cursor.execute("""
                        UPDATE UserPortfolio 
                        SET Cantidad = %s, CostoPromedio = %s
                        WHERE UserID = %s AND AssetKey = %s
                    """, (new_qty, new_cost, user_id, activo))
                else:
                    new_qty = cantidad_comprada
                    new_cost = precio_actual
                    
                    cursor.execute("""
                        INSERT INTO UserPortfolio (UserID, AssetKey, Cantidad, CostoPromedio)
                        VALUES (%s, %s, %s, %s)
                    """, (user_id, activo, new_qty, new_cost))
                
                # Registrar la transacción en el historial del bot
                registrar_transaccion(
                    user_id, 
                    -monto, 
                    f"Bolsa Compra: {cantidad_comprada:.6f} unidades de {activo}", 
                    cursor=cursor
                )
        except Exception as e:
            logger.error(f"[BolsaCog] Error de base de datos en compra de {activo} para {user_id}: {e}")
            # Reintegrar saldo al usuario
            await asyncio.to_thread(add_balance, user_id, monto)
            await interaction.followup.send("❌ Error interno al registrar tu compra. Tu saldo ha sido reembolsado.", ephemeral=True)
            return

        # 5. Aplicar impacto de gran operación comercial en el mercado
        await asyncio.to_thread(MarketService.apply_large_operation_impact, activo, cantidad_comprada, is_buy=True)

        # 6. Responder con embed de éxito
        asset_data = MARKET_ASSETS[activo]
        emoji = ASSET_EMOJIS.get(activo, "📦")
        
        embed = discord.Embed(
            title=f"🛒 Compra Exitosa — {asset_data['nombre']}",
            color=discord.Color.green(),
            timestamp=discord.utils.utcnow() if hasattr(discord.utils, 'utcnow') else datetime.now()
        )
        embed.add_field(name="💰 Monto Gastado", value=f"`{monto:,}` monedas", inline=True)
        embed.add_field(name="🛡️ Impuesto (1.5%)", value=f"`{impuesto_int:,}` monedas (destruido)", inline=True)
        embed.add_field(name="📉 Valor Efectivo", value=f"`{monto_neto_int:,}` monedas", inline=True)
        embed.add_field(name="🏷️ Precio Unitario", value=f"`{precio_actual:,.2f}` monedas", inline=True)
        embed.add_field(name="📦 Unidades Adquiridas", value=f"`{cantidad_comprada:.6f}`", inline=True)
        embed.add_field(name="💼 Tu Portafolio", value=f"Total actual: `{new_qty:.6f}` unidades\nCosto Promedio: `{new_cost:,.2f}` monedas", inline=False)
        embed.set_footer(text=f"Saldo restante: {nuevo_saldo:,} monedas")
        
        await interaction.followup.send(embed=embed)

    @app_commands.command(
        name="bolsa_vender",
        description="Vende una cantidad específica de unidades de un activo al precio actual."
    )
    @app_commands.describe(
        activo="Activo financiero a vender",
        cantidad="Cantidad de unidades a vender (acepta decimales)"
    )
    @app_commands.choices(activo=[
        app_commands.Choice(name="AgroUnión (agrounion)", value="agrounion"),
        app_commands.Choice(name="BancoNova (banconova)", value="banconova"),
        app_commands.Choice(name="TecnoCorp (tecnocorp)", value="tecnocorp"),
        app_commands.Choice(name="ObsidianChain (obsidianchain)", value="obsidianchain"),
        app_commands.Choice(name="ByteCoin (bytecoin)", value="bytecoin"),
        app_commands.Choice(name="MoonToken (moontoken)", value="moontoken"),
    ])
    @ECONOMY_COOLDOWN
    async def bolsa_vender(self, interaction: discord.Interaction, activo: str, cantidad: float):
        if cantidad <= 0:
            await interaction.response.send_message("❌ La cantidad a vender debe ser mayor a 0.", ephemeral=True)
            return

        await interaction.response.defer()
        user_id = interaction.user.id
        await asyncio.to_thread(ensure_user, user_id, interaction.user.name)

        # Validar activo
        if activo not in MARKET_ASSETS:
            await interaction.followup.send("❌ El activo seleccionado no es válido.", ephemeral=True)
            return

        precio_actual = MarketService.get_price(activo)
        monto_bruto = cantidad * precio_actual
        
        # Calcular impuestos
        from src.utils.economy_config import TRANSACTION_TAX
        tax_pct = TRANSACTION_TAX.get("bolsa", 0.015)
        monto_bruto_int = int(monto_bruto)
        impuesto_int = int(monto_bruto * tax_pct)
        monto_neto_int = monto_bruto_int - impuesto_int

        if monto_neto_int <= 0:
            await interaction.followup.send("❌ La cantidad especificada a vender es demasiado pequeña y no genera saldo neto.", ephemeral=True)
            return

        try:
            with db_cursor() as cursor:
                # Bloquear fila de portafolio
                cursor.execute("""
                    SELECT Cantidad, CostoPromedio FROM UserPortfolio 
                    WHERE UserID = %s AND AssetKey = %s
                    FOR UPDATE
                """, (user_id, activo))
                row = cursor.fetchone()
                
                if not row:
                    embed = discord.Embed(
                        title="❌ Venta Rechazada",
                        description=f"No posees ninguna unidad de `{activo.upper()}` en tu portafolio.",
                        color=discord.Color.red()
                    )
                    await interaction.followup.send(embed=embed)
                    return
                    
                old_qty = float(row[0])
                costo_promedio = float(row[1])
                
                if old_qty < cantidad:
                    embed = discord.Embed(
                        title="❌ Venta Rechazada",
                        description=f"No tienes suficientes unidades para realizar la venta.\n💼 Posees: `{old_qty:.6f}` unidades de `{activo.upper()}`.",
                        color=discord.Color.red()
                    )
                    await interaction.followup.send(embed=embed)
                    return
                
                new_qty = old_qty - cantidad
                
                # Actualizar base de datos
                if new_qty < 1e-9:
                    # Si vende todo, borrar registro
                    cursor.execute("""
                        DELETE FROM UserPortfolio 
                        WHERE UserID = %s AND AssetKey = %s
                    """, (user_id, activo))
                    new_qty = 0.0
                else:
                    cursor.execute("""
                        UPDATE UserPortfolio 
                        SET Cantidad = %s
                        WHERE UserID = %s AND AssetKey = %s
                    """, (new_qty, user_id, activo))
                
                # Acreditar saldo neto al usuario
                add_balance(user_id, monto_neto_int, cursor=cursor)
                
                # Registrar transacción en historial
                registrar_transaccion(
                    user_id,
                    monto_neto_int,
                    f"Bolsa Venta: {cantidad:.6f} unidades de {activo}",
                    cursor=cursor
                )
        except Exception as e:
            logger.error(f"[BolsaCog] Error de base de datos en venta de {activo} para {user_id}: {e}")
            await interaction.followup.send("❌ Ocurrió un error al procesar tu venta. Inténtalo de nuevo.", ephemeral=True)
            return

        # 5. Aplicar impacto de gran venta en el mercado
        await asyncio.to_thread(MarketService.apply_large_operation_impact, activo, cantidad, is_buy=False)

        # 6. Responder con embed de éxito
        asset_data = MARKET_ASSETS[activo]
        emoji = ASSET_EMOJIS.get(activo, "📦")
        
        embed = discord.Embed(
            title=f"💰 Venta Exitosa — {asset_data['nombre']}",
            color=discord.Color.green(),
            timestamp=discord.utils.utcnow() if hasattr(discord.utils, 'utcnow') else datetime.now()
        )
        embed.add_field(name="📦 Cantidad Vendida", value=f"`{cantidad:.6f}` unidades", inline=True)
        embed.add_field(name="🏷️ Precio Unitario", value=f"`{precio_actual:,.2f}` monedas", inline=True)
        embed.add_field(name="📉 Valor Bruto", value=f"`{monto_bruto_int:,}` monedas", inline=True)
        embed.add_field(name="🛡️ Impuesto (1.5%)", value=f"`{impuesto_int:,}` monedas (destruido)", inline=True)
        embed.add_field(name="💰 Acreditado Neto", value=f"**{monto_neto_int:,}** monedas", inline=True)
        embed.add_field(name="💼 Portafolio Restante", value=f"`{new_qty:.6f}` unidades de {asset_data['nombre']}", inline=False)
        
        # Obtener nuevo balance para mostrar
        nuevo_balance = await asyncio.to_thread(get_balance, user_id)
        embed.set_footer(text=f"Saldo actual: {nuevo_balance:,} monedas")
        
        await interaction.followup.send(embed=embed)

    @app_commands.command(
        name="bolsa_portafolio",
        description="Muestra el estado de tu portafolio de activos, costo promedio y ganancias no realizadas."
    )
    async def bolsa_portafolio(self, interaction: discord.Interaction):
        await interaction.response.defer()
        user_id = interaction.user.id
        await asyncio.to_thread(ensure_user, user_id, interaction.user.name)

        try:
            with db_cursor() as cursor:
                cursor.execute("""
                    SELECT AssetKey, Cantidad, CostoPromedio 
                    FROM UserPortfolio 
                    WHERE UserID = %s AND Cantidad > 0
                """, (user_id,))
                rows = cursor.fetchall()
        except Exception as e:
            logger.error(f"[BolsaCog] Error obteniendo portafolio para {user_id}: {e}")
            await interaction.followup.send("❌ Ocurrió un error al cargar tu portafolio.", ephemeral=True)
            return

        if not rows:
            embed = discord.Embed(
                title="💼 Tu Portafolio Financiero",
                description="⚠️ **No posees ningún activo en tu portafolio en este momento.**\n\nUsa `/bolsa` para consultar los activos disponibles y `/bolsa_comprar` para realizar tu primera inversión.",
                color=discord.Color.orange(),
                timestamp=discord.utils.utcnow() if hasattr(discord.utils, 'utcnow') else datetime.now()
            )
            await interaction.followup.send(embed=embed)
            return

        embed = discord.Embed(
            title="💼 Tu Portafolio Financiero",
            description="Resumen de tus inversiones y rendimiento no realizado en tiempo real.",
            color=discord.Color.teal(),
            timestamp=discord.utils.utcnow() if hasattr(discord.utils, 'utcnow') else datetime.now()
        )

        total_valor_portafolio = 0.0
        total_costo_portafolio = 0.0

        for row in rows:
            asset_key = row[0]
            cantidad = float(row[1])
            costo_promedio = float(row[2])
            
            precio_actual = MarketService.get_price(asset_key)
            valor_actual = cantidad * precio_actual
            costo_total = cantidad * costo_promedio
            
            # Ganancia / Pérdida no realizada
            ganancia = valor_actual - costo_total
            ganancia_pct = (ganancia / costo_total) * 100.0 if costo_total > 0 else 0.0
            
            total_valor_portafolio += valor_actual
            total_costo_portafolio += costo_total
            
            emoji = ASSET_EMOJIS.get(asset_key, "📦")
            asset_data = MARKET_ASSETS[asset_key]
            
            # Formato de ganancia no realizada
            if ganancia > 0:
                ganancia_str = f"🟢 `+{ganancia:,.2f}` (`+{ganancia_pct:.2f}%`)"
            elif ganancia < 0:
                ganancia_str = f"🔴 `{ganancia:,.2f}` (`{ganancia_pct:.2f}%`)"
            else:
                ganancia_str = f"⚪ `0.00` (`0.00%`)"
                
            embed.add_field(
                name=f"{emoji} {asset_data['nombre']} ({asset_key.upper()})",
                value=(
                    f"📦 **Unidades:** `{cantidad:.6f}`\n"
                    f"🏷️ **Costo Promedio:** `{costo_promedio:,.2f}` monedas\n"
                    f"🏷️ **Precio Actual:** `{precio_actual:,.2f}` monedas\n"
                    f"💰 **Valor de Posición:** `{valor_actual:,.2f}` monedas\n"
                    f"✨ **Rendimiento:** {ganancia_str}"
                ),
                inline=True
            )

        # Totales globales del portafolio
        ganancia_total = total_valor_portafolio - total_costo_portafolio
        ganancia_total_pct = (ganancia_total / total_costo_portafolio) * 100.0 if total_costo_portafolio > 0 else 0.0
        
        if ganancia_total > 0:
            total_performance_str = f"🟢 **+{ganancia_total:,.2f}** monedas (`+{ganancia_total_pct:.2f}%`)"
        elif ganancia_total < 0:
            total_performance_str = f"🔴 **{ganancia_total:,.2f}** monedas (`{ganancia_total_pct:.2f}%`)"
        else:
            total_performance_str = f"⚪ **0.00** monedas (`0.00%`)"

        embed.add_field(
            name="📊 Resumen Total",
            value=(
                f"💵 **Inversión Total:** `{total_costo_portafolio:,.2f}` monedas\n"
                f"💰 **Valor Total del Portafolio:** `{total_valor_portafolio:,.2f}` monedas\n"
                f"✨ **Rendimiento Global:** {total_performance_str}"
            ),
            inline=False
        )

        await interaction.followup.send(embed=embed)

async def setup(bot):
    await bot.add_cog(BolsaCog(bot))
    logger.info("Cog Bolsa cargado exitosamente.")
