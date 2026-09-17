"""Composite athlete-state read for coaching — one grounding call."""

from __future__ import annotations

import asyncio
from datetime import date, timedelta
from typing import Annotated, Any, TypeVar, cast

from fastmcp import Context

from ..athlete_state_compute import (
    calendar_block,
    compliance_block,
    ctl_trend,
    current_fitness,
    derive_phase_context,
    derived_flags,
    durability_from_streams,
    empty_subjective_days,
    fitness_points,
    ftp_from_settings,
    gaps,
    observed_constraints,
    power_keys,
    readiness_block,
    sport_constraints,
    trailing_weekly_ramps,
    tsb_tolerance,
    weekly_fitness_series,
)
from ..auth import ICUConfig
from ..client import ICUAPIError, ICUClient
from ..models import ActivitySummary, CurveSet, Event, SportSettings, Wellness
from ..response_builder import ResponseBuilder

VALID_INCLUDE = frozenset(
    {
        "fitness_form",
        "power_profile",
        "calendar",
        "phase_context",
        "athlete_constraints",
        "compliance",
        "readiness",
        "durability",
    }
)
DEFAULT_INCLUDE = frozenset(VALID_INCLUDE - {"durability"})
MAX_LOOKBACK_DAYS = 365
MAX_HORIZON_DAYS = 365
ACTIVITY_LIMIT = 200
DURABILITY_ACTIVITY_CAP = 6
MIN_DURABILITY_MOVING_S = 3600
_RIDE_TYPES = frozenset({"Ride", "VirtualRide"})

# identity + ISO week → durability payload. Never process-global without the identity key.
_durability_cache: dict[tuple[str, str], dict[str, Any]] = {}


def _parse_include(include: list[str] | str | None) -> set[str] | str:
    """Return a set of blocks, or an error message."""
    if include is None:
        return set(DEFAULT_INCLUDE)
    raw: list[str]
    if isinstance(include, str):
        raw = [part.strip() for part in include.split(",") if part.strip()]
    else:
        raw = [part.strip() for part in include if part and part.strip()]
    if not raw:
        return set(DEFAULT_INCLUDE)
    unknown = [name for name in raw if name not in VALID_INCLUDE]
    if unknown:
        valid = ", ".join(sorted(VALID_INCLUDE))
        return f"Unknown include block(s): {', '.join(unknown)}. Valid: {valid}"
    return set(raw)


