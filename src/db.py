"""
Este módulo proporciona acceso simplificado a las funciones de base de datos PostgreSQL.
"""

import psycopg2
import os
import threading
from contextlib import contextmanager
from psycopg2.pool import ThreadedConnectionPool

# Configurar conexión cargando desde variables de entorno con fallbacks seguros de PostgreSQL
host = os.getenv('DB_HOST', 'localhost')
port = os.getenv('DB_PORT', '5432')
database = os.getenv('DB_NAME', 'CasinoBot')
username = os.getenv('DB_USER', 'postgres')
password = os.getenv('DB_PASSWORD', '123')
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

def agregar_item_usuario(user_id, item_id, quantity=1, expiry=None):
    """Agrega un item al inventario del usuario."""
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
            # Verificar si el usuario ya tiene este ítem
            cursor.execute("SELECT Quantity FROM UserItems WHERE UserID = %s AND ItemID = %s AND Expiry > NOW() AND Used = 0", 
                           (user_id, item_id))
            row = cursor.fetchone()
            
            if row:
                # El usuario ya tiene este ítem, aumentamos la cantidad
                cursor.execute("""
                    UPDATE UserItems 
                    SET Quantity = Quantity + %s
                    WHERE UserID = %s AND ItemID = %s AND Expiry > NOW() AND Used = 0
                """, (quantity, user_id, item_id))
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
    """Obtiene todos los ítems activos de un usuario."""
    try:
        with db_cursor() as cursor:
            cursor.execute("""
                SELECT ItemID, Quantity, Expiry, Used 
                FROM UserItems 
                WHERE UserID = %s AND Quantity > 0 AND Used = 0
                AND Expiry > NOW()
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
    """Marca un ítem como usado en el inventario del usuario."""
    try:
        with db_cursor() as cursor:
            # Obtenemos la fecha de expiración del item más antiguo para usar en la cláusula WHERE
            cursor.execute("""
                SELECT Expiry 
                FROM UserItems 
                WHERE UserID = %s AND ItemID = %s AND Quantity > 0 AND Used = 0
                AND Expiry > NOW()
                ORDER BY Expiry
                LIMIT 1
            """, (user_id, item_id))
            
            row = cursor.fetchone()
            if not row:
                return False
                
            expiry_date = row[0]
            
            # Actualizamos el registro usando todos los criterios de búsqueda para garantizar unicidad
            cursor.execute("""
                UPDATE UserItems 
                SET Quantity = Quantity - 1,
                    Used = CASE WHEN Quantity - 1 <= 0 THEN 1 ELSE Used END
                WHERE UserID = %s AND ItemID = %s AND Quantity > 0 AND Used = 0 
                AND Expiry = %s
            """, (user_id, item_id, expiry_date))
            return True
    except Exception as e:
        print(f"Error usando ítem: {e}")
        return False

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
        cursor.execute("SELECT LastLogin, Streak, Balance FROM Users WHERE UserID = %s", (user_id,))
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
            
        reward = 100 * (streak // 7 + 1)
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

def get_lottery_tickets():
    with db_cursor() as cursor:
        cursor.execute("SELECT UserID FROM LotteryTickets")
        return [row[0] for row in cursor.fetchall()]

def buy_lottery_tickets(user_id, count):
    with db_cursor() as cursor:
        args = [(user_id,)] * count
        cursor.executemany("INSERT INTO LotteryTickets (UserID) VALUES (%s)", args)

def clear_lottery():
    with db_cursor() as cursor:
        cursor.execute("TRUNCATE TABLE LotteryTickets")

def get_lottery_pot(ticket_price=100, base_pot=5000):
    with db_cursor() as cursor:
        cursor.execute("SELECT COUNT(*) FROM LotteryTickets")
        count = cursor.fetchone()[0]
        return base_pot + (count * ticket_price)

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
                    print(f"Base de datos '{database}' encontrada.")
                else:
                    print(f"Base de datos '{database}' no existe. Creandola...")
                    cursor.execute(
                        sql.SQL("CREATE DATABASE {}").format(
                            sql.Identifier(database)
                        )
                    )
                    print(f"Base de datos '{database}' creada exitosamente.")
        finally:
            conn_admin.close()
    except Exception as e:
        print(f"Error al verificar/crear la base de datos: {e}")
        raise

    # 2. Conectar a la base de datos y crear todas las tablas
    print(f"🔄 Inicializando tablas en la base de datos '{database}'...")
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
            
            # Tabla: RoboStats
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS RoboStats (
                    UserID BIGINT PRIMARY KEY,
                    LastRoboTime TIMESTAMP,
                    LastRobadoTime TIMESTAMP,
                    RobosExitosos INT DEFAULT 0,
                    RobosFallidos INT DEFAULT 0,
                    TotalRobado BIGINT DEFAULT 0,
                    TotalPerdido BIGINT DEFAULT 0,
                    ProteccionActiva BOOLEAN DEFAULT FALSE
                )
            """)
            
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

            # Tabla: MinaStats
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS MinaStats (
                    UserID BIGINT PRIMARY KEY,
                    MinasPisadas INT DEFAULT 0
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
            
        print("✅ Todas las tablas de la base de datos se han inicializado/verificado correctamente.")
    except Exception as e:
        print(f"❌ Error inicializando las tablas de la base de datos: {e}")
        raise e
