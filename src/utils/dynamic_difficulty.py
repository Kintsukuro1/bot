import pyodbc
import time
from datetime import datetime, timedelta
from typing import Dict, Tuple, Any
import os
import sys

# Importar configuración de base de datos
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from db import conn_str, ensure_user

class DynamicDifficulty:
    """
    Sistema de dificultad dinámica para juegos de casino.
    Ajusta automáticamente la dificultad basándose en el comportamiento del jugador.
    """
    
    @staticmethod
    def init_difficulty_db():
        """Inicializar tablas necesarias para el sistema de dificultad."""
        conn = pyodbc.connect(conn_str)
        cursor = conn.cursor()
        
        try:
            # Tabla para resultados de juegos
            cursor.execute("""
                IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='GameResults' AND xtype='U')
                CREATE TABLE GameResults (
                    ResultID INT IDENTITY(1,1) PRIMARY KEY,
                    UserID BIGINT NOT NULL,
                    GameType NVARCHAR(50) NOT NULL,
                    BetAmount INT NOT NULL,
                    Result NVARCHAR(20) NOT NULL,
                    Winnings INT NOT NULL,
                    DifficultyModifier FLOAT NOT NULL,
                    Balance BIGINT NOT NULL,
                    Timestamp DATETIME2 DEFAULT GETDATE()
                )
            """)
            
            # Tabla para estadísticas de dificultad
            cursor.execute("""
                IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='DifficultyStats' AND xtype='U')
                CREATE TABLE DifficultyStats (
                    UserID BIGINT PRIMARY KEY,
                    CurrentDifficulty FLOAT DEFAULT 0.0,
                    TotalGames INT DEFAULT 0,
                    WinRate FLOAT DEFAULT 0.0,
                    HotStreak INT DEFAULT 0,
                    ColdStreak INT DEFAULT 0,
                    AvgBet FLOAT DEFAULT 0.0,
                    RiskProfile NVARCHAR(20) DEFAULT 'BALANCED',
                    LastUpdate DATETIME2 DEFAULT GETDATE()
                )
            """)
            
            conn.commit()
            print("✅ Sistema de dificultad dinámica inicializado")
            
        except pyodbc.Error as e:
            print(f"❌ Error inicializando sistema de dificultad: {e}")
        finally:
            conn.close()
    
    @staticmethod
    def calculate_dynamic_difficulty(user_id: int, bet_amount: int, game_type: str) -> Tuple[float, str]:
        """
        Calcula la dificultad dinámica para un jugador específico.
        
        Returns:
            Tuple[float, str]: (difficulty_modifier, explanation)
        """
        conn = pyodbc.connect(conn_str)
        cursor = conn.cursor()
        
        try:
            # Asegurar que el usuario existe sin sobrescribir el nombre
            ensure_user(user_id)
            
            # Obtener estadísticas del usuario
            cursor.execute("""
                SELECT CurrentDifficulty, TotalGames, WinRate, HotStreak, ColdStreak, 
                       AvgBet, RiskProfile, LastUpdate
                FROM DifficultyStats 
                WHERE UserID = ?
            """, (user_id,))
            
            stats = cursor.fetchone()
            
            if not stats or stats[1] < 5:  # Menos de 5 juegos
                return 0.0, "🆕 Jugador nuevo - Dificultad estándar"
            
            current_difficulty, total_games, win_rate, hot_streak, cold_streak, avg_bet, risk_profile, last_update = stats
            
            # Nuevos factores con más peso en apuestas altas y ganancias
            difficulty_factors = []
            
            # 1. Relación apuesta/promedio (30% peso)
            if avg_bet > 0:
                bet_ratio = bet_amount / avg_bet
                if bet_ratio > 3.0:
                    difficulty_factors.append(("very_high_bet", 0.25))
                elif bet_ratio > 2.0:
                    difficulty_factors.append(("high_bet", 0.15))
                elif bet_ratio > 1.5:
                    difficulty_factors.append(("elevated_bet", 0.08))
                elif bet_ratio < 0.5:
                    difficulty_factors.append(("low_bet", -0.10))
            
            # 2. Tasa de victoria (25% peso)
            if win_rate > 0.7:
                difficulty_factors.append(("very_high_winrate", 0.20))
            elif win_rate > 0.6:
                difficulty_factors.append(("high_winrate", 0.12))
            elif win_rate > 0.55:
                difficulty_factors.append(("medium_winrate", 0.06))
            elif win_rate < 0.3:
                difficulty_factors.append(("very_low_winrate", -0.15))
            elif win_rate < 0.4:
                difficulty_factors.append(("low_winrate", -0.08))
            
            # 3. Balance reciente (20% peso)
            balance_trend = DynamicDifficulty._get_balance_trend(user_id)
            if balance_trend > 0.3:
                difficulty_factors.append(("large_gains", 0.18))
            elif balance_trend > 0.15:
                difficulty_factors.append(("moderate_gains", 0.10))
            elif balance_trend < -0.3:
                difficulty_factors.append(("large_losses", -0.20))
            elif balance_trend < -0.15:
                difficulty_factors.append(("moderate_losses", -0.12))
            
            # 4. Rachas (15% peso)
            if hot_streak >= 7:
                difficulty_factors.append(("extreme_hot_streak", 0.15))
            elif hot_streak >= 5:
                difficulty_factors.append(("hot_streak", 0.10))
            elif hot_streak >= 3:
                difficulty_factors.append(("warm_streak", 0.05))
            elif cold_streak >= 7:
                difficulty_factors.append(("extreme_cold_streak", -0.18))
            elif cold_streak >= 5:
                difficulty_factors.append(("cold_streak", -0.12))
            elif cold_streak >= 3:
                difficulty_factors.append(("cool_streak", -0.06))
            
            # 5. Perfil de riesgo (10% peso)
            if risk_profile == "AGGRESSIVE":
                difficulty_factors.append(("aggressive_player", 0.08))
            elif risk_profile == "CONSERVATIVE":
                difficulty_factors.append(("conservative_player", -0.05))
            
            # 6. Ganancias totales acumuladas (peso variable según magnitud)
            total_winnings = DynamicDifficulty._get_total_winnings(user_id)
            if total_winnings > 50000:  # Ganancias muy altas
                difficulty_factors.append(("massive_winnings", 0.30))
            elif total_winnings > 20000:  # Ganancias altas
                difficulty_factors.append(("high_winnings", 0.20))
            elif total_winnings > 10000:  # Ganancias moderadas
                difficulty_factors.append(("moderate_winnings", 0.12))
            elif total_winnings > 5000:  # Ganancias pequeñas
                difficulty_factors.append(("small_winnings", 0.08))
            elif total_winnings < -10000:  # Pérdidas grandes
                difficulty_factors.append(("heavy_losses", -0.25))
            elif total_winnings < -5000:  # Pérdidas moderadas
                difficulty_factors.append(("moderate_losses_total", -0.15))
            elif total_winnings < -1000:  # Pérdidas pequeñas
                difficulty_factors.append(("small_losses", -0.08))
            
            # Calcular nueva dificultad con más rango (-0.5 a 0.5)
            new_difficulty = sum(factor[1] for factor in difficulty_factors)
            
            # Suavizar cambios manteniendo más historial (60% peso al historial)
            if current_difficulty is not None:
                new_difficulty = current_difficulty * 0.6 + new_difficulty * 0.4
            
            # Ampliar rango de dificultad
            new_difficulty = max(-0.5, min(0.5, new_difficulty))
            
            # Actualizar estadísticas
            cursor.execute("""
                UPDATE DifficultyStats 
                SET CurrentDifficulty = ?, LastUpdate = GETDATE()
                WHERE UserID = ?
            """, (new_difficulty, user_id))
            
            conn.commit()
            
            # Generar explicación
            explanation = DynamicDifficulty._generate_explanation(new_difficulty, difficulty_factors)
            
            return new_difficulty, explanation
            
        except Exception as e:
            print(f"Error calculando dificultad: {e}")
            return 0.0, "⚠️ Error calculando dificultad - Usando estándar"
        finally:
            conn.close()
    
    @staticmethod
    def apply_difficulty_to_odds(base_odds: float, difficulty_modifier: float) -> float:
        """
        Aplica el modificador de dificultad a las probabilidades base.
        
        Args:
            base_odds: Probabilidad base (0.0 a 1.0)
            difficulty_modifier: Modificador de dificultad (-0.5 a 0.5)
            
        Returns:
            float: Probabilidad ajustada
        """
        # Aplicar modificador de dificultad
        adjusted_odds = base_odds - difficulty_modifier
        
        # Asegurar que las probabilidades estén en rango válido
        return max(0.01, min(0.99, adjusted_odds))
    
    @staticmethod
    def record_game_result(user_id: int, game_type: str, bet_amount: int, 
                          result: str, winnings: int, difficulty_modifier: float, 
                          new_balance: int):
        """Registra el resultado de un juego para futuras calculaciones."""
        conn = pyodbc.connect(conn_str)
        cursor = conn.cursor()
        
        try:
            # Registrar resultado
            cursor.execute("""
                INSERT INTO GameResults (UserID, GameType, BetAmount, Result, Winnings, DifficultyModifier, Balance)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (user_id, game_type, bet_amount, result, winnings, difficulty_modifier, new_balance))
            
            # Actualizar estadísticas
            DynamicDifficulty._update_user_stats(user_id, result, bet_amount, winnings)
            
            conn.commit()
            
        except Exception as e:
            print(f"Error registrando resultado: {e}")
        finally:
            conn.close()
    
    @staticmethod
    def get_difficulty_stats(user_id: int) -> Dict[str, Any]:
        """Obtiene estadísticas detalladas de dificultad para un usuario."""
        conn = pyodbc.connect(conn_str)
        cursor = conn.cursor()
        
        try:
            # Obtener estadísticas principales
            cursor.execute("""
                SELECT CurrentDifficulty, TotalGames, WinRate, HotStreak, ColdStreak, 
                       AvgBet, RiskProfile, LastUpdate
                FROM DifficultyStats 
                WHERE UserID = ?
            """, (user_id,))
            
            stats = cursor.fetchone()
            
            if not stats or stats[1] < 5:
                return {'status': 'new_player'}
            
            current_difficulty, total_games, win_rate, hot_streak, cold_streak, avg_bet, risk_profile, last_update = stats
            
            # Obtener juegos recientes
            recent_games = DynamicDifficulty._get_recent_games(user_id, 24)
            
            # Obtener último juego
            cursor.execute("""
                SELECT TOP 1 Timestamp FROM GameResults 
                WHERE UserID = ? 
                ORDER BY Timestamp DESC
            """, (user_id,))
            
            last_game_result = cursor.fetchone()
            last_game = last_game_result[0] if last_game_result else None
            
            return {
                'status': 'experienced_player',
                'current_difficulty': current_difficulty,
                'total_games': total_games,
                'win_rate': win_rate,
                'hot_streak': hot_streak,
                'cold_streak': cold_streak,
                'avg_bet': avg_bet,
                'risk_profile': risk_profile,
                'recent_games_24h': recent_games,
                'last_game': last_game,
                'last_update': last_update
            }
            
        except Exception as e:
            print(f"Error obteniendo estadísticas: {e}")
            return {'status': 'error'}
        finally:
            conn.close()
    
    @staticmethod
    def _get_recent_games(user_id: int, hours: int) -> int:
        """Obtiene el número de juegos en las últimas X horas."""
        conn = pyodbc.connect(conn_str)
        cursor = conn.cursor()
        
        try:
            cursor.execute("""
                SELECT COUNT(*) FROM GameResults 
                WHERE UserID = ? AND Timestamp > DATEADD(hour, -?, GETDATE())
            """, (user_id, hours))
            
            result = cursor.fetchone()
            return result[0] if result else 0
            
        except Exception as e:
            print(f"Error obteniendo juegos recientes: {e}")
            return 0
        finally:
            conn.close()
    
    @staticmethod
    def _get_balance_trend(user_id: int) -> float:
        """Calcula la tendencia del balance en los últimos juegos."""
        conn = pyodbc.connect(conn_str)
        cursor = conn.cursor()
        
        try:
            cursor.execute("""
                SELECT TOP 20 Balance FROM GameResults 
                WHERE UserID = ? 
                ORDER BY Timestamp DESC
            """, (user_id,))
            
            balances = [row[0] for row in cursor.fetchall()]
            
            if len(balances) < 5:
                return 0.0
            
            # Calcular tendencia simple
            recent_avg = sum(balances[:5]) / 5
            older_avg = sum(balances[-5:]) / 5
            
            if older_avg > 0:
                return (recent_avg - older_avg) / older_avg
            
            return 0.0
            
        except Exception as e:
            print(f"Error calculando tendencia: {e}")
            return 0.0
        finally:
            conn.close()
    
    @staticmethod
    def _update_user_stats(user_id: int, result: str, bet_amount: int, winnings: int):
        """Actualiza las estadísticas del usuario."""
        conn = pyodbc.connect(conn_str)
        cursor = conn.cursor()
        
        try:
            # Obtener estadísticas actuales
            cursor.execute("""
                SELECT TotalGames, WinRate, HotStreak, ColdStreak, AvgBet
                FROM DifficultyStats 
                WHERE UserID = ?
            """, (user_id,))
            
            stats = cursor.fetchone()
            
            if not stats:
                # Crear nuevo registro
                cursor.execute("""
                    INSERT INTO DifficultyStats (UserID, TotalGames, WinRate, HotStreak, ColdStreak, AvgBet)
                    VALUES (?, 1, ?, ?, ?, ?)
                """, (user_id, 1.0 if result == 'win' else 0.0, 
                      1 if result == 'win' else 0, 
                      1 if result == 'loss' else 0, 
                      bet_amount))
            else:
                total_games, win_rate, hot_streak, cold_streak, avg_bet = stats
                
                # Actualizar estadísticas
                new_total_games = total_games + 1
                new_win_rate = (win_rate * total_games + (1 if result == 'win' else 0)) / new_total_games
                new_avg_bet = (avg_bet * total_games + bet_amount) / new_total_games
                
                # Actualizar rachas
                if result == 'win':
                    new_hot_streak = hot_streak + 1
                    new_cold_streak = 0
                else:
                    new_hot_streak = 0
                    new_cold_streak = cold_streak + 1
                
                # Determinar perfil de riesgo
                if new_avg_bet > 1000:
                    risk_profile = "AGGRESSIVE"
                elif new_avg_bet < 200:
                    risk_profile = "CONSERVATIVE"
                else:
                    risk_profile = "BALANCED"
                
                cursor.execute("""
                    UPDATE DifficultyStats 
                    SET TotalGames = ?, WinRate = ?, HotStreak = ?, ColdStreak = ?, 
                        AvgBet = ?, RiskProfile = ?, LastUpdate = GETDATE()
                    WHERE UserID = ?
                """, (new_total_games, new_win_rate, new_hot_streak, new_cold_streak, 
                      new_avg_bet, risk_profile, user_id))
            
            conn.commit()
            
        except Exception as e:
            print(f"Error actualizando estadísticas: {e}")
        finally:
            conn.close()
    
    @staticmethod
    def _generate_explanation(difficulty: float, factors: list) -> str:
        """Genera una explicación legible de la dificultad."""
        if abs(difficulty) < 0.05:
            return "🎯 Dificultad equilibrada"
        
        explanations = {
            "very_high_bet": "apuesta muy alta",
            "high_bet": "apuesta alta",
            "elevated_bet": "apuesta elevada",
            "low_bet": "apuesta conservadora",
            "very_high_winrate": "tasa de victorias muy alta",
            "high_winrate": "alta tasa de victorias",
            "medium_winrate": "buena tasa de victorias",
            "very_low_winrate": "tasa de victorias muy baja",
            "low_winrate": "baja tasa de victorias",
            "large_gains": "grandes ganancias recientes",
            "moderate_gains": "ganancias moderadas",
            "large_losses": "grandes pérdidas recientes",
            "moderate_losses": "pérdidas moderadas",
            "extreme_hot_streak": "racha ganadora extrema",
            "hot_streak": "racha ganadora",
            "warm_streak": "tendencia positiva",
            "extreme_cold_streak": "racha perdedora extrema",
            "cold_streak": "racha perdedora",
            "cool_streak": "tendencia negativa",
            "aggressive_player": "perfil agresivo",
            "conservative_player": "perfil conservador",
            "massive_winnings": "ganancias masivas acumuladas",
            "high_winnings": "altas ganancias acumuladas",
            "moderate_winnings": "ganancias moderadas acumuladas",
            "small_winnings": "pequeñas ganancias acumuladas",
            "heavy_losses": "grandes pérdidas acumuladas",
            "moderate_losses_total": "pérdidas moderadas acumuladas",
            "small_losses": "pequeñas pérdidas acumuladas"
        }
        
        main_factors = []
        for factor in factors[:3]:
            if factor[0] in explanations:
                explanation = explanations[factor[0]]
                if explanation:
                    main_factors.append(explanation)
        
        if not main_factors:
            return "🎯 Dificultad ajustada automáticamente"
        
        if difficulty > 0:
            return f"🔥 Dificultad aumentada por: {', '.join(main_factors)}"
        else:
            return f"🍀 Dificultad reducida por: {', '.join(main_factors)}"
    
    @staticmethod
    def _get_total_winnings(user_id: int) -> int:
        """Calcula las ganancias totales acumuladas del jugador."""
        conn = pyodbc.connect(conn_str)
        cursor = conn.cursor()
        
        try:
            cursor.execute("""
                SELECT SUM(Winnings) FROM GameResults 
                WHERE UserID = ?
            """, (user_id,))
            
            result = cursor.fetchone()
            return result[0] if result and result[0] is not None else 0
            
        except Exception as e:
            print(f"Error obteniendo ganancias totales: {e}")
            return 0
        finally:
            conn.close()

# Inicializar el sistema al importar
DynamicDifficulty.init_difficulty_db()
