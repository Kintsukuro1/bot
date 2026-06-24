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

if __name__ == '__main__':
    unittest.main()
