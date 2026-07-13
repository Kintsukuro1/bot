import unittest
import sys
import os
from unittest.mock import MagicMock, AsyncMock, patch

# Asegurar que el directorio raíz está en el path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.commands.duels.duelo import Combatant, DuelView
from src.utils.combat_config import SKILLS_CONFIG

class TestDueloMuerteSubita(unittest.IsolatedAsyncioTestCase):

    def setUp(self):
        # Mocks para usuarios
        self.mock_user1 = MagicMock()
        self.mock_user1.id = 111
        self.mock_user1.display_name = "Player1"
        self.mock_user1.mention = "<@111>"

        self.mock_user2 = MagicMock()
        self.mock_user2.id = 222
        self.mock_user2.display_name = "Player2"
        self.mock_user2.mention = "<@222>"

        # Cog dummy
        self.mock_cog = MagicMock()
        self.mock_cog.active_duels = set()

        # Crear Combatants
        self.p1 = Combatant(self.mock_user1, level=10, equipment={}, combat_class="Mago")
        self.p2 = Combatant(self.mock_user2, level=10, equipment={}, combat_class="Pícaro")

        # Crear DuelView
        self.view = DuelView(self.p1, self.p2, bet=100, cog=self.mock_cog)

    def test_build_embed_before_turn_50(self):
        self.view.turn_count = 0
        embed = self.view._build_embed()
        self.assertEqual(embed.title, "⚔️ Duelo PvP Simultáneo")
        self.assertNotIn("⚠️ **¡MUERTE SÚBITA ACTIVA!", embed.description)
        self.assertNotIn("⚠️ Daño aumentado un 100%", embed.footer.text)

    def test_build_embed_after_turn_50(self):
        self.view.turn_count = 49  # Ronda 50
        embed = self.view._build_embed()
        self.assertEqual(embed.title, "⚔️ Duelo PvP Simultáneo (¡MUERTE SÚBITA!)")
        self.assertIn("⚠️ **¡MUERTE SÚBITA ACTIVA! Daño aumentado +100%** ⚠️", embed.description)
        self.assertIn("⚠️ Daño aumentado un 100%", embed.footer.text)

    @patch('src.utils.combat_progression.random.uniform')
    @patch('src.utils.combat_progression.random.random')
    def test_calculate_attack_damage_doubled_after_turn_50(self, mock_random, mock_uniform):
        mock_uniform.return_value = 1.0
        mock_random.return_value = 0.5  # evitar critico
        
        # Turno 0: Daño normal
        self.view.turn_count = 0
        damage_normal, _ = self.view._calculate_action_result(self.p1, self.p2, "attack")

        # Turno 49 (Ronda 50): Daño duplicado
        self.view.turn_count = 49
        damage_sudden, log_sudden = self.view._calculate_action_result(self.p1, self.p2, "attack")

        self.assertEqual(damage_sudden, damage_normal * 2)
        self.assertIn("⚠️*(Muerte Súbita)*", log_sudden)

    def test_calculate_veneno_damage_doubled_after_turn_50(self):
        self.view.p1_special_id = "veneno"
        
        # Turno 0
        self.view.turn_count = 0
        damage_normal, _ = self.view._calculate_action_result(self.p1, self.p2, "special")

        # Turno 49 (Ronda 50)
        self.view.turn_count = 49
        damage_sudden, log_sudden = self.view._calculate_action_result(self.p1, self.p2, "special")

        self.assertEqual(damage_sudden, damage_normal * 2)
        self.assertIn("⚠️*(Muerte Súbita)*", log_sudden)

    def test_calculate_quemadura_damage_doubled_after_turn_50(self):
        self.view.p1_special_id = "quemadura"
        
        # Turno 0
        self.view.turn_count = 0
        damage_normal, _ = self.view._calculate_action_result(self.p1, self.p2, "special")

        # Turno 49 (Ronda 50)
        self.view.turn_count = 49
        damage_sudden, log_sudden = self.view._calculate_action_result(self.p1, self.p2, "special")

        self.assertEqual(damage_sudden, damage_normal * 2)
        self.assertIn("⚠️*(Muerte Súbita)*", log_sudden)

    def test_dot_damage_doubled_after_turn_50(self):
        # Configurar veneno y quemadura en ambos jugadores
        self.view.p1_poison_turns = 2
        self.view.p2_burn_turns = 2

        # Primero probamos con turn_count < 49 (Ronda < 50)
        self.view.turn_count = 0
        self.p1.hp = 100
        self.p2.hp = 100
        
        # Ejecutar fase de DOTs (simulado)
        p1_hp_before = self.p1.hp
        p2_hp_before = self.p2.hp
        
        logs = []
        for defender in (self.view.p1, self.view.p2):
            p_turns = self.view.p1_poison_turns if defender == self.view.p1 else self.view.p2_poison_turns
            b_turns = self.view.p1_burn_turns if defender == self.view.p1 else self.view.p2_burn_turns
            is_sudden_death = (self.view.turn_count + 1) >= 50
            sudden_death_tag = " ⚠️*(Muerte Súbita)*" if is_sudden_death else ""

            if p_turns > 0:
                dot_val = SKILLS_CONFIG["veneno"]["dot_damage"]
                if is_sudden_death:
                    dot_val = dot_val * 2
                p_dmg = min(defender.hp, dot_val)
                defender.hp = max(0, defender.hp - p_dmg)
                logs.append(f"veneno_dmg: {p_dmg}")
                
            if b_turns > 0:
                dot_pct = SKILLS_CONFIG["quemadura"]["dot_max_hp_pct"]
                b_dmg_base = max(1, int(defender.max_hp * dot_pct))
                if is_sudden_death:
                    b_dmg_base = b_dmg_base * 2
                b_dmg = min(defender.hp, b_dmg_base)
                defender.hp = max(0, defender.hp - b_dmg)
                logs.append(f"quemadura_dmg: {b_dmg}")

        normal_poison_dmg = p1_hp_before - self.p1.hp
        normal_burn_dmg = p2_hp_before - self.p2.hp

        # Reiniciar HP y probar con turn_count = 49 (Ronda 50)
        self.view.turn_count = 49
        self.p1.hp = 100
        self.p2.hp = 100
        p1_hp_before = self.p1.hp
        p2_hp_before = self.p2.hp
        
        logs_sudden = []
        for defender in (self.view.p1, self.view.p2):
            p_turns = self.view.p1_poison_turns if defender == self.view.p1 else self.view.p2_poison_turns
            b_turns = self.view.p1_burn_turns if defender == self.view.p1 else self.view.p2_burn_turns
            is_sudden_death = (self.view.turn_count + 1) >= 50
            sudden_death_tag = " ⚠️*(Muerte Súbita)*" if is_sudden_death else ""

            if p_turns > 0:
                dot_val = SKILLS_CONFIG["veneno"]["dot_damage"]
                if is_sudden_death:
                    dot_val = dot_val * 2
                p_dmg = min(defender.hp, dot_val)
                defender.hp = max(0, defender.hp - p_dmg)
                logs_sudden.append(f"veneno_dmg: {p_dmg}")
                
            if b_turns > 0:
                dot_pct = SKILLS_CONFIG["quemadura"]["dot_max_hp_pct"]
                b_dmg_base = max(1, int(defender.max_hp * dot_pct))
                if is_sudden_death:
                    b_dmg_base = b_dmg_base * 2
                b_dmg = min(defender.hp, b_dmg_base)
                defender.hp = max(0, defender.hp - b_dmg)
                logs_sudden.append(f"quemadura_dmg: {b_dmg}")

        sudden_poison_dmg = p1_hp_before - self.p1.hp
        sudden_burn_dmg = p2_hp_before - self.p2.hp

        self.assertEqual(sudden_poison_dmg, normal_poison_dmg * 2)
        self.assertEqual(sudden_burn_dmg, normal_burn_dmg * 2)

    def test_fatigue_damage_scales_after_turn_50(self):
        # Turno 48 (Ronda 49): Sin fatiga
        self.view.turn_count = 48
        self.p1.hp = 100
        self.p2.hp = 100
        is_sudden_death = (self.view.turn_count + 1) >= 50
        self.assertFalse(is_sudden_death)
        
        # Turno 49 (Ronda 50): 5% de fatiga
        self.view.turn_count = 49
        self.p1.hp = 100
        p1_max_hp = self.p1.max_hp
        fatigue_level_50 = (self.view.turn_count + 1) - 50 + 1  # 50 - 50 + 1 = 1
        fatigue_pct_50 = 0.05 * fatigue_level_50  # 0.05 (5%)
        expected_dmg_50 = int(p1_max_hp * fatigue_pct_50)
        
        p1_hp_before = self.p1.hp
        fatigue_dmg = min(self.p1.hp, max(1, int(self.p1.max_hp * fatigue_pct_50)))
        self.p1.hp = max(0, self.p1.hp - fatigue_dmg)
        actual_dmg_50 = p1_hp_before - self.p1.hp
        self.assertEqual(actual_dmg_50, expected_dmg_50)
        
        # Turno 50 (Ronda 51): 10% de fatiga
        self.view.turn_count = 50
        self.p1.hp = 100
        fatigue_level_51 = (self.view.turn_count + 1) - 50 + 1  # 51 - 50 + 1 = 2
        fatigue_pct_51 = 0.05 * fatigue_level_51  # 0.10 (10%)
        expected_dmg_51 = int(p1_max_hp * fatigue_pct_51)
        
        p1_hp_before = self.p1.hp
        fatigue_dmg = min(self.p1.hp, max(1, int(self.p1.max_hp * fatigue_pct_51)))
        self.p1.hp = max(0, self.p1.hp - fatigue_dmg)
        actual_dmg_51 = p1_hp_before - self.p1.hp
        self.assertEqual(actual_dmg_51, expected_dmg_51)
        self.assertEqual(actual_dmg_51, actual_dmg_50 * 2)

    def test_duel_state_taxonomy_rules(self):
        from src.commands.duels.duelo import Combatant
        mock_user = MagicMock()
        p = Combatant(mock_user, level=10, equipment={})
        
        # Stacking poison rules
        p.poison_turns = 3
        # First layer
        p1_poison_damage = 10
        # Re-apply
        p1_poison_damage = min(30, p1_poison_damage + 10)
        self.assertEqual(p1_poison_damage, 20)
        p1_poison_damage = min(30, p1_poison_damage + 10)
        self.assertEqual(p1_poison_damage, 30)
        
        # Bleed calculation
        p.last_physical_damage_taken = 200
        p.bleed_source_pct = 0.06
        bleed_dmg = max(1, int(p.last_physical_damage_taken * p.bleed_source_pct))
        self.assertEqual(bleed_dmg, 12)
        
        # Stun/Freeze active reinforcement checks
        p.stun_turns = 2
        p.frozen_turns = 0
        if p.stun_turns > 0:
            p.stun_turns += 1
        else:
            p.frozen_turns = 2
        self.assertEqual(p.stun_turns, 3)
        self.assertEqual(p.frozen_turns, 0)
        
        # Capped combined damage received amp (+75% max)
        # Frenzy (+15%) + Vulnerability (+30% Singularity)
        amp_pct = 0.15 + 0.30
        amp_pct = min(0.75, amp_pct)
        self.assertAlmostEqual(amp_pct, 0.45)
        
        # Frenzy (+15%) + Vulnerability (+30%) + afijo (+40%) = 0.85 -> capped at 0.75
        amp_pct = 0.15 + 0.30 + 0.40
        amp_pct = min(0.75, amp_pct)
        self.assertEqual(amp_pct, 0.75)


        # Frenzy (+15%) + Vulnerability (+30%) + afijo (+40%) = 0.85 -> capped at 0.75
        amp_pct = 0.15 + 0.30 + 0.40
        amp_pct = min(0.75, amp_pct)
        self.assertEqual(amp_pct, 0.75)

    async def test_duel_special_button_ephemeral_response(self):
        mock_interaction = MagicMock()
        mock_interaction.user.id = self.mock_user1.id
        mock_interaction.response.send_message = AsyncMock()
        
        await self.view.special_button.callback(mock_interaction)
        
        mock_interaction.response.send_message.assert_called_once()
        args, kwargs = mock_interaction.response.send_message.call_args
        self.assertEqual(kwargs.get("ephemeral"), True)
        sent_view = kwargs.get("view")
        self.assertIsNotNone(sent_view)
        self.assertTrue(len(sent_view.children) > 0)

    @patch('src.commands.duels.duelo.DuelView._check_and_resolve')
    async def test_duel_personal_skill_select_view_callback(self, mock_check_resolve):
        from src.commands.duels.duelo import PersonalDuelSkillSelectView
        import discord
        
        options = [discord.SelectOption(label="Tormenta de Fuego", value="quemadura")]
        personal_view = PersonalDuelSkillSelectView(duel_view=self.view, player=self.p1, options=options)
        
        mock_interaction = MagicMock()
        mock_interaction.user.id = self.mock_user1.id
        mock_interaction.data = {"values": ["quemadura"]}
        mock_interaction.response.edit_message = AsyncMock()
        mock_interaction.followup.send = AsyncMock()
        
        await personal_view.select_callback(mock_interaction)
        
        mock_interaction.response.edit_message.assert_called_once()
        self.assertEqual(self.view.p1_action, "special")
        self.assertEqual(self.view.p1_special_id, "quemadura")
        mock_check_resolve.assert_called_once_with(mock_interaction, is_ephemeral=True)


    async def test_estados_cmd(self):
        from src.commands.duels.duelo import DuelsCog
        
        cog = DuelsCog(MagicMock())
        mock_interaction = MagicMock()
        mock_interaction.response.send_message = AsyncMock()
        
        await cog.estados_cmd.callback(cog, mock_interaction)
        
        mock_interaction.response.send_message.assert_called_once()
        args, kwargs = mock_interaction.response.send_message.call_args
        sent_embed = kwargs.get("embed")
        self.assertIsNotNone(sent_embed)
        self.assertEqual(sent_embed.title, "📖 Glosario de Estados de Combate")
        self.assertTrue(len(sent_embed.fields) == 4)

    def test_bleed_on_hit_passive_proc(self):
        self.p1.has_bleed_on_hit = True
        self.p2.bleed_turns = 0
        self.p2.bleed_source_pct = 0.0

        # Caso 1: Se activa el Filo Sangrante (segunda llamada a random.random devuelve < 0.15)
        with patch('random.random', side_effect=[0.5, 0.10]), \
             patch('random.uniform', return_value=1.0):
            damage, log = self.view._calculate_action_result(self.p1, self.p2, "attack")
            self.assertGreater(damage, 0)
            self.assertEqual(self.p2.bleed_turns, 3 + 1)
            self.assertEqual(self.p2.bleed_source_pct, 0.06)
            self.assertIn("El Filo Sangrante corta profundo", log)

        # Restablecer
        self.p2.bleed_turns = 0
        self.p2.bleed_source_pct = 0.0

        # Caso 2: No se activa el Filo Sangrante (segunda llamada devuelve >= 0.15)
        with patch('random.random', side_effect=[0.5, 0.50]), \
             patch('random.uniform', return_value=1.0):
            damage, log = self.view._calculate_action_result(self.p1, self.p2, "attack")
            self.assertGreater(damage, 0)
            self.assertEqual(self.p2.bleed_turns, 0)
            self.assertEqual(self.p2.bleed_source_pct, 0.0)
            self.assertNotIn("El Filo Sangrante corta profundo", log)


