"""Pure derived metrics for `icu_get_athlete_state` (no HTTP)."""

from __future__ import annotations

import statistics
from collections import defaultdict
from datetime import date, datetime, timedelta
from typing import Any

from .methodology import (
    PHASE_FROM_A_RACE,
    READINESS_THRESHOLDS,
    TSB_EXCURSION_THRESHOLD,
    TSB_RECOVERED_THRESHOLD,
)
from .models import ActivitySummary, CurveData, Event, SportSettings, Wellness

RACE_CATEGORIES = frozenset({"RACE_A", "RACE_B", "RACE_C"})
KEY_POWER_DURATIONS: tuple[tuple[int, str], ...] = (
    (5, "5s"),
    (60, "1m"),
    (300, "5m"),
    (1200, "20m"),
    (3600, "60m"),
)
DURABILITY_BINS_KJ = (0, 1000, 2000, 3000)
DURABILITY_WINDOWS_S = (300, 1200)
INTENSITY_BINS = (
    ("recovery", 0.0, 0.75),
    ("endurance", 0.75, 0.85),
    ("threshold", 0.85, 0.95),
    ("vo2", 0.95, 10.0),
)
SUBJECTIVE_FIELDS = ("mood", "motivation", "fatigue", "soreness", "stress")


def parse_iso_date(value: str | date | datetime) -> date:
    """Parse an Intervals date or datetime string to a date."""
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return datetime.fromisoformat(value.replace("Z", "+00:00")).date()


def _median(values: list[float]) -> float | None:
    if not values:
        return None
    return round(float(statistics.median(values)), 1)


def _mean(values: list[float]) -> float | None:
    if not values:
        return None
    return float(statistics.fmean(values))


def _stdev(values: list[float]) -> float | None:
    if len(values) < 2:
        return None
    return float(statistics.pstdev(values))


def _z_score(today: float | None, mean: float | None, sd: float | None) -> float | None:
    if today is None or mean is None:
        return None
    if sd is None or sd == 0:
        return 0.0
    return round((today - mean) / sd, 2)


def fitness_points(records: list[Wellness], today: date) -> list[dict[str, Any]]:
    """Daily CTL/ATL/TSB points, oldest first, skipping days with no fitness."""
    points: list[dict[str, Any]] = []
    for record in records:
        if record.ctl is None and record.atl is None:
            continue
        tsb = record.tsb
        if tsb is None and record.ctl is not None and record.atl is not None:
            tsb = record.ctl - record.atl
        point: dict[str, Any] = {"date": record.id}
        if record.ctl is not None:
            point["ctl"] = round(record.ctl, 1)
        if record.atl is not None:
            point["atl"] = round(record.atl, 1)
        if tsb is not None:
            point["tsb"] = round(tsb, 1)
        if record.ramp_rate is not None:
            point["ramp_rate"] = round(record.ramp_rate, 1)
        record_date = parse_iso_date(record.id)
        if record_date > today:
            point["is_projected"] = True
        points.append(point)
    points.sort(key=lambda p: p["date"])
    return points


