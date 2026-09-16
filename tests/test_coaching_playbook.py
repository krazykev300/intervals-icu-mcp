"""Coaching playbook resource, prompt, and server instructions."""

from intervals_icu_mcp.prompts.coaching_playbook import COACHING_PLAYBOOK, SERVER_INSTRUCTIONS
from intervals_icu_mcp.server import mcp


class TestCoachingPlaybook:
    def test_instructions_point_at_playbook(self):
        assert mcp.instructions is not None
        assert "intervals-icu://coaching-playbook" in mcp.instructions
        assert "Propose" in SERVER_INSTRUCTIONS or "propose" in SERVER_INSTRUCTIONS.lower()

    def test_playbook_names_the_loop(self):
        for needle in (
            "icu_create_event",
            "RACE_A",
            "icu_bulk_create_events",
            "event_type Other",
            "icu_duplicate_events",
        ):
            assert needle in COACHING_PLAYBOOK
