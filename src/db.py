"""
Este módulo proporciona acceso simplificado a las funciones de base de datos.
"""

import pyodbc

# Configura tu conexión aquí
server = 'FELIPE'
database = 'CasinoBot'
username = 'sa'
password = '123'

conn_str = (
    f'DRIVER={{ODBC Driver 17 for SQL Server}};'
    f'SERVER={server};DATABASE={database};'
    f'UID={username};PWD={password}'
    # f'Trusted_Connection=yes'
)

def get_connection():
    """Retorna una conexión a la base de datos."""
    return pyodbc.connect(conn_str)

def get_balance(user_id):
    conn = pyodbc.connect(conn_str)
    cursor = conn.cursor()
    cursor.execute("SELECT Balance FROM Users WHERE UserID = ?", user_id)
    row = cursor.fetchone()
    conn.close()
    return row.Balance if row else 0

def set_balance(user_id, balance):
    conn = pyodbc.connect(conn_str)
    cursor = conn.cursor()
    cursor.execute("""
        IF EXISTS (SELECT 1 FROM Users WHERE UserID = ?)
            UPDATE Users SET Balance = ? WHERE UserID = ?
        ELSE
            INSERT INTO Users (UserID, Balance) VALUES (?, ?)
        """, user_id, balance, user_id, user_id, balance)
    conn.commit()
    conn.close()

def add_balance(user_id, amount):
    current = get_balance(user_id)
    set_balance(user_id, current + amount)

def ensure_user(user_id, user_name=None):
    from datetime import datetime
    conn = pyodbc.connect(conn_str)
    cursor = conn.cursor()
    cursor.execute("SELECT UserName, StartDate FROM Users WHERE UserID = ?", user_id)
    row = cursor.fetchone()
    
    # Verificar si el nombre parece un nombre genérico (User_ID) para no usarlo
    is_generic_name = user_name and (user_name == f"User_{user_id}" or user_name.startswith("User_"))
    
    if not row:
        start_date = datetime.now().date()
        # Solo usar el nombre si no es genérico
        actual_user_name = None if is_generic_name else user_name
        cursor.execute(
            "INSERT INTO Users (UserID, Balance, LastLogin, Streak, UserName, StartDate) VALUES (?, ?, ?, ?, ?, ?)",
            user_id, 500, None, 0, actual_user_name, start_date
        )
    else:
        # Si falta alguno de los campos, actualízalo
        current_name, current_start = row
        updates = []
        params = []
        
        # Solo actualizar el nombre si:
        # 1. El nombre actual está vacío o es None
        # 2. El nombre nuevo no es genérico
        # 3. El nombre nuevo no es igual al actual
        if ((not current_name) and user_name and not is_generic_name) or \
           (current_name and user_name and current_name != user_name and not is_generic_name):
            updates.append("UserName = ?")
            params.append(user_name)
        if not current_start:
            updates.append("StartDate = ?")
            params.append(datetime.now().date())
        if updates:
            set_clause = ", ".join(updates)
            cursor.execute(f"UPDATE Users SET {set_clause} WHERE UserID = ?", *params, user_id)
    conn.commit()
    conn.close()