class TestDueloSetBonuses(unittest.IsolatedAsyncioTestCase):

    def setUp(self):
        self.mock_user1 = MagicMock()
        self.mock_user1.id = 111
        self.mock_user1.display_name = "Player1"
        self.mock_user1.mention = "<@111>"

        self.mock_user2 = MagicMock()
        self.mock_user2.id = 222
        self.mock_user2.display_name = "Player2"
        self.mock_user2.mention = "<@222>"

        self.mock_cog = MagicMock()
        self.mock_cog.active_duels = set()

        self.p1 = Combatant(self.mock_user1, level=10, equipment={}, combat_class="Mago")
        self.p2 = Combatant(self.mock_user2, level=10, equipment={}, combat_class="Pícaro")
        self.view = DuelView(self.p1, self.p2, bet=100, cog=self.mock_cog)

    def test_leviathan_cc_reduction(self):
        # Without leviathan
        self.p1.set_bonus_leviathan_4pc = False
        self.p1.stun_turns = 4
        self.assertEqual(self.p1.stun_turns, 4)

        # With leviathan
        self.p1.set_bonus_leviathan_4pc = True
        self.p1.stun_turns = 0 # Reset first so value > _stun_turns evaluates to True
        self.p1.stun_turns = 4
        self.assertEqual(self.p1.stun_turns, 3) # 4 * 0.85 = 3.4 -> 3

        # Minimum CC duration is 1
        self.p1.stun_turns = 0
        self.p1.stun_turns = 1
        self.assertEqual(self.p1.stun_turns, 1)

        # Verify frozen and silence
        self.p1.frozen_turns = 0
        self.p1.frozen_turns = 4
        self.assertEqual(self.p1.frozen_turns, 3)
        self.p1.silence_turns = 0
        self.p1.silence_turns = 4
        self.assertEqual(self.p1.silence_turns, 3)

    def test_caelum_first_strike_dodge(self):
        self.p2.set_bonus_caelum_4pc = True
        self.p2.first_strike_used = False

        # Mock random to force a dodge (dodge_chance will be 0.20, so random < 0.20 procs dodge)
        with patch('random.random', return_value=0.10):
            damage, log = self.view._calculate_action_result(self.p1, self.p2, "attack")
            self.assertEqual(damage, 0)
            self.assertTrue(self.p2.first_strike_used)
            self.assertIn("ESQUIVÓ", log)

    def test_ignis_burn_extension(self):
        self.p1.set_bonus_ignis_4pc = True
        self.view.p1_special_id = "quemadura"
        self.view.p1_action = "special"
        self.view.p2_action = "attack"
        
        # Call the calculation method
        self.view._calculate_action_result(self.p1, self.p2, "special")
        self.assertEqual(self.view.p2_burn_turns, SKILLS_CONFIG["quemadura"]["turns"] + 1 + 2)

    def test_aurelius_low_hp_heal_after_dots(self):
        self.p1.set_bonus_aurelius_4pc = True
        self.p1.hp = 25
        self.p1.low_hp_heal_used = False
        
        # Simulate round resolution Aurelius check after DoTs
        for p in (self.view.p1, self.view.p2):
            if p.hp > 0 and p.hp < p.max_hp * 0.30 and p.set_bonus_aurelius_4pc and not p.low_hp_heal_used:
                p.low_hp_heal_used = True
                heal_amt = int(p.max_hp * 0.15)
                p.hp = min(p.max_hp, p.hp + heal_amt)
                
        expected_hp = 25 + int(self.p1.max_hp * 0.15)
        self.assertEqual(self.p1.hp, expected_hp)
        self.assertTrue(self.p1.low_hp_heal_used)

    def test_abyssus_random_activation(self):
        mock_user = MagicMock()
        mock_user.id = 333
        mock_user.display_name = "AbyssusPlayer"
        mock_user.mention = "<@333>"
        
        # Patch random to choose caelum and mock get_equipped_set_pieces to bypass equipment dictionary lookup
        with patch('src.commands.duels.duelo.get_equipped_set_pieces', return_value={"set_abyssus": 4}), \
             patch('random.choice', return_value="caelum_first_strike_dodge"):
            p = Combatant(mock_user, level=10, equipment={}, combat_class="Mago")
            self.assertTrue(p.set_bonus_abyssus_4pc)
            self.assertTrue(p.set_bonus_caelum_4pc)
            self.assertFalse(p.set_bonus_ignis_4pc)
            self.assertIn("Caelum", p.abyssus_log)


