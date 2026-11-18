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
            "event_type WeightTraining",
            "icu_duplicate_events",
            "icu_get_athlete_state",
            "horizon_days=365",
            "intervals-icu://methodology",
        ):
            assert needle in COACHING_PLAYBOOK

    def test_playbook_writes_on_yes_and_defers_follow_ups(self):
        assert "Write-on-yes" in COACHING_PLAYBOOK
        assert "coach_brief.follow_ups" in COACHING_PLAYBOOK
        assert "Never promise later action" in COACHING_PLAYBOOK
        assert "analysis.ftp_check" in COACHING_PLAYBOOK
        assert "same turn" in SERVER_INSTRUCTIONS

    def test_playbook_caps_flags_and_handles_travel_focus_moves(self):
        for needle in (
            "coach_brief.flags",
            "flags_more",
            "coach_brief.away",
            "HOLIDAY event in the same calendar offer",
            "coach_brief.phase.focus",
            "icu_update_event",
        ):
            assert needle in COACHING_PLAYBOOK

    def test_playbook_session_layout_availability_and_logging(self):
        for needle in (
            "Session layout",
            "`purpose`",
            "`fallback`",
            "`carbs_per_hour`",
            "`role`",
            "`indoor`",
            "`max_training_seconds`",
            "`can_train_sports`",
            "icu_log_session",
        ):
            assert needle in COACHING_PLAYBOOK
