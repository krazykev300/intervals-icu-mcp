"""Data-quality sentinel for the athlete-state coaching brief."""

from __future__ import annotations

from collections import defaultdict
from typing import Any, cast

from ..models import ActivityStream, ActivitySummary, SportSettings, Wellness

_RIDE_TYPES = frozenset(
    {"Ride", "VirtualRide", "MountainBikeRide", "GravelRide", "EBikeRide", "EMountainBikeRide"}
)
_RUN_TYPES = frozenset({"Run", "VirtualRun", "TrailRun"})
_SWIM_TYPES = frozenset({"Swim", "OpenWaterSwim"})
_POWER_DROPOUT_SAMPLES = 120
_HR_DROPOUT_SAMPLES = 10


def is_strava_stub(activity: ActivitySummary) -> bool:
    """Whether an activity list row is a Strava-restricted empty stub."""
    if activity.source != "STRAVA":
        return False
    return not any(
        value is not None
        for value in (
            activity.distance,
            activity.moving_time,
            activity.elapsed_time,
            activity.total_elevation_gain,
            activity.average_watts,
            activity.normalized_power,
            activity.average_heartrate,
            activity.average_cadence,
            activity.average_speed,
        )
    )


def stream_sensor_issues(
    streams: list[ActivityStream],
    *,
    ftp: int | None,
    max_hr: int | None,
) -> list[str]:
    """Detect sustained missing samples and physiologically implausible spikes."""
    by_name = {(stream.type or stream.name): stream.data for stream in streams}
    issues: list[str] = []

    watts = _numeric_series(by_name.get("watts"))
    cadence = _numeric_series(by_name.get("cadence"))
    if watts:
        if _has_bounded_dropout(watts, cadence, _POWER_DROPOUT_SAMPLES):
            issues.append("power_dropout")
        power_ceiling = max(2500.0, float(ftp or 0) * 6)
        if max(watts) > power_ceiling:
            issues.append("power_spike")

    heartrate = _numeric_series(by_name.get("heartrate"))
    if heartrate:
        hr_reference = cadence if cadence else watts
        if _has_bounded_dropout(heartrate, hr_reference, _HR_DROPOUT_SAMPLES):
            issues.append("heart_rate_dropout")
        hr_ceiling = min(230.0, max(float(max_hr + 15), float(max_hr) * 1.1)) if max_hr else 230.0
        if max(heartrate) > hr_ceiling:
            issues.append("heart_rate_spike")

    return issues


def data_quality_report(
    *,
    activities: list[ActivitySummary],
    wellness: list[Wellness],
    settings: list[SportSettings],
    stream_issues: dict[str, list[str]] | None = None,
) -> dict[str, Any]:
    """Return existing-gap-shaped findings plus activities excluded from models."""
    stream_issues = stream_issues or {}
    excluded: set[str] = set()
    findings: list[dict[str, str]] = []

    strava_ids = sorted(activity.id for activity in activities if is_strava_stub(activity))
    if strava_ids:
        excluded.update(strava_ids)
        findings.append(
            _gap(
                "activities.source",
                "high",
                _excluded_message(
                    strava_ids,
                    "Strava-restricted activity stubs have no usable metrics",
                ),
                "Sync the recording device directly to Intervals.icu instead of through Strava.",
            )
        )

    powered_athlete = _has_power_meter_evidence(activities, settings)
    rides_without_power = sorted(
        activity.id
        for activity in activities
        if powered_athlete
        and activity.type in _RIDE_TYPES
        and not is_strava_stub(activity)
        and (activity.moving_time or 0) >= 600
        and activity.average_watts is None
        and activity.normalized_power is None
    )
    if rides_without_power:
        excluded.update(rides_without_power)
        findings.append(
            _gap(
                "activities.power",
                "medium",
                _excluded_message(
                    rides_without_power,
                    "Rides are missing power although this athlete has power-meter evidence",
                ),
                "Check the activity sensor/source and re-sync power before using these rides.",
            )
        )

    anomalous_ids = sorted(activity_id for activity_id, issues in stream_issues.items() if issues)
    if anomalous_ids:
        excluded.update(anomalous_ids)
        detail = "; ".join(
            f"{activity_id} ({', '.join(sorted(stream_issues[activity_id]))})"
            for activity_id in anomalous_ids
        )
        findings.append(
            _gap(
                "activities.streams",
                "high",
                f"Sensor dropouts or implausible spikes: {detail}. "
                f"Excluded from coach models: {', '.join(anomalous_ids)}.",
                "Inspect the source file and sensor connection; correct or re-import before modelling.",
            )
        )

    duplicate_ids = _duplicate_ids(activities)
    if duplicate_ids:
        excluded.update(duplicate_ids)
        findings.append(
            _gap(
                "activities.duplicates",
                "high",
                _excluded_message(duplicate_ids, "Probable duplicate activities"),
                "Keep the correct recording and delete or mark the duplicate in Intervals.icu.",
            )
        )

    threshold_sports = _sports_missing_thresholds(activities, settings)
    if threshold_sports:
        findings.append(
            _gap(
                "sport_settings.thresholds",
                "medium",
                "No configured threshold for active sport(s): "
                f"{', '.join(threshold_sports)}. Models will not infer one silently.",
                "Set FTP, LTHR, or pace threshold for each sport in Intervals.icu.",
            )
        )

    load_findings, load_exclusions = _daily_load_mismatches(activities, wellness)
    if load_findings:
        findings.append(load_findings)
        excluded.update(load_exclusions)

    return {
        "gaps": findings,
        "excluded_activity_ids": sorted(excluded),
        "activities_checked": len(activities),
        "stream_activities_checked": len(stream_issues),
    }


