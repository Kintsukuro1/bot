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

        # Secret with repeated digits, guess is a permutation with different distribution
        self.assertEqual(_calcular_feedback_mastermind("2211", "1122"), "🟨🟨🟨🟨")

        # Mixed case: some duplicates are 🟩 and others 🟨 in the same guess
        self.assertEqual(_calcular_feedback_mastermind("1212", "1122"), "🟩🟨🟨🟩")

        # Complex duplicate interaction: limited occurrences cause extra guesses to be ⬛
        self.assertEqual(_calcular_feedback_mastermind("2211", "1123"), "🟨⬛🟨🟨")

class TestCientificoPurity(unittest.TestCase):
    def test_calcular_bono_pureza(self):
        from src.commands.economy.cientifico import _calcular_bono_pureza

        # 0% - perfect synthesis
        mult, tag = _calcular_bono_pureza(0)
        self.assertEqual(mult, 1.5)
        self.assertEqual(tag, "🌟 Síntesis Perfecta")

        # Typical values inside each tier
        # 10% - excellent purity
        mult, tag = _calcular_bono_pureza(10)
        self.assertEqual(mult, 1.25)
        self.assertEqual(tag, "💎 Pureza Excelente")

        # 40% - acceptable purity
        mult, tag = _calcular_bono_pureza(40)
        self.assertEqual(mult, 1.0)
        self.assertEqual(tag, "✅ Pureza Aceptable")

        # 75% - low purity
        mult, tag = _calcular_bono_pureza(75)
        self.assertEqual(mult, 0.85)
        self.assertEqual(tag, "🧪 Pureza Baja")

        # Boundary-value tests around purity thresholds

        # Exactly at 20% → still Excellent
        mult, tag = _calcular_bono_pureza(20)
        self.assertEqual(mult, 1.25)
        self.assertEqual(tag, "💎 Pureza Excelente")

        # Just over 20% → moves to Acceptable
        mult, tag = _calcular_bono_pureza(21)
        self.assertEqual(mult, 1.0)
        self.assertEqual(tag, "✅ Pureza Aceptable")

        # Exactly at 50% → still Acceptable
        mult, tag = _calcular_bono_pureza(50)
        self.assertEqual(mult, 1.0)
        self.assertEqual(tag, "✅ Pureza Aceptable")

        # Just over 50% → Low purity
        mult, tag = _calcular_bono_pureza(51)
        self.assertEqual(mult, 0.85)
        self.assertEqual(tag, "🧪 Pureza Baja")

        # High instability (99%) → Low purity
        mult, tag = _calcular_bono_pureza(99)
        self.assertEqual(mult, 0.85)
        self.assertEqual(tag, "🧪 Pureza Baja")

class TestMedicoDiagnosis(unittest.TestCase):
    def test_normalizar_texto(self):
        from src.commands.economy.medico import _normalizar
        
        self.assertEqual(_normalizar("bisturí"), "bisturi")
        self.assertEqual(_normalizar("  Bisturí  "), "bisturi")
        self.assertEqual(_normalizar("anestesia"), "anestesia")
        self.assertEqual(_normalizar("INYECCIÓN"), "inyeccion")

class TestEnergyItemUsage(unittest.TestCase):
    @patch('src.db.db_cursor')
    def test_check_and_register_energy_use_first_time(self, mock_db_cursor):
        from src.db import check_and_register_energy_use
        mock_cursor = MagicMock()
        mock_db_cursor.return_value.__enter__.return_value = mock_cursor
        
        # 1. No BlockedUntil row
        # 2. No UsageCount row (first time)
        mock_cursor.fetchone.side_effect = [None, None]
        
        status, time_remaining = check_and_register_energy_use(123, 3)
        self.assertEqual(status, 'ok')
        self.assertIsNone(time_remaining)
        
        # Verify insert query was executed
        mock_cursor.execute.assert_any_call(
            """
                    INSERT INTO DailyItemUsage (UserID, ItemID, UsageDate, UsageCount) 
                    VALUES (%s, %s, CURRENT_DATE, 1)
                """,
            (123, 3)
        )

    @patch('src.db.db_cursor')
    def test_check_and_register_energy_use_increment(self, mock_db_cursor):
        from src.db import check_and_register_energy_use
        mock_cursor = MagicMock()
        mock_db_cursor.return_value.__enter__.return_value = mock_cursor
        
        # 1. No BlockedUntil row
        # 2. UsageCount row with count 2
        mock_cursor.fetchone.side_effect = [None, (2,)]
        
        status, time_remaining = check_and_register_energy_use(123, 3)
        self.assertEqual(status, 'ok')
        self.assertIsNone(time_remaining)
        
        # Verify update query was executed
        mock_cursor.execute.assert_any_call(
            """
                        UPDATE DailyItemUsage 
                        SET UsageCount = UsageCount + 1 
                        WHERE UserID = %s AND ItemID = %s AND UsageDate = CURRENT_DATE
                    """,
            (123, 3)
        )

    @patch('src.db.db_cursor')
    def test_check_and_register_energy_use_blocked(self, mock_db_cursor):
        from src.db import check_and_register_energy_use
        mock_cursor = MagicMock()
        mock_db_cursor.return_value.__enter__.return_value = mock_cursor
        
        # 1. No BlockedUntil row
        # 2. UsageCount row with count 4 (already used 4 times today)
        mock_cursor.fetchone.side_effect = [None, (4,)]
        
        status, time_remaining = check_and_register_energy_use(123, 3)
        self.assertEqual(status, 'blocked_start')
        self.assertEqual(time_remaining, 86400)

if __name__ == '__main__':
    unittest.main()