def registrar_transaccion(user_id, amount, tipo):
    from datetime import datetime
    conn = pyodbc.connect(conn_str)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO Transactions (UserID, Amount, TransactionType, Date)
        VALUES (?, ?, ?, ?)
    """, user_id, amount, tipo, datetime.now())
    conn.commit()
    conn.close()

def agregar_item_usuario(user_id, item_id, quantity=1, expiry=None):
    """
    Agrega un item al inventario del usuario.
    
    Args:
        user_id: ID del usuario
        item_id: ID del ítem a agregar
        quantity: Cantidad (por defecto 1)
        expiry: Fecha de expiración (puede ser None para ítems permanentes)
    
    Returns:
        bool: True si se agregó correctamente, False en caso contrario
    """
    from datetime import datetime, timedelta
    
    conn = pyodbc.connect(conn_str)
    cursor = conn.cursor()
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
        
        # Verificar si el usuario ya tiene este ítem
        cursor.execute("SELECT Quantity FROM UserItems WHERE UserID = ? AND ItemID = ? AND Expiry > GETDATE() AND Used = 0", 
                       user_id, item_id)
        row = cursor.fetchone()
        
        if row:
            # El usuario ya tiene este ítem, aumentamos la cantidad
            cursor.execute("""
                UPDATE UserItems 
                SET Quantity = Quantity + ?
                WHERE UserID = ? AND ItemID = ? AND Expiry > GETDATE() AND Used = 0
            """, quantity, user_id, item_id)
        else:
            # El usuario no tiene el ítem, lo insertamos
            cursor.execute("""
                INSERT INTO UserItems (UserID, ItemID, Quantity, Expiry, Used)
                VALUES (?, ?, ?, ?, 0)
            """, user_id, item_id, quantity, expiry)
        
        conn.commit()
        return True
    except Exception as e:
        print(f"Error agregando ítem al usuario: {e}")
        conn.rollback()
        return False
    finally:
        cursor.close()
        conn.close()

def usuario_tiene_item(user_id, item_id):
    """
    Verifica si un usuario tiene un ítem específico en su inventario.
    
    Args:
        user_id: ID del usuario
        item_id: ID del ítem a verificar
    
    Returns:
        bool: True si el usuario tiene el ítem, False en caso contrario
    """
    conn = pyodbc.connect(conn_str)
    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT COUNT(*) FROM UserItems 
            WHERE UserID = ? AND ItemID = ? AND Quantity > 0 AND Used = 0
            AND Expiry > GETDATE()
        """, user_id, item_id)
        row = cursor.fetchone()
        count = row[0] if row else 0
        return count > 0
    except (pyodbc.Error, pyodbc.ProgrammingError, pyodbc.DatabaseError) as e:
        print(f"Error de base de datos al verificar ítem de usuario: {e}")
        return False
    except Exception as e:
        print(f"Error inesperado verificando ítem de usuario: {e}")
        return False
    finally:
        cursor.close()
        conn.close()

def usuario_tiene_mejora(user_id, item_id):
    """Alias para usuario_tiene_item para mantener compatibilidad"""
    return usuario_tiene_item(user_id, item_id)