async def get_athlete_state(
    athlete_id: Annotated[
        str | None, "Athlete ID (only for coaches; uses configured default otherwise)"
    ] = None,
    horizon_days: Annotated[
        int,
        "Forward calendar window in days (default 90). Pass 365 for a season / year-out plan.",
    ] = 90,
    lookback_days: Annotated[
        int, "History window in days for trends, TSB tolerance, and observed load (default 180)"
    ] = 180,
    include: Annotated[
        list[str] | str | None,
        "Blocks to return. Default: all except durability. "
        "fitness_form, power_profile, calendar, phase_context, athlete_constraints, "
        "compliance, readiness, durability.",
    ] = None,
    ctx: Context | None = None,
) -> str:
    """COMPOSITE grounding read (icu_get_athlete_state / athlete state) for coaching.

    Trajectory, empirical TSB tolerance, races, observed load, readiness, gaps.
    Call this FIRST before drafting a plan. Not today's snapshot
    (icu_get_fitness_summary) and not the raw PMC series (icu_get_fitness_chart).
    Season / year-out: horizon_days=365; if no RACE_A, search goals MCP then
    ask — do not invent a year plan. Durability kJ bins are opt-in via
    include=durability.
    """
    assert ctx is not None
    config: ICUConfig = await ctx.get_state("config")

    if lookback_days < 0 or horizon_days < 0:
        return ResponseBuilder.build_error_response(
            "lookback_days and horizon_days must be zero or positive.",
            error_type="validation_error",
        )
    if lookback_days > MAX_LOOKBACK_DAYS:
        return ResponseBuilder.build_error_response(
            f"lookback_days cannot exceed {MAX_LOOKBACK_DAYS}.",
            error_type="validation_error",
        )
    if horizon_days > MAX_HORIZON_DAYS:
        return ResponseBuilder.build_error_response(
            f"horizon_days cannot exceed {MAX_HORIZON_DAYS}.",
            error_type="validation_error",
        )

    parsed = _parse_include(include)
    if isinstance(parsed, str):
        return ResponseBuilder.build_error_response(parsed, error_type="validation_error")
    blocks = parsed

    resolved_athlete = athlete_id or config.intervals_icu_athlete_id
    today = date.today()
    oldest = (today - timedelta(days=lookback_days)).isoformat()
    newest = (today + timedelta(days=horizon_days)).isoformat()

    need_wellness = bool(blocks & {"fitness_form", "readiness"})
    need_events = bool(blocks & {"calendar", "phase_context", "compliance"})
    need_activities = bool(blocks & {"athlete_constraints", "compliance", "durability"})
    need_curves = "power_profile" in blocks
    need_settings = bool(blocks & {"power_profile", "athlete_constraints"})

    try:
        async with ICUClient(config) as client:

            async def _wellness() -> list[Wellness]:
                if not need_wellness:
                    return []
                return await client.get_wellness(
                    athlete_id=athlete_id, oldest=oldest, newest=today.isoformat()
                )

            async def _events() -> list[Event]:
                if not need_events:
                    return []
                return await client.get_events(athlete_id=athlete_id, oldest=oldest, newest=newest)

            async def _activities() -> list[ActivitySummary]:
                if not need_activities:
                    return []
                return await client.get_activities(
                    athlete_id=athlete_id,
                    oldest=oldest,
                    newest=today.isoformat(),
                    limit=ACTIVITY_LIMIT,
                )

            async def _curves() -> CurveSet | None:
                if not need_curves:
                    return None
                return await client.get_power_curves(
                    athlete_id=athlete_id, type="Ride", curves="42d,90d,365d"
                )

            async def _settings() -> list[SportSettings]:
                if not need_settings:
                    return []
                return await client.get_sport_settings(athlete_id=athlete_id)

            gathered = await asyncio.gather(
                _wellness(),
                _events(),
                _activities(),
                _curves(),
                _settings(),
                return_exceptions=True,
            )

            wellness_res, events_res, activities_res, curves_res, settings_res = gathered
            fetch_errors: list[str] = []

            wellness = _unwrap(wellness_res, "wellness", fetch_errors, default=list[Wellness]())
            events = _unwrap(events_res, "events", fetch_errors, default=list[Event]())
            activities = _unwrap(
                activities_res, "activities", fetch_errors, default=list[ActivitySummary]()
            )
            curve_set = _unwrap(curves_res, "power_curves", fetch_errors, default=None)
            settings = _unwrap(
                settings_res, "sport_settings", fetch_errors, default=list[SportSettings]()
            )

            data: dict[str, Any] = {
                "athlete_id": resolved_athlete,
                "date": today.isoformat(),
                "lookback_days": lookback_days,
                "horizon_days": horizon_days,
            }
            analysis: dict[str, Any] = {}

            daily = fitness_points(wellness, today) if wellness else []
            weekly = weekly_fitness_series(daily)

            if "fitness_form" in blocks:
                current = current_fitness(daily, today)
                form: dict[str, Any] = {}
                if current:
                    form["current"] = current
                if weekly:
                    form["series"] = weekly
                ramps = trailing_weekly_ramps(weekly)
                if current.get("ramp_rate") is not None or ramps:
                    ramp_block: dict[str, Any] = {}
                    if current.get("ramp_rate") is not None:
                        ramp_block["current_weekly"] = current["ramp_rate"]
                    if ramps:
                        ramp_block["trailing_4wk"] = ramps
                    form["ramp_rate"] = ramp_block
                trend = ctl_trend(daily, today)
                if trend:
                    form["ctl_trend"] = trend
                tolerance = tsb_tolerance(daily)
                if tolerance:
                    form["tsb_tolerance"] = tolerance
                data["fitness_form"] = form

            ftp_info = ftp_from_settings(settings) if settings else {}
            power: dict[str, dict[str, int]] = {}
            if "power_profile" in blocks:
                profile: dict[str, Any] = {}
                if curve_set and curve_set.curves:
                    power = power_keys(curve_set.curves)
                    if power:
                        profile["curves"] = power
                profile.update(ftp_info)
                data["power_profile"] = profile

            races: list[dict[str, Any]] = []
            if "calendar" in blocks:
                cal = calendar_block(events, today, horizon_days)
                data["calendar"] = cal
                races = cal.get("goal_events") or []

            phase: dict[str, Any] = {}
            if "phase_context" in blocks:
                phase = derive_phase_context(events, today)
                data["phase_context"] = phase
                if "calendar" in data:
                    data["calendar"]["phase_context"] = phase

            constraints: dict[str, Any] = {}
            if "athlete_constraints" in blocks:
                constraints = observed_constraints(activities, lookback_days)
                constraints.update(sport_constraints(settings))
                data["athlete_constraints"] = constraints

            compliance: dict[str, Any] | None = None
            if "compliance" in blocks:
                compliance = compliance_block(events, activities, today, lookback_days)
                data["compliance"] = compliance

            readiness: dict[str, Any] = {}
            if "readiness" in blocks:
                readiness = readiness_block(wellness, today)
                data["readiness"] = readiness

            if "durability" in blocks:
                durability = await _durability_block(client, resolved_athlete, activities, today)
                if durability:
                    if "power_profile" not in data:
                        data["power_profile"] = {}
                    data["power_profile"]["durability"] = durability

            flags = derived_flags(
                ftp=ftp_info.get("estimated_ftp"),
                power=power,
                constraints=constraints,
                compliance=compliance,
            )
            if flags:
                analysis["derived_flags"] = flags

            subjective_empty = (
                empty_subjective_days(wellness, today) if "readiness" in blocks else None
            )
            analysis["gaps"] = gaps(
                horizon_days=horizon_days,
                races=races if "calendar" in blocks else None,
                phase_source=phase.get("source") if "phase_context" in blocks else None,
                subjective_empty_days=subjective_empty,
                has_power=bool(power) if "power_profile" in blocks else None,
                readiness_state=readiness.get("readiness_state") if readiness else None,
            )

            metadata: dict[str, Any] = {
                "include": sorted(blocks),
                "usage": (
                    "Ground planning here. Textbook TSB bands on icu_get_fitness_summary "
                    "ignore this athlete's tsb_tolerance. Propose calendar writes; wait for yes."
                ),
            }
            if fetch_errors:
                metadata["partial_errors"] = fetch_errors

            return ResponseBuilder.build_response(
                data,
                analysis=analysis,
                metadata=metadata,
                query_type="athlete_state",
            )

    except ICUAPIError as e:
        return ResponseBuilder.build_error_response(e.message, error_type="api_error")
    except Exception as e:
        return ResponseBuilder.build_error_response(
            f"Unexpected error: {str(e)}", error_type="internal_error"
        )


