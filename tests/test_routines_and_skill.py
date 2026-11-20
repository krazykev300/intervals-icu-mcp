"""Named routines, the prompt profile, the illness protocol text, and the Claude Skill."""

import asyncio
import importlib
import importlib.util
import re
import sys
from pathlib import Path

import pytest

from intervals_icu_mcp.coaching.methodology import METHODOLOGY_SPEC, RETURN_FROM_BREAK
from intervals_icu_mcp.prompts import routines
from intervals_icu_mcp.prompts.coaching_playbook import COACHING_PLAYBOOK
from intervals_icu_mcp.prompts.routines import ROUTINE_PROMPTS, ROUTINES
from intervals_icu_mcp.prompts.skill import SKILL_DESCRIPTION, SKILL_NAME, render_skill
from intervals_icu_mcp.tool_profile import COACHING_PROMPTS, COACHING_TOOLS

ROOT = Path(__file__).resolve().parent.parent
UPSTREAM_PROMPTS = {
    "generate_workout",
    "analyze_recent_training",
    "performance_analysis",
    "activity_deep_dive",
    "recovery_check",
    "training_plan_review",
    "plan_training_week",
    "verify_multi_athlete",
}


def _prompt_names(monkeypatch: pytest.MonkeyPatch, profile: str) -> set[str]:
    monkeypatch.setenv("INTERVALS_ICU_TOOL_PROFILE", profile)
    sys.modules.pop("intervals_icu_mcp.server", None)
    server = importlib.import_module("intervals_icu_mcp.server")
    names = {p.name for p in asyncio.run(server.mcp.list_prompts())}
    sys.modules.pop("intervals_icu_mcp.server", None)
    return names


class TestRoutineIndex:
    def test_every_routine_has_a_prompt_and_the_reverse(self):
        assert {fn.__name__ for fn in ROUTINE_PROMPTS} == set(ROUTINES)

    def test_the_seven_backlog_routines(self):
        assert set(ROUTINES) == {
            "morning_check",
            "review_my_week",
            "plan_next_week",
            "race_week",
            "after_the_race",
            "im_sick",
            "i_have_45_minutes",
        }

    @pytest.mark.parametrize("name", sorted(ROUTINES))
    def test_heading_exists_in_playbook(self, name: str):
        assert ROUTINES[name].heading in COACHING_PLAYBOOK

    @pytest.mark.parametrize("name", sorted(ROUTINES))
    def test_tools_are_in_the_coaching_profile(self, name: str):
        assert set(ROUTINES[name].tools) <= COACHING_TOOLS

    @pytest.mark.parametrize("name", sorted(ROUTINES))
    async def test_body_reads_state_then_guide_then_names_the_routine(self, name: str):
        body = await getattr(routines, name)()
        state = body.index("icu_get_athlete_state")
        guide = body.index("icu_get_coaching_guide")
        where = body.index(ROUTINES[name].heading.strip("*# "))
        assert state < guide < where
        for tool in ROUTINES[name].tools:
            assert tool in body
        # Every tool a routine body names is one the coaching profile registers.
        assert set(re.findall(r"\bicu_[a-z_]+\b", body)) <= COACHING_TOOLS

    async def test_arguments_reach_the_body(self):
        body = await routines.i_have_45_minutes(minutes="30", location="trainer")
        assert "30 minutes" in body and "trainer" in body
        assert "45 minutes" in await routines.i_have_45_minutes(minutes=" ")
        assert "head cold" in await routines.im_sick(what="head cold")
        assert "What is wrong" not in await routines.im_sick()


class TestPromptProfile:
    def test_coaching_registers_only_athlete_prompts(self, monkeypatch: pytest.MonkeyPatch):
        names = _prompt_names(monkeypatch, "coaching")
        assert names == set(COACHING_PROMPTS)
        assert set(ROUTINES) <= names
        assert not names & UPSTREAM_PROMPTS

    def test_full_keeps_upstream_prompts_and_adds_routines(self, monkeypatch: pytest.MonkeyPatch):
        names = _prompt_names(monkeypatch, "full")
        assert UPSTREAM_PROMPTS <= names
        assert set(COACHING_PROMPTS) <= names


