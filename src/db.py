"""
Este módulo proporciona acceso simplificado a las funciones de base de datos PostgreSQL.
"""

import psycopg2
import os
import threading
import logging
from contextlib import contextmanager
from psycopg2.pool import ThreadedConnectionPool
from dotenv import load_dotenv

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

def _connect_direct(database_name=None):
    return psycopg2.connect(
        host=host,
        port=port,
        database=database_name or database,
        user=username,
        password=password
    )

def _get_pool():
    global _pool
    if _pool is None:
        with _pool_lock:
            if _pool is None:
                _pool = ThreadedConnectionPool(
                    minconn=pool_min,
                    maxconn=pool_max,
                    host=host,
                    port=port,
                    database=database,
                    user=username,
                    password=password
                )
    return _pool

def get_connection():
    """Retorna una conexión directa a PostgreSQL.

    Se conserva para compatibilidad con módulos que llaman conn.close()
    manualmente. El pool se usa en db_cursor().
    """
    return _connect_direct()

def close_connection_pool():
    """Cierra todas las conexiones del pool si fue inicializado."""
    global _pool
    if _pool is not None:
        _pool.closeall()
        _pool = None

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

def add_balance(user_id, amount):
    """Añade (o resta) saldo a un usuario de forma atómica usando Upsert nativo de PostgreSQL."""
    with db_cursor() as cursor:
        cursor.execute("""
            INSERT INTO Users (UserID, Balance) VALUES (%s, %s)
            ON CONFLICT (UserID) DO UPDATE SET Balance = Users.Balance + EXCLUDED.Balance
            """, (user_id, amount))

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

def registrar_transaccion(user_id, amount, tipo):
    """Registra una transacción en el historial."""
    from datetime import datetime
    with db_cursor() as cursor:
        cursor.execute("""
            INSERT INTO Transactions (UserID, Amount, TransactionType, Date)
            VALUES (%s, %s, %s, %s)
        """, (user_id, amount, tipo, datetime.now()))

def transfer_balance(from_user_id, to_user_id, amount, reason):
    """Realiza una transferencia atómica de saldo entre dos usuarios."""
    from datetime import datetime
    with db_cursor() as cursor:
        # Verificar saldo del emisor
        cursor.execute("SELECT Balance FROM Users WHERE UserID = %s", (from_user_id,))
        row = cursor.fetchone()
        if not row or row[0] < amount:
            return False, 0, 0
        
        # Descontar del emisor
        cursor.execute("UPDATE Users SET Balance = Balance - %s WHERE UserID = %s RETURNING Balance", (amount, from_user_id))
        from_new_balance = cursor.fetchone()[0]
        
        # Sumar al receptor
        cursor.execute("""
            INSERT INTO Users (UserID, Balance) VALUES (%s, %s)
            ON CONFLICT (UserID) DO UPDATE SET Balance = Users.Balance + EXCLUDED.Balance
            RETURNING Balance
        """, (to_user_id, amount))
        to_new_balance = cursor.fetchone()[0]
        
        # Registrar transacciones
        cursor.execute("""
            INSERT INTO Transactions (UserID, Amount, TransactionType, Date)
            VALUES (%s, %s, %s, %s)
        """, (from_user_id, -amount, f"Transferencia: {reason} (a {to_user_id})", datetime.now()))
        cursor.execute("""
            INSERT INTO Transactions (UserID, Amount, TransactionType, Date)
            VALUES (%s, %s, %s, %s)
        """, (to_user_id, amount, f"Transferencia: {reason} (de {from_user_id})", datetime.now()))
        
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
        print(f"Error agregando ítem al usuario: {e}")
        return False

def usuario_tiene_item(user_id, item_id):
    """Verifica si un usuario tiene un ítem específico en su inventario."""
    try:
        with db_cursor() as cursor:
            cursor.execute("""
                SELECT COUNT(*) FROM UserItems 
                WHERE UserID = %s AND ItemID = %s AND Quantity > 0 AND Used = 0
                AND Expiry > NOW()
            """, (user_id, item_id))
            row = cursor.fetchone()
            count = row[0] if row else 0
            return count > 0
    except Exception as e:
        print(f"Error de base de datos al verificar ítem de usuario: {e}")
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
        print(f"Error obteniendo ítems de usuario: {e}")
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
        print(f"Error usando ítem: {e}")
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
        print(f"Error en check_and_register_energy_use: {e}")
        # En caso de error de BD, por seguridad permitimos el uso
        return 'ok', None

def check_and_register_shield_use(user_id):
    """
    Verifica si un usuario puede usar un escudo de protección en trabajos/casino (máximo 3 usos al día).
    Si está bloqueado por cooldown, retorna ('blocked', segundos_restantes).
    Si alcanza los 3 usos, inicia un bloqueo de 24 horas y retorna ('blocked_start', 86400).
    De lo contrario, registra el uso y retorna ('ok', None).
    """
    from datetime import datetime, timedelta
    shield_item_group_id = 999
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
        print(f"Error comprobando cooldown de escudos: {e}")
        return 'ok', None


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

