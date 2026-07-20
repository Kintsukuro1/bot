import unittest
from unittest.mock import MagicMock, patch
import asyncio
import sys
import os

# Asegurar que el directorio raíz está en el path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.services import CasinoService

class TestCasinoService(unittest.TestCase):
    
    @patch('src.services.casino_service.CasinoService.check_game_circuit_breaker', return_value=(True, ""))
    @patch('src.db.db_cursor')
    def test_place_bet_success(self, mock_db_cursor, mock_check_cb):
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = (4000,) # Saldo restante tras restar
        mock_db_cursor.return_value.__enter__.return_value = mock_cursor
        
        success, new_balance = asyncio.run(CasinoService.place_bet(12345, 1000, "slots"))
        
        self.assertTrue(success)
        self.assertEqual(new_balance, 4000)
        # Verificar que se descuenta el balance y se registra la transacción
        mock_cursor.execute.assert_any_call("""
            UPDATE Users 
            SET Balance = Balance - %s 
            WHERE UserID = %s AND Balance >= %s
            RETURNING Balance
        """, (1000, 12345, 1000))

    @patch('src.services.casino_service.CasinoService.check_game_circuit_breaker', return_value=(True, ""))
    @patch('src.db.db_cursor')
    def test_place_bet_insufficient_funds(self, mock_db_cursor, mock_check_cb):
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = None
        mock_db_cursor.return_value.__enter__.return_value = mock_cursor
        
        success, new_balance = asyncio.run(CasinoService.place_bet(12345, 10000, "slots"))
        
        self.assertFalse(success)
        self.assertEqual(new_balance, 0)

    @patch('src.db.db_cursor')
    def test_settle_win(self, mock_db_cursor):
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = None
        mock_db_cursor.return_value.__enter__.return_value = mock_cursor
        
        # Settle a win of 2000 coins on a 1000 coin bet
        nuevo_saldo, impuesto = asyncio.run(
            CasinoService.settle_win(12345, 1000, 2000, "slots", 0.0, 3000)
        )
        
        self.assertEqual(nuevo_saldo, 4940) # 2000 - 3% (60) = 1940. 3000 + 1940 = 4940
        self.assertEqual(impuesto, 60)
        # Verificar que se añade el premio neto y se registra el resultado
        mock_cursor.execute.assert_any_call("""
            INSERT INTO Users (UserID, Balance) VALUES (%s, %s)
            ON CONFLICT (UserID) DO UPDATE SET Balance = Users.Balance + EXCLUDED.Balance
            """, (12345, 1940))

    @patch('src.db.db_cursor')
    def test_settle_loss(self, mock_db_cursor):
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = None
        mock_db_cursor.return_value.__enter__.return_value = mock_cursor
        
        nuevo_saldo = asyncio.run(
            CasinoService.settle_loss(12345, 1000, "slots", 0.0, 3000)
        )
        
        self.assertEqual(nuevo_saldo, 3000)
        # Verificar que se registra la pérdida en GameResults
        mock_cursor.execute.assert_any_call("""
            INSERT INTO GameResults (UserID, GameType, BetAmount, Result, Winnings, DifficultyModifier, Balance)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, (12345, "slots", 1000, "loss", 0, 0.0, 3000))

    @patch('src.db.db_cursor')
    @patch('src.db.get_balance')
    def test_refund_bet(self, mock_get_balance, mock_db_cursor):
        mock_cursor = MagicMock()
        mock_db_cursor.return_value.__enter__.return_value = mock_cursor
        mock_get_balance.return_value = 4000
        
        nuevo_saldo = asyncio.run(
            CasinoService.refund_bet(12345, 1000, "slots", "timeout")
        )
        
        self.assertEqual(nuevo_saldo, 4000)
        # Verificar que se suma el reembolso
        mock_cursor.execute.assert_any_call("""
            INSERT INTO Users (UserID, Balance) VALUES (%s, %s)
            ON CONFLICT (UserID) DO UPDATE SET Balance = Users.Balance + EXCLUDED.Balance
            """, (12345, 1000))

    @patch('src.db.get_casino_lockout_data')
    @patch('src.db.apply_casino_lockout')
    @patch('src.db.update_casino_reference_balance')
    @patch('src.db.get_balance')
    def test_check_casino_lockout_active(self, mock_get_balance, mock_update, mock_apply, mock_get_lockout):
        from datetime import datetime, timedelta
        bloqueado_hasta = datetime.now() + timedelta(minutes=15)
        mock_get_lockout.return_value = (5000, 10000, datetime.now(), bloqueado_hasta)
        
        can_play, msg = asyncio.run(CasinoService.check_casino_lockout(12345))
        self.assertFalse(can_play)
        self.assertIn("tómate un descanso", msg)

    @patch('src.db.get_casino_lockout_data')
    @patch('src.db.apply_casino_lockout')
    @patch('src.db.update_casino_reference_balance')
    @patch('src.db.get_balance')
    def test_check_casino_lockout_not_active(self, mock_get_balance, mock_update, mock_apply, mock_get_lockout):
        mock_get_lockout.return_value = (5000, None, None, None)
        mock_get_balance.return_value = 5000
        
        can_play, msg = asyncio.run(CasinoService.check_casino_lockout(12345))
        self.assertTrue(can_play)
        mock_update.assert_called_once()

    @patch('src.db.get_casino_lockout_data')
    @patch('src.db.apply_casino_lockout')
    def test_check_and_apply_winstreak_lockout_trigger(self, mock_apply, mock_get_lockout):
        from datetime import datetime
        mock_get_lockout.return_value = (5000, 10000, datetime.now(), None)
        
        locked = asyncio.run(CasinoService.check_and_apply_winstreak_lockout(12345, 12500))
        self.assertTrue(locked)
        mock_apply.assert_called_once()

    @patch('src.db.get_casino_lockout_data')
    @patch('src.db.apply_casino_lockout')
    def test_check_and_apply_winstreak_lockout_no_trigger(self, mock_apply, mock_get_lockout):
        from datetime import datetime
        mock_get_lockout.return_value = (5000, 10000, datetime.now(), None)
        
        locked = asyncio.run(CasinoService.check_and_apply_winstreak_lockout(12345, 12400))
        self.assertFalse(locked)
        mock_apply.assert_not_called()

class TestCrashTicket(unittest.IsolatedAsyncioTestCase):
    
    @patch('src.commands.casino.crash.usuario_tiene_mejora')
    @patch('src.commands.casino.crash.CasinoService.settle_win')
    @patch('src.commands.casino.crash.process_post_game_events')
    @patch('src.commands.casino.crash.CrashView._safe_edit_or_followup')
    async def test_finalizar_juego_retiro_no_debuff(self, mock_safe_edit, mock_post_events, mock_settle_win, mock_tiene_mejora):
        from src.commands.casino.crash import CrashView
        
        # Mocks
        mock_tiene_mejora.return_value = False
        mock_settle_win.return_value = (6940, 60)
        
        mock_ctx = MagicMock()
        mock_user = MagicMock()
        mock_user.id = 12345
        
        # Initialize CrashView with ticket_activo = True
        view = CrashView(
            ctx_or_interaction=mock_ctx,
            user=mock_user,
            apuesta=1000,
            saldo_post_apuesta=5000,
            crash_point=2.5,
            difficulty_modifier=0.0,
            ticket_activo=True
        )
        
        # Simulate final multiplier
        view.current_mult = 2.0
        view.crash_mult = 2.0
        
        # Call finalize
        await view._finalizar_juego(motivo="retiro")
        
        # Check that CasinoService.settle_win was called
        # with full winnings (1000 * 2.0 = 2000), NOT debuffed (which would have been 1300)
        mock_settle_win.assert_called_once_with(
            12345,      # user_id
            1000,       # apuesta
            2000,       # ganancia_total (no debuff!)
            'crash',    # game_type
            0.0,        # difficulty_modifier
            5000        # saldo_post_apuesta
        )

    @patch('src.commands.casino.crash.usuario_tiene_mejora')
    @patch('src.commands.casino.crash.CasinoService.settle_win')
    @patch('src.commands.casino.crash.process_post_game_events')
    @patch('src.commands.casino.crash.CrashView._safe_edit_or_followup')
    async def test_finalizar_juego_completado_no_debuff(self, mock_safe_edit, mock_post_events, mock_settle_win, mock_tiene_mejora):
        from src.commands.casino.crash import CrashView
        
        # Mocks
        mock_tiene_mejora.return_value = False
        mock_settle_win.return_value = (7425, 75)
        
        mock_ctx = MagicMock()
        mock_user = MagicMock()
        mock_user.id = 12345
        
        # Initialize CrashView with ticket_activo = True
        view = CrashView(
            ctx_or_interaction=mock_ctx,
            user=mock_user,
            apuesta=1000,
            saldo_post_apuesta=5000,
            crash_point=2.5,
            difficulty_modifier=0.0,
            ticket_activo=True
        )
        
        # Simulate final multiplier
        view.current_mult = 2.5
        view.crash_mult = 2.5
        
        # Call finalize
        await view._finalizar_juego(motivo="completado")
        
        # Check that CasinoService.settle_win was called
        # with full winnings (1000 * 2.5 = 2500), NOT debuffed (which would have been 1625)
        mock_settle_win.assert_called_once_with(
            12345,      # user_id
            1000,       # apuesta
            2500,       # ganancia_total (no debuff!)
            'crash',    # game_type
            0.0,        # difficulty_modifier
            5000        # saldo_post_apuesta
        )

    @patch('src.commands.casino.crash.usuario_tiene_mejora')
    @patch('src.commands.casino.crash.CasinoService.settle_win')
    @patch('src.commands.casino.crash.CasinoService.check_and_apply_winstreak_lockout')
    @patch('src.commands.casino.crash.process_post_game_events')
    @patch('src.commands.casino.crash.CrashView._safe_edit_or_followup')
    async def test_finalizar_juego_retiro_triggers_lockout(self, mock_safe_edit, mock_post_events, mock_lockout, mock_settle_win, mock_tiene_mejora):
        from src.commands.casino.crash import CrashView
        
        # Mocks
        mock_tiene_mejora.return_value = False
        mock_settle_win.return_value = (6940, 60)
        mock_lockout.return_value = True
        
        mock_ctx = MagicMock()
        mock_user = MagicMock()
        mock_user.id = 12345
        
        view = CrashView(
            ctx_or_interaction=mock_ctx,
            user=mock_user,
            apuesta=1000,
            saldo_post_apuesta=5000,
            crash_point=2.5,
            difficulty_modifier=0.0,
            ticket_activo=False
        )
        view.current_mult = 2.0
        view.crash_mult = 2.0
        
        await view._finalizar_juego(motivo="retiro")
        
        mock_lockout.assert_called_once_with(12345, 6940)
        called_embed = mock_safe_edit.call_args[0][1]
        self.assertIn("tómate un descanso de 25 minutos", called_embed.description)

    @patch('src.commands.casino.crash.usuario_tiene_mejora')
    @patch('src.commands.casino.crash.CasinoService.settle_win')
    @patch('src.commands.casino.crash.CasinoService.check_and_apply_winstreak_lockout')
    @patch('src.commands.casino.crash.process_post_game_events')
    @patch('src.commands.casino.crash.CrashView._safe_edit_or_followup')
    async def test_finalizar_juego_completado_triggers_lockout(self, mock_safe_edit, mock_post_events, mock_lockout, mock_settle_win, mock_tiene_mejora):
        from src.commands.casino.crash import CrashView
        
        # Mocks
        mock_tiene_mejora.return_value = False
        mock_settle_win.return_value = (7425, 75)
        mock_lockout.return_value = True
        
        mock_ctx = MagicMock()
        mock_user = MagicMock()
        mock_user.id = 12345
        
        view = CrashView(
            ctx_or_interaction=mock_ctx,
            user=mock_user,
            apuesta=1000,
            saldo_post_apuesta=5000,
            crash_point=2.5,
            difficulty_modifier=0.0,
            ticket_activo=False
        )
        view.current_mult = 2.5
        view.crash_mult = 2.5
        
        await view._finalizar_juego(motivo="completado")
        
        mock_lockout.assert_called_once_with(12345, 7425)
        called_embed = mock_safe_edit.call_args[0][1]
        self.assertIn("tómate un descanso de 25 minutos", called_embed.description)

class TestCrashGeneration(unittest.IsolatedAsyncioTestCase):
    
    @patch('src.commands.casino.crash.get_provably_fair_seeds')
    @patch('src.commands.casino.crash.advance_provably_fair_nonce')
    @patch('src.commands.casino.crash.get_uniform_float')
    @patch('src.commands.casino.crash.ensure_user')
    @patch('src.commands.casino.crash.CasinoService.check_casino_lockout')
    @patch('src.commands.casino.crash.CasinoService.place_bet')
    @patch('src.commands.casino.crash.DynamicDifficulty.calculate_dynamic_difficulty')
    @patch('src.commands.casino.crash.usuario_tiene_item')
    @patch('src.commands.casino.crash.CrashView')
    async def test_crash_game_generation_math(
        self, mock_crash_view, mock_tiene_item, mock_calc_diff, 
        mock_place_bet, mock_lockout, mock_ensure, mock_get_uniform, mock_advance_nonce, mock_get_seeds
    ):
        from src.commands.casino.crash import Crash
        from unittest.mock import AsyncMock
        
        # Mocks setup
        mock_get_seeds.return_value = {"server_seed": "server", "client_seed": "client", "nonce": 5}
        mock_advance_nonce.return_value = 6
        mock_ensure.return_value = None
        mock_lockout.return_value = (True, "")
        mock_place_bet.return_value = (True, 9000)
        mock_calc_diff.return_value = (0.0, "normal") # difficulty modifier = 0.0 => edge = 0.04
        mock_tiene_item.return_value = False
        
        # We will mock the Cog and interaction
        bot = MagicMock()
        cog = Crash(bot)
        
        interaction = MagicMock()
        interaction.user.id = 12345
        interaction.user.name = "TestUser"
        interaction.response = MagicMock()
        interaction.response.defer = AsyncMock()
        interaction.followup.send = AsyncMock()
        
        mock_crash_view.return_value.run_crash = AsyncMock()
        
        # Test Case 1: U = 0.01 (which is <= edge, so val <= 1.0, should floor to 1.00)
        mock_get_uniform.return_value = 0.01
        await cog._crash_game(interaction, 1000, is_slash=True)
        
        # Verify CrashView was instantiated with crash_point = 1.00
        mock_crash_view.assert_called_with(
            interaction, interaction.user, 1000, 9000, 1.00, 0.0, "normal", False
        )
        
        # Test Case 2: U = 0.5 (val = 1.94, crash_point should be 1.94)
        mock_get_uniform.return_value = 0.5
        await cog._crash_game(interaction, 1000, is_slash=True)
        mock_crash_view.assert_called_with(
            interaction, interaction.user, 1000, 9000, 1.94, 0.0, "normal", False
        )

        # Test Case 3: U = 0.9999 (val = 11.58, crash_point should be 11.58)
        mock_get_uniform.return_value = 0.9999
        await cog._crash_game(interaction, 1000, is_slash=True)
        mock_crash_view.assert_called_with(
            interaction, interaction.user, 1000, 9000, 11.58, 0.0, "normal", False
        )


class TestCasinoCircuitBreaker(unittest.TestCase):
    @patch('src.db.check_game_circuit_breaker_db')
    @patch('src.db.db_cursor')
    def test_place_bet_blocked_by_circuit_breaker(self, mock_db_cursor, mock_check_cb):
        # Configurar el circuit breaker para reportar que el juego está bloqueado
        mock_check_cb.return_value = (False, "Bloqueado por pruebas")
        
        # Intentar apostar debe lanzar la excepción CasinoCircuitBreakerError
        from src.services.casino_service import CasinoCircuitBreakerError
        with self.assertRaises(CasinoCircuitBreakerError) as context:
            asyncio.run(CasinoService.place_bet(12345, 1000, "slots"))
        
        self.assertIn("Este juego está temporalmente deshabilitado", str(context.exception))

    @patch('src.services.casino_service.CasinoService._notify_staff_circuit_breaker')
    @patch('src.services.casino_service.CasinoService.get_total_server_balance')
    @patch('src.db.track_game_payout_db')
    @patch('src.db.activar_circuit_breaker_db')
    @patch('src.db.db_cursor')
    def test_settle_win_triggers_circuit_breaker(self, mock_db_cursor, mock_activar, mock_track, mock_get_total_balance, mock_notify):
        # 1. Configurar la economía total en 100,000 monedas
        mock_get_total_balance.return_value = 100000
        
        # 2. Configurar que el juego ha pagado acumuladamente 30,000 monedas hoy (30% > 25%)
        mock_track.return_value = 30000
        
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = None
        mock_db_cursor.return_value.__enter__.return_value = mock_cursor
        
        # 3. Procesar una victoria
        asyncio.run(
            CasinoService.settle_win(12345, 1000, 2000, "slots", 0.0, 5000)
        )
        
        # Verificar que se activa el circuit breaker
        mock_activar.assert_called_once_with("slots", 2, unittest.mock.ANY)
        # Verificar que se notifica al staff
        mock_notify.assert_called_once()

    @patch('src.services.casino_service.CasinoService.get_total_server_balance')
    @patch('src.db.track_game_payout_db')
    @patch('src.db.activar_circuit_breaker_db')
    @patch('src.db.db_cursor')
    def test_settle_win_does_not_trigger_circuit_breaker_below_threshold(self, mock_db_cursor, mock_activar, mock_track, mock_get_total_balance):
        # 1. Configurar la economía total en 100,000 monedas
        mock_get_total_balance.return_value = 100000
        
        # 2. Configurar que el juego ha pagado acumuladamente 20,000 monedas hoy (20% < 25%)
        mock_track.return_value = 20000
        
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = None
        mock_db_cursor.return_value.__enter__.return_value = mock_cursor
        
        # 3. Procesar una victoria
        asyncio.run(
            CasinoService.settle_win(12345, 1000, 2000, "slots", 0.0, 5000)
        )
        
        # Verificar que NO se activa el circuit breaker
        mock_activar.assert_not_called()


if __name__ == '__main__':
    unittest.main()
