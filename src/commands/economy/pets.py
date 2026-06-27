import discord
from discord.ext import commands
from discord import app_commands
import asyncio
import random
import logging

from src.db import db_cursor, add_balance, deduct_balance

logger = logging.getLogger(__name__)

async def process_post_game_events(interaction: discord.Interaction, user_id: int, game_type: str, bet_amount: int, profit: int):
    """
    Función central del Plan Maestro de Pets.
    Se ejecuta al final de cualquier partida de casino.
    Maneja:
    1. Procs de la mascota activa.
    2. Evaluación de lealtad y abandono.
    3. Triggers de encuentros.
    """
    if bet_amount <= 0:
        return

    # Si es Context, envolverlo en un objeto compatible con Interaction
    if not isinstance(interaction, discord.Interaction):
        class ContextWrapper:
            def __init__(self, ctx):
                self.ctx = ctx
                self.client = ctx.bot
                self.channel = ctx.channel
                self.user = ctx.author
        interaction = ContextWrapper(interaction)

    # Evitamos bloquear el event loop con las consultas DB
    await asyncio.to_thread(_process_db_logic, interaction, user_id, game_type, bet_amount, profit)


def _process_db_logic(interaction, user_id, game_type, bet_amount, profit):
    with db_cursor() as cursor:
        is_win = profit > 0
        
        # 1. Obtener Mascota Activa
        cursor.execute("""
            SELECT up.UserPetID, p.PetID, p.Name, p.Emoji, p.EffectType, p.EffectValue, p.EffectChance, p.EffectCap, p.FavoriteGame, up.Loyalty
            FROM UserPets up
            JOIN PetsCatalog p ON up.PetID = p.PetID
            WHERE up.UserID = %s AND up.IsActive = 1
        """, (user_id,))
        active_pet = cursor.fetchone()
        
        proc_amount = 0
        pet_escaped = False
        
        if active_pet:
            up_id, pet_id, p_name, p_emoji, effect_type, eff_val, eff_chance, eff_cap, fav_game, loyalty = active_pet
            
            # 2. Evaluar Proc
            proc_trigger = False
            
            if effect_type == "multiplier" and is_win:
                proc_trigger = True
                raw_proc = int(profit * (eff_val - 1.0)) # Ej: 1.10 -> 0.10
            elif effect_type == "refund" and not is_win:
                proc_trigger = True
                raw_proc = int(bet_amount * eff_val)
            elif effect_type == "proc_universal":
                proc_trigger = random.random() < eff_chance
                raw_proc = int(bet_amount * eff_val)
            elif effect_type == "proc_derrota" and not is_win:
                proc_trigger = random.random() < eff_chance
                raw_proc = int(bet_amount * eff_val)
            elif effect_type == "proc_derrota_y_revive" and not is_win:
                proc_trigger = random.random() < eff_chance
                raw_proc = int(bet_amount * eff_val)
            elif effect_type == "proc_juego" and game_type == fav_game:
                proc_trigger = random.random() < eff_chance
                raw_proc = int(bet_amount * eff_val)
            elif effect_type == "proc_juego_y_mult" and game_type == fav_game:
                proc_trigger = random.random() < eff_chance
                raw_proc = int(bet_amount * eff_val)
            elif effect_type == "proc_high_roller" and get_user_balance(cursor, user_id) > 0 and (bet_amount / get_user_balance(cursor, user_id)) >= 0.10:
                proc_trigger = random.random() < eff_chance
                raw_proc = int(bet_amount * eff_val)
            
            if proc_trigger:
                proc_amount = min(raw_proc, eff_cap) if eff_cap > 0 else raw_proc
                if proc_amount > 0:
                    add_balance(user_id, proc_amount)
                    # Notificamos el proc
                    asyncio.run_coroutine_threadsafe(
                        send_proc_message(interaction, p_emoji, p_name, proc_amount, effect_type),
                        interaction.client.loop
                    )
            
            # 3. Lealtad y Abandono
            new_loyalty = loyalty + 1 if is_win else loyalty - 2
            new_loyalty = max(0, min(100, new_loyalty))
            
            cursor.execute("UPDATE UserPets SET Loyalty = %s, GamesWithOwner = GamesWithOwner + 1, WinsWithOwner = WinsWithOwner + %s, LossesWithOwner = LossesWithOwner + %s WHERE UserPetID = %s",
                           (new_loyalty, 1 if is_win else 0, 0 if is_win else 1, up_id))
            
            if new_loyalty <= 0:
                # Abandono
                if effect_type == "proc_derrota_y_revive":
                    # Fénix revive una vez
                    cursor.execute("UPDATE UserPets SET Loyalty = 50 WHERE UserPetID = %s", (up_id,))
                    asyncio.run_coroutine_threadsafe(
                        send_revive_message(interaction, p_emoji, p_name),
                        interaction.client.loop
                    )
                else:
                    cursor.execute("UPDATE UserPets SET IsActive = 0, Status = 'Escapó' WHERE UserPetID = %s", (up_id,))
                    pet_escaped = True
                    asyncio.run_coroutine_threadsafe(
                        send_escape_message(interaction, p_emoji, p_name),
                        interaction.client.loop
                    )

        # 4. Triggers de Encuentro
        # Obtenemos stats del usuario
        cursor.execute("SELECT GamblerLevel, TotalBetVolume FROM GamblerProgress WHERE UserID = %s", (user_id,))
        gp = cursor.fetchone()
        g_level = gp[0] if gp else 1
        
        cursor.execute("SELECT HotStreak, ColdStreak FROM UserGameStats WHERE UserID = %s", (user_id,))
        stats = cursor.fetchone()
        hot_streak = stats[0] if stats else 0
        cold_streak = stats[1] if stats else 0
        
        # Evaluamos si hay encuentro
        encounter = evaluate_encounters(cursor, user_id, g_level, hot_streak, cold_streak, bet_amount, game_type)
        if encounter:
            pet_data = get_random_pet_by_encounter(cursor, encounter['type'], g_level)
            if pet_data:
                # Disparar UI de captura
                asyncio.run_coroutine_threadsafe(
                    send_encounter_ui(interaction, user_id, pet_data),
                    interaction.client.loop
                )

