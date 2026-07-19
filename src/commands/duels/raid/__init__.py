import sys
import os
import importlib.util

# 1. Dynamically load the shadowed raid.py module from the parent directory
parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
raid_py_path = os.path.join(parent_dir, "raid.py")

spec = importlib.util.spec_from_file_location("src.commands.duels.raid_file", raid_py_path)
raid_module = importlib.util.module_from_spec(spec)
sys.modules["src.commands.duels.raid_file"] = raid_module
spec.loader.exec_module(raid_module)

# 2. Expose the classes/functions from the new package modules
from .boss import RaidBoss
from .combatant import RaidCombatant
from .lobby_view import RaidLobbyView, get_combatant_available_skills
from .skill_views import PersonalSkillSelectView, PersonalRaidConsumableSelectView, RaidSilenceTargetSelectView
from .loot_views import (
    RaidLootView, RaidLootRollView, log_raid, count_mythic_raids_today,
    build_minions_from_pool, build_miniboss_config, roll_unique_item,
    LOOT_ROLL_TIMEOUT
)
from .merchant_views import PhantomMerchantSlotSelectView, PhantomMerchantView

# 3. Expose the remaining items from the original raid.py file
RaidsCog = getattr(raid_module, "RaidsCog")
RaidCombatView = getattr(raid_module, "RaidCombatView")
setup = getattr(raid_module, "setup")
trigger_fury_phase = getattr(raid_module, "trigger_fury_phase", None)

# 4. Expose DB/config objects that are patched in unit tests
db_cursor = getattr(raid_module, "db_cursor")
get_user_equipment = getattr(raid_module, "get_user_equipment")
generate_raid_loot = getattr(raid_module, "generate_raid_loot")
ensure_user = getattr(raid_module, "ensure_user")
get_combat_stats = getattr(raid_module, "get_combat_stats")

__all__ = [
    'RaidBoss',
    'RaidCombatant',
    'RaidLobbyView',
    'get_combatant_available_skills',
    'PersonalSkillSelectView',
    'PersonalRaidConsumableSelectView',
    'RaidSilenceTargetSelectView',
    'RaidLootView',
    'RaidLootRollView',
    'log_raid',
    'count_mythic_raids_today',
    'build_minions_from_pool',
    'build_miniboss_config',
    'roll_unique_item',
    'PhantomMerchantSlotSelectView',
    'PhantomMerchantView',
    'RaidsCog',
    'RaidCombatView',
    'setup',
    'trigger_fury_phase',
    'LOOT_ROLL_TIMEOUT',
    'db_cursor',
    'get_user_equipment',
    'generate_raid_loot',
    'ensure_user',
    'get_combat_stats'
]