def _numeric_series(raw: Any) -> list[float]:
    if not isinstance(raw, list):
        return []
    values = cast(list[Any], raw)
    return [float(value) if isinstance(value, int | float) else 0.0 for value in values]


def _has_bounded_dropout(
    values: list[float],
    reference: list[float],
    minimum_samples: int,
) -> bool:
    """A zero run bounded by real samples while another sensor remains active."""
    if len(reference) != len(values):
        return False
    index = 0
    while index < len(values):
        if values[index] > 0:
            index += 1
            continue
        start = index
        while index < len(values) and values[index] <= 0:
            index += 1
        if start == 0 or index == len(values):
            continue
        run_length = index - start
        active_reference = sum(1 for value in reference[start:index] if value > 0)
        if run_length >= minimum_samples and active_reference / run_length >= 0.8:
            return True
    return False


def _gap(field: str, severity: str, message: str, prompt: str) -> dict[str, str]:
    return {
        "field": field,
        "severity": severity,
        "message": message,
        "prompt": prompt,
    }


def _excluded_message(activity_ids: list[str], finding: str) -> str:
    return (
        f"{finding}: {', '.join(activity_ids)}. "
        f"Excluded from coach models: {', '.join(activity_ids)}."
    )


def _has_power_meter_evidence(
    activities: list[ActivitySummary], settings: list[SportSettings]
) -> bool:
    if any(
        activity.type in _RIDE_TYPES
        and (activity.average_watts is not None or activity.normalized_power is not None)
        for activity in activities
    ):
        return True
    return any(
        setting.type == "Ride" and (setting.ftp is not None or bool(setting.power_zones))
        for setting in settings
    )


def _duplicate_ids(activities: list[ActivitySummary]) -> list[str]:
    groups: dict[tuple[Any, ...], list[str]] = defaultdict(list)
    for activity in activities:
        if is_strava_stub(activity):
            continue
        if not activity.moving_time or not (activity.distance or activity.icu_training_load):
            continue
        started = activity.start_date_local.replace(second=0, microsecond=0)
        signature = (
            started.isoformat(),
            activity.type,
            round((activity.moving_time or 0) / 30),
            round((activity.distance or 0) / 100),
            round((activity.icu_training_load or 0) / 5),
        )
        groups[signature].append(activity.id)
    duplicates: list[str] = []
    for ids in groups.values():
        if len(ids) > 1:
            duplicates.extend(sorted(ids)[1:])
    return sorted(duplicates)


def _sport_family(activity_type: str | None) -> str | None:
    if activity_type in _RIDE_TYPES:
        return "Ride"
    if activity_type in _RUN_TYPES:
        return "Run"
    if activity_type in _SWIM_TYPES:
        return "Swim"
    return activity_type


def _sports_missing_thresholds(
    activities: list[ActivitySummary], settings: list[SportSettings]
) -> list[str]:
    active_sports = {
        family
        for activity in activities
        if (family := _sport_family(activity.type)) is not None and not is_strava_stub(activity)
    }
    by_sport = {setting.type: setting for setting in settings if setting.type}
    missing: list[str] = []
    for sport in sorted(active_sports):
        setting = by_sport.get(sport)
        if setting is None:
            missing.append(sport)
            continue
        thresholds = (
            setting.ftp,
            setting.fthr,
            setting.pace_threshold,
            setting.swim_threshold,
        )
        if not any(value is not None for value in thresholds):
            missing.append(sport)
    return missing


def _daily_load_mismatches(
    activities: list[ActivitySummary], wellness: list[Wellness]
) -> tuple[dict[str, str] | None, list[str]]:
    load_rows = {
        record.id: float(record.ctl_load) for record in wellness if record.ctl_load is not None
    }
    if not load_rows:
        return None, []

    by_day: dict[str, list[ActivitySummary]] = defaultdict(list)
    for activity in activities:
        by_day[activity.start_date_local.date().isoformat()].append(activity)

    load_without_activity = sorted(
        day for day, load in load_rows.items() if load > 0 and not by_day.get(day)
    )
    activity_without_load = sorted(
        day
        for day, day_activities in by_day.items()
        if any((activity.icu_training_load or 0) > 0 for activity in day_activities)
        and day in load_rows
        and load_rows[day] <= 0
    )
    if not load_without_activity and not activity_without_load:
        return None, []

    excluded = sorted(
        activity.id for day in activity_without_load for activity in by_day.get(day, [])
    )
    parts: list[str] = []
    if load_without_activity:
        parts.append(f"load but no activity on {', '.join(load_without_activity)}")
    if activity_without_load:
        parts.append(f"activity but no daily load on {', '.join(activity_without_load)}")
    message = "Daily load/activity mismatch: " + "; ".join(parts) + "."
    if excluded:
        message += f" Excluded from coach models: {', '.join(excluded)}."
    return (
        _gap(
            "fitness.daily_load",
            "high",
            message,
            "Reconcile the activity and fitness-chart load in Intervals.icu before modelling.",
        ),
        excluded,
    )