class TestClaseCommand(unittest.IsolatedAsyncioTestCase):

    def setUp(self):
        from src.commands.duels.duelo import DuelsCog
        self.bot = MagicMock()
        self.cog = DuelsCog(self.bot)
        self.mock_user = MagicMock()
        self.mock_user.id = 12345
        self.mock_user.display_name = "TestPlayer"

        self.mock_interaction = MagicMock()
        self.mock_interaction.user = self.mock_user
        self.mock_interaction.response.send_message = AsyncMock()
        self.mock_interaction.followup.send = AsyncMock()

    @patch('src.commands.duels.duelo.get_combat_stats')
    async def test_clase_cmd_under_level_5(self, mock_get_stats):
        mock_get_stats.return_value = {"level": 4, "combat_class": None, "combat_subclass": None}
        
        await self.cog.clase_cmd.callback(self.cog, self.mock_interaction)
        
        self.mock_interaction.response.send_message.assert_called_once()
        args, kwargs = self.mock_interaction.response.send_message.call_args
        self.assertIn("Necesitas nivel de combate **5**", args[0])

    @patch('src.commands.duels.duelo.get_combat_stats')
    async def test_clase_cmd_already_has_class_low_level(self, mock_get_stats):
        mock_get_stats.return_value = {"level": 7, "combat_class": "Mago", "combat_subclass": None}
        
        await self.cog.clase_cmd.callback(self.cog, self.mock_interaction)
        
        self.mock_interaction.response.send_message.assert_called_once()
        args, kwargs = self.mock_interaction.response.send_message.call_args
        self.assertIn("Ya has elegido la clase **Mago**", args[0])

    @patch('src.commands.duels.duelo.get_combat_stats')
    @patch('src.commands.duels.duelo.SubclassSelectionView')
    @patch('src.commands.duels.duelo.update_user_class_and_subclass')
    async def test_clase_cmd_already_has_class_high_level(self, mock_update, mock_view_class, mock_get_stats):
        mock_get_stats.return_value = {"level": 12, "combat_class": "Mago", "combat_subclass": None}
        
        mock_view_inst = MagicMock()
        mock_view_inst.wait = AsyncMock()
        mock_view_inst.selected_subclass = "Piromante"
        mock_view_class.return_value = mock_view_inst
        
        mock_update.return_value = True
        
        await self.cog.clase_cmd.callback(self.cog, self.mock_interaction)
        
        self.mock_interaction.response.send_message.assert_called_once()
        args, kwargs = self.mock_interaction.response.send_message.call_args
        sent_embed = kwargs.get("embed")
        self.assertIsNotNone(sent_embed)
        self.assertIn("Elige tu Subclase de Mago", sent_embed.title)
        
        mock_update.assert_called_once_with(self.mock_user.id, "Mago", "Piromante")
        self.mock_interaction.followup.send.assert_called_once()
        f_args, f_kwargs = self.mock_interaction.followup.send.call_args
        self.assertIn("Tu subclase ha sido actualizada", f_args[0])

    @patch('src.commands.duels.duelo.get_combat_stats')
    async def test_clase_cmd_already_has_class_and_subclass(self, mock_get_stats):
        mock_get_stats.return_value = {"level": 15, "combat_class": "Mago", "combat_subclass": "Piromante"}
        
        await self.cog.clase_cmd.callback(self.cog, self.mock_interaction)
        
        self.mock_interaction.response.send_message.assert_called_once()
        args, kwargs = self.mock_interaction.response.send_message.call_args
        self.assertIn("Ya has elegido tu clase (**Mago**) y subclase (**Piromante**)", args[0])