T = TypeVar("T")


def _unwrap(
    value: T | BaseException,
    label: str,
    errors: list[str],
    default: T,
) -> T:
    if isinstance(value, BaseException):
        errors.append(f"{label}: {value}")
        return default
    return value


async def _durability_block(
    client: ICUClient,
    athlete_id: str,
    activities: list[ActivitySummary],
    today: date,
) -> dict[str, Any] | None:
    iso = today.isocalendar()
    cache_key = (athlete_id, f"{iso.year}-W{iso.week:02d}")
    cached = _durability_cache.get(cache_key)
    if cached is not None:
        return cached

    candidates = [
        a
        for a in activities
        if a.type in _RIDE_TYPES and (a.moving_time or 0) >= MIN_DURABILITY_MOVING_S
    ]
    candidates.sort(key=lambda a: a.moving_time or 0, reverse=True)
    chosen = candidates[:DURABILITY_ACTIVITY_CAP]
    if not chosen:
        return None

    async def _watts(activity_id: str) -> list[float]:
        streams = await client.get_activity_streams(activity_id, ["watts"])
        for stream in streams:
            name = stream.type or stream.name
            raw: Any = stream.data
            if name == "watts" and isinstance(raw, list):
                items = cast(list[Any], raw)
                return [float(x) if isinstance(x, int | float) else 0.0 for x in items]
        return []

    traces = await asyncio.gather(
        *[_watts(a.id) for a in chosen],
        return_exceptions=True,
    )
    samples: list[list[float]] = []
    for trace in traces:
        if isinstance(trace, list) and trace:
            samples.append(trace)
    if not samples:
        return None
    payload = durability_from_streams(samples)
    _durability_cache[cache_key] = payload
    return payload
