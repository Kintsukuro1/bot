import discord
from discord.ext import commands
from discord import app_commands
import random
import asyncio
from src.db import get_balance, set_balance, deduct_balance, add_balance, ensure_user, usuario_tiene_item, usuario_tiene_mejora, registrar_transaccion, record_game_result
from src.commands.economy.pets import process_post_game_events
from src.utils.dynamic_difficulty import DynamicDifficulty

class Slots(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="slots", description="Juega a las tragamonedas y prueba tu suerte.")
    @app_commands.describe(apuesta="Cantidad a apostar")
    async def slots(self, interaction: discord.Interaction, apuesta: int):
        try:
            user_id = interaction.user.id
            user_name = interaction.user.name
            await asyncio.to_thread(ensure_user, user_id, user_name)
            if apuesta <= 0:
                await interaction.response.send_message("La apuesta debe ser mayor a 0.", ephemeral=True)
                return

            success, saldo_usuario = await asyncio.to_thread(deduct_balance, user_id, apuesta)
            if not success:
                await interaction.response.send_message("No tienes suficiente saldo para esa apuesta.", ephemeral=True)
                return

            # Calcular dificultad dinámica
            difficulty_modifier, difficulty_explanation = await asyncio.to_thread(
                DynamicDifficulty.calculate_dynamic_difficulty, user_id, apuesta, 'slots'
            )

            symbols = ['🍒', '🍋', '🍉', '🍇', '🔔', '🍀', '⭐', '💎']
            
            # 1. Tirar rodillos naturalmente
            result = [random.choice(symbols) for _ in range(3)]
            
            # --- MEJORAS BLACK MARKET ---
            prob_bonus = 0.0
            ganancia_bonus = 1.0
            if await asyncio.to_thread(usuario_tiene_mejora, user_id, 1):  # Suerte Eterna
                prob_bonus += 0.10
            if await asyncio.to_thread(usuario_tiene_mejora, user_id, 3):  # Magnate
                ganancia_bonus += 0.15
            # ---------------------------

            # Evaluar resultado natural
            unique_count = len(set(result))
            
            # 2. El resultado base de slots es 100% aleatorio (sin redraws ocultos)

            # Si el jugador tiene "Suerte Eterna", forzar un par si no se sacó nada
            if unique_count == 3 and prob_bonus > 0 and random.random() < prob_bonus:
                sym = random.choice(symbols)
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
                    from src.db import usar_item_usuario
                    if await asyncio.to_thread(usar_item_usuario, user_id, 5):
                        ticket_multiplier = 2.0
                        ticket_desc = " 🎫 (Ticket x2 aplicado)"
                        
                # Ajuste de dificultad a los multiplicadores
                mult_adjustment = 1.0 - (difficulty_modifier * 0.20)
                mult_adjustment = max(0.70, min(1.30, mult_adjustment))
                winnings = int(apuesta * multiplier * ganancia_bonus * ticket_multiplier * mult_adjustment)
                profit = winnings - apuesta
                
                # add_balance is atomic, returns None, so we re-fetch balance or just calculate
                await asyncio.to_thread(add_balance, user_id, winnings)
                nuevo_saldo = saldo_usuario + winnings # because saldo_usuario is balance after deduction
                
                await asyncio.to_thread(registrar_transaccion, user_id, profit, f"Slots: {payout_desc}{ticket_desc}")
                await asyncio.to_thread(record_game_result, user_id, 'slots', apuesta, 'win', profit, difficulty_modifier, nuevo_saldo)
                try:
                    await process_post_game_events(interaction, user_id, 'slots', apuesta, profit)
                except Exception:
                    pass
                
                title = '🎰 ¡Felicidades! ¡Has ganado!'
                color = discord.Color.green()
                footer = f"{payout_desc}{ticket_desc}"
                desc = f'**[ {result_display} ]**\n\n💰 Apuesta: **{apuesta}** monedas\n🎉 Premio: **{winnings:,}** monedas\n🪙 Nuevo saldo: **{nuevo_saldo:,}** monedas'
            else:
                # Perdió (la apuesta ya fue deducida al inicio)
                nuevo_saldo = saldo_usuario
                await asyncio.to_thread(registrar_transaccion, user_id, -apuesta, "Slots: sin premio")
                await asyncio.to_thread(record_game_result, user_id, 'slots', apuesta, 'loss', 0, difficulty_modifier, nuevo_saldo)
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
            await interaction.response.send_message(embed=embed)
        except Exception as e:
            try:
                await interaction.response.send_message(f"Ocurrió un error: {e}", ephemeral=True)
            except:
                pass
            raise

async def setup(bot):
    await bot.add_cog(Slots(bot))
