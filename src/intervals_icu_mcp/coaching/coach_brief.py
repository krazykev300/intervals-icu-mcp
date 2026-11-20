"""Deterministic coach brief for `icu_get_athlete_state` (no HTTP).

Applies the methodology tables to this athlete's numbers so every chat starts
from the same prescription: phase, intensity distribution, ramp tier, next
week's load target, today's call, and an ordered to-do list. The model
explains and schedules; it does not re-derive these numbers.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from typing import Any, cast

from ..models import ActivitySummary, Event
from .athlete_state_compute import parse_iso_date
from .methodology import (
    CTL_WEEK_GAIN_FACTOR,
    DISTRIBUTION_MODELS,
    HARD_SESSION_INTENSITY_FACTOR,
    KB_VERSION,
    POST_A_RECOVERY_LOAD_PCT,
    RAMP,
    RAMP_SELECTION,
    RECOVERY_WEEK_RATIO,
    RETURN_FROM_BREAK,
    TAPER_WEEK_LOAD_PCT,
    TSB_EXCURSION_THRESHOLD,
)

_TIERS = ("conservative", "standard", "aggressive")
_AWAY_CATEGORIES = ("HOLIDAY", "SICK", "INJURED")
_AWAY_WINDOW_DAYS = 14
_BREAK_CATEGORIES = ("SICK", "INJURED")
_RETURN_LOOKBACK_DAYS = 14
# A "Focus: ..." NOTE with no end date stops the A-race question for this long.
FOCUS_NOTE_DAYS = 120
FOCUS_PREFIX = "focus:"
MAX_TODAY_FLAGS = 2
_WEEKDAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
ENGINE_VERSION = "1.0.0"


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
    floors: dict[str, float] = DISTRIBUTION_MODELS["min_weekly_hours"]
    model = next((name for name, floor in floors.items() if hours >= floor), "threshold")
    shares = DISTRIBUTION_MODELS["shares"][model]
    result: dict[str, Any] = {
        "model": model,
        "time_share": {
            "z1_easy": shares["z1"],
            "z2_tempo_threshold": shares["z2"],
            "z3_vo2_plus": shares["z3"],
        },
        "based_on_median_weekly_hours": round(hours, 1),
    }
    if model == "polarized":
        result["alternative"] = "pyramidal if training is recreational rather than competitive"
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


def _event_span(event: Event) -> tuple[date, date]:
    start = parse_iso_date(event.start_date_local)
    end = parse_iso_date(event.end_date_local) if event.end_date_local else start
    # Intervals stores ranged events with an exclusive midnight end.
    if end > start and event.end_date_local and "T00:00" in event.end_date_local:
        end -= timedelta(days=1)
    return start, max(start, end)


def training_focus(events: list[Event], today: date) -> dict[str, Any] | None:
    """Active `Focus: ...` NOTE: the athlete's stated goal when there is no A-race."""
    best: dict[str, Any] | None = None
    for event in events:
        if event.category != "NOTE" or not event.name:
            continue
        if not event.name.strip().lower().startswith(FOCUS_PREFIX):
            continue
        start = parse_iso_date(event.start_date_local)
        if event.end_date_local:
            until = _event_span(event)[1]
        else:
            until = start + timedelta(days=FOCUS_NOTE_DAYS)
        if not start <= today <= until:
            continue
        item = {"id": event.id, "name": event.name.strip(), "since": start.isoformat()}
        item["review_by"] = until.isoformat()
        if best is None or item["since"] > best["since"]:
            best = item
    return best


def away_days(events: list[Event], today: date) -> list[dict[str, Any]]:
    """HOLIDAY / SICK / INJURED events overlapping the next two weeks."""
    horizon = today + timedelta(days=_AWAY_WINDOW_DAYS)
    items: list[dict[str, Any]] = []
    for event in events:
        if event.category not in _AWAY_CATEGORIES:
            continue
        start, end = _event_span(event)
        if end < today or start > horizon:
            continue
        item: dict[str, Any] = {
            "category": event.category,
            "name": event.name,
            "start": start.isoformat(),
            "end": end.isoformat(),
        }
        if event.training_availability:
            item["training_availability"] = event.training_availability
        if event.max_training_time is not None:
            item["max_training_seconds"] = event.max_training_time
        if event.can_train_sports:
            item["can_train_sports"] = event.can_train_sports
        items.append(item)
    items.sort(key=lambda i: i["start"])
    return items


