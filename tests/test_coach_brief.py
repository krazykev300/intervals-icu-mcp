"""Coach brief: deterministic prescription from methodology tables."""

from __future__ import annotations

from datetime import date, datetime, timedelta

from intervals_icu_mcp.athlete_state_compute import (
    _intensity_bin,
    derive_phase_context,
    derived_flags,
)
from intervals_icu_mcp.coach_brief import (
    build_coach_brief,
    completed_week_loads,
    intensity_factor,
    select_distribution,
    select_ramp_tier,
    weeks_since_recovery,
)
from intervals_icu_mcp.models import ActivitySummary, Event
from intervals_icu_mcp.tools.coaching_guide import get_coaching_guide

TODAY = date(2026, 11, 16)  # a Monday


def _activity(day: date, load: int, intensity: float | None = None) -> ActivitySummary:
    return ActivitySummary.model_validate(
        {
            "id": f"i{day.toordinal()}{load}",
            "start_date_local": datetime(day.year, day.month, day.day, 9).isoformat(),
            "type": "Ride",
            "name": "Ride",
            "moving_time": 3600,
            "icu_training_load": load,
            "icu_intensity": intensity,
        }
    )


def _event(day: date, category: str, **extra) -> Event:
    return Event.model_validate(
        {
            "id": day.toordinal(),
            "start_date_local": day.isoformat(),
            "name": "E",
            "category": category,
            **extra,
        }
    )


def _weeks(loads: list[int]) -> list[ActivitySummary]:
    """One activity per completed week, oldest first, ending the week before TODAY."""
    start = TODAY - timedelta(days=7 * len(loads))
    return [_activity(start + timedelta(days=7 * i + 2), load) for i, load in enumerate(loads)]


def _brief(**overrides):
    args = {
        "today": TODAY,
        "events": [],
        "activities": _weeks([500, 520, 540, 560]),
        "phase_context": {"current_phase": None, "source": "unspecified"},
        "current_fitness": {"ctl": 70.0, "tsb": -5.0},
        "tolerance": {
            "min_observed": -38.0,
            "excursions_below_-25": 8,
            "median_days_to_recover": 5.0,
        },
        "constraints": {
            "typical_weekly_hours": {"median": 10.5},
            "typical_weekly_load": {"p90": 840.0},
        },
        "readiness_state": "green",
    }
    args.update(overrides)
    return build_coach_brief(**args)


class TestIntensityScale:
    def test_percent_is_normalized(self):
        assert intensity_factor(81.0) == 0.81
        assert intensity_factor(0.81) == 0.81
        assert intensity_factor(None) is None

    def test_bins_accept_percent(self):
        assert _intensity_bin(66.3) == "recovery"
        assert _intensity_bin(81.0) == "endurance"
        assert _intensity_bin(0.9) == "threshold"
        assert _intensity_bin(101.0) == "vo2"


class TestWeeks:
    def test_current_week_excluded_and_gaps_zero_filled(self):
        activities = [
            _activity(date(2026, 10, 27), 300),
            _activity(date(2026, 11, 10), 400),
            _activity(TODAY, 999),
        ]
        weeks = completed_week_loads(activities, TODAY)
        assert [w["load"] for w in weeks] == [300, 0, 400]
        assert weeks[-1]["week_start"] == "2026-11-09"

    def test_weeks_since_recovery(self):
        assert weeks_since_recovery([500, 520, 300, 520, 540]) == 2
        assert weeks_since_recovery([500, 520, 540, 300]) == 0
        assert weeks_since_recovery([500, 520, 540, 560]) == 4


class TestRampTier:
    def test_aggressive_when_deep_and_fast_recovery(self):
        tier = select_ramp_tier(
            {"min_observed": -38, "excursions_below_-25": 8, "median_days_to_recover": 5.0}, "green"
        )
        assert tier["tier"] == "aggressive" and tier["ctl_per_week"] == 7

    def test_red_readiness_drops_a_tier(self):
        tier = select_ramp_tier(
            {"min_observed": -38, "excursions_below_-25": 8, "median_days_to_recover": 5.0}, "red"
        )
        assert tier["tier"] == "standard"

    def test_slow_recovery_is_conservative(self):
        tier = select_ramp_tier(
            {"min_observed": -30, "excursions_below_-25": 3, "median_days_to_recover": 16.0}, None
        )
        assert tier["tier"] == "conservative"

    def test_no_deep_history(self):
        assert select_ramp_tier({"min_observed": -8.0}, None)["tier"] == "conservative"
        assert select_ramp_tier({"min_observed": -18.0}, None)["tier"] == "standard"


