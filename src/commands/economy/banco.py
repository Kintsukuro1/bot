import discord
from discord.ext import commands, tasks
from discord import app_commands
import asyncio
import logging
import os
from datetime import datetime, time, timedelta
from typing import Optional

from src.services.bank_service import BankService
from src.db import (
    ensure_user,
    get_user_loan,
    get_user_protection_info,
    cobrar_cuotas_proteccion_db,
    get_balance,
    get_user_prestige_level,
    pagar_bonos_prestigio_mensuales_db
)
from src.utils.cooldowns import ECONOMY_COOLDOWN

logger = logging.getLogger(__name__)


class BancoCog(commands.Cog):
    """Cog del Banco Central: préstamos, pagos, cuotas de protección y tareas diarias."""

    def __init__(self, bot):
        self.bot = bot
        self.daily_interest_task.start()
        self.daily_protection_fee_task.start()
        self.monthly_prestige_bonus_task.start()
        self.daily_investment_resolution_task.start()

    def cog_unload(self):
        self.daily_interest_task.cancel()
        self.daily_protection_fee_task.cancel()
        self.monthly_prestige_bonus_task.cancel()
        self.daily_investment_resolution_task.cancel()

    # ──────────────────────────────────────────────
    # TAREAS DIARIAS (INTERÉS Y CUOTA DE PROTECCIÓN)
    # ──────────────────────────────────────────────

    @tasks.loop(time=time(hour=1, minute=0, second=0))
    async def daily_interest_task(self):
        """Aplica 0.5% de interés diario a todos los préstamos activos y marca mora."""
        logger.info("[BancoCentral] Aplicando interés diario...")
        try:
            resultado = await BankService.apply_daily_interest()
            logger.info(
                f"[BancoCentral] Interés aplicado: "
                f"{resultado['prestamos_procesados']} préstamos procesados, "
                f"+{resultado['total_interes']:,} monedas a reservas, "
                f"{len(resultado['en_mora'])} usuarios marcados en mora."
            )
        except Exception as e:
            logger.error(f"[BancoCentral] Error en tarea de interés diario: {e}")

    @daily_interest_task.before_loop
    async def before_daily_interest(self):
        await self.bot.wait_until_ready()

    @tasks.loop(time=time(hour=2, minute=0, second=0))
    async def daily_protection_fee_task(self):
        """Cobra la cuota de protección diaria a todos los usuarios correspondientes."""
        logger.info("[BancoCentral] Iniciando cobro de Cuota de Protección diaria...")
        try:
            resultados = await asyncio.to_thread(cobrar_cuotas_proteccion_db)
            logger.info(f"[BancoCentral] Cobro de protección completado para {len(resultados)} usuarios.")
            
            # Notificar a los usuarios vía DM
            for res in resultados:
                user_id = res['user_id']
                cobrado = res['cobrado']
                exito = res['exito']
                
                user = self.bot.get_user(user_id)
                if not user:
                    try:
                        user = await self.bot.fetch_user(user_id)
                    except Exception:
                        pass
                
                if user:
                    try:
                        if exito:
                            await user.send(
                                f"🛡️ Se cobró tu Cuota de Protección de **{cobrado:,}** monedas — "
                                f"tu escudo contra robos está activo por 24 horas más (30 min por robo en vez de 3)."
                            )
                        else:
                            await user.send(
                                f"⚠️ No se pudo cobrar tu Cuota de Protección completa (se cobraron **{cobrado:,}** monedas). "
                                f"Tu escudo extendido de 30 minutos no estará activo."
                            )
                    except Exception as dm_err:
                        logger.warning(f"[BancoCentral] No se pudo enviar DM al usuario {user_id}: {dm_err}")
                        
        except Exception as e:
            logger.error(f"[BancoCentral] Error en tarea de cuota de protección diaria: {e}")

    @daily_protection_fee_task.before_loop
    async def before_daily_protection_fee(self):
        await self.bot.wait_until_ready()

    @tasks.loop(time=time(hour=3, minute=0, second=0))
    async def monthly_prestige_bonus_task(self):
        """Otorga el bono mensual de prestigio (100.000 monedas) a los usuarios Prestigio III+."""
        logger.info("[BancoCentral] Iniciando pago de Bonos Mensuales de Prestigio...")
        try:
            resultados = await asyncio.to_thread(pagar_bonos_prestigio_mensuales_db)
            if resultados:
                logger.info(f"[BancoCentral] Se otorgaron bonos de prestigio a {len(resultados)} usuarios.")
                for res in resultados:
                    user_id = res['user_id']
                    lvl = res['prestige_level']
                    user = self.bot.get_user(user_id)
                    if not user:
                        try:
                            user = await self.bot.fetch_user(user_id)
                        except Exception:
                            pass
                    if user:
                        try:
                            await user.send(
                                f"🌟 **¡Bono Mensual de Prestigio!** 🌟\n"
                                f"Se han acreditado **100,000** monedas a tu cuenta por mantener tu estatus de **Prestigio {lvl}**.\n"
                                f"¡Gracias por tu fidelidad e inversión en el servidor! 👑"
                            )
                        except Exception as dm_err:
                            logger.warning(f"[BancoCentral] No se pudo enviar DM de bono de prestigio al usuario {user_id}: {dm_err}")
            else:
                logger.info("[BancoCentral] No hubo usuarios elegibles para el bono de prestigio mensual hoy.")
        except Exception as e:
            logger.error(f"[BancoCentral] Error en tarea de bono de prestigio mensual: {e}")

    @monthly_prestige_bonus_task.before_loop
    async def before_monthly_prestige_bonus(self):
        await self.bot.wait_until_ready()

    @tasks.loop(time=time(hour=4, minute=0, second=0))
    async def daily_investment_resolution_task(self):
        """Revisa e inscribe los resultados de todas las inversiones de plazo fijo que han vencido."""
        logger.info("[BancoCentral] Resolviendo inversiones de plazo fijo vencidas...")
        try:
            resultado = await BankService.resolve_matured_investments()
            if resultado['count'] > 0:
                logger.info(
                    f"[BancoCentral] Inversiones resueltas: {resultado['count']} procesadas, "
                    f"total pagado: {resultado['total_payout']:,} monedas."
                )
                # Notificar a cada usuario por DM
                for res in resultado['results']:
                    user_id = res['user_id']
                    monto_inicial = res['monto_inicial']
                    payout = res['payout']
                    diff = res['diff']
                    label = res['label']
                    mult = res['mult']
                    
                    user = self.bot.get_user(user_id)
                    if not user:
                        try:
                            user = await self.bot.fetch_user(user_id)
                        except Exception:
                            pass
                    
                    if user:
                        try:
                            sign = "+" if diff >= 0 else ""
                            emoji = "📈" if diff > 0 else ("📉" if diff < 0 else "🟰")
                            await user.send(
                                f"🏦 **¡Tu Inversión en el Banco Central ha vencido!** {emoji}\n\n"
                                f"💰 **Monto Invertido:** {monto_inicial:,} monedas\n"
                                f"📊 **Resultado:** *{label}* (Multiplicador: x{mult:.2f})\n"
                                f"💵 **Monto Recibido:** {payout:,} monedas\n"
                                f"✨ **Diferencia:** `{sign}{diff:,}` monedas"
                            )
                        except Exception as dm_err:
                            logger.warning(f"[BancoCentral] No se pudo enviar DM de inversión al usuario {user_id}: {dm_err}")
            else:
                logger.info("[BancoCentral] No hay inversiones de plazo fijo vencidas hoy.")
        except Exception as e:
            logger.error(f"[BancoCentral] Error en tarea de resolución de inversiones: {e}")

    @daily_investment_resolution_task.before_loop
    async def before_daily_investment_resolution(self):
        await self.bot.wait_until_ready()

    # ──────────────────────────────────────────────
    # COMANDO /banco
    # ──────────────────────────────────────────────

    @app_commands.command(
        name="banco",
        description="Consulta las reservas del Banco Central y el estado de tu préstamo."
    )
    async def banco(self, interaction: discord.Interaction):
        await interaction.response.defer()
        user_id = interaction.user.id
        await asyncio.to_thread(ensure_user, user_id, interaction.user.name)

        reservas, prestamos = await asyncio.gather(
            BankService.get_reserves(),
            BankService.get_all_loans(user_id),
        )

        embed = discord.Embed(
            title="🏦 Banco Central",
            color=discord.Color.gold(),
            timestamp=discord.utils.utcnow() if hasattr(discord.utils, 'utcnow') else datetime.now()
        )
        embed.add_field(
            name="💰 Reservas Totales",
            value=f"`{reservas:,}` monedas",
            inline=False
        )

        prestamos_activos = [p for p in prestamos if p['MontoAdeudado'] > 0]

        if prestamos_activos:
            for p in prestamos_activos:
                mora_str = "⚠️ **EN MORA** — se retiene 10% de cada trabajo" if p['EnMora'] else "✅ Al día"
                venc = p['FechaVencimiento']
                venc_str = venc.strftime("%d/%m/%Y %H:%M") if venc else "N/A"

                embed.add_field(
                    name=f"📋 Tu Préstamo Activo (Slot {p['LoanSlot']})",
                    value=(
                        f"💳 **Deuda:** `{p['MontoAdeudado']:,}` monedas\n"
                        f"📅 **Vencimiento:** `{venc_str}`\n"
                        f"📊 **Estado:** {mora_str}\n"
                        f"🎯 **Límite de préstamo:** `{p['LimitePrestamo']:,}` monedas"
                    ),
                    inline=False
                )
        else:
            prestige_lvl = await asyncio.to_thread(get_user_prestige_level, user_id)
            limite_default = 500000 if prestige_lvl >= 2 else 200000
            limite = prestamos[0]['LimitePrestamo'] if prestamos else limite_default
            
            prestige_note = "\n🌟 *Al tener Prestigio II, puedes tener hasta 2 préstamos simultáneos.*" if prestige_lvl >= 2 else ""
            embed.add_field(
                name="📋 Tu Préstamo",
                value=(
                    f"✅ Sin deuda activa.\n"
                    f"🎯 **Límite disponible:** `{limite:,}` monedas"
                    f"{prestige_note}"
                ),
                inline=False
            )

        embed.set_footer(
            text="Usa /banco_prestamo para solicitar un préstamo · /banco_pagar para pagar tu deuda · /proteccion para tu escudo"
        )
        await interaction.followup.send(embed=embed)

    # ──────────────────────────────────────────────
    # COMANDO /banco_prestamo
    # ──────────────────────────────────────────────

    @app_commands.command(
        name="banco_prestamo",
        description="Solicita un préstamo al Banco Central."
    )
    @app_commands.describe(monto="Cantidad de monedas a solicitar en préstamo")
    @ECONOMY_COOLDOWN
    async def banco_prestamo(self, interaction: discord.Interaction, monto: int):
        await interaction.response.defer()
        user_id = interaction.user.id
        await asyncio.to_thread(ensure_user, user_id, interaction.user.name)

        success, mensaje = await BankService.request_loan(user_id, monto)

        if success:
            reservas = await BankService.get_reserves()
            embed = discord.Embed(
                title="🏦 Préstamo Aprobado",
                description=mensaje,
                color=discord.Color.green(),
            )
            embed.add_field(
                name="💰 Reservas del banco tras el préstamo",
                value=f"`{reservas:,}` monedas",
                inline=False
            )
        else:
            embed = discord.Embed(
                title="🏦 Préstamo Denegado",
                description=mensaje,
                color=discord.Color.red(),
            )

        await interaction.followup.send(embed=embed)

    # ──────────────────────────────────────────────
    # COMANDO /banco_pagar
    # ──────────────────────────────────────────────

    @app_commands.command(
        name="banco_pagar",
        description="Paga (total o parcialmente) tu préstamo con el Banco Central."
    )
    @app_commands.describe(
        monto="Cantidad de monedas a abonar a tu deuda",
        slot="Slot de préstamo a pagar (1 o 2)"
    )
    @ECONOMY_COOLDOWN
    async def banco_pagar(self, interaction: discord.Interaction, monto: int, slot: int = 1):
        if slot not in (1, 2):
            await interaction.response.send_message("❌ El slot debe ser 1 o 2.", ephemeral=True)
            return

        await interaction.response.defer()
        user_id = interaction.user.id
        await asyncio.to_thread(ensure_user, user_id, interaction.user.name)

        success, mensaje = await BankService.repay_loan(user_id, monto, slot)

        color = discord.Color.green() if success else discord.Color.red()
        titulo = "🏦 Pago Registrado" if success else "🏦 Error al Pagar"

        embed = discord.Embed(title=titulo, description=mensaje, color=color)

        if success:
            # Mostrar deuda restante si la hay
            prestamo = await BankService.get_user_loan(user_id, slot)
            if prestamo and prestamo['MontoAdeudado'] > 0:
                mora_str = "⚠️ Aún en mora." if prestamo['EnMora'] else "✅ Sin mora."
                embed.add_field(
                    name=f"📋 Estado actual (Slot {slot})",
                    value=(
                        f"💳 Deuda restante: `{prestamo['MontoAdeudado']:,}` monedas\n"
                        f"{mora_str}"
                    ),
                    inline=False
                )

        await interaction.followup.send(embed=embed)

    # ──────────────────────────────────────────────
    # COMANDO /proteccion
    # ──────────────────────────────────────────────

    @app_commands.command(
        name="proteccion",
        description="Muestra el estado de tu escudo de protección extendido contra robos."
    )
    async def proteccion(self, interaction: discord.Interaction):
        await interaction.response.defer()
        user_id = interaction.user.id
        await asyncio.to_thread(ensure_user, user_id, interaction.user.name)

        ultimo_pago, ultimo_monto = await asyncio.to_thread(get_user_protection_info, user_id)
        balance = await asyncio.to_thread(get_balance, user_id)

        # Calcular proyección
        proyeccion = 0
        if balance > 500000:
            excedente = balance - 500000
            cuota = 0
            
            # Tramo 1: hasta 10M (1% = 100 bps)
            t1 = min(excedente, 10000000)
            cuota += (t1 * 100) // 10000
            excedente -= t1
            
            if excedente > 0:
                # Tramo 2: de 10M a 100M (2% = 200 bps)
                t2 = min(excedente, 90000000)
                cuota += (t2 * 200) // 10000
                excedente -= t2
                
            if excedente > 0:
                # Tramo 3: de 100M a 1000M (3% = 300 bps)
                t3 = min(excedente, 900000000)
                cuota += (t3 * 300) // 10000
                excedente -= t3
                
            if excedente > 0:
                # Tramo 4: más de 1000M (5% = 500 bps)
                cuota += (excedente * 500) // 10000
                
            proyeccion = cuota
            prestige_lvl = await asyncio.to_thread(get_user_prestige_level, user_id)
            if prestige_lvl >= 2:
                proyeccion = (proyeccion * 8000) // 10000

        # Calcular estado del escudo extendido
        activo = False
        tiempo_restante_str = ""
        if ultimo_pago:
            if ultimo_pago.tzinfo is not None:
                ultimo_pago = ultimo_pago.replace(tzinfo=None)
            transcurrido = datetime.now() - ultimo_pago
            if transcurrido < timedelta(hours=24):
                activo = True
                restante = timedelta(hours=24) - transcurrido
                horas, resto = divmod(int(restante.total_seconds()), 3600)
                minutos, _ = divmod(resto, 60)
                tiempo_restante_str = f"{horas}h {minutos}m"

        embed = discord.Embed(
            title="🛡️ Escudo de Protección contra Robos",
            color=discord.Color.blue(),
            timestamp=discord.utils.utcnow() if hasattr(discord.utils, 'utcnow') else datetime.now()
        )

        if activo:
            embed.description = (
                f"✅ **Escudo Extendido Activo**\n"
                f"⏱️ **Tiempo restante:** `{tiempo_restante_str}`\n"
                f"⚡ **Efecto:** Recibes **30 minutos** de protección contra robos cada vez que te roban con éxito."
            )
        else:
            embed.description = (
                f"❌ **Escudo Extendido Inactivo**\n"
                f"⚡ **Efecto actual:** Recibes el escudo base de **3 minutos** tras ser robado.\n"
                f"💡 *Para activarlo, debes pagar tu Cuota de Protección diaria.*"
            )

        embed.add_field(
            name="📊 Último Cobro",
            value=f"`{ultimo_monto:,}` monedas" if ultimo_monto > 0 else "Nunca cobrado",
            inline=True
        )
        embed.add_field(
            name="🔮 Siguiente Proyección",
            value=f"`{proyeccion:,}` monedas" if proyeccion > 0 else "Exento (balance < 500k)",
            inline=True
        )

        embed.set_footer(
            text="La cuota se calcula progresivamente sobre el balance que exceda los 500k y se cobra cada 24h."
        )
        await interaction.followup.send(embed=embed)

    # ──────────────────────────────────────────────
    # COMANDO ADMIN: forzar interés diario y cuotas
    # ──────────────────────────────────────────────

    @app_commands.command(
        name="banco_tick",
        description="[ADMIN] Fuerza la aplicación del interés diario, cobro de cuotas y bonos de prestigio manualmente."
    )
    async def banco_tick(self, interaction: discord.Interaction):
        if not await self.bot.is_owner(interaction.user):
            await interaction.response.send_message(
                "❌ Solo el dueño del bot puede usar este comando.", ephemeral=True
            )
            return

        await interaction.response.defer(thinking=True)
        try:
            # 1. Aplicar interés
            resultado_interes = await BankService.apply_daily_interest()
            
            # 2. Cobrar cuotas
            resultado_cuotas = await asyncio.to_thread(cobrar_cuotas_proteccion_db)
            total_cobrado_cuotas = sum(r['cobrado'] for r in resultado_cuotas)
            exitosos_cuotas = sum(1 for r in resultado_cuotas if r['exito'])

            # 3. Pagar bonos de prestigio mensual
            resultado_bonos = await asyncio.to_thread(pagar_bonos_prestigio_mensuales_db)

            # 4. Resolver inversiones vencidas
            resultado_inversiones = await BankService.resolve_matured_investments()

            embed = discord.Embed(
                title="🏦 Ciclo Bancario Diario Aplicado (Manual)",
                color=discord.Color.blue(),
            )
            embed.add_field(name="Interés: Préstamos procesados", value=str(resultado_interes['prestamos_procesados']), inline=True)
            embed.add_field(name="Interés generado", value=f"{resultado_interes['total_interes']:,} monedas", inline=True)
            embed.add_field(name="Usuarios en mora", value=str(len(resultado_interes['en_mora'])), inline=True)
            
            embed.add_field(name="Cuotas: Usuarios evaluados", value=str(len(resultado_cuotas)), inline=True)
            embed.add_field(name="Cuotas: Cobros completos", value=str(exitosos_cuotas), inline=True)
            embed.add_field(name="Total recaudado por protección", value=f"{total_cobrado_cuotas:,} monedas", inline=True)
            
            embed.add_field(name="Bonos Prestigio: Pagados", value=str(len(resultado_bonos)), inline=True)
            embed.add_field(name="Inversiones: Resueltas", value=str(resultado_inversiones['count']), inline=True)
            embed.add_field(name="Inversiones: Total pagado", value=f"{resultado_inversiones['total_payout']:,} monedas", inline=True)
            
            # Notificar a los usuarios de las inversiones resueltas manualmente
            if resultado_inversiones['count'] > 0:
                for res in resultado_inversiones['results']:
                    user_id = res['user_id']
                    monto_inicial = res['monto_inicial']
                    payout = res['payout']
                    diff = res['diff']
                    label = res['label']
                    mult = res['mult']
                    
                    user = self.bot.get_user(user_id)
                    if not user:
                        try:
                            user = await self.bot.fetch_user(user_id)
                        except Exception:
                            pass
                    if user:
                        try:
                            sign = "+" if diff >= 0 else ""
                            emoji = "📈" if diff > 0 else ("📉" if diff < 0 else "🟰")
                            await user.send(
                                f"🏦 **¡Tu Inversión en el Banco Central ha vencido! (Manual Tick)** {emoji}\n\n"
                                f"💰 **Monto Invertido:** {monto_inicial:,} monedas\n"
                                f"📊 **Resultado:** *{label}* (Multiplicador: x{mult:.2f})\n"
                                f"💵 **Monto Recibido:** {payout:,} monedas\n"
                                f"✨ **Diferencia:** `{sign}{diff:,}` monedas"
                            )
                        except Exception as dm_err:
                            logger.warning(f"[BancoCentral] No se pudo enviar DM de inversión manual al usuario {user_id}: {dm_err}")

            await interaction.followup.send(embed=embed)
        except Exception as e:
            logger.error(f"[BancoCentral] Error en banco_tick: {e}")
            await interaction.followup.send(f"❌ Error: {e}", ephemeral=True)

    # ──────────────────────────────────────────────
    # COMANDO /banco_invertir
    # ──────────────────────────────────────────────

    @app_commands.command(
        name="banco_invertir",
        description="Invierte monedas a plazo fijo por 7 días con riesgo de ganancia/pérdida."
    )
    @app_commands.describe(monto="Cantidad de monedas a invertir")
    @ECONOMY_COOLDOWN
    async def banco_invertir(self, interaction: discord.Interaction, monto: int):
        if monto <= 0:
            await interaction.response.send_message("❌ El monto a invertir debe ser mayor a 0.", ephemeral=True)
            return

        await interaction.response.defer()
        user_id = interaction.user.id
        await asyncio.to_thread(ensure_user, user_id, interaction.user.name)

        result = await BankService.start_investment(user_id, monto)
        
        if result.success:
            color = discord.Color.green()
            titulo = "🏦 Inversión Iniciada"
            mensaje = f"✅ ¡Inversión de **{monto:,}** monedas iniciada! Vencerá el {result.vencimiento.strftime('%d/%m/%Y a las %H:%M')}."
            embed = discord.Embed(title=titulo, description=mensaje, color=color)
            embed.add_field(
                name="📊 Detalles de la Inversión",
                value=(
                    f"🔒 **Monto Bloqueado:** `{monto:,}` monedas\n"
                    f"📅 **Vencimiento:** `{result.vencimiento.strftime('%d/%m/%Y %H:%M')}`\n"
                    f"⚠️ **Nota:** No se permite el retiro anticipado. Los fondos se liberarán automáticamente al vencer."
                ),
                inline=False
            )
            embed.set_footer(text="¡Suerte con tu inversión!")
        else:
            color = discord.Color.red()
            titulo = "🏦 Error al Invertir"
            if result.reason == "ACTIVE_INVESTMENT_EXISTS":
                mensaje = "❌ Ya tienes una inversión activa en curso. Debes esperar a que venza."
            elif result.reason == "IN_MORA":
                mensaje = "❌ Estás en **mora** en uno de tus préstamos. No puedes realizar inversiones con el Banco Central."
            elif result.reason == "INSUFFICIENT_FUNDS":
                mensaje = f"❌ No tienes suficiente saldo para invertir {monto:,} monedas. Saldo actual: {result.new_balance:,} monedas."
            else:
                mensaje = "❌ Error al descontar saldo o procesar la inversión. Inténtalo de nuevo."
            embed = discord.Embed(title=titulo, description=mensaje, color=color)
            
        await interaction.followup.send(embed=embed)

    # ──────────────────────────────────────────────
    # COMANDO /banco_inversion
    # ──────────────────────────────────────────────

    @app_commands.command(
        name="banco_inversion",
        description="Muestra el estado de tu inversión activa en el Banco Central."
    )
    async def banco_inversion(self, interaction: discord.Interaction):
        await interaction.response.defer()
        user_id = interaction.user.id
        await asyncio.to_thread(ensure_user, user_id, interaction.user.name)

        inv = await BankService.get_active_investment(user_id)
        
        embed = discord.Embed(
            title="🏦 Tu Inversión Activa",
            color=discord.Color.blue(),
            timestamp=discord.utils.utcnow() if hasattr(discord.utils, 'utcnow') else datetime.now()
        )

        if inv:
            monto = inv['Monto']
            inicio = inv['FechaInicio']
            venc = inv['FechaVencimiento']
            
            if venc.tzinfo is not None:
                venc = venc.replace(tzinfo=None)
            
            restante = venc - datetime.now()
            if restante.total_seconds() > 0:
                days = restante.days
                hours, remainder = divmod(restante.seconds, 3600)
                minutes, _ = divmod(remainder, 60)
                
                time_parts = []
                if days > 0:
                    time_parts.append(f"{days} día{'s' if days != 1 else ''}")
                if hours > 0:
                    time_parts.append(f"{hours} hora{'s' if hours != 1 else ''}")
                if minutes > 0:
                    time_parts.append(f"{minutes} minuto{'s' if minutes != 1 else ''}")
                    
                tiempo_restante_str = ", ".join(time_parts) if time_parts else "menos de un minuto"
            else:
                tiempo_restante_str = "Vencida (se resolverá en el próximo ciclo)"

            embed.description = "Tienes una inversión a plazo fijo en curso."
            embed.add_field(
                name="💰 Monto Invertido",
                value=f"`{monto:,}` monedas",
                inline=True
            )
            embed.add_field(
                name="⏱️ Tiempo Restante",
                value=f"`{tiempo_restante_str}`",
                inline=True
            )
            embed.add_field(
                name="📅 Fechas",
                value=(
                    f"**Inicio:** {inicio.strftime('%d/%m/%Y %H:%M')}\n"
                    f"**Vencimiento:** {venc.strftime('%d/%m/%Y %H:%M')}"
                ),
                inline=False
            )
            embed.set_footer(text="Los fondos se acreditarán con un rendimiento variable al vencer.")
        else:
            embed.description = (
                "❌ **No tienes ninguna inversión activa en este momento.**\n\n"
                "💡 Puedes empezar una usando `/banco_invertir <monto>`.\n"
                "Invertirás monedas por 7 días fijos con retorno variable."
            )
            embed.set_footer(text="Riesgo real: pérdida de capital posible.")
            
        await interaction.followup.send(embed=embed)


async def setup(bot):
    await bot.add_cog(BancoCog(bot))
    logger.info("Cog BancoCentral cargado exitosamente.")
