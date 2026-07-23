"""
Este módulo proporciona acceso simplificado a las funciones de base de datos PostgreSQL.
"""

import psycopg2
import os
import threading
import logging
import hashlib
from contextlib import contextmanager
from psycopg2.pool import ThreadedConnectionPool
from dotenv import load_dotenv
from typing import Tuple, Optional
from dataclasses import dataclass
from datetime import datetime

@dataclass
class InvestmentStartResult:
    success: bool
    user_id: int
    amount: int
    new_balance: Optional[int] = None
    started_at: Optional[datetime] = None
    vencimiento: Optional[datetime] = None
    reason: Optional[str] = None

# Cargar variables de entorno del archivo .env ubicado en la raíz del proyecto
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.env'))

logger = logging.getLogger(__name__)

# Configurar conexión cargando desde variables de entorno con fallbacks seguros de PostgreSQL
host = os.getenv('DB_HOST', 'localhost')
port = os.getenv('DB_PORT', '5432')
database = os.getenv('DB_NAME', 'CasinoBot')
username = os.getenv('DB_USER', 'postgres')
password = os.getenv('DB_PASSWORD')

if not password:
    raise ValueError("ERROR CRÍTICO DE CONFIGURACIÓN: La variable de entorno 'DB_PASSWORD' no está configurada en el archivo .env.")

pool_min = int(os.getenv('DB_POOL_MIN', '1'))
pool_max = int(os.getenv('DB_POOL_MAX', '10'))
_pool = None
_pool_lock = threading.Lock()
_pool_init_failed = False
_pool_init_error = None

def _connect_direct(database_name=None):
    return psycopg2.connect(
        host=host,
        port=port,
        database=database_name or database,
        user=username,
        password=password
    )

def _get_pool():
    """
    Inicializa el ThreadedConnectionPool de forma lazy con manejo explícito de errores
    de conexión. Si la creación falla, se marca el estado de fallo para evitar
    bucles de reintentos y se devuelve una excepción consistente a las capas superiores.
    """
    global _pool, _pool_init_failed, _pool_init_error

    # Si ya se marcó que la inicialización falló anteriormente, no volver a intentar
    if _pool_init_failed:
        # Re-lanzamos la última excepción registrada para mantener trazabilidad
        raise RuntimeError(
            "Error inicializando el pool de conexiones a la base de datos."
        ) from _pool_init_error

    # Si ya existe un pool inicializado correctamente, lo reutilizamos
    if _pool is not None:
        return _pool

    # Inicialización lazy con doble chequeo bajo lock para seguridad en concurrencia
    with _pool_lock:
        if _pool is not None:
            return _pool

        try:
            logger.info(
                "Inicializando ThreadedConnectionPool (minconn=%s, maxconn=%s, host=%s, db=%s, user=%s)",
                pool_min,
                pool_max,
                host,
                database,
                username,
            )
            _pool = ThreadedConnectionPool(
                minconn=pool_min,
                maxconn=pool_max,
                host=host,
                port=port,
                database=database,
                user=username,
                password=password,
            )
            logger.info("ThreadedConnectionPool inicializado correctamente.")
            return _pool
        except psycopg2.OperationalError as e:
            # Errores típicos de conexión: credenciales inválidas, DB caída, etc.
            _pool_init_failed = True
            _pool_init_error = e
            logger.error(
                "Fallo al inicializar el ThreadedConnectionPool (error de conexión): %s",
                str(e),
                exc_info=True,
            )
            raise RuntimeError(
                "No se pudo establecer el pool de conexiones a la base de datos "
                "(error de conexión)."
            ) from e
        except Exception as e:
            # Cualquier otro tipo de error inesperado también marca fallo
            _pool_init_failed = True
            _pool_init_error = e
            logger.error(
                "Fallo inesperado al inicializar el ThreadedConnectionPool: %s",
                str(e),
                exc_info=True,
            )
            raise RuntimeError(
                "Error inesperado al inicializar el pool de conexiones a la base de datos."
            ) from e

def close_connection_pool():
    """Cierra todas las conexiones del pool si fue inicializado."""
    global _pool, _pool_init_failed, _pool_init_error
    if _pool is not None:
        _pool.closeall()
        _pool = None
    _pool_init_failed = False
    _pool_init_error = None

def get_connection():
    """Retorna una conexión directa a PostgreSQL.

    Se conserva para compatibilidad con módulos que llaman conn.close()
    manualmente. El pool se usa en db_cursor().
    """
    return _connect_direct()

@contextmanager
def db_cursor():
    """Context manager para obtener un cursor con commit/rollback automático."""
    pool = _get_pool()
    conn = pool.getconn()
    try:
        with conn.cursor() as cursor:
            yield cursor
        conn.commit()
    except Exception:
        if not conn.closed:
            conn.rollback()
        raise
    finally:
        pool.putconn(conn, close=bool(conn.closed))

def get_balance(user_id):
    """Obtiene el saldo actual de un usuario."""
    with db_cursor() as cursor:
        cursor.execute("SELECT Balance FROM Users WHERE UserID = %s", (user_id,))
        row = cursor.fetchone()
        return row[0] if row else 0

def set_balance(user_id, balance):
    """Establece directamente el saldo de un usuario usando Upsert nativo de PostgreSQL."""
    with db_cursor() as cursor:
        cursor.execute("""
            INSERT INTO Users (UserID, Balance) VALUES (%s, %s)
            ON CONFLICT (UserID) DO UPDATE SET Balance = EXCLUDED.Balance
            """, (user_id, balance))

def add_balance(user_id, amount, cursor=None):
    """Añade (o resta) saldo a un usuario de forma atómica usando Upsert nativo de PostgreSQL."""
    query = """
            INSERT INTO Users (UserID, Balance) VALUES (%s, %s)
            ON CONFLICT (UserID) DO UPDATE SET Balance = Users.Balance + EXCLUDED.Balance
            """
    if cursor is not None:
        cursor.execute(query, (user_id, amount))
    else:
        with db_cursor() as cursor:
            cursor.execute(query, (user_id, amount))

def deduct_balance(user_id, amount):
    """Resta saldo a un usuario de forma atómica y segura. 
    Retorna (True, nuevo_saldo) si tuvo éxito, (False, 0) en caso contrario."""
    with db_cursor() as cursor:
        cursor.execute("""
            UPDATE Users 
            SET Balance = Balance - %s 
            WHERE UserID = %s AND Balance >= %s
            RETURNING Balance
        """, (amount, user_id, amount))
        row = cursor.fetchone()
        if row:
            return True, row[0]
        return False, 0

def get_combat_wallet(user_id):
    """Retorna el saldo en Bronce de un usuario."""
    with db_cursor() as cursor:
        cursor.execute("SELECT Bronze FROM CombatWallet WHERE UserID = %s", (user_id,))
        row = cursor.fetchone()
        return row[0] if row else 0

def add_combat_currency(user_id, bronze_amount, cursor=None):
    """Añade (o resta, si bronze_amount es negativo) Bronce de forma atómica."""
    query = """
            INSERT INTO CombatWallet (UserID, Bronze) VALUES (%s, %s)
            ON CONFLICT (UserID) DO UPDATE SET Bronze = CombatWallet.Bronze + EXCLUDED.Bronze
            """
    if cursor is not None:
        cursor.execute(query, (user_id, bronze_amount))
    else:
        with db_cursor() as cursor:
            cursor.execute(query, (user_id, bronze_amount))

def spend_combat_currency(user_id, bronze_amount, cursor=None):
    """Intenta gastar Bronce. Retorna (True, nuevo_saldo) si alcanzaba, (False, saldo_actual) si no.
    Debe ser atómico (verificar saldo y descontar en la misma transacción, evitar condiciones de
    carrera si dos compras ocurren casi al mismo tiempo) — seguir el mismo patrón de `deduct_balance`
    adaptado a esta tabla."""
    def _execute_spend(cur):
        cur.execute("""
            UPDATE CombatWallet 
            SET Bronze = Bronze - %s 
            WHERE UserID = %s AND Bronze >= %s
            RETURNING Bronze
        """, (bronze_amount, user_id, bronze_amount))
        row = cur.fetchone()
        if row:
            return True, row[0]
        
        # Si no alcanzó, obtenemos el saldo actual para retornarlo
        cur.execute("SELECT Bronze FROM CombatWallet WHERE UserID = %s", (user_id,))
        row = cur.fetchone()
        return False, row[0] if row else 0

    if cursor is not None:
        return _execute_spend(cursor)
    else:
        with db_cursor() as db_cur:
            return _execute_spend(db_cur)

def ensure_user(user_id, user_name=None):
    """Verifica si el usuario existe en la base de datos y lo crea si no."""
    from datetime import datetime
    
    # Verificar si el nombre parece un nombre genérico (User_ID) para no usarlo
    is_generic_name = user_name and (user_name == f"User_{user_id}" or user_name.startswith("User_"))
    
    with db_cursor() as cursor:
        cursor.execute("SELECT UserName, StartDate FROM Users WHERE UserID = %s", (user_id,))
        row = cursor.fetchone()
        
        if not row:
            start_date = datetime.now().date()
            # Solo usar el nombre si no es genérico
            actual_user_name = None if is_generic_name else user_name
            cursor.execute("""
                INSERT INTO Users (UserID, Balance, LastLogin, Streak, UserName, StartDate) 
                VALUES (%s, %s, NULL, %s, %s, %s)
                """, (user_id, 500, 0, actual_user_name, start_date))
        else:
            # Si falta alguno de los campos, actualízalo
            current_name, current_start = row[0], row[1]
            updates = []
            params = []
            
            # Solo actualizar el nombre si:
            # 1. El nombre actual está vacío o es None
            # 2. El nombre nuevo no es genérico
            # 3. El nombre nuevo no es igual al actual
            if ((not current_name) and user_name and not is_generic_name) or \
               (current_name and user_name and current_name != user_name and not is_generic_name):
                updates.append("UserName = %s")
                params.append(user_name)
            if not current_start:
                updates.append("StartDate = %s")
                params.append(datetime.now().date())
            if updates:
                set_clause = ", ".join(updates)
                cursor.execute(f"UPDATE Users SET {set_clause} WHERE UserID = %s", tuple(params) + (user_id,))

def registrar_transaccion(user_id, amount, tipo, cursor=None):
    """Registra una transacción en el historial."""
    from datetime import datetime
    if cursor is not None:
        cursor.execute("""
            INSERT INTO Transactions (UserID, Amount, TransactionType, Date)
            VALUES (%s, %s, %s, %s)
        """, (user_id, amount, tipo, datetime.now()))
    else:
        with db_cursor() as cursor:
            cursor.execute("""
                INSERT INTO Transactions (UserID, Amount, TransactionType, Date)
                VALUES (%s, %s, %s, %s)
            """, (user_id, amount, tipo, datetime.now()))

def transfer_balance(from_user_id, to_user_id, amount, reason):
    """Realiza una transferencia atómica de saldo entre dos usuarios."""
    from datetime import datetime
    from src.utils.economy_config import TRANSACTION_TAX
    with db_cursor() as cursor:
        # Prevenir deadlocks ordenando los IDs y bloqueando ambas filas
        ids = sorted([from_user_id, to_user_id])
        cursor.execute("SELECT UserID, Balance FROM Users WHERE UserID IN (%s, %s) FOR UPDATE", (ids[0], ids[1]))
        balances = {row[0]: row[1] for row in cursor.fetchall()}
        
        from_balance = balances.get(from_user_id, 0)
        if from_balance < amount:
            return False, 0, 0
        
        # Descontar del emisor
        cursor.execute("UPDATE Users SET Balance = Balance - %s WHERE UserID = %s RETURNING Balance", (amount, from_user_id))
        from_new_balance = cursor.fetchone()[0]
        
        # Calcular impuesto por transacción y monto neto
        impuesto = int(amount * TRANSACTION_TAX["transferencia"])
        monto_neto = amount - impuesto
        
        # Sumar al receptor (solo recibe monto neto)
        cursor.execute("""
            INSERT INTO Users (UserID, Balance) VALUES (%s, %s)
            ON CONFLICT (UserID) DO UPDATE SET Balance = Users.Balance + EXCLUDED.Balance
            RETURNING Balance
        """, (to_user_id, monto_neto))
        to_new_balance = cursor.fetchone()[0]
        
        # Registrar transacciones
        cursor.execute("""
            INSERT INTO Transactions (UserID, Amount, TransactionType, Date)
            VALUES (%s, %s, %s, %s)
        """, (from_user_id, -amount, f"Transferencia: {reason} (a {to_user_id})", datetime.now()))
        cursor.execute("""
            INSERT INTO Transactions (UserID, Amount, TransactionType, Date)
            VALUES (%s, %s, %s, %s)
        """, (to_user_id, monto_neto, f"Transferencia: {reason} (de {from_user_id})", datetime.now()))
        
        return True, from_new_balance, to_new_balance

def agregar_item_usuario(user_id, item_id, quantity=1, expiry=None):
    """Agrega un item al inventario del usuario.
    Usa el ID primario para evitar actualizar múltiples filas duplicadas."""
    from datetime import datetime, timedelta
    try:
        # Si no se proporciona fecha de expiración, decidimos qué hacer según el tipo de ítem
        if expiry is None:
            # Los ítems con IDs >= 1000 son mejoras permanentes (usar fecha lejana)
            if item_id >= 1000:
                # Fecha muy lejana para representar "permanente" (10 años)
                expiry = datetime.now() + timedelta(days=3650)
            else:
                # Ítems normales duran 7 días por defecto
                expiry = datetime.now() + timedelta(days=7)
        
        with db_cursor() as cursor:
            # Buscar UNA fila activa por ID primario para evitar duplicados
            cursor.execute("""
                SELECT ID FROM UserItems 
                WHERE UserID = %s AND ItemID = %s AND Expiry > NOW() AND Used = 0
                ORDER BY ID ASC LIMIT 1
            """, (user_id, item_id))
            row = cursor.fetchone()
            
            if row:
                # El usuario ya tiene este ítem, aumentamos la cantidad SOLO en esa fila
                cursor.execute("""
                    UPDATE UserItems 
                    SET Quantity = Quantity + %s
                    WHERE ID = %s
                """, (quantity, row[0]))
            else:
                # El usuario no tiene el ítem, lo insertamos
                cursor.execute("""
                    INSERT INTO UserItems (UserID, ItemID, Quantity, Expiry, Used)
                    VALUES (%s, %s, %s, %s, 0)
                """, (user_id, item_id, quantity, expiry))
            return True
    except Exception as e:
        logger.error(f"Error agregando ítem al usuario: {e}", exc_info=e)
        return False

def usuario_tiene_item(user_id, item_id):
    """Verifica si un usuario tiene un ítem específico en su inventario."""
    try:
        with db_cursor() as cursor:
            cursor.execute("""
                SELECT 1 FROM UserItems 
                WHERE UserID = %s AND ItemID = %s AND Quantity > 0 AND Used = 0
                AND Expiry > NOW()
                LIMIT 1
            """, (user_id, item_id))
            row = cursor.fetchone()
            return row is not None
    except Exception as e:
        logger.error(f"Error de base de datos al verificar ítem de usuario: {e}")
        return False

def usuario_tiene_mejora(user_id, item_id):
    """Verifica si el usuario tiene una mejora permanente del black market (IDs 1000+)."""
    if item_id < 1000:
        return usuario_tiene_item(user_id, 1000 + item_id)
    return usuario_tiene_item(user_id, item_id)

def get_user_items(user_id):
    """Obtiene todos los ítems activos de un usuario.
    Consolida filas duplicadas del mismo ItemID sumando sus cantidades."""
    try:
        with db_cursor() as cursor:
            cursor.execute("""
                SELECT ItemID, SUM(Quantity) as TotalQty, MAX(Expiry) as Expiry, 0 as Used
                FROM UserItems 
                WHERE UserID = %s AND Quantity > 0 AND Used = 0
                AND Expiry > NOW()
                GROUP BY ItemID
            """, (user_id,))
            
            items = []
            for row in cursor.fetchall():
                items.append({
                    'item_id': row[0],
                    'quantity': row[1],
                    'expiry': row[2],
                    'used': row[3]
                })
            return items
    except Exception as e:
        logger.error(f"Error obteniendo ítems de usuario: {e}", exc_info=e)
        return []

def usar_item_usuario(user_id, item_id):
    """Consume 1 unidad del ítem del inventario del usuario.
    Usa el ID primario para garantizar que solo se toque una fila."""
    try:
        with db_cursor() as cursor:
            # Seleccionamos la fila específica por ID primario (la más antigua primero)
            cursor.execute("""
                SELECT ID, Quantity
                FROM UserItems 
                WHERE UserID = %s AND ItemID = %s AND Quantity > 0 AND Used = 0
                AND Expiry > NOW()
                ORDER BY Expiry ASC
                LIMIT 1
            """, (user_id, item_id))
            
            row = cursor.fetchone()
            if not row:
                return False
                
            row_id = row[0]
            
            # Actualizamos SOLO esa fila usando su ID primario
            cursor.execute("""
                UPDATE UserItems 
                SET Quantity = Quantity - 1,
                    Used = CASE WHEN Quantity - 1 <= 0 THEN 1 ELSE Used END
                WHERE ID = %s AND Quantity > 0
            """, (row_id,))
            return cursor.rowcount > 0
    except Exception as e:
        logger.error(f"Error usando ítem: {e}", exc_info=e)
        return False

def check_and_register_energy_use(user_id, item_id):
    """
    Verifica si un usuario puede usar un objeto de energía (máximo 4 usos al día).
    Si está bloqueado por cooldown, retorna ('blocked', segundos_restantes).
    Si supera los 4 usos, inicia un bloqueo de 24 horas y retorna ('blocked_start', 86400).
    De lo contrario, registra el uso y retorna ('ok', None).
    """
    from datetime import datetime, timedelta
    try:
        with db_cursor() as cursor:
            # 1. Verificar si el usuario está bloqueado actualmente por este ítem
            cursor.execute("""
                SELECT BlockedUntil FROM DailyItemUsage 
                WHERE UserID = %s AND ItemID = %s AND BlockedUntil > NOW()
                ORDER BY BlockedUntil DESC LIMIT 1
            """, (user_id, item_id))
            row = cursor.fetchone()
            if row:
                blocked_until = row[0]
                time_remaining = (blocked_until - datetime.now()).total_seconds()
                return 'blocked', max(0, int(time_remaining))

            # 2. Obtener la cantidad de usos de hoy
            cursor.execute("""
                SELECT UsageCount FROM DailyItemUsage 
                WHERE UserID = %s AND ItemID = %s AND UsageDate = CURRENT_DATE
            """, (user_id, item_id))
            row = cursor.fetchone()

            if row:
                count = row[0]
                if count >= 4:
                    # Intento 5 o superior: iniciar bloqueo de 24 horas
                    blocked_until = datetime.now() + timedelta(hours=24)
                    cursor.execute("""
                        UPDATE DailyItemUsage 
                        SET BlockedUntil = %s 
                        WHERE UserID = %s AND ItemID = %s AND UsageDate = CURRENT_DATE
                    """, (blocked_until, user_id, item_id))
                    return 'blocked_start', 86400
                else:
                    # Incrementar usos
                    cursor.execute("""
                        UPDATE DailyItemUsage 
                        SET UsageCount = UsageCount + 1 
                        WHERE UserID = %s AND ItemID = %s AND UsageDate = CURRENT_DATE
                    """, (user_id, item_id))
                    return 'ok', None
            else:
                # Primer uso del día
                cursor.execute("""
                    INSERT INTO DailyItemUsage (UserID, ItemID, UsageDate, UsageCount) 
                    VALUES (%s, %s, CURRENT_DATE, 1)
                """, (user_id, item_id))
                return 'ok', None
    except Exception as e:
        logger.error(f"Error en check_and_register_energy_use: {e}", exc_info=e)
        return 'error', None

def check_and_register_shield_use(user_id, shield_item_group_id=999):
    """
    Verifica si un usuario puede usar un escudo de protección en trabajos/casino (máximo 3 usos al día).
    Si está bloqueado por cooldown, retorna ('blocked', segundos_restantes).
    Si alcanza los 3 usos, inicia un bloqueo de 24 horas y retorna ('blocked_start', 86400).
    De lo contrario, registra el uso y retorna ('ok', None).
    """
    from datetime import datetime, timedelta
    try:
        with db_cursor() as cursor:
            # 1. Verificar si el usuario está bloqueado actualmente
            cursor.execute("""
                SELECT BlockedUntil FROM DailyItemUsage 
                WHERE UserID = %s AND ItemID = %s AND BlockedUntil > NOW()
            """, (user_id, shield_item_group_id))
            row = cursor.fetchone()
            if row:
                blocked_until = row[0]
                time_remaining = (blocked_until - datetime.now()).total_seconds()
                return 'blocked', max(0, int(time_remaining))

            # 2. Obtener la cantidad de usos de hoy
            cursor.execute("""
                SELECT UsageCount FROM DailyItemUsage 
                WHERE UserID = %s AND ItemID = %s AND UsageDate = CURRENT_DATE
            """, (user_id, shield_item_group_id))
            row = cursor.fetchone()

            if row:
                count = row[0]
                if count >= 3:
                    # Iniciar/actualizar bloqueo de 24 horas
                    blocked_until = datetime.now() + timedelta(hours=24)
                    cursor.execute("""
                        UPDATE DailyItemUsage 
                        SET BlockedUntil = %s 
                        WHERE UserID = %s AND ItemID = %s AND UsageDate = CURRENT_DATE
                    """, (blocked_until, user_id, shield_item_group_id))
                    return 'blocked_start', 86400
                else:
                    # Incrementar usos
                    new_count = count + 1
                    blocked_until = None
                    if new_count >= 3:
                        blocked_until = datetime.now() + timedelta(hours=24)
                    
                    cursor.execute("""
                        UPDATE DailyItemUsage 
                        SET UsageCount = %s, BlockedUntil = %s
                        WHERE UserID = %s AND ItemID = %s AND UsageDate = CURRENT_DATE
                    """, (new_count, blocked_until, user_id, shield_item_group_id))
                    
                    if new_count >= 3:
                        return 'blocked_start', 86400
                    return 'ok', None
            else:
                # Primer uso del día
                cursor.execute("""
                    INSERT INTO DailyItemUsage (UserID, ItemID, UsageDate, UsageCount) 
                    VALUES (%s, %s, CURRENT_DATE, 1)
                """, (user_id, shield_item_group_id))
                return 'ok', None
    except Exception as e:
        logger.error(f"Error comprobando cooldown de escudos: {e}", exc_info=e)
        return 'error', None


# Funciones para el sistema de dificultad dinámica
def get_user_game_stats(user_id):
    """Obtener estadísticas de juego del usuario."""
    with db_cursor() as cursor:
        cursor.execute("""
            SELECT TotalGamesPlayed, TotalWins, TotalLosses, WinRate, 
                   HotStreak, ColdStreak, RiskProfile, DifficultyLevel
            FROM UserGameStats WHERE UserID = %s
        """, (user_id,))
        row = cursor.fetchone()
        if row:
            return {
                'total_games': row[0] or 0,
                'total_wins': row[1] or 0,
                'total_losses': row[2] or 0,
                'win_rate': row[3] or 0.0,
                'hot_streak': row[4] or 0,
                'cold_streak': row[5] or 0,
                'risk_profile': row[6] or 'BALANCED',
                'difficulty_level': row[7] or 0.0
            }
    return None

def record_game_result(user_id, game_type, bet_amount, result, win_amount, difficulty_applied, user_balance, cursor=None):
    """Registrar resultado de un juego para el sistema de dificultad, sincronizando todas las tablas de estadísticas."""
    from datetime import datetime
    is_win = result.lower() in ['win', 'victory', 'won', 'ganaste', 'ganador']
    result_str = 'win' if is_win else 'loss'
    
    if cursor is not None:
        return _record_game_result_inner(cursor, user_id, game_type, bet_amount, result, win_amount, difficulty_applied, user_balance, result_str, is_win)
        
    with db_cursor() as cursor:
        return _record_game_result_inner(cursor, user_id, game_type, bet_amount, result, win_amount, difficulty_applied, user_balance, result_str, is_win)