def get_user_items(user_id):
    """
    Obtiene todos los ítems activos de un usuario.
    
    Args:
        user_id: ID del usuario
    
    Returns:
        list: Lista de diccionarios con información de los ítems
    """
    conn = pyodbc.connect(conn_str)
    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT ItemID, Quantity, Expiry, Used 
            FROM UserItems 
            WHERE UserID = ? AND Quantity > 0 AND Used = 0
            AND Expiry > GETDATE()
        """, user_id)
        
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
    finally:
        cursor.close()
        conn.close()

def usar_item_usuario(user_id, item_id):
    """
    Marca un ítem como usado en el inventario del usuario.
    
    Args:
        user_id: ID del usuario
        item_id: ID del ítem a usar
    
    Returns:
        bool: True si se usó correctamente, False en caso contrario
    """
    conn = pyodbc.connect(conn_str)
    cursor = conn.cursor()
    try:
        # Obtenemos la fecha de expiración del item más antiguo para usar en la cláusula WHERE
        cursor.execute("""
            SELECT TOP 1 Expiry 
            FROM UserItems 
            WHERE UserID = ? AND ItemID = ? AND Quantity > 0 AND Used = 0
            AND Expiry > GETDATE()
            ORDER BY Expiry
        """, user_id, item_id)
        
        row = cursor.fetchone()
        if not row:
            return False
            
        expiry_date = row[0]
        
        # Actualizamos el registro usando todos los criterios de búsqueda para garantizar unicidad
        cursor.execute("""
            UPDATE UserItems 
            SET Quantity = Quantity - 1,
                Used = CASE WHEN Quantity - 1 <= 0 THEN 1 ELSE Used END
            WHERE UserID = ? AND ItemID = ? AND Quantity > 0 AND Used = 0 
            AND Expiry = ?
        """, user_id, item_id, expiry_date)
        
        conn.commit()
        return True
    except pyodbc.Error as e:
        print(f"Error de base de datos usando ítem: {e}")
        conn.rollback()
        return False
    except Exception as e:
        print(f"Error inesperado usando ítem: {e}")
        conn.rollback()
        return False
    finally:
        cursor.close()
        conn.close()

# Funciones para el sistema de dificultad dinámica
def get_user_game_stats(user_id):
    """Obtener estadísticas de juego del usuario"""
    conn = pyodbc.connect(conn_str)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT TotalGamesPlayed, TotalWins, TotalLosses, WinRate, 
               HotStreak, ColdStreak, RiskProfile, DifficultyLevel
        FROM UserGameStats WHERE UserID = ?
    """, user_id)
    row = cursor.fetchone()
    cursor.close()
    conn.close()
    
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
    """Registrar resultado de un juego para el sistema de dificultad"""
    from datetime import datetime
    conn = pyodbc.connect(conn_str)
    cursor = conn.cursor()
    
    try:
        # Registrar en GameHistory
        cursor.execute("""
            INSERT INTO GameHistory 
            (UserID, GameType, BetAmount, Result, WinAmount, Timestamp, DifficultyApplied, UserBalance)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, user_id, game_type, bet_amount, result, win_amount, datetime.now(), difficulty_applied, user_balance)
        
        # Actualizar o crear estadísticas del usuario
        cursor.execute("SELECT * FROM UserGameStats WHERE UserID = ?", user_id)
        stats = cursor.fetchone()
        
        is_win = result.lower() in ['win', 'victory', 'won', 'ganaste', 'ganador']
        
        if not stats:
            # Crear nuevas estadísticas
            cursor.execute("""
                INSERT INTO UserGameStats 
                (UserID, TotalGamesPlayed, TotalWins, TotalLosses, TotalAmountBet, 
                 TotalAmountWon, WinRate, AvgBetSize, LastGameTime, 
                 HotStreak, ColdStreak, RiskProfile, DifficultyLevel)
                VALUES (?, 1, ?,
                        0, 0, ?, ?, ?, ?, ?, ?, 'BALANCED', ?)
            """, user_id, 1 if is_win else 0, win_amount, 1.0 if is_win else 0.0, float(bet_amount), 
                 datetime.now(), 1 if is_win else 0, 0 if is_win else 1, difficulty_applied)
        else:
            # Actualizar estadísticas existentes
            new_games = stats[1] + 1
            new_wins = stats[2] + (1 if is_win else 0)
            new_losses = stats[3] + (0 if is_win else 1)
            new_bet_total = stats[4] + bet_amount
            new_won_total = stats[5] + win_amount
            new_win_rate = new_wins / new_games if new_games > 0 else 0.0
            new_avg_bet = new_bet_total / new_games if new_games > 0 else 0.0
            
            # Actualizar rachas
            hot_streak = stats[9] if stats[9] is not None else 0
            cold_streak = stats[10] if stats[10] is not None else 0
            
            if is_win:
                hot_streak += 1
                cold_streak = 0
            else:
                cold_streak += 1
                hot_streak = 0
                
            # Determinar perfil de riesgo
            risk_profile = calculate_risk_profile(new_avg_bet, new_win_rate, hot_streak, cold_streak)
            
            cursor.execute("""
                UPDATE UserGameStats SET
                    TotalGamesPlayed = ?, TotalWins = ?, TotalLosses = ?,
                    TotalAmountBet = ?, TotalAmountWon = ?, WinRate = ?,
                    AvgBetSize = ?, LastGameTime = ?,
                    HotStreak = ?, ColdStreak = ?, RiskProfile = ?, DifficultyLevel = ?
                WHERE UserID = ?
            """, new_games, new_wins, new_losses, new_bet_total, new_won_total,
                 new_win_rate, new_avg_bet, datetime.now(), hot_streak, cold_streak, 
                 risk_profile, difficulty_applied, user_id)
        
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        cursor.close()
        conn.close()

def calculate_risk_profile(avg_bet, win_rate, hot_streak, cold_streak):
    """Calcular el perfil de riesgo del usuario"""
    if avg_bet < 100 and win_rate < 0.4:
        return 'CONSERVATIVE'
    elif avg_bet > 500 or hot_streak > 5 or cold_streak > 8:
        return 'AGGRESSIVE'
    else:
        return 'BALANCED'

def get_recent_game_history(user_id, hours=24, limit=20):
    """Obtener historial reciente de juegos"""
    conn = pyodbc.connect(conn_str)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT TOP (?) GameType, BetAmount, Result, WinAmount, Timestamp, DifficultyApplied
        FROM GameHistory 
        WHERE UserID = ? AND Timestamp >= DATEADD(hour, -?, GETDATE())
        ORDER BY Timestamp DESC
    """, limit, user_id, hours)
    
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
    
    cursor.close()
    conn.close()
    return games