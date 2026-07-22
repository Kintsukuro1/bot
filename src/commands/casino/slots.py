import discord
from discord.ext import commands
from discord import app_commands
import random
import asyncio
from src.db import ensure_user, usuario_tiene_item, usuario_tiene_mejora
from src.services.casino_service import CasinoService
from src.commands.economy.pets import process_post_game_events
from src.utils.dynamic_difficulty import DynamicDifficulty
from src.utils.cooldowns import CASINO_COOLDOWN

class Slots(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def slots(self, interaction: discord.Interaction, apuesta: int):

        try:
            await interaction.response.defer()
            user_id = interaction.user.id
            user_name = interaction.user.name

            can_play, lockout_msg = await CasinoService.check_casino_lockout(user_id)
            if not can_play:
                await interaction.followup.send(lockout_msg, ephemeral=True)
                return

            await asyncio.to_thread(ensure_user, user_id, user_name)
            if apuesta <= 0:
                await interaction.followup.send("La apuesta debe ser mayor a 0.", ephemeral=True)
                return

            success, saldo_usuario = await CasinoService.place_bet(user_id, apuesta, 'slots')
            if not success:
                await interaction.followup.send("No tienes suficiente saldo para esa apuesta.", ephemeral=True)
                return

            # Calcular dificultad dinámica
            difficulty_modifier, difficulty_explanation = await asyncio.to_thread(
                DynamicDifficulty.calculate_dynamic_difficulty, user_id, apuesta, 'slots'
            )

            SYMBOL_WEIGHTS = {
                '🍒': 100, '🍋': 70, '🍉': 45, '🍇': 35,
                '🔔': 22, '🍀': 14, '⭐': 6, '💎': 3,
            }
            symbols = list(SYMBOL_WEIGHTS.keys())
            weights = list(SYMBOL_WEIGHTS.values())
            
            # 1. Tirar rodillos naturalmente con pesos ponderados
            result = random.choices(symbols, weights=weights, k=3)
            
            # --- MEJORAS BLACK MARKET ---
            prob_bonus = 0.0
            ganancia_bonus = 1.0
            if await asyncio.to_thread(usuario_tiene_mejora, user_id, 1):  # Suerte Eterna
                prob_bonus += 0.10
            if await asyncio.to_thread(usuario_tiene_mejora, user_id, 3):  # Magnate
                ganancia_bonus += 0.15
            if await asyncio.to_thread(usuario_tiene_mejora, user_id, 10):  # Corona
                ganancia_bonus += 0.05
            # ---------------------------

            # Evaluar resultado natural
            unique_count = len(set(result))
            
            # 2. El resultado base de slots es 100% aleatorio (sin redraws ocultos)

            # Si el jugador tiene "Suerte Eterna", forzar un par si no se sacó nada
            if unique_count == 3 and prob_bonus > 0 and random.random() < prob_bonus:
                sym = random.choices(symbols, weights=weights, k=1)[0]
                result = [sym, sym, random.choice([s for s in symbols if s != sym])]
                unique_count = len(set(result))

            result_display = ' | '.join(result)

            # 3. Determinar premio y multiplicador
            multiplier = 0.0
            payout_desc = ""
            
            if unique_count == 1:
                jackpot_symbol = result[0]
                if jackpot_symbol == '🍒':
                    multiplier = 5.0
                elif jackpot_symbol == '🍋':
                    multiplier = 7.0
                elif jackpot_symbol == '🍉':
                    multiplier = 10.0
                elif jackpot_symbol == '🍇':
                    multiplier = 12.0
                elif jackpot_symbol == '🔔':
                    multiplier = 15.0
                elif jackpot_symbol == '🍀':
                    multiplier = 20.0
                elif jackpot_symbol == '⭐':
                    multiplier = 35.0
                elif jackpot_symbol == '💎':
                    multiplier = 50.0
                payout_desc = f"🏆 **¡JACKPOT de {jackpot_symbol}!** x{multiplier:.1f}"
                
            elif unique_count == 2:
                dup_symbol = max(set(result), key=result.count)
                if dup_symbol in ['🍒', '🍋', '🍉', '🍇']:
                    multiplier = 1.2
                else:
                    multiplier = 1.8
                payout_desc = f"✨ **Par de {dup_symbol}!** x{multiplier:.1f}"
            else:
                payout_desc = "❌ Sin combinaciones"

            # Calcular ganancia neta
            if multiplier > 0:
                ticket_multiplier = 1.0
                ticket_desc = ""
                if await asyncio.to_thread(usuario_tiene_item, user_id, 5):  # Ticket Slots
                    from src.db import usar_item_usuario, check_and_register_shield_use
                    status, time_remaining = await asyncio.to_thread(check_and_register_shield_use, user_id)
                    if status == 'ok' or status == 'blocked_start':
                        if await asyncio.to_thread(usar_item_usuario, user_id, 5):
                            ticket_multiplier = 2.0
                            ticket_desc = " 🎫 (Ticket x2 aplicado)"
                            if status == 'blocked_start':
                                ticket_desc += "\n⏱️ **Has alcanzado el límite de 3 escudos diarios.** Cooldown de 24h iniciado."
                    elif status == 'blocked' and time_remaining is not None:
                        hours = time_remaining // 3600
                        minutes = (time_remaining % 3600) // 60
                        ticket_desc = f"\n⚠️ **No se pudo usar tu Ticket de Slots.** Bloqueado por cooldown de escudos ({hours}h {minutes:02d}m restantes)."
                    elif status == 'error':
                        ticket_desc = "\n⚠️ **No se pudo usar tu Ticket de Slots debido a un error de base de datos.**"
                        
                # Ajuste de dificultad a los multiplicadores
                mult_adjustment = 1.0 - (difficulty_modifier * 0.20)
                mult_adjustment = max(0.70, min(1.30, mult_adjustment))
                winnings = int(apuesta * multiplier * ganancia_bonus * ticket_multiplier * mult_adjustment)
                if ticket_multiplier > 1.0:
                    winnings = int(winnings * 0.65)
                    ticket_desc += "\n⚠️ **Debuff de 35% menos de dinero aplicado por protección activa.**"
                profit = winnings - apuesta

                winnings_total = winnings
                nuevo_saldo, impuesto = await CasinoService.settle_win(
                    user_id,
                    apuesta,
                    winnings_total,
                    'slots',
                    difficulty_modifier,
                    saldo_usuario
                )
                lockout_activated = await CasinoService.check_and_apply_winstreak_lockout(user_id, nuevo_saldo)
                try:
                    await process_post_game_events(interaction, user_id, 'slots', apuesta, profit)
                except Exception:
                    pass
                
                title = '🎰 ¡Felicidades! ¡Has ganado!'
                color = discord.Color.green()
                footer = f"{payout_desc}{ticket_desc}"
                desc = (
                    f'**[ {result_display} ]**\n\n'
                    f'💰 Apuesta: **{apuesta}** monedas\n'
                    f'🎉 Premio Bruto: **{winnings:,}** monedas\n'
                    f'💸 Impuesto Casino (3%): **{impuesto:,}** monedas (destruido)\n'
                    f'✨ Premio Neto: **{winnings - impuesto:,}** monedas\n'
                    f'🪙 Nuevo saldo: **{nuevo_saldo:,}** monedas'
                )
                if lockout_activated:
                    desc += "\n\n⚠️ **🎰 Has ganado mucho muy rápido — tómate un descanso de 25 minutos antes de seguir jugando.**"
            else:
                nuevo_saldo = await CasinoService.settle_loss(
                    user_id,
                    apuesta,
                    'slots',
                    difficulty_modifier,
                    saldo_usuario
                )
                try:
                    await process_post_game_events(interaction, user_id, 'slots', apuesta, 0)
                except Exception:
                    pass
                
                title = '🎰 Lo siento, has perdido.'
                color = discord.Color.red()
                footer = 'Inténtalo de nuevo.'
                desc = f'**[ {result_display} ]**\n\n💰 Apuesta: **{apuesta}** monedas\n🪙 Nuevo saldo: **{nuevo_saldo:,}** monedas'

            embed = discord.Embed(
                title=title,
                description=desc,
                color=color
            )
            embed.set_footer(text=footer)
            await interaction.followup.send(embed=embed)
        except Exception as e:
            try:
                await interaction.followup.send(f"Ocurrió un error: {e}", ephemeral=True)
            except Exception:
                pass
            raise

async def setup(bot):
    await bot.add_cog(Slots(bot))
