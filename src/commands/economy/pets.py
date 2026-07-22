import discord
from discord.ext import commands
from discord import app_commands
import asyncio
import random
import math
import logging
from typing import Optional

from src.db import db_cursor, add_balance, deduct_balance, rename_user_pet, get_fusionable_pets, fuse_pets, get_user_items, usar_item_usuario

logger = logging.getLogger(__name__)

SLOTS_PERMITIDOS = ["casino", "robar", "raid"]

REEMBOLSO_RAREZA = {
    "Normal": 5000,
    "Rara": 25000,
    "Épica": 120000,
    "Legendaria": 600000,
    "Mítica": 2500000
}

def display_pet_name(catalog_name, nickname=None):
    if nickname and str(nickname).strip():
        return str(nickname).strip()
    return catalog_name

def get_xp_for_level(level: int) -> int:
    return level * 200

def _describe_effect(effect_type, effect_value, effect_chance, effect_cap, favorite_game):
    pct_chance = int((effect_chance or 0) * 100) if effect_chance else None
    cap_text = f" (máx {effect_cap:,})" if effect_cap and effect_cap > 0 else ""
    
    descriptions = {
        "multiplier": f"Multiplica las ganancias x{effect_value:.2f} en victorias{cap_text}",
        "refund": f"Recupera el {int((effect_value or 0) * 100)}% de la apuesta al perder{cap_text}",
        "proc_universal": f"{pct_chance}% de prob. de hallar bonus extra de monedas{cap_text}",
        "proc_derrota": f"{pct_chance}% de recuperar parte de la apuesta al perder{cap_text}",
        "proc_derrota_y_revive": f"{pct_chance}% de recuperar apuesta al perder + resurge si llega a 0 lealtad{cap_text}",
        "proc_juego": f"{pct_chance}% de bonus multiplicador en **{favorite_game or 'juego preferido'}**{cap_text}",
        "proc_juego_y_mult": f"{pct_chance}% de bonus x{effect_value:.1f} en **{favorite_game or 'slots'}**{cap_text}",
        "proc_high_roller": f"{pct_chance}% de bonus en apuestas de alto riesgo (≥10% de saldo){cap_text}",
        "multiplier_safe": f"Multiplicador seguro x{effect_value:.2f} y protección contra pérdidas{cap_text}",
        "multiplier_scaling": f"Multiplicador escalable por racha de victorias consecutivas{cap_text}",
    }
    return descriptions.get(effect_type, "Habilidad pasiva de beneficio económico/combate.")

async def process_post_game_events(interaction: discord.Interaction, user_id: int, game_type: str, bet_amount: int, profit: int):
    if bet_amount <= 0:
        return

    if not isinstance(interaction, discord.Interaction):
        class ContextWrapper:
            def __init__(self, ctx):
                self.ctx = ctx
                self.client = ctx.bot
                self.channel = ctx.channel
                self.user = ctx.author
        interaction = ContextWrapper(interaction)

    await asyncio.to_thread(_process_db_logic, interaction, user_id, game_type, bet_amount, profit)