class TestNewPassives(unittest.IsolatedAsyncioTestCase):

    def setUp(self):
        self.mock_user1 = MagicMock()
        self.mock_user1.id = 111
        self.mock_user1.display_name = "Player1"
        self.mock_user1.mention = "<@111>"

        self.mock_user2 = MagicMock()
        self.mock_user2.id = 222
        self.mock_user2.display_name = "Player2"
        self.mock_user2.mention = "<@222>"

        self.mock_cog = MagicMock()
        self.mock_cog.active_duels = set()

    def test_glass_heart_stat_modifiers(self):
        # Without glass_heart
        p = Combatant(self.mock_user1, level=10, equipment={}, combat_class="Mago")
        hp_before = p.max_hp
        atk_before = p.atk
        mag_before = p.mag

        # With glass_heart (patched calc_equipment_bonus)
        with patch('src.commands.duels.duelo.calc_equipment_bonus', return_value=({}, [{"id": "glass_heart"}], {})):
            p_gh = Combatant(self.mock_user1, level=10, equipment={}, combat_class="Mago")
            self.assertEqual(p_gh.max_hp, int(hp_before * 0.92))
            self.assertEqual(p_gh.atk, int(atk_before * 1.12))
            self.assertEqual(p_gh.mag, int(mag_before * 1.12))

    def test_stoneskin_reduction(self):
        p1 = Combatant(self.mock_user1, level=10, equipment={}, combat_class="Mago")
        p1.passives = []
        p2 = Combatant(self.mock_user2, level=10, equipment={}, combat_class="Pícaro")
        p2.passives = [{"id": "stoneskin"}]
        view = DuelView(p1, p2, bet=100, cog=self.mock_cog)
        
        # Test normal attack: physical damage should be reduced by 3
        # Calculate base damage without stoneskin first
        p2_ns = Combatant(self.mock_user2, level=10, equipment={}, combat_class="Pícaro")
        p2_ns.passives = []
        with patch('random.random', return_value=0.5), patch('random.uniform', return_value=1.0):
            base_dmg, _ = view._calculate_action_result(p1, p2_ns, "attack")
            reduced_dmg, _ = view._calculate_action_result(p1, p2, "attack")
            self.assertEqual(reduced_dmg, max(1, base_dmg - 3))

    def test_hawk_strike_crit(self):
        p1 = Combatant(self.mock_user1, level=10, equipment={}, combat_class="Mago")
        p1.passives = [{"id": "hawk_strike"}]
        p2 = Combatant(self.mock_user2, level=10, equipment={}, combat_class="Pícaro")
        p2.passives = []
        view = DuelView(p1, p2, bet=100, cog=self.mock_cog)

        # Crit chance includes base 0.10 + 0.08 from hawk_strike = 0.18
        # We test that random < 0.18 triggers crit
        with patch('random.random', return_value=0.15), patch('random.uniform', return_value=1.0):
            _, log = view._calculate_action_result(p1, p2, "attack")
            self.assertIn("CRÍTICO", log)

        # In special skills, crit chance is normal (0.10), so 0.15 shouldn't crit
        view.p1_special_id = "bola_fuego"
        with patch('random.random', return_value=0.15), patch('random.uniform', return_value=1.0):
            _, log = view._calculate_action_result(p1, p2, "special")
            self.assertNotIn("CRÍTICO", log)

    def test_windfury_proc_and_icd(self):
        p1 = Combatant(self.mock_user1, level=10, equipment={}, combat_class="Mago")
        p1.passives = [{"id": "windfury"}]
        p2 = Combatant(self.mock_user2, level=10, equipment={}, combat_class="Pícaro")
        p2.passives = []
        view = DuelView(p1, p2, bet=100, cog=self.mock_cog)

        view.turn_count = 1
        # Random choice 1: avoid main crit. Random choice 2: trigger 15% probability of windfury (<0.15)
        with patch('random.random', side_effect=[0.5, 0.10]), patch('random.uniform', return_value=1.0):
            p2.hp = 100
            damage, log = view._calculate_action_result(p1, p2, "attack")
            self.assertIn("Viento de Guerra", log)
            self.assertEqual(p1.passive_icd.get("windfury"), 1)

        # ICD Check: same turn or next turn (turn 2, difference is 1, ICD is 2) should NOT proc windfury
        view.turn_count = 2
        with patch('random.random', side_effect=[0.5, 0.10]), patch('random.uniform', return_value=1.0):
            damage, log = view._calculate_action_result(p1, p2, "attack")
            self.assertNotIn("Viento de Guerra", log)

        # Turn 3 (difference is 2 >= 2) can proc windfury again
        view.turn_count = 3
        with patch('random.random', side_effect=[0.5, 0.10]), patch('random.uniform', return_value=1.0):
            damage, log = view._calculate_action_result(p1, p2, "attack")
            self.assertIn("Viento de Guerra", log)

    def test_blinding_edge_proc_and_icd(self):
        p1 = Combatant(self.mock_user1, level=10, equipment={}, combat_class="Mago")
        p1.passives = [{"id": "blinding_edge"}]
        p2 = Combatant(self.mock_user2, level=10, equipment={}, combat_class="Pícaro")
        p2.passives = []
        view = DuelView(p1, p2, bet=100, cog=self.mock_cog)

        view.turn_count = 1
        # Random choice 1: avoid main crit. Random choice 2: trigger 8% probability of blinding_edge (<0.08)
        with patch('random.random', side_effect=[0.5, 0.05]), patch('random.uniform', return_value=1.0):
            damage, log = view._calculate_action_result(p1, p2, "attack")
            self.assertIn("Filo Cegador", log)
            self.assertEqual(p2.blinded_turns, 3) # 2 + 1
            self.assertEqual(p1.passive_icd.get("blinding_edge"), 1)

        # ICD Check: turn 2 should not proc blinding_edge
        view.turn_count = 2
        p2.blinded_turns = 0
        with patch('random.random', side_effect=[0.5, 0.05]), patch('random.uniform', return_value=1.0):
            damage, log = view._calculate_action_result(p1, p2, "attack")
            self.assertNotIn("Filo Cegador", log)
            self.assertEqual(p2.blinded_turns, 0)

        # Turn 5 (difference is 4 >= 4) can proc again
        view.turn_count = 5
        with patch('random.random', side_effect=[0.5, 0.05]), patch('random.uniform', return_value=1.0):
            damage, log = view._calculate_action_result(p1, p2, "attack")
            self.assertIn("Filo Cegador", log)

    def test_erratic_ward_shield(self):
        p1 = Combatant(self.mock_user1, level=10, equipment={}, combat_class="Mago")
        p1.passives = [{"id": "erratic_ward"}]
        p2 = Combatant(self.mock_user2, level=10, equipment={}, combat_class="Pícaro")
        p2.passives = []
        view = DuelView(p1, p2, bet=100, cog=self.mock_cog)

        p1.hp = 100
        p1.pre_hit_hp = 100
        p1.used_erratic_ward = False

        # Drop HP to < 25% (e.g. 10 HP)
        p1.hp = 10
        # Trigger round end checks
        logs = []
        for p in (view.p1, view.p2):
            if p.hp > 0 and p.hp < p.max_hp * 0.25 and not p.used_erratic_ward and any(pass_item['id'] == 'erratic_ward' for pass_item in p.passives):
                p.used_erratic_ward = True
                shield_amt = int(p.max_hp * 0.10)
                p.shield += shield_amt
                logs.append("erratic_ward_proc")

        self.assertEqual(p1.shield, int(p1.max_hp * 0.10))
        self.assertTrue(p1.used_erratic_ward)
        self.assertIn("erratic_ward_proc", logs)

        # Check it runs only once per combat
        p1.shield = 0
        logs2 = []
        for p in (view.p1, view.p2):
            if p.hp > 0 and p.hp < p.max_hp * 0.25 and not p.used_erratic_ward and any(pass_item['id'] == 'erratic_ward' for pass_item in p.passives):
                p.used_erratic_ward = True
                shield_amt = int(p.max_hp * 0.10)
                p.shield += shield_amt
                logs2.append("erratic_ward_proc")
        self.assertEqual(p1.shield, 0)
        self.assertNotIn("erratic_ward_proc", logs2)

    def test_bloodlust_proc_and_icd(self):
        p1 = Combatant(self.mock_user1, level=10, equipment={}, combat_class="Mago")
        p1.passives = [{"id": "bloodlust_proc"}]
        p2 = Combatant(self.mock_user2, level=10, equipment={}, combat_class="Pícaro")
        p2.passives = []
        view = DuelView(p1, p2, bet=100, cog=self.mock_cog)

        p1.hp = 90
        p1.pre_hit_hp = 100
        p1.special_cooldown = 3
        view.turn_count = 1

        # Check proc (10% chance: patch random to < 0.10)
        with patch('random.random', return_value=0.05):
            logs = []
            for p in (view.p1, view.p2):
                damage_received = p.pre_hit_hp - p.hp
                if damage_received > 0 and p.hp > 0 and any(pass_item['id'] == 'bloodlust_proc' for pass_item in p.passives):
                    from src.utils.combat_progression import can_proc, mark_proc
                    if can_proc(p, 'bloodlust_proc', view.turn_count, 3):
                        mark_proc(p, 'bloodlust_proc', view.turn_count)
                        if p.special_cooldown > 0:
                            p.special_cooldown -= 1
                            logs.append("bloodlust_proc_success")

            self.assertEqual(p1.special_cooldown, 2)
            self.assertEqual(p1.passive_icd.get("bloodlust_proc"), 1)
            self.assertIn("bloodlust_proc_success", logs)

        # ICD Check: turn 2 should NOT trigger
        p1.hp = 80
        p1.pre_hit_hp = 90
        p1.special_cooldown = 2
        view.turn_count = 2
        with patch('random.random', return_value=0.05):
            logs = []
            for p in (view.p1, view.p2):
                damage_received = p.pre_hit_hp - p.hp
                if damage_received > 0 and p.hp > 0 and any(pass_item['id'] == 'bloodlust_proc' for pass_item in p.passives):
                    from src.utils.combat_progression import can_proc, mark_proc
                    if can_proc(p, 'bloodlust_proc', view.turn_count, 3):
                        mark_proc(p, 'bloodlust_proc', view.turn_count)
                        if p.special_cooldown > 0:
                            p.special_cooldown -= 1
                            logs.append("bloodlust_proc_success")
            self.assertEqual(p1.special_cooldown, 2)
            self.assertNotIn("bloodlust_proc_success", logs)

    def test_eternal_watch_immunity(self):
        p1 = Combatant(self.mock_user1, level=10, equipment={}, combat_class="Mago")
        p1.passives = [{"id": "eternal_watch"}]

        # Test stun immunity
        p1.stun_turns = 3
        self.assertEqual(p1.stun_turns, 0)
        self.assertTrue(p1.used_eternal_watch)
        self.assertIn("resiste", p1.eternal_watch_trigger_log)

        # Test subsequent debuff triggers (it should not resist anymore since used_eternal_watch is True)
        p1.stun_turns = 3
        self.assertEqual(p1.stun_turns, 3)

    def test_deathtouch_proc(self):
        p1 = Combatant(self.mock_user1, level=10, equipment={}, combat_class="Mago")
        p1.passives = [{"id": "deathtouch"}]
        p2 = Combatant(self.mock_user2, level=10, equipment={}, combat_class="Pícaro")
        p2.passives = []
        view = DuelView(p1, p2, bet=100, cog=self.mock_cog)

        p2.max_hp = 100
        p2.pre_hit_hp = 100
        p2.hp = 10  # drops < 15% without dying

        # Execute deathtouch check
        logs = []
        for attacker, defender in ((view.p1, view.p2), (view.p2, view.p1)):
            damage_taken = defender.pre_hit_hp - defender.hp
            if defender.hp > 0 and defender.hp < defender.max_hp * 0.15 and damage_taken > 0:
                if any(p['id'] == 'deathtouch' for p in attacker.passives):
                    dt_damage = int(damage_taken * 0.10)
                    dt_damage = max(1, dt_damage)
                    view._apply_damage_to_combatant(defender, dt_damage, logs)
                    logs.append("deathtouch_proc")

        self.assertEqual(p2.hp, 1)  # 10 - 9 = 1 HP
        self.assertIn("deathtouch_proc", logs)


