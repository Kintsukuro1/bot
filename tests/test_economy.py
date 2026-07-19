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
        from src.utils.economy_config import TRANSACTION_TAX
        amount = 1000
        tax = TRANSACTION_TAX["transferencia"]
        impuesto = int(amount * tax)
        net_amount = amount - impuesto

        mock_cursor = MagicMock()
        # Mocking selects & updates responses
        mock_cursor.fetchone.side_effect = [
            (5000,), # Balance remitente
            (4000,), # Nuevo balance remitente después de restar
            (net_amount,)   # Nuevo balance destinatario después de sumar el monto neto
        ]
        mock_db_cursor.return_value.__enter__.return_value = mock_cursor
        
        success, from_bal, to_bal = asyncio.run(
            EconomyService.transfer_balance(111, 222, amount, "Regalo de test")
        )
        
        self.assertTrue(success)
        self.assertEqual(from_bal, 4000)
        self.assertEqual(to_bal, net_amount)

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

class TestBancoCentral(unittest.TestCase):
    @patch('src.db.db_cursor')
    def test_get_bank_reserves(self, mock_db_cursor):
        from src.db import get_bank_reserves
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = (150000,)
        mock_db_cursor.return_value.__enter__.return_value = mock_cursor
        
        reserves = get_bank_reserves()
        self.assertEqual(reserves, 150000)
        mock_cursor.execute.assert_called_with("SELECT Reservas FROM BancoCentral WHERE ID = 1")

    @patch('src.db.db_cursor')
    def test_add_to_bank_reserves(self, mock_db_cursor):
        from src.db import add_to_bank_reserves
        mock_cursor = MagicMock()
        mock_db_cursor.return_value.__enter__.return_value = mock_cursor
        
        add_to_bank_reserves(5000)
        mock_cursor.execute.assert_called_with("UPDATE BancoCentral SET Reservas = Reservas + %s WHERE ID = 1", (5000,))

    @patch('src.db.db_cursor')
    def test_get_user_loan_none(self, mock_db_cursor):
        from src.db import get_user_loan
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = None
        mock_db_cursor.return_value.__enter__.return_value = mock_cursor
        
        loan = get_user_loan(12345)
        self.assertIsNone(loan)

    @patch('src.db.db_cursor')
    def test_get_user_loan_exists(self, mock_db_cursor):
        from src.db import get_user_loan
        import datetime
        mock_cursor = MagicMock()
        venc = datetime.datetime.now()
        mock_cursor.fetchone.return_value = (50000, None, venc, 200000, 1, True)
        mock_db_cursor.return_value.__enter__.return_value = mock_cursor
        
        loan = get_user_loan(12345)
        self.assertIsNotNone(loan)
        self.assertEqual(loan['MontoAdeudado'], 50000)
        self.assertEqual(loan['LimitePrestamo'], 200000)
        self.assertEqual(loan['EnMora'], True)

    @patch('src.db.db_cursor')
    def test_pagar_recompensa_trabajo_no_mora(self, mock_db_cursor):
        from src.db import pagar_recompensa_trabajo
        mock_cursor = MagicMock()
        # EnMora query fetchone -> (False,)
        mock_cursor.fetchone.return_value = (False,)
        mock_db_cursor.return_value.__enter__.return_value = mock_cursor
        
        neto, retencion = pagar_recompensa_trabajo(12345, 1000, "minero")
        self.assertEqual(neto, 1000)
        self.assertEqual(retencion, 0)
        
        # Verify set_balance counterpart (Users table update)
        mock_cursor.execute.assert_any_call(
            "\n                INSERT INTO Users (UserID, Balance) VALUES (%s, %s)\n                ON CONFLICT (UserID) DO UPDATE SET Balance = Users.Balance + EXCLUDED.Balance\n            ", 
            (12345, 1000)
        )

    @patch('src.db.db_cursor')
    def test_pagar_recompensa_trabajo_with_mora(self, mock_db_cursor):
        from src.db import pagar_recompensa_trabajo
        mock_cursor = MagicMock()
        # EnMora query fetchone -> (True,)
        mock_cursor.fetchone.return_value = (True,)
        mock_db_cursor.return_value.__enter__.return_value = mock_cursor
        
        neto, retencion = pagar_recompensa_trabajo(12345, 1000, "minero")
        self.assertEqual(neto, 900)
        self.assertEqual(retencion, 100)
        
        # Verify user gets neto (900)
        mock_cursor.execute.assert_any_call(
            "\n                INSERT INTO Users (UserID, Balance) VALUES (%s, %s)\n                ON CONFLICT (UserID) DO UPDATE SET Balance = Users.Balance + EXCLUDED.Balance\n            ", 
            (12345, 900)
        )
        
        # Verify loan amount is reduced by 100
        mock_cursor.execute.assert_any_call(
            "\n                UPDATE UserLoans\n                SET MontoAdeudado = GREATEST(0, MontoAdeudado - %s)\n                WHERE UserID = %s\n                RETURNING MontoAdeudado\n            ",
            (100, 12345)
        )
        
        # Verify bank reserves receive the retencion (100)
        mock_cursor.execute.assert_any_call(
            "UPDATE BancoCentral SET Reservas = Reservas + %s WHERE ID = 1",
            (100,)
        )

    @patch('src.db.db_cursor')
    def test_pagar_recompensa_trabajo_clears_mora(self, mock_db_cursor):
        from src.db import pagar_recompensa_trabajo
        mock_cursor = MagicMock()
        # side_effect returns (True,) (EnMora) first, and (0,) (MontoAdeudado after retencion) second
        mock_cursor.fetchone.side_effect = [(True,), (0,)]
        mock_db_cursor.return_value.__enter__.return_value = mock_cursor

        neto, retencion = pagar_recompensa_trabajo(12345, 1000, "minero")
        self.assertEqual(neto, 900)
        self.assertEqual(retencion, 100)

        # Verify UserLoans EnMora set to FALSE update was executed
        mock_cursor.execute.assert_any_call(
            "\n                    UPDATE UserLoans\n                    SET FechaPrestamo = NULL,\n                        FechaVencimiento = NULL,\n                        EnMora = FALSE\n                    WHERE UserID = %s\n                ",
            (12345,)
        )

    @patch('src.db.db_cursor')
    def test_get_protection_minutes_no_payment(self, mock_db_cursor):
        from src.utils.robo_progression import get_protection_minutes
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = None
        mock_db_cursor.return_value.__enter__.return_value = mock_cursor

        minutes = get_protection_minutes(12345)
        self.assertEqual(minutes, 3)

    @patch('src.db.db_cursor')
    def test_get_protection_minutes_recent_payment(self, mock_db_cursor):
        from src.utils.robo_progression import get_protection_minutes
        import datetime
        mock_cursor = MagicMock()
        recent = datetime.datetime.now() - datetime.timedelta(hours=2)
        mock_cursor.fetchone.return_value = (recent, 5000)
        mock_db_cursor.return_value.__enter__.return_value = mock_cursor

        minutes = get_protection_minutes(12345)
        self.assertEqual(minutes, 30)

    @patch('src.db.db_cursor')
    def test_get_protection_minutes_old_payment(self, mock_db_cursor):
        from src.utils.robo_progression import get_protection_minutes
        import datetime
        mock_cursor = MagicMock()
        old = datetime.datetime.now() - datetime.timedelta(hours=25)
        mock_cursor.fetchone.return_value = (old, 5000)
        mock_db_cursor.return_value.__enter__.return_value = mock_cursor

        minutes = get_protection_minutes(12345)
        self.assertEqual(minutes, 3)

    @patch('src.db.db_cursor')
    def test_cobrar_cuotas_proteccion_db_sufficient_balance(self, mock_db_cursor):
        from src.db import cobrar_cuotas_proteccion_db
        mock_cursor = MagicMock()
        # Mocking users with balance > 500k: (user_id, balance)
        mock_cursor.fetchall.return_value = [
            (111, 15500000),  # excedente: 15M -> cuota: 10M*0.01 + 5M*0.02 = 200,000
            (222, 600000),    # excedente: 100k -> cuota: 1,000
        ]
        mock_db_cursor.return_value.__enter__.return_value = mock_cursor

        resultados = cobrar_cuotas_proteccion_db()
        self.assertEqual(len(resultados), 2)
        
        # User 111 check
        res1 = next(r for r in resultados if r['user_id'] == 111)
        self.assertEqual(res1['cobrado'], 200000)
        self.assertTrue(res1['exito'])
        self.assertEqual(res1['nuevo_saldo'], 15300000)
        
        # User 222 check
        res2 = next(r for r in resultados if r['user_id'] == 222)
        self.assertEqual(res2['cobrado'], 1000)
        self.assertTrue(res2['exito'])
        self.assertEqual(res2['nuevo_saldo'], 599000)

        # Verify bank reserves update
        mock_cursor.execute.assert_any_call("UPDATE BancoCentral SET Reservas = Reservas + %s WHERE ID = 1", (200000,))
        mock_cursor.execute.assert_any_call("UPDATE BancoCentral SET Reservas = Reservas + %s WHERE ID = 1", (1000,))