def _process_db_logic(interaction, user_id, game_type, bet_amount, profit):
    with db_cursor() as cursor:
        is_win = profit > 0
        
        cursor.execute("""
            SELECT up.UserPetID, p.PetID, p.Name, p.Emoji, p.EffectType, p.EffectValue, p.EffectChance, p.EffectCap, p.FavoriteGame, up.Loyalty, up.Nickname, up.Level, up.XP
            FROM UserPets up
            JOIN PetsCatalog p ON up.PetID = p.PetID
            WHERE up.UserID = %s AND (up.EquippedSlot = 'casino' OR (up.IsActive = 1 AND up.EquippedSlot IS NULL))
            LIMIT 1
        """, (user_id,))
        active_pet = cursor.fetchone()
        
        proc_amount = 0
        
        if active_pet:
            up_id, pet_id, p_name, p_emoji, effect_type, eff_val, eff_chance, eff_cap, fav_game, loyalty, nickname, p_level, p_xp = active_pet
            p_display_name = display_pet_name(p_name, nickname)
            
            level_mult = 1.0 + ((p_level - 1) * 0.05) if p_level else 1.0
            eff_val = (eff_val or 1.0) * level_mult
            
            proc_trigger = False
            
            if effect_type == "multiplier" and is_win:
                proc_trigger = True
                raw_proc = int(profit * (eff_val - 1.0))
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
                    asyncio.run_coroutine_threadsafe(
                        send_proc_message(interaction, p_emoji, p_display_name, proc_amount, effect_type),
                        interaction.client.loop
                    )
            
            new_xp = (p_xp or 0) + 15
            new_level = p_level or 1
            xp_needed = get_xp_for_level(new_level)
            if new_xp >= xp_needed and new_level < 15:
                new_level += 1
                new_xp -= xp_needed
            
            new_loyalty = loyalty + 1 if is_win else loyalty - 2
            new_loyalty = max(0, min(100, new_loyalty))
            
            cursor.execute("""
                UPDATE UserPets
                SET Loyalty = %s, Level = %s, XP = %s, GamesWithOwner = GamesWithOwner + 1, WinsWithOwner = WinsWithOwner + %s, LossesWithOwner = LossesWithOwner + %s
                WHERE UserPetID = %s
            """, (new_loyalty, new_level, new_xp, 1 if is_win else 0, 0 if is_win else 1, up_id))
            
            if new_loyalty <= 0:
                if effect_type == "proc_derrota_y_revive":
                    cursor.execute("UPDATE UserPets SET Loyalty = 50 WHERE UserPetID = %s", (up_id,))
                    asyncio.run_coroutine_threadsafe(
                        send_revive_message(interaction, p_emoji, p_display_name),
                        interaction.client.loop
                    )
                else:
                    cursor.execute("DELETE FROM UserPets WHERE UserPetID = %s", (up_id,))
                    asyncio.run_coroutine_threadsafe(
                        send_escape_message(interaction, p_emoji, p_display_name),
                        interaction.client.loop
                    )

        cursor.execute("SELECT GamblerLevel, TotalBetVolume FROM GamblerProgress WHERE UserID = %s", (user_id,))
        gp = cursor.fetchone()
        g_level = gp[0] if gp else 1
        
        cursor.execute("SELECT HotStreak, ColdStreak FROM UserGameStats WHERE UserID = %s", (user_id,))
        stats = cursor.fetchone()
        hot_streak = stats[0] if stats else 0
        cold_streak = stats[1] if stats else 0
        
        encounter = evaluate_encounters(cursor, user_id, g_level, hot_streak, cold_streak, bet_amount, game_type)
        if encounter:
            pet_data = get_random_pet_by_encounter(cursor, encounter['type'], g_level)
            if pet_data:
                asyncio.run_coroutine_threadsafe(
                    send_encounter_ui(interaction, user_id, pet_data),
                    interaction.client.loop
                )

def get_user_balance(cursor, user_id):
    cursor.execute("SELECT Balance FROM Users WHERE UserID = %s", (user_id,))
    row = cursor.fetchone()
    return row[0] if row else 0

def evaluate_encounters(cursor, user_id, level, hot_streak, cold_streak, bet_amount, game_type):
    cursor.execute("""
        SELECT FailedEncounters, LastEncounterAt
        FROM UserPetEncounterState
        WHERE UserID = %s AND EncounterType = '_global_cooldown'
    """, (user_id,))
    cd_row = cursor.fetchone()
    
    if cd_row:
        games_since = cd_row[0]
        if games_since < 15:
            cursor.execute("""
                UPDATE UserPetEncounterState
                SET FailedEncounters = FailedEncounters + 1
                WHERE UserID = %s AND EncounterType = '_global_cooldown'
            """, (user_id,))
            return None
    
    chances = {
        "hot_streak": {5: 0.08, 8: 0.15, 12: 0.25},
        "cold_streak": {5: 0.08, 8: 0.15, 12: 0.22}
    }
    
    encounter = None
    if hot_streak in chances["hot_streak"]:
        if random.random() < chances["hot_streak"][hot_streak]:
            encounter = {"type": "hot_streak"}
            
    if not encounter and cold_streak in chances["cold_streak"]:
        if random.random() < chances["cold_streak"][cold_streak]:
            encounter = {"type": "cold_streak"}
            
    if not encounter and random.random() < 0.015:
        encounter = {"type": random.choice(["volume", "specialized", "wealth"])}
    
    if encounter:
        cursor.execute("""
            INSERT INTO UserPetEncounterState (UserID, EncounterType, FailedEncounters, LastEncounterAt)
            VALUES (%s, '_global_cooldown', 0, CURRENT_TIMESTAMP)
            ON CONFLICT (UserID, EncounterType) DO UPDATE
            SET FailedEncounters = 0, LastEncounterAt = CURRENT_TIMESTAMP
        """, (user_id,))
        return encounter
    else:
        cursor.execute("""
            INSERT INTO UserPetEncounterState (UserID, EncounterType, FailedEncounters, LastEncounterAt)
            VALUES (%s, '_global_cooldown', 1, NULL)
            ON CONFLICT (UserID, EncounterType) DO UPDATE
            SET FailedEncounters = UserPetEncounterState.FailedEncounters + 1
        """, (user_id,))
        return None

