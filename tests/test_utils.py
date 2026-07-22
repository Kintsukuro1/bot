import unittest
from unittest.mock import patch, MagicMock

class TestUtilsPackageImports(unittest.TestCase):
    def test_utils_exports(self):
        import src.utils as utils_pkg
        expected = {
            'combat_config',
            'combat_progression',
            'cooldowns',
            'dynamic_difficulty',
            'economy_config',
            'pets_logic',
            'prestige_config',
            'provably_fair',
            'raid_config',
            'robo_progression',
            'subclass_config',
        }
        self.assertEqual(set(utils_pkg.__all__), expected)

class TestDynamicDifficulty(unittest.TestCase):
    def test_apply_difficulty_to_odds_clamping(self):
        from src.utils.dynamic_difficulty import DynamicDifficulty
        
        # Base 0.5, mod 0.1 -> 0.4
        self.assertAlmostEqual(DynamicDifficulty.apply_difficulty_to_odds(0.5, 0.1), 0.4)
        
        # Lower clamp bound check (min 0.01)
        self.assertEqual(DynamicDifficulty.apply_difficulty_to_odds(0.0, 0.5), 0.01)
        
        # Upper clamp bound check (max 0.99)
        self.assertEqual(DynamicDifficulty.apply_difficulty_to_odds(1.0, -0.5), 0.99)

    def test_generate_explanation_balanced(self):
        from src.utils.dynamic_difficulty import DynamicDifficulty
        exp = DynamicDifficulty._generate_explanation(0.0, [])
        self.assertIn("equilibrada", exp)

    def test_generate_explanation_boosted(self):
        from src.utils.dynamic_difficulty import DynamicDifficulty
        exp = DynamicDifficulty._generate_explanation(0.2, [("high_winrate", 0.12)])
        self.assertIn("aumentada", exp)
        self.assertIn("tasa de victorias", exp)


if __name__ == '__main__':
    unittest.main()