def _record_game_result_inner(cursor, user_id, game_type, bet_amount, result, win_amount, difficulty_applied, user_balance, result_str, is_win):
        from datetime import datetime
        # Acumular un pozo constante del 2% de la apuesta para el loto si no es un juego PvP
        if game_type not in {'coinflip_duel', 'russian_roulette', 'liars_dice', 'rps', 'horse_race'}:
            contribution = int(bet_amount * 0.02)
            if contribution > 0:
                cursor.execute("""
                    UPDATE LotteryState 
                    SET JackpotPool = JackpotPool + %s 
                    WHERE ID = 1
                """, (contribution,))

        # === 1. Tablas Legacy (GameHistory y UserGameStats) ===
        # Registrar en GameHistory
        cursor.execute("""
            INSERT INTO GameHistory 
            (UserID, GameType, BetAmount, Result, WinAmount, Timestamp, DifficultyApplied, UserBalance)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """, (user_id, game_type, bet_amount, result_str.upper(), win_amount, datetime.now(), difficulty_applied, user_balance))
        
        # Initialize default risk profile once for consistency
        risk_profile = 'BALANCED'

        # Obtener estadísticas de UserGameStats
        cursor.execute("""
            SELECT TotalGamesPlayed, TotalWins, TotalLosses, TotalAmountBet, TotalAmountWon, WinRate, AvgBetSize, HotStreak, ColdStreak, RiskProfile, DifficultyLevel 
            FROM UserGameStats WHERE UserID = %s
        """, (user_id,))
        stats = cursor.fetchone()
        
        if not stats:
            # Crear nuevas estadísticas
            new_games = 1
            new_wins = 1 if is_win else 0
            new_losses = 0 if is_win else 1
            new_bet_total = float(bet_amount)
            new_won_total = float(win_amount)
            new_win_rate = 1.0 if is_win else 0.0
            new_avg_bet = float(bet_amount)
            hot_streak = 1 if is_win else 0
            cold_streak = 0 if is_win else 1
            risk_profile = 'BALANCED'
            
            cursor.execute("""
                INSERT INTO UserGameStats 
                (UserID, TotalGamesPlayed, TotalWins, TotalLosses, TotalAmountBet, 
                 TotalAmountWon, WinRate, AvgBetSize, LastGameTime, 
                 HotStreak, ColdStreak, RiskProfile, DifficultyLevel)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (user_id, new_games, new_wins, new_losses, new_bet_total, 
                  new_won_total, new_win_rate, new_avg_bet, datetime.now(), 
                  hot_streak, cold_streak, risk_profile, difficulty_applied))
        else:
            # Actualizar estadísticas existentes
            new_games = stats[0] + 1
            new_wins = stats[1] + (1 if is_win else 0)
            new_losses = stats[2] + (0 if is_win else 1)
            new_bet_total = stats[3] + bet_amount
            new_won_total = stats[4] + win_amount
            new_win_rate = new_wins / new_games if new_games > 0 else 0.0
            new_avg_bet = new_bet_total / new_games if new_games > 0 else 0.0
            
            hot_streak = stats[7] if stats[7] is not None else 0
            cold_streak = stats[8] if stats[8] is not None else 0
            
            if is_win:
                hot_streak += 1
                cold_streak = 0
            else:
                cold_streak += 1
                hot_streak = 0
                
            risk_profile = calculate_risk_profile(new_avg_bet, new_win_rate, hot_streak, cold_streak)
            
            cursor.execute("""
                UPDATE UserGameStats SET
                    TotalGamesPlayed = %s, TotalWins = %s, TotalLosses = %s,
                    TotalAmountBet = %s, TotalAmountWon = %s, WinRate = %s,
                    AvgBetSize = %s, LastGameTime = %s,
                    HotStreak = %s, ColdStreak = %s, RiskProfile = %s, DifficultyLevel = %s
                WHERE UserID = %s
            """, (new_games, new_wins, new_losses, new_bet_total, new_won_total,
                  new_win_rate, new_avg_bet, datetime.now(), hot_streak, cold_streak, 
                  risk_profile, difficulty_applied, user_id))

        # === 2. Tablas del Sistema de Dificultad Dinámica (GameResults y DifficultyStats) ===
        # Registrar en GameResults
        cursor.execute("""
            INSERT INTO GameResults (UserID, GameType, BetAmount, Result, Winnings, DifficultyModifier, Balance)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, (user_id, game_type, bet_amount, result_str, win_amount, difficulty_applied, user_balance))
        
        # Obtener estadísticas de DifficultyStats
        cursor.execute("""
            SELECT TotalGames, WinRate, HotStreak, ColdStreak, AvgBet
            FROM DifficultyStats WHERE UserID = %s
        """, (user_id,))
        diff_stats = cursor.fetchone()
        
        if not diff_stats:
            cursor.execute("""
                INSERT INTO DifficultyStats (UserID, TotalGames, WinRate, HotStreak, ColdStreak, AvgBet, RiskProfile)
                VALUES (%s, 1, %s, %s, %s, %s, %s)
            """, (user_id, 1.0 if is_win else 0.0, 1 if is_win else 0, 0 if is_win else 1, float(bet_amount), risk_profile))
        else:
            d_total_games, d_win_rate, d_hot_streak, d_cold_streak, d_avg_bet = diff_stats
            
            d_new_games = d_total_games + 1
            d_new_win_rate = (d_win_rate * d_total_games + (1 if is_win else 0)) / d_new_games
            d_new_avg_bet = (d_avg_bet * d_total_games + bet_amount) / d_new_games
            
            if is_win:
                d_new_hot_streak = d_hot_streak + 1
                d_new_cold_streak = 0
            else:
                d_new_hot_streak = 0
                d_new_cold_streak = d_cold_streak + 1
                
            cursor.execute("""
                UPDATE DifficultyStats 
                SET TotalGames = %s, WinRate = %s, HotStreak = %s, ColdStreak = %s, 
                    AvgBet = %s, RiskProfile = %s, LastUpdate = CURRENT_TIMESTAMP
                WHERE UserID = %s
            """, (d_new_games, d_new_win_rate, d_new_hot_streak, d_new_cold_streak, 
                  d_new_avg_bet, risk_profile, user_id))

        # === 3. Progreso de Apostador (GamblerProgress) ===
        if bet_amount >= 25:
            base_xp = 0
            if bet_amount >= 10000: base_xp = 12
            elif bet_amount >= 5000: base_xp = 9
            elif bet_amount >= 2500: base_xp = 7
            elif bet_amount >= 1000: base_xp = 5
            elif bet_amount >= 500: base_xp = 3
            elif bet_amount >= 100: base_xp = 2
            else: base_xp = 1
            
            rtp = win_amount / bet_amount
            rtp_mod = 1.0
            if rtp < 0.25: rtp_mod = 1.30
            elif rtp < 0.75: rtp_mod = 1.15
            elif rtp < 1.25: rtp_mod = 1.00
            elif rtp < 2.00: rtp_mod = 0.90
            else: rtp_mod = 0.75
            
            xp_earned = max(1, round(base_xp * rtp_mod))
            
            cursor.execute("SELECT GamblerLevel, GamblerXP, TotalValidBets, TotalBetVolume FROM GamblerProgress WHERE UserID = %s", (user_id,))
            gp_row = cursor.fetchone()
            
            if not gp_row:
                g_level, g_xp, g_bets, g_vol = 1, xp_earned, 1, bet_amount
                cursor.execute("""
                    INSERT INTO GamblerProgress (UserID, GamblerLevel, GamblerXP, TotalValidBets, TotalBetVolume) 
                    VALUES (%s, %s, %s, %s, %s)
                """, (user_id, g_level, g_xp, g_bets, g_vol))
            else:
                g_level, g_xp, g_bets, g_vol = gp_row
                g_xp += xp_earned
                g_bets += 1
                g_vol += bet_amount
                
                # Subir de nivel
                leveled_up = False
                while g_level < 50:
                    req_xp = 40 + (g_level - 1) * 15
                    if g_xp >= req_xp:
                        g_xp -= req_xp
                        g_level += 1
                        leveled_up = True
                    else:
                        break
                
                if leveled_up:
                    cursor.execute("""
                        UPDATE GamblerProgress 
                        SET GamblerLevel = %s, GamblerXP = %s, TotalValidBets = %s, TotalBetVolume = %s, LastLevelUpAt = CURRENT_TIMESTAMP
                        WHERE UserID = %s
                    """, (g_level, g_xp, g_bets, g_vol, user_id))
                else:
                    cursor.execute("""
                        UPDATE GamblerProgress 
                        SET GamblerLevel = %s, GamblerXP = %s, TotalValidBets = %s, TotalBetVolume = %s
                        WHERE UserID = %s
                    """, (g_level, g_xp, g_bets, g_vol, user_id))
        else:
            # Aunque la apuesta sea menor a 25, necesitamos las stats básicas para los triggers.
            cursor.execute("SELECT GamblerLevel, GamblerXP, TotalValidBets, TotalBetVolume FROM GamblerProgress WHERE UserID = %s", (user_id,))
            gp_row = cursor.fetchone()
            if not gp_row:
                g_level, g_xp, g_bets, g_vol = 1, 0, 0, 0
            else:
                g_level, g_xp, g_bets, g_vol = gp_row


def calculate_risk_profile(avg_bet, win_rate, hot_streak, cold_streak):
    """Calcular el perfil de riesgo del usuario."""
    if avg_bet < 100 and win_rate < 0.4:
        return 'CONSERVATIVE'
    elif avg_bet > 500 or hot_streak > 5 or cold_streak > 8:
        return 'AGGRESSIVE'
    else:
        return 'BALANCED'

def get_recent_game_history(user_id, hours=24, limit=20):
    """Obtener historial reciente de juegos."""
    with db_cursor() as cursor:
        cursor.execute("""
            SELECT GameType, BetAmount, Result, WinAmount, Timestamp, DifficultyApplied
            FROM GameHistory 
            WHERE UserID = %s AND Timestamp >= NOW() - %s * INTERVAL '1 hour'
            ORDER BY Timestamp DESC
            LIMIT %s
        """, (user_id, hours, limit))
        
        games = []
        for row in cursor.fetchall():
            games.append({
                'game_type': row[0],
                'bet_amount': row[1],
                'result': row[2],
                'win_amount': row[3],
                'timestamp': row[4],
                'difficulty_applied': row[5]
            })
        return games

def claim_daily(user_id):
    """
    Intenta reclamar la recompensa diaria para el usuario.
    Retorna una tupla (success, data, streak, balance)
    - success: bool (True si se pudo reclamar, False si ya la reclamó hoy)
    - data: int si success=True (recompensa ganada), timedelta si success=False (tiempo restante)
    - streak: int (racha de días)
    - balance: int (nuevo saldo del usuario)
    """
    from datetime import datetime, timedelta
    
    with db_cursor() as cursor:
        cursor.execute("""
            INSERT INTO Users (UserID, Balance, LastLogin, Streak)
            VALUES (%s, 500, NULL, 0)
            ON CONFLICT (UserID) DO NOTHING
        """, (user_id,))
        cursor.execute(
            "SELECT LastLogin, Streak, Balance FROM Users WHERE UserID = %s FOR UPDATE",
            (user_id,),
        )
        row = cursor.fetchone()
        
        today = datetime.now().date()
        
        if row:
            last_login, streak, balance = row[0], row[1], row[2]
            if isinstance(last_login, datetime):
                last_login = last_login.date()
            elif last_login:
                try:
                    last_login = datetime.strptime(str(last_login).split(' ')[0], '%Y-%m-%d').date()
                except Exception as exc:
                    logger.warning(
                        "No se pudo parsear LastLogin para user_id=%s (valor=%r): %s",
                        user_id,
                        last_login,
                        exc
                    )
                    last_login = None
        else:
            last_login, streak, balance = None, 0, 500
            
        if last_login == today:
            now = datetime.now()
            next_day = datetime.combine(today + timedelta(days=1), datetime.min.time())
            time_remaining = next_day - now
            return False, time_remaining, streak, balance
            
        if last_login and (today - last_login).days == 1:
            streak += 1
        else:
            streak = 1
            
        reward = min(100 * streak, 1000)
        new_balance = (balance or 0) + reward
        
        cursor.execute("""
            UPDATE Users SET LastLogin = %s, Streak = %s, Balance = %s WHERE UserID = %s
        """, (today, streak, new_balance, user_id))
        
        # Registrar la transacción
        cursor.execute("""
            INSERT INTO Transactions (UserID, Amount, TransactionType, Date)
            VALUES (%s, %s, %s, %s)
        """, (user_id, reward, "Recompensa diaria", datetime.now()))
        
        return True, reward, streak, new_balance

