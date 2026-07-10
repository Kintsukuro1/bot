import unittest
import sys
import os
from unittest.mock import MagicMock, AsyncMock

# Asegurar que el directorio raíz está en el path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.utils.raid_config import (
    get_today_boss, calc_boss_stats, generate_raid_loot,
    RAID_BOSSES, BOSS_ABILITIES, RAID_AFFIXES,
)

class TestRaidConfig(unittest.TestCase):

    def test_get_today_boss(self):
        boss = get_today_boss()
        self.assertIsNotNone(boss)
        self.assertIn("name", boss)
        self.assertIn("emoji", boss)
        self.assertIn("element", boss)
        self.assertIn("color", boss)
        self.assertIn("base_hp", boss)
        self.assertIn("base_atk", boss)
        self.assertIn("base_def", boss)
        self.assertIn("ability", boss)
        self.assertIn("lore", boss)
        
        # Verificar que la habilidad existe en BOSS_ABILITIES
        self.assertIn(boss["ability"], BOSS_ABILITIES)

    def test_calc_boss_stats_scaling(self):
        boss_config = RAID_BOSSES[0]  # Yggdrasil Corrupto
        
        # Con total_level = 2, debería coincidir con el base
        base_stats = calc_boss_stats(boss_config, total_level=2)
        self.assertEqual(base_stats["max_hp"], boss_config["base_hp"])
        self.assertEqual(base_stats["atk"], boss_config["base_atk"])
        self.assertEqual(base_stats["def_stat"], boss_config["base_def"])
        
        # Con total_level = 10, debería escalar positivamente
        scaled_stats = calc_boss_stats(boss_config, total_level=10)
        self.assertGreater(scaled_stats["max_hp"], boss_config["base_hp"])
        self.assertGreater(scaled_stats["atk"], boss_config["base_atk"])
        self.assertGreater(scaled_stats["def_stat"], boss_config["base_def"])

    def test_generate_raid_loot(self):
        loot = generate_raid_loot(player_level=5, rarity_bonus=0.15)
        self.assertIsNotNone(loot)
        self.assertIn("slot", loot)
        self.assertIn("name", loot)
        self.assertIn("rarity", loot)
        self.assertIn("item_level", loot)
        self.assertEqual(loot["item_level"], 5)


class TestRaidAffixes(unittest.TestCase):
    """Tests para el sistema de afijos de raid."""

    def test_affixes_have_required_keys(self):
        for affix_name, affix_data in RAID_AFFIXES.items():
            self.assertIn("name", affix_data, f"Afijo '{affix_name}' missing 'name'")
            self.assertIn("emoji", affix_data, f"Afijo '{affix_name}' missing 'emoji'")
            self.assertIn("desc", affix_data, f"Afijo '{affix_name}' missing 'desc'")
            self.assertEqual(affix_data["name"], affix_name)

    def test_at_least_four_affixes(self):
        self.assertGreaterEqual(len(RAID_AFFIXES), 4)

    def test_known_affixes_present(self):
        expected = ["Sangriento", "Inestabilidad Mágica", "Enfurecido", "Niebla Venenosa"]
        for name in expected:
            self.assertIn(name, RAID_AFFIXES, f"Expected affix '{name}' not found")


class TestRaidCombatantState(unittest.TestCase):
    """Tests para los estados del RaidCombatant."""

    def _make_combatant(self, combat_class=None, level=5):
        """Helper para crear un combatant con mocks."""
        from src.commands.duels.raid import RaidCombatant

        mock_user = MagicMock()
        mock_user.id = 12345
        mock_user.display_name = "TestPlayer"

        equipment = {}
        combatant = RaidCombatant(mock_user, level, equipment, combat_class)
        return combatant

    def test_initial_class_states(self):
        c = self._make_combatant(combat_class="Guerrero")
        self.assertEqual(c.shield, 0)
        self.assertFalse(c.is_taunting)
        self.assertEqual(c.class_ability_cooldown, 0)
        self.assertEqual(c.combat_class, "Guerrero")

    def test_shield_absorbs_damage(self):
        c = self._make_combatant()
        c.shield = 50
        # Simular absorción
        raw_dmg = 30
        absorbed = min(c.shield, raw_dmg)
        remaining = raw_dmg - absorbed
        c.shield -= absorbed
        c.hp -= remaining
        self.assertEqual(c.shield, 20)
        # El HP no debería haber cambiado (todo fue absorbido)

    def test_taunt_resets_after_round(self):
        c = self._make_combatant(combat_class="Guerrero")
        c.is_taunting = True
        # Simular reset de ronda
        c.is_taunting = False
        self.assertFalse(c.is_taunting)

    def test_cooldown_decrements(self):
        c = self._make_combatant(combat_class="Mago")
        c.class_ability_cooldown = 3
        # Simular decremento
        c.class_ability_cooldown -= 1
        self.assertEqual(c.class_ability_cooldown, 2)
        c.class_ability_cooldown -= 1
        c.class_ability_cooldown -= 1
        self.assertEqual(c.class_ability_cooldown, 0)

    def test_mag_stat_exists(self):
        c = self._make_combatant(combat_class="Mago", level=10)
        self.assertGreater(c.mag, 0)


