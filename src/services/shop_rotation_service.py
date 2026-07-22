import time
import random
from datetime import datetime

NORMAL_SHOP_ROTATION_SECONDS = 1800   # 30 minutos
BLACKMARKET_ROTATION_SECONDS = 10800  # 3 horas

def get_rotation_info(rotation_seconds: int):
    """Devuelve el seed actual y los segundos restantes para el próximo reset."""
    now = int(time.time())
    current_seed = now // rotation_seconds
    next_reset = (current_seed + 1) * rotation_seconds
    seconds_remaining = max(0, next_reset - now)
    
    mins, secs = divmod(seconds_remaining, 60)
    hours, mins = divmod(mins, 60)
    if hours > 0:
        time_str = f"{hours}h {mins:02d}m {secs:02d}s"
    else:
        time_str = f"{mins:02d}m {secs:02d}s"
        
    return current_seed, seconds_remaining, time_str

def select_rotated_items(catalog, count: int, rotation_seconds: int, rarity_key: str = "rarity_weight"):
    """
    Selecciona determinísticamente `count` ítems del catálogo basados en la ventana de tiempo.
    Usa el campo `rarity_weight` de cada ítem (si existe) para ponderar las probabilidades.
    """
    current_seed, _, _ = get_rotation_info(rotation_seconds)
    rng = random.Random(current_seed)
    
    if len(catalog) <= count:
        return catalog.copy()

    # Copia el catálogo y calcula pesos
    weights = [item.get(rarity_key, 100) for item in catalog]
    
    selected = []
    available = list(zip(catalog, weights))
    
    for _ in range(count):
        if not available:
            break
        items_list, w_list = zip(*available)
        chosen = rng.choices(items_list, weights=w_list, k=1)[0]
        selected.append(chosen)
        available = [(item, w) for item, w in available if item["id"] != chosen["id"]]
        
    return selected
