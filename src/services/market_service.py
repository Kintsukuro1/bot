import random
import math
import logging
from src.db import db_cursor

logger = logging.getLogger(__name__)

MARKET_ASSETS = {
    "agrounion":     {"nombre": "AgroUnión",     "categoria": "accion", "precio_inicial": 100.0, "sigma_tick": 0.0018, "drift": 0.00005, "dividendo_pct": 0.008},
    "banconova":     {"nombre": "BancoNova",     "categoria": "accion", "precio_inicial": 150.0, "sigma_tick": 0.0022, "drift": 0.00006, "dividendo_pct": 0.005},
    "tecnocorp":     {"nombre": "TecnoCorp",     "categoria": "accion", "precio_inicial": 80.0,  "sigma_tick": 0.0028, "drift": 0.00008, "dividendo_pct": 0.003},
    "obsidianchain": {"nombre": "ObsidianChain",  "categoria": "cripto", "precio_inicial": 50.0,  "sigma_tick": 0.0055, "drift": 0.00002, "dividendo_pct": 0.0},
    "bytecoin":      {"nombre": "ByteCoin",      "categoria": "cripto", "precio_inicial": 200.0, "sigma_tick": 0.0070, "drift": 0.00005, "dividendo_pct": 0.0},
    "moontoken":     {"nombre": "MoonToken",     "categoria": "cripto", "precio_inicial": 10.0,  "sigma_tick": 0.0095, "drift": -0.00002, "dividendo_pct": 0.0},
}
PUMP_DUMP_CHANCE = 0.0025  # por tick, solo activos categoria "cripto" (~1 cada 30 min)
PUMP_DUMP_RANGE = (0.20, 0.35)  # magnitud del salto, dirección aleatoria
TICK_SECONDS = 5
PERSIST_EVERY_SECONDS = 30  # cada 30 segundos