def get_user_balance(cursor, user_id):
    cursor.execute("SELECT Balance FROM Users WHERE UserID = %s", (user_id,))
    row = cursor.fetchone()
    return row[0] if row else 0

def evaluate_encounters(cursor, user_id, level, hot_streak, cold_streak, bet_amount, game_type):
    """Devuelve un dict con el tipo de encuentro si se activa."""
    # Tabla base de chances de V1
    chances = {
        "hot_streak": {3: 0.18, 5: 0.28, 8: 0.42, 12: 0.60},
        "cold_streak": {4: 0.16, 6: 0.26, 8: 0.38}
    }
    
    if hot_streak in chances["hot_streak"]:
        if random.random() < chances["hot_streak"][hot_streak]:
            return {"type": "hot_streak"}
            
    if cold_streak in chances["cold_streak"]:
        if random.random() < chances["cold_streak"][cold_streak]:
            return {"type": "cold_streak"}
            
    # Volume/Especialización simplificado para V1
    if random.random() < 0.05: # 5% flat chance en cada jugada de sacar pet de volumen o especialización
        return {"type": random.choice(["volume", "specialized", "wealth"])}
        
    return None

def get_random_pet_by_encounter(cursor, encounter_type, level):
    # Determinar Rareza según Nivel (Simplificado)
    r = random.random()
    if level < 10:
        rarity = "Normal" if r < 0.85 else "Rara"
    elif level < 25:
        if r < 0.65: rarity = "Normal"
        elif r < 0.90: rarity = "Rara"
        else: rarity = "Épica"
    elif level < 40:
        if r < 0.45: rarity = "Normal"
        elif r < 0.75: rarity = "Rara"
        elif r < 0.90: rarity = "Épica"
        else: rarity = "Legendaria"
    else:
        if r < 0.30: rarity = "Normal"
        elif r < 0.60: rarity = "Rara"
        elif r < 0.80: rarity = "Épica"
        elif r < 0.95: rarity = "Legendaria"
        else: rarity = "Mítica"

    cursor.execute("""
        SELECT PetID, Name, Emoji, Rarity, CaptureType, CaptureConfig, FlavorText
        FROM PetsCatalog 
        WHERE EncounterType = %s AND Rarity = %s AND Enabled = 1
        ORDER BY RANDOM() LIMIT 1
    """, (encounter_type, rarity))
    row = cursor.fetchone()
    
    # Fallback si no hay pet exacta de ese tipo/rareza, buscar cualquier pet de esa rareza
    if not row:
        cursor.execute("""
            SELECT PetID, Name, Emoji, Rarity, CaptureType, CaptureConfig, FlavorText
            FROM PetsCatalog 
            WHERE Rarity = %s AND Enabled = 1
            ORDER BY RANDOM() LIMIT 1
        """, (rarity,))
        row = cursor.fetchone()
        
    if row:
        return {
            "id": row[0], "name": row[1], "emoji": row[2], "rarity": row[3],
            "cap_type": row[4], "cap_cost": row[5], "flavor": row[6]
        }
    return None