# Funciones del sistema de energía
def init_energia_db():
    """Inicializar tabla de energía en SQL Server / PostgreSQL."""
    with db_cursor() as cursor:
        # En PostgreSQL consultamos 'users' en minúsculas en el catálogo del sistema
        cursor.execute("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = 'users'
        """)
        columns = [row[0].lower() for row in cursor.fetchall()]
        
        if 'energia' not in columns:
            cursor.execute("ALTER TABLE Users ADD COLUMN Energia INT DEFAULT 100")
            logger.info("Columna 'Energia' agregada a la tabla Users")
            
        if 'ultimarecarga' not in columns:
            cursor.execute("ALTER TABLE Users ADD COLUMN UltimaRecarga BIGINT DEFAULT 0")
            logger.info("Columna 'UltimaRecarga' agregada a la tabla Users")
            
        import time
        tiempo_actual = int(time.time())
        cursor.execute("""
            UPDATE Users 
            SET Energia = 100, UltimaRecarga = %s 
            WHERE Energia IS NULL OR UltimaRecarga IS NULL
        """, (tiempo_actual,))

def _recalculate_energia(cursor, user_id: int, energia_actual: Optional[int], ultima_recarga: Optional[int]) -> int:
    """
    Recalcula la energía del usuario en base al tiempo transcurrido desde la última recarga.
    Esta función encapsula la lógica de recarga automática para evitar duplicaciones y
    divergencias de estado entre get_energia y consumir_energia.
    """
    import time
    tiempo_actual = int(time.time())

    if energia_actual is None or ultima_recarga is None:
        energia_actual = 100
        ultima_recarga = tiempo_actual
        cursor.execute("UPDATE Users SET Energia = %s, UltimaRecarga = %s WHERE UserID = %s", (energia_actual, ultima_recarga, user_id))
        return energia_actual

    if energia_actual >= 100:
        return energia_actual

    tiempo_transcurrido = tiempo_actual - ultima_recarga
    puntos_recarga = tiempo_transcurrido // 180
    
    if puntos_recarga > 0:
        energia_actual = min(100, energia_actual + puntos_recarga)
        ultima_recarga = ultima_recarga + (puntos_recarga * 180)
        cursor.execute("UPDATE Users SET Energia = %s, UltimaRecarga = %s WHERE UserID = %s", (energia_actual, ultima_recarga, user_id))

    return energia_actual


def get_energia(user_id: int) -> int:
    """Obtener la energía actual del usuario, aplicando recarga automática."""
    import time
    with db_cursor() as cursor:
        cursor.execute("SELECT Energia, UltimaRecarga FROM Users WHERE UserID = %s", (user_id,))
        result = cursor.fetchone()
        
        if not result:
            ensure_user(user_id)
            tiempo_actual = int(time.time())
            cursor.execute("UPDATE Users SET Energia = 100, UltimaRecarga = %s WHERE UserID = %s", (tiempo_actual, user_id))
            return 100
        
        energia_actual, ultima_recarga = result[0], result[1]
        return _recalculate_energia(cursor, user_id, energia_actual, ultima_recarga)


def consumir_energia(user_id: int, cantidad: int) -> bool:
    """Consume energía de forma atómica. Retorna True si se descontó correctamente."""
    import time
    ensure_user(user_id)
    with db_cursor() as cursor:
        cursor.execute(
            "SELECT Energia, UltimaRecarga FROM Users WHERE UserID = %s FOR UPDATE",
            (user_id,),
        )
        row = cursor.fetchone()
        if not row:
            return False

        energia_actual, ultima_recarga = row[0], row[1]
        energia_actual = _recalculate_energia(cursor, user_id, energia_actual, ultima_recarga)

        if energia_actual < cantidad:
            return False

        tiempo_actual = int(time.time())
        cursor.execute(
            "UPDATE Users SET Energia = %s, UltimaRecarga = %s WHERE UserID = %s",
            (energia_actual - cantidad, tiempo_actual, user_id),
        )
        return True

def set_energia(user_id: int, nueva_energia: int):
    """Establecer la energía del usuario."""
    import time
    ensure_user(user_id)
    nueva_energia = max(0, min(100, nueva_energia))
    tiempo_actual = int(time.time())
    with db_cursor() as cursor:
        cursor.execute("UPDATE Users SET Energia = %s, UltimaRecarga = %s WHERE UserID = %s", (nueva_energia, tiempo_actual, user_id))

def tiempo_hasta_recarga_completa(user_id: int) -> int:
    """Calcular minutos hasta que la energía esté completamente recargada."""
    energia_actual = get_energia(user_id)
    if energia_actual >= 100:
        return 0
    puntos_faltantes = 100 - energia_actual
    return puntos_faltantes * 3

def get_energia_info(user_id: int) -> dict:
    """Obtener información completa sobre la energía del usuario."""
    energia_actual = get_energia(user_id)
    tiempo_recarga = tiempo_hasta_recarga_completa(user_id)
    return {
        'energia_actual': energia_actual,
        'energia_maxima': 100,
        'tiempo_recarga_completa': tiempo_recarga,
        'porcentaje': energia_actual,
        'puede_trabajar': energia_actual >= 15
    }

def fix_timestamps_energia():
    """Arreglar timestamps de energía que puedan estar en el futuro o ser inválidos."""
    import time
    tiempo_actual = int(time.time())
    with db_cursor() as cursor:
        cursor.execute("""
            UPDATE Users 
            SET UltimaRecarga = %s 
            WHERE UltimaRecarga > %s OR UltimaRecarga < %s
        """, (tiempo_actual, tiempo_actual, tiempo_actual - 86400 * 30))



def get_provably_fair_seeds(user_id: int):
    """Obtiene las semillas actuales del usuario, o las genera si no existen."""
    with db_cursor() as cursor:
        cursor.execute("SELECT ServerSeed, ClientSeed, Nonce FROM ProvablyFairSeeds WHERE UserID = %s", (user_id,))
        row = cursor.fetchone()
        if row:
            return {"server_seed": row[0], "client_seed": row[1], "nonce": row[2]}
        
        # Si no existe, generamos semillas iniciales
        import secrets
        server_seed = secrets.token_hex(32)
        client_seed = secrets.token_hex(16)
        
        cursor.execute("""
            INSERT INTO ProvablyFairSeeds (UserID, ServerSeed, ClientSeed, Nonce)
            VALUES (%s, %s, %s, 0)
        """, (user_id, server_seed, client_seed))
        return {"server_seed": server_seed, "client_seed": client_seed, "nonce": 0}
        
def rotate_provably_fair_seeds(user_id: int, new_client_seed: str = None):
    """Rota la semilla del servidor. El usuario puede proveer un nuevo client seed opcional."""
    import secrets
    current = get_provably_fair_seeds(user_id)
    
    new_server_seed = secrets.token_hex(32)
    new_client = new_client_seed if new_client_seed else current["client_seed"]
    
    with db_cursor() as cursor:
        cursor.execute("""
            UPDATE ProvablyFairSeeds
            SET PastServerSeed = ServerSeed,
                PastClientSeed = ClientSeed,
                PastNonce = Nonce,
                ServerSeed = %s,
                ClientSeed = %s,
                Nonce = 0
            WHERE UserID = %s
        """, (new_server_seed, new_client, user_id))
        
    return {"server_seed": new_server_seed, "client_seed": new_client, "nonce": 0, "past_server_seed": current["server_seed"]}

def advance_provably_fair_nonce(user_id: int):
    """Avanza el nonce en 1. Debe llamarse CADA VEZ que se genera un resultado en un juego."""
    with db_cursor() as cursor:
        cursor.execute("""
            UPDATE ProvablyFairSeeds
            SET Nonce = Nonce + 1
            WHERE UserID = %s
            RETURNING Nonce
        """, (user_id,))
        return cursor.fetchone()[0]

def save_multiplayer_game(game_id: str, game_type: str, state: dict):
    """Guarda el estado de un juego multijugador."""
    import json
    with db_cursor() as cursor:
        cursor.execute("""
            INSERT INTO ActiveMultiplayerGames (GameID, GameType, GameState, LastUpdate)
            VALUES (%s, %s, %s, CURRENT_TIMESTAMP)
            ON CONFLICT (GameID) DO UPDATE 
            SET GameState = EXCLUDED.GameState,
                LastUpdate = CURRENT_TIMESTAMP
        """, (game_id, game_type, json.dumps(state)))

def get_multiplayer_game(game_id: str):
    """Obtiene el estado de un juego multijugador."""
    import json
    with db_cursor() as cursor:
        cursor.execute("SELECT GameState FROM ActiveMultiplayerGames WHERE GameID = %s", (game_id,))
        row = cursor.fetchone()
        if not row:
            return None

        game_state = row[0]
        if isinstance(game_state, dict):
            return {
                "status": "ok",
                "state": game_state,
            }

        if isinstance(game_state, (str, bytes)):
            try:
                parsed_state = json.loads(game_state)
                return {
                    "status": "ok",
                    "state": parsed_state,
                }
            except (TypeError, ValueError) as exc:
                logger.warning(
                    "Error al parsear GameState para GameID %s: %s (valor=%r)",
                    game_id,
                    exc,
                    game_state,
                )
                return {
                    "status": "invalid_state",
                    "raw": game_state,
                    "error": str(exc),
                }

        logger.warning(
            "Tipo inesperado en GameState para GameID %s: %s (valor=%r)",
            game_id,
            type(game_state).__name__,
            game_state,
        )
        return {
            "status": "invalid_state",
            "raw": game_state,
            "error": "Unexpected data type",
        }

def delete_multiplayer_game(game_id: str):
    """Elimina un juego multijugador activo."""
    with db_cursor() as cursor:
        cursor.execute("DELETE FROM ActiveMultiplayerGames WHERE GameID = %s", (game_id,))

# ==========================================
# SISTEMA DE PETS
# ==========================================

def get_pet_catalog():
    """Obtiene todo el catálogo de mascotas disponibles."""
    with db_cursor() as cursor:
        cursor.execute("SELECT * FROM PetsCatalog WHERE Enabled = 1")
        columns = [desc[0] for desc in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]

def get_active_pet(user_id: int):
    """Obtiene la mascota activa del usuario con todos sus datos del catálogo."""
    with db_cursor() as cursor:
        cursor.execute("""
            SELECT up.*, pc.* 
            FROM UserPets up
            JOIN PetsCatalog pc ON up.PetID = pc.PetID
            WHERE up.UserID = %s AND up.IsActive = 1
        """, (user_id,))
        row = cursor.fetchone()
        if not row:
            return None
        columns = [desc[0] for desc in cursor.description]
        return dict(zip(columns, row))

def add_user_pet(user_id: int, pet_id: int):
    """Añade una mascota al usuario y la pone como activa automáticamente."""
    with db_cursor() as cursor:
        # Desactivar la mascota actual
        cursor.execute("UPDATE UserPets SET IsActive = 0 WHERE UserID = %s", (user_id,))
        # Insertar nueva
        cursor.execute("""
            INSERT INTO UserPets (UserID, PetID, IsActive, Loyalty, Mood, GamesWithOwner, WinsWithOwner, LossesWithOwner)
            VALUES (%s, %s, 1, 50, 'Feliz', 0, 0, 0)
            RETURNING UserPetID
        """, (user_id, pet_id))
        return cursor.fetchone()[0]

def remove_user_pet(user_id: int, user_pet_id: int):
    """Elimina una mascota del inventario (ej. cuando abandona al usuario)."""
    with db_cursor() as cursor:
        cursor.execute("DELETE FROM UserPets WHERE UserID = %s AND UserPetID = %s", (user_id, user_pet_id))

def rename_user_pet(user_id: int, user_pet_id: int, nickname):
    """Asigna o quita el apodo de una mascota del usuario. Devuelve (éxito, mensaje o apodo)."""
    if nickname is not None:
        nickname = nickname.strip()
        if not nickname:
            return False, "El nombre no puede estar vacío."
        if len(nickname) > 32:
            return False, "El nombre no puede superar 32 caracteres."
        if "\n" in nickname or "\r" in nickname:
            return False, "El nombre no puede contener saltos de línea."

    with db_cursor() as cursor:
        cursor.execute(
            "SELECT UserPetID FROM UserPets WHERE UserPetID = %s AND UserID = %s AND Status != 'Escapó'",
            (user_pet_id, user_id),
        )
        if not cursor.fetchone():
            return False, "No se encontró esa mascota en tu colección."

        cursor.execute(
            "UPDATE UserPets SET Nickname = %s WHERE UserPetID = %s AND UserID = %s",
            (nickname, user_pet_id, user_id),
        )
        return True, nickname or ""

def update_pet_stats(user_id: int, win: bool):
    """Actualiza las estadísticas de la mascota activa tras un juego de casino."""
    with db_cursor() as cursor:
        if win:
            cursor.execute("""
                UPDATE UserPets SET 
                GamesWithOwner = GamesWithOwner + 1,
                WinsWithOwner = WinsWithOwner + 1
                WHERE UserID = %s AND IsActive = 1
            """, (user_id,))
        else:
            cursor.execute("""
                UPDATE UserPets SET 
                GamesWithOwner = GamesWithOwner + 1,
                LossesWithOwner = LossesWithOwner + 1
                WHERE UserID = %s AND IsActive = 1
            """, (user_id,))


# --- SISTEMA DE FUSIÓN DE MASCOTAS ---

RARITY_UPGRADE = {
    "Normal": "Rara",
    "Rara": "Épica",
    "Épica": "Legendaria",
    "Legendaria": "Mítica",
    "Mítica": "Mítica",  # Mítica se queda en Mítica pero con boost
}

def get_fusionable_pets(user_id: int):
    """
    Busca mascotas que el usuario tiene 5+ duplicados (mismo PetID), excluyendo la mascota activa.
    Retorna lista de dicts: [{pet_id, name, emoji, rarity, count}, ...]
    """
    with db_cursor() as cursor:
        cursor.execute("""
            SELECT up.PetID, pc.Name, pc.Emoji, pc.Rarity, COUNT(*) as cnt
            FROM UserPets up
            JOIN PetsCatalog pc ON up.PetID = pc.PetID
            WHERE up.UserID = %s AND up.Status != 'Escapó' AND COALESCE(up.IsActive, 0) = 0
            GROUP BY up.PetID, pc.Name, pc.Emoji, pc.Rarity
            HAVING COUNT(*) >= 5
            ORDER BY pc.Rarity DESC, cnt DESC
        """, (user_id,))
        rows = cursor.fetchall()
        return [
            {"pet_id": r[0], "name": r[1], "emoji": r[2], "rarity": r[3], "count": r[4]}
            for r in rows
        ]


def fuse_pets(user_id: int, pet_id: int):
    """
    Fusiona 5 mascotas inactivas del mismo PetID en 1 mascota aleatoria de rareza superior.
    Retorna (success: bool, result: dict o str).
    result dict: {new_pet_name, new_pet_emoji, new_rarity, new_user_pet_id, flavor_text, is_mythic_boost}
    """
    with db_cursor() as cursor:
        # 1. Verificar que tiene al menos 5 del mismo PetID (excluyendo activa)
        cursor.execute("""
            SELECT up.UserPetID
            FROM UserPets up
            WHERE up.UserID = %s AND up.PetID = %s AND up.Status != 'Escapó' AND COALESCE(up.IsActive, 0) = 0
            ORDER BY up.Loyalty ASC
            LIMIT 5
        """, (user_id, pet_id))
        victims = cursor.fetchall()
        
        if len(victims) < 5:
            return False, "No tienes 5 mascotas de esta especie para fusionar."
        
        victim_ids = [v[0] for v in victims]
        
        # 2. Obtener rareza actual
        cursor.execute("SELECT Rarity FROM PetsCatalog WHERE PetID = %s", (pet_id,))
        rarity_row = cursor.fetchone()
        if not rarity_row:
            return False, "Especie no encontrada en el catálogo."
        
        current_rarity = rarity_row[0]
        target_rarity = RARITY_UPGRADE.get(current_rarity, current_rarity)
        is_mythic_boost = (current_rarity == "Mítica")
        
        # 3. Elegir mascota aleatoria de la rareza objetivo
        cursor.execute("""
            SELECT PetID, Name, Emoji, Rarity, FlavorText, EffectValue
            FROM PetsCatalog
            WHERE Rarity = %s AND Enabled = 1
            ORDER BY RANDOM() LIMIT 1
        """, (target_rarity,))
        new_pet_row = cursor.fetchone()
        
        if not new_pet_row:
            return False, f"No hay mascotas de rareza {target_rarity} disponibles en el catálogo."
        
        new_pet_id, new_name, new_emoji, new_rarity, flavor, eff_val = new_pet_row
        
        # 4. Eliminar las 5 mascotas sacrificadas
        for vid in victim_ids:
            cursor.execute("DELETE FROM UserPets WHERE UserPetID = %s AND UserID = %s", (vid, user_id))
        
        # 5. Crear la nueva mascota
        base_loyalty = 75 if is_mythic_boost else 50
        cursor.execute("""
            INSERT INTO UserPets (UserID, PetID, IsActive, Loyalty, Mood, GamesWithOwner, WinsWithOwner, LossesWithOwner, Status)
            VALUES (%s, %s, 0, %s, 'Feliz', 0, 0, 0, 'Normal')
            RETURNING UserPetID
        """, (user_id, new_pet_id, base_loyalty))
        new_up_id = cursor.fetchone()[0]
        
        # 6. Registrar evento
        cursor.execute("""
            INSERT INTO UserPetEvents (UserID, PetID, EventType, Details)
            VALUES (%s, %s, 'fusion', %s)
        """, (user_id, new_pet_id, f"Fusionó 5x PetID={pet_id} ({current_rarity}) → {new_name} ({new_rarity})"))
        
        return True, {
            "new_pet_name": new_name,
            "new_pet_emoji": new_emoji,
            "new_rarity": new_rarity,
            "new_user_pet_id": new_up_id,
            "flavor_text": flavor,
            "is_mythic_boost": is_mythic_boost,
            "sacrificed_count": 5,
            "old_rarity": current_rarity,
        }

def get_all_minas():
    """Obtiene todas las minas activas en todos los canales."""
    with db_cursor() as cursor:
        cursor.execute("SELECT CanalID, Cantidad FROM MinasActivas WHERE Cantidad > 0")
        return {row[0]: row[1] for row in cursor.fetchall()}

def set_minas_canal(canal_id, cantidad):
    """Establece la cantidad de minas en un canal específico."""
    with db_cursor() as cursor:
        if cantidad <= 0:
            cursor.execute("DELETE FROM MinasActivas WHERE CanalID = %s", (canal_id,))
        else:
            cursor.execute("""
                INSERT INTO MinasActivas (CanalID, Cantidad) VALUES (%s, %s)
                ON CONFLICT (CanalID) DO UPDATE SET Cantidad = EXCLUDED.Cantidad
            """, (canal_id, cantidad))

def registrar_mina_pisada(user_id):
    """Registra que un usuario pisó una mina."""
    with db_cursor() as cursor:
        cursor.execute("""
            INSERT INTO MinaStats (UserID, MinasPisadas) VALUES (%s, 1)
            ON CONFLICT (UserID) DO UPDATE SET MinasPisadas = MinaStats.MinasPisadas + 1
        """, (user_id,))

def get_top_minas(limit=10, member_ids=None):
    """Obtiene el top de usuarios que más minas han pisado."""
    if member_ids is not None and len(member_ids) == 0:
        return []

    with db_cursor() as cursor:
        base_query = """
            SELECT m.UserID, m.MinasPisadas, u.UserName
            FROM MinaStats m
            LEFT JOIN Users u ON m.UserID = u.UserID
        """

        params = []

        if member_ids:
            if len(member_ids) == 1:
                query = base_query + """
            WHERE m.UserID = %s
            ORDER BY m.MinasPisadas DESC
            LIMIT %s
                """
                params = [member_ids[0], limit]
            else:
                placeholders = ", ".join(["%s"] * len(member_ids))
                query = base_query + f"""
            WHERE m.UserID IN ({placeholders})
            ORDER BY m.MinasPisadas DESC
            LIMIT %s
                """
                params = list(member_ids) + [limit]
        else:
            query = base_query + """
            ORDER BY m.MinasPisadas DESC
            LIMIT %s
            """
            params = [limit]

        cursor.execute(query, params)
        return cursor.fetchall()

def get_user_ticket_count(user_id):
    """Obtiene el número de boletos activos que posee el usuario para el sorteo actual."""
    with db_cursor() as cursor:
        cursor.execute("SELECT COUNT(*) FROM LotteryTickets WHERE UserID = %s", (user_id,))
        row = cursor.fetchone()
        return row[0] if row else 0

def comprar_boleto_db(user_id, numbers, cost, max_tickets=5):
    """Compra un boleto de loto de forma atómica con límite diario."""
    with db_cursor() as cursor:
        cursor.execute("SELECT COUNT(*) FROM LotteryTickets WHERE UserID = %s", (user_id,))
        if cursor.fetchone()[0] >= max_tickets:
            return False, 0

        cursor.execute("""
            UPDATE Users 
            SET Balance = Balance - %s 
            WHERE UserID = %s AND Balance >= %s
            RETURNING Balance
        """, (cost, user_id, cost))
        row = cursor.fetchone()
        if not row:
            return False, 0
        
        new_balance = row[0]
        
        cursor.execute("""
            INSERT INTO LotteryTickets (UserID, Numbers)
            VALUES (%s, %s)
        """, (user_id, numbers))
        
        cursor.execute("""
            UPDATE LotteryState 
            SET JackpotPool = JackpotPool + %s 
            WHERE ID = 1
        """, (cost,))
        
        return True, new_balance

def comprar_item_tienda(user_id, item_id, precio, expiry):
    """Compra un ítem de la tienda de forma atómica (saldo + inventario).
    Usa el ID primario para evitar actualizar múltiples filas duplicadas."""
    with db_cursor() as cursor:
        cursor.execute("""
            UPDATE Users
            SET Balance = Balance - %s
            WHERE UserID = %s AND Balance >= %s
            RETURNING Balance
        """, (precio, user_id, precio))
        if not cursor.fetchone():
            return "no_balance"

        # Buscar UNA fila activa por ID primario
        cursor.execute("""
            SELECT ID FROM UserItems 
            WHERE UserID = %s AND ItemID = %s AND Expiry > NOW() AND Used = 0
            ORDER BY ID ASC LIMIT 1
        """, (user_id, item_id))
        row = cursor.fetchone()
        if row:
            # Incrementar SOLO esa fila específica
            cursor.execute("""
                UPDATE UserItems
                SET Quantity = Quantity + 1
                WHERE ID = %s
            """, (row[0],))
        else:
            cursor.execute("""
                INSERT INTO UserItems (UserID, ItemID, Quantity, Expiry, Used)
                VALUES (%s, %s, 1, %s, 0)
            """, (user_id, item_id, expiry))

        return "ok"

def get_lottery_pool():
    """Obtiene el pozo acumulado actual de la lotería."""
    with db_cursor() as cursor:
        cursor.execute("SELECT JackpotPool FROM LotteryState WHERE ID = 1")
        row = cursor.fetchone()
        return row[0] if row else 10000

def add_to_lottery_pool(amount):
    """Suma monedas directamente al pozo de la lotería."""
    with db_cursor() as cursor:
        cursor.execute("""
            UPDATE LotteryState 
            SET JackpotPool = JackpotPool + %s 
            WHERE ID = 1 
            RETURNING JackpotPool
        """, (amount,))
        row = cursor.fetchone()
        return row[0] if row else 10000

def get_active_tickets():
    """Retorna los boletos activos para el sorteo de hoy."""
    with db_cursor() as cursor:
        cursor.execute("SELECT UserID, Numbers FROM LotteryTickets")
        return cursor.fetchall()

def get_lottery_state():
    """Obtiene el estado actual completo de la lotería."""
    with db_cursor() as cursor:
        cursor.execute("SELECT JackpotPool, LastDrawDate, NextDrawDate FROM LotteryState WHERE ID = 1")
        row = cursor.fetchone()
        if row:
            return {
                'pool': row[0],
                'last_draw': row[1],
                'next_draw': row[2]
            }
        return {'pool': 10000, 'last_draw': None, 'next_draw': None}

def process_lottery_draw_db(winners_data, new_pool_amount, last_draw, next_draw):
    """Procesa el sorteo de lotería: paga premios, limpia boletos y actualiza estado."""
    with db_cursor() as cursor:
        # Pagar a ganadores e insertar transacciones
        for user_id, amount, matches in winners_data:
            if amount > 0:
                cursor.execute("""
                    INSERT INTO Users (UserID, Balance) VALUES (%s, %s)
                    ON CONFLICT (UserID) DO UPDATE SET Balance = Users.Balance + EXCLUDED.Balance
                """, (user_id, amount))
                
                cursor.execute("""
                    INSERT INTO Transactions (UserID, Amount, TransactionType)
                    VALUES (%s, %s, %s)
                """, (user_id, amount, f"Premio Loto: {matches} aciertos"))
        
        # Eliminar todos los boletos ya sorteados
        cursor.execute("DELETE FROM LotteryTickets")
        
        # Actualizar estado de la lotería
        cursor.execute("""
            UPDATE LotteryState 
            SET JackpotPool = %s, LastDrawDate = %s, NextDrawDate = %s 
            WHERE ID = 1
        """, (new_pool_amount, last_draw, next_draw))

def init_db():
    """
    Inicializa la base de datos PostgreSQL:
    1. Verifica si la base de datos especificada existe, si no la crea.
    2. Crea todas las tablas necesarias de la aplicación si no existen.
    """
    import psycopg2
    from psycopg2 import sql
    from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT

    # 1. Verificar/Crear la base de datos desde la base administrativa.
    # Evita conectarse primero a una DB inexistente: en Windows, PostgreSQL puede
    # devolver ese error en CP1252 y psycopg2 intenta decodificarlo como UTF-8.
    try:
        conn_admin = _connect_direct('postgres')
        conn_admin.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
        try:
            with conn_admin.cursor() as cursor:
                cursor.execute(
                    "SELECT 1 FROM pg_database WHERE datname = %s",
                    (database,)
                )
                if cursor.fetchone():
                    logger.info(f"Base de datos '{database}' encontrada.")
                else:
                    logger.info(f"Base de datos '{database}' no existe. Creandola...")
                    cursor.execute(
                        sql.SQL("CREATE DATABASE {}").format(
                             sql.Identifier(database)
                        )
                    )
                    logger.info(f"Base de datos '{database}' creada exitosamente.")
        finally:
            conn_admin.close()
    except Exception as e:
        logger.error(f"Error al verificar/crear la base de datos: {e}")
        raise

    # 2. Conectar a la base de datos y crear todas las tablas
    logger.info(f"🔄 Inicializando tablas en la base de datos '{database}'...")
    try:
        with db_cursor() as cursor:
            # Tabla: Users
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS Users (
                    UserID BIGINT PRIMARY KEY,
                    Balance BIGINT DEFAULT 500,
                    LastLogin TIMESTAMP,
                    Streak INT DEFAULT 0,
                    UserName VARCHAR(100),
                    StartDate DATE,
                    Energia INT DEFAULT 100,
                    UltimaRecarga BIGINT DEFAULT 0
                )
            """)
            cursor.execute("ALTER TABLE Users ADD COLUMN IF NOT EXISTS BankBalance BIGINT DEFAULT 0")
            cursor.execute("ALTER TABLE Users ADD COLUMN IF NOT EXISTS SaldoReferenciaCasino BIGINT DEFAULT NULL")
            cursor.execute("ALTER TABLE Users ADD COLUMN IF NOT EXISTS SaldoReferenciaTimestamp TIMESTAMP DEFAULT NULL")
            cursor.execute("ALTER TABLE Users ADD COLUMN IF NOT EXISTS CasinoBloqueadoHasta TIMESTAMP DEFAULT NULL")
            
            # --- TABLAS DEL PLAN MAESTRO DE PETS ---
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS PetsCatalog (
                    PetID SERIAL PRIMARY KEY,
                    Name VARCHAR(100) NOT NULL UNIQUE,
                    Rarity VARCHAR(20) NOT NULL,
                    Emoji VARCHAR(50) NOT NULL,
                    Family VARCHAR(50),
                    Temperament VARCHAR(50),
                    EffectType VARCHAR(50),
                    EffectValue DOUBLE PRECISION,
                    EffectChance DOUBLE PRECISION,
                    EffectCap INT,
                    FavoriteGame VARCHAR(50),
                    EncounterType VARCHAR(50),
                    CaptureType VARCHAR(50),
                    CaptureConfig INT,
                    BaseLeaveChance DOUBLE PRECISION,
                    FlavorText TEXT,
                    Enabled INT DEFAULT 1
                )
            """)

            # --- AUTO-SEEDING DE LAS 50 MASCOTAS ---
            pets_seed_50 = [
                ("Ratón de Casino", "Normal", "🐭", "Roedor", "Curioso", "proc_universal", 0.04, 0.14, 120, "any", "volume", "auto", 0, 0.20, "Se alimenta de las monedas caídas en las ranuras."),
                ("Conejo de Cobre", "Normal", "🐰", "Mamífero", "Asustadizo", "multiplier", 1.02, 1.0, 0, "any", "hot_streak", "win_next_5", 1, 0.25, "Su pata de la suerte es más que un mito."),
                ("Buitre del Fondo", "Normal", "🦅", "Ave", "Oportunista", "proc_derrota", 0.06, 0.20, 180, "any", "cold_streak", "pay", 300, 0.15, "Solo aparece cuando hueles a desesperación."),
                ("Gato de la Fortuna", "Normal", "🐱", "Felino", "Tranquilo", "multiplier", 1.03, 1.0, 0, "trabajo", "volume", "auto", 0, 0.20, "Mueve su pata atrayendo moneditas y buena fortuna."),
                ("Dron Chismoso", "Normal", "🛰️", "Tecnología", "Curioso", "proc_universal", 0.05, 0.10, 150, "robar", "volume", "auto", 0, 0.15, "Escanea saldos ajenos e informa de objetivos vulnerables."),
                ("Escarabajo Neón", "Normal", "🪲", "Insecto", "Brillante", "proc_universal", 0.03, 0.15, 100, "any", "volume", "auto", 0, 0.20, "Genera Balance continuo con la energía estática del casino."),
                ("Cuervo Transmisor", "Normal", "📡", "Tecnología", "Vigilante", "proc_universal", 0.04, 0.12, 130, "any", "volume", "auto", 0, 0.15, "Transmite alertas tempranas de movimientos sospechosos."),
                ("Abeja Obrera", "Normal", "🐝", "Insecto", "Trabajador", "multiplier", 1.05, 1.0, 0, "trabajo", "volume", "auto", 0, 0.20, "Aumenta la producción en todos los oficios manuales."),
                ("Pez Neón Flotante", "Normal", "🐠", "Marino", "Pacífico", "proc_universal", 0.04, 0.12, 140, "pesca", "volume", "auto", 0, 0.20, "Atrae especies de peces exóticos con su fulgor bioluminiscente."),
                ("Mapache Reciclador", "Normal", "🦝", "Mamífero", "Ingenioso", "proc_derrota", 0.10, 0.10, 200, "mines", "cold_streak", "auto", 0, 0.20, "Rebusca entre los restos para rescatar fichas perdidas."),

                ("Zorro de la Mesa Roja", "Rara", "🦊", "Mamífero", "Astuto", "proc_juego", 0.08, 0.15, 300, "coinflip", "specialized", "play_more", 3, 0.20, "Le encanta apostar a doble o nada."),
                ("Tortuga del Tesoro", "Rara", "🐢", "Piedra", "Conservador", "multiplier_safe", 1.03, 1.0, 0, "any", "wealth", "pay", 1500, 0.10, "Camina lento, pero su caparazón está forrado de oro."),
                ("Polilla de la Ruina", "Rara", "🦋", "Insecto", "Atraído por la luz", "proc_derrota", 0.10, 0.12, 500, "any", "cold_streak", "pay", 2000, 0.15, "Se alimenta del polvo de las billeteras vacías."),
                ("Búho Místico", "Rara", "🦉", "Ave", "Sabio", "proc_universal", 0.07, 0.15, 400, "any", "volume", "auto", 0, 0.15, "Sus ojos ven a través del destino y disipan debuffs."),
                ("Gólem de Obsidiana", "Rara", "🗿", "Piedra", "Resistente", "multiplier_safe", 1.04, 1.0, 0, "any", "wealth", "pay", 2500, 0.10, "Forjado en roca volcánica para absorber impactos y comisiones."),
                ("Ciber-Gato 9000", "Rara", "🤖", "Tecnología", "Calculador", "proc_juego", 0.10, 0.12, 350, "slots", "specialized", "auto", 0, 0.15, "Filtra algoritmos de las tragaperras para dar procs frecuentes."),
                ("Perro Biónico", "Rara", "🐕", "Tecnología", "Leal", "proc_universal", 0.06, 0.15, 300, "robar", "volume", "auto", 0, 0.15, "Guardián cibernético con sensor de presencia de ladrones."),
                ("Cerdito Gourmet", "Rara", "🐷", "Mamífero", "Glotón", "multiplier", 1.04, 1.0, 0, "any", "volume", "auto", 0, 0.15, "Potencia los efectos nutritivos de los consumibles."),
                ("Topo Minero", "Rara", "⛏️", "Roedor", "Trabajador", "proc_universal", 0.08, 0.12, 450, "mineria", "volume", "auto", 0, 0.15, "Excava túneles profundos en busca de gemas raras."),
                ("Sombra Errante", "Rara", "👻", "Sombra", "Furtivo", "proc_universal", 0.09, 0.14, 500, "robar", "specialized", "auto", 0, 0.15, "Se desliza inadvertida durante los asaltos nocturnos."),
                ("Murciélago Vampírico", "Rara", "🦇", "Mamífero", "Nocturno", "proc_universal", 0.08, 0.12, 400, "duelo", "volume", "auto", 0, 0.15, "Drena la energía del oponente en duelos de combate."),
                ("Salamandra de Fuego", "Rara", "🔥", "Reptil", "Ferviente", "proc_universal", 0.07, 0.15, 380, "any", "volume", "auto", 0, 0.15, "Resiste las llamas de las pérdidas continuas."),
                ("Medusa de Cristal", "Rara", "🪼", "Marino", "Reflejante", "proc_derrota", 0.12, 0.10, 600, "robar", "cold_streak", "auto", 0, 0.15, "Refleja los intentos de asalto con su veneno paralizante."),
                ("Panda Sabio", "Rara", "🐼", "Mamífero", "Pacífico", "multiplier_safe", 1.05, 1.0, 0, "any", "wealth", "auto", 0, 0.10, "Equilibra el chi financiero reduciendo multas bancarias."),
                ("Camaleón Ilusorio", "Rara", "🦎", "Reptil", "Evasivo", "proc_universal", 0.08, 0.14, 420, "any", "volume", "auto", 0, 0.15, "Se mimetiza con el saldo para engañar a los estafadores."),

                ("Lobo del Streak", "Épica", "🐺", "Lobo", "Depredador", "multiplier_scaling", 1.01, 1.0, 0, "any", "hot_streak", "keep_streak_or_pay", 4000, 0.18, "Un cazador implacable que huele la victoria."),
                ("Ballena Dorada", "Épica", "🐳", "Marino", "Codicioso", "proc_high_roller", 0.12, 0.12, 1500, "any", "wealth", "pay", 7500, 0.20, "Nada en mares de opulencia. Exige grandes apuestas."),
                ("Cuervo del Pacto", "Épica", "🐦‍⬛", "Ave", "Oscuro", "proc_universal", 0.09, 0.14, 900, "any", "ritual", "sacrifice", 0, 0.40, "Un trato en las sombras. No te quedes sin dinero..."),
                ("Grifo de Tormenta", "Épica", "🦅", "Ave", "Imponente", "proc_universal", 0.11, 0.12, 1000, "raid", "volume", "auto", 0, 0.20, "Desata ráfagas de viento que aceleran el trabajo y aturden a los jefes."),
                ("Basilisco de Esmeralda", "Épica", "🐍", "Reptil", "Venenoso", "proc_derrota", 0.15, 0.10, 1200, "any", "cold_streak", "pay", 5000, 0.20, "Sombra petrificante que reduce el impacto de las pérdidas."),
                ("Mantícora de Sombras", "Épica", "🦂", "Sombra", "Agresivo", "proc_high_roller", 0.14, 0.10, 1300, "robar", "specialized", "pay", 6000, 0.20, "Afecta a sus presas con un veneno corrosivo e implacable."),
                ("Pegaso Rúnico", "Épica", "🐴", "Mítico", "Ágil", "multiplier", 1.08, 1.0, 0, "any", "hot_streak", "auto", 0, 0.15, "Galopa por los cielos recortando cooldowns de robos y batallas."),
                ("Pulpo Subterráneo", "Épica", "🐙", "Marino", "Astuto", "proc_juego", 0.14, 0.10, 1100, "crash", "specialized", "auto", 0, 0.20, "Especialista en hackear operaciones de bolsa y casino."),
                ("Búho Erudito", "Épica", "📜", "Ave", "Erudito", "multiplier", 1.10, 1.0, 0, "trabajo", "volume", "auto", 0, 0.15, "Guarda compendios de conocimiento que aceleran el nivel de oficio."),
                ("Espectro Codicioso", "Épica", "👹", "Sombra", "Desalmado", "proc_universal", 0.12, 0.12, 1400, "robar", "specialized", "auto", 0, 0.25, "Extrae fragmentos de fortuna adicional en cada atraco."),
                ("Íncubo de Furia", "Épica", "😈", "Furia", "Indomable", "proc_juego_y_mult", 0.15, 0.10, 1250, "blackjack", "specialized", "auto", 0, 0.20, "Alimenta su fuego interno con la tensión de las grandes apuestas."),
                ("Axolote Astral", "Épica", "🦎", "Mítico", "Místico", "proc_universal", 0.10, 0.15, 1150, "any", "volume", "auto", 0, 0.15, "Ser místico capaz de sanar la lealtad y vida de aliados."),

                ("Dragón del Jackpot", "Legendaria", "🐉", "Furia", "Orgulloso", "proc_juego_y_mult", 0.18, 0.10, 3000, "slots", "specialized", "pay", 15000, 0.15, "Custodia las máquinas tragamonedas más calientes."),
                ("Tiburón del Abismo", "Legendaria", "🦈", "Marino", "Agresivo", "proc_high_roller", 0.20, 0.08, 4000, "any", "volume", "pay", 12000, 0.25, "Huele el miedo y la codicia. Solo respeta a los arriesgados."),
                ("Quimera Oscura", "Legendaria", "🦁", "Sombra", "Furtivo", "proc_universal", 0.15, 0.10, 3500, "robar", "specialized", "pay", 14000, 0.20, "Acecha en la penumbra para garantizar golpes limpios."),
                ("Kirin del Firmamento", "Legendaria", "🦄", "Mítico", "Noble", "multiplier", 1.12, 1.0, 0, "any", "hot_streak", "pay", 16000, 0.10, "Bestia sagrada que restaura la lealtad de la party y otorga bendición."),
                ("Behemoth de Piedra", "Legendaria", "🦣", "Piedra", "Colosal", "multiplier_safe", 1.10, 1.0, 0, "any", "wealth", "pay", 18000, 0.10, "Coloso legendario que protege grandes fortunas ante asaltos."),
                ("Kraken del Abismo", "Legendaria", "🦑", "Marino", "Monstruoso", "proc_juego", 0.22, 0.08, 4500, "crash", "specialized", "pay", 17000, 0.20, "Gigante de las profundidades que atrapa grandes multiplicadores."),
                ("Cerbero del Infierno", "Legendaria", "🐕‍🦺", "Furia", "Feroz", "proc_universal", 0.18, 0.10, 3800, "robar", "specialized", "pay", 15500, 0.20, "Tres cabezas que velan por tu saldo e imponen quemadura en Raids."),
                ("Zorro del Firmamento", "Legendaria", "🦊", "Mítico", "Celestial", "proc_universal", 0.16, 0.12, 3200, "loteria", "volume", "pay", 14500, 0.15, "Nueve colas de luz que manipulan la probabilidad del destino."),
                ("Oso del Helero", "Legendaria", "🧊", "Gólem", "Implacable", "multiplier_safe", 1.08, 1.0, 0, "raid", "wealth", "pay", 13500, 0.15, "Guardián de hielo que congela jefes y mantiene la estabilidad."),

                ("Fénix de las Cenizas", "Mítica", "🔥", "Fénix", "Protector", "proc_derrota_y_revive", 0.25, 0.07, 5000, "any", "recovery", "pay_and_survive", 20000, 0.05, "Renace de la bancarrota absoluta."),
                ("Hidra de Siete Cabezas", "Mítica", "🐍", "Furia", "Insaciable", "proc_derrota", 0.30, 0.06, 6000, "any", "cold_streak", "pay_and_survive", 25000, 0.05, "Cada cabeza que cae resurge con un ataque feroz e incesante."),
                ("Dragón Estelar", "Mítica", "🌟", "Mítico", "Cosmico", "multiplier", 1.20, 1.0, 0, "any", "wealth", "pay_and_survive", 30000, 0.05, "Entidad astral que altera la realidad financiera de toda la economía."),
                ("Llama Sagrada", "Mítica", "🦙", "Mítico", "Divino", "proc_universal", 0.25, 0.08, 5500, "any", "ritual", "pay_and_survive", 22000, 0.05, "Ser divino que concede bonificaciones astronómicas y protección total.")
            ]
            seed_q = """
                INSERT INTO PetsCatalog (
                    Name, Rarity, Emoji, Family, Temperament, EffectType, 
                    EffectValue, EffectChance, EffectCap, FavoriteGame, 
                    EncounterType, CaptureType, CaptureConfig, BaseLeaveChance, FlavorText
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """
            for pet_item in pets_seed_50:
                cursor.execute("SELECT 1 FROM PetsCatalog WHERE Name = %s", (pet_item[0],))
                if not cursor.fetchone():
                    cursor.execute(seed_q, pet_item)
            
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS UserPets (
                    UserPetID SERIAL PRIMARY KEY,
                    UserID BIGINT NOT NULL,
                    PetID INT NOT NULL,
                    Nickname VARCHAR(32),
                    IsActive INT DEFAULT 0,
                    Status VARCHAR(20) DEFAULT 'Normal',
                    Loyalty INT DEFAULT 50,
                    Mood VARCHAR(20) DEFAULT 'Feliz',
                    RecruitedAt TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    GamesWithOwner INT DEFAULT 0,
                    WinsWithOwner INT DEFAULT 0,
                    LossesWithOwner INT DEFAULT 0
                )
            """)
            cursor.execute("ALTER TABLE UserPets ADD COLUMN IF NOT EXISTS Nickname VARCHAR(32)")
            cursor.execute("ALTER TABLE UserPets ADD COLUMN IF NOT EXISTS Level INT DEFAULT 1")
            cursor.execute("ALTER TABLE UserPets ADD COLUMN IF NOT EXISTS XP BIGINT DEFAULT 0")
            cursor.execute("ALTER TABLE UserPets ADD COLUMN IF NOT EXISTS EquippedSlot VARCHAR(20) DEFAULT NULL")
            
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS GuildConfig (
                    GuildID BIGINT PRIMARY KEY,
                    AuctionChannelID BIGINT DEFAULT NULL
                )
            """)
            cursor.execute("ALTER TABLE GuildConfig ADD COLUMN IF NOT EXISTS AuctionChannelID BIGINT DEFAULT NULL")
            
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS UserPityState (
                    UserID BIGINT PRIMARY KEY,
                    UnluckyBoxesCount INT DEFAULT 0
                )
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS UserMarketListings (
                    ListingID SERIAL PRIMARY KEY,
                    SellerID BIGINT NOT NULL,
                    ItemType VARCHAR(20) NOT NULL,
                    ItemID INT NOT NULL,
                    Price BIGINT NOT NULL,
                    Currency VARCHAR(20) DEFAULT 'balance',
                    CreatedAt TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS UserAuctions (
                    AuctionID SERIAL PRIMARY KEY,
                    SellerID BIGINT NOT NULL,
                    ItemType VARCHAR(20) NOT NULL,
                    ItemID INT NOT NULL,
                    CurrentBid BIGINT NOT NULL,
                    HighestBidderID BIGINT DEFAULT NULL,
                    AuctionEndTime TIMESTAMP NOT NULL,
                    Currency VARCHAR(20) DEFAULT 'balance',
                    CreatedAt TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS UserShopStock (
                    RotationSeed BIGINT NOT NULL,
                    ShopType VARCHAR(20) NOT NULL,
                    ItemID INT NOT NULL,
                    StockRemaining INT NOT NULL,
                    PRIMARY KEY (RotationSeed, ShopType, ItemID)
                )
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS GuildPoblado (
                    GuildID BIGINT PRIMARY KEY,
                    RecursoMadera INT DEFAULT 0,
                    RecursoPiedra INT DEFAULT 0,
                    RecursoCristal INT DEFAULT 0,
                    RecursoSolar INT DEFAULT 0,
                    ProyectoActivo VARCHAR(50) DEFAULT 'Herrería de Combate',
                    ProgresoProyecto INT DEFAULT 0,
                    PuntosSemanales INT DEFAULT 0,
                    UltimoResetSemanal TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS GuildEdificios (
                    GuildID BIGINT NOT NULL,
                    NombreEdificio VARCHAR(50) NOT NULL,
                    Nivel INT DEFAULT 0,
                    FinConstruccion TIMESTAMP DEFAULT NULL,
                    PRIMARY KEY (GuildID, NombreEdificio)
                )
            """)
            cursor.execute("ALTER TABLE GuildEdificios ADD COLUMN IF NOT EXISTS FinConstruccion TIMESTAMP DEFAULT NULL;")


            cursor.execute("""
                CREATE TABLE IF NOT EXISTS PobladoContribuciones (
                    GuildID BIGINT NOT NULL,
                    UserID BIGINT NOT NULL,
                    PuntosAportados INT DEFAULT 0,
                    MaterialesDonados INT DEFAULT 0,
                    PRIMARY KEY (GuildID, UserID)
                )
            """)


            
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS GamblerProgress (
                    UserID BIGINT PRIMARY KEY,
                    GamblerLevel INT DEFAULT 1,
                    GamblerXP INT DEFAULT 0,
                    TotalValidBets INT DEFAULT 0,
                    TotalBetVolume BIGINT DEFAULT 0,
                    LastLevelUpAt TIMESTAMP
                )
            """)
            
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS UserPetEvents (
                    EventID SERIAL PRIMARY KEY,
                    UserID BIGINT NOT NULL,
                    PetID INT,
                    EventType VARCHAR(50) NOT NULL,
                    Details TEXT,
                    CreatedAt TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS UserPetEncounterState (
                    UserID BIGINT NOT NULL,
                    EncounterType VARCHAR(50) NOT NULL,
                    FailedEncounters INT DEFAULT 0,
                    LastEncounterAt TIMESTAMP,
                    LastEncounterPetID INT,
                    SpecialProgress INT DEFAULT 0,
                    PRIMARY KEY (UserID, EncounterType)
                )
            """)
            # ---------------------------------------

            
            # Tabla: Transactions
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS Transactions (
                    TransactionID SERIAL PRIMARY KEY,
                    UserID BIGINT NOT NULL,
                    Amount BIGINT NOT NULL,
                    TransactionType VARCHAR(150) NOT NULL,
                    Date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Tabla: UserItems
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS UserItems (
                    ID SERIAL PRIMARY KEY,
                    UserID BIGINT NOT NULL,
                    ItemID INT NOT NULL,
                    Quantity INT DEFAULT 1,
                    Expiry TIMESTAMP NOT NULL,
                    Used INT DEFAULT 0
                )
            """)
            
            # Tabla: UserGameStats
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS UserGameStats (
                    UserID BIGINT PRIMARY KEY,
                    TotalGamesPlayed INT DEFAULT 0,
                    TotalWins INT DEFAULT 0,
                    TotalLosses INT DEFAULT 0,
                    TotalAmountBet DOUBLE PRECISION DEFAULT 0.0,
                    TotalAmountWon DOUBLE PRECISION DEFAULT 0.0,
                    WinRate DOUBLE PRECISION DEFAULT 0.0,
                    AvgBetSize DOUBLE PRECISION DEFAULT 0.0,
                    LastGameTime TIMESTAMP,
                    HotStreak INT DEFAULT 0,
                    ColdStreak INT DEFAULT 0,
                    RiskProfile VARCHAR(20) DEFAULT 'BALANCED',
                    DifficultyLevel DOUBLE PRECISION DEFAULT 0.0
                )
            """)
            
            # Tabla: GameHistory
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS GameHistory (
                    ID SERIAL PRIMARY KEY,
                    UserID BIGINT NOT NULL,
                    GameType VARCHAR(50) NOT NULL,
                    BetAmount BIGINT NOT NULL,
                    Result VARCHAR(20) NOT NULL,
                    WinAmount BIGINT NOT NULL,
                    Timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    DifficultyApplied DOUBLE PRECISION DEFAULT 0.0,
                    UserBalance BIGINT NOT NULL
                )
            """)
            
            # Tabla: GameResults (Para el sistema de dificultad dinámica)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS GameResults (
                    ResultID SERIAL PRIMARY KEY,
                    UserID BIGINT NOT NULL,
                    GameType VARCHAR(50) NOT NULL,
                    BetAmount BIGINT NOT NULL,
                    Result VARCHAR(20) NOT NULL,
                    Winnings BIGINT NOT NULL,
                    DifficultyModifier DOUBLE PRECISION NOT NULL,
                    Balance BIGINT NOT NULL,
                    Timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Tabla: DifficultyStats (Para el sistema de dificultad dinámica)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS DifficultyStats (
                    UserID BIGINT PRIMARY KEY,
                    CurrentDifficulty DOUBLE PRECISION DEFAULT 0.0,
                    TotalGames INT DEFAULT 0,
                    WinRate DOUBLE PRECISION DEFAULT 0.0,
                    HotStreak INT DEFAULT 0,
                    ColdStreak INT DEFAULT 0,
                    AvgBet DOUBLE PRECISION DEFAULT 0.0,
                    RiskProfile VARCHAR(20) DEFAULT 'BALANCED',
                    LastUpdate TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Tabla: joblevels
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS joblevels (
                    ID SERIAL PRIMARY KEY,
                    UserId BIGINT NOT NULL,
                    JobType VARCHAR(20) NOT NULL,
                    CompletedJobs INT DEFAULT 0,
                    Level INT DEFAULT 0,
                    Experience INT DEFAULT 0,
                    CreatedAt TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UpdatedAt TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    CONSTRAINT uq_userid_jobtype UNIQUE (UserId, JobType)
                )
            """)
            cursor.execute("ALTER TABLE joblevels ADD COLUMN IF NOT EXISTS LastJobTime TIMESTAMP")
            cursor.execute("ALTER TABLE joblevels ADD COLUMN IF NOT EXISTS Streak INT DEFAULT 0")
            
            # Tabla: RoboStats
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS RoboStats (
                    UserID BIGINT PRIMARY KEY,
                    LastRoboTime TIMESTAMP,
                    LastRobadoTime TIMESTAMP,
                    RobosExitosos INT DEFAULT 0,
                    RobosFallidos INT DEFAULT 0,
                    RobosFallidosConsecutivos INT DEFAULT 0,
                    TotalRobado BIGINT DEFAULT 0,
                    TotalPerdido BIGINT DEFAULT 0,
                    ThiefLevel INT DEFAULT 1,
                    ThiefXP BIGINT DEFAULT 0,
                    ProteccionActiva BOOLEAN DEFAULT FALSE
                )
            """)
            cursor.execute("ALTER TABLE RoboStats ADD COLUMN IF NOT EXISTS ThiefLevel INT DEFAULT 1")
            cursor.execute("ALTER TABLE RoboStats ADD COLUMN IF NOT EXISTS ThiefXP BIGINT DEFAULT 0")
            cursor.execute("ALTER TABLE RoboStats ADD COLUMN IF NOT EXISTS RobosFallidosConsecutivos INT DEFAULT 0")
            cursor.execute("ALTER TABLE RoboStats ADD COLUMN IF NOT EXISTS ShieldExpiry TIMESTAMP")
            cursor.execute("ALTER TABLE RoboStats ADD COLUMN IF NOT EXISTS LastBancoRoboTime TIMESTAMP")
            
            # Tabla: RoboLog
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS RoboLog (
                    LogID SERIAL PRIMARY KEY,
                    LadronID BIGINT NOT NULL,
                    VictimaID BIGINT NOT NULL,
                    CantidadRobada BIGINT NOT NULL,
                    Exitoso BOOLEAN NOT NULL,
                    Timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Tabla: MinasActivas
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS MinasActivas (
                    CanalID BIGINT PRIMARY KEY,
                    Cantidad INT DEFAULT 0
                )
            """)
            
            # Tabla: LotteryTickets
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS LotteryTickets (
                    TicketID SERIAL PRIMARY KEY,
                    UserID BIGINT NOT NULL,
                    PurchaseDate TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            cursor.execute("ALTER TABLE LotteryTickets ADD COLUMN IF NOT EXISTS Numbers VARCHAR(50);")

            # Tabla: LotteryState
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS LotteryState (
                    ID INT PRIMARY KEY DEFAULT 1,
                    JackpotPool BIGINT DEFAULT 10000,
                    LastDrawDate TIMESTAMP,
                    NextDrawDate TIMESTAMP,
                    CONSTRAINT single_row CHECK (ID = 1)
                )
            """)
            cursor.execute("""
                INSERT INTO LotteryState (ID, JackpotPool)
                VALUES (1, 10000)
                ON CONFLICT (ID) DO NOTHING
            """)

            # Tabla: MinaStats
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS MinaStats (
                    UserID BIGINT PRIMARY KEY,
                    MinasPisadas INT DEFAULT 0
                )
            """)

            # Tabla: ProvablyFairSeeds
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS ProvablyFairSeeds (
                    UserID BIGINT PRIMARY KEY,
                    ServerSeed VARCHAR(64) NOT NULL,
                    ClientSeed VARCHAR(64) NOT NULL,
                    Nonce INT DEFAULT 0,
                    PastServerSeed VARCHAR(64),
                    PastClientSeed VARCHAR(64),
                    PastNonce INT
                )
            """)

            # Tabla: ActiveMultiplayerGames
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS ActiveMultiplayerGames (
                    GameID VARCHAR(50) PRIMARY KEY,
                    GameType VARCHAR(50) NOT NULL,
                    GameState JSONB NOT NULL,
                    LastUpdate TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Índices para rutas frecuentes de comandos, juegos e inventario.

            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_transactions_user_date
                ON Transactions (UserID, Date DESC)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_gameresults_user_timestamp
                ON GameResults (UserID, Timestamp DESC)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_gamehistory_user_timestamp
                ON GameHistory (UserID, Timestamp DESC)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_useritems_active_lookup
                ON UserItems (UserID, ItemID, Expiry)
                WHERE Quantity > 0 AND Used = 0
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_users_balance_desc
                ON Users (Balance DESC)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_robolog_ladron_timestamp
                ON RoboLog (LadronID, Timestamp DESC)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_robolog_victima_timestamp
                ON RoboLog (VictimaID, Timestamp DESC)
            """)
            
            # Tabla: DailyItemUsage para limitar el uso de objetos de energía
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS DailyItemUsage (
                    UserID BIGINT,
                    ItemID INT,
                    UsageDate DATE DEFAULT CURRENT_DATE,
                    UsageCount INT DEFAULT 0,
                    BlockedUntil TIMESTAMP,
                    PRIMARY KEY (UserID, ItemID, UsageDate)
                )
            """)

            # ─── TABLAS DEL SISTEMA DE DUELOS PVP ───
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS CombatStats (
                    UserID BIGINT PRIMARY KEY,
                    CombatLevel INT DEFAULT 1,
                    CombatXP BIGINT DEFAULT 0,
                    Wins INT DEFAULT 0,
                    Losses INT DEFAULT 0,
                    WinStreak INT DEFAULT 0,
                    BestWinStreak INT DEFAULT 0,
                    LastDuelTime TIMESTAMP,
                    TotalMoneyWon BIGINT DEFAULT 0,
                    TotalMoneyLost BIGINT DEFAULT 0,
                    CombatClass VARCHAR(20) DEFAULT NULL,
                    CombatSubclass VARCHAR(30) DEFAULT NULL
                )
            """)

            # Migración dirigida para añadir CombatClass si CombatStats existe
            cursor.execute("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables 
                    WHERE table_name = 'combatstats'
                )
            """)
            if cursor.fetchone()[0]:
                cursor.execute("""
                    SELECT 1 FROM information_schema.columns 
                    WHERE table_name = 'combatstats' AND column_name = 'combatclass'
                """)
                if not cursor.fetchone():
                    cursor.execute("ALTER TABLE CombatStats ADD COLUMN CombatClass VARCHAR(20) DEFAULT NULL")
                # Migración: añadir CombatSubclass si no existe
                cursor.execute("ALTER TABLE CombatStats ADD COLUMN IF NOT EXISTS CombatSubclass VARCHAR(30) DEFAULT NULL")

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS CombatLog (
                    LogID SERIAL PRIMARY KEY,
                    ChallengerID BIGINT NOT NULL,
                    RivalID BIGINT NOT NULL,
                    WinnerID BIGINT NOT NULL,
                    Bet BIGINT NOT NULL,
                    Turns INT NOT NULL,
                    ChallengerLevel INT,
                    RivalLevel INT,
                    Timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Targeted migration to add missing columns in UserEquipment if it already exists
            cursor.execute("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables 
                    WHERE table_name = 'userequipment'
                )
            """)
            table_exists = cursor.fetchone()[0]
            if table_exists:
                cursor.execute("""
                    SELECT 1 FROM information_schema.columns 
                    WHERE table_name = 'userequipment' AND column_name = 'primarystat'
                """)
                if not cursor.fetchone():
                    cursor.execute("ALTER TABLE UserEquipment ADD COLUMN IF NOT EXISTS PrimaryStat VARCHAR(10) DEFAULT 'ATK'")
                    cursor.execute("ALTER TABLE UserEquipment ADD COLUMN IF NOT EXISTS PrimaryValue INT DEFAULT 0")

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS UserEquipment (
                    ID SERIAL PRIMARY KEY,
                    UserID BIGINT NOT NULL,
                    Slot VARCHAR(20) NOT NULL,
                    ItemName VARCHAR(100) NOT NULL,
                    Rarity VARCHAR(20) NOT NULL,
                    ItemLevel INT NOT NULL,
                    PrimaryStat VARCHAR(10) NOT NULL,
                    PrimaryValue INT NOT NULL,
                    Secondaries JSONB DEFAULT '[]'::jsonb,
                    Passive JSONB DEFAULT NULL,
                    MiniAffixKey VARCHAR(20) DEFAULT NULL,
                    MiniAffixValue NUMERIC DEFAULT NULL,
                    WeaponSubtype VARCHAR(10) DEFAULT NULL,
                    CONSTRAINT uq_user_slot UNIQUE (UserID, Slot)
                )
            """)
            cursor.execute("ALTER TABLE UserEquipment ADD COLUMN IF NOT EXISTS GemKey VARCHAR(40) DEFAULT NULL")
            cursor.execute("ALTER TABLE UserEquipment ADD COLUMN IF NOT EXISTS MiniAffixKey VARCHAR(20) DEFAULT NULL")
            cursor.execute("ALTER TABLE UserEquipment ADD COLUMN IF NOT EXISTS MiniAffixValue NUMERIC DEFAULT NULL")
            cursor.execute("ALTER TABLE UserEquipment ADD COLUMN IF NOT EXISTS WeaponSubtype VARCHAR(10) DEFAULT NULL")

            # Tabla: GemCatalog (Gemas y Encantamientos)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS GemCatalog (
                    GemKey VARCHAR(40) PRIMARY KEY,
                    Name VARCHAR(60) NOT NULL,
                    StatTarget VARCHAR(10) NOT NULL,
                    Tier VARCHAR(10) NOT NULL,
                    BonusValue NUMERIC NOT NULL,
                    IsPercentage BOOLEAN DEFAULT FALSE,
                    Price BIGINT NOT NULL
                )
            """)

            gemas = [
                ('gema_menor_vida', 'Gema de Vida (Menor)', 'hp', 'menor', 3, False, 300),
                ('gema_mayor_vida', 'Gema de Vida (Mayor)', 'hp', 'mayor', 6, False, 1200),
                ('gema_perfecta_vida', 'Gema de Vida (Perfecta)', 'hp', 'perfecta', 10, False, 10000),
                ('gema_menor_fuerza', 'Gema de Fuerza (Menor)', 'atk', 'menor', 3, False, 300),
                ('gema_mayor_fuerza', 'Gema de Fuerza (Mayor)', 'atk', 'mayor', 6, False, 1200),
                ('gema_perfecta_fuerza', 'Gema de Fuerza (Perfecta)', 'atk', 'perfecta', 10, False, 10000),
                ('gema_menor_poder', 'Gema de Poder (Menor)', 'mag', 'menor', 3, False, 300),
                ('gema_mayor_poder', 'Gema de Poder (Mayor)', 'mag', 'mayor', 6, False, 1200),
                ('gema_perfecta_poder', 'Gema de Poder (Perfecta)', 'mag', 'perfecta', 10, False, 10000),
                ('gema_menor_resistencia', 'Gema de Resistencia (Menor)', 'def', 'menor', 3, False, 300),
                ('gema_mayor_resistencia', 'Gema de Resistencia (Mayor)', 'def', 'mayor', 6, False, 1200),
                ('gema_perfecta_resistencia', 'Gema de Resistencia (Perfecta)', 'def', 'perfecta', 10, False, 10000),
                ('gema_menor_agilidad', 'Gema de Agilidad (Menor)', 'dodge', 'menor', 0.01, True, 400),
                ('gema_mayor_agilidad', 'Gema de Agilidad (Mayor)', 'dodge', 'mayor', 0.02, True, 1600),
                ('gema_perfecta_agilidad', 'Gema de Agilidad (Perfecta)', 'dodge', 'perfecta', 0.04, True, 13000),
                ('gema_menor_letalidad', 'Gema de Letalidad (Menor)', 'crit', 'menor', 0.01, True, 400),
                ('gema_mayor_letalidad', 'Gema de Letalidad (Mayor)', 'crit', 'mayor', 0.02, True, 1600),
                ('gema_perfecta_letalidad', 'Gema de Letalidad (Perfecta)', 'crit', 'perfecta', 0.04, True, 13000),
            ]
            for g in gemas:
                cursor.execute("""
                    INSERT INTO GemCatalog (GemKey, Name, StatTarget, Tier, BonusValue, IsPercentage, Price)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (GemKey) DO NOTHING
                """, g)

            # Tablas: Consumibles de combate
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS ConsumableCatalog (
                    ConsumableKey VARCHAR(30) PRIMARY KEY,
                    Name VARCHAR(60) NOT NULL,
                    Description VARCHAR(200) NOT NULL,
                    Price BIGINT NOT NULL
                )
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS UserConsumables (
                    UserID BIGINT NOT NULL,
                    ConsumableKey VARCHAR(30) NOT NULL,
                    Quantity INT NOT NULL DEFAULT 0,
                    PRIMARY KEY (UserID, ConsumableKey)
                )
            """)

            consumables = [
                ('pocion_curacion', 'Poción de Curación', 'Cura 25% del HP máximo propio', 20),
                ('pergamino_purificacion', 'Pergamino de Purificación', 'Limpia todos los debuffs propios activos', 35),
                ('bomba_humo', 'Bomba de Humo', 'Garantiza esquivar el próximo golpe recibido (1 turno)', 25),
                ('frasco_silencio', 'Frasco de Silencio', 'Aplica Silencio (2 turnos) a un enemigo (rival en duelo, o boss/esbirro elegido en raid)', 40),
            ]
            for c in consumables:
                cursor.execute("""
                    INSERT INTO ConsumableCatalog (ConsumableKey, Name, Description, Price)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (ConsumableKey) DO NOTHING
                """, c)

            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_combatlog_challenger
                ON CombatLog (ChallengerID, Timestamp DESC)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_combatlog_rival
                ON CombatLog (RivalID, Timestamp DESC)
            """)

            # Tabla: IgnoredUsers
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS IgnoredUsers (
                    UserID BIGINT PRIMARY KEY,
                    AddedAt TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Tabla: CombatWallet (Moneda de combate)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS CombatWallet (
                    UserID BIGINT PRIMARY KEY,
                    Bronze BIGINT NOT NULL DEFAULT 0
                )
            """)
            
            # Tabla: RaidLog (Sistema de Raids)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS RaidLog (
                    ID SERIAL PRIMARY KEY,
                    BossName VARCHAR(50),
                    Participants JSONB,
                    Result VARCHAR(10),
                    Turns INT,
                    TotalLevel INT,
                    Timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            cursor.execute("ALTER TABLE RaidLog ADD COLUMN IF NOT EXISTS Difficulty VARCHAR(10) DEFAULT 'normal'")
            
            # Tabla: UniqueItemCatalog (Catálogo de ítems únicos)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS UniqueItemCatalog (
                    ID SERIAL PRIMARY KEY,
                    ItemKey VARCHAR(50) UNIQUE NOT NULL,
                    Name VARCHAR(100) NOT NULL,
                    Slot VARCHAR(20) NOT NULL,
                    Rarity VARCHAR(20) DEFAULT 'Legendario',
                    PrimaryStat VARCHAR(10) NOT NULL,
                    PrimaryValue INT NOT NULL,
                    Secondaries JSONB DEFAULT '[]'::jsonb,
                    Passive JSONB DEFAULT NULL,
                    BossSource VARCHAR(50),
                    Lore TEXT
                )
            """)
            cursor.execute("ALTER TABLE UniqueItemCatalog ADD COLUMN IF NOT EXISTS SetKey VARCHAR(30) DEFAULT NULL")

            # Tabla: EquipmentSets (Sets de equipo y sus bonus)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS EquipmentSets (
                    SetKey VARCHAR(30) PRIMARY KEY,
                    SetName VARCHAR(100) NOT NULL,
                    Bonus2pc JSONB NOT NULL,
                    Bonus4pc JSONB NOT NULL
                )
            """)

            equipment_sets_data = [
                (
                    "set_yggdrasil",
                    "Manto del Bosque Corrupto",
                    {"type": "flat_pct", "stat": "hp", "value": 0.08},
                    {"type": "passive", "effect_id": "yggdrasil_group_regen"}
                ),
                (
                    "set_ignis",
                    "Armadura del Coloso",
                    {"type": "flat_pct", "stat": "atk", "value": 0.08},
                    {"type": "passive", "effect_id": "ignis_burn_extension"}
                ),
                (
                    "set_caelum",
                    "Vestimenta de Tormenta",
                    {"type": "flat_pct", "stat": "crit", "value": 0.08},
                    {"type": "passive", "effect_id": "caelum_first_strike_dodge"}
                ),
                (
                    "set_thanatos",
                    "Ropaje del Segador",
                    {"type": "flat_pct", "stat": "vamp", "value": 0.08},
                    {"type": "passive", "effect_id": "thanatos_ally_death_lifesteal"}
                ),
                (
                    "set_leviathan",
                    "Escamas Glaciales",
                    {"type": "flat_pct", "stat": "def", "value": 0.08},
                    {"type": "passive", "effect_id": "leviathan_cc_reduction"}
                ),
                (
                    "set_aurelius",
                    "Vestidura Celestial",
                    {"type": "flat_pct", "stat": "heal_power", "value": 0.08},
                    {"type": "passive", "effect_id": "aurelius_low_hp_heal"}
                ),
                (
                    "set_abyssus",
                    "Fragmentos del Caos",
                    {"type": "flat_pct", "stat": "random_stat", "value": 0.08},
                    {"type": "passive", "effect_id": "abyssus_random_4pc"}
                )
            ]
            
            import psycopg2.extras
            for skey, sname, b2, b4 in equipment_sets_data:
                cursor.execute("""
                    INSERT INTO EquipmentSets (SetKey, SetName, Bonus2pc, Bonus4pc)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (SetKey) DO UPDATE 
                    SET SetName = EXCLUDED.SetName,
                        Bonus2pc = EXCLUDED.Bonus2pc,
                        Bonus4pc = EXCLUDED.Bonus4pc
                """, (skey, sname, psycopg2.extras.Json(b2), psycopg2.extras.Json(b4)))

            unique_items = [
                {
                    "ItemKey": "corona_yggdrasil",
                    "Name": "Corona del Yggdrasil Corrupto",
                    "Slot": "Cabeza",
                    "Rarity": "Legendario",
                    "PrimaryStat": "hp",
                    "PrimaryValue": 87,
                    "Secondaries": [{"stat": "def", "value": 34}, {"stat": "mag", "value": 34}],
                    "Passive": {"id": "regen_improved", "value": 0.06},
                    "BossSource": "Yggdrasil Corrupto",
                    "Lore": "Una corona orgánica que pulsa con una energía oscura y regenerativa.",
                    "SetKey": "set_yggdrasil"
                },
                {
                    "ItemKey": "nucleo_ignis",
                    "Name": "Núcleo de Ignis",
                    "Slot": "Arma",
                    "Rarity": "Legendario",
                    "PrimaryStat": "mag",
                    "PrimaryValue": 87,
                    "Secondaries": [{"stat": "hp", "value": 34}, {"stat": "atk", "value": 34}],
                    "Passive": {"id": "burn_extend", "value": 50},
                    "BossSource": "Ignis, el Coloso de Magma",
                    "Lore": "Un fragmento ardiente del núcleo del coloso, irradia un calor abrasador.",
                    "SetKey": "set_ignis"
                },
                {
                    "ItemKey": "garra_caelum",
                    "Name": "Garra de la Tempestad",
                    "Slot": "Arma",
                    "Rarity": "Legendario",
                    "PrimaryStat": "atk",
                    "PrimaryValue": 87,
                    "Secondaries": [{"stat": "hp", "value": 34}, {"stat": "def", "value": 34}],
                    "Passive": {"id": "guaranteed_crit_cycle", "value": 4},
                    "BossSource": "Caelum, la Tempestad Viviente",
                    "Lore": "Una garra afilada infundida con rayos y vientos huracanados.",
                    "SetKey": "set_caelum"
                },
                {
                    "ItemKey": "manto_thanatos",
                    "Name": "Manto del Segador",
                    "Slot": "Pecho",
                    "Rarity": "Legendario",
                    "PrimaryStat": "hp",
                    "PrimaryValue": 104,
                    "Secondaries": [{"stat": "def", "value": 41}, {"stat": "atk", "value": 41}],
                    "Passive": {"id": "vampirism_improved", "value": 0.15},
                    "BossSource": "Thanatos, el Segador de Almas",
                    "Lore": "Una túnica oscura que parece absorber la luz de su alrededor.",
                    "SetKey": "set_thanatos"
                },
                {
                    "ItemKey": "escama_leviathan",
                    "Name": "Escama de Leviathán",
                    "Slot": "Escudo",
                    "Rarity": "Legendario",
                    "PrimaryStat": "def",
                    "PrimaryValue": 87,
                    "Secondaries": [{"stat": "hp", "value": 34}, {"stat": "atk", "value": 34}],
                    "Passive": {"id": "special_resist", "value": 0.10},
                    "BossSource": "Leviathán de la Fosa Glacial",
                    "Lore": "Una escama helada e impenetrable extraída de las profundidades del océano glacial.",
                    "SetKey": "set_leviathan"
                },
                {
                    "ItemKey": "pluma_aurelius",
                    "Name": "Pluma de Aurelius Caído",
                    "Slot": "Hombros",
                    "Rarity": "Legendario",
                    "PrimaryStat": "hp",
                    "PrimaryValue": 87,
                    "Secondaries": [{"stat": "def", "value": 34}, {"stat": "mag", "value": 34}],
                    "Passive": [{"id": "regen", "value": 0.03}, {"id": "dodge", "value": 0.05}],
                    "BossSource": "Aurelius, el Arcángel Caído",
                    "Lore": "Una pluma de ala angelical que ha perdido su brillo, pero conserva un gran poder divino.",
                    "SetKey": "set_aurelius"
                },
                {
                    "ItemKey": "fragmento_abyssus",
                    "Name": "Fragmento de Abyssus",
                    "Slot": "Pantalones",
                    "Rarity": "Legendario",
                    "PrimaryStat": "def",
                    "PrimaryValue": 87,
                    "Secondaries": [{"stat": "hp", "value": 34}, {"stat": "mag", "value": 34}],
                    "Passive": {"id": "chaos_random"},
                    "BossSource": "Abyssus, el Devorador Estelar",
                    "Lore": "Un fragmento de vacío puro que distorsiona la realidad alrededor de quien lo viste.",
                    "SetKey": "set_abyssus"
                },
                # --- YGGDRASIL SET ---
                {
                    "ItemKey": "hombros_yggdrasil",
                    "Name": "Manto del Yggdrasil Corrupto",
                    "Slot": "Hombros",
                    "Rarity": "Legendario",
                    "PrimaryStat": "hp",
                    "PrimaryValue": 87,
                    "Secondaries": [{"stat": "def", "value": 34}, {"stat": "mag", "value": 34}],
                    "Passive": {"id": "regen", "value": 0.03},
                    "BossSource": "Yggdrasil Corrupto",
                    "Lore": "Hombreras hechas de corteza podrida que supuran savia con propiedades curativas.",
                    "SetKey": "set_yggdrasil"
                },
                {
                    "ItemKey": "pecho_yggdrasil",
                    "Name": "Corteza del Yggdrasil Corrupto",
                    "Slot": "Pecho",
                    "Rarity": "Legendario",
                    "PrimaryStat": "hp",
                    "PrimaryValue": 104,
                    "Secondaries": [{"stat": "def", "value": 41}, {"stat": "mag", "value": 41}],
                    "Passive": {"id": "dodge", "value": 0.05},
                    "BossSource": "Yggdrasil Corrupto",
                    "Lore": "Una coraza pesada tejida de raíces milenarias infestadas por la plaga.",
                    "SetKey": "set_yggdrasil"
                },
                {
                    "ItemKey": "botas_yggdrasil",
                    "Name": "Raíces del Yggdrasil Corrupto",
                    "Slot": "Botas",
                    "Rarity": "Legendario",
                    "PrimaryStat": "hp",
                    "PrimaryValue": 87,
                    "Secondaries": [{"stat": "def", "value": 34}, {"stat": "mag", "value": 34}],
                    "Passive": {"id": "regen", "value": 0.03},
                    "BossSource": "Yggdrasil Corrupto",
                    "Lore": "Grebas orgánicas que se aferran al suelo, absorbiendo nutrientes de la tierra.",
                    "SetKey": "set_yggdrasil"
                },
                # --- IGNIS SET ---
                {
                    "ItemKey": "cabeza_ignis",
                    "Name": "Yelmo del Coloso de Magma",
                    "Slot": "Cabeza",
                    "Rarity": "Legendario",
                    "PrimaryStat": "hp",
                    "PrimaryValue": 87,
                    "Secondaries": [{"stat": "atk", "value": 34}, {"stat": "mag", "value": 34}],
                    "Passive": {"id": "fury"},
                    "BossSource": "Ignis, el Coloso de Magma",
                    "Lore": "Una corona de obsidiana ardiente que calienta la sangre del portador con furia volcánica.",
                    "SetKey": "set_ignis"
                },
                {
                    "ItemKey": "pecho_ignis",
                    "Name": "Coraza del Coloso de Magma",
                    "Slot": "Pecho",
                    "Rarity": "Legendario",
                    "PrimaryStat": "hp",
                    "PrimaryValue": 104,
                    "Secondaries": [{"stat": "atk", "value": 41}, {"stat": "mag", "value": 41}],
                    "Passive": {"id": "vampirism", "value": 0.08},
                    "BossSource": "Ignis, el Coloso de Magma",
                    "Lore": "Una armadura forjada en el núcleo del volcán, capaz de derretir el acero enemigo.",
                    "SetKey": "set_ignis"
                },
                {
                    "ItemKey": "botas_ignis",
                    "Name": "Paso del Coloso de Magma",
                    "Slot": "Botas",
                    "Rarity": "Legendario",
                    "PrimaryStat": "hp",
                    "PrimaryValue": 87,
                    "Secondaries": [{"stat": "atk", "value": 34}, {"stat": "mag", "value": 34}],
                    "Passive": {"id": "dodge", "value": 0.05},
                    "BossSource": "Ignis, el Coloso de Magma",
                    "Lore": "Botas de piedra volcánica que dejan un rastro de ceniza y ascuas a cada paso.",
                    "SetKey": "set_ignis"
                },
                # --- CAELUM SET ---
                {
                    "ItemKey": "hombros_caelum",
                    "Name": "Hombreras de la Tempestad",
                    "Slot": "Hombros",
                    "Rarity": "Legendario",
                    "PrimaryStat": "hp",
                    "PrimaryValue": 87,
                    "Secondaries": [{"stat": "def", "value": 34}, {"stat": "atk", "value": 34}],
                    "Passive": {"id": "dodge", "value": 0.05},
                    "BossSource": "Caelum, la Tempestad Viviente",
                    "Lore": "Hombreras livianas como la brisa y cargadas de electricidad estática.",
                    "SetKey": "set_caelum"
                },
                {
                    "ItemKey": "botas_caelum",
                    "Name": "Sandalias de la Tempestad",
                    "Slot": "Botas",
                    "Rarity": "Legendario",
                    "PrimaryStat": "hp",
                    "PrimaryValue": 87,
                    "Secondaries": [{"stat": "def", "value": 34}, {"stat": "atk", "value": 34}],
                    "Passive": {"id": "dodge", "value": 0.05},
                    "BossSource": "Caelum, la Tempestad Viviente",
                    "Lore": "Calzado que parece flotar sobre el suelo, permitiendo movimientos rápidos como el rayo.",
                    "SetKey": "set_caelum"
                },
                {
                    "ItemKey": "escudo_caelum",
                    "Name": "Baluarte de la Tempestad",
                    "Slot": "Escudo",
                    "Rarity": "Legendario",
                    "PrimaryStat": "def",
                    "PrimaryValue": 87,
                    "Secondaries": [{"stat": "hp", "value": 34}, {"stat": "atk", "value": 34}],
                    "Passive": {"id": "parry"},
                    "BossSource": "Caelum, la Tempestad Viviente",
                    "Lore": "Un escudo redondo formado por vientos densos y relámpagos condensados.",
                    "SetKey": "set_caelum"
                },
                # --- THANATOS SET ---
                {
                    "ItemKey": "cabeza_thanatos",
                    "Name": "Máscara del Segador",
                    "Slot": "Cabeza",
                    "Rarity": "Legendario",
                    "PrimaryStat": "hp",
                    "PrimaryValue": 87,
                    "Secondaries": [{"stat": "def", "value": 34}, {"stat": "atk", "value": 34}],
                    "Passive": {"id": "vampirism", "value": 0.08},
                    "BossSource": "Thanatos, el Segador de Almas",
                    "Lore": "Una máscara de hueso frío que oculta la humanidad de quien la porta.",
                    "SetKey": "set_thanatos"
                },
                {
                    "ItemKey": "pantalones_thanatos",
                    "Name": "Musleras del Segador",
                    "Slot": "Pantalones",
                    "Rarity": "Legendario",
                    "PrimaryStat": "hp",
                    "PrimaryValue": 87,
                    "Secondaries": [{"stat": "def", "value": 34}, {"stat": "atk", "value": 34}],
                    "Passive": {"id": "bleed_on_hit"},
                    "BossSource": "Thanatos, el Segador de Almas",
                    "Lore": "Musleras sombrías que irradian una fría neblina espectral.",
                    "SetKey": "set_thanatos"
                },
                {
                    "ItemKey": "botas_thanatos",
                    "Name": "Senderos del Segador",
                    "Slot": "Botas",
                    "Rarity": "Legendario",
                    "PrimaryStat": "hp",
                    "PrimaryValue": 87,
                    "Secondaries": [{"stat": "def", "value": 34}, {"stat": "atk", "value": 34}],
                    "Passive": {"id": "second_wind"},
                    "BossSource": "Thanatos, el Segador de Almas",
                    "Lore": "Calzado de cuero negro que amortigua todo sonido, como el paso de la muerte.",
                    "SetKey": "set_thanatos"
                },
                # --- LEVIATHAN SET ---
                {
                    "ItemKey": "cabeza_leviathan",
                    "Name": "Corona del Leviathán",
                    "Slot": "Cabeza",
                    "Rarity": "Legendario",
                    "PrimaryStat": "hp",
                    "PrimaryValue": 87,
                    "Secondaries": [{"stat": "def", "value": 34}, {"stat": "atk", "value": 34}],
                    "Passive": {"id": "regen", "value": 0.03},
                    "BossSource": "Leviathán de la Fosa Glacial",
                    "Lore": "Un yelmo forjado con huesos del gran monstruo marino y hielo eterno.",
                    "SetKey": "set_leviathan"
                },
                {
                    "ItemKey": "hombros_leviathan",
                    "Name": "Placas del Leviathán",
                    "Slot": "Hombros",
                    "Rarity": "Legendario",
                    "PrimaryStat": "hp",
                    "PrimaryValue": 87,
                    "Secondaries": [{"stat": "def", "value": 34}, {"stat": "atk", "value": 34}],
                    "Passive": {"id": "special_resist", "value": 0.10},
                    "BossSource": "Leviathán de la Fosa Glacial",
                    "Lore": "Hombreras cubiertas de picos de escarcha que congelan el aire a su alrededor.",
                    "SetKey": "set_leviathan"
                },
                {
                    "ItemKey": "pantalones_leviathan",
                    "Name": "Quillas del Leviathán",
                    "Slot": "Pantalones",
                    "Rarity": "Legendario",
                    "PrimaryStat": "hp",
                    "PrimaryValue": 87,
                    "Secondaries": [{"stat": "def", "value": 34}, {"stat": "atk", "value": 34}],
                    "Passive": {"id": "dodge", "value": 0.05},
                    "BossSource": "Leviathán de la Fosa Glacial",
                    "Lore": "Pantalones de malla escamosa que repelen el agua y el frío más extremo.",
                    "SetKey": "set_leviathan"
                },
                # --- AURELIUS SET ---
                {
                    "ItemKey": "cabeza_aurelius",
                    "Name": "Aureola del Arcángel Caído",
                    "Slot": "Cabeza",
                    "Rarity": "Legendario",
                    "PrimaryStat": "hp",
                    "PrimaryValue": 87,
                    "Secondaries": [{"stat": "def", "value": 34}, {"stat": "mag", "value": 34}],
                    "Passive": {"id": "regen", "value": 0.03},
                    "BossSource": "Aurelius, el Arcángel Caído",
                    "Lore": "Una aureola quebrada y corrupta que aún emana fragmentos de luz celestial.",
                    "SetKey": "set_aurelius"
                },
                {
                    "ItemKey": "pecho_aurelius",
                    "Name": "Coraza del Arcángel Caído",
                    "Slot": "Pecho",
                    "Rarity": "Legendario",
                    "PrimaryStat": "hp",
                    "PrimaryValue": 104,
                    "Secondaries": [{"stat": "def", "value": 41}, {"stat": "mag", "value": 41}],
                    "Passive": {"id": "arcane_shield"},
                    "BossSource": "Aurelius, el Arcángel Caído",
                    "Lore": "Peto dorado ornamentado con relieves celestiales profanados por la caída.",
                    "SetKey": "set_aurelius"
                },
                {
                    "ItemKey": "pantalones_aurelius",
                    "Name": "Grebas del Arcángel Caído",
                    "Slot": "Pantalones",
                    "Rarity": "Legendario",
                    "PrimaryStat": "hp",
                    "PrimaryValue": 87,
                    "Secondaries": [{"stat": "def", "value": 34}, {"stat": "mag", "value": 34}],
                    "Passive": {"id": "dodge", "value": 0.05},
                    "BossSource": "Aurelius, el Arcángel Caído",
                    "Lore": "Protección de piernas forjada en plata sagrada, ahora opacada por la impureza del abismo.",
                    "SetKey": "set_aurelius"
                },
                # --- ABYSSUS SET ---
                {
                    "ItemKey": "cabeza_abyssus",
                    "Name": "Mirada del Devorador Estelar",
                    "Slot": "Cabeza",
                    "Rarity": "Legendario",
                    "PrimaryStat": "hp",
                    "PrimaryValue": 87,
                    "Secondaries": [{"stat": "def", "value": 34}, {"stat": "mag", "value": 34}],
                    "Passive": {"id": "chaos_random"},
                    "BossSource": "Abyssus, el Devorador Estelar",
                    "Lore": "Un vacío sin rostro que parece devorar la luz misma de las estrellas.",
                    "SetKey": "set_abyssus"
                },
                {
                    "ItemKey": "botas_abyssus",
                    "Name": "Pasos del Devorador Estelar",
                    "Slot": "Botas",
                    "Rarity": "Legendario",
                    "PrimaryStat": "hp",
                    "PrimaryValue": 87,
                    "Secondaries": [{"stat": "def", "value": 34}, {"stat": "mag", "value": 34}],
                    "Passive": {"id": "chaos_random"},
                    "BossSource": "Abyssus, el Devorador Estelar",
                    "Lore": "Botas que distorsionan el espacio bajo los pies de quien las lleva.",
                    "SetKey": "set_abyssus"
                },
                {
                    "ItemKey": "escudo_abyssus",
                    "Name": "Falla del Devorador Estelar",
                    "Slot": "Escudo",
                    "Rarity": "Legendario",
                    "PrimaryStat": "def",
                    "PrimaryValue": 87,
                    "Secondaries": [{"stat": "hp", "value": 34}, {"stat": "mag", "value": 34}],
                    "Passive": {"id": "chaos_random"},
                    "BossSource": "Abyssus, el Devorador Estelar",
                    "Lore": "Una grieta espacial sostenida por pura fuerza de voluntad que absorbe golpes enemigos.",
                    "SetKey": "set_abyssus"
                }
            ]

            for item in unique_items:
                cursor.execute("""
                    INSERT INTO UniqueItemCatalog (
                        ItemKey, Name, Slot, Rarity, PrimaryStat, PrimaryValue, Secondaries, Passive, BossSource, Lore, SetKey
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (ItemKey) DO UPDATE
                    SET SetKey = EXCLUDED.SetKey,
                        Name = EXCLUDED.Name,
                        Slot = EXCLUDED.Slot,
                        Rarity = EXCLUDED.Rarity,
                        PrimaryStat = EXCLUDED.PrimaryStat,
                        PrimaryValue = EXCLUDED.PrimaryValue,
                        Secondaries = EXCLUDED.Secondaries,
                        Passive = EXCLUDED.Passive,
                        BossSource = EXCLUDED.BossSource,
                        Lore = EXCLUDED.Lore
                """, (
                    item["ItemKey"], item["Name"], item["Slot"], item["Rarity"],
                    item["PrimaryStat"], item["PrimaryValue"],
                    psycopg2.extras.Json(item["Secondaries"]),
                    psycopg2.extras.Json(item["Passive"]),
                    item["BossSource"], item["Lore"], item["SetKey"]
                ))
            # ─── FIN TABLAS DUELOS PVP ───

            # ─── BANCO CENTRAL ───
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS BancoCentral (
                    ID INT PRIMARY KEY DEFAULT 1,
                    Reservas BIGINT NOT NULL DEFAULT 0,
                    CHECK (ID = 1)
                )
            """)
            cursor.execute("""
                INSERT INTO BancoCentral (ID, Reservas)
                VALUES (1, 0)
                ON CONFLICT (ID) DO NOTHING
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS UserLoans (
                    UserID BIGINT NOT NULL,
                    MontoAdeudado BIGINT NOT NULL DEFAULT 0,
                    FechaPrestamo TIMESTAMP,
                    FechaVencimiento TIMESTAMP,
                    LimitePrestamo BIGINT NOT NULL DEFAULT 200000,
                    PrestamosPagadosATiempo INT NOT NULL DEFAULT 0,
                    EnMora BOOLEAN NOT NULL DEFAULT FALSE,
                    LoanSlot INT NOT NULL DEFAULT 1,
                    PRIMARY KEY (UserID, LoanSlot)
                )
            """)
            cursor.execute("ALTER TABLE UserLoans ADD COLUMN IF NOT EXISTS LoanSlot INT NOT NULL DEFAULT 1")
            
            # Cambiar PK a compuesta (UserID, LoanSlot) si aún es simple (solo UserID)
            cursor.execute("""
                SELECT constraint_name 
                FROM information_schema.table_constraints 
                WHERE table_name = 'userloans' AND constraint_type = 'PRIMARY KEY'
            """)
            row_constraint = cursor.fetchone()
            if row_constraint:
                constraint_name = row_constraint[0]
                cursor.execute("""
                    SELECT column_name 
                    FROM information_schema.key_column_usage 
                    WHERE constraint_name = %s
                """, (constraint_name,))
                columns = [r[0].lower() for r in cursor.fetchall()]
                if len(columns) == 1 and 'userid' in columns:
                    cursor.execute(f"ALTER TABLE UserLoans DROP CONSTRAINT IF EXISTS {constraint_name}")
                    cursor.execute("ALTER TABLE UserLoans ADD CONSTRAINT userloans_pkey PRIMARY KEY (UserID, LoanSlot)")
            else:
                cursor.execute("ALTER TABLE UserLoans ADD CONSTRAINT userloans_pkey PRIMARY KEY (UserID, LoanSlot)")

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS CuotaProteccion (
                    UserID BIGINT PRIMARY KEY,
                    UltimoPago TIMESTAMP,
                    UltimoMonto BIGINT DEFAULT 0
                )
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS UserInvestments (
                    UserID BIGINT PRIMARY KEY,
                    Monto BIGINT NOT NULL,
                    FechaInicio TIMESTAMP NOT NULL,
                    FechaVencimiento TIMESTAMP NOT NULL,
                    Resuelto BOOLEAN NOT NULL DEFAULT FALSE
                )
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS UserPrestige (
                    UserID BIGINT PRIMARY KEY,
                    PrestigeLevel INT NOT NULL DEFAULT 0,
                    FechaUltimoPrestigio TIMESTAMP
                )
            """)
            cursor.execute("""
                ALTER TABLE UserPrestige ADD COLUMN IF NOT EXISTS UltimoBonoMensual TIMESTAMP DEFAULT NULL
            """)
            # ─── MIGRACIÓN: INT → BIGINT en columnas de dinero/apuestas ───────────────
            # Estas migraciones son idempotentes: sólo se ejecutan si la columna todavía
            # es de tipo INT (postgres type_name 'integer'). No tocan columnas BIGINT,
            # SERIAL ni ningún otro tipo. Safe to re-run.
            _bigint_migrations = [
                ("gamehistory",      "betamount"),
                ("gamehistory",      "winamount"),
                ("gamehistory",      "userbalance"),
                ("gameresults",      "betamount"),
                ("gameresults",      "winnings"),
                ("gemcatalog",       "price"),
                ("consumablecatalog","price"),
            ]
            for _table, _col in _bigint_migrations:
                cursor.execute("""
                    SELECT data_type FROM information_schema.columns
                    WHERE table_name = %s AND column_name = %s
                """, (_table, _col))
                _row = cursor.fetchone()
                if _row and _row[0] == 'integer':
                    cursor.execute(
                        f'ALTER TABLE "{_table}" ALTER COLUMN "{_col}" TYPE BIGINT'
                    )
            # ─── FIN MIGRACIÓN BIGINT ─────────────────────────────────────────────────

            # ─── INICIO MIGRACIÓN BOLSA ────────────────────────────────────────────────
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS MarketAssets (
                    AssetKey VARCHAR(20) PRIMARY KEY,
                    PrecioActual NUMERIC NOT NULL,
                    UltimaActualizacion TIMESTAMP NOT NULL
                )
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS MarketPriceHistory (
                    ID SERIAL PRIMARY KEY,
                    AssetKey VARCHAR(20) NOT NULL,
                    Precio NUMERIC NOT NULL,
                    Timestamp TIMESTAMP NOT NULL
                )
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS UserPortfolio (
                    UserID BIGINT NOT NULL,
                    AssetKey VARCHAR(20) NOT NULL,
                    Cantidad NUMERIC NOT NULL DEFAULT 0,
                    CostoPromedio NUMERIC NOT NULL DEFAULT 0,
                    PRIMARY KEY (UserID, AssetKey)
                )
            """)

            # Poblar MarketAssets con los 6 activos y sus precio_inicial
            market_assets_init = [
                ("agrounion", 100.0),
                ("banconova", 150.0),
                ("tecnocorp", 80.0),
                ("obsidianchain", 50.0),
                ("bytecoin", 200.0),
                ("moontoken", 10.0),
            ]
            for asset_key, precio_inicial in market_assets_init:
                cursor.execute("""
                    INSERT INTO MarketAssets (AssetKey, PrecioActual, UltimaActualizacion)
                    VALUES (%s, %s, NOW())
                    ON CONFLICT (AssetKey) DO NOTHING
                """, (asset_key, precio_inicial))
            
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_marketpricehistory_key_timestamp
                ON MarketPriceHistory (AssetKey, Timestamp DESC)
            """)
            # ─── FIN MIGRACIÓN BOLSA ──────────────────────────────────────────────────

            # ─── FIN BANCO CENTRAL ───

            # ─── INICIO MIGRACIÓN CIRCUIT BREAKER ───
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS GameDailyStats (
                    GameKey VARCHAR(20) NOT NULL,
                    FechaDia DATE NOT NULL,
                    TotalPagado BIGINT NOT NULL DEFAULT 0,
                    PRIMARY KEY (GameKey, FechaDia)
                )
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS GameCircuitBreaker (
                    GameKey VARCHAR(20) PRIMARY KEY,
                    BloqueadoHasta TIMESTAMP DEFAULT NULL,
                    MotivoBloqueo TEXT DEFAULT NULL
                )
            """)
            # ─── FIN MIGRACIÓN CIRCUIT BREAKER ───

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS UserCampaignProgress (
                    UserID BIGINT NOT NULL,
                    ChapterID INT NOT NULL,
                    IsCompleted BOOLEAN NOT NULL DEFAULT FALSE,
                    CompletedAt TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (UserID, ChapterID)
                )
            """)


        logger.info("Todas las tablas de la base de datos se han inicializado/verificado correctamente.")
    except Exception as e:
        logger.error(f"Error inicializando las tablas de la base de datos: {e}")
        raise e

# ==========================================
# SISTEMA DE DUELOS PVP
# ==========================================

def get_combat_stats(user_id):
    """Obtiene las estadísticas de combate de un usuario. Las crea si no existen."""
    with db_cursor() as cursor:
        cursor.execute("""
            INSERT INTO CombatStats (UserID)
            VALUES (%s)
            ON CONFLICT (UserID) DO NOTHING
        """, (user_id,))
        cursor.execute("""
            SELECT CombatLevel, CombatXP, Wins, Losses, WinStreak,
                   BestWinStreak, LastDuelTime, TotalMoneyWon, TotalMoneyLost,
                   CombatClass, CombatSubclass
            FROM CombatStats WHERE UserID = %s
        """, (user_id,))
        row = cursor.fetchone()
        return {
            'level': row[0] or 1,
            'xp': row[1] or 0,
            'wins': row[2] or 0,
            'losses': row[3] or 0,
            'win_streak': row[4] or 0,
            'best_win_streak': row[5] or 0,
            'last_duel_time': row[6],
            'total_money_won': row[7] or 0,
            'total_money_lost': row[8] or 0,
            'combat_class': row[9],       # None o nombre de la clase
            'combat_subclass': row[10],   # None o nombre de la subclase
        }


def update_combat_stats_after_duel(user_id, xp_gained, is_win, money_change):
    """Actualiza las stats de combate tras un duelo, con level-up automático.

    Args:
        user_id: ID del usuario
        xp_gained: XP obtenida
        is_win: True si ganó
        money_change: monedas ganadas (positivo) o perdidas (negativo)

    Returns:
        dict con level, xp, leveled_up, previous_level, rank, xp_for_next
    """
    from src.utils.combat_progression import apply_combat_xp, get_combat_rank
    with db_cursor() as cursor:
        # Asegurar que existe
        cursor.execute("""
            INSERT INTO CombatStats (UserID)
            VALUES (%s)
            ON CONFLICT (UserID) DO NOTHING
        """, (user_id,))
        cursor.execute("""
            SELECT CombatLevel, CombatXP, WinStreak, BestWinStreak
            FROM CombatStats WHERE UserID = %s FOR UPDATE
        """, (user_id,))
        row = cursor.fetchone()
        current_level = row[0] or 1
        current_xp = row[1] or 0
        win_streak = row[2] or 0
        best_streak = row[3] or 0

        # Calcular nivel y XP
        xp_result = apply_combat_xp(current_level, current_xp, xp_gained)

        # Actualizar racha
        if is_win:
            win_streak += 1
            best_streak = max(best_streak, win_streak)
        else:
            win_streak = 0

        # Actualizar money stats
        money_won_add = money_change if money_change > 0 else 0
        money_lost_add = abs(money_change) if money_change < 0 else 0

        cursor.execute("""
            UPDATE CombatStats SET
                CombatLevel = %s,
                CombatXP = %s,
                Wins = Wins + %s,
                Losses = Losses + %s,
                WinStreak = %s,
                BestWinStreak = %s,
                LastDuelTime = CURRENT_TIMESTAMP,
                TotalMoneyWon = TotalMoneyWon + %s,
                TotalMoneyLost = TotalMoneyLost + %s
            WHERE UserID = %s
        """, (
            xp_result['level'], xp_result['xp'],
            1 if is_win else 0,
            0 if is_win else 1,
            win_streak, best_streak,
            money_won_add, money_lost_add,
            user_id
        ))

        xp_result['win_streak'] = win_streak
        xp_result['best_win_streak'] = best_streak
        return xp_result


def get_user_max_unlocked_chapter(user_id: int) -> int:
    """Retorna el número máximo de Capítulo desbloqueado para el usuario (por defecto 1)."""
    with db_cursor() as cursor:
        cursor.execute("""
            SELECT MAX(ChapterID) FROM UserCampaignProgress
            WHERE UserID = %s AND IsCompleted = TRUE
        """, (user_id,))
        row = cursor.fetchone()
        max_completed = row[0] if row and row[0] is not None else 0
        return min(10, max_completed + 1)


def complete_user_chapter(user_id: int, chapter_id: int):
    """Marca un Capítulo como completado para el usuario."""
    with db_cursor() as cursor:
        cursor.execute("""
            INSERT INTO UserCampaignProgress (UserID, ChapterID, IsCompleted, CompletedAt)
            VALUES (%s, %s, TRUE, CURRENT_TIMESTAMP)
            ON CONFLICT (UserID, ChapterID) DO UPDATE
            SET IsCompleted = TRUE, CompletedAt = CURRENT_TIMESTAMP
        """, (user_id, chapter_id))


def log_duel(challenger_id, rival_id, winner_id, bet, turns, c_level, r_level):
    """Registra un duelo en el historial."""
    with db_cursor() as cursor:
        cursor.execute("""
            INSERT INTO CombatLog (ChallengerID, RivalID, WinnerID, Bet, Turns, ChallengerLevel, RivalLevel)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, (challenger_id, rival_id, winner_id, bet, turns, c_level, r_level))