class TestIllnessProtocol:
    def test_playbook_protocol_steps(self):
        section = COACHING_PLAYBOOK.split("## 7. Illness and injury protocol", 1)[1]
        for needle in (
            "see a doctor",
            "not a medical service",
            "category SICK or",
            "`training_availability`",
            "UNAVAILABLE",
            "LIMITED",
            "`max_training_seconds` 2700",
            "`can_train_sports`",
            "`icu_get_calendar_events`",
            "`icu_delete_event`",
            "category NOTE",
            "drops its planned load",
            "never deleted",
            '"Return from a break"',
            "`icu_bulk_create_events`",
            "`end_date`",
            "`coach_brief.returning`",
        ):
            assert needle in section, needle

    def test_playbook_routes_sick_days_to_the_protocol(self):
        morning = COACHING_PLAYBOOK.split("**Morning check**", 1)[1].split("**", 1)[0]
        assert "section 7" in morning
        assert "SICK / INJURED and section 7" in COACHING_PLAYBOOK

    def test_methodology_text_matches_the_table(self):
        section = METHODOLOGY_SPEC.split("## Return from a break", 1)[1].split("\n## ", 1)[0]
        short, long = RETURN_FROM_BREAK["short"], RETURN_FROM_BREAK["long"]
        resume = RETURN_FROM_BREAK["resume_plan_days_missed_max"]
        assert f"1-{resume} days:" in section
        assert f"{resume + 1}-{short['days_missed_max']} days:" in section
        assert f"{long['days_missed_min']}+ days:" in section
        assert long["days_missed_min"] == short["days_missed_max"] + 1
        assert f"{short['first_week_load_pct']}% of pre-break load" in section
        assert f"first {short['easy_days_first']} days easy" in section
        assert f"{long['first_week_load_pct']}% of pre-break load" in section
        assert f"first {long['easy_days_first']} days easy" in section
        limit_min = RETURN_FROM_BREAK["limited_illness_max_training_seconds"] // 60
        assert f"up to {limit_min} minutes" in section
        assert f"`max_training_seconds` {limit_min * 60}" in COACHING_PLAYBOOK


class TestSkill:
    def test_committed_skill_matches_source(self):
        """Fails when the playbook, methodology or routines changed without `make skill`."""
        for rel, content in render_skill().items():
            path = ROOT / "skills" / SKILL_NAME / rel
            assert path.exists(), f"{path} missing; run `make skill`"
            assert path.read_text(encoding="utf-8") == content, f"{rel} is stale; run `make skill`"

    def test_frontmatter(self):
        skill = render_skill()["SKILL.md"]
        match = re.match(r"---\nname: (.+)\ndescription: (.+)\n---\n", skill)
        assert match, "SKILL.md must open with name and description frontmatter"
        assert match.group(1) == SKILL_NAME
        assert re.fullmatch(r"[a-z0-9-]{1,64}", SKILL_NAME)
        assert match.group(2) == SKILL_DESCRIPTION
        assert len(SKILL_DESCRIPTION) <= 1024

    def test_state_first_then_guide_and_every_routine_listed(self):
        skill = render_skill()["SKILL.md"]
        assert skill.index("`icu_get_athlete_state`") < skill.index("`icu_get_coaching_guide`")
        for name, routine in ROUTINES.items():
            assert f"`{name}`" in skill
            assert routine.title in skill
        assert set(re.findall(r"`(icu_[a-z_]+)`", skill)) <= COACHING_TOOLS

    def test_references_carry_the_playbook_and_methodology(self):
        files = render_skill()
        assert COACHING_PLAYBOOK in files["references/playbook.md"]
        assert METHODOLOGY_SPEC in files["references/methodology.md"]

    def test_build_script_check_mode_agrees(self):
        spec = importlib.util.spec_from_file_location(
            "build_skill", ROOT / "scripts" / "build_skill.py"
        )
        assert spec and spec.loader
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        assert module.stale_files() == []


def test_full_profile_prompt_count_in_docs(monkeypatch: pytest.MonkeyPatch):
    """docs/tools.md states the `full` prompt count; test_doc_counts covers coaching."""
    full = len(_prompt_names(monkeypatch, "full"))
    tools_md = (ROOT / "docs" / "tools.md").read_text(encoding="utf-8")
    assert f"({full} in `full`)" in tools_md
    assert f"### Added by the `full` profile ({full - len(COACHING_PROMPTS)})" in tools_md
    assert f"### Coaching profile ({len(COACHING_PROMPTS)})" in tools_md