class MarketService:
    _prices = {}  # {asset_key: precio_actual_float}, cargado desde DB al iniciar

    @classmethod
    def load_prices_from_db(cls):
        """Al arrancar el bot, cargar MarketAssets.PrecioActual en cls._prices."""
        try:
            with db_cursor() as cursor:
                cursor.execute("SELECT AssetKey, PrecioActual FROM MarketAssets")
                rows = cursor.fetchall()
                db_prices = {row[0]: float(row[1]) for row in rows}
                
            # Cargar activos desde DB o usar precio inicial si no existen
            for key, data in MARKET_ASSETS.items():
                if key in db_prices:
                    cls._prices[key] = db_prices[key]
                else:
                    cls._prices[key] = data["precio_inicial"]
            logger.info(f"[MarketService] Precios iniciales cargados: {cls._prices}")
        except Exception as e:
            logger.error(f"[MarketService] Error al cargar precios desde la DB: {e}")
            # Fallback en caso de error
            for key, data in MARKET_ASSETS.items():
                cls._prices[key] = data["precio_inicial"]

    @classmethod
    def tick(cls):
        """Se llama cada TICK_SECONDS. Para cada activo:
        Z = random.gauss(0, 1)
        precio_nuevo = precio_actual * math.exp(drift + sigma_tick * Z)
        Si categoria == 'cripto' y random.random() < PUMP_DUMP_CHANCE:
            aplicar un salto adicional de +/- PUMP_DUMP_RANGE (dirección al azar)
        Actualizar cls._prices[asset_key]."""
        for key, data in MARKET_ASSETS.items():
            precio_actual = cls._prices.get(key, data["precio_inicial"])
            drift = data["drift"]
            sigma_tick = data["sigma_tick"]
            category = data["categoria"]
            
            Z = random.gauss(0, 1)
            precio_nuevo = precio_actual * math.exp(drift + sigma_tick * Z)
            
            # Jump diffusion para criptomonedas
            if category == "cripto" and random.random() < PUMP_DUMP_CHANCE:
                direction = 1 if random.random() < 0.5 else -1
                jump_pct = random.uniform(PUMP_DUMP_RANGE[0], PUMP_DUMP_RANGE[1])
                old_val = precio_nuevo
                precio_nuevo = precio_nuevo * (1.0 + direction * jump_pct)
                logger.warning(f"[MarketService] ¡EVENTO PUMP/DUMP en {key}! Precio saltó de {old_val:.4f} a {precio_nuevo:.4f}")
                
            cls._prices[key] = max(0.01, precio_nuevo)

    @classmethod
    def get_price(cls, asset_key) -> float:
        """Obtiene el precio actual de un activo en memoria."""
        return cls._prices.get(asset_key, MARKET_ASSETS.get(asset_key, {}).get("precio_inicial", 0.0))

    @classmethod
    def get_all_prices(cls) -> dict:
        """Retorna una copia del diccionario de precios actuales."""
        return cls._prices.copy()

    @classmethod
    def persist_prices(cls):
        """Guarda los precios actuales en la DB e inserta el historial de precios."""
        try:
            with db_cursor() as cursor:
                for key, price in cls._prices.items():
                    # Actualizar precio actual
                    cursor.execute("""
                        UPDATE MarketAssets 
                        SET PrecioActual = %s, UltimaActualizacion = NOW() 
                        WHERE AssetKey = %s
                    """, (price, key))
                    # Insertar en historial
                    cursor.execute("""
                        INSERT INTO MarketPriceHistory (AssetKey, Precio, Timestamp) 
                        VALUES (%s, %s, NOW())
                    """, (key, price))
            logger.info("[MarketService] Precios persistidos e historial registrado en DB.")
        except Exception as e:
            logger.error(f"[MarketService] Error al persistir precios en la DB: {e}")

    @classmethod
    def apply_large_operation_impact(cls, asset_key: str, quantity: float, is_buy: bool):
        """Aplica un empujón al precio si la operación representa más del 2% del total circulante."""
        try:
            with db_cursor() as cursor:
                cursor.execute("SELECT SUM(Cantidad) FROM UserPortfolio WHERE AssetKey = %s", (asset_key,))
                row = cursor.fetchone()
                total_circulante = float(row[0]) if row and row[0] is not None else 0.0
                
            if total_circulante <= 0.0:
                # Si no hay circulante en portafolios, no hay impacto comercial
                return
                
            fraction = quantity / total_circulante
            if fraction > 0.02:
                # Cap el impacto máximo a un 50% de cambio para evitar anomalías absurdas
                fraction = min(fraction, 0.5)
                # Empujón proporcional al tamaño (factor multiplicativo de 0.5)
                push_factor = 0.5
                change_pct = fraction * push_factor
                
                current_price = cls.get_price(asset_key)
                if is_buy:
                    new_price = current_price * (1.0 + change_pct)
                else:
                    new_price = current_price * (1.0 - change_pct)
                    
                new_price = max(0.01, new_price)
                cls._prices[asset_key] = new_price
                
                # Actualizar inmediatamente en base de datos el precio impactado
                with db_cursor() as cursor:
                    cursor.execute("""
                        UPDATE MarketAssets 
                        SET PrecioActual = %s, UltimaActualizacion = NOW() 
                        WHERE AssetKey = %s
                    """, (new_price, asset_key))
                    cursor.execute("""
                        INSERT INTO MarketPriceHistory (AssetKey, Precio, Timestamp) 
                        VALUES (%s, %s, NOW())
                    """, (asset_key, new_price))
                    
                logger.info(
                    f"[MarketService] Gran operación detectada en {asset_key}. "
                    f"Impacto aplicado: {current_price:.2f} -> {new_price:.2f} ({(new_price/current_price - 1)*100:+.2f}%)"
                )
        except Exception as e:
            logger.error(f"[MarketService] Error aplicando impacto de gran operación para {asset_key}: {e}")