def get_user_equipment(user_id):
    """Obtiene todo el equipo de un usuario con su gema equipada si existe.

    Returns:
        dict de slot -> {item_name, rarity, item_level, primary_stat, primary_value, secondaries, passive, gem_key, gem, set_key}
    """
    with db_cursor() as cursor:
        cursor.execute("""
            SELECT ue.Slot, ue.ItemName, ue.Rarity, ue.ItemLevel, ue.PrimaryStat, ue.PrimaryValue, ue.Secondaries, ue.Passive, ue.GemKey,
                   gc.StatTarget, gc.BonusValue, gc.IsPercentage, gc.Name,
                   uic.SetKey, ue.MiniAffixKey, ue.MiniAffixValue, ue.WeaponSubtype
            FROM UserEquipment ue
            LEFT JOIN GemCatalog gc ON ue.GemKey = gc.GemKey
            LEFT JOIN UniqueItemCatalog uic ON ue.ItemName = uic.Name
            WHERE ue.UserID = %s
        """, (user_id,))
        equipment = {}
        for row in cursor.fetchall():
            gem_key = row[8]
            gem_data = None
            if gem_key:
                gem_data = {
                    'stat_target': row[9],
                    'bonus_value': float(row[10]) if row[10] is not None else 0.0,
                    'is_percentage': row[11] if row[11] is not None else False,
                    'name': row[12],
                }
            equipment[row[0]] = {
                'item_name': row[1],
                'rarity': row[2],
                'item_level': row[3],
                'primary_stat': row[4],
                'primary_value': row[5],
                'secondaries': row[6] if isinstance(row[6], list) else [],
                'passive': row[7] if isinstance(row[7], dict) else None,
                'gem_key': gem_key,
                'gem': gem_data,
                'set_key': row[13],
                'mini_affix_key': row[14],
                'mini_affix_value': float(row[15]) if row[15] is not None else None,
                'weapon_subtype': row[16],
            }
        return equipment