def record_game_result(user_id, game_type, bet_amount, result, win_amount, difficulty_applied, user_balance):
    """Registrar resultado de un juego para el sistema de dificultad, sincronizando todas las tablas de estadísticas."""
    from datetime import datetime
    is_win = result.lower() in ['win', 'victory', 'won', 'ganaste', 'ganador']
    result_str = 'win' if is_win else 'loss'
    
    with db_cursor() as cursor:
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
                except Exception:
                    last_login = today - timedelta(days=2)
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
            print("✅ Columna 'Energia' agregada")
            
        if 'ultimarecarga' not in columns:
            cursor.execute("ALTER TABLE Users ADD COLUMN UltimaRecarga BIGINT DEFAULT 0")
            print("✅ Columna 'UltimaRecarga' agregada")
            
        import time
        tiempo_actual = int(time.time())
        cursor.execute("""
            UPDATE Users 
            SET Energia = 100, UltimaRecarga = %s 
            WHERE Energia IS NULL OR UltimaRecarga IS NULL
        """, (tiempo_actual,))

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
        
        if energia_actual is None:
            energia_actual = 100
            ultima_recarga = int(time.time())
            cursor.execute("UPDATE Users SET Energia = %s, UltimaRecarga = %s WHERE UserID = %s", (energia_actual, ultima_recarga, user_id))
            return energia_actual
        
        if ultima_recarga is None:
            ultima_recarga = int(time.time())
            cursor.execute("UPDATE Users SET UltimaRecarga = %s WHERE UserID = %s", (ultima_recarga, user_id))
            return energia_actual
        
        if energia_actual < 100:
            tiempo_actual = int(time.time())
            tiempo_transcurrido = tiempo_actual - ultima_recarga
            puntos_recarga = tiempo_transcurrido // 180
            
            if puntos_recarga > 0:
                energia_actual = min(100, energia_actual + puntos_recarga)
                ultima_recarga = ultima_recarga + (puntos_recarga * 180)
                cursor.execute("UPDATE Users SET Energia = %s, UltimaRecarga = %s WHERE UserID = %s", (energia_actual, ultima_recarga, user_id))
        
        return energia_actual

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

        energia_actual = row[0] if row[0] is not None else 100
        ultima_recarga = row[1] if row[1] is not None else int(time.time())

        if energia_actual < 100:
            tiempo_actual = int(time.time())
            puntos_recarga = (tiempo_actual - ultima_recarga) // 180
            if puntos_recarga > 0:
                energia_actual = min(100, energia_actual + puntos_recarga)
                ultima_recarga = ultima_recarga + (puntos_recarga * 180)

        if energia_actual < cantidad:
            cursor.execute(
                "UPDATE Users SET Energia = %s, UltimaRecarga = %s WHERE UserID = %s",
                (energia_actual, ultima_recarga, user_id),
            )
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
        if row:
            return row[0] if isinstance(row[0], dict) else json.loads(row[0])
        return None

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
    Busca mascotas que el usuario tiene 5+ duplicados (mismo PetID).
    Retorna lista de dicts: [{pet_id, name, emoji, rarity, count}, ...]
    """
    with db_cursor() as cursor:
        cursor.execute("""
            SELECT up.PetID, pc.Name, pc.Emoji, pc.Rarity, COUNT(*) as cnt
            FROM UserPets up
            JOIN PetsCatalog pc ON up.PetID = pc.PetID
            WHERE up.UserID = %s AND up.Status != 'Escapó'
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
    Fusiona 5 mascotas del mismo PetID en 1 mascota aleatoria de rareza superior.
    Retorna (success: bool, result: dict o str).
    result dict: {new_pet_name, new_pet_emoji, new_rarity, new_user_pet_id, flavor_text, is_mythic_boost}
    """
    with db_cursor() as cursor:
        # 1. Verificar que tiene al menos 5 del mismo PetID
        cursor.execute("""
            SELECT up.UserPetID
            FROM UserPets up
            WHERE up.UserID = %s AND up.PetID = %s AND up.Status != 'Escapó'
            ORDER BY up.IsActive ASC, up.Loyalty ASC
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
    with db_cursor() as cursor:
        if member_ids:
            if len(member_ids) == 1:
                cursor.execute("""
                    SELECT m.UserID, m.MinasPisadas, u.UserName 
                    FROM MinaStats m
                    LEFT JOIN Users u ON m.UserID = u.UserID
                    WHERE m.UserID = %s
                    ORDER BY m.MinasPisadas DESC
                    LIMIT %s
                """, (member_ids[0], limit))
            else:
                cursor.execute("""
                    SELECT m.UserID, m.MinasPisadas, u.UserName 
                    FROM MinaStats m
                    LEFT JOIN Users u ON m.UserID = u.UserID
                    WHERE m.UserID IN %s
                    ORDER BY m.MinasPisadas DESC
                    LIMIT %s
                """, (tuple(member_ids), limit))
        else:
            cursor.execute("""
                SELECT m.UserID, m.MinasPisadas, u.UserName 
                FROM MinaStats m
                LEFT JOIN Users u ON m.UserID = u.UserID
                ORDER BY m.MinasPisadas DESC
                LIMIT %s
            """, (limit,))
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
            
            # --- TABLAS DEL PLAN MAESTRO DE PETS ---
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS PetsCatalog (
                    PetID SERIAL PRIMARY KEY,
                    Name VARCHAR(100) NOT NULL,
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
                    BetAmount INT NOT NULL,
                    Result VARCHAR(20) NOT NULL,
                    WinAmount INT NOT NULL,
                    Timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    DifficultyApplied DOUBLE PRECISION DEFAULT 0.0,
                    UserBalance INT NOT NULL
                )
            """)
            
            # Tabla: GameResults (Para el sistema de dificultad dinámica)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS GameResults (
                    ResultID SERIAL PRIMARY KEY,
                    UserID BIGINT NOT NULL,
                    GameType VARCHAR(50) NOT NULL,
                    BetAmount INT NOT NULL,
                    Result VARCHAR(20) NOT NULL,
                    Winnings INT NOT NULL,
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
                    TotalMoneyLost BIGINT DEFAULT 0
                )
            """)

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

            # Drop old table to migrate to new schema if it lacks PrimaryStat
            cursor.execute("""
                SELECT 1 FROM information_schema.columns 
                WHERE table_name = 'userequipment' AND column_name = 'primarystat'
            """)
            if not cursor.fetchone():
                cursor.execute("DROP TABLE IF EXISTS UserEquipment CASCADE")

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
                    CONSTRAINT uq_user_slot UNIQUE (UserID, Slot)
                )
            """)

            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_combatlog_challenger
                ON CombatLog (ChallengerID, Timestamp DESC)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_combatlog_rival
                ON CombatLog (RivalID, Timestamp DESC)
            """)
            # ─── FIN TABLAS DUELOS PVP ───

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
                   BestWinStreak, LastDuelTime, TotalMoneyWon, TotalMoneyLost
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