# --- Funciones de Interfaz (Discord) ---

async def send_proc_message(interaction, emoji, name, amount, effect_type):
    try:
        if effect_type == "multiplier":
            await interaction.channel.send(f"🐾 *¡Tu {emoji} **{name}** aumentó tus ganancias en **{amount:,}** monedas!*")
        elif effect_type == "refund":
            await interaction.channel.send(f"🐾 *¡Tu {emoji} **{name}** recuperó **{amount:,}** monedas de tus pérdidas!*")
        else:
            await interaction.channel.send(f"🐾 *¡Tu {emoji} **{name}** encontró **{amount:,}** monedas extra!*")
    except Exception as e:
        logger.warning(f"No se pudo enviar mensaje de proc de mascota: {e}")

async def send_escape_message(interaction, emoji, name):
    try:
        await interaction.channel.send(f"💔 *Tu {emoji} **{name}** te mira con decepción tras tus fracasos... y te abandona.*")
    except Exception as e:
        logger.warning(f"No se pudo enviar mensaje de escape de mascota: {e}")

async def send_revive_message(interaction, emoji, name):
    try:
        await interaction.channel.send(f"🔥 *Tu {emoji} **{name}** arde en cenizas y resurge, negándose a abandonarte.*")
    except Exception as e:
        logger.warning(f"No se pudo enviar mensaje de resurrección de mascota: {e}")

async def send_encounter_ui(interaction, user_id, pet_data):
    try:
        embed = discord.Embed(
            title="✨ ¡Un encuentro misterioso!",
            description=f"Una criatura salvaje te observa en la distancia.\n\n{pet_data['emoji']} **{pet_data['name']}**\n🌟 Rareza: **{pet_data['rarity']}**\n\n_{pet_data['flavor']}_",
            color=discord.Color.gold()
        )
        
        view = CaptureView(user_id, pet_data)
        
        if pet_data['cap_type'] == "pay":
            embed.add_field(name="Requisito", value=f"Pide **{pet_data['cap_cost']:,}** monedas como ofrenda.")
        elif pet_data['cap_type'] == "auto":
            embed.add_field(name="Requisito", value="Se ve muy amigable. No pide nada.")
        else:
            embed.add_field(name="Requisito", value="Requiere que demuestres tu valor (Condición especial).")
            
        await interaction.channel.send(content=f"<@{user_id}>", embed=embed, view=view)
    except Exception as e:
        logger.warning(f"No se pudo enviar interfaz de encuentro de mascota: {e}")

class CaptureView(discord.ui.View):
    def __init__(self, user_id, pet_data):
        super().__init__(timeout=60)
        self.user_id = user_id
        self.pet_data = pet_data

    @discord.ui.button(label="Capturar", style=discord.ButtonStyle.success, emoji="🐾")
    async def btn_capture(self, inter: discord.Interaction, button: discord.ui.Button):
        if inter.user.id != self.user_id:
            await inter.response.send_message("¡Esta criatura no te está mirando a ti!", ephemeral=True)
            return
            
        # Evaluar costo
        success = False
        if self.pet_data['cap_type'] == "pay" or self.pet_data['cap_type'] == "pay_and_survive":
            cost = self.pet_data['cap_cost']
            from src.db import deduct_balance
            has_money = await asyncio.to_thread(deduct_balance, self.user_id, cost)
            if has_money[0]:
                success = True
            else:
                await inter.response.send_message(f"❌ No tienes las {cost:,} monedas que exige esta criatura.", ephemeral=True)
                return
        else:
            success = True # Auto o especial simplificado
            
        if success:
            # Guardar en DB
            from src.db import db_cursor
            def _save_pet():
                with db_cursor() as c:
                    c.execute("INSERT INTO UserPets (UserID, PetID) VALUES (%s, %s)", (self.user_id, self.pet_data['id']))
            await asyncio.to_thread(_save_pet)
            
            # Deshabilitar botones
            for child in self.children:
                child.disabled = True
            
            embed = inter.message.embeds[0]
            embed.color = discord.Color.green()
            embed.title = "🎉 ¡Captura Exitosa!"
            embed.description = f"¡Has atrapado a {self.pet_data['emoji']} **{self.pet_data['name']}**!\nUsa `/pets` para ver tu colección."
            embed.clear_fields()
            
            await inter.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="Dejar ir", style=discord.ButtonStyle.danger)
    async def btn_leave(self, inter: discord.Interaction, button: discord.ui.Button):
        if inter.user.id != self.user_id:
            return
        
        for child in self.children:
            child.disabled = True
            
        embed = inter.message.embeds[0]
        embed.color = discord.Color.dark_grey()
        embed.title = "💨 Se ha marchado"
        embed.description = "Decidiste dejar ir a la criatura. Rápidamente desaparece entre las sombras."
        embed.clear_fields()
        
        await inter.response.edit_message(embed=embed, view=self)