def get_gem_catalog():
    """Retorna todas las gemas disponibles, para mostrar en tienda."""
    with db_cursor() as cursor:
        cursor.execute("SELECT GemKey, Name, StatTarget, Tier, BonusValue, IsPercentage, Price FROM GemCatalog ORDER BY Price ASC")
        catalog = []
        for row in cursor.fetchall():
            catalog.append({
                'gem_key': row[0],
                'name': row[1],
                'stat_target': row[2],
                'tier': row[3],
                'bonus_value': float(row[4]),
                'is_percentage': row[5],
                'price': row[6]
            })
        return catalog


def insert_gem(user_id, slot, gem_key):
    """Verifica que el usuario tenga equipada una pieza en ese slot, cobra el precio de la gema
    con spend_combat_currency, y si alcanza, hace UPDATE UserEquipment SET GemKey = %s WHERE
    UserID = %s AND Slot = %s. Retorna (True, mensaje) o (False, motivo del fallo)."""
    from src.utils.combat_progression import format_currency
    with db_cursor() as cursor:
        # Verificar gema y equipamiento
        cursor.execute("SELECT Price, Name FROM GemCatalog WHERE GemKey = %s", (gem_key,))
        gem_row = cursor.fetchone()
        if not gem_row:
            return False, "La gema especificada no existe."
        gem_price, gem_name = gem_row[0], gem_row[1]

        cursor.execute("SELECT GemKey FROM UserEquipment WHERE UserID = %s AND Slot = %s", (user_id, slot))
        eq_row = cursor.fetchone()
        if not eq_row:
            return False, "No tienes ninguna pieza equipada en este slot."
        
        if eq_row[0] is not None:
            return False, "Este slot ya tiene una gema equipada. Remuévela primero."

        # Cobrar el precio de la gema
        success, current_balance = spend_combat_currency(user_id, gem_price, cursor=cursor)
        if not success:
            return False, f"No tienes suficiente Bronce. Requieres {format_currency(gem_price)} (tienes {format_currency(current_balance)})."

        # Realizar UPDATE
        cursor.execute("UPDATE UserEquipment SET GemKey = %s WHERE UserID = %s AND Slot = %s", (gem_key, user_id, slot))
        return True, f"Compraste e insertaste **{gem_name}** en tu pieza de **{slot}**."


