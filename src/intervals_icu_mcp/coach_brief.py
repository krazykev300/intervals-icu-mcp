"""Deterministic coach brief for `icu_get_athlete_state` (no HTTP).

Applies the methodology tables to this athlete's numbers so every chat starts
from the same prescription: phase, intensity distribution, ramp tier, next
week's load target, today's call, and an ordered to-do list. The model
explains and schedules; it does not re-derive these numbers.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from typing import Any

from .athlete_state_compute import parse_iso_date
from .methodology import (
    CTL_WEEK_GAIN_FACTOR,
    DISTRIBUTION_MODELS,
    HARD_SESSION_INTENSITY_FACTOR,
    POST_A_RECOVERY_LOAD_PCT,
    RAMP,
    RAMP_SELECTION,
    RECOVERY_WEEK_RATIO,
    TAPER_WEEK_LOAD_PCT,
    TSB_EXCURSION_THRESHOLD,
)
from .models import ActivitySummary, Event

_TIERS = ("conservative", "standard", "aggressive")
_WEEKDAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")


def intensity_factor(value: float | None) -> float | None:
    """Normalize Intervals intensity to a fraction (the API sends percent, e.g. 81.0)."""
    if value is None:
        return None
    return round(value / 100.0, 3) if value > 2.0 else round(value, 3)


def _week_start(day: date) -> date:
    return day - timedelta(days=day.weekday())


def completed_week_loads(activities: list[ActivitySummary], today: date) -> list[dict[str, Any]]:
    """Load per completed ISO week (oldest first), zero-filled, current week excluded."""
    this_week = _week_start(today)
    by_week: dict[date, float] = defaultdict(float)
    for activity in activities:
        day = parse_iso_date(activity.start_date_local)
        week = _week_start(day)
        if week < this_week:
            by_week[week] += float(activity.icu_training_load or 0)
    if not by_week:
        return []
    week = min(by_week)
    series: list[dict[str, Any]] = []
    while week < this_week:
        series.append({"week_start": week.isoformat(), "load": round(by_week.get(week, 0.0))})
        week += timedelta(days=7)
    return series


def weeks_since_recovery(loads: list[float]) -> int:
    """Completed weeks since the last recovery week (the whole window if none found)."""
    count = 0
    for index in range(len(loads) - 1, -1, -1):
        prior = loads[max(0, index - 3) : index]
        if len(prior) >= 2:
            prior_mean = sum(prior) / len(prior)
            if prior_mean > 0 and loads[index] <= RECOVERY_WEEK_RATIO * prior_mean:
                return count
        count += 1
    return count


def select_ramp_tier(tolerance: dict[str, Any], readiness_state: str | None) -> dict[str, Any]:
    """Pick conservative / standard / aggressive from empirical TSB tolerance."""
    excursions = int(tolerance.get("excursions_below_-25") or 0)
    recover = tolerance.get("median_days_to_recover")
    min_tsb = tolerance.get("min_observed")
    aggressive = RAMP_SELECTION["aggressive"]
    if recover is not None and recover > RAMP_SELECTION["conservative_if_recover_days_over"]:
        tier, why = "conservative", f"median {recover:g} days to recover from deep fatigue"
    elif (
        excursions >= aggressive["excursions_min"]
        and recover is not None
        and recover <= aggressive["median_days_to_recover_max"]
    ):
        tier = "aggressive"
        why = f"{excursions} excursions below -25 TSB, median recovery {recover:g} days"
    elif min_tsb is not None and min_tsb <= RAMP_SELECTION["standard_if_min_tsb_at_or_below"]:
        tier, why = "standard", f"min observed TSB {min_tsb:g}"
    else:
        tier, why = RAMP_SELECTION["default"], "no history of absorbing deep fatigue"
    if readiness_state == "red" and tier != "conservative":
        tier = _TIERS[_TIERS.index(tier) - 1]
        why += "; dropped one tier for red readiness"
    return {"tier": tier, "ctl_per_week": RAMP["ctl_per_week"][tier], "why": why}


def select_distribution(median_weekly_hours: float | None, phase: str | None) -> dict[str, Any]:
    """Intensity distribution from observed weekly hours."""
    if median_weekly_hours is None:
        return {}
    hours = median_weekly_hours
    if hours > 14:
        model = "polarized"
    elif hours >= 6:
        model = "pyramidal"
    else:
        model = "threshold"
    shares = DISTRIBUTION_MODELS[model]
    result: dict[str, Any] = {
        "model": model,
        "time_share": {
            "z1_easy": shares["z1"],
            "z2_tempo_threshold": shares["z2"],
            "z3_vo2_plus": shares["z3"],
        },
        "based_on_median_weekly_hours": round(hours, 1),
    }
    if model == "pyramidal" and hours >= 8 and phase == "base":
        result["alternative"] = "polarized is acceptable in base at this volume"
    return result


def _hard_sessions(phase: str | None, recovery_week: bool, hours: float | None) -> int:
    if phase == "recovery":
        return 0
    if recovery_week:
        return 1
    if phase in ("build", "peak") and hours is not None and hours >= 12:
        return 3
    return 2


def _a_race(
    events: list[Event], today: date
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    """(next future RACE_A, most recent past RACE_A)."""
    nxt: dict[str, Any] | None = None
    last: dict[str, Any] | None = None
    for event in events:
        if event.category != "RACE_A":
            continue
        day = parse_iso_date(event.start_date_local)
        item = {"id": event.id, "name": event.name, "date": day.isoformat()}
        if day >= today:
            if nxt is None or day.isoformat() < nxt["date"]:
                nxt = {**item, "days_out": (day - today).days}
        elif last is None or day.isoformat() > last["date"]:
            last = {**item, "days_ago": (today - day).days}
    return nxt, last


def _today_block(
    events: list[Event],
    activities: list[ActivitySummary],
    today: date,
    readiness_state: str | None,
    tsb: float | None,
) -> dict[str, Any]:
    planned: list[dict[str, Any]] = []
    hard = False
    for event in events:
        if event.category != "WORKOUT" or parse_iso_date(event.start_date_local) != today:
            continue
        item: dict[str, Any] = {"id": event.id, "name": event.name}
        if event.type:
            item["type"] = event.type
        if event.icu_training_load:
            item["planned_load"] = event.icu_training_load
        factor = intensity_factor(event.icu_intensity)
        if factor is not None:
            item["intensity_factor"] = round(factor, 2)
            hard = hard or factor >= HARD_SESSION_INTENSITY_FACTOR
        planned.append(item)
    done = [
        a.name or a.type or "activity"
        for a in activities
        if parse_iso_date(a.start_date_local) == today
    ]

    if readiness_state == "red":
        action = "recovery_or_rest"
        why = "red readiness: easy spin or rest; move any key session, do not delete it"
    elif readiness_state == "amber":
        if hard:
            action = "swap_hard_for_endurance"
            why = "amber readiness and a hard session planned: swap with the nearest easy day"
        else:
            action = "proceed_easy_only"
            why = "amber readiness: planned easy work is fine; add no intensity"
    elif readiness_state == "green":
        action, why = "proceed_as_planned", "green readiness"
    else:
        action = "ask_before_intensity"
        why = (
            "no HRV or sleep for today yet: ask how they slept and feel before "
            "approving a hard session; easy work is fine"
        )
    if tsb is not None and tsb < TSB_EXCURSION_THRESHOLD and action == "proceed_as_planned":
        why += f"; TSB {tsb:g} is below {TSB_EXCURSION_THRESHOLD:g}, keep an easy day close"

    block: dict[str, Any] = {
        "date": today.isoformat(),
        "weekday": _WEEKDAYS[today.weekday()],
        "week_start_monday": _week_start(today).isoformat(),
        "next_monday": (_week_start(today) + timedelta(days=7)).isoformat(),
        "readiness_state": readiness_state or "not_requested",
        "action": action,
        "why": why,
        "planned": planned,
    }
    if done:
        block["already_done"] = done
    return block


def build_coach_brief(
    *,
    today: date,
    events: list[Event],
    activities: list[ActivitySummary],
    phase_context: dict[str, Any],
    current_fitness: dict[str, Any],
    tolerance: dict[str, Any],
    constraints: dict[str, Any],
    readiness_state: str | None,
) -> dict[str, Any]:
    """Assemble the brief. Every input may be empty; omit what cannot be computed."""
    next_a, last_a = _a_race(events, today)
    phase = phase_context.get("current_phase")
    if phase in (None, "unspecified"):
        phase = "general_fitness"
    hours_block: dict[str, Any] = constraints.get("typical_weekly_hours") or {}
    hours: float | None = hours_block.get("median")
    ctl = current_fitness.get("ctl")
    tsb = current_fitness.get("tsb")

    brief: dict[str, Any] = {
        "today": _today_block(events, activities, today, readiness_state, tsb),
        "phase": {"name": phase, "source": phase_context.get("source", "unspecified")},
    }
    if next_a:
        brief["phase"]["a_race"] = next_a
    elif last_a:
        brief["phase"]["last_a_race"] = last_a

    b_c_soon = [
        {
            "name": e.name,
            "category": e.category,
            "date": parse_iso_date(e.start_date_local).isoformat(),
            "days_out": (parse_iso_date(e.start_date_local) - today).days,
        }
        for e in events
        if e.category in ("RACE_B", "RACE_C")
        and 0 <= (parse_iso_date(e.start_date_local) - today).days <= 14
    ]
    if b_c_soon:
        brief["phase"]["b_c_races_within_14d"] = b_c_soon

    distribution = select_distribution(hours, phase)
    if distribution:
        brief["intensity_distribution"] = distribution

    weeks = completed_week_loads(activities, today)
    loads = [float(w["load"]) for w in weeks]
    recent = loads[-3:]
    reference = round(sum(recent) / len(recent)) if recent else None
    since_recovery = weeks_since_recovery(loads) if loads else None
    recovery_due = (
        since_recovery is not None
        and since_recovery >= RAMP["consecutive_build_weeks_max"]
        and phase in ("base", "build", "general_fitness")
    )

    ramp = select_ramp_tier(tolerance, readiness_state) if tolerance else None
    load: dict[str, Any] = {}
    if weeks:
        load["last_completed_weeks"] = weeks[-4:]
        load["weeks_since_recovery_week"] = since_recovery
    target: int | None = None
    basis = ""
    days_out = next_a["days_out"] if next_a else None
    if phase == "recovery" and reference is not None:
        target = round(reference * POST_A_RECOVERY_LOAD_PCT / 100)
        basis = (
            f"post-A recovery: at most {POST_A_RECOVERY_LOAD_PCT}% of recent weeks, no intensity"
        )
    elif phase == "taper" and reference is not None:
        key = "days_out_0_to_7" if (days_out is not None and days_out <= 7) else "days_out_8_to_14"
        pct = TAPER_WEEK_LOAD_PCT[key]
        target = round(reference * pct / 100)
        basis = f"taper: {pct}% of recent weeks (race day excluded), keep intensity, cut volume"
    elif recovery_due and reference is not None:
        pct = RAMP["recovery_week_load_pct"]
        target = round(reference * pct / 100)
        basis = f"recovery week due after {since_recovery} loading weeks: {pct}% of recent weeks"
    elif ctl is not None:
        if phase == "peak":
            rate = 0
            basis = "peak: hold CTL, race-specific intensity, no extra volume"
        elif ramp is not None:
            rate = ramp["ctl_per_week"]
            basis = f"{ramp['tier']} ramp, +{rate} CTL/week from CTL {ctl:g}"
        else:
            rate = RAMP["ctl_per_week"]["conservative"]
            basis = f"conservative ramp (no TSB history), +{rate} CTL/week from CTL {ctl:g}"
        target = round(7 * (float(ctl) + CTL_WEEK_GAIN_FACTOR * rate))
    if target is not None:
        load["next_week_target"] = {
            "load": target,
            "range": [round(target * 0.9), round(target * 1.1)],
            "basis": basis,
        }
        load_block: dict[str, Any] = constraints.get("typical_weekly_load") or {}
        ceiling: float | None = load_block.get("p90")
        if ceiling and target > ceiling * 1.1:
            load["next_week_target"]["warning"] = (
                f"above this athlete's p90 week ({ceiling:g}); confirm available hours first"
            )
    if ramp is not None:
        load["ramp"] = ramp
    load["recovery_week_due"] = bool(recovery_due)
    load["hard_sessions_per_week"] = _hard_sessions(phase, bool(recovery_due), hours)
    brief["load"] = load

    brief["next_actions"] = _next_actions(
        brief=brief,
        phase=phase,
        has_a_race=next_a is not None,
        recovery_due=bool(recovery_due),
    )
    return brief


def _next_actions(
    *, brief: dict[str, Any], phase: str, has_a_race: bool, recovery_due: bool
) -> list[str]:
    actions: list[str] = []
    today = brief["today"]
    if today["action"] == "ask_before_intensity":
        actions.append(
            "Ask how they slept and feel (or wait for the overnight sync); offer to log it "
            "with icu_update_wellness."
        )
    elif today["action"] in ("recovery_or_rest", "swap_hard_for_endurance"):
        actions.append(f"Tell them today's call first: {today['why']}.")
    if not has_a_race:
        actions.append(
            "No future RACE_A on the calendar: ask what they are training for. Until then "
            "coach general fitness; do not invent a season plan."
        )
    if phase == "recovery":
        actions.append(
            "Post-A recovery: 7-14 easy days, then review the race and set the next goal."
        )
    if phase == "taper":
        actions.append(
            "Taper: check the remaining days hold intensity and cut volume; no new stress."
        )
    if recovery_due:
        actions.append("Propose a recovery week next (see load.next_week_target).")
    if not today["planned"] and not today.get("already_done"):
        actions.append("Nothing planned today: offer a session that fits load.next_week_target.")
    actions.append(
        "Before writing events call icu_get_coaching_guide; propose a day-by-day table and "
        "wait for a yes."
    )
    return actions