def get_random_pet_by_encounter(cursor, encounter_type, level):
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

async def send_proc_message(interaction, emoji, name, amount, effect_type):
    try:
        await interaction.channel.send(f"🐾 *¡Tu {emoji} **{name}** activó su habilidad y te otorgó **{amount:,}** monedas!*")
    except Exception as e:
        logger.warning(f"Error mensaje proc: {e}")

async def send_escape_message(interaction, emoji, name):
    try:
        await interaction.channel.send(f"💔 *Tu {emoji} **{name}** te mira con decepción tras tus fracasos y se marchó permanentemente.*")
    except Exception as e:
        logger.warning(f"Error mensaje escape: {e}")

async def send_revive_message(interaction, emoji, name):
    try:
        await interaction.channel.send(f"🔥 *Tu {emoji} **{name}** arde en cenizas y resurge, negándose a abandonarte.*")
    except Exception as e:
        logger.warning(f"Error mensaje revive: {e}")

async def send_encounter_ui(interaction, user_id, pet_data):
    try:
        embed = discord.Embed(
            title="✨ ¡Un encuentro misterioso!",
            description=f"Una criatura salvaje te observa en la distancia.\n\n{pet_data['emoji']} **{pet_data['name']}**\n🌟 Rareza: **{pet_data['rarity']}**\n\n_{pet_data['flavor']}_",
            color=discord.Color.gold()
        )
        view = CaptureView(user_id, pet_data)
        await interaction.channel.send(content=f"<@{user_id}>", embed=embed, view=view)
    except Exception as e:
        logger.warning(f"Error enviar encounter UI: {e}")

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
            
        success = False
        if self.pet_data['cap_type'] in ["pay", "pay_and_survive"]:
            cost = self.pet_data['cap_cost']
            has_money = await asyncio.to_thread(deduct_balance, self.user_id, cost)
            if has_money[0]:
                success = True
            else:
                await inter.response.send_message(f"❌ No tienes las {cost:,} monedas que exige esta criatura.", ephemeral=True)
                return
        else:
            success = True
            
        if success:
            def _save_pet():
                with db_cursor() as c:
                    c.execute("INSERT INTO UserPets (UserID, PetID, Level, XP, Loyalty) VALUES (%s, %s, 1, 0, 100)", (self.user_id, self.pet_data['id']))
            await asyncio.to_thread(_save_pet)
            
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
        embed.description = "Decidiste dejar ir a la criatura."
        embed.clear_fields()
        await inter.response.edit_message(embed=embed, view=self)

def _format_loyalty_bar(loyalty, size=10):
    filled = min(size, int((loyalty / 100) * size))
    return "█" * filled + "░" * (size - filled)

def _get_mood_from_loyalty(loyalty):
    if loyalty >= 75: return "😊", "Feliz"
    elif loyalty >= 50: return "🙂", "Contenta"
    elif loyalty >= 25: return "😐", "Neutral"
    else: return "😢", "Triste"

# --- VISTA PAGINADA DEL CATÁLOGO DE MASCOTAS ---

