"""Tests for INTERVALS_ICU_TOOL_PROFILE config and filtered tool registration."""

import asyncio
import importlib
import sys

import pytest
from pydantic import ValidationError

from intervals_icu_mcp.auth import ICUConfig
from intervals_icu_mcp.tool_profile import COACHING_TOOLS, coaching_tools_for_delete_mode


class TestToolProfileValidation:
    def test_default_is_coaching(self, monkeypatch):
        monkeypatch.delenv("INTERVALS_ICU_TOOL_PROFILE", raising=False)
        cfg = ICUConfig(intervals_icu_api_key="k", intervals_icu_athlete_id="a")
        assert cfg.intervals_icu_tool_profile == "coaching"

    def test_accepts_full(self):
        cfg = ICUConfig(
            intervals_icu_api_key="k",
            intervals_icu_athlete_id="a",
            intervals_icu_tool_profile="full",
        )
        assert cfg.intervals_icu_tool_profile == "full"

    def test_normalizes_case_and_whitespace(self):
        cfg = ICUConfig.model_validate(
            {
                "intervals_icu_api_key": "k",
                "intervals_icu_athlete_id": "a",
                "intervals_icu_tool_profile": "  FULL  ",
            }
        )
        assert cfg.intervals_icu_tool_profile == "full"

    def test_rejects_invalid_value(self):
        with pytest.raises(ValidationError) as exc_info:
            ICUConfig.model_validate(
                {
                    "intervals_icu_api_key": "k",
                    "intervals_icu_athlete_id": "a",
                    "intervals_icu_tool_profile": "banana",
                }
            )
        message = str(exc_info.value)
        assert "INTERVALS_ICU_TOOL_PROFILE must be one of" in message
        assert "banana" in message


def _reload_server() -> object:
    """Re-import the server module so module-level registration re-runs."""
    sys.modules.pop("intervals_icu_mcp.server", None)
    return importlib.import_module("intervals_icu_mcp.server")


class TestCoachingRegistration:
    @staticmethod
    def _tool_names(server_module: object) -> set[str]:
        tools = asyncio.run(server_module.mcp.list_tools())  # type: ignore[attr-defined]
        return {t.name for t in tools}

    def test_coaching_safe_matches_allow_list(self, monkeypatch):
        monkeypatch.setenv("INTERVALS_ICU_TOOL_PROFILE", "coaching")
        monkeypatch.setenv("INTERVALS_ICU_DELETE_MODE", "safe")
        names = self._tool_names(_reload_server())
        assert names == set(coaching_tools_for_delete_mode("safe"))
        assert "icu_get_calendar_events" in names
        assert "icu_get_activity_streams" in names
        assert "icu_get_power_histogram" in names
        assert "icu_get_gear_list" not in names
        assert "icu_get_custom_items" not in names
        assert "icu_update_sport_settings" not in names
        assert "icu_list_athletes" not in names

    def test_coaching_none_drops_delete_event(self, monkeypatch):
        monkeypatch.setenv("INTERVALS_ICU_TOOL_PROFILE", "coaching")
        monkeypatch.setenv("INTERVALS_ICU_DELETE_MODE", "none")
        names = self._tool_names(_reload_server())
        assert names == set(coaching_tools_for_delete_mode("none"))
        assert "icu_delete_event" not in names

    def test_full_safe_keeps_upstream_catalog(self, monkeypatch):
        monkeypatch.setenv("INTERVALS_ICU_TOOL_PROFILE", "full")
        monkeypatch.setenv("INTERVALS_ICU_DELETE_MODE", "safe")
        names = self._tool_names(_reload_server())
        assert len(names) == 61
        assert "icu_get_gear_list" in names
        assert "icu_get_custom_items" in names
        assert "icu_update_sport_settings" in names
        assert COACHING_TOOLS <= names

    def test_coach_with_goals_prompt_registered(self, monkeypatch):
        monkeypatch.setenv("INTERVALS_ICU_TOOL_PROFILE", "coaching")
        server = _reload_server()

        async def _names() -> set[str]:
            prompts = await server.mcp.list_prompts()  # type: ignore[attr-defined]
            return {p.name for p in prompts}

        names = asyncio.run(_names())
        assert "coach_with_goals" in names
        assert "plan_training_week" in names