# Cogs de Comandos
class PetsMasterCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="pets", description="Muestra tu colección de mascotas.")
    async def pets_cmd(self, interaction: discord.Interaction):
        await interaction.response.defer()
        user_id = interaction.user.id
        
        def _get_pets():
            with db_cursor() as c:
                c.execute("""
                    SELECT up.UserPetID, p.Name, p.Emoji, p.Rarity, up.IsActive, up.Loyalty
                    FROM UserPets up JOIN PetsCatalog p ON up.PetID = p.PetID
                    WHERE up.UserID = %s AND up.Status != 'Escapó'
                    ORDER BY up.IsActive DESC, p.Rarity DESC
                """, (user_id,))
                return c.fetchall()
                
        pets = await asyncio.to_thread(_get_pets)
        
        if not pets:
            await interaction.followup.send("No tienes ninguna mascota en tu colección. ¡Juega en el casino para encontrar una!", ephemeral=True)
            return
            
        embed = discord.Embed(title=f"🐾 Colección de {interaction.user.display_name}", color=discord.Color.blurple())
        
        for up_id, p_name, p_emoji, p_rarity, is_active, loyalty in pets:
            status = "🟢 Activa" if is_active == 1 else "⚪ Guardada"
            embed.add_field(
                name=f"{p_emoji} {p_name} ({p_rarity})",
                value=f"Estado: {status}\nLealtad: {loyalty}/100\nID: `{up_id}`",
                inline=False
            )
            
        await interaction.followup.send(embed=embed)

    @app_commands.command(name="pet_equipar", description="Equipa una mascota de tu colección usando su ID.")
    async def pet_equipar_cmd(self, interaction: discord.Interaction, pet_id: int):
        await interaction.response.defer(ephemeral=True)
        user_id = interaction.user.id
        
        def _equip():
            with db_cursor() as c:
                c.execute("SELECT UserPetID FROM UserPets WHERE UserPetID = %s AND UserID = %s AND Status != 'Escapó'", (pet_id, user_id))
                if not c.fetchone():
                    return False
                c.execute("UPDATE UserPets SET IsActive = 0 WHERE UserID = %s", (user_id,))
                c.execute("UPDATE UserPets SET IsActive = 1 WHERE UserPetID = %s", (pet_id,))
                return True
                
        success = await asyncio.to_thread(_equip)
        if success:
            await interaction.followup.send(f"✅ Has equipado la mascota ID `{pet_id}` exitosamente.", ephemeral=True)
        else:
            await interaction.followup.send("❌ No se encontró esa mascota en tu colección.", ephemeral=True)

    @app_commands.command(name="apostador", description="Muestra tu progreso y Nivel de Apostador.")
    async def apostador_cmd(self, interaction: discord.Interaction):
        await interaction.response.defer()
        user_id = interaction.user.id
        
        def _get_level():
            with db_cursor() as c:
                c.execute("SELECT GamblerLevel, GamblerXP FROM GamblerProgress WHERE UserID = %s", (user_id,))
                return c.fetchone()
                
        prog = await asyncio.to_thread(_get_level)
        level = prog[0] if prog else 1
        xp = prog[1] if prog else 0
        req_xp = 40 + (level - 1) * 15
        
        embed = discord.Embed(title=f"🎲 Perfil de Apostador de {interaction.user.display_name}", color=discord.Color.purple())
        embed.add_field(name="Nivel", value=f"**{level}** / 50")
        embed.add_field(name="Experiencia", value=f"{xp} / {req_xp} XP")
        
        await interaction.followup.send(embed=embed)

async def setup(bot):
    await bot.add_cog(PetsMasterCog(bot))