class TestPrestige(unittest.TestCase):
    @patch('src.db.db_cursor')
    def test_get_user_prestige_level_default(self, mock_db_cursor):
        from src.db import get_user_prestige_level
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = None
        mock_db_cursor.return_value.__enter__.return_value = mock_cursor

        level = get_user_prestige_level(12345)
        self.assertEqual(level, 0)
        mock_cursor.execute.assert_called_with("SELECT PrestigeLevel FROM UserPrestige WHERE UserID = %s", (12345,))

    @patch('src.db.db_cursor')
    def test_get_user_prestige_level_exists(self, mock_db_cursor):
        from src.db import get_user_prestige_level
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = (3,)
        mock_db_cursor.return_value.__enter__.return_value = mock_cursor

        level = get_user_prestige_level(12345)
        self.assertEqual(level, 3)

    @patch('src.db.db_cursor')
    def test_set_user_prestige_db(self, mock_db_cursor):
        from src.db import set_user_prestige_db
        mock_cursor = MagicMock()
        mock_db_cursor.return_value.__enter__.return_value = mock_cursor

        set_user_prestige_db(12345, 2)
        self.assertTrue(mock_cursor.execute.called)

    @patch('src.utils.prestige_config.get_user_prestige_level')
    def test_get_next_prestige_tier(self, mock_get_prestige_level):
        from src.utils.prestige_config import get_next_prestige_tier
        
        # User prestige is 0
        mock_get_prestige_level.return_value = 0
        tier = get_next_prestige_tier(12345)
        self.assertIsNotNone(tier)
        self.assertEqual(tier["level"], 1)
        self.assertEqual(tier["threshold"], 100000)

        # User prestige is 7 (max)
        mock_get_prestige_level.return_value = 7
        tier = get_next_prestige_tier(12345)
        self.assertIsNone(tier)

    @patch('src.utils.prestige_config.get_next_prestige_tier')
    @patch('src.utils.prestige_config.get_balance')
    def test_can_prestige(self, mock_get_balance, mock_get_next_tier):
        from src.utils.prestige_config import can_prestige
        
        mock_get_next_tier.return_value = {"level": 1, "threshold": 100000, "title": "Prestigio I"}
        
        # Balance is 50,000 (not enough)
        mock_get_balance.return_value = 50000
        ok, tier = can_prestige(12345)
        self.assertFalse(ok)
        self.assertIsNone(tier)

        # Balance is 120,000 (enough)
        mock_get_balance.return_value = 120000
        ok, tier = can_prestige(12345)
        self.assertTrue(ok)
        self.assertEqual(tier["level"], 1)

    @patch('src.utils.prestige_config.registrar_transaccion')
    @patch('src.utils.prestige_config.set_user_prestige_db')
    @patch('src.utils.prestige_config.set_balance')
    @patch('src.utils.prestige_config.get_user_prestige_level')
    @patch('src.utils.prestige_config.get_balance')
    @patch('src.db.db_cursor')
    def test_do_prestige_success(self, mock_db_cursor, mock_get_balance, mock_get_prestige_level, mock_set_balance, mock_set_prestige_db, mock_registrar_tx):
        from src.utils.prestige_config import do_prestige
        mock_cursor = MagicMock()
        mock_db_cursor.return_value.__enter__.return_value = mock_cursor

        # User has level 0 prestige and 150k balance
        mock_get_prestige_level.return_value = 0
        mock_get_balance.return_value = 150000

        success, message = do_prestige(12345)
        self.assertTrue(success)
        self.assertIn("Prestigio I", message)

        # Verify calls
        mock_set_balance.assert_called_with(12345, 10000)
        mock_set_prestige_db.assert_called_with(12345, 1)
        mock_registrar_tx.assert_called_with(12345, -140000, "Prestigio alcanzado: Prestigio I")

    @patch('src.db.db_cursor')
    def test_pagar_bonos_prestigio_mensuales_db(self, mock_db_cursor):
        from src.db import pagar_bonos_prestigio_mensuales_db
        import datetime
        mock_cursor = MagicMock()
        mock_db_cursor.return_value.__enter__.return_value = mock_cursor
        
        recent_date = datetime.datetime.now() - datetime.timedelta(days=10)
        old_date = datetime.datetime.now() - datetime.timedelta(days=35)
        
        mock_cursor.fetchall.return_value = [
            (1001, 3, None),
            (1002, 4, old_date),
            (1003, 3, recent_date)
        ]
        
        resultados = pagar_bonos_prestigio_mensuales_db()
        
        # Should pay user 1001 and 1002
        self.assertEqual(len(resultados), 2)
        
        u1 = next(r for r in resultados if r['user_id'] == 1001)
        self.assertEqual(u1['monto'], 100000)
        self.assertEqual(u1['prestige_level'], 3)
        self.assertIsNone(u1['ultimo_pago_previo'])
        
        u2 = next(r for r in resultados if r['user_id'] == 1002)
        self.assertEqual(u2['monto'], 100000)
        self.assertEqual(u2['prestige_level'], 4)
        self.assertEqual(u2['ultimo_pago_previo'], old_date)
        
        # Check that we didn't pay 1003
        self.assertFalse(any(r['user_id'] == 1003 for r in resultados))
        
        # Verify db select was made
        mock_cursor.execute.assert_any_call("""
            SELECT UserID, PrestigeLevel, UltimoBonoMensual 
            FROM UserPrestige 
            WHERE PrestigeLevel >= 3
        """)


