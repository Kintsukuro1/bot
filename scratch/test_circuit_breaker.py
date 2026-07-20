import asyncio
import sys
import os

# Asegurar que el directorio raíz está en el path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.db import init_db, db_cursor, ensure_user, get_balance
from src.services.casino_service import CasinoService, CasinoCircuitBreakerError

async def main():
    print("--- Inicializando Base de Datos e Invocando Migraciones ---")
    try:
        init_db()
        print("Tablas verificadas/creadas con exito.")
    except Exception as e:
        print(f"Error al inicializar la base de datos: {e}")
        return

    print("\n--- Verificando Tablas Nuevas en la DB ---")
    with db_cursor() as cursor:
        cursor.execute("SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = 'gamedailystats')")
        has_stats = cursor.fetchone()[0]
        cursor.execute("SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = 'gamecircuitbreaker')")
        has_breaker = cursor.fetchone()[0]
        
    print(f"Tabla GameDailyStats existe: {has_stats}")
    print(f"Tabla GameCircuitBreaker existe: {has_breaker}")
    if not (has_stats and has_breaker):
        print("[ERROR] Las tablas no fueron creadas.")
        return

    print("\n--- Probando Simulacion del Circuit Breaker ---")
    test_game = "test_game"
    test_user = 999444
    
    # 1. Limpiar datos viejos de test
    with db_cursor() as cursor:
        cursor.execute("DELETE FROM GameDailyStats WHERE GameKey = %s", (test_game,))
        cursor.execute("DELETE FROM GameCircuitBreaker WHERE GameKey = %s", (test_game,))
        cursor.execute("DELETE FROM Users WHERE UserID = %s", (test_user,))

    # Asegurar usuario
    await asyncio.to_thread(ensure_user, test_user, "CircuitUser")
    
    # Set total server balance to a fixed known amount, e.g. 100,000 coins
    with db_cursor() as cursor:
        cursor.execute("UPDATE Users SET Balance = 100000 WHERE UserID = %s", (test_user,))
    
    # Forzar recarga del cache de balance total en CasinoService
    # (Como es el único usuario, el balance total del servidor será 100,000 monedas)
    total_economia = await CasinoService.get_total_server_balance()
    print(f"Economia total del servidor calculada: {total_economia:,} monedas")
    
    # 2. Intentar colocar una apuesta inicial - Debe funcionar bien
    try:
        success, nuevo_saldo = await CasinoService.place_bet(test_user, 1000, test_game)
        print(f"Apuesta inicial de 1000 monedas exitosa. Saldo restante: {nuevo_saldo}")
    except CasinoCircuitBreakerError as e:
        safe_msg = str(e).encode('ascii', errors='replace').decode('ascii')
        print(f"[ERROR] Error inesperado: El juego ya estaba bloqueado: {safe_msg}")
        return

    # 3. Simular que el juego paga 30,000 monedas (30% de la economía, que es > 25%)
    # Settle win de 31,000 monedas (bet_amount=1000, profit=30,000 netas)
    print("Settle win de 31,000 monedas (ganancia neta de 30,000)...")
    nuevo_saldo, impuesto = await CasinoService.settle_win(
        user_id=test_user,
        bet_amount=1000,
        winnings=31000,
        game_type=test_game,
        difficulty_modifier=0.0,
        current_balance=nuevo_saldo
    )
    print(f"Premio neto acreditado. Nuevo saldo del usuario: {nuevo_saldo}")

    # 4. Verificar si el circuit breaker se activó
    is_available, motivo = await CasinoService.check_game_circuit_breaker(test_game)
    if not is_available:
        safe_motivo = motivo.encode('ascii', errors='replace').decode('ascii')
        print(f"[OK] El Circuit Breaker se activo correctamente. Motivo: {safe_motivo}")
    else:
        print("[ERROR] El Circuit Breaker no se activo.")
        return

    # 5. Intentar realizar otra apuesta - Debe ser rechazada con CasinoCircuitBreakerError
    print("Intentando realizar otra apuesta en el juego bloqueado...")
    try:
        await CasinoService.place_bet(test_user, 500, test_game)
        print("[ERROR] Se permitio la apuesta en un juego bloqueado.")
    except CasinoCircuitBreakerError as e:
        safe_msg = str(e).encode('ascii', errors='replace').decode('ascii')
        print(f"[OK] La apuesta fue bloqueada correctamente con el error: {safe_msg}")

    # 6. Limpieza final de datos de test
    with db_cursor() as cursor:
        cursor.execute("DELETE FROM GameDailyStats WHERE GameKey = %s", (test_game,))
        cursor.execute("DELETE FROM GameCircuitBreaker WHERE GameKey = %s", (test_game,))
        cursor.execute("DELETE FROM Users WHERE UserID = %s", (test_user,))
    print("\n--- Verificacion manual completada con exito ---")

if __name__ == '__main__':
    asyncio.run(main())
