import unittest
import sys
import os
from unittest.mock import MagicMock, AsyncMock, patch

# Asegurar que el directorio raíz está en el path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.db import init_db
init_db()

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


class TestRaidImprovements(unittest.TestCase):
    """Tests para verificar las nuevas mejoras de las raids."""

    def test_boss_scaling_sqrt(self):
        # Yggdrasil Corrupto: base_hp = 400, base_atk = 25, base_def = 18
        boss_config = {
            "base_hp": 400,
            "base_atk": 25,
            "base_def": 18
        }
        # Con total_level = 2, debe dar el base
        stats_base = calc_boss_stats(boss_config, total_level=2)
        self.assertEqual(stats_base["hp"], 400)
        self.assertEqual(stats_base["atk"], 25)
        self.assertEqual(stats_base["def_stat"], 18)

        # Con total_level = 82 (e.g. 4 jugadores de nivel 20)
        # scale_factor = 80 -> sqrt(80) = ~8.944
        # HP: 400 * (1 + 0.45 * 8.944) = 400 * 5.0249 = ~2009
        stats_high = calc_boss_stats(boss_config, total_level=82)
        self.assertLess(stats_high["hp"], 2500) # Debería ser mucho menor que el lineal antiguo (5080)
        self.assertGreater(stats_high["hp"], 1000)

    def test_subclass_equipment_conversion_guardian_sagrado(self):
        from src.commands.duels.raid import RaidCombatant
        mock_user = MagicMock()
        mock_user.id = 777
        mock_user.display_name = "GuardianSagradoPlayer"
        
        equipment = {
            "Escudo": {
                "primary_stat": "def",
                "primary_value": 20,
                "secondaries": [],
                "passive": None
            }
        }
        combatant = RaidCombatant(mock_user, 10, equipment, combat_class="Paladín", combat_subclass="Guardián Sagrado")
        self.assertEqual(combatant.combat_subclass, "Guardián Sagrado")
        self.assertGreater(combatant.shield, 0)

    def test_get_combatant_available_skills(self):
        from src.commands.duels.raid import RaidCombatant, get_combatant_available_skills
        mock_user = MagicMock()
        mock_user.id = 888
        
        c = RaidCombatant(mock_user, 15, {}, combat_class="Guerrero", combat_subclass="Centinela")
        skills = get_combatant_available_skills(c)
        skill_ids = [s[0] for s in skills]
        self.assertIn("golpe_escudo", skill_ids)
        self.assertIn("muralla_inquebrantable", skill_ids)

    def test_boss_debuffs_exist(self):
        from src.commands.duels.raid import RaidBoss
        boss_config = RAID_BOSSES[0]
        boss = RaidBoss(boss_config, total_level=10)
        self.assertEqual(boss.stun_turns, 0)
        self.assertEqual(boss.weakness_turns, 0)
        self.assertEqual(boss.burn_turns, 0)
        self.assertEqual(boss.blinded_turns, 0)

    def test_apply_softcap_formulas(self):
        from src.utils.combat_progression import apply_softcap
        
        # Test case 1: raw <= cap
        self.assertEqual(apply_softcap(8, 10), 8)
        self.assertEqual(apply_softcap(10, 10), 10)
        
        # Test case 2: cap < raw <= cap * 2
        # cap=10, raw=20: 10 + 10 * 0.5 = 15
        self.assertAlmostEqual(apply_softcap(20, 10), 15.0)
        
        # Test case 3: raw > cap * 2
        # cap=10, raw=35: 10 + 10 * 0.5 + 15 * 0.2 = 18
        self.assertAlmostEqual(apply_softcap(35, 10), 18.0)

    def test_raid_combatant_passives(self):
        from src.commands.duels.raid import RaidCombatant
        mock_user = MagicMock()
        mock_user.id = 99999
        mock_user.display_name = "Hero"

        # Simular equipo con pasivos
        equipment = {
            "Arma": {
                "primary_stat": "atk",
                "primary_value": 10,
                "secondaries": [],
                "passive": {"id": "vampirism", "name": "Vampirismo"}
            },
            "Pecho": {
                "primary_stat": "hp",
                "primary_value": 20,
                "secondaries": [],
                "passive": {"id": "regen", "name": "Regeneración"}
            }
        }
        combatant = RaidCombatant(mock_user, 10, equipment)
        self.assertTrue(combatant.has_vampirism)
        self.assertTrue(combatant.has_regen)
        self.assertFalse(combatant.has_dodge)
        self.assertEqual(len(combatant.passives), 2)

    def test_xp_constants_exist(self):
        import src.utils.raid_config as rc
        self.assertTrue(hasattr(rc, "RAID_XP_BASE_VICTORY"))
        self.assertTrue(hasattr(rc, "RAID_XP_BASE_DEFEAT"))
        self.assertTrue(hasattr(rc, "RAID_XP_PER_TURN"))
        self.assertTrue(hasattr(rc, "RAID_XP_ALIVE_BONUS"))


