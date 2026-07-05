import unittest
from unittest.mock import MagicMock, patch
import asyncio
import sys
import os

# Asegurar que el directorio raíz está en el path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.services import UserService, EconomyService

class TestEconomyService(unittest.TestCase):
    
    @patch('src.db.db_cursor')
    def test_ensure_user(self, mock_db_cursor):
        # Configurar mocks de base de datos
        mock_cursor = MagicMock()
        mock_conn = MagicMock()
        mock_db_cursor.return_value.__enter__.return_value = mock_cursor
        
        # Ejecutar método de UserService
        asyncio.run(UserService.ensure_user(12345, "TestUser"))
        
        # Verificar que se intentó seleccionar al usuario primero
        mock_cursor.execute.assert_any_call("SELECT UserName, StartDate FROM Users WHERE UserID = %s", (12345,))

    @patch('src.db.db_cursor')
    def test_get_balance(self, mock_db_cursor):
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = (5000,)
        mock_db_cursor.return_value.__enter__.return_value = mock_cursor
        
        balance = asyncio.run(UserService.get_balance(12345))
        
        mock_cursor.execute.assert_called_with("SELECT Balance FROM Users WHERE UserID = %s", (12345,))
        self.assertEqual(balance, 5000)

    @patch('src.db.db_cursor')
    def test_add_balance(self, mock_db_cursor):
        mock_cursor = MagicMock()
        mock_db_cursor.return_value.__enter__.return_value = mock_cursor
        
        asyncio.run(EconomyService.add_balance(12345, 1000))
        
        # Verificar que se ejecuta el query de inserción/actualización
        self.assertTrue(mock_cursor.execute.called)

    @patch('src.db.db_cursor')
    def test_deduct_balance_success(self, mock_db_cursor):
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = (4000,)
        mock_db_cursor.return_value.__enter__.return_value = mock_cursor
        
        success, new_balance = asyncio.run(EconomyService.deduct_balance(12345, 1000))
        
        self.assertTrue(success)
        self.assertEqual(new_balance, 4000)

    @patch('src.db.db_cursor')
    def test_deduct_balance_insufficient(self, mock_db_cursor):
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = None
        mock_db_cursor.return_value.__enter__.return_value = mock_cursor
        
        success, new_balance = asyncio.run(EconomyService.deduct_balance(12345, 10000))
        
        self.assertFalse(success)
        self.assertEqual(new_balance, 0)

    @patch('src.db.db_cursor')
    def test_transfer_balance_success(self, mock_db_cursor):
        mock_cursor = MagicMock()
        # Mocking selects & updates responses
        mock_cursor.fetchone.side_effect = [
            (5000,), # Balance remitente
            (4000,), # Nuevo balance remitente después de restar
            (1000,)  # Nuevo balance destinatario después de sumar
        ]
        mock_db_cursor.return_value.__enter__.return_value = mock_cursor
        
        success, from_bal, to_bal = asyncio.run(
            EconomyService.transfer_balance(111, 222, 1000, "Regalo de test")
        )
        
        self.assertTrue(success)
        self.assertEqual(from_bal, 4000)
        self.assertEqual(to_bal, 1000)

    @patch('src.db.db_cursor')
    def test_transfer_balance_fail_no_money(self, mock_db_cursor):
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = (500,) # Solo tiene 500 monedas
        mock_db_cursor.return_value.__enter__.return_value = mock_cursor
        
        success, from_bal, to_bal = asyncio.run(
            EconomyService.transfer_balance(111, 222, 1000, "Regalo de test")
        )
        
        self.assertFalse(success)
        self.assertEqual(from_bal, 0)
        self.assertEqual(to_bal, 0)

class TestHackerFeedback(unittest.TestCase):
    def test_calcular_feedback_mastermind(self):
        from src.commands.economy.hacker import _calcular_feedback_mastermind
        
        # Exact match
        self.assertEqual(_calcular_feedback_mastermind("1234", "1234"), "🟩🟩🟩🟩")
        
        # Complete mismatch
        self.assertEqual(_calcular_feedback_mastermind("5678", "1234"), "⬛⬛⬛⬛")
        
        # Permutation (all wrong positions)
        self.assertEqual(_calcular_feedback_mastermind("4321", "1234"), "🟨🟨🟨🟨")
        
        # Partial match with repetitions
        self.assertEqual(_calcular_feedback_mastermind("1122", "1234"), "🟩⬛🟨⬛")
        
        # Another test with duplicates
        self.assertEqual(_calcular_feedback_mastermind("1111", "1213"), "🟩⬛🟩⬛")

class TestCientificoPurity(unittest.TestCase):
    def test_calcular_bono_pureza(self):
        from src.commands.economy.cientifico import _calcular_bono_pureza
        
        # 0%
        mult, tag = _calcular_bono_pureza(0)
        self.assertEqual(mult, 1.5)
        self.assertEqual(tag, "🌟 Síntesis Perfecta")
        
        # 10%
        mult, tag = _calcular_bono_pureza(10)
        self.assertEqual(mult, 1.25)
        self.assertEqual(tag, "💎 Pureza Excelente")
        
        # 40%
        mult, tag = _calcular_bono_pureza(40)
        self.assertEqual(mult, 1.0)
        self.assertEqual(tag, "✅ Pureza Aceptable")
        
        # 75%
        mult, tag = _calcular_bono_pureza(75)
        self.assertEqual(mult, 0.85)
        self.assertEqual(tag, "🧪 Pureza Baja")

if __name__ == '__main__':
    unittest.main()


