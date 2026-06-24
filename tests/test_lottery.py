import unittest
from unittest.mock import MagicMock, patch
import asyncio
import sys
import os

# Asegurar que el directorio raíz está en el path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.services.lottery_service import LotteryService

class TestLotteryService(unittest.TestCase):

    @patch('src.services.lottery_service.get_user_ticket_count')
    def test_purchase_ticket_invalid_length(self, mock_get_user_ticket_count):
        mock_get_user_ticket_count.return_value = 0
        success, msg, bal = asyncio.run(LotteryService.purchase_ticket(123, [1, 2, 3]))
        self.assertFalse(success)
        self.assertIn("exactamente 4 números", msg)

    @patch('src.services.lottery_service.get_user_ticket_count')
    def test_purchase_ticket_out_of_range(self, mock_get_user_ticket_count):
        mock_get_user_ticket_count.return_value = 0
        success, msg, bal = asyncio.run(LotteryService.purchase_ticket(123, [0, 5, 12, 26]))
        self.assertFalse(success)
        self.assertIn("entre 1 y 25", msg)

    @patch('src.services.lottery_service.get_user_ticket_count')
    def test_purchase_ticket_duplicates(self, mock_get_user_ticket_count):
        mock_get_user_ticket_count.return_value = 0
        success, msg, bal = asyncio.run(LotteryService.purchase_ticket(123, [5, 5, 12, 19]))
        self.assertFalse(success)
        self.assertIn("no se pueden repetir", msg)

    @patch('src.services.lottery_service.get_user_ticket_count')
    def test_purchase_ticket_limit_exceeded(self, mock_get_user_ticket_count):
        mock_get_user_ticket_count.return_value = 5
        success, msg, bal = asyncio.run(LotteryService.purchase_ticket(123, [1, 2, 3, 4]))
        self.assertFalse(success)
        self.assertIn("límite de 5 boletos", msg)

    @patch('src.services.lottery_service.get_user_ticket_count')
    @patch('src.services.lottery_service.comprar_boleto_db')
    def test_purchase_ticket_success(self, mock_comprar_boleto_db, mock_get_user_ticket_count):
        mock_get_user_ticket_count.return_value = 2
        mock_comprar_boleto_db.return_value = (True, 4500)
        
        success, msg, bal = asyncio.run(LotteryService.purchase_ticket(123, [15, 5, 25, 1]))
        
        self.assertTrue(success)
        self.assertIn("comprado con éxito", msg)
        self.assertIn("1, 5, 15, 25", msg) # Verificamos que se ordenaron al imprimir
        self.assertEqual(bal, 4500)
        # Verificar que se ordenaron los números al pasar a la base de datos
        mock_comprar_boleto_db.assert_called_with(123, "1,5,15,25", 500)

    @patch('src.services.lottery_service.get_lottery_state')
    @patch('src.services.lottery_service.get_active_tickets')
    @patch('src.services.lottery_service.process_lottery_draw_db')
    def test_draw_lottery_no_tickets(self, mock_process_db, mock_get_active_tickets, mock_get_lottery_state):
        mock_get_lottery_state.return_value = {'pool': 25000, 'last_draw': None, 'next_draw': None}
        mock_get_active_tickets.return_value = []
        
        results = asyncio.run(LotteryService.draw_lottery())
        
        self.assertTrue(results['no_tickets'])
        self.assertEqual(results['pool'], 25000)
        self.assertEqual(results['new_pool'], 25000)
        # Verificar que se llamó a la base de datos para guardar el estado sin cambios
        self.assertTrue(mock_process_db.called)

    @patch('src.services.lottery_service.get_lottery_state')
    @patch('src.services.lottery_service.get_active_tickets')
    @patch('src.services.lottery_service.process_lottery_draw_db')
    @patch('random.sample')
    def test_draw_lottery_with_winners(self, mock_sample, mock_process_db, mock_get_active_tickets, mock_get_lottery_state):
        # Configurar estado de la lotería y boletos vendidos
        mock_get_lottery_state.return_value = {'pool': 100000, 'last_draw': None, 'next_draw': None}
        
        # Sorteamos [5, 10, 15, 20]
        mock_sample.return_value = [10, 5, 20, 15]
        
        active_tickets = [
            (111, "5,10,15,20"), # 4 aciertos (Jackpot)
            (222, "5,10,15,25"), # 3 aciertos (15% del pozo)
            (333, "5,10,24,25"), # 2 aciertos (2% del pozo)
            (444, "5,23,24,25"), # 1 acierto (200 monedas de reembolso)
            (555, "1,2,3,4"),    # 0 aciertos
        ]
        mock_get_active_tickets.return_value = active_tickets
        
        results = asyncio.run(LotteryService.draw_lottery())
        
        self.assertFalse(results['no_tickets'])
        self.assertEqual(results['winning_numbers'], [5, 10, 15, 20])
        
        # Validar ganadores
        self.assertEqual(results['winners_4'], [111])
        self.assertEqual(results['winners_3'], [222])
        self.assertEqual(results['winners_2'], [333])
        self.assertEqual(results['winners_1'], [444])
        
        # Validar pagos
        payouts = results['payouts']
        self.assertEqual(payouts[111], 100000) # 100% de 100,000
        self.assertEqual(payouts[222], 15000)  # 15% de 100,000
        self.assertEqual(payouts[333], 2000)   # 2% de 100,000
        self.assertEqual(payouts[444], 200)    # 200 reembolso
        
        # Dado que se ganó el jackpot, el pozo se reinicia a 10,000
        self.assertEqual(results['new_pool'], 10000)
        self.assertTrue(mock_process_db.called)

    @patch('src.services.lottery_service.get_lottery_state')
    @patch('src.services.lottery_service.get_active_tickets')
    @patch('src.services.lottery_service.process_lottery_draw_db')
    @patch('random.sample')
    def test_draw_lottery_rollover(self, mock_sample, mock_process_db, mock_get_active_tickets, mock_get_lottery_state):
        mock_get_lottery_state.return_value = {'pool': 100000, 'last_draw': None, 'next_draw': None}
        mock_sample.return_value = [10, 5, 20, 15]
        
        active_tickets = [
            (222, "5,10,15,25"), # 3 aciertos (15% del pozo = 15,000)
            (333, "5,10,24,25"), # 2 aciertos (2% del pozo = 2,000)
            (444, "5,23,24,25"), # 1 acierto (200 monedas = 200)
        ]
        mock_get_active_tickets.return_value = active_tickets
        
        results = asyncio.run(LotteryService.draw_lottery())
        
        self.assertEqual(results['winners_4'], [])
        
        # Payouts = 15000 + 2000 + 200 = 17,200
        # Pozo anterior = 100,000
        # Nuevo pozo = 100,000 - 17,200 = 82,800
        self.assertEqual(results['new_pool'], 82800)
        self.assertTrue(mock_process_db.called)

if __name__ == '__main__':
    unittest.main()