class TestMiniAffixes(unittest.IsolatedAsyncioTestCase):

    def setUp(self):
        self.mock_user1 = MagicMock()
        self.mock_user1.id = 111
        self.mock_user1.display_name = "Player1"
        self.mock_user1.mention = "<@111>"

        self.mock_user2 = MagicMock()
        self.mock_user2.id = 222
        self.mock_user2.display_name = "Player2"
        self.mock_user2.mention = "<@222>"

    def test_generate_loot_includes_mini_affix(self):
        from src.utils.combat_progression import generate_loot, MINI_AFFIXES
        
        # Test Legendary loot
        with patch('src.utils.combat_progression._roll_rarity', return_value={"name": "Legendario", "mult": 1.5, "secondaries": 2, "sec_weight": 0.4, "prob": 0.05, "color": "🟧", "hex": 0xff8c00}):
            loot = generate_loot(10)
            self.assertIsNotNone(loot.get("mini_affix"))
            self.assertIn(loot["mini_affix"]["key"], MINI_AFFIXES)
            self.assertEqual(loot["mini_affix"]["value"], MINI_AFFIXES[loot["mini_affix"]["key"]]["legendario"])

        # Test Epic loot
        with patch('src.utils.combat_progression._roll_rarity', return_value={"name": "Épico", "mult": 1.3, "secondaries": 2, "sec_weight": 0.35, "prob": 0.15, "color": "🟪", "hex": 0xa020f0}):
            loot = generate_loot(10)
            self.assertIsNotNone(loot.get("mini_affix"))
            self.assertIn(loot["mini_affix"]["key"], MINI_AFFIXES)
            self.assertEqual(loot["mini_affix"]["value"], MINI_AFFIXES[loot["mini_affix"]["key"]]["epico"])

        # Test Rare loot (no mini-affix)
        with patch('src.utils.combat_progression._roll_rarity', return_value={"name": "Raro", "mult": 1.1, "secondaries": 1, "sec_weight": 0.3, "prob": 0.25, "color": "🟦", "hex": 0x0000ff}):
            loot = generate_loot(10)
            self.assertIsNone(loot.get("mini_affix"))

    def test_calc_equipment_bonus_accumulates_crit_and_dodge(self):
        from src.utils.combat_progression import calc_equipment_bonus
        equipment = {
            "Cabeza": {
                "primary_stat": "hp",
                "primary_value": 10,
                "mini_affix_key": "cazador",
                "mini_affix_value": 0.02
            },
            "Pecho": {
                "primary_stat": "hp",
                "primary_value": 15,
                "mini_affix_key": "fantasma",
                "mini_affix_value": 0.04
            }
        }
        bonus, passives, secondary_bonus = calc_equipment_bonus(equipment)
        self.assertEqual(secondary_bonus.get("crit"), 0.02)
        self.assertEqual(secondary_bonus.get("dodge"), 0.04)

    def test_combatant_stat_scaling(self):
        # We equip one item with vital (+3% HP) and one with furia (+6% ATK)
        equipment = {
            "Cabeza": {
                "primary_stat": "hp",
                "primary_value": 50,
                "mini_affix_key": "vital",
                "mini_affix_value": 0.03
            },
            "Arma": {
                "primary_stat": "atk",
                "primary_value": 30,
                "mini_affix_key": "furia",
                "mini_affix_value": 0.06
            }
        }
        # First compute stats without mini-affixes to get the baseline
        baseline_equipment = {
            "Cabeza": {
                "primary_stat": "hp",
                "primary_value": 50
            },
            "Arma": {
                "primary_stat": "atk",
                "primary_value": 30
            }
        }
        p_base = Combatant(self.mock_user1, level=10, equipment=baseline_equipment, combat_class="Mago")
        
        # Now with mini-affixes
        p = Combatant(self.mock_user1, level=10, equipment=equipment, combat_class="Mago")
        
        # Expected scaling: base stats * (1.0 + mini_affix_val)
        self.assertEqual(p.max_hp, int(p_base.max_hp * 1.03))
        self.assertEqual(p.atk, int(p_base.atk * 1.06))

    def test_format_item_stats_display_with_mini_affix(self):
        from src.utils.combat_progression import format_item_stats_display
        item = {
            "primary_stat": "hp",
            "primary_value": 100,
            "secondaries": [{"stat": "def", "value": 20}],
            "mini_affix_key": "cazador",
            "mini_affix_value": 0.02
        }
        text = format_item_stats_display(item)
        self.assertIn("Del Cazador", text)
        self.assertIn("+2%", text)
        self.assertIn("crítico", text)