def weekly_fitness_series(daily: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """One point per ISO week — last daily observation in that week."""
    by_week: dict[tuple[int, int], dict[str, Any]] = {}
    for point in daily:
        if point.get("is_projected"):
            continue
        week = parse_iso_date(point["date"]).isocalendar()
        by_week[(week.year, week.week)] = point
    series: list[dict[str, Any]] = []
    for year, week in sorted(by_week):
        point = by_week[(year, week)]
        item: dict[str, Any] = {
            "week_start": date.fromisocalendar(year, week, 1).isoformat(),
        }
        for key in ("ctl", "atl", "tsb", "ramp_rate"):
            if key in point:
                item[key] = point[key]
        series.append(item)
    return series


def ctl_trend(daily: list[dict[str, Any]], today: date) -> dict[str, float]:
    """CTL today minus CTL N days ago for 30/90/180."""
    by_date: dict[date, float] = {}
    for point in daily:
        if "ctl" not in point or point.get("is_projected"):
            continue
        by_date[parse_iso_date(point["date"])] = float(point["ctl"])
    if today not in by_date:
        past = [d for d in by_date if d <= today]
        if not past:
            return {}
        today = max(past)
    current = by_date[today]
    trend: dict[str, float] = {}
    for days, key in ((30, "d30"), (90, "d90"), (180, "d180")):
        target = today - timedelta(days=days)
        prior = _nearest_on_or_before(by_date, target)
        if prior is not None:
            trend[key] = round(current - prior, 1)
    return trend


def _nearest_on_or_before(by_date: dict[date, float], target: date) -> float | None:
    eligible = [d for d in by_date if d <= target]
    if not eligible:
        return None
    return by_date[max(eligible)]


def trailing_weekly_ramps(weekly: list[dict[str, Any]], n: int = 4) -> list[float]:
    """CTL deltas between consecutive weekly points, newest last, length <= n."""
    with_ctl = [w for w in weekly if "ctl" in w]
    if len(with_ctl) < 2:
        return []
    deltas = [
        round(float(with_ctl[i]["ctl"]) - float(with_ctl[i - 1]["ctl"]), 1)
        for i in range(1, len(with_ctl))
    ]
    return deltas[-n:]


def tsb_tolerance(daily: list[dict[str, Any]]) -> dict[str, Any]:
    """Empirical TSB depth: min, days below -25, median days to recover to -10."""
    dated: list[tuple[date, float]] = []
    for point in daily:
        if "tsb" not in point or point.get("is_projected"):
            continue
        dated.append((parse_iso_date(point["date"]), float(point["tsb"])))
    dated.sort(key=lambda item: item[0])
    if not dated:
        return {}

    result: dict[str, Any] = {
        "min_observed": round(min(t for _, t in dated), 1),
    }
    recoveries: list[float] = []
    excursion_count = 0
    i = 0
    while i < len(dated):
        _day, tsb = dated[i]
        if tsb < TSB_EXCURSION_THRESHOLD:
            excursion_count += 1
            start = dated[i][0]
            while i < len(dated) and dated[i][1] < TSB_EXCURSION_THRESHOLD:
                i += 1
            recovered_days: int | None = None
            for later_day, later_tsb in dated[i:]:
                if later_tsb >= TSB_RECOVERED_THRESHOLD:
                    recovered_days = (later_day - start).days
                    break
            if recovered_days is not None:
                recoveries.append(float(recovered_days))
        else:
            i += 1
    result["excursions_below_-25"] = excursion_count
    median_recover = _median(recoveries)
    if median_recover is not None:
        result["median_days_to_recover"] = median_recover
    return result


def current_fitness(daily: list[dict[str, Any]], today: date) -> dict[str, Any]:
    """Today's CTL/ATL/TSB point, or the latest on-or-before today."""
    eligible = [
        p for p in daily if not p.get("is_projected") and parse_iso_date(p["date"]) <= today
    ]
    if not eligible:
        return {}
    today_str = today.isoformat()
    match = next((p for p in eligible if p["date"] == today_str), eligible[-1])
    current = {k: v for k, v in match.items() if k != "is_projected"}
    return current


def derive_phase_context(
    events: list[Event],
    today: date,
) -> dict[str, Any]:
    """ATP PLAN covering today, else nearest RACE_A, else unspecified."""
    atp = _phase_from_atp(events, today)
    if atp is not None:
        return atp
    race = _nearest_race_a(events, today)
    if race is None:
        return {"current_phase": None, "source": "unspecified"}
    race_date = parse_iso_date(race.start_date_local)
    days_out = (race_date - today).days
    phase = _phase_from_days_out(days_out)
    context: dict[str, Any] = {
        "current_phase": phase,
        "source": "derived_from_race",
        "anchor_event_id": race.id,
        "next_transition": race_date.isoformat(),
    }
    return context


def _phase_from_days_out(days_out: int) -> str:
    if days_out < 0:
        after = -days_out
        if after <= PHASE_FROM_A_RACE["recovery_post_a"]["days_after_a_max"]:
            return "recovery"
        return "unspecified"
    if days_out <= PHASE_FROM_A_RACE["taper"]["days_out_max"]:
        return "taper"
    if days_out <= PHASE_FROM_A_RACE["peak"]["days_out_max"]:
        return "peak"
    if days_out <= PHASE_FROM_A_RACE["build"]["days_out_max"]:
        return "build"
    return "base"


def _phase_from_atp(events: list[Event], today: date) -> dict[str, Any] | None:
    covering: list[tuple[date, Event]] = []
    for event in events:
        if event.category != "PLAN":
            continue
        start = parse_iso_date(event.start_date_local)
        end_raw = event.end_date_local or event.start_date_local
        end = parse_iso_date(end_raw)
        if start <= today <= end:
            covering.append((start, event))
    if not covering:
        return None
    _, event = max(covering, key=lambda item: item[0])
    phase = event.tags[0] if event.tags else None
    context: dict[str, Any] = {
        "current_phase": phase.lower() if isinstance(phase, str) else None,
        "source": "atp",
        "anchor_event_id": event.id,
        "phase_start": parse_iso_date(event.start_date_local).isoformat(),
    }
    if event.end_date_local:
        context["next_transition"] = parse_iso_date(event.end_date_local).isoformat()
    return context


def _nearest_race_a(events: list[Event], today: date) -> Event | None:
    races = [e for e in events if e.category == "RACE_A"]
    if not races:
        return None

    def sort_key(event: Event) -> tuple[int, int]:
        delta = (parse_iso_date(event.start_date_local) - today).days
        # Prefer the next future A-race; otherwise the most recent past one.
        return (0 if delta >= 0 else 1, abs(delta))

    return min(races, key=sort_key)


def calendar_block(events: list[Event], today: date, horizon_days: int) -> dict[str, Any]:
    """Lean forward calendar: races plus a handful of upcoming workouts."""
    newest = today + timedelta(days=horizon_days)
    dated_events = sorted(events, key=lambda e: parse_iso_date(e.start_date_local))
    upcoming: list[dict[str, Any]] = []
    races: list[dict[str, Any]] = []
    for event in dated_events:
        event_date = parse_iso_date(event.start_date_local)
        if event_date < today or event_date > newest:
            continue
        days_out = (event_date - today).days
        if event.category in RACE_CATEGORIES:
            item: dict[str, Any] = {
                "id": event.id,
                "date": event_date.isoformat(),
                "name": event.name,
                "category": event.category,
                "days_out": days_out,
            }
            if event.type:
                item["type"] = event.type
            if event.moving_time:
                item["duration_s"] = event.moving_time
            if event.icu_training_load:
                item["planned_load"] = event.icu_training_load
            races.append(item)
        elif event.category == "WORKOUT" and len(upcoming) < 14:
            workout: dict[str, Any] = {
                "id": event.id,
                "date": event_date.isoformat(),
                "name": event.name,
                "days_out": days_out,
            }
            if event.type:
                workout["type"] = event.type
            if event.icu_training_load:
                workout["planned_load"] = event.icu_training_load
            if event.icu_intensity is not None:
                workout["intensity_factor"] = round(event.icu_intensity, 2)
            upcoming.append(workout)

    races.sort(key=lambda r: r["date"])
    upcoming.sort(key=lambda w: w["date"])
    return {"events": upcoming, "goal_events": races}


def power_keys(curves: list[CurveData]) -> dict[str, dict[str, int]]:
    """Key-duration watts keyed by curve window (d42 / d90 / d365)."""
    result: dict[str, dict[str, int]] = {}
    for curve in curves:
        label = _curve_label(curve)
        keys: dict[str, int] = {}
        for target, name in KEY_POWER_DURATIONS:
            value = _value_at_duration(curve.secs, curve.values, target)
            if value is not None:
                keys[name] = value
        if keys:
            result[label] = keys
    return result


def _curve_label(curve: CurveData) -> str:
    if curve.days is not None:
        return f"d{curve.days}"
    if curve.start_date_local and curve.end_date_local:
        start = parse_iso_date(curve.start_date_local)
        end = parse_iso_date(curve.end_date_local)
        return f"d{(end - start).days}"
    return "unknown"


def _value_at_duration(secs: list[int], values: list[int], target: int) -> int | None:
    if not secs or not values:
        return None
    best_idx = min(range(len(secs)), key=lambda i: abs(secs[i] - target))
    if abs(secs[best_idx] - target) <= target * 0.1:
        return values[best_idx]
    return None


def ftp_from_settings(settings: list[SportSettings]) -> dict[str, Any]:
    """Configured Ride FTP (outdoor), not a curve estimate."""
    ride = next((s for s in settings if s.type == "Ride" and s.ftp), None)
    if ride is None:
        ride = next((s for s in settings if s.ftp), None)
    if ride is None or ride.ftp is None:
        return {}
    return {"estimated_ftp": ride.ftp, "ftp_source": "sport_settings"}


def sport_constraints(settings: list[SportSettings]) -> dict[str, Any]:
    sports: list[str] = []
    sport_settings: dict[str, Any] = {}
    for entry in settings:
        if not entry.type:
            continue
        sports.append(entry.type)
        block: dict[str, Any] = {}
        if entry.ftp is not None:
            block["ftp"] = entry.ftp
        if entry.fthr is not None:
            block["lthr"] = entry.fthr
        if entry.pace_threshold is not None:
            block["threshold_pace"] = entry.pace_threshold
        if block:
            sport_settings[entry.type] = block
    result: dict[str, Any] = {}
    if sports:
        result["sports"] = sports
    if sport_settings:
        result["sport_settings"] = sport_settings
    return result


def observed_constraints(activities: list[ActivitySummary], lookback_days: int) -> dict[str, Any]:
    """Weekly hours/load and max day load from completed activities."""
    if not activities:
        return {}
    by_week_hours: dict[tuple[int, int], float] = defaultdict(float)
    by_week_load: dict[tuple[int, int], float] = defaultdict(float)
    by_day_load: dict[date, float] = defaultdict(float)
    sport_counts: dict[str, int] = defaultdict(int)
    for activity in activities:
        day = parse_iso_date(activity.start_date_local)
        iso = day.isocalendar()
        key = (iso.year, iso.week)
        if activity.moving_time:
            by_week_hours[key] += activity.moving_time / 3600.0
        load = float(activity.icu_training_load or 0)
        by_week_load[key] += load
        by_day_load[day] += load
        if activity.type:
            sport_counts[activity.type] += 1
    hours = [round(v, 2) for v in by_week_hours.values() if v > 0]
    loads = [v for v in by_week_load.values() if v > 0]
    result: dict[str, Any] = {"lookback_days": lookback_days}
    if hours:
        result["typical_weekly_hours"] = {
            "min": round(min(hours), 1),
            "max": round(max(hours), 1),
            "median": _median(hours),
        }
    if loads:
        result["typical_weekly_load"] = {
            "median": _median(loads),
            "p90": round(float(statistics.quantiles(loads, n=10)[8]), 1)
            if len(loads) >= 10
            else round(max(loads), 1),
        }
    if by_day_load:
        result["max_single_day_load_observed"] = round(max(by_day_load.values()), 1)
    if len(sport_counts) > 1:
        result["mixed_sport"] = True
    return result


def _iso_week_start(day: date) -> date:
    return date.fromisocalendar(day.isocalendar().year, day.isocalendar().week, 1)


def _intensity_bin(factor: float | None) -> str | None:
    if factor is None:
        return None
    for name, low, high in INTENSITY_BINS:
        if low <= factor < high:
            return name
    return None


def compliance_block(
    events: list[Event],
    activities: list[ActivitySummary],
    today: date,
    lookback_days: int,
) -> dict[str, Any]:
    """Weekly planned vs actual load and intensity-factor completion rates."""
    oldest = today - timedelta(days=lookback_days)
    planned_by_week: dict[date, dict[str, float]] = defaultdict(
        lambda: {"planned_load": 0.0, "sessions_planned": 0.0}
    )
    actual_by_week: dict[date, dict[str, float]] = defaultdict(
        lambda: {"actual_load": 0.0, "sessions_completed": 0.0}
    )
    activity_dates = {parse_iso_date(a.start_date_local) for a in activities}
    by_bin: dict[str, dict[str, list[float]]] = defaultdict(
        lambda: {"completion": [], "load_ratio": []}
    )

    for event in events:
        if event.category != "WORKOUT":
            continue
        event_date = parse_iso_date(event.start_date_local)
        if event_date < oldest or event_date > today:
            continue
        week = _iso_week_start(event_date)
        planned_by_week[week]["planned_load"] += float(event.icu_training_load or 0)
        planned_by_week[week]["sessions_planned"] += 1
        completed = event_date in activity_dates
        if completed:
            planned_by_week[week]["matched"] = planned_by_week[week].get("matched", 0) + 1
        intensity_name = _intensity_bin(event.icu_intensity)
        if intensity_name:
            by_bin[intensity_name]["completion"].append(1.0 if completed else 0.0)

    for activity in activities:
        day = parse_iso_date(activity.start_date_local)
        if day < oldest or day > today:
            continue
        week = _iso_week_start(day)
        actual_by_week[week]["actual_load"] += float(activity.icu_training_load or 0)
        actual_by_week[week]["sessions_completed"] += 1
        intensity_name = _intensity_bin(activity.icu_intensity)
        if intensity_name and activity.icu_training_load:
            by_bin[intensity_name]["load_ratio"].append(float(activity.icu_training_load))

    weeks: list[dict[str, Any]] = []
    all_weeks = sorted(set(planned_by_week) | set(actual_by_week))
    for week in all_weeks:
        planned = planned_by_week[week]["planned_load"]
        actual = actual_by_week[week]["actual_load"]
        item: dict[str, Any] = {
            "week_start": week.isoformat(),
            "planned_load": round(planned, 1),
            "actual_load": round(actual, 1),
            "sessions_planned": int(planned_by_week[week]["sessions_planned"]),
            "sessions_completed": int(planned_by_week[week].get("matched", 0)),
        }
        if planned > 0:
            item["ratio"] = round(actual / planned, 2)
        weeks.append(item)

    by_session_type: dict[str, dict[str, float]] = {}
    for name, _low, _high in INTENSITY_BINS:
        completion = by_bin[name]["completion"]
        if not completion:
            continue
        entry: dict[str, float] = {
            "completion_rate": round(sum(completion) / len(completion), 2),
        }
        by_session_type[name] = entry

    flags: list[str] = []
    ratios = [float(w["ratio"]) for w in weeks if "ratio" in w]
    mean_ratio = _mean(ratios)
    if mean_ratio is not None and mean_ratio > 1.15:
        flags.append("actual_load_averages_above_planned")

    result: dict[str, Any] = {"weekly": weeks}
    if by_session_type:
        result["by_session_type"] = by_session_type
    if flags:
        result["pattern_flags"] = flags
    return result


def readiness_block(records: list[Wellness], today: date) -> dict[str, Any]:
    """HRV / RHR / sleep vs 60d baseline and a green|amber|red state."""
    by_date = {parse_iso_date(r.id): r for r in records if parse_iso_date(r.id) <= today}
    if not by_date:
        return {}
    latest_day = max(by_date)
    latest = by_date[latest_day]
    window_start = today - timedelta(days=60)
    baseline_records = [r for d, r in by_date.items() if window_start <= d <= today]

    hrv_values = [float(r.hrv) for r in baseline_records if r.hrv is not None]
    rhr_values = [float(r.resting_hr) for r in baseline_records if r.resting_hr is not None]
    sleep_h = [r.sleep_secs / 3600.0 for r in baseline_records if r.sleep_secs and r.sleep_secs > 0]

    hrv_mean = _mean(hrv_values)
    hrv_sd = _stdev(hrv_values)
    rhr_mean = _mean(rhr_values)
    rhr_sd = _stdev(rhr_values)
    sleep_mean = _mean(sleep_h)

    today_hrv = float(latest.hrv) if latest.hrv is not None else None
    today_rhr = float(latest.resting_hr) if latest.resting_hr is not None else None
    last_night_h = (latest.sleep_secs / 3600.0) if latest.sleep_secs else None
    hrv_z = _z_score(today_hrv, hrv_mean, hrv_sd)
    rhr_z = _z_score(today_rhr, rhr_mean, rhr_sd)

    last7 = [d for d in sorted(by_date) if today - timedelta(days=6) <= d <= today]
    sleep_7: list[float] = []
    for day in last7:
        secs = by_date[day].sleep_secs
        if secs is not None and secs > 0:
            sleep_7.append(secs / 3600.0)

    consecutive_low = _consecutive_hrv_below(by_date, today, hrv_mean)
    consecutive_high_rhr = _consecutive_rhr_above(by_date, today, rhr_mean)
    hrv_trend = _hrv_trend(by_date, today)

    sleep_debt = None
    if last_night_h is not None and sleep_mean is not None:
        sleep_debt = round(sleep_mean - last_night_h, 2)

    block: dict[str, Any] = {}
    if today_hrv is not None or hrv_mean is not None:
        hrv: dict[str, Any] = {}
        if today_hrv is not None:
            hrv["today"] = round(today_hrv, 1)
        if hrv_mean is not None:
            hrv["baseline_60d_mean"] = round(hrv_mean, 1)
        if hrv_sd is not None:
            hrv["baseline_60d_sd"] = round(hrv_sd, 1)
        if hrv_z is not None:
            hrv["z_score"] = hrv_z
        hrv["consecutive_days_below_baseline"] = consecutive_low
        hrv["trend_7d"] = hrv_trend
        block["hrv"] = hrv
    if today_rhr is not None or rhr_mean is not None:
        rhr: dict[str, Any] = {}
        if today_rhr is not None:
            rhr["today"] = round(today_rhr, 0)
        if rhr_mean is not None:
            rhr["baseline_60d_mean"] = round(rhr_mean, 0)
        if rhr_z is not None:
            rhr["z_score"] = rhr_z
        rhr["consecutive_days_above_baseline"] = consecutive_high_rhr
        block["rhr"] = rhr
    if last_night_h is not None or sleep_mean is not None:
        sleep: dict[str, Any] = {}
        if last_night_h is not None:
            sleep["last_night_h"] = round(last_night_h, 2)
        if sleep_7:
            sleep["trailing_7d_mean_h"] = round(sum(sleep_7) / len(sleep_7), 2)
        if sleep_debt is not None:
            sleep["debt_vs_baseline_h"] = sleep_debt
        block["sleep"] = sleep

    subjective: dict[str, Any] = {}
    for field in SUBJECTIVE_FIELDS:
        value = getattr(latest, field, None)
        if value is not None:
            subjective[field] = value
    block["subjective"] = subjective if subjective else None

    state, rationale = _readiness_state(
        hrv_z=hrv_z,
        rhr_z=rhr_z,
        sleep_debt_h=sleep_debt,
        consecutive_hrv_low=consecutive_low,
    )
    if state:
        block["readiness_state"] = state
        block["state_rationale"] = rationale
    return block


def _consecutive_hrv_below(
    by_date: dict[date, Wellness], today: date, baseline: float | None
) -> int:
    if baseline is None:
        return 0
    count = 0
    day = today
    while day in by_date:
        hrv = by_date[day].hrv
        if hrv is None or hrv >= baseline:
            break
        count += 1
        day -= timedelta(days=1)
    return count


def _consecutive_rhr_above(
    by_date: dict[date, Wellness], today: date, baseline: float | None
) -> int:
    if baseline is None:
        return 0
    count = 0
    day = today
    while day in by_date:
        rhr = by_date[day].resting_hr
        if rhr is None or rhr <= baseline:
            break
        count += 1
        day -= timedelta(days=1)
    return count


def _hrv_trend(by_date: dict[date, Wellness], today: date) -> str:
    window = [d for d in sorted(by_date) if today - timedelta(days=6) <= d <= today]
    values: list[float] = []
    for day in window:
        hrv = by_date[day].hrv
        if hrv is not None:
            values.append(float(hrv))
    if len(values) < 3:
        return "stable"
    first = statistics.fmean(values[: max(1, len(values) // 3)])
    last = statistics.fmean(values[-max(1, len(values) // 3) :])
    if last - first > 1.0:
        return "rising"
    if first - last > 1.0:
        return "falling"
    return "stable"


def _readiness_state(
    *,
    hrv_z: float | None,
    rhr_z: float | None,
    sleep_debt_h: float | None,
    consecutive_hrv_low: int,
) -> tuple[str | None, str]:
    thresholds = READINESS_THRESHOLDS
    red = thresholds["red"]
    green = thresholds["green"]
    if hrv_z is None and rhr_z is None and sleep_debt_h is None:
        return None, "insufficient wellness signals"
    if (
        (hrv_z is not None and hrv_z < red["hrv_z_below"])
        or consecutive_hrv_low >= red["consecutive_days_below_baseline"]
        or (rhr_z is not None and rhr_z > red["rhr_z_above"])
    ):
        return "red", "HRV and/or RHR outside red thresholds, or 3+ low-HRV days"
    amber = False
    if hrv_z is not None and green["hrv_z_min"] > hrv_z >= red["hrv_z_below"]:
        amber = True
    if rhr_z is not None and green["rhr_z_max"] < rhr_z <= red["rhr_z_above"]:
        amber = True
    if sleep_debt_h is not None and sleep_debt_h >= green["sleep_debt_h_max"]:
        amber = True
    if amber:
        return "amber", "one of HRV z, RHR z, or sleep debt in the amber band"
    if (
        (hrv_z is None or hrv_z >= green["hrv_z_min"])
        and (rhr_z is None or rhr_z <= green["rhr_z_max"])
        and (sleep_debt_h is None or sleep_debt_h < green["sleep_debt_h_max"])
    ):
        return "green", "HRV, RHR, and sleep debt within green thresholds"
    return "amber", "mixed or partial signals"


def empty_subjective_days(records: list[Wellness], today: date, window: int = 14) -> int:
    """How many of the last `window` days have no subjective wellness fields."""
    by_date = {parse_iso_date(r.id): r for r in records}
    empty = 0
    for offset in range(window):
        day = today - timedelta(days=offset)
        record = by_date.get(day)
        if record is None:
            empty += 1
            continue
        if not any(getattr(record, field, None) is not None for field in SUBJECTIVE_FIELDS):
            empty += 1
    return empty


def derived_flags(
    *,
    ftp: int | None,
    power: dict[str, dict[str, int]],
    constraints: dict[str, Any],
    compliance: dict[str, Any] | None,
) -> list[str]:
    flags: list[str] = []
    hour = None
    for window in ("d365", "d90", "d42"):
        if window in power and "60m" in power[window]:
            hour = power[window]["60m"]
            break
    if ftp and hour and ftp > 0:
        gap_pct = round((ftp - hour) / ftp * 100, 1)
        if gap_pct >= 10:
            flags.append(
                f"60m_to_ftp_gap: {hour}w vs {ftp}w ({gap_pct}%) — limiter is "
                "time-at-threshold, not aerobic volume"
            )
    if constraints.get("mixed_sport"):
        flags.append("mixed_sport_weeks: Intervals combined TSS; do not reweight by sport")
    if compliance and "actual_load_averages_above_planned" in compliance.get("pattern_flags", []):
        flags.append("actual_load_averages_above_planned")
    return flags


def gaps(
    *,
    horizon_days: int,
    races: list[dict[str, Any]] | None,
    phase_source: str | None,
    subjective_empty_days: int | None,
    has_power: bool | None,
) -> list[dict[str, str]]:
    """ICU-only gaps. Missing ATP / fuelling / demands are not gaps."""
    items: list[dict[str, str]] = []
    year_out = horizon_days >= 365
    if races is not None and not any(r.get("category") == "RACE_A" for r in races):
        severity = "high" if year_out else "medium"
        items.append(
            {
                "field": "calendar.goal_events",
                "severity": severity,
                "message": f"No RACE_A on this calendar in the next {horizon_days} days.",
                "prompt": (
                    "Search goals MCP / Drive / GCal / chat for the A-date, then "
                    "icu_create_event (RACE_A + event_type). Do not draft a year "
                    "plan without an Intervals A-date."
                ),
            }
        )
    if phase_source == "unspecified" and year_out:
        items.append(
            {
                "field": "calendar.phase_context",
                "severity": "high",
                "message": "No RACE_A and no ATP PLAN covering today.",
                "prompt": (
                    "Confirm WHEN on this calendar (365d). Derive phase after an "
                    "A-date exists; do not require an ATP."
                ),
            }
        )
    if subjective_empty_days is not None and subjective_empty_days >= 14:
        items.append(
            {
                "field": "readiness.subjective",
                "severity": "medium",
                "message": (
                    f"Wellness subjective fields empty for {subjective_empty_days} of last 14 days."
                ),
                "prompt": "Log mood/motivation/fatigue/soreness/stress via icu_update_wellness.",
            }
        )
    if has_power is False:
        items.append(
            {
                "field": "power_profile",
                "severity": "medium",
                "message": "No power curve data in the requested windows.",
            }
        )
    return items


def durability_from_streams(
    samples_by_activity: list[list[float]],
) -> dict[str, Any]:
    """kJ-binned 5m/20m power from per-second watt traces."""
    best: dict[int, dict[int, float]] = {
        bin_kj: {window: 0.0 for window in DURABILITY_WINDOWS_S} for bin_kj in DURABILITY_BINS_KJ
    }
    for watts in samples_by_activity:
        series = [float(w) if w and w > 0 else 0.0 for w in watts]
        if len(series) < max(DURABILITY_WINDOWS_S):
            continue
        cumulative = 0.0
        kj_at: list[float] = []
        for watt in series:
            cumulative += watt / 1000.0
            kj_at.append(cumulative)
        for window in DURABILITY_WINDOWS_S:
            if len(series) < window:
                continue
            running = sum(series[:window])
            for start in range(0, len(series) - window + 1):
                if start:
                    running += series[start + window - 1] - series[start - 1]
                work_kj = kj_at[start]
                bin_kj = _kj_bin(work_kj)
                mean_w = running / window
                if mean_w > best[bin_kj][window]:
                    best[bin_kj][window] = mean_w

    curves_by_bin: dict[str, dict[str, int]] = {}
    for bin_kj in DURABILITY_BINS_KJ:
        entry: dict[str, int] = {}
        if best[bin_kj][300] > 0:
            entry["5m"] = round(best[bin_kj][300])
        if best[bin_kj][1200] > 0:
            entry["20m"] = round(best[bin_kj][1200])
        if entry:
            curves_by_bin[str(bin_kj)] = entry

    decay: dict[str, float] = {}
    fresh_5 = best[0][300]
    deep_5 = best[3000][300]
    if fresh_5 > 0 and deep_5 > 0:
        decay["5m"] = round((fresh_5 - deep_5) / fresh_5 / 3 * 100, 1)
    fresh_20 = best[0][1200]
    deep_20 = best[3000][1200]
    if fresh_20 > 0 and deep_20 > 0:
        decay["20m"] = round((fresh_20 - deep_20) / fresh_20 / 3 * 100, 1)

    result: dict[str, Any] = {
        "bins_kj": list(DURABILITY_BINS_KJ),
        "curves_by_bin": curves_by_bin,
    }
    if decay:
        result["decay_pct_per_1000kj"] = decay
    return result


def _kj_bin(work_kj: float) -> int:
    if work_kj >= 3000:
        return 3000
    if work_kj >= 2000:
        return 2000
    if work_kj >= 1000:
        return 1000
    return 0