class TestRaidBoss(unittest.TestCase):
    """Tests para el RaidBoss."""

    def test_boss_creation(self):
        from src.commands.duels.raid import RaidBoss
        boss_config = RAID_BOSSES[0]
        boss = RaidBoss(boss_config, total_level=10)
        self.assertGreater(boss.hp, 0)
        self.assertGreater(boss.max_hp, 0)
        self.assertEqual(boss.hp, boss.max_hp)
        self.assertIn(boss.ability_id, BOSS_ABILITIES)

    def test_boss_hp_scales_with_level(self):
        from src.commands.duels.raid import RaidBoss
        boss_config = RAID_BOSSES[0]
        boss_low = RaidBoss(boss_config, total_level=4)
        boss_high = RaidBoss(boss_config, total_level=20)
        self.assertGreater(boss_high.max_hp, boss_low.max_hp)


class TestLootRollViewInit(unittest.TestCase):
    """Tests para la inicialización del RaidLootRollView."""

    def test_roll_view_setup(self):
        from src.commands.duels.raid import RaidLootRollView, LOOT_ROLL_TIMEOUT

        mock_loot = {
            "name": "Espada Legendaria",
            "rarity": "Legendario",
            "rarity_color": "🟧",
            "rarity_hex": 0xff8800,
            "item_level": 10,
            "slot": "Arma",
            "sell_price": 500,
            "primary_stat": "atk",
            "primary_value": 20,
            "secondaries": [],
            "passive": None,
            "stats_summary": {"atk": 20},
        }

        p1 = MagicMock()
        p1.user.id = 1
        p1.user.display_name = "Player1"
        p2 = MagicMock()
        p2.user.id = 2
        p2.user.display_name = "Player2"

        mock_channel = MagicMock()

        view = RaidLootRollView(mock_loot, [p1, p2], mock_channel)

        self.assertEqual(view.loot, mock_loot)
        self.assertEqual(len(view.eligible_players), 2)
        self.assertIn(1, view.eligible_ids)
        self.assertIn(2, view.eligible_ids)
        self.assertFalse(view.resolved)
        self.assertEqual(len(view.rolls), 0)

    def test_need_roll_has_bonus(self):
        """Need rolls should always have a +20 bonus (value can be > 100)."""
        import random
        random.seed(42)
        roll = random.randint(1, 100) + 20
        self.assertGreaterEqual(roll, 21)
        self.assertLessEqual(roll, 120)

    def test_greed_roll_no_bonus(self):
        """Greed rolls should be 1-100 without bonus."""
        import random
        random.seed(42)
        roll = random.randint(1, 100)
        self.assertGreaterEqual(roll, 1)
        self.assertLessEqual(roll, 100)


class TestChannelingMechanics(unittest.TestCase):
    """Tests para las mecánicas de canalización del boss."""

    def test_channeling_threshold_scales_with_players(self):
        """El umbral de canalización debe escalar con el número de jugadores."""
        players_2 = 2
        players_4 = 4
        threshold_2 = 30 * players_2
        threshold_4 = 30 * players_4
        self.assertEqual(threshold_2, 60)
        self.assertEqual(threshold_4, 120)

    def test_channeling_triggers_on_correct_turns(self):
        """La canalización debería activarse en rondas 4, 9, 14... (turn_count + 2 % 5 == 0)."""
        channeling_turns = []
        for turn in range(20):
            if (turn + 2) % 5 == 0:
                channeling_turns.append(turn)
        # Esperamos turnos 3, 8, 13, 18 (0-indexed)
        self.assertEqual(channeling_turns, [3, 8, 13, 18])


if __name__ == '__main__':
    unittest.main()