def recent_break(
    events: list[Event], weeks: list[dict[str, Any]], today: date
) -> dict[str, Any] | None:
    """Latest SICK / INJURED window that ended in the last two weeks, with its return rule.

    Days missed pick the rule in RETURN_FROM_BREAK. The rebuild lasts one week
    per week missed (rounded up) and climbs linearly from the first-week share
    back to 100% of the last full week before the break.
    """
    latest: tuple[date, date, Event] | None = None
    for event in events:
        if event.category not in _BREAK_CATEGORIES:
            continue
        start, end = _event_span(event)
        if not 1 <= (today - end).days <= _RETURN_LOOKBACK_DAYS:
            continue
        if latest is None or end > latest[1]:
            latest = (start, end, event)
    if latest is None:
        return None
    start, end, event = latest
    days_missed = (end - start).days + 1
    item: dict[str, Any] = {
        "category": event.category,
        "name": event.name,
        "start": start.isoformat(),
        "end": end.isoformat(),
        "days_missed": days_missed,
        "days_since_end": (today - end).days,
    }
    if days_missed <= RETURN_FROM_BREAK["resume_plan_days_missed_max"]:
        item["rule"] = "resume_plan"
        item["in_rebuild"] = False
        return item
    tier = "short" if days_missed <= RETURN_FROM_BREAK["short"]["days_missed_max"] else "long"
    rule = RETURN_FROM_BREAK[tier]
    rebuild_weeks = -(-days_missed // 7)
    week_index = (today - end - timedelta(days=1)).days // 7
    first_pct = rule["first_week_load_pct"]
    item.update(
        {
            "rule": tier,
            "first_week_load_pct": first_pct,
            "easy_days_first": rule["easy_days_first"],
            "rebuild_weeks": rebuild_weeks,
            "rebuild_until": (end + timedelta(days=7 * rebuild_weeks)).isoformat(),
            "in_rebuild": week_index < rebuild_weeks,
        }
    )
    before = [w for w in weeks if date.fromisoformat(w["week_start"]) + timedelta(days=7) <= start]
    if before and item["in_rebuild"]:
        item["pre_break_week_load"] = before[-1]["load"]
        item["this_rebuild_week"] = week_index + 1
        item["this_week_load_pct"] = round(
            first_pct + (100 - first_pct) * week_index / rebuild_weeks
        )
    return item


def today_flags(
    *,
    brief: dict[str, Any],
    ftp_check: dict[str, Any] | None,
    gaps: list[dict[str, str]] | None,
) -> dict[str, list[str]]:
    """Rank flags for a daily answer: the top two go in `flags`, the rest wait.

    Order: things that change this week's plan first, then settings that skew
    load numbers, then logging gaps.
    """
    ranked: list[str] = []
    phase: dict[str, Any] = brief.get("phase", {})
    races: list[dict[str, Any]] = phase.get("b_c_races_within_14d", [])
    for race in races:
        ranked.append(
            f"{race['category']} {race['name']} in {race['days_out']} days ({race['date']})."
        )
    load: dict[str, Any] = brief.get("load", {})
    target: dict[str, Any] = load.get("next_week_target") or {}
    if load.get("recovery_week_due") and target:
        low, high = target["range"]
        ranked.append(f"Recovery week due next week: about {target['load']} load ({low}-{high}).")
    if target.get("warning"):
        ranked.append(f"Next week's target is {target['warning']}.")
    if ftp_check and ftp_check.get("verdict") in ("raise", "lower"):
        looks = "low" if ftp_check["verdict"] == "raise" else "high"
        ranked.append(
            f"FTP setting {ftp_check['setting']} W looks {looks}: "
            f"estimate {ftp_check['estimate']} W ({ftp_check['estimate_source']}); zones and "
            "load are computed from the setting."
        )
    for gap in gaps or []:
        if gap.get("field") == "readiness.subjective":
            ranked.append(
                "How-you-feel wellness fields are empty: offer to log them after the session."
            )
    result = {"flags": ranked[:MAX_TODAY_FLAGS]}
    if ranked[MAX_TODAY_FLAGS:]:
        result["flags_more"] = ranked[MAX_TODAY_FLAGS:]
    return result


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
    focus = None if next_a else training_focus(events, today)
    if focus:
        brief["phase"]["focus"] = focus
    away = away_days(events, today)
    if away:
        brief["away"] = away

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
    returning = recent_break(events, weeks, today)
    if returning:
        brief["returning"] = returning
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
    if returning and "this_week_load_pct" in returning:
        pct = returning["this_week_load_pct"]
        target = round(returning["pre_break_week_load"] * pct / 100)
        basis = (
            f"return from {returning['category'].lower()} ({returning['days_missed']} days "
            f"missed): rebuild week {returning['this_rebuild_week']} of "
            f"{returning['rebuild_weeks']}, {pct}% of the last full week before the break, "
            f"{returning['easy_days_first']} easy days first"
        )
    elif phase == "recovery" and reference is not None:
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
        recovery_due=bool(recovery_due),
    )
    follow_ups = _follow_ups(has_a_race=next_a is not None, focus=focus)
    if follow_ups:
        brief["follow_ups"] = follow_ups
    brief["provenance"] = _brief_provenance(
        brief=brief,
        phase_context=phase_context,
        current_fitness=current_fitness,
        tolerance=tolerance,
        constraints=constraints,
        readiness_state=readiness_state,
    )
    return brief