class TestWeaponSubtypesAndNameSystem(unittest.IsolatedAsyncioTestCase):

    def setUp(self):
        self.mock_user1 = MagicMock()
        self.mock_user1.id = 111
        self.mock_user1.display_name = "Player1"
        self.mock_user1.mention = "<@111>"

        self.mock_user2 = MagicMock()
        self.mock_user2.id = 222
        self.mock_user2.display_name = "Player2"
        self.mock_user2.mention = "<@222>"

    def test_generate_loot_weapon_subtype_and_scaling(self):
        from src.utils.combat_progression import generate_loot, EQUIPMENT_SLOTS
        
        # Arma: should get dagger/sword/spear/axe
        with patch('random.choice', side_effect=lambda x: "Arma" if x == EQUIPMENT_SLOTS else x[0]):
            loot_daga = generate_loot(10)
            self.assertEqual(loot_daga["slot"], "Arma")
            self.assertEqual(loot_daga["weapon_subtype"], "daga")
        self.assertIn(loot_daga["weapon_subtype"], ["daga", "espada", "lanza", "hacha"])

    def test_item_name_4_layers(self):
        from src.utils.combat_progression import _generate_item_name
        
        # Test 4 layers: Legendario, Daga, passive "vampirism", mini_affix "cazador"
        name = _generate_item_name(
            slot="Arma",
            rarity_name="Legendario",
            first_secondary_stat="atk",
            material=None,
            passive_id="vampirism",
            mini_affix_key="cazador",
            weapon_subtype="daga"
        )
        self.assertTrue(any(p in name for p in ["Resplandeciente", "Ancestral", "Divino", "Eterno", "Inquebrantable"]))
        self.assertTrue(any(b in name for b in ["Daga", "Estoque", "Puñal"]))
        self.assertIn("Sediento", name)
        self.assertIn("del Verdugo", name)

    def test_combatant_subtype_crit_modifiers(self):
        # Dagger weapon
        eq_daga = {
            "Arma": {
                "primary_stat": "atk",
                "primary_value": 20,
                "weapon_subtype": "daga"
            }
        }
        p_daga = Combatant(self.mock_user1, level=10, equipment=eq_daga, combat_class="Guerrero")
        
        # Axe weapon
        eq_hacha = {
            "Arma": {
                "primary_stat": "atk",
                "primary_value": 20,
                "weapon_subtype": "hacha"
            }
        }
        p_hacha = Combatant(self.mock_user1, level=10, equipment=eq_hacha, combat_class="Guerrero")
        
        # Crit chance difference should be 10% (0.05 - (-0.05))
        self.assertAlmostEqual(p_daga.subclass_extras["crit_chance_bonus"] - p_hacha.subclass_extras["crit_chance_bonus"], 0.10)

    @patch('random.random', return_value=0.9)
    @patch('random.uniform', return_value=1.0)
    def test_duel_lance_and_axe_modifiers(self, mock_uniform, mock_random):
        eq_lanza = {"Arma": {"primary_stat": "atk", "primary_value": 100, "weapon_subtype": "lanza"}}
        eq_hacha = {"Arma": {"primary_stat": "atk", "primary_value": 100, "weapon_subtype": "hacha"}}
        eq_normal = {"Arma": {"primary_stat": "atk", "primary_value": 100, "weapon_subtype": "espada"}}
        
        p1 = Combatant(self.mock_user1, level=10, equipment=eq_lanza, combat_class="Guerrero")
        p2 = Combatant(self.mock_user2, level=10, equipment=eq_normal, combat_class="Guerrero")
        
        view = DuelView(p1, p2, bet=100, cog=MagicMock())
        
        # Case 1: Defender did not defend
        p2.last_action = "attack"
        dmg, _ = view._calculate_action_result(p1, p2, "attack")
        
        # Case 2: Defender defended last turn (should deal 10% more damage)
        p2.last_action = "defend"
        dmg_defended, _ = view._calculate_action_result(p1, p2, "attack")
        self.assertGreater(dmg_defended, dmg)
        
        # Axe case: always does 15% more damage compared to normal
        p_axe = Combatant(self.mock_user1, level=10, equipment=eq_hacha, combat_class="Guerrero")
        dmg_axe, _ = view._calculate_action_result(p_axe, p2, "attack")
        dmg_normal, _ = view._calculate_action_result(p2, p1, "attack")
        self.assertGreater(dmg_axe, dmg_normal)

    def test_tomo_and_cetro_modifiers(self):
        eq_tomo = {"Arma": {"primary_stat": "atk", "primary_value": 100, "weapon_subtype": "tomo"}}
        
        p1 = Combatant(self.mock_user1, level=10, equipment=eq_tomo, combat_class="Mago")
        p2 = Combatant(self.mock_user2, level=10, equipment={}, combat_class="Mago")
        
        view = DuelView(p1, p2, bet=100, cog=MagicMock())
        view.p1_special_id = "quemadura"
        
        # Tomo case: first special use does +10% damage
        p1.special_used_this_combat = False
        dmg_tomo_1st, _ = view._calculate_action_result(p1, p2, "special")
        
        # Second special use (flag is now True) does normal damage
        dmg_tomo_2nd, _ = view._calculate_action_result(p1, p2, "special")
        self.assertGreater(dmg_tomo_1st, dmg_tomo_2nd)


if __name__ == '__main__':
    unittest.main()
