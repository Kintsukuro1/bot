import unittest
from unittest.mock import MagicMock, patch
import asyncio
import sys
import os

# Asegurar que el directorio raíz está en el path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.services import CasinoService

class TestCasinoService(unittest.TestCase):
    
    @patch('src.db.db_cursor')
    def test_place_bet_success(self, mock_db_cursor):
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

    @patch('src.db.db_cursor')
    def test_place_bet_insufficient_funds(self, mock_db_cursor):
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
        nuevo_saldo = asyncio.run(
            CasinoService.settle_win(12345, 1000, 2000, "slots", 0.0, 3000)
        )
        
        self.assertEqual(nuevo_saldo, 5000)
        # Verificar que se añade el premio y se registra el resultado
        mock_cursor.execute.assert_any_call("""
            INSERT INTO Users (UserID, Balance) VALUES (%s, %s)
            ON CONFLICT (UserID) DO UPDATE SET Balance = Users.Balance + EXCLUDED.Balance
            """, (12345, 2000))

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

class TestCrashTicket(unittest.IsolatedAsyncioTestCase):
    
    @patch('src.commands.casino.crash.usuario_tiene_mejora')
    @patch('src.commands.casino.crash.process_crash_payout_atomic')
    @patch('src.commands.casino.crash.process_post_game_events')
    @patch('src.commands.casino.crash.CrashView._safe_edit_or_followup')
    async def test_finalizar_juego_retiro_no_debuff(self, mock_safe_edit, mock_post_events, mock_payout_atomic, mock_tiene_mejora):
        from src.commands.casino.crash import CrashView
        
        # Mocks
        mock_tiene_mejora.return_value = False
        
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
        
        # Check that process_crash_payout_atomic was called
        # with full winnings (1000 * 2.0 = 2000), NOT debuffed (which would have been 1300)
        mock_payout_atomic.assert_called_once_with(
            12345,      # user_id
            1000,       # apuesta
            2000,       # ganancia_total (no debuff!)
            1000,       # ganancia_neta
            'win',      # result_type
            0.0,        # difficulty_modifier
            7000,       # nuevo_saldo
            "Crash: retirado x2.00" # desc_transaccion
        )

    @patch('src.commands.casino.crash.usuario_tiene_mejora')
    @patch('src.commands.casino.crash.process_crash_payout_atomic')
    @patch('src.commands.casino.crash.process_post_game_events')
    @patch('src.commands.casino.crash.CrashView._safe_edit_or_followup')
    async def test_finalizar_juego_completado_no_debuff(self, mock_safe_edit, mock_post_events, mock_payout_atomic, mock_tiene_mejora):
        from src.commands.casino.crash import CrashView
        
        # Mocks
        mock_tiene_mejora.return_value = False
        
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
        
        # Check that process_crash_payout_atomic was called
        # with full winnings (1000 * 2.5 = 2500), NOT debuffed (which would have been 1625)
        mock_payout_atomic.assert_called_once_with(
            12345,      # user_id
            1000,       # apuesta
            2500,       # ganancia_total (no debuff!)
            1500,       # ganancia_neta
            'win',      # result_type
            0.0,        # difficulty_modifier
            7500,       # nuevo_saldo
            "Crash: completó sin explotar x2.50" # desc_transaccion
        )

class TestCrashGeneration(unittest.IsolatedAsyncioTestCase):
    
    @patch('src.commands.casino.crash.get_provably_fair_seeds')
    @patch('src.commands.casino.crash.advance_provably_fair_nonce')
    @patch('src.commands.casino.crash.get_uniform_float')
    @patch('src.commands.casino.crash.ensure_user')
    @patch('src.commands.casino.crash.deduct_balance')
    @patch('src.commands.casino.crash.DynamicDifficulty.calculate_dynamic_difficulty')
    @patch('src.commands.casino.crash.usuario_tiene_item')
    @patch('src.commands.casino.crash.CrashView')
    async def test_crash_game_generation_math(
        self, mock_crash_view, mock_tiene_item, mock_calc_diff, 
        mock_deduct, mock_ensure, mock_get_uniform, mock_advance_nonce, mock_get_seeds
    ):
        from src.commands.casino.crash import Crash
        from unittest.mock import AsyncMock
        
        # Mocks setup
        mock_get_seeds.return_value = {"server_seed": "server", "client_seed": "client", "nonce": 5}
        mock_advance_nonce.return_value = 6
        mock_ensure.return_value = None
        mock_deduct.return_value = (True, 9000)
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
        
        # Test Case 2: U = 0.5 (val = 0.96 / 0.5 = 1.92, crash_point should be 1.92)
        mock_get_uniform.return_value = 0.5
        await cog._crash_game(interaction, 1000, is_slash=True)
        mock_crash_view.assert_called_with(
            interaction, interaction.user, 1000, 9000, 1.92, 0.0, "normal", False
        )

        # Test Case 3: U = 0.9999 (val = 0.96 / 0.0001 = 9600.0, crash_point should cap at 1000.00)
        mock_get_uniform.return_value = 0.9999
        await cog._crash_game(interaction, 1000, is_slash=True)
        mock_crash_view.assert_called_with(
            interaction, interaction.user, 1000, 9000, 1000.00, 0.0, "normal", False
        )

if __name__ == '__main__':
    unittest.main()