def _brief_provenance(
    *,
    brief: dict[str, Any],
    phase_context: dict[str, Any],
    current_fitness: dict[str, Any],
    tolerance: dict[str, Any],
    constraints: dict[str, Any],
    readiness_state: str | None,
) -> dict[str, Any]:
    """Trace each numeric brief subtree to Intervals fields or a versioned rule.

    A provenance path covers that value and all descendants. This keeps the
    brief readable while making every number reproducible without wrapping
    each scalar in a value/source envelope.
    """
    values: dict[str, dict[str, Any]] = {
        "today": {
            "kind": "computed",
            "rule_id": "today_action.v1",
            "inputs": [
                "events.start_date_local",
                "events.icu_intensity",
                "activities.start_date_local",
                "wellness.readiness_state",
                "wellness.tsb",
            ],
        },
        "phase": {
            "kind": "computed",
            "rule_id": "phase_context.v1",
            "inputs": [
                "events.category",
                "events.start_date_local",
                "events.end_date_local",
                "methodology.phase_from_a_race",
            ],
            "source": phase_context.get("source", "unspecified"),
        },
        "load": {
            "kind": "computed",
            "rule_id": "weekly_load_target.v1",
            "inputs": [
                "activities.icu_training_load",
                "activities.start_date_local",
                "wellness.ctl",
                "wellness.tsb_history",
                "methodology.ramp",
                "methodology.taper",
            ],
        },
    }
    if "away" in brief:
        values["away"] = {
            "kind": "intervals_field",
            "inputs": [
                "events.start_date_local",
                "events.end_date_local",
                "events.max_training_time",
            ],
        }
    if "returning" in brief:
        values["returning"] = {
            "kind": "computed",
            "rule_id": "return_from_break.v1",
            "inputs": [
                "events.start_date_local",
                "events.end_date_local",
                "activities.icu_training_load",
                "methodology.return_from_break",
            ],
        }
    if "intensity_distribution" in brief:
        values["intensity_distribution"] = {
            "kind": "computed",
            "rule_id": "distribution_by_observed_hours.v1",
            "inputs": [
                "activities.moving_time",
                "methodology.distribution_models",
            ],
        }

    missing: list[str] = []
    if phase_context.get("source") in (None, "unspecified"):
        missing.append("calendar.RACE_A_or_PLAN")
    if current_fitness.get("ctl") is None:
        missing.append("wellness.ctl")
    if current_fitness.get("tsb") is None:
        missing.append("wellness.tsb")
    if not tolerance:
        missing.append("wellness.tsb_history")
    hours_block = constraints.get("typical_weekly_hours")
    if not isinstance(hours_block, dict) or cast(dict[str, Any], hours_block).get("median") is None:
        missing.append("activities.moving_time")
    load_block = brief.get("load")
    if not isinstance(load_block, dict) or not cast(dict[str, Any], load_block).get(
        "last_completed_weeks"
    ):
        missing.append("activities.icu_training_load")
    if readiness_state is None:
        missing.append("wellness.hrv_or_sleep_today")

    return {
        "engine_version": ENGINE_VERSION,
        "kb_version": KB_VERSION,
        "values": values,
        "missing_inputs": sorted(missing),
    }


def _next_actions(*, brief: dict[str, Any], phase: str, recovery_due: bool) -> list[str]:
    """Do-now list. Calendar work comes before profile questions (see `_follow_ups`)."""
    actions: list[str] = []
    today = brief["today"]
    if today["action"] == "ask_before_intensity":
        actions.append(
            "Ask how they slept and feel (or wait for the overnight sync); offer to log it "
            "with icu_update_wellness."
        )
    elif today["action"] in ("recovery_or_rest", "swap_hard_for_endurance"):
        actions.append(f"Tell them today's call first: {today['why']}.")
    if not today["planned"] and not today.get("already_done"):
        actions.append(
            "Nothing planned today: propose one session that fits load.next_week_target "
            "and offer to add it to the Intervals calendar. That offer is this turn's question."
        )
    if phase == "recovery":
        actions.append(
            "Post-A recovery: 7-14 easy days, then review the race and set the next goal."
        )
    if phase == "taper":
        actions.append(
            "Taper: check the remaining days hold intensity and cut volume; no new stress."
        )
    returning = brief.get("returning")
    if returning and returning.get("in_rebuild"):
        actions.append(
            f"Back from {returning['category'].lower()} ({returning['end']}): check the return "
            "week is on the calendar before planning anything harder; offer to write it if not."
        )
    if recovery_due:
        actions.append(
            "Propose next week as a recovery week now (day-by-day table inside "
            "load.next_week_target) and offer to add it to the calendar."
        )
    actions.append(
        "Before writing events call icu_get_coaching_guide. On a yes, write in the same "
        "turn, confirm what is now on the calendar, then ask the first of follow_ups."
    )
    return actions


def _follow_ups(*, has_a_race: bool, focus: dict[str, Any] | None) -> list[str]:
    """Questions to ask after the calendar offer is answered, one per turn."""
    items: list[str] = []
    if not has_a_race and not focus:
        items.append(
            "No future RACE_A and no Focus note: ask what they are training for (a "
            "placeholder date is fine). If there is no race, offer a NOTE named 'Focus: "
            "<their answer>' from today to a review date 8-12 weeks out so this question "
            "is not asked again. Until then coach general fitness; do not invent a season plan."
        )
    return items