class TestBankInvestments(unittest.TestCase):
    
    @patch('src.db.db_cursor')
    def test_start_investment_success(self, mock_db_cursor):
        from src.services.bank_service import BankService
        mock_cursor = MagicMock()
        # mock returns:
        # 1. SELECT active investment -> None (not active)
        # 2. SELECT UserLoans EnMora -> None (no mora)
        # 3. SELECT Balance -> (5000,)
        # 4. UPDATE Balance -> (4000,)
        mock_cursor.fetchone.side_effect = [
            None,
            None,
            (5000,),
            (4000,)
        ]
        mock_db_cursor.return_value.__enter__.return_value = mock_cursor
        
        success, msg = asyncio.run(BankService.start_investment(12345, 1000))
        self.assertTrue(success)
        self.assertIn("iniciada", msg)
        
        # Verify the insert was called
        mock_cursor.execute.assert_any_call("""
            INSERT INTO UserInvestments (UserID, Monto, FechaInicio, FechaVencimiento, Resuelto)
            VALUES (%s, %s, %s, %s, FALSE)
            ON CONFLICT (UserID) DO UPDATE
            SET Monto = EXCLUDED.Monto,
                FechaInicio = EXCLUDED.FechaInicio,
                FechaVencimiento = EXCLUDED.FechaVencimiento,
                Resuelto = FALSE
        """, (12345, 1000, unittest.mock.ANY, unittest.mock.ANY))

    @patch('src.db.db_cursor')
    def test_start_investment_already_active(self, mock_db_cursor):
        from src.services.bank_service import BankService
        mock_cursor = MagicMock()
        # mock returns:
        # 1. SELECT active investment -> (1000, date, date, False)
        mock_cursor.fetchone.return_value = (1000, None, None, False)
        mock_db_cursor.return_value.__enter__.return_value = mock_cursor
        
        success, msg = asyncio.run(BankService.start_investment(12345, 1000))
        self.assertFalse(success)
        self.assertIn("Ya tienes una inversión activa", msg)

    @patch('src.db.db_cursor')
    def test_start_investment_in_mora(self, mock_db_cursor):
        from src.services.bank_service import BankService
        mock_cursor = MagicMock()
        # mock returns:
        # 1. SELECT active investment -> None
        # 2. SELECT UserLoans EnMora -> (1,) (mora exists)
        mock_cursor.fetchone.side_effect = [None, (1,)]
        mock_db_cursor.return_value.__enter__.return_value = mock_cursor
        
        success, msg = asyncio.run(BankService.start_investment(12345, 1000))
        self.assertFalse(success)
        self.assertIn("mora", msg)

    @patch('src.db.db_cursor')
    def test_start_investment_insufficient_funds(self, mock_db_cursor):
        from src.services.bank_service import BankService
        mock_cursor = MagicMock()
        # mock returns:
        # 1. SELECT active investment -> None
        # 2. SELECT UserLoans EnMora -> None
        # 3. SELECT Balance -> (500,)
        mock_cursor.fetchone.side_effect = [None, None, (500,)]
        mock_db_cursor.return_value.__enter__.return_value = mock_cursor
        
        success, msg = asyncio.run(BankService.start_investment(12345, 1000))
        self.assertFalse(success)
        self.assertIn("No tienes suficiente saldo", msg)

    @patch('src.db.db_cursor')
    def test_get_active_investment_exists(self, mock_db_cursor):
        from src.services.bank_service import BankService
        import datetime
        mock_cursor = MagicMock()
        now = datetime.datetime.now()
        mock_cursor.fetchone.return_value = (1000, now, now, False)
        mock_db_cursor.return_value.__enter__.return_value = mock_cursor
        
        inv = asyncio.run(BankService.get_active_investment(12345))
        self.assertIsNotNone(inv)
        self.assertEqual(inv['Monto'], 1000)
        self.assertEqual(inv['Resuelto'], False)

    @patch('src.db.db_cursor')
    def test_resolve_matured_investments(self, mock_db_cursor):
        from src.services.bank_service import BankService
        import datetime
        mock_cursor = MagicMock()
        # SELECT resolved=FALSE investments list: (user_id, monto, inicio, venc)
        mock_cursor.fetchall.return_value = [
            (111, 1000, datetime.datetime.now(), datetime.datetime.now()),
            (222, 2000, datetime.datetime.now(), datetime.datetime.now())
        ]
        mock_db_cursor.return_value.__enter__.return_value = mock_cursor
        
        res = asyncio.run(BankService.resolve_matured_investments())
        self.assertEqual(res['count'], 2)
        # Verify that it updated the balance for both users
        mock_cursor.execute.assert_any_call("UPDATE UserInvestments SET Resuelto = TRUE WHERE UserID = %s", (111,))
        mock_cursor.execute.assert_any_call("UPDATE UserInvestments SET Resuelto = TRUE WHERE UserID = %s", (222,))

if __name__ == '__main__':
    unittest.main()