def remove_gem(user_id, slot):
    """Cobra la mitad del precio de la gema actualmente puesta (leer su Price desde GemCatalog
    antes de cobrar), luego pone GemKey = NULL. Si no tiene gema puesta en ese slot, retorna error."""
    from src.utils.combat_progression import format_currency
    with db_cursor() as cursor:
        cursor.execute("""
            SELECT ue.GemKey, gc.Price, gc.Name
            FROM UserEquipment ue
            JOIN GemCatalog gc ON ue.GemKey = gc.GemKey
            WHERE ue.UserID = %s AND ue.Slot = %s
        """, (user_id, slot))
        row = cursor.fetchone()
        if not row or not row[0]:
            return False, "No hay ninguna gema equipada en ese slot."
        
        gem_key, price, gem_name = row[0], row[1], row[2]
        cost = price // 2

        # Cobrar la mitad del precio
        success, current_balance = spend_combat_currency(user_id, cost, cursor=cursor)
        if not success:
            return False, f"No tienes suficiente Bronce para remover la gema. Requiere {format_currency(cost)} (tienes {format_currency(current_balance)})."

        cursor.execute("UPDATE UserEquipment SET GemKey = NULL WHERE UserID = %s AND Slot = %s", (user_id, slot))
        return True, f"Removiste **{gem_name}** de tu pieza de **{slot}** por un costo de {format_currency(cost)}."


def equip_item(user_id, slot, name, rarity, item_level, primary_stat, primary_value, secondaries=None, passive=None, mini_affix_key=None, mini_affix_value=None, weapon_subtype=None):
    """Equipa un ítem en un slot (UPSERT). Retorna la pieza anterior si existía.

    Returns:
        dict de la pieza anterior o None si el slot estaba vacío
    """
    import psycopg2.extras
    if secondaries is None:
        secondaries = []
    
    with db_cursor() as cursor:
        # Obtener pieza actual
        cursor.execute("""
            SELECT ItemName, Rarity, ItemLevel, PrimaryStat, PrimaryValue, Secondaries, Passive, MiniAffixKey, MiniAffixValue, WeaponSubtype
            FROM UserEquipment WHERE UserID = %s AND Slot = %s
        """, (user_id, slot))
        old_row = cursor.fetchone()
        old_item = None
        if old_row:
            old_item = {
                'item_name': old_row[0],
                'rarity': old_row[1],
                'item_level': old_row[2],
                'primary_stat': old_row[3],
                'primary_value': old_row[4],
                'secondaries': old_row[5] if isinstance(old_row[5], list) else [],
                'passive': old_row[6] if isinstance(old_row[6], dict) else None,
                'mini_affix_key': old_row[7],
                'mini_affix_value': float(old_row[8]) if old_row[8] is not None else None,
                'weapon_subtype': old_row[9],
            }

        # UPSERT
        cursor.execute("""
            INSERT INTO UserEquipment (UserID, Slot, ItemName, Rarity, ItemLevel, PrimaryStat, PrimaryValue, Secondaries, Passive, MiniAffixKey, MiniAffixValue, WeaponSubtype)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT ON CONSTRAINT uq_user_slot
            DO UPDATE SET ItemName = EXCLUDED.ItemName,
                         Rarity = EXCLUDED.Rarity,
                         ItemLevel = EXCLUDED.ItemLevel,
                         PrimaryStat = EXCLUDED.PrimaryStat,
                         PrimaryValue = EXCLUDED.PrimaryValue,
                         Secondaries = EXCLUDED.Secondaries,
                         Passive = EXCLUDED.Passive,
                         MiniAffixKey = EXCLUDED.MiniAffixKey,
                         MiniAffixValue = EXCLUDED.MiniAffixValue,
                         WeaponSubtype = EXCLUDED.WeaponSubtype
        """, (user_id, slot, name, rarity, item_level, primary_stat, primary_value,
              psycopg2.extras.Json(secondaries), psycopg2.extras.Json(passive) if passive else None,
              mini_affix_key, mini_affix_value, weapon_subtype))

        return old_item


def get_duel_leaderboard(order_by='wins', limit=10):
    """Obtiene el ranking de duelos.

    Args:
        order_by: 'wins' o 'level'
        limit: número de resultados

    Returns:
        lista de tuplas (UserID, CombatLevel, Wins, Losses, WinStreak, BestWinStreak)
    """
    with db_cursor() as cursor:
        if order_by == 'level':
            cursor.execute("""
                SELECT UserID, CombatLevel, Wins, Losses, WinStreak, BestWinStreak
                FROM CombatStats
                WHERE Wins + Losses > 0
                ORDER BY CombatLevel DESC, CombatXP DESC
                LIMIT %s
            """, (limit,))
        else:
            cursor.execute("""
                SELECT UserID, CombatLevel, Wins, Losses, WinStreak, BestWinStreak
                FROM CombatStats
                WHERE Wins + Losses > 0
                ORDER BY Wins DESC, CombatLevel DESC
                LIMIT %s
            """, (limit,))
        return cursor.fetchall()


def actualizar_racha_trabajo(user_id, job_type):
    """
    Registra/actualiza la racha de trabajo consecutiva diaria para un oficio específico.
    Retorna un diccionario con 'racha' y 'es_nueva_hoy'.
    """
    from datetime import datetime, timedelta
    
    today = datetime.now().date()
    
    with db_cursor() as cursor:
        cursor.execute("""
            INSERT INTO joblevels (UserId, JobType, CompletedJobs, Level, Experience, Streak)
            VALUES (%s, %s, 0, 0, 0, 0)
            ON CONFLICT (UserId, JobType) DO NOTHING
        """, (user_id, job_type))
        
        cursor.execute("""
            SELECT LastJobTime, Streak FROM joblevels 
            WHERE UserId = %s AND JobType = %s FOR UPDATE
        """, (user_id, job_type))
        row = cursor.fetchone()
        
        last_job_time, streak = None, 0
        if row:
            last_job_time, streak = row[0], row[1] or 0
            
        if last_job_time:
            last_job_date = last_job_time.date()
        else:
            last_job_date = None
            
        es_nueva_hoy = False
        
        if last_job_date == today:
            # Ya trabajó hoy, la racha se mantiene igual
            es_nueva_hoy = False
        elif last_job_date and (today - last_job_date).days == 1:
            # Trabajó ayer, incrementa racha
            streak += 1
            es_nueva_hoy = True
        else:
            # Primera vez o pasaron más días, reinicia racha a 1
            streak = 1
            es_nueva_hoy = True
            
        cursor.execute("""
            UPDATE joblevels 
            SET LastJobTime = %s, Streak = %s 
            WHERE UserId = %s AND JobType = %s
        """, (datetime.now(), streak, user_id, job_type))
        
        return {
            "racha": streak,
            "es_nueva_hoy": es_nueva_hoy
        }