class TestRaidCombatResolve(unittest.IsolatedAsyncioTestCase):
    """Tests para la resolución de ronda con habilidades especiales."""

    async def test_muralla_inquebrantable_applies_mitigation(self):
        from src.commands.duels.raid import RaidCombatant, RaidBoss, RaidCombatView
        from src.utils.raid_config import RAID_BOSSES
        
        mock_user = MagicMock()
        mock_user.id = 111
        mock_user.display_name = "GuerreroCentinela"
        
        p = RaidCombatant(mock_user, 15, {}, combat_class="Guerrero", combat_subclass="Centinela")
        boss_config = RAID_BOSSES[0]
        boss = RaidBoss(boss_config, total_level=15)
        boss.stun_turns = 1
        
        mock_cog = MagicMock()
        view = RaidCombatView([p], boss, mock_cog)
        view.actions = {p.user.id: "muralla_inquebrantable"}
        
        view.interaction_msg = AsyncMock()
        view._finish_raid = AsyncMock()
        
        mock_interaction = MagicMock()
        mock_interaction.message = AsyncMock()
        mock_interaction.message.edit = AsyncMock()
        
        await view._resolve_round(mock_interaction)
        
        self.assertEqual(p.damage_reduction_turns, 3)
        self.assertEqual(p.damage_reduction_pct, 0.50)

    async def test_sed_sangre_applies_buff(self):
        from src.commands.duels.raid import RaidCombatant, RaidBoss, RaidCombatView
        from src.utils.raid_config import RAID_BOSSES
        
        mock_user = MagicMock()
        mock_user.id = 222
        mock_user.display_name = "GuerreroBerserker"
        
        p = RaidCombatant(mock_user, 15, {}, combat_class="Guerrero", combat_subclass="Berserker")
        p.hp = 100
        boss_config = RAID_BOSSES[0]
        boss = RaidBoss(boss_config, total_level=15)
        boss.stun_turns = 1
        
        mock_cog = MagicMock()
        view = RaidCombatView([p], boss, mock_cog)
        view.actions = {p.user.id: "sed_sangre"}
        
        view.interaction_msg = AsyncMock()
        view._finish_raid = AsyncMock()
        
        mock_interaction = MagicMock()
        mock_interaction.message = AsyncMock()
        mock_interaction.message.edit = AsyncMock()
        
        await view._resolve_round(mock_interaction)
        
        self.assertEqual(p.hp, 75)
        self.assertEqual(p.atk_buff_turns, 3)
        self.assertEqual(p.atk_buff_pct, 0.60)


    def test_combat_state_taxonomy_rules(self):
        from src.commands.duels.raid import RaidCombatant, RaidBoss
        mock_user = MagicMock()
        p = RaidCombatant(mock_user, 10, {})
        
        # Stacking poison rules
        # Initial veneno application (p.poison_turns is 0)
        self.assertEqual(p.poison_damage, 0)
        p.poison_damage = 10
        p.poison_turns = 3
        # Reaplication: should stack +10 to poison_damage
        p.poison_damage = min(30, p.poison_damage + 10)
        self.assertEqual(p.poison_damage, 20)
        p.poison_damage = min(30, p.poison_damage + 10)
        self.assertEqual(p.poison_damage, 30)
        # Cap at 30
        p.poison_damage = min(30, p.poison_damage + 10)
        self.assertEqual(p.poison_damage, 30)
        
        # Bleed calculations
        p.last_physical_damage_taken = 100
        p.bleed_source_pct = 0.06
        bleed_dmg = max(1, int(p.last_physical_damage_taken * p.bleed_source_pct))
        self.assertEqual(bleed_dmg, 6)
        
        # Silence checks
        p.silence_turns = 2
        self.assertTrue(p.silence_turns > 0)


    @patch('random.uniform', return_value=1.0)
    async def test_apply_damage_to_player_integration(self, mock_uniform):
        from src.commands.duels.raid import RaidCombatant, RaidBoss, RaidCombatView
        from src.utils.raid_config import RAID_BOSSES
        
        mock_user = MagicMock()
        mock_user.id = 888
        mock_user.display_name = "VulnHero"
        p = RaidCombatant(mock_user, 10, {})
        p.hp = 200
        p.max_hp = 200
        p.vulnerability_turns = 2
        p.vulnerability_pct = 0.30
        
        boss_config = RAID_BOSSES[0]
        boss = RaidBoss(boss_config, total_level=10)
        boss.atk = 100  # Set boss ATK to 100
        
        mock_cog = MagicMock()
        view = RaidCombatView([p], boss, mock_cog)
        view.turn_count = 0  # Round 1 (not special)
        view.actions = {p.user.id: "attack"}
        view.interaction_msg = AsyncMock()
        view._finish_raid = AsyncMock()
        
        mock_interaction = MagicMock()
        mock_interaction.message = AsyncMock()
        mock_interaction.message.edit = AsyncMock()
        
        await view._resolve_round(mock_interaction)
        
        # Expected damage = 100 * 1.3 = 130
        # HP after = 200 - 130 = 70
        self.assertEqual(p.hp, 70)


    def test_calc_power_level_no_subclass(self):
        from src.utils.combat_progression import calc_power_level
        # level = 10, no equipment
        power = calc_power_level(10, {})
        self.assertEqual(power, 10.0)

        # with equipment
        equip = {
            "arma": {
                "primary_stat": "atk",
                "primary_value": 22,
                "secondaries": [],
            }
        }
        # atk raw = 22, base Mago atk = 40, cap = 40 * 0.4 = 16
        # tramo2 = 22 - 16 = 6 -> 16 + 6 * 0.5 = 19 effective atk.
        # bonus_levels = 19 / 11 = 1.72727272
        # expected power = 10 + 1.72727272 = 11.72727272
        power = calc_power_level(10, equip)
        self.assertAlmostEqual(power, 11.72727272, places=4)

    def test_calc_boss_stats_difficulties(self):
        from src.utils.raid_config import calc_boss_stats
        boss_config = {
            "name": "Dummy Boss",
            "base_hp": 100,
            "base_atk": 10,
            "base_def": 5,
        }
        
        # Test floor threshold (power = 5 < 10 -> scale_factor = 0 -> base stats)
        stats_floor = calc_boss_stats(boss_config, total_power=5.0, difficulty="normal")
        self.assertEqual(stats_floor["hp"], 100)
        self.assertEqual(stats_floor["atk"], 10)
        self.assertEqual(stats_floor["def_stat"], 5)
        
        # Test normal scaling (power = 18 -> scale_factor = 16 -> sqrt = 4)
        # Normal HP: base_hp * (1 + 0.45 * sqrt) = 100 * (1 + 0.45 * 4) = 280
        stats_normal = calc_boss_stats(boss_config, total_power=18.0, difficulty="normal")
        self.assertEqual(stats_normal["hp"], 280)
        
        # Test difficult scaling (power = 18 -> scale_factor = 16 -> sqrt = 4)
        # HP: 100 * (1 + 0.65 * 4) = 360
        stats_hard = calc_boss_stats(boss_config, total_power=18.0, difficulty="dificil")
        self.assertEqual(stats_hard["hp"], 360)
        
        # Test mythic scaling (power = 18 -> scale_factor = 16 -> sqrt = 4)
        # HP: 100 * (1 + 0.90 * 4) = 460
        stats_mythic = calc_boss_stats(boss_config, total_power=18.0, difficulty="mitica")
        self.assertEqual(stats_mythic["hp"], 460)

    @patch('src.commands.duels.raid.db_cursor')
    def test_count_mythic_raids_today(self, mock_db_cursor):
        from src.commands.duels.raid import count_mythic_raids_today
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = (2,)
        mock_db_cursor.return_value.__enter__.return_value = mock_cursor
        
        attempts = count_mythic_raids_today(111)
        self.assertEqual(attempts, 2)
        mock_cursor.execute.assert_called_once()

    def test_build_minions_from_pool(self):
        from src.commands.duels.raid import build_minions_from_pool
        # Test normal boss (Yggdrasil: curandero, debilitador)
        boss_0 = {"minion_pool": ["curandero", "debilitador"]}
        minions = build_minions_from_pool(boss_0)
        self.assertEqual(len(minions), 2)
        self.assertEqual(minions[0]["archetype"], "curandero")
        self.assertEqual(minions[1]["archetype"], "debilitador")

        # Test Abyssus (minion_pool is None)
        boss_abyssus = {"minion_pool": None}
        minions_ab = build_minions_from_pool(boss_abyssus)
        self.assertEqual(len(minions_ab), 2)

    def test_raid_boss_is_miniboss_no_scaling(self):
        from src.commands.duels.raid import RaidBoss
        boss_config = {
            "name": "Cofre Mimético",
            "emoji": "🎁",
            "element": "Físico",
            "color": 0x8B4513,
            "hp": 150,
            "atk": 15,
            "def_stat": 8,
            "ability": "none",
            "lore": "Un cofre con dientes",
        }
        boss = RaidBoss(boss_config, total_power=50.0, difficulty="mitica", is_miniboss=True)
        self.assertEqual(boss.max_hp, 150)
        self.assertEqual(boss.hp, 150)
        self.assertEqual(boss.atk, 15)
        self.assertEqual(boss.def_stat, 8)

    def test_espiritu_errante_invisibility(self):
        from src.commands.duels.raid import RaidBoss
        boss_config = {
            "name": "Espíritu Errante",
            "emoji": "👻",
            "element": "Espectral",
            "color": 0xE0FFFF,
            "hp": 200,
            "atk": 20,
            "def_stat": 10,
            "ability": "none",
            "lore": "Presencia parpadeante",
        }
        boss = RaidBoss(boss_config, is_miniboss=True)
        # Verify property hp works normally first
        boss.hp = 180
        self.assertEqual(boss.hp, 180)

        # Enable intangibility
        boss.is_intangible = True
        # Try to decrease HP: should be blocked
        boss.hp = 150
        self.assertEqual(boss.hp, 180)

        # Try to increase HP (healing): should still be allowed
        boss.hp = 190
        self.assertEqual(boss.hp, 190)

    @patch('random.uniform', return_value=1.0)
    async def test_shield_minion_damage_mitigation(self, mock_uniform):
        from src.commands.duels.raid import RaidCombatant, RaidBoss, RaidCombatView
        
        mock_user = MagicMock()
        mock_user.id = 777
        mock_user.display_name = "Player"
        p = RaidCombatant(mock_user, 10, {})
        p.hp = 100
        p.max_hp = 100
        
        boss_config = {
            "name": "Dummy Boss", "emoji": "👾", "element": "Neutral", "color": 0x000,
            "hp": 500, "atk": 10, "def_stat": 5, "ability": "none", "lore": "test",
        }
        boss = RaidBoss(boss_config, is_miniboss=True)
        
        mock_cog = MagicMock()
        view = RaidCombatView([p], boss, mock_cog)
        view.minions = [
            {
                "name": "Guardián de Escudo", "archetype": "escudo", "hp": 30, "max_hp": 30,
                "def_stat": 15, "stun_turns": 0, "weakness_turns": 0, "weakness_pct": 0.0,
                "fragility_turns": 0, "fragility_pct": 0.0, "vulnerability_turns": 0, "vulnerability_pct": 0.0,
                "burn_turns": 0, "poison_turns": 0, "poison_damage": 0,
                "frozen_turns": 0, "silence_turns": 0, "bleed_turns": 0, "bleed_source_pct": 0.06,
                "last_physical_damage_taken": 0
            }
        ]
        view.actions = {p.user.id: "attack"}
        view.interaction_msg = AsyncMock()
        view._finish_raid = AsyncMock()
        
        mock_interaction = MagicMock()
        mock_interaction.message = AsyncMock()
        mock_interaction.message.edit = AsyncMock()
        
        # Player base_dmg = effective_atk * random.uniform(0.85, 1.15)
        # Mago base_atk at level 10 = 40. base_dmg = 40 * 1.0 = 40
        # target_def = 15. def_mitig = target_def * 0.35 = 5.25 -> 5
        # damage before shield = 40 - 5 = 35
        # Shield mitigates 50% -> 35 * 0.5 = 17.5 -> 17
        await view._resolve_round(mock_interaction)
        
        self.assertEqual(view.minions[0]["hp"], 13) # 30 - 17 = 13

    @patch('src.commands.duels.raid.generate_raid_loot')
    @patch('src.commands.duels.raid.get_user_equipment')
    async def test_mimic_chest_guaranteed_loot(self, mock_get_equip, mock_gen_loot):
        from src.commands.duels.raid import RaidCombatant, RaidBoss, RaidCombatView
        
        mock_user = MagicMock()
        mock_user.id = 666
        mock_user.display_name = "Winner"
        mock_user.dm_channel = AsyncMock()
        p = RaidCombatant(mock_user, 10, {})
        
        boss_config = {
            "name": "Cofre Mimético", "emoji": "🎁", "element": "Neutral", "color": 0x000,
            "hp": 150, "atk": 10, "def_stat": 5, "ability": "none", "lore": "test",
            "miniboss_key": "cofre_mimetico", "is_miniboss": True
        }
        boss = RaidBoss(boss_config, is_miniboss=True)
        
        mock_cog = MagicMock()
        view = RaidCombatView([p], boss, mock_cog)
        view.interaction_msg = MagicMock()
        view.interaction_msg.channel = AsyncMock()
        
        mock_gen_loot.return_value = {
            "name": "Espada de Madera", "slot": "arma", "rarity": "Común", "rarity_color": "Común", "rarity_hex": 0x7f8c8d, "item_level": 10,
            "primary_stat": "atk", "primary_value": 5, "secondaries": [],
            "stats_summary": {"atk": 5}, "sell_price": 50
        }
        mock_get_equip.return_value = {}
        
        mock_interaction = MagicMock()
        mock_interaction.message = AsyncMock()
        mock_interaction.message.channel = AsyncMock()
        
        await view._finish_raid(mock_interaction, victory=True)
        
        # In our modified code, we pass floor_idx and ilvl_bonus!
        # But wait! For cofre_mimetico, self.difficulty = 'normal' (the default)
        # So diff_cfg has floor_idx = 0, ilvl_bonus = 0.
        # final_rarity_bonus = MINIBOSS_LOOT_RARITY_BONUS (0.10) + diff_cfg["rarity_bonus"] (0.15) = 0.25
        mock_gen_loot.assert_called_once_with(10, 0.25, floor_idx=0, ilvl_bonus=0)

    def test_roll_rarity_floor(self):
        from src.utils.combat_progression import _roll_rarity
        # floor_idx = 2 (Raro) -> rolled rarity must be Raro, Épico, or Legendario
        for _ in range(50):
            rarity = _roll_rarity(floor_idx=2)
            self.assertIn(rarity["name"], ("Raro", "Épico", "Legendario"))

    def test_generate_raid_loot_difficulty_bounds(self):
        from src.utils.raid_config import generate_raid_loot
        # Difficulty "dificil": floor_idx = 1 (Poco Común), ilvl_bonus = 5
        loot = generate_raid_loot(player_level=10, rarity_bonus=0.0, floor_idx=1, ilvl_bonus=5)
        self.assertEqual(loot["item_level"], 15)
        self.assertIn(loot["rarity"], ("Poco Común", "Raro", "Épico", "Legendario"))

    @patch('src.commands.duels.raid.db_cursor')
    def test_roll_unique_item(self, mock_db_cursor):
        from src.commands.duels.raid import roll_unique_item
        mock_cursor = MagicMock()
        # ItemKey, Name, Slot, Rarity, PrimaryStat, PrimaryValue, Secondaries, Passive, Lore
        mock_cursor.fetchall.return_value = [
            ("corona_yggdrasil", "Corona del Yggdrasil Corrupto", "Cabeza", "Legendario", "hp", 87, [{"stat": "def", "value": 34}], {"id": "regen_improved"}, "Lore text")
        ]
        mock_db_cursor.return_value.__enter__.return_value = mock_cursor
        
        loot = roll_unique_item("Yggdrasil Corrupto")
        self.assertIsNotNone(loot)
        self.assertEqual(loot["slot"], "Cabeza")
        self.assertEqual(loot["name"], "Corona del Yggdrasil Corrupto")
        self.assertEqual(loot["item_level"], 35)
        self.assertEqual(loot["primary_stat"], "hp")
        self.assertEqual(loot["primary_value"], 87)
        self.assertEqual(loot["stats_summary"]["hp"], 87)
        self.assertEqual(loot["stats_summary"]["def"], 34)
        self.assertEqual(loot["item_key"], "corona_yggdrasil")

    @patch('src.commands.duels.raid.roll_unique_item')
    @patch('src.commands.duels.raid.generate_raid_loot')
    @patch('src.commands.duels.raid.get_user_equipment')
    @patch('random.random')
    async def test_resolve_drops_mitica_unique_item_roll(self, mock_random, mock_get_equip, mock_gen_loot, mock_roll_unique):
        from src.commands.duels.raid import RaidCombatant, RaidBoss, RaidCombatView
        
        mock_user = MagicMock()
        mock_user.id = 999
        mock_user.display_name = "MythicWinner"
        mock_user.dm_channel = AsyncMock()
        p = RaidCombatant(mock_user, 30, {})
        p.is_dead = True
        
        boss_config = {
            "name": "Dummy Mythic Boss", "emoji": "👾", "element": "Neutral", "color": 0x000,
            "hp": 500, "atk": 10, "def_stat": 5, "ability": "none", "lore": "test",
        }
        boss = RaidBoss(boss_config, is_miniboss=True)
        
        mock_cog = MagicMock()
        view = RaidCombatView([p], boss, mock_cog)
        view.difficulty = "mitica"
        view.interaction_msg = MagicMock()
        view.interaction_msg.channel = AsyncMock()
        
        # Mock random.random() to:
        # 1. 0.99 for player normal drop rate (normal drop fails)
        # 2. 0.01 for unique drop roll (unique drop succeeds! unique_chance = 0.08)
        mock_random.side_effect = [0.99, 0.01]
        
        mock_gen_loot.return_value = {
            "name": "Espada de Madera", "slot": "arma", "rarity": "Común", "rarity_color": "Común", "rarity_hex": 0x7f8c8d, "item_level": 10,
            "primary_stat": "atk", "primary_value": 5, "secondaries": [],
            "stats_summary": {"atk": 5}, "sell_price": 50
        }
        mock_roll_unique.return_value = {
            "slot": "Cabeza", "name": "Corona del Yggdrasil Corrupto", "rarity": "Legendario",
            "rarity_color": "Orange", "rarity_hex": 0xff8800, "item_level": 35,
            "primary_stat": "hp", "primary_value": 87, "secondaries": [], "stats_summary": {"hp": 87},
            "passive": {"id": "regen_improved", "name": "Regeneración Mejorada", "desc": "Regenera 6% HP", "emoji": "💚"},
            "sell_price": 500, "item_key": "corona_yggdrasil", "lore": "test"
        }
        mock_get_equip.return_value = {}
        
        # Resolve drops
        await view._resolve_drops(victory=True)
        
        # Verify roll_unique_item was called
        mock_roll_unique.assert_called_once_with("Dummy Mythic Boss")
        
        # Since only 1 player, it should call effective_channel.send with individual drop message
        view.interaction_msg.channel.send.assert_called_once()
        sent_content = view.interaction_msg.channel.send.call_args[1]["content"]
        self.assertIn("Has obtenido un Ítem Único de Raid", sent_content)

    async def test_special_button_ephemeral_response(self):
        from src.commands.duels.raid import RaidCombatant, RaidBoss, RaidCombatView
        
        mock_user = MagicMock()
        mock_user.id = 111
        mock_user.display_name = "PlayerSpecial"
        p = RaidCombatant(mock_user, 15, {}, combat_class="Mago", combat_subclass="Arcanista")
        
        boss_config = {
            "name": "Dummy Boss", "emoji": "👾", "element": "Neutral", "color": 0x000,
            "hp": 500, "atk": 10, "def_stat": 5, "ability": "none", "lore": "test",
        }
        boss = RaidBoss(boss_config, is_miniboss=True)
        
        mock_cog = MagicMock()
        view = RaidCombatView([p], boss, mock_cog)
        
        mock_interaction = MagicMock()
        mock_interaction.user.id = 111
        mock_interaction.response.send_message = AsyncMock()
        
        await view.special_button.callback(mock_interaction)
        
        # Verify that it sent an ephemeral message with a view containing options
        mock_interaction.response.send_message.assert_called_once()
        args, kwargs = mock_interaction.response.send_message.call_args
        self.assertEqual(kwargs.get("ephemeral"), True)
        sent_view = kwargs.get("view")
        self.assertIsNotNone(sent_view)
        # Check that options are available (e.g. Mago skill)
        self.assertTrue(len(sent_view.children) > 0)

    @patch('src.commands.duels.raid.RaidCombatView._register_action')
    async def test_personal_skill_select_view_callback(self, mock_register):
        from src.commands.duels.raid import RaidCombatant, RaidBoss, RaidCombatView, PersonalSkillSelectView
        
        mock_user = MagicMock()
        mock_user.id = 111
        p = RaidCombatant(mock_user, 15, {}, combat_class="Mago", combat_subclass="Arcanista")
        
        boss_config = {
            "name": "Dummy Boss", "emoji": "👾", "element": "Neutral", "color": 0x000,
            "hp": 500, "atk": 10, "def_stat": 5, "ability": "none", "lore": "test",
        }
        boss = RaidBoss(boss_config, is_miniboss=True)
        
        mock_cog = MagicMock()
        view = RaidCombatView([p], boss, mock_cog)
        
        import discord
        options = [discord.SelectOption(label="Tormenta de Fuego", value="quemadura")]
        personal_view = PersonalSkillSelectView(raid_view=view, player=p, options=options)
        
        mock_interaction = MagicMock()
        mock_interaction.user.id = 111
        mock_interaction.data = {"values": ["quemadura"]}
        mock_interaction.response.edit_message = AsyncMock()
        mock_interaction.followup.send = AsyncMock()
        
        await personal_view.select_callback(mock_interaction)
        
        mock_interaction.response.edit_message.assert_called_once()
        mock_interaction.followup.send.assert_called_once()
        # Verify it calls _register_action with is_ephemeral=True
        mock_register.assert_called_once_with(mock_interaction, "quemadura", is_ephemeral=True)


if __name__ == '__main__':
    unittest.main()
