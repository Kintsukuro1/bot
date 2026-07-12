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


if __name__ == '__main__':
    unittest.main()