def log_duel(challenger_id, rival_id, winner_id, bet, turns, c_level, r_level):
    """Registra un duelo en el historial."""
    with db_cursor() as cursor:
        cursor.execute("""
            INSERT INTO CombatLog (ChallengerID, RivalID, WinnerID, Bet, Turns, ChallengerLevel, RivalLevel)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, (challenger_id, rival_id, winner_id, bet, turns, c_level, r_level))


def get_user_equipment(user_id):
    """Obtiene todo el equipo de un usuario.

    Returns:
        dict de slot -> {item_name, rarity, item_level, primary_stat, primary_value, secondaries, passive}
    """
    with db_cursor() as cursor:
        cursor.execute("""
            SELECT Slot, ItemName, Rarity, ItemLevel, PrimaryStat, PrimaryValue, Secondaries, Passive
            FROM UserEquipment WHERE UserID = %s
        """, (user_id,))
        equipment = {}
        for row in cursor.fetchall():
            equipment[row[0]] = {
                'item_name': row[1],
                'rarity': row[2],
                'item_level': row[3],
                'primary_stat': row[4],
                'primary_value': row[5],
                'secondaries': row[6] if isinstance(row[6], list) else [],
                'passive': row[7] if isinstance(row[7], dict) else None,
            }
        return equipment


def equip_item(user_id, slot, name, rarity, item_level, primary_stat, primary_value, secondaries=None, passive=None):
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
            SELECT ItemName, Rarity, ItemLevel, PrimaryStat, PrimaryValue, Secondaries, Passive
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
            }

        # UPSERT
        cursor.execute("""
            INSERT INTO UserEquipment (UserID, Slot, ItemName, Rarity, ItemLevel, PrimaryStat, PrimaryValue, Secondaries, Passive)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT ON CONSTRAINT uq_user_slot
            DO UPDATE SET ItemName = EXCLUDED.ItemName,
                         Rarity = EXCLUDED.Rarity,
                         ItemLevel = EXCLUDED.ItemLevel,
                         PrimaryStat = EXCLUDED.PrimaryStat,
                         PrimaryValue = EXCLUDED.PrimaryValue,
                         Secondaries = EXCLUDED.Secondaries,
                         Passive = EXCLUDED.Passive
        """, (user_id, slot, name, rarity, item_level, primary_stat, primary_value,
              psycopg2.extras.Json(secondaries), psycopg2.extras.Json(passive) if passive else None))

        return old_item


def get_duel_leaderboard(order_by='wins', limit=10):
    """Obtiene el ranking de duelos.

    Args:
        order_by: 'wins' o 'level'
        limit: número de resultados

    Returns:
        lista de tuplas (UserID, CombatLevel, Wins, Losses, WinStreak, BestWinStreak)
    """
    valid_orders = {
        'wins': 'Wins DESC, CombatLevel DESC',
        'level': 'CombatLevel DESC, CombatXP DESC',
    }
    order_clause = valid_orders.get(order_by, valid_orders['wins'])
    with db_cursor() as cursor:
        cursor.execute(f"""
            SELECT UserID, CombatLevel, Wins, Losses, WinStreak, BestWinStreak
            FROM CombatStats
            WHERE Wins + Losses > 0
            ORDER BY {order_clause}
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