def obtener_ranking_trabajo(job_type, limit=10):
    """
    Obtiene el ranking de los mejores jugadores en un oficio específico,
    ordenado por nivel, luego experiencia y luego trabajos completados.
    """
    with db_cursor() as cursor:
        cursor.execute("""
            SELECT UserId, Level, Experience, CompletedJobs
            FROM joblevels
            WHERE JobType = %s
            ORDER BY Level DESC, Experience DESC, CompletedJobs DESC
            LIMIT %s
        """, (job_type, limit))
        return cursor.fetchall()

# Alias for compatibility with Mejoras files
consumir_energia_atomico = consumir_energia


def process_crash_payout_atomic(user_id, apuesta, ganancia_total, ganancia_neta, result_type, difficulty_modifier, nuevo_saldo, desc_transaccion):
    """
    Registra el balance, la transacción y el resultado del juego en una única transacción de BD atómica.
    """
    with db_cursor() as cursor:
        add_balance(user_id, ganancia_total, cursor=cursor)
        registrar_transaccion(user_id, ganancia_neta, desc_transaccion, cursor=cursor)
        record_game_result(user_id, 'crash', apuesta, result_type, ganancia_neta, difficulty_modifier, nuevo_saldo, cursor=cursor)


def is_user_ignored(user_id: int) -> bool:
    """Verifica si un usuario está en la lista de ignorados."""
    try:
        with db_cursor() as cursor:
            cursor.execute("SELECT 1 FROM IgnoredUsers WHERE UserID = %s", (user_id,))
            return cursor.fetchone() is not None
    except Exception as e:
        logger.error(f"Error checking if user {user_id} is ignored: {e}")
        return False


def add_ignored_user(user_id: int) -> bool:
    """Añade un usuario a la lista de ignorados (evita duplicados)."""
    try:
        with db_cursor() as cursor:
            cursor.execute("""
                INSERT INTO IgnoredUsers (UserID) VALUES (%s)
                ON CONFLICT (UserID) DO NOTHING
            """, (user_id,))
            return True
    except Exception as e:
        logger.error(f"Error adding user {user_id} to ignored list: {e}")
        return False


def remove_ignored_user(user_id: int) -> bool:
    """Elimina un usuario de la lista de ignorados."""
    try:
        with db_cursor() as cursor:
            cursor.execute("DELETE FROM IgnoredUsers WHERE UserID = %s", (user_id,))
            return True
    except Exception as e:
        logger.error(f"Error removing user {user_id} from ignored list: {e}")
        return False


def get_all_ignored_users() -> list[int]:
    """Obtiene la lista de IDs de todos los usuarios ignorados."""
    try:
        with db_cursor() as cursor:
            cursor.execute("SELECT UserID FROM IgnoredUsers")
            return [row[0] for row in cursor.fetchall()]
    except Exception as e:
        logger.error(f"Error getting ignored users list: {e}")
        return []


def reset_user_daily_usage(user_id: int, item_id: int = None) -> bool:
    """Resetea los límites/tickets diarios de un usuario eliminando sus registros en DailyItemUsage."""
    try:
        with db_cursor() as cursor:
            if item_id is not None:
                cursor.execute("""
                    DELETE FROM DailyItemUsage 
                    WHERE UserID = %s AND ItemID = %s
                """, (user_id, item_id))
            else:
                cursor.execute("""
                    DELETE FROM DailyItemUsage 
                    WHERE UserID = %s
                """, (user_id,))
            return True
    except Exception as e:
        logger.error(f"Error resetting daily usage for user {user_id}: {e}")
        return False


def update_user_class(user_id: int, class_name: str) -> bool:
    """Actualiza la clase de combate de un usuario."""
    try:
        with db_cursor() as cursor:
            cursor.execute("""
                UPDATE CombatStats 
                SET CombatClass = %s 
                WHERE UserID = %s
            """, (class_name, user_id))
            return True
    except Exception as e:
        logger.error(f"Error updating user class for user {user_id}: {e}")
        return False


def update_user_subclass(user_id: int, subclass_name: str) -> bool:
    """Actualiza la subclase de combate de un usuario."""
    try:
        with db_cursor() as cursor:
            cursor.execute("""
                UPDATE CombatStats 
                SET CombatSubclass = %s 
                WHERE UserID = %s
            """, (subclass_name, user_id))
            return True
    except Exception as e:
        logger.error(f"Error updating user subclass for user {user_id}: {e}")
        return False


def update_user_class_and_subclass(user_id: int, class_name: str, subclass_name: str | None) -> bool:
    """Actualiza clase y subclase de combate en una sola operación."""
    try:
        with db_cursor() as cursor:
            cursor.execute("""
                UPDATE CombatStats 
                SET CombatClass = %s, CombatSubclass = %s 
                WHERE UserID = %s
            """, (class_name, subclass_name, user_id))
            return True
    except Exception as e:
        logger.error(f"Error updating user class/subclass for user {user_id}: {e}")
        return False


def ensure_consumables_catalog_seeded(cursor=None):
    items = [
        ("pocion_curacion", "Poción de Curación", "Cura un 25% del HP máximo del usuario.", 150),
        ("pergamino_purificacion", "Pergamino de Purificación", "Limpia todos los debuffs y DoTs del usuario.", 200),
        ("bomba_humo", "Bomba de Humo", "Esquiva con 100% de certeza el próximo ataque recibido.", 250),
        ("frasco_silencio", "Frasco de Silencio", "Silencia las habilidades especiales del objetivo por 2 turnos.", 200),
        ("pocion_curacion_colectiva", "Poción de Curación Colectiva", "Cura un 30% del HP Máximo a todo el grupo en Raid o Aventura.", 300),
        ("totem_baluarte", "Tótem de Baluarte", "Confiere un escudo de absorción del 20% HP a todo el equipo.", 500),
        ("pergamino_purificacion_grupo", "Pergamino de Purificación de Grupo", "Limpia todos los debuffs y DoTs de la party.", 400),
        ("elixir_ultimate", "Elixir de Carga de Ultimate", "Suma +30% de carga a la barra de Ultimate de Equipo.", 650),
        ("manjar_companero", "Manjar del Compañero", "Restaura la lealtad de la mascota al 100% y le otorga +25% Bronce en Aventura.", 350)
    ]
    def _run(c):
        for key, name, desc, price in items:
            c.execute("""
                INSERT INTO ConsumableCatalog (ConsumableKey, Name, Description, Price)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (ConsumableKey) DO NOTHING
            """, (key, name, desc, price))

    if cursor:
        _run(cursor)
    else:
        with db_cursor() as c:
            _run(c)

def get_user_combat_level(user_id: int) -> int:
    """Obtiene el nivel de combate del usuario."""
    stats = get_combat_stats(user_id)
    return stats.get('level', 1)

def get_user_pets(user_id: int):
    """Obtiene todas las mascotas registradas del usuario."""
    with db_cursor() as cursor:
        cursor.execute("""
            SELECT up.*, pc.Name as name, pc.Emoji as emoji, pc.Rarity as rarity, pc.FlavorText as flavor_text
            FROM UserPets up
            JOIN PetsCatalog pc ON up.PetID = pc.PetID
            WHERE up.UserID = %s AND up.Status != 'Escapó'
        """, (user_id,))
        columns = [desc[0] for desc in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]

def get_consumable_catalog():

    """Retorna los consumibles disponibles en el catálogo."""
    ensure_consumables_catalog_seeded()
    with db_cursor() as cursor:
        cursor.execute("SELECT ConsumableKey, Name, Description, Price FROM ConsumableCatalog ORDER BY Price ASC")
        catalog = []
        for row in cursor.fetchall():
            catalog.append({
                'consumable_key': row[0],
                'name': row[1],
                'description': row[2],
                'price': row[3]
            })
        return catalog



def buy_consumable(user_id, consumable_key, quantity=1):
    """Cobra Price * quantity con spend_combat_currency; si alcanza, hace
    INSERT ... ON CONFLICT (UserID, ConsumableKey) DO UPDATE SET Quantity = Quantity + quantity.
    Retorna (True, mensaje) o (False, motivo)."""
    if quantity <= 0:
        return False, "La cantidad debe ser mayor a 0."

    from src.utils.combat_progression import format_currency
    with db_cursor() as cursor:
        cursor.execute("SELECT Price, Name FROM ConsumableCatalog WHERE ConsumableKey = %s", (consumable_key,))
        row = cursor.fetchone()
        if not row:
            return False, "El consumible especificado no existe."
        price, name = row[0], row[1]
        total_cost = price * quantity

        # Cobrar total
        success, current_balance = spend_combat_currency(user_id, total_cost, cursor=cursor)
        if not success:
            return False, f"No tienes suficiente Bronce. Requieres {format_currency(total_cost)} (tienes {format_currency(current_balance)})."

        cursor.execute("""
            INSERT INTO UserConsumables (UserID, ConsumableKey, Quantity)
            VALUES (%s, %s, %s)
            ON CONFLICT (UserID, ConsumableKey)
            DO UPDATE SET Quantity = UserConsumables.Quantity + EXCLUDED.Quantity
        """, (user_id, consumable_key, quantity))
        return True, f"Compraste {quantity}x **{name}** por {format_currency(total_cost)}."


def get_user_consumables(user_id):
    """Retorna dict {ConsumableKey: Quantity} de lo que tiene el usuario."""
    with db_cursor() as cursor:
        cursor.execute("SELECT ConsumableKey, Quantity FROM UserConsumables WHERE UserID = %s", (user_id,))
        res = {}
        for row in cursor.fetchall():
            if row[1] > 0:
                res[row[0]] = row[1]
        return res


def use_consumable(user_id, consumable_key):
    """Descuenta 1 unidad de forma atómica.
    Retorna True si tenía al menos 1 y se descontó, False si no tenía."""
    with db_cursor() as cursor:
        cursor.execute("""
            UPDATE UserConsumables
            SET Quantity = Quantity - 1
            WHERE UserID = %s AND ConsumableKey = %s AND Quantity > 0
            RETURNING Quantity
        """, (user_id, consumable_key))
        row = cursor.fetchone()
        return row is not None


def buy_consumable_discounted(user_id, consumable_key, discounted_price):
    """Cobra discounted_price con spend_combat_currency de forma atómica y añade 1 consumable."""
    from src.utils.combat_progression import format_currency
    with db_cursor() as cursor:
        cursor.execute("SELECT Name FROM ConsumableCatalog WHERE ConsumableKey = %s", (consumable_key,))
        row = cursor.fetchone()
        if not row:
            return False, "El consumible especificado no existe."
        name = row[0]

        # Cobrar
        success, current_balance = spend_combat_currency(user_id, discounted_price, cursor=cursor)
        if not success:
            return False, f"No tienes suficiente Bronce. Requieres {format_currency(discounted_price)} (tienes {format_currency(current_balance)})."

        cursor.execute("""
            INSERT INTO UserConsumables (UserID, ConsumableKey, Quantity)
            VALUES (%s, %s, 1)
            ON CONFLICT (UserID, ConsumableKey)
            DO UPDATE SET Quantity = UserConsumables.Quantity + EXCLUDED.Quantity
        """, (user_id, consumable_key))
        return True, f"Compraste 1x **{name}** por {format_currency(discounted_price)}."


def insert_gem_discounted(user_id, slot, gem_key, discounted_price):
    """Verifica el slot y gem_key, cobra discounted_price y realiza la inserción de la gema."""
    from src.utils.combat_progression import format_currency
    with db_cursor() as cursor:
        cursor.execute("SELECT Name FROM GemCatalog WHERE GemKey = %s", (gem_key,))
        gem_row = cursor.fetchone()
        if not gem_row:
            return False, "La gema especificada no existe."
        gem_name = gem_row[0]

        cursor.execute("SELECT GemKey FROM UserEquipment WHERE UserID = %s AND Slot = %s", (user_id, slot))
        eq_row = cursor.fetchone()
        if not eq_row:
            return False, "No tienes ninguna pieza equipada en este slot."
        
        if eq_row[0] is not None:
            return False, "Este slot ya tiene una gema equipada. Remuévela primero."

        # Cobrar
        success, current_balance = spend_combat_currency(user_id, discounted_price, cursor=cursor)
        if not success:
            return False, f"No tienes suficiente Bronce. Requieres {format_currency(discounted_price)} (tienes {format_currency(current_balance)})."

        cursor.execute("UPDATE UserEquipment SET GemKey = %s WHERE UserID = %s AND Slot = %s", (gem_key, user_id, slot))
        return True, f"Compraste e insertaste **{gem_name}** en tu pieza de **{slot}** por {format_currency(discounted_price)}."


# ==========================================
# BANCO CENTRAL — FUNCIONES DE BASE DE DATOS
# ==========================================

def get_bank_reserves() -> int:
    """Retorna el total de Reservas del Banco Central."""
    with db_cursor() as cursor:
        cursor.execute("SELECT Reservas FROM BancoCentral WHERE ID = 1")
        row = cursor.fetchone()
        return row[0] if row else 0


def add_to_bank_reserves(amount: int, cursor=None) -> None:
    """Suma `amount` a las Reservas del Banco Central.
    Acepta un cursor externo para operar dentro de una transacción mayor.
    Puede usarse con amount negativo para descontar reservas."""
    query = "UPDATE BancoCentral SET Reservas = Reservas + %s WHERE ID = 1"
    if cursor is not None:
        cursor.execute(query, (amount,))
    else:
        with db_cursor() as cursor:
            cursor.execute(query, (amount,))


def get_user_loan(user_id, slot: int = 1) -> dict | None:
    """Retorna el préstamo activo del usuario como dict en el slot especificado, o None si no tiene.
    Campos: MontoAdeudado, FechaPrestamo, FechaVencimiento, LimitePrestamo,
            PrestamosPagadosATiempo, EnMora, LoanSlot."""
    with db_cursor() as cursor:
        cursor.execute("""
            SELECT MontoAdeudado, FechaPrestamo, FechaVencimiento,
                   LimitePrestamo, PrestamosPagadosATiempo, EnMora, LoanSlot
            FROM UserLoans WHERE UserID = %s AND LoanSlot = %s
        """, (user_id, slot))
        row = cursor.fetchone()
        if not row:
            return None
        return {
            'MontoAdeudado': row[0],
            'FechaPrestamo': row[1],
            'FechaVencimiento': row[2],
            'LimitePrestamo': row[3],
            'PrestamosPagadosATiempo': row[4],
            'EnMora': row[5],
            'LoanSlot': row[6] if len(row) > 6 else 1,
        }


def get_all_user_loans(user_id) -> list:
    """Retorna todos los préstamos del usuario como una lista de dicts."""
    with db_cursor() as cursor:
        cursor.execute("""
            SELECT MontoAdeudado, FechaPrestamo, FechaVencimiento,
                   LimitePrestamo, PrestamosPagadosATiempo, EnMora, LoanSlot
            FROM UserLoans WHERE UserID = %s ORDER BY LoanSlot ASC
        """, (user_id,))
        rows = cursor.fetchall()
        loans = []
        for row in rows:
            loans.append({
                'MontoAdeudado': row[0],
                'FechaPrestamo': row[1],
                'FechaVencimiento': row[2],
                'LimitePrestamo': row[3],
                'PrestamosPagadosATiempo': row[4],
                'EnMora': row[5],
                'LoanSlot': row[6],
            })
        return loans


def pagar_recompensa_trabajo(user_id, recompensa_bruta: int, tipo_trabajo: str) -> tuple:
    """Paga la recompensa de un trabajo al usuario, aplicando retención del 10%
    si el usuario está EnMora. Registra la transacción internamente.

    Returns:
        (neto_pagado, retencion_aplicada): ambos int.
        Si no hay mora, retencion_aplicada = 0 y neto_pagado = recompensa_bruta.
    """
    from datetime import datetime
    
    # Aplicar bonus de Corona (+5% ingresos por trabajo) si tiene la mejora 10
    if usuario_tiene_mejora(user_id, 10):
        recompensa_bruta = int(recompensa_bruta * 1.05)

    with db_cursor() as cursor:
        # Verificar si cualquiera de los slots del usuario está en mora
        cursor.execute(
            "SELECT EXISTS(SELECT 1 FROM UserLoans WHERE UserID = %s AND EnMora = TRUE)",
            (user_id,)
        )
        row = cursor.fetchone()
        en_mora = row[0] if row else False

        if en_mora and recompensa_bruta > 0:
            retencion = max(1, int(recompensa_bruta * 0.10))
            neto = recompensa_bruta - retencion

            # Acreditar neto al usuario
            cursor.execute("""
                INSERT INTO Users (UserID, Balance) VALUES (%s, %s)
                ON CONFLICT (UserID) DO UPDATE SET Balance = Users.Balance + EXCLUDED.Balance
            """, (user_id, neto))

            # Registrar pago neto
            cursor.execute("""
                INSERT INTO Transactions (UserID, Amount, TransactionType, Date)
                VALUES (%s, %s, %s, %s)
            """, (user_id, neto, f"Trabajo: {tipo_trabajo} (mora: -{retencion} retenidos)", datetime.now()))

            # Obtener préstamos en mora activos ordenados por LoanSlot
            cursor.execute("""
                SELECT LoanSlot FROM UserLoans 
                WHERE UserID = %s AND EnMora = TRUE AND MontoAdeudado > 0
                ORDER BY LoanSlot ASC
            """)
            mora_loans = cursor.fetchall()
            if mora_loans:
                target_slot = mora_loans[0][0]
                # Aplicar retención al préstamo seleccionado
                cursor.execute("""
                    UPDATE UserLoans
                    SET MontoAdeudado = GREATEST(0, MontoAdeudado - %s)
                    WHERE UserID = %s AND LoanSlot = %s
                    RETURNING MontoAdeudado
                """, (retencion, user_id, target_slot))
                row_loan = cursor.fetchone()
                nuevo_monto = row_loan[0] if row_loan else 0

                if nuevo_monto <= 0:
                    cursor.execute("""
                        UPDATE UserLoans
                        SET FechaPrestamo = NULL,
                            FechaVencimiento = NULL,
                            EnMora = FALSE
                        WHERE UserID = %s AND LoanSlot = %s
                    """, (user_id, target_slot))

            cursor.execute(
                "UPDATE BancoCentral SET Reservas = Reservas + %s WHERE ID = 1",
                (retencion,)
            )
        else:
            retencion = 0
            neto = recompensa_bruta

            cursor.execute("""
                INSERT INTO Users (UserID, Balance) VALUES (%s, %s)
                ON CONFLICT (UserID) DO UPDATE SET Balance = Users.Balance + EXCLUDED.Balance
            """, (user_id, neto))

            cursor.execute("""
                INSERT INTO Transactions (UserID, Amount, TransactionType, Date)
                VALUES (%s, %s, %s, %s)
            """, (user_id, neto, f"Trabajo: {tipo_trabajo} completado", datetime.now()))

    return neto, retencion


def get_user_protection_info(user_id) -> tuple:
    """Retorna (UltimoPago, UltimoMonto) de CuotaProteccion para un usuario.
    Si no existe registro, retorna (None, 0)."""
    with db_cursor() as cursor:
        cursor.execute("SELECT UltimoPago, UltimoMonto FROM CuotaProteccion WHERE UserID = %s", (user_id,))
        row = cursor.fetchone()
        if not row:
            return None, 0
        return row[0], row[1]


def cobrar_cuotas_proteccion_db() -> list:
    """Cobra la cuota de protección diaria a todos los usuarios con balance > 500k.
    Calcula de manera progresiva sobre el excedente de 500k.
    Envía lo recaudado a las reservas del Banco Central.
    Actualiza la tabla CuotaProteccion con UltimoPago y UltimoMonto si pagó completo.
    Retorna la lista de cobros realizados.
    """
    resultados = []
    
    with db_cursor() as cursor:
        cursor.execute("""
            SELECT u.UserID, u.Balance, COALESCE(up.PrestigeLevel, 0)
            FROM Users u
            LEFT JOIN UserPrestige up ON u.UserID = up.UserID
            WHERE u.Balance > 500000 FOR UPDATE OF u
        """)
        usuarios = cursor.fetchall()
        
        for user_id, balance, prestige_level in usuarios:
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
                
            if prestige_level >= 2:
                # Aplicar 20% descuento -> multiplicar por 8000 bps (80%)
                cuota = (cuota * 8000) // 10000
                
            if cuota <= 0:
                continue
                
            cobrado = min(cuota, balance)
            exito = (cobrado == cuota)
            nuevo_balance = balance - cobrado
            
            # Descontar saldo
            cursor.execute("UPDATE Users SET Balance = %s WHERE UserID = %s", (nuevo_balance, user_id))
            
            # Registrar transacción
            cursor.execute("""
                INSERT INTO Transactions (UserID, Amount, TransactionType, Date)
                VALUES (%s, %s, %s, CURRENT_TIMESTAMP)
            """, (user_id, -cobrado, f"Cuota de Protección: {'completa' if exito else 'parcial'}"))
            
            # Enviar a reservas del Banco Central
            cursor.execute("UPDATE BancoCentral SET Reservas = Reservas + %s WHERE ID = 1", (cobrado,))
            
            # Si se cobró completo, registrar en CuotaProteccion
            if exito:
                cursor.execute("""
                    INSERT INTO CuotaProteccion (UserID, UltimoPago, UltimoMonto)
                    VALUES (%s, CURRENT_TIMESTAMP, %s)
                    ON CONFLICT (UserID) DO UPDATE 
                    SET UltimoPago = CURRENT_TIMESTAMP, UltimoMonto = %s
                """, (user_id, cobrado, cobrado))
                
            resultados.append({
                'user_id': user_id,
                'cobrado': cobrado,
                'exito': exito,
                'nuevo_saldo': nuevo_balance
            })
            
    return resultados


def get_user_prestige_level(user_id) -> int:
    """Retorna el PrestigeLevel actual del usuario, o 0 si no tiene registro."""
    with db_cursor() as cursor:
        cursor.execute("SELECT PrestigeLevel FROM UserPrestige WHERE UserID = %s", (user_id,))
        row = cursor.fetchone()
        if not row:
            return 0
        val = row[0]
        if hasattr(val, '__class__') and val.__class__.__name__ == 'MagicMock':
            return 0
        try:
            return int(val)
        except (ValueError, TypeError):
            return 0


def set_user_prestige_db(user_id, level: int) -> None:
    """Establece el PrestigeLevel del usuario y actualiza FechaUltimoPrestigio."""
    with db_cursor() as cursor:
        cursor.execute("""
            INSERT INTO UserPrestige (UserID, PrestigeLevel, FechaUltimoPrestigio)
            VALUES (%s, %s, CURRENT_TIMESTAMP)
            ON CONFLICT (UserID) DO UPDATE 
            SET PrestigeLevel = EXCLUDED.PrestigeLevel, FechaUltimoPrestigio = CURRENT_TIMESTAMP
        """, (user_id, level))


def _ensure_flex_message_column() -> None:
    """Migración idempotente: añade FlexMessage a UserPrestige si no existe."""
    with db_cursor() as cursor:
        cursor.execute("""
            ALTER TABLE UserPrestige
            ADD COLUMN IF NOT EXISTS FlexMessage VARCHAR(100)
        """)


def get_flex_message(user_id) -> str | None:
    """Retorna el mensaje Flex personalizado del usuario, o None si no tiene."""
    _ensure_flex_message_column()
    with db_cursor() as cursor:
        cursor.execute(
            "SELECT FlexMessage FROM UserPrestige WHERE UserID = %s",
            (user_id,)
        )
        row = cursor.fetchone()
        return row[0] if row else None


def set_flex_message(user_id, mensaje: str) -> None:
    """Guarda o actualiza el mensaje Flex personalizado del usuario (máx. 100 chars)."""
    _ensure_flex_message_column()
    mensaje = mensaje[:100]
    with db_cursor() as cursor:
        cursor.execute("""
            INSERT INTO UserPrestige (UserID, PrestigeLevel, FlexMessage)
            VALUES (%s, 0, %s)
            ON CONFLICT (UserID) DO UPDATE
            SET FlexMessage = EXCLUDED.FlexMessage
        """, (user_id, mensaje))


def set_robar_shield(user_id):
    """Establece un escudo contra robos de 24 horas para el usuario."""
    from datetime import datetime, timedelta
    expiry = datetime.now() + timedelta(days=1)
    with db_cursor() as cursor:
        cursor.execute("""
            INSERT INTO RoboStats (UserID, ShieldExpiry)
            VALUES (%s, %s)
            ON CONFLICT (UserID) DO UPDATE
            SET ShieldExpiry = EXCLUDED.ShieldExpiry
        """, (user_id, expiry))
    return expiry


