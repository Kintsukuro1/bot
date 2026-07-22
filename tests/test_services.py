import unittest
from unittest.mock import patch, MagicMock
import asyncio

class TestServicesPackageImports(unittest.TestCase):
    def test_services_exports(self):
        import src.services as services_pkg
        expected = {
            'UserService',
            'EconomyService',
            'CasinoService',
            'CasinoCircuitBreakerError',
            'LeaderboardService',
            'LotteryService',
            'BankService',
            'MarketService',
        }
        self.assertEqual(set(services_pkg.__all__), expected)
        for name in expected:
            self.assertTrue(hasattr(services_pkg, name))

class TestServicesBasicFunctionality(unittest.IsolatedAsyncioTestCase):
    @patch('src.services.user_service.get_balance')
    async def test_user_service_get_balance(self, mock_get_bal):
        from src.services import UserService
        mock_get_bal.return_value = 1500
        bal = await UserService.get_balance(12345)
        self.assertEqual(bal, 1500)

    @patch('src.services.economy_service.add_balance')
    async def test_economy_service_add_balance(self, mock_add):
        from src.services import EconomyService
        await EconomyService.add_balance(12345, 500)
        mock_add.assert_called_once_with(12345, 500)

    def test_market_service_prices_access(self):
        from src.services import MarketService
        prices = MarketService.get_all_prices()
        self.assertIsInstance(prices, dict)

    def test_close_connection_pool_resets_flags(self):
        import src.db as db_module
        db_module._pool_init_failed = True
        db_module._pool_init_error = Exception("Test failure")
        db_module.close_connection_pool()
        self.assertFalse(db_module._pool_init_failed)
        self.assertIsNone(db_module._pool_init_error)


    def test_bot_instance_import(self):
        from src.bot import bot
        self.assertIsNotNone(bot)


if __name__ == '__main__':
    unittest.main()