class PetsCatalogPaginatorView(discord.ui.View):
    """Vista interactiva con botones Anterior (◀️) y Siguiente (▶️) para explorar las mascotas (5 por página)."""
    def __init__(self, all_pets: list[dict], user_id: int):
        super().__init__(timeout=180)
        self.all_pets = all_pets
        self.user_id = user_id
        self.current_page = 0
        self.page_size = 5
        self.total_pages = max(1, math.ceil(len(all_pets) / self.page_size))
        self._update_buttons()

    def _build_embed(self) -> discord.Embed:
        embed = discord.Embed(
            title=f"📖 Catálogo de Mascotas (Página {self.current_page + 1}/{self.total_pages})",
            description=f"Explora las **{len(self.all_pets)}** mascotas disponibles. Cada lista muestra 5 mascotas con sus efectos.",
            color=discord.Color.gold()
        )
        embed.set_thumbnail(url="https://cdn-icons-png.flaticon.com/512/3062/3062634.png")

        start = self.current_page * self.page_size
        end = start + self.page_size
        page_items = self.all_pets[start:end]

        rarity_colors = {
            "Normal": "⚪", "Rara": "🔵", "Épica": "🟣", "Legendaria": "🟡", "Mítica": "🔴"
        }

        for pet in page_items:
            r_badge = rarity_colors.get(pet['rarity'], '🌟')
            name_header = f"{pet['emoji']} {pet['name']} — {r_badge} **{pet['rarity']}**"
            
            effect_desc = _describe_effect(pet['effect_type'], pet['effect_value'], pet['effect_chance'], pet['effect_cap'], pet['favorite_game'])
            
            value_str = (
                f"👪 **Familia:** {pet['family'] or 'N/A'} | 🎭 **Temperamento:** {pet['temperament'] or 'N/A'}\n"
                f"✨ **Lo que hace:** {effect_desc}\n"
                f"📜 *{pet['flavor'] or 'Sin descripción disponible.'}*"
            )
            embed.add_field(name=name_header, value=value_str, inline=False)

        embed.set_footer(text=f"Página {self.current_page + 1} de {self.total_pages} · Usa ◀️ y ▶️ para navegar")
        return embed

    def _update_buttons(self):
        self.btn_prev.disabled = (self.current_page == 0)
        self.btn_next.disabled = (self.current_page >= self.total_pages - 1)
        self.btn_page.label = f"Página {self.current_page + 1}/{self.total_pages}"

    @discord.ui.button(label="◀️ Anterior", style=discord.ButtonStyle.primary, custom_id="btn_catalog_prev")
    async def btn_prev(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ Esta sesión de catálogo no es tuya.", ephemeral=True)
            return
        if self.current_page > 0:
            self.current_page -= 1
            self._update_buttons()
            embed = self._build_embed()
            await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="1/1", style=discord.ButtonStyle.secondary, disabled=True, custom_id="btn_catalog_page")
    async def btn_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        pass

    @discord.ui.button(label="▶️ Siguiente", style=discord.ButtonStyle.primary, custom_id="btn_catalog_next")
    async def btn_next(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ Esta sesión de catálogo no es tuya.", ephemeral=True)
            return
        if self.current_page < self.total_pages - 1:
            self.current_page += 1
            self._update_buttons()
            embed = self._build_embed()
            await interaction.response.edit_message(embed=embed, view=self)

class PetsMasterCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="catalogo_mascotas", description="Muestra el catálogo interactivo de mascotas (5 por página) con botones ◀️ y ▶️.")
    async def catalogo_mascotas_cmd(self, interaction: discord.Interaction):
        await interaction.response.defer()
        
        def _fetch_catalog():
            with db_cursor() as c:
                c.execute("""
                    SELECT PetID, Name, Rarity, Emoji, Family, Temperament, EffectType, EffectValue, EffectChance, EffectCap, FavoriteGame, FlavorText
                    FROM PetsCatalog
                    WHERE Enabled = 1
                    ORDER BY 
                        CASE Rarity 
                            WHEN 'Normal' THEN 1 
                            WHEN 'Rara' THEN 2 
                            WHEN 'Épica' THEN 3 
                            WHEN 'Legendaria' THEN 4 
                            WHEN 'Mítica' THEN 5 
                        END ASC, PetID ASC
                """)
                rows = c.fetchall()
                return [
                    {
                        "id": r[0], "name": r[1], "rarity": r[2], "emoji": r[3],
                        "family": r[4], "temperament": r[5], "effect_type": r[6],
                        "effect_value": r[7], "effect_chance": r[8], "effect_cap": r[9],
                        "favorite_game": r[10], "flavor": r[11]
                    }
                    for r in rows
                ]

        all_pets = await asyncio.to_thread(_fetch_catalog)
        
        if not all_pets:
            await interaction.followup.send("❌ No hay mascotas registradas en el catálogo en este momento.", ephemeral=True)
            return

        view = PetsCatalogPaginatorView(all_pets, interaction.user.id)
        embed = view._build_embed()
        await interaction.followup.send(embed=embed, view=view)

    @app_commands.command(name="pets_catalogo", description="Muestra el catálogo interactivo de mascotas (5 por página). (Alias de /catalogo_mascotas)")
    async def pets_catalogo_cmd(self, interaction: discord.Interaction):
        await self.catalogo_mascotas_cmd(interaction)

    @app_commands.command(name="pets", description="Muestra tu colección de mascotas con sus 3 slots, nivel (1-15) y habilidades.")
    async def pets_cmd(self, interaction: discord.Interaction):
        await interaction.response.defer()
        user_id = interaction.user.id
        
        def _get_pets():
            with db_cursor() as c:
                c.execute("""
                    SELECT up.UserPetID, p.Name, p.Emoji, p.Rarity, up.EquippedSlot, up.Loyalty, up.Nickname,
                           p.EffectType, p.EffectValue, p.EffectChance, p.EffectCap, p.FavoriteGame,
                           p.Family, p.Temperament, p.FlavorText,
                           up.GamesWithOwner, up.WinsWithOwner, up.LossesWithOwner,
                           COALESCE(up.Level, 1), COALESCE(up.XP, 0)
                    FROM UserPets up JOIN PetsCatalog p ON up.PetID = p.PetID
                    WHERE up.UserID = %s AND up.Status != 'Escapó'
                    ORDER BY up.EquippedSlot IS NOT NULL DESC, p.Rarity DESC
                """, (user_id,))
                return c.fetchall()
                
        pets = await asyncio.to_thread(_get_pets)
        
        if not pets:
            embed_empty = discord.Embed(
                title="🐾 Tu Colección",
                description="No tienes ninguna mascota en tu colección.\n¡Usa `/catalogo_mascotas` para explorar todas las mascotas disponibles!",
                color=discord.Color.greyple()
            )
            await interaction.followup.send(embed=embed_empty, ephemeral=True)
            return
        
        embeds = []
        embed_main = discord.Embed(
            title=f"🐾 Colección de Mascotas de {interaction.user.display_name}",
            description=f"Tienes **{len(pets)}** mascota(s) en tu colección.",
            color=discord.Color.blurple()
        )
        embeds.append(embed_main)
        
        for (up_id, p_name, p_emoji, p_rarity, slot, loyalty, nickname,
             effect_type, effect_value, effect_chance, effect_cap, favorite_game,
             family, temperament, flavor_text,
             games_with, wins_with, losses_with, p_level, p_xp) in pets[:9]:
            
            slot_badge = f" 🏆 **[SLOT {slot.upper()}]**" if slot else " ⚪ Guardada"
            d_name = display_pet_name(p_name, nickname)
            mood_emoji, mood_text = _get_mood_from_loyalty(loyalty or 50)
            loyalty_bar = _format_loyalty_bar(loyalty or 50)
            
            rarity_colors = {
                "Normal": discord.Color.light_grey(),
                "Rara": discord.Color.blue(),
                "Épica": discord.Color.purple(),
                "Legendaria": discord.Color.gold(),
                "Mítica": discord.Color.red(),
            }
            embed_color = rarity_colors.get(p_rarity, discord.Color.blurple())
            
            pet_embed = discord.Embed(
                title=f"{p_emoji} {d_name} (Nv. {p_level}/15){slot_badge}",
                description=f"*{flavor_text or 'Una criatura leal.'}*",
                color=embed_color
            )
            
            xp_needed = get_xp_for_level(p_level)
            info_text = f"🌟 Rareza: **{p_rarity}** | 🆔 ID: `{up_id}`\n⚡ XP: **{p_xp}/{xp_needed}**"
            pet_embed.add_field(name="📋 Datos Básicos", value=info_text, inline=False)
            
            h1 = "🔓 **Nv.5 (Pasiva):** +5% efectividad de bonificación" if p_level >= 5 else "🔒 **Nv.5:** Se desbloquea en Nivel 5"
            h2 = "🔓 **Nv.10 (Reacción/Activa):** Activación autónoma de emergencia" if p_level >= 10 else "🔒 **Nv.10:** Se desbloquea en Nivel 10"
            h3 = "🔓 **Nv.15 (Definitiva):** Habilidad Definitiva Mítica" if p_level >= 15 else "🔒 **Nv.15:** Se desbloquea en Nivel 15"
            
            pet_embed.add_field(name="✨ Habilidades Desbloqueadas", value=f"{h1}\n{h2}\n{h3}", inline=False)
            
            loyalty_val = loyalty or 50
            pet_embed.add_field(
                name=f"{mood_emoji} Lealtad — {mood_text}",
                value=f"`{loyalty_bar}` **{loyalty_val}/100**",
                inline=False
            )
            
            embeds.append(pet_embed)
        
        await interaction.followup.send(embeds=embeds[:10])

    @app_commands.command(name="pet_equipar", description="Equipa una mascota en uno de los 3 slots (casino, robar, raid).")
    @app_commands.describe(pet_id="ID de la mascota", slot="Slot de equipamiento (casino, robar, raid)")
    @app_commands.choices(slot=[
        app_commands.Choice(name="Casino 🎰", value="casino"),
        app_commands.Choice(name="Robar 🥷", value="robar"),
        app_commands.Choice(name="Raid ⚔️", value="raid")
    ])
    async def pet_equipar_cmd(self, interaction: discord.Interaction, pet_id: int, slot: str):
        await interaction.response.defer(ephemeral=True)
        user_id = interaction.user.id
        
        if slot not in SLOTS_PERMITIDOS:
            await interaction.followup.send("❌ Slot no válido. Elige entre `casino`, `robar` o `raid`.", ephemeral=True)
            return

        def _equip():
            with db_cursor() as c:
                c.execute("SELECT UserPetID FROM UserPets WHERE UserPetID = %s AND UserID = %s AND Status != 'Escapó'", (pet_id, user_id))
                if not c.fetchone():
                    return False
                c.execute("UPDATE UserPets SET EquippedSlot = NULL WHERE UserID = %s AND EquippedSlot = %s", (user_id, slot))
                c.execute("UPDATE UserPets SET EquippedSlot = %s, IsActive = 1 WHERE UserPetID = %s", (slot, pet_id))
                return True
                
        success = await asyncio.to_thread(_equip)
        if success:
            await interaction.followup.send(f"✅ Mascota ID `{pet_id}` equipada exitosamente en el **Slot [{slot.upper()}]**.", ephemeral=True)
        else:
            await interaction.followup.send("❌ No se encontró esa mascota en tu colección.", ephemeral=True)

    @app_commands.command(name="pet_liberar", description="Libera una mascota de tu colección a cambio de un reembolso en Balance.")
    @app_commands.describe(pet_id="ID de la mascota a liberar")
    async def pet_liberar_cmd(self, interaction: discord.Interaction, pet_id: int):
        await interaction.response.defer(ephemeral=True)
        user_id = interaction.user.id
        
        def _liberar():
            with db_cursor() as c:
                c.execute("""
                    SELECT up.UserPetID, p.Name, p.Rarity, p.Emoji
                    FROM UserPets up JOIN PetsCatalog p ON up.PetID = p.PetID
                    WHERE up.UserPetID = %s AND up.UserID = %s AND up.Status != 'Escapó'
                """, (pet_id, user_id))
                row = c.fetchone()
                if not row:
                    return False, "Mascota no encontrada."
                
                up_id, name, rarity, emoji = row
                reembolso = REEMBOLSO_RAREZA.get(rarity, 5000)
                
                c.execute("DELETE FROM UserPets WHERE UserPetID = %s", (up_id,))
                c.execute("UPDATE Users SET Balance = Balance + %s WHERE UserID = %s", (reembolso, user_id))
                return True, (name, rarity, emoji, reembolso)
                
        success, res = await asyncio.to_thread(_liberar)
        if success:
            name, rarity, emoji, reembolso = res
            await interaction.followup.send(f"🕊️ Has liberado a {emoji} **{name}** ({rarity}). Recibiste **{reembolso:,}** 🪙 Balance de reembolso.", ephemeral=True)
        else:
            await interaction.followup.send(f"❌ {res}", ephemeral=True)

    @app_commands.command(name="abrir_caja", description="Abre una Caja de Mascotas Sellada de tu inventario (Costo: 15,000 Balance, Pity de 35).")
    async def abrir_caja_cmd(self, interaction: discord.Interaction):
        await interaction.response.defer()
        user_id = interaction.user.id
        
        def _check_and_consume():
            with db_cursor() as c:
                c.execute("SELECT Quantity FROM UserItems WHERE UserID = %s AND ItemID = 20 AND Quantity > 0 AND Used = 0", (user_id,))
                row_caja = c.fetchone()
                if not row_caja:
                    return False, "no_box"
                
                c.execute("SELECT Balance FROM Users WHERE UserID = %s", (user_id,))
                bal = c.fetchone()
                if not bal or bal[0] < 15000:
                    return False, "no_balance"
                
                c.execute("UPDATE Users SET Balance = Balance - 15000 WHERE UserID = %s", (user_id,))
                usar_item_usuario(user_id, 20)
                
                c.execute("SELECT UnluckyBoxesCount FROM UserPityState WHERE UserID = %s", (user_id,))
                pity_row = c.fetchone()
                pity_count = pity_row[0] if pity_row else 0
                
                force_high_rarity = pity_count >= 35
                
                if force_high_rarity:
                    rarity = random.choice(["Legendaria", "Mítica"])
                    c.execute("UPDATE UserPityState SET UnluckyBoxesCount = 0 WHERE UserID = %s", (user_id,))
                else:
                    r = random.random()
                    if r < 0.50: rarity = "Normal"
                    elif r < 0.80: rarity = "Rara"
                    elif r < 0.95: rarity = "Épica"
                    elif r < 0.99: rarity = "Legendaria"
                    else: rarity = "Mítica"
                    
                    if rarity in ["Legendaria", "Mítica"]:
                        c.execute("INSERT INTO UserPityState (UserID, UnluckyBoxesCount) VALUES (%s, 0) ON CONFLICT (UserID) DO UPDATE SET UnluckyBoxesCount = 0", (user_id,))
                    else:
                        c.execute("INSERT INTO UserPityState (UserID, UnluckyBoxesCount) VALUES (%s, 1) ON CONFLICT (UserID) DO UPDATE SET UnluckyBoxesCount = UserPityState.UnluckyBoxesCount + 1", (user_id,))

                c.execute("SELECT PetID, Name, Emoji, Rarity, FlavorText FROM PetsCatalog WHERE Rarity = %s AND Enabled = 1 ORDER BY RANDOM() LIMIT 1", (rarity,))
                chosen_pet = c.fetchone()
                
                c.execute("INSERT INTO UserPets (UserID, PetID, Level, XP, Loyalty) VALUES (%s, %s, 1, 0, 100) RETURNING UserPetID", (user_id, chosen_pet[0]))
                new_up_id = c.fetchone()[0]
                
                return True, (chosen_pet, force_high_rarity, pity_count)

        success, res = await asyncio.to_thread(_check_and_consume)
        if not success:
            if res == "no_box":
                await interaction.followup.send("❌ No tienes una **Caja de Mascotas Sellada (ID: 20)** en tu inventario.", ephemeral=True)
            elif res == "no_balance":
                await interaction.followup.send("❌ Requieres **15,000 Balance** para cubrir la tasa de apertura de esta caja.", ephemeral=True)
            return

        chosen_pet, force_high_rarity, pity_count = res
        pet_id, pet_name, pet_emoji, pet_rarity, flavor = chosen_pet

        reel_emojis = ["🐱", "🐶", "🦊", "🦄", "🐉", "🦅", "🦁", "🐺", "🐼"]
        msg = await interaction.followup.send("🎰 **[ ABRIENDO CAJA DE MASCOTAS ]**\n`[ ❓ | ❓ | ❓ | ❓ | ❓ ]`\n⏱️ Girando el carrete...")

        delays = [0.6, 0.8, 1.2, 1.8]
        for delay in delays:
            await asyncio.sleep(delay)
            random.shuffle(reel_emojis)
            reel_str = " | ".join(reel_emojis[:5])
            await msg.edit(content=f"🎰 **[ ABRIENDO CAJA DE MASCOTAS ]**\n`[ {reel_str} ]`\n⏱️ Desacelerando ruleta...")

        await asyncio.sleep(2.0)

        pity_text = " *(✨ ¡GARANTÍA DE PITY DE 35 CAJAS ACTIVADA!)*" if force_high_rarity else f" *(Pity acumulado: {pity_count+1}/35)*"
        embed = discord.Embed(
            title="🎉 ¡CAJA ABIERTA CON ÉXITO!",
            description=f"¡Has obtenido a {pet_emoji} **{pet_name}**!\n\n🌟 Rareza: **{pet_rarity}**{pity_text}\n_{flavor}_",
            color=discord.Color.gold()
        )
        embed.set_footer(text="Usa /pets para ver a tu nueva mascota.")
        await msg.edit(content="🎰 **[ REEL DETENIDO ]**", embed=embed)

async def setup(bot):
    await bot.add_cog(PetsMasterCog(bot))
    print("PetsMasterCog loaded successfully.")