def get_robar_shield_expiry(user_id):
    """Retorna la fecha de expiración del escudo de robo del usuario, o None si no tiene."""
    with db_cursor() as cursor:
        cursor.execute("SELECT ShieldExpiry FROM RoboStats WHERE UserID = %s", (user_id,))
        row = cursor.fetchone()
        return row[0] if row else None


def pagar_bonos_prestigio_mensuales_db() -> list:
    """
    Busca usuarios con PrestigeLevel >= 3.
    Para cada uno, si UltimoBonoMensual es NULL o han pasado al menos 30 días,
    acredita 100,000 monedas, registra la transacción y actualiza UltimoBonoMensual.
    Retorna una lista de diccionarios con la información de los pagos realizados.
    """
    from datetime import datetime, timedelta
    ahora = datetime.now()
    resultados = []
    
    with db_cursor() as cursor:
        cursor.execute("""
            SELECT UserID, PrestigeLevel, UltimoBonoMensual 
            FROM UserPrestige 
            WHERE PrestigeLevel >= 3
        """)
        candidatos = cursor.fetchall()
        
        for user_id, lvl, ultimo_pago in candidatos:
            debiera_pagar = False
            if ultimo_pago is None:
                debiera_pagar = True
            else:
                if ultimo_pago.tzinfo is not None:
                    ultimo_pago = ultimo_pago.replace(tzinfo=None)
                if ahora - ultimo_pago >= timedelta(days=30):
                    debiera_pagar = True
            
            if debiera_pagar:
                add_balance(user_id, 100000, cursor=cursor)
                registrar_transaccion(user_id, 100000, f"Bono Mensual Prestigio (Nivel {lvl})", cursor=cursor)
                cursor.execute("""
                    UPDATE UserPrestige 
                    SET UltimoBonoMensual = %s 
                    WHERE UserID = %s
                """, (ahora, user_id))
                
                resultados.append({
                    'user_id': user_id,
                    'monto': 100000,
                    'prestige_level': lvl,
                    'ultimo_pago_previo': ultimo_pago
                })
                
    return resultados


def start_investment_db(user_id: int, amount: int) -> InvestmentStartResult:
    """Operación de DB para iniciar una inversión. Bloqueante."""
    from datetime import datetime, timedelta
    
    with db_cursor() as cursor:
        # 1. Verificar si tiene inversión activa (Resuelto = False)
        cursor.execute("""
            SELECT Monto, FechaInicio, FechaVencimiento, Resuelto 
            FROM UserInvestments 
            WHERE UserID = %s AND Resuelto = FALSE
        """, (user_id,))
        active_inv = cursor.fetchone()
        if active_inv:
            return InvestmentStartResult(
                success=False,
                user_id=user_id,
                amount=amount,
                reason="ACTIVE_INVESTMENT_EXISTS"
            )
            
        # 2. Verificar si está en mora en algún préstamo
        cursor.execute("SELECT 1 FROM UserLoans WHERE UserID = %s AND EnMora = TRUE", (user_id,))
        if cursor.fetchone():
            return InvestmentStartResult(
                success=False,
                user_id=user_id,
                amount=amount,
                reason="IN_MORA"
            )
            
        # 3. Verificar saldo suficiente
        cursor.execute("SELECT Balance FROM Users WHERE UserID = %s FOR UPDATE", (user_id,))
        bal_row = cursor.fetchone()
        balance = bal_row[0] if bal_row else 0
        if balance < amount:
            return InvestmentStartResult(
                success=False,
                user_id=user_id,
                amount=amount,
                new_balance=balance,
                reason="INSUFFICIENT_FUNDS"
            )
            
        # 4. Descontar saldo
        cursor.execute("UPDATE Users SET Balance = Balance - %s WHERE UserID = %s RETURNING Balance", (amount, user_id))
        row = cursor.fetchone()
        if not row:
            return InvestmentStartResult(
                success=False,
                user_id=user_id,
                amount=amount,
                reason="DB_ERROR"
            )
        new_balance = row[0]
            
        # 5. Insertar / Upsert inversión
        ahora = datetime.now()
        vencimiento = ahora + timedelta(days=7)
        cursor.execute("""
            INSERT INTO UserInvestments (UserID, Monto, FechaInicio, FechaVencimiento, Resuelto)
            VALUES (%s, %s, %s, %s, FALSE)
            ON CONFLICT (UserID) DO UPDATE
            SET Monto = EXCLUDED.Monto,
                FechaInicio = EXCLUDED.FechaInicio,
                FechaVencimiento = EXCLUDED.FechaVencimiento,
                Resuelto = FALSE
        """, (user_id, amount, ahora, vencimiento))
        
        # Registrar transacción
        registrar_transaccion(user_id, -amount, "Banco Central: Inversión", cursor=cursor)
        
        return InvestmentStartResult(
            success=True,
            user_id=user_id,
            amount=amount,
            new_balance=new_balance,
            started_at=ahora,
            vencimiento=vencimiento
        )


def resolve_matured_investments_db() -> dict:
    """Operación de DB para resolver inversiones vencidas. Bloqueante."""
    from datetime import datetime
    import random
    
    ahora = datetime.now()
    resolved_list = []
    total_payout = 0
    
    with db_cursor() as cursor:
        cursor.execute("""
            SELECT UserID, Monto, FechaInicio, FechaVencimiento
            FROM UserInvestments
            WHERE Resuelto = FALSE AND FechaVencimiento <= %s
        """, (ahora,))
        matured = cursor.fetchall()
        
        outcomes = [
            (0.85, "Pérdida grande"),
            (0.95, "Pérdida pequeña"),
            (1.00, "Neutro"),
            (1.08, "Ganancia pequeña"),
            (1.20, "Ganancia grande"),
        ]
        weights = [15, 25, 20, 25, 15]
        
        for user_id, monto, inicio, venc in matured:
            seed_str = f"{user_id}:{monto}:{inicio.isoformat()}"
            seed_hash = hashlib.sha256(seed_str.encode('utf-8')).hexdigest()
            seed_int = int(seed_hash, 16) % (2**32)
            
            local_rng = random.Random(seed_int)
            outcome = local_rng.choices(outcomes, weights=weights, k=1)[0]
            mult, label = outcome
            
            payout = int(monto * mult)
            diff = payout - monto
            total_payout += payout
            
            # Acreditar al balance
            cursor.execute("""
                INSERT INTO Users (UserID, Balance) VALUES (%s, %s)
                ON CONFLICT (UserID) DO UPDATE SET Balance = Users.Balance + EXCLUDED.Balance
            """, (user_id, payout))
            
            # Registrar transacción
            registrar_transaccion(user_id, payout, f"Inversión vencida: {label} (x{mult})", cursor=cursor)
            
            # Marcar como resuelto
            cursor.execute("UPDATE UserInvestments SET Resuelto = TRUE WHERE UserID = %s", (user_id,))
            
            resolved_list.append({
                'user_id': user_id,
                'monto_inicial': monto,
                'payout': payout,
                'diff': diff,
                'mult': mult,
                'label': label
            })
            
    return {
        'count': len(matured),
        'total_payout': total_payout,
        'results': resolved_list
    }


def get_active_investment_db(user_id: int) -> dict | None:
    """Operación de DB para obtener la inversión activa de un usuario."""
    with db_cursor() as cursor:
        cursor.execute("""
            SELECT Monto, FechaInicio, FechaVencimiento, Resuelto
            FROM UserInvestments
            WHERE UserID = %s AND Resuelto = FALSE
        """, (user_id,))
        row = cursor.fetchone()
        if row:
            return {
                'Monto': row[0],
                'FechaInicio': row[1],
                'FechaVencimiento': row[2],
                'Resuelto': row[3]
            }
        return None


# =======================================================
# SISTEMA DE BANCO: DEPOSITOS, RETIROS Y COMISION DIARIA
# =======================================================

def get_bank_balance(user_id: int) -> int:
    """Obtiene el saldo bancario actual de un usuario."""
    with db_cursor() as cursor:
        cursor.execute("SELECT BankBalance FROM Users WHERE UserID = %s", (user_id,))
        row = cursor.fetchone()
        return row[0] if row and row[0] is not None else 0


def deposit_to_bank_db(user_id: int, amount: int) -> Tuple[bool, str, int, int]:
    """Realiza el depósito de dinero al banco. Retorna (success, message, new_cash, new_bank)."""
    if amount <= 0:
        return False, "❌ El monto a depositar debe ser mayor a 0.", 0, 0
    
    with db_cursor() as cursor:
        cursor.execute("SELECT Balance, BankBalance FROM Users WHERE UserID = %s FOR UPDATE", (user_id,))
        row = cursor.fetchone()
        if not row:
            return False, "❌ Usuario no encontrado.", 0, 0
        
        cash, bank = row[0], row[1] or 0
        if cash < amount:
            return False, f"❌ No tienes suficiente saldo en mano para depositar **{amount:,}** monedas. Saldo en mano: **{cash:,}**.", cash, bank
        
        new_cash = cash - amount
        new_bank = bank + amount
        
        cursor.execute("UPDATE Users SET Balance = %s, BankBalance = %s WHERE UserID = %s", (new_cash, new_bank, user_id))
        cursor.execute("UPDATE BancoCentral SET Reservas = Reservas + %s WHERE ID = 1", (amount,))
        
        from datetime import datetime
        cursor.execute("""
            INSERT INTO Transactions (UserID, Amount, TransactionType, Date)
            VALUES (%s, %s, 'Depósito Bancario', %s)
        """, (user_id, -amount, datetime.now()))
        
        return True, f"✅ Has depositado **{amount:,}** monedas en tu cuenta bancaria.", new_cash, new_bank


def withdraw_from_bank_db(user_id: int, amount: int) -> Tuple[bool, str, int, int]:
    """Realiza el retiro de dinero del banco. Retorna (success, message, new_cash, new_bank)."""
    if amount <= 0:
        return False, "❌ El monto a retirar debe ser mayor a 0.", 0, 0
    
    with db_cursor() as cursor:
        cursor.execute("SELECT Balance, BankBalance FROM Users WHERE UserID = %s FOR UPDATE", (user_id,))
        row = cursor.fetchone()
        if not row:
            return False, "❌ Usuario no encontrado.", 0, 0
        
        cash, bank = row[0], row[1] or 0
        if bank < amount:
            return False, f"❌ No tienes suficiente saldo en el banco para retirar **{amount:,}** monedas. Saldo en banco: **{bank:,}**.", cash, bank
        
        cursor.execute("SELECT Reservas FROM BancoCentral WHERE ID = 1 FOR UPDATE")
        banco_row = cursor.fetchone()
        reservas = banco_row[0] if banco_row else 0
        
        if reservas < amount:
            return False, (
                f"❌ El Banco Central no tiene suficientes reservas físicas en este momento para procesar tu retiro completo (crisis de liquidez).\n"
                f"🏦 Reservas en bóveda: **{reservas:,}** monedas.\n"
                f"💡 Puedes retirar hasta **{reservas:,}** monedas o esperar a que otros usuarios depositen o paguen sus préstamos."
            ), cash, bank
        
        new_cash = cash + amount
        new_bank = bank - amount
        
        cursor.execute("UPDATE Users SET Balance = %s, BankBalance = %s WHERE UserID = %s", (new_cash, new_bank, user_id))
        cursor.execute("UPDATE BancoCentral SET Reservas = Reservas - %s WHERE ID = 1", (amount,))
        
        from datetime import datetime
        cursor.execute("""
            INSERT INTO Transactions (UserID, Amount, TransactionType, Date)
            VALUES (%s, %s, 'Retiro Bancario', %s)
        """, (user_id, amount, datetime.now()))
        
        return True, f"✅ Has retirado **{amount:,}** monedas de tu cuenta bancaria.", new_cash, new_bank


def apply_daily_bank_fee_db() -> list:
    """Cobra la comisión diaria del 1% por custodia bancaria a todos los usuarios con BankBalance > 0."""
    resultados = []
    
    with db_cursor() as cursor:
        cursor.execute("""
            SELECT u.UserID, u.BankBalance, COALESCE(up.PrestigeLevel, 0)
            FROM Users u
            LEFT JOIN UserPrestige up ON u.UserID = up.UserID
            WHERE u.BankBalance > 0 FOR UPDATE OF u
        """)
        usuarios = cursor.fetchall()
        
        for user_id, bank_balance, prestige_level in usuarios:
            # 1% de comisión diaria
            comision = max(1, int(bank_balance * 0.01))
            
            if prestige_level >= 2:
                # 20% descuento -> multiplicar por 80% (8000 bps)
                comision = (comision * 8000) // 10000
                
            if comision <= 0:
                continue
                
            comision_cobrada = min(comision, bank_balance)
            new_bank = bank_balance - comision_cobrada
            
            cursor.execute("UPDATE Users SET BankBalance = %s WHERE UserID = %s", (new_bank, user_id))
            cursor.execute("UPDATE BancoCentral SET Reservas = Reservas + %s WHERE ID = 1", (comision_cobrada,))
            
            cursor.execute("""
                INSERT INTO Transactions (UserID, Amount, TransactionType, Date)
                VALUES (%s, %s, 'Comisión Diaria Custodia', CURRENT_TIMESTAMP)
            """, (user_id, -comision_cobrada))
            
            resultados.append({
                'user_id': user_id,
                'cobrado': comision_cobrada,
                'nuevo_saldo_banco': new_bank
            })
            
    return resultados


def get_casino_lockout_data(user_id: int):
    """Retorna (balance, saldo_ref, ts_ref, bloqueado_hasta) para el usuario."""
    ensure_user(user_id)
    with db_cursor() as cursor:
        cursor.execute("""
            SELECT Balance, SaldoReferenciaCasino, SaldoReferenciaTimestamp, CasinoBloqueadoHasta 
            FROM Users 
            WHERE UserID = %s
        """, (user_id,))
        row = cursor.fetchone()
        if row:
            return row[0], row[1], row[2], row[3]
        return 500, None, None, None


def update_casino_reference_balance(user_id: int, balance: int, timestamp):
    """Actualiza el saldo de referencia del casino y la fecha/hora de referencia."""
    with db_cursor() as cursor:
        cursor.execute("""
            UPDATE Users 
            SET SaldoReferenciaCasino = %s, SaldoReferenciaTimestamp = %s 
            WHERE UserID = %s
        """, (balance, timestamp, user_id))


def apply_casino_lockout(user_id: int, bloqueado_hasta, nuevo_saldo_ref: int):
    """Aplica el bloqueo del casino y actualiza el saldo de referencia."""
    with db_cursor() as cursor:
        cursor.execute("""
            UPDATE Users 
            SET CasinoBloqueadoHasta = %s, SaldoReferenciaCasino = %s, SaldoReferenciaTimestamp = CURRENT_TIMESTAMP 
            WHERE UserID = %s
        """, (bloqueado_hasta, nuevo_saldo_ref, user_id))


def track_game_payout_db(game_key: str, ganancia_neta: int) -> int:
    """Suma ganancia_neta a GameDailyStats para el día de hoy (UPSERT) y retorna el acumulado."""
    with db_cursor() as cursor:
        cursor.execute("""
            INSERT INTO GameDailyStats (GameKey, FechaDia, TotalPagado)
            VALUES (%s, CURRENT_DATE, %s)
            ON CONFLICT (GameKey, FechaDia) DO UPDATE
            SET TotalPagado = GameDailyStats.TotalPagado + EXCLUDED.TotalPagado
            RETURNING TotalPagado
        """, (game_key, ganancia_neta))
        row = cursor.fetchone()
        return row[0] if row else 0


def get_total_server_balance_db() -> int:
    """Obtiene la suma de todos los saldos de Users."""
    with db_cursor() as cursor:
        cursor.execute("SELECT SUM(Balance) FROM Users")
        row = cursor.fetchone()
        return int(row[0]) if row and row[0] is not None else 0


def activar_circuit_breaker_db(game_key: str, duracion_horas: int, motivo: str):
    """Activa el circuit breaker insertando o actualizando GameCircuitBreaker."""
    from datetime import datetime, timedelta
    bloqueado_hasta = datetime.now() + timedelta(hours=duracion_horas)
    with db_cursor() as cursor:
        cursor.execute("""
            INSERT INTO GameCircuitBreaker (GameKey, BloqueadoHasta, MotivoBloqueo)
            VALUES (%s, %s, %s)
            ON CONFLICT (GameKey) DO UPDATE
            SET BloqueadoHasta = EXCLUDED.BloqueadoHasta,
                MotivoBloqueo = EXCLUDED.MotivoBloqueo
        """, (game_key, bloqueado_hasta, motivo))


def check_game_circuit_breaker_db(game_key: str) -> tuple:
    """Verifica si un juego está bloqueado por circuit breaker.
    Retorna (True, '') si está disponible, o (False, motivo) si está bloqueado."""
    from datetime import datetime
    with db_cursor() as cursor:
        cursor.execute("""
            SELECT BloqueadoHasta, MotivoBloqueo FROM GameCircuitBreaker WHERE GameKey = %s
        """, (game_key,))
        row = cursor.fetchone()
        if row:
            bloqueado_hasta, motivo = row
            if bloqueado_hasta and bloqueado_hasta > datetime.now():
                return False, motivo
        return True, ""


# ══════════════════════════════════════════════
# POBLADO COMUNITARIO HELPERS
# ══════════════════════════════════════════════

def check_and_update_construction(guild_id: int):
    """Comprueba si algún edificio en construcción ya completó sus 4 horas y lo sube de nivel."""
    if not guild_id:
        return
    with db_cursor() as cursor:
        cursor.execute("""
            UPDATE GuildEdificios
            SET Nivel = Nivel + 1,
                FinConstruccion = NULL
            WHERE GuildID = %s AND FinConstruccion IS NOT NULL AND FinConstruccion <= NOW()
        """, (guild_id,))

def ensure_guild_poblado(guild_id: int):
    """Asegura que el servidor tenga registro en GuildPoblado y sus 6 edificios iniciales en Nivel 0."""
    if not guild_id:
        return
    with db_cursor() as cursor:
        cursor.execute("""
            INSERT INTO GuildPoblado (GuildID) VALUES (%s)
            ON CONFLICT (GuildID) DO NOTHING
        """, (guild_id,))
        
        edificios = [
            "Herrería de Combate",
            "Gran Mercado del Servidor",
            "Bastión de Raids",
            "Gran Biblioteca Arcana",
            "Templo del Alba",
            "Taberna del Aventurero"
        ]
        for ed in edificios:
            cursor.execute("""
                INSERT INTO GuildEdificios (GuildID, NombreEdificio, Nivel)
                VALUES (%s, %s, 0)
                ON CONFLICT (GuildID, NombreEdificio) DO NOTHING
            """, (guild_id, ed))

def get_guild_poblado(guild_id: int) -> dict:
    """Obtiene los recursos y estado del Poblado del servidor."""
    ensure_guild_poblado(guild_id)
    check_and_update_construction(guild_id)
    with db_cursor() as cursor:
        cursor.execute("""
            SELECT RecursoMadera, RecursoPiedra, RecursoCristal, RecursoSolar,
                   ProyectoActivo, ProgresoProyecto, PuntosSemanales, UltimoResetSemanal
            FROM GuildPoblado WHERE GuildID = %s
        """, (guild_id,))
        row = cursor.fetchone()
        if not row:
            return {}
        return {
            "madera": row[0],
            "piedra": row[1],
            "cristal": row[2],
            "solar": row[3],
            "proyecto_activo": row[4],
            "progreso_proyecto": row[5],
            "puntos_semanales": row[6],
            "ultimo_reset": row[7]
        }

def get_guild_buildings(guild_id: int) -> dict:
    """Devuelve los niveles y fin de construcción de todos los edificios del servidor."""
    ensure_guild_poblado(guild_id)
    check_and_update_construction(guild_id)
    with db_cursor() as cursor:
        cursor.execute("SELECT NombreEdificio, Nivel, FinConstruccion FROM GuildEdificios WHERE GuildID = %s", (guild_id,))
        rows = cursor.fetchall()
        return {r[0]: {"nivel": r[1], "fin_construccion": r[2]} for r in rows}

def get_building_level(guild_id: int, building_name: str) -> int:
    """Obtiene el nivel de un edificio específico en el servidor."""
    if not guild_id:
        return 0
    ensure_guild_poblado(guild_id)
    check_and_update_construction(guild_id)
    with db_cursor() as cursor:
        cursor.execute("SELECT Nivel FROM GuildEdificios WHERE GuildID = %s AND NombreEdificio = %s", (guild_id, building_name))
        row = cursor.fetchone()
        return row[0] if row else 0

def start_building_construction(guild_id: int, building_name: str) -> tuple[bool, str]:
    """Inicia el temporizador de 4 horas de construcción para subir un edificio de nivel."""
    if not guild_id:
        return False, "Servidor inválido."
    ensure_guild_poblado(guild_id)
    check_and_update_construction(guild_id)
    with db_cursor() as cursor:
        cursor.execute("SELECT Nivel, FinConstruccion FROM GuildEdificios WHERE GuildID = %s AND NombreEdificio = %s", (guild_id, building_name))
        row = cursor.fetchone()
        current_lvl = row[0] if row else 0
        fin_const = row[1] if row else None

        if current_lvl >= 5:
            return False, f"El edificio **{building_name}** ya alcanzó el Nivel Máximo (5)."
        if fin_const is not None:
            return False, f"El edificio **{building_name}** ya está en proceso de construcción."

        cursor.execute("""
            UPDATE GuildEdificios
            SET FinConstruccion = NOW() + INTERVAL '4 hours'
            WHERE GuildID = %s AND NombreEdificio = %s
        """, (guild_id, building_name))
        return True, f"🔨 ¡La obra de **{building_name}** ha comenzado! Tardará **4 horas** en construirse y habilitar el Nivel {current_lvl + 1}."



def add_poblado_resources(guild_id: int, madera: int = 0, piedra: int = 0, cristal: int = 0, solar: int = 0, puntos: int = 0):
    """Suma recursos y puntos semanales al Poblado del servidor."""
    if not guild_id:
        return
    ensure_guild_poblado(guild_id)
    with db_cursor() as cursor:
        cursor.execute("""
            UPDATE GuildPoblado
            SET RecursoMadera = RecursoMadera + %s,
                RecursoPiedra = RecursoPiedra + %s,
                RecursoCristal = RecursoCristal + %s,
                RecursoSolar = RecursoSolar + %s,
                PuntosSemanales = PuntosSemanales + %s
            WHERE GuildID = %s
        """, (madera, piedra, cristal, solar, puntos, guild_id))

def set_active_project(guild_id: int, building_name: str) -> tuple[bool, str]:
    """Establece el proyecto de edificio activo a construir/mejorar."""
    ensure_guild_poblado(guild_id)
    current_lvl = get_building_level(guild_id, building_name)
    if current_lvl >= 5:
        return False, f"El edificio **{building_name}** ya alcanzó el nivel máximo (5)."

    with db_cursor() as cursor:
        cursor.execute("UPDATE GuildPoblado SET ProyectoActivo = %s WHERE GuildID = %s", (building_name, guild_id))
        return True, f"Proyecto activo cambiado a **{building_name}** (Nivel actual: {current_lvl})."

def record_poblado_contribution(guild_id: int, user_id: int, puntos: int, materiales: int):
    """Registra los aportes individuales de un usuario al Poblado del servidor."""
    if not guild_id or not user_id:
        return
    with db_cursor() as cursor:
        cursor.execute("""
            INSERT INTO PobladoContribuciones (GuildID, UserID, PuntosAportados, MaterialesDonados)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (GuildID, UserID) DO UPDATE
            SET PuntosAportados = PobladoContribuciones.PuntosAportados + EXCLUDED.PuntosAportados,
                MaterialesDonados = PobladoContribuciones.MaterialesDonados + EXCLUDED.MaterialesDonados
        """, (guild_id, user_id, puntos, materiales))

def get_poblado_leaderboard(guild_id: int, limit: int = 10) -> list:
    """Devuelve el ranking de mayores aportadores al Poblado en el servidor."""
    if not guild_id:
        return []
    with db_cursor() as cursor:
        cursor.execute("""
            SELECT UserID, PuntosAportados, MaterialesDonados
            FROM PobladoContribuciones
            WHERE GuildID = %s
            ORDER BY (PuntosAportados + MaterialesDonados * 5) DESC
            LIMIT %s
        """, (guild_id, limit))
        return cursor.fetchall()





