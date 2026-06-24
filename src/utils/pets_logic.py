import random
from src.db import get_active_pet, add_user_pet, remove_user_pet, get_pet_catalog, db_cursor

def get_user_stats_for_pets(user_id):
    with db_cursor() as cursor:
        cursor.execute("SELECT TotalGamesPlayed, HotStreak, ColdStreak, TotalAmountWon, TotalAmountBet FROM UserGameStats WHERE UserID = %s", (user_id,))
        row = cursor.fetchone()
        if row:
            return {
                "TotalGamesPlayed": row[0] or 0,
                "HotStreak": row[1] or 0,
                "ColdStreak": row[2] or 0,
                "TotalAmountWon": row[3] or 0.0,
                "TotalAmountBet": row[4] or 0.0
            }
        return None

def check_pet_encounter(user_id: int):
    """Devuelve (pet_dict) si hay un encuentro, o None."""
    stats = get_user_stats_for_pets(user_id)
    if not stats: return None
        
    hot_streak = stats["HotStreak"]
    cold_streak = stats["ColdStreak"]
    volume = stats["TotalGamesPlayed"]
    
    catalog = get_pet_catalog()
    candidatas = []
    
    for pet in catalog:
        # Asegurarse de acceder por nombre de columna (dict) o tupla
        # Si get_pet_catalog devuelve dicts:
        encounter_type = pet.get("EncounterType", "any")
        
        cumple = False
        if encounter_type == "hot_streak" and hot_streak >= 5:
            cumple = True
        elif encounter_type == "cold_streak" and cold_streak >= 5:
            cumple = True
        elif encounter_type == "volume" and volume > 10:
            cumple = True
            
        if cumple:
            # EffectChance se usará como spawn chance
            chance = pet.get("EffectChance", 0.05)
            if encounter_type == "hot_streak": chance += (hot_streak * 0.02)
            if encounter_type == "cold_streak": chance += (cold_streak * 0.02)
            
            if random.random() < chance:
                candidatas.append(pet)
                
    if candidatas:
        return random.choice(candidatas)
    return None

def check_pet_abandonment(user_id: int):
    """Verifica si la mascota activa abandona al usuario. Retorna la mascota que escapó o None."""
    active_pet = get_active_pet(user_id)
    if not active_pet: return None
        
    stats = get_user_stats_for_pets(user_id)
    if not stats: return None
        
    hot_streak = stats["HotStreak"]
    cold_streak = stats["ColdStreak"]
    encounter_type = active_pet.get("EncounterType", "any")
    
    abandona = False
    razon = ""
    
    if encounter_type == "hot_streak" and cold_streak >= 5:
        abandona = True
        razon = "odia perder."
    elif encounter_type == "cold_streak" and hot_streak >= 4:
        abandona = True
        razon = "solo se alimenta de tu miseria."
        
    if abandona and random.random() < 0.6: # 60% chance de escapar si se cumple
        remove_user_pet(user_id, active_pet["UserPetID"])
        active_pet["razon_escape"] = razon
        return active_pet
        
    return None

# --- HELPERS DE BENEFICIOS ---

def get_pet_multiplier(user_id: int) -> float:
    """Devuelve el multiplicador de ganancias de casino (ej: 1.10) si tiene un pet 'multiplier'."""
    pet = get_active_pet(user_id)
    if pet and pet.get("EffectType") == "multiplier":
        return float(pet.get("EffectValue", 1.0))
    return 1.0

def get_pet_refund(user_id: int) -> float:
    """Devuelve el porcentaje de devolución de pérdidas de casino (ej: 0.15) si tiene un pet 'refund'."""
    pet = get_active_pet(user_id)
    if pet and pet.get("EffectType") == "refund":
        return float(pet.get("EffectValue", 0.0))
    return 0.0

def get_pet_energy_discount(user_id: int) -> float:
    """Devuelve el multiplicador de coste de energía (ej: 0.95) si tiene un pet 'energy_reduction'."""
    pet = get_active_pet(user_id)
    if pet and pet.get("EffectType") == "energy_reduction":
        return float(pet.get("EffectValue", 1.0))
    return 1.0
