import time
import random
from datetime import datetime
from src.db import db_cursor

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

def get_initial_stock_for_item(item: dict) -> int:
    """Calcula el stock inicial de un ítem según su peso de rareza."""
    w = item.get("rarity_weight", 100)
    if w >= 40:
        return 10
    elif w >= 25:
        return 5
    elif w >= 15:
        return 2
    else:
        return 1

def select_rotated_items(catalog, count: int, rotation_seconds: int, rarity_key: str = "rarity_weight"):
    """
    Selecciona determinísticamente `count` ítems del catálogo basados en la ventana de tiempo.
    Usa el campo `rarity_weight` de cada ítem (si existe) para ponderar las probabilidades.
    """
    current_seed, _, _ = get_rotation_info(rotation_seconds)
    rng = random.Random(current_seed)
    
    if len(catalog) <= count:
        return catalog.copy()

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

def get_stock_remaining(shop_type: str, item: dict, rotation_seconds: int) -> int:
    """Obtiene el stock restante de un ítem para la rotación actual."""
    current_seed, _, _ = get_rotation_info(rotation_seconds)
    initial_stock = get_initial_stock_for_item(item)
    item_id = item["id"]

    with db_cursor() as c:
        c.execute("""
            SELECT StockRemaining FROM UserShopStock
            WHERE RotationSeed = %s AND ShopType = %s AND ItemID = %s
        """, (current_seed, shop_type, item_id))
        row = c.fetchone()
        if row:
            return max(0, row[0])
        else:
            c.execute("""
                INSERT INTO UserShopStock (RotationSeed, ShopType, ItemID, StockRemaining)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (RotationSeed, ShopType, ItemID) DO NOTHING
            """, (current_seed, shop_type, item_id, initial_stock))
            return initial_stock

def consume_stock(shop_type: str, item: dict, rotation_seconds: int) -> bool:
    """Intenta consumir 1 unidad del stock disponible del ítem en la rotación actual."""
    current_seed, _, _ = get_rotation_info(rotation_seconds)
    initial_stock = get_initial_stock_for_item(item)
    item_id = item["id"]

    with db_cursor() as c:
        # Asegurar fila
        c.execute("""
            INSERT INTO UserShopStock (RotationSeed, ShopType, ItemID, StockRemaining)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (RotationSeed, ShopType, ItemID) DO NOTHING
        """, (current_seed, shop_type, item_id, initial_stock))

        c.execute("""
            UPDATE UserShopStock
            SET StockRemaining = StockRemaining - 1
            WHERE RotationSeed = %s AND ShopType = %s AND ItemID = %s AND StockRemaining > 0
            RETURNING StockRemaining
        """, (current_seed, shop_type, item_id))
        
        row = c.fetchone()
        return row is not None