class TestDistribution:
    def test_by_hours(self):
        assert select_distribution(4.0, "build")["model"] == "threshold"
        assert select_distribution(10.5, "build")["model"] == "pyramidal"
        assert select_distribution(16.0, "build")["model"] == "polarized"
        assert "alternative" in select_distribution(10.5, "base")
        assert select_distribution(None, "base") == {}


class TestBrief:
    def test_general_fitness_without_a_race(self):
        brief = _brief()
        assert brief["phase"]["name"] == "general_fitness"
        assert brief["today"]["weekday"] == "Mon"
        assert brief["today"]["next_monday"] == "2026-11-23"
        assert any("RACE_A" in a for a in brief["next_actions"])
        # four loading weeks in a row → recovery week at 60% of the last three
        assert brief["load"]["recovery_week_due"] is True
        assert brief["load"]["next_week_target"]["load"] == round(540 * 0.6)
        assert brief["load"]["hard_sessions_per_week"] == 1

    def test_build_target_from_ctl_and_ramp(self):
        race = _event(TODAY + timedelta(days=60), "RACE_A", type="Ride")
        brief = _brief(
            events=[race],
            activities=_weeks([500, 520, 300, 520]),
            phase_context={"current_phase": "build", "source": "derived_from_race"},
        )
        assert brief["phase"]["a_race"]["days_out"] == 60
        assert brief["load"]["recovery_week_due"] is False
        assert brief["load"]["next_week_target"]["load"] == round(7 * (70 + 6.51 * 7))
        assert not any("RACE_A" in a for a in brief["next_actions"])

    def test_target_above_capacity_warns(self):
        brief = _brief(
            activities=_weeks([500, 520, 300, 520]),
            constraints={
                "typical_weekly_hours": {"median": 6.0},
                "typical_weekly_load": {"p90": 500.0},
            },
        )
        assert "warning" in brief["load"]["next_week_target"]

    def test_taper_race_week(self):
        race = _event(TODAY + timedelta(days=5), "RACE_A", type="Ride")
        brief = _brief(
            events=[race], phase_context={"current_phase": "taper", "source": "derived_from_race"}
        )
        assert brief["load"]["next_week_target"]["load"] == round(540 * 0.45)

    def test_peak_holds_ctl(self):
        brief = _brief(phase_context={"current_phase": "peak", "source": "derived_from_race"})
        assert brief["load"]["next_week_target"]["load"] == 490

    def test_amber_swaps_a_hard_day(self):
        hard = _event(TODAY, "WORKOUT", type="Ride", icu_intensity=92.0, icu_training_load=90)
        brief = _brief(events=[hard], readiness_state="amber")
        assert brief["today"]["action"] == "swap_hard_for_endurance"
        assert brief["today"]["planned"][0]["intensity_factor"] == 0.92

    def test_unknown_readiness_asks(self):
        brief = _brief(readiness_state="unknown")
        assert brief["today"]["action"] == "ask_before_intensity"
        assert "slept" in brief["next_actions"][0]

    def test_empty_inputs_do_not_raise(self):
        brief = build_coach_brief(
            today=TODAY,
            events=[],
            activities=[],
            phase_context={},
            current_fitness={},
            tolerance={},
            constraints={},
            readiness_state=None,
        )
        assert "next_week_target" not in brief["load"]
        assert brief["today"]["action"] == "ask_before_intensity"


class TestPhaseFixes:
    def test_stale_past_a_race_is_unspecified(self):
        ctx = derive_phase_context([_event(date(2026, 9, 7), "RACE_A")], TODAY)
        assert ctx["source"] == "unspecified"
        assert ctx["last_a_race"]["date"] == "2026-09-07"
        assert "anchor_event_id" not in ctx

    def test_recent_a_race_beats_a_far_future_one(self):
        events = [
            _event(TODAY - timedelta(days=5), "RACE_A"),
            _event(TODAY + timedelta(days=200), "RACE_A"),
        ]
        assert derive_phase_context(events, TODAY)["current_phase"] == "recovery"

    def test_hour_power_flag_reads_any_window_label(self):
        flags = derived_flags(
            ftp=300, power={"d366": {"60m": 250}}, constraints={}, compliance=None
        )
        assert any(f.startswith("60m_to_ftp_gap") for f in flags)


class TestCoachingGuide:
    async def test_default_is_playbook_and_methodology(self):
        text = await get_coaching_guide()
        assert "# Coaching playbook" in text
        assert "# Coaching methodology parameters" in text
        assert "Workout Syntax Reference" not in text

    async def test_topics_as_string_and_unknown(self):
        text = await get_coaching_guide("workout_syntax, event_categories")
        assert "Workout Syntax Reference" in text and "Event Categories" in text
        assert (await get_coaching_guide(["nope"])).startswith("Unknown topic")
