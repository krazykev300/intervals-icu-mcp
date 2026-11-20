"""Event/calendar management tools for Intervals.icu MCP server."""

import asyncio
import uuid
from datetime import date, datetime
from typing import Annotated, Any, cast

from fastmcp import Context

from ..auth import ICUConfig
from ..client import ICUAPIError, ICUClient
from ..models import ACTIVITY_DISCIPLINES, Event
from ..response_builder import ResponseBuilder
from ..workout_parser import WorkoutLint, lint_workout_description, looks_like_workout_syntax

PAST_EVENT_HINT = (
    "Past events (today and earlier) require INTERVALS_ICU_DELETE_MODE=full. "
    "Safe mode only deletes events dated tomorrow or later, to absorb "
    "server-vs-athlete timezone skew. This is a server-side env var set by the "
    "operator, not a tool parameter."
)
MISSING_DATE_HINT = (
    "Event has no start_date_local; cannot verify it is in the future. "
    "Use INTERVALS_ICU_DELETE_MODE=full to override."
)


def _classify_event_date(start_date_local: str | None) -> str:
    """Classify an event's date for safe-mode gating.

    Compares at date granularity (planned events typically lack meaningful times).
    Today is classified as 'past' so safe mode only deletes events dated tomorrow
    or later. The one-day buffer absorbs server-vs-athlete timezone skew (e.g.,
    UTC server with non-UTC athlete profile) without an extra API call.

    Returns one of: 'future', 'past', 'unknown'.
    """
    if not start_date_local:
        return "unknown"
    try:
        parsed = datetime.fromisoformat(start_date_local).date()
    except (ValueError, TypeError):
        return "unknown"
    return "future" if parsed > date.today() else "past"


def _delete_envelope(
    deleted: list[int],
    skipped: list[dict[str, Any]],
) -> dict[str, Any]:
    """Build the uniform deleted/skipped response envelope."""
    return {
        "deleted": deleted,
        "deleted_count": len(deleted),
        "skipped": skipped,
        "skipped_count": len(skipped),
    }


def _skipped_entry_for(event_id: int, event: Event | None) -> dict[str, Any]:
    """Build a `skipped` entry for an event refused in safe mode."""
    classification = _classify_event_date(event.start_date_local if event else None)
    if classification == "past":
        return {
            "id": event_id,
            "reason": "past_event",
            "start_date_local": event.start_date_local if event else None,
            "hint": PAST_EVENT_HINT,
        }
    return {
        "id": event_id,
        "reason": "missing_date",
        "start_date_local": event.start_date_local if event else None,
        "hint": MISSING_DATE_HINT,
    }


VALID_CATEGORIES = {
    "WORKOUT",
    "NOTE",
    "RACE_A",
    "RACE_B",
    "RACE_C",
    "TARGET",
    "PLAN",
    "HOLIDAY",
    "SICK",
    "INJURED",
    "SET_EFTP",
    "FITNESS_DAYS",
    "SEASON_START",
    "SET_FITNESS",
}
CATEGORY_ALIASES = {"RACE": "RACE_A", "GOAL": "TARGET"}
VALID_AVAILABILITY = {"NORMAL", "LIMITED", "UNAVAILABLE"}
RACE_CATEGORIES = {"RACE_A", "RACE_B", "RACE_C"}
# Curated subset of models.ACTIVITY_DISCIPLINES for parameter hints and errors.
# The full enum is in the intervals-icu://event-categories resource.
COMMON_ACTIVITY_TYPES = (
    "Ride",
    "Run",
    "Swim",
    "Walk",
    "Hike",
    "WeightTraining",
    "Workout",
    "VirtualRide",
    "VirtualRun",
    "Other",
)
ACTIVITY_TYPES_HINT = ", ".join(COMMON_ACTIVITY_TYPES) + (
    " (full list: intervals-icu://event-categories)"
)

# ---- Session layout (backlog 1.1) -------------------------------------------
# A coach-written session reads the same everywhere: purpose line, steps, a
# fuelling line, a fallback. Role picks a calendar colour so key sessions stand
# out, and becomes a `role:<name>` tag the coach can filter on later.
SESSION_ROLE_COLORS = {
    "key": "#d32f2f",
    "support": "#1976d2",
    "easy": "#388e3c",
    "strength": "#7b1fa2",
}
SESSION_ROLES_HINT = ", ".join(SESSION_ROLE_COLORS)
FUEL_PREFIX = "Fuel:"
FALLBACK_PREFIX = "Fallback:"
COACH_EXTERNAL_ID_PREFIX = "coach-"
MAX_CARBS_PER_HOUR = 200
_SPORTS_BY_LOWER = {s.lower(): s for s in ACTIVITY_DISCIPLINES}


def _one_line(text: str) -> str:
    return " ".join(text.split())


def _compose_session_description(
    description: str | None,
    purpose: str | None,
    carbs_per_hour: int | None,
    fallback: str | None,
) -> str | None:
    """Lay out purpose / steps / fuel / fallback in the fixed coach order.

    Returns `description` unchanged when no layout field is given. Existing
    `Fuel:` / `Fallback:` lines and a leading copy of the purpose are dropped
    first, so passing back a previously composed description does not stack
    duplicate lines.
    """
    if purpose is None and fallback is None and carbs_per_hour is None:
        return description
    lines = [
        ln
        for ln in (description or "").splitlines()
        if not ln.strip().startswith((FUEL_PREFIX, FALLBACK_PREFIX))
    ]
    body = "\n".join(lines).strip()
    parts: list[str] = []
    if purpose and purpose.strip():
        purpose_line = _one_line(purpose)
        first, _, rest = body.partition("\n")
        if first.strip() == purpose_line:
            body = rest.strip()
        parts.append(purpose_line)
    if body:
        parts.append(body)
    tail: list[str] = []
    if carbs_per_hour:
        tail.append(f"{FUEL_PREFIX} {carbs_per_hour} g carbs per hour.")
    if fallback and fallback.strip():
        tail.append(f"{FALLBACK_PREFIX} {_one_line(fallback)}")
    if tail:
        parts.append("\n".join(tail))
    return "\n\n".join(parts)


def _session_fields(
    *,
    role: str | None,
    tags: list[str] | None,
    indoor: bool | None,
    carbs_per_hour: int | None,
    external_id: str | None,
    color: str | None,
    is_create: bool,
) -> tuple[dict[str, Any], str | None]:
    """API fields for the session layout. Returns (fields, error_message).

    On create, a session with a `role` gets a `coach-…` external_id when none is
    given, so the coach can find the events it wrote.
    """
    fields: dict[str, Any] = {}
    normalized_role: str | None = None
    if role is not None:
        normalized_role = role.strip().lower()
        if normalized_role not in SESSION_ROLE_COLORS:
            return {}, f"Invalid role. Must be one of: {SESSION_ROLES_HINT}"
    if carbs_per_hour is not None and not 0 <= carbs_per_hour <= MAX_CARBS_PER_HOUR:
        return {}, f"carbs_per_hour must be between 0 and {MAX_CARBS_PER_HOUR}."

    if tags is not None or normalized_role:
        merged: list[str] = []
        for tag in [*(tags or []), *([f"role:{normalized_role}"] if normalized_role else [])]:
            clean = str(tag).strip()
            if clean and clean not in merged:
                merged.append(clean)
        fields["tags"] = merged
    if color is not None:
        fields["color"] = color
    elif normalized_role:
        fields["color"] = SESSION_ROLE_COLORS[normalized_role]
    if indoor is not None:
        fields["indoor"] = indoor
    if carbs_per_hour is not None:
        fields["carbs_per_hour"] = carbs_per_hour
    if external_id is not None:
        fields["external_id"] = external_id
    elif is_create and normalized_role:
        fields["external_id"] = f"{COACH_EXTERNAL_ID_PREFIX}{uuid.uuid4().hex[:12]}"
    return fields, None


# ---- Availability (backlog 1.6) ---------------------------------------------


def _availability_fields(
    *,
    training_availability: str | None,
    max_training_seconds: int | None,
    can_train_sports: list[str] | None,
) -> tuple[dict[str, Any], str | None]:
    """API fields for native availability on HOLIDAY/SICK/INJURED events."""
    fields: dict[str, Any] = {}
    if training_availability is not None:
        normalized = str(training_availability).upper()
        if normalized not in VALID_AVAILABILITY:
            return {}, (
                "Invalid training_availability. Must be one of: "
                f"{', '.join(sorted(VALID_AVAILABILITY))}"
            )
        fields["training_availability"] = normalized
    if max_training_seconds is not None:
        if max_training_seconds < 0:
            return {}, "max_training_seconds must be 0 or more."
        fields["max_training_time"] = max_training_seconds
    if can_train_sports is not None:
        sports: list[str] = []
        unknown: list[str] = []
        for sport in can_train_sports:
            canonical = _SPORTS_BY_LOWER.get(str(sport).strip().lower())
            if canonical is None:
                unknown.append(str(sport))
            elif canonical not in sports:
                sports.append(canonical)
        if unknown:
            return {}, (
                f"Unknown sport(s) in can_train_sports: {', '.join(unknown)}. "
                f"Use activity disciplines: {ACTIVITY_TYPES_HINT}."
            )
        fields["can_train_sports"] = sports
    return fields, None


# Compact, in-context workout-syntax cheat-sheet for the `description` field.
# Inlined (not only pointed at via the intervals-icu://workout-syntax resource)
# because many hosts — notably Claude Desktop — never surface MCP resources to the
# model, so weaker models fall back to inventing non-native formats. Each "NOT"
# clause targets a failure mode observed in real model output.
WORKOUT_SYNTAX_HINT = (
    "For WORKOUT events the server parses this into structured, device-syncable "
    "steps with zones and a training load. Use Intervals.icu workout syntax: one "
    "step per line as '- <duration> <target>' (duration FIRST), grouped under "
    "Warmup / Main / Cooldown headers. Targets: bike '- 5m 85%', '- 5m Z4', or "
    "absolute '- 5m 210w'; HR '- 10m 70-80% HR' or '- 10m 145bpm'; run/swim pace "
    "'- 5m Z2 Pace', absolute only with a trailing 'pace' word: '- 5m 4:45/km pace', "
    "'- 200mtr 1:45/100m pace' (bare '5:00/km' or '1:45/100m' silently drops); "
    "threshold is relative — run '- 25m 100% pace', swim CSS '- 200mtr 100% pace' — "
    "the words 'threshold'/'CSS'/'5K pace' are NOT parsed as targets. "
    "Add cadence to any step: '- 3m Z2 90rpm'. "
    "No target: '- 20m free'. Repeats: 'Nx' on the header, steps on the very next "
    "line — e.g. 'Main 5x' then immediately '- 3m 110%' / '- 3m 50%'. A blank line "
    "BETWEEN the Nx header and its first step makes Intervals.icu ignore the repeat "
    "(runs 1x). Blank lines BETWEEN sections are required: after the last step of "
    "one block, then the next header. Never put a blank line inside the repeat."
    "Duration ranges ('3-4h', '15-20m') are rejected — pick one value. "
    "Dry-run with icu_preview_workout before writing. Ramps: '- 10m ramp "
    "50-70%'. Rest: append 'Ns rest' "
    "to a step ('- 200mtr Z2 20s rest') or use a separate '- 20s intensity=rest' "
    "step (only intensity=rest exports as a device rest step) — never a bare "
    "'- 20s' step (that becomes work, not rest). Durations: 'm'=minutes, 's'=seconds; "
    "distance steps use 'mtr'=meters / 'km' / 'yrd' (e.g. swim '- 400mtr Z2 Pace'). "
    "Do NOT write '[repeat 5x ...]', nested bullets, or 'Z5 3m' (target before "
    "duration). Runs need a pace or HR target — a bare 'Z2' gives no load. Full "
    "reference: intervals-icu://workout-syntax resource."
)


def _count_workout_steps(steps: list[Any]) -> int:
    """Count total steps in a parsed workout_doc, expanding repeat blocks.

    Each entry in workout_doc["steps"] is either a plain step or a repeat block
    (has `reps` plus a nested `steps` list). Repeats count as reps × nested count.
    """
    total = 0
    for step in steps:
        if isinstance(step, dict):
            step_dict = cast(dict[str, Any], step)
            nested = step_dict.get("steps")
            if isinstance(nested, list):
                total += int(step_dict.get("reps", 1)) * len(cast(list[Any], nested))
                continue
        total += 1
    return total


def _swim_work_lacks_intensity(steps: list[Any]) -> bool:
    """True if a swim's work steps carry no pace/HR target.

    Swim load comes from a pace target (needs a swim CSS/threshold) or an HR target
    (needs swim FTHR). Warmup/cooldown steps are excluded so a warmup pace zone
    can't mask a main set with no intensity, and repeat blocks are flattened to
    their steps. Flat steps under a Warmup/Cooldown header carry a `warmup`/
    `cooldown` flag — as do steps tagged `intensity=warmup`/`cooldown`, at any
    nesting level — but a repeated header ("Warmup 4x") never does — the header
    survives only in the block's `text` — so repeat blocks are matched on that
    (same case-insensitive exact word the API recognizes; live-verified).
    Returns False when there are no work steps to judge. Keying the
    swim load hint on this (rather than total load) catches a main set that parsed
    structurally but dropped its target — e.g. an unrecognized `CSS` token — even
    when a stray misapplied zone leaves a token training load behind.
    """
    work: list[dict[str, Any]] = []

    def _collect(items: list[Any], excluded: bool) -> None:
        for step in items:
            if not isinstance(step, dict):
                continue
            step_dict = cast(dict[str, Any], step)
            nested = step_dict.get("steps")
            if isinstance(nested, list):
                text = str(step_dict.get("text") or "").lower()
                _collect(
                    cast(list[Any], nested),
                    excluded or text.startswith(("warmup", "cooldown")),
                )
            elif not excluded and not step_dict.get("warmup") and not step_dict.get("cooldown"):
                work.append(step_dict)

    _collect(steps, False)
    if not work:
        return False
    return not any(s.get("pace") or s.get("hr") for s in work)


def _workout_parse_info(event: Event) -> dict[str, Any] | None:
    """Echo whether a WORKOUT `description` parsed into a structured workout.

    Intervals.icu always returns a workout_doc object, but its `steps` list is
    empty when the description could not be parsed (prose, or a non-native format
    a model invented). Surfacing this lets the caller tell a real structured
    workout — one that syncs to devices and gets a computed load — from free text
    stored verbatim, instead of a silent "success". Returns None for non-WORKOUT
    events or WORKOUT events with no description (nothing to parse).
    """
    if event.category != "WORKOUT" or not event.description:
        return None
    doc: dict[str, Any] = event.workout_doc or {}
    steps: list[Any] = doc.get("steps") or []
    if steps:
        info: dict[str, Any] = {
            "workout_parsed": True,
            "workout_steps": _count_workout_steps(steps),
        }
        # Swim-specific: a swim can parse into steps yet get no usable training load,
        # because pace targets need a swim CSS/threshold (commonly unset) while HR
        # targets load fine off swim FTHR. Key on whether the *work* steps carry an
        # intensity target rather than on total load — a warmup pace zone or a stray
        # misapplied zone can leave a token load on an otherwise intensity-less set.
        if event.type == "Swim" and _swim_work_lacks_intensity(steps):
            info["workout_load_hint"] = (
                "Swim parsed but its work steps have no recognized pace or HR target, "
                "so it gets no meaningful training load. Common causes: the words "
                "'CSS'/'threshold' are NOT parsed as targets, and absolute pace needs "
                "a trailing 'pace' word ('- 200mtr 1:45/100m pace'). Write threshold "
                "as '- 200mtr 100% pace' or a zone ('- 200mtr Z3 Pace'), which load "
                "off the swim CSS/threshold in sport settings, or HR ('- 200mtr Z2 "
                "HR'), which loads off swim FTHR without a CSS. Check "
                "icu_get_sport_settings before reporting the CSS unset; without a "
                "CSS, distance-step durations are placeholders."
            )
        return info
    return {
        "workout_parsed": False,
        "workout_parse_hint": (
            "Description saved as plain text, not a structured workout (no steps "
            "parsed, no training load). For device-syncable steps/zones use "
            "Intervals.icu workout syntax: '- 5m 85%' / '- 3m Z5' lines under "
            "Warmup/Main/Cooldown headers, 'Nx' after a section name for repeats. "
            "See intervals-icu://workout-syntax."
        ),
    }


_LINT_SUGGESTIONS = [
    "Use icu_preview_workout to inspect the parse before writing.",
    "Duration ranges like '3-4h' or '15-20m' are not parsed — pick a single value.",
    "Put steps on the line immediately after an Nx header, with no blank line in between.",
]


def _lint_description(description: str | None) -> WorkoutLint | None:
    """Lint a description that looks like workout syntax; otherwise skip."""
    if not description or not looks_like_workout_syntax(description):
        return None
    return lint_workout_description(description)


def _lint_error_response(lint: WorkoutLint) -> str | None:
    """Validation-error JSON when the linter found fatal issues, else None."""
    if not lint.errors:
        return None
    return ResponseBuilder.build_error_response(
        " ".join(lint.errors),
        error_type="validation_error",
        suggestions=_LINT_SUGGESTIONS,
    )


def _server_parse_warnings(lint: WorkoutLint, event: Event) -> list[str]:
    """Warnings from comparing our lint to the API's workout_doc, if present."""
    expected_repeats = [s for s in lint.steps if int(s.get("reps") or 1) > 1]
    if not expected_repeats:
        return []
    doc: dict[str, Any] = event.workout_doc or {}
    doc_steps: list[Any] = doc.get("steps") or []
    if not doc_steps:
        return []
    if any(
        isinstance(s, dict) and int(cast(dict[str, Any], s).get("reps") or 1) > 1 for s in doc_steps
    ):
        return []
    return [
        "Intervals.icu did not apply an Nx repeat from the description; "
        "duration may be too low. Put steps on the line immediately after "
        "the Nx header, with no blank line in between."
    ]


def _attach_workout_warnings(
    result: dict[str, Any],
    event: Event,
    lint: WorkoutLint | None,
) -> dict[str, Any]:
    """Add a ``warnings`` array when the linter or the API parse dropped tokens."""
    if lint is None:
        return result
    warnings = list(lint.warnings)
    warnings.extend(_server_parse_warnings(lint, event))
    if warnings:
        result["warnings"] = warnings
    return result


def _normalize_category(category: str) -> tuple[str | None, str | None]:
    """Normalize a category string to its canonical API value.

    Uppercases the input, applies legacy aliases (RACE→RACE_A, GOAL→TARGET),
    and validates against the API enum. Returns (normalized, error_message).
    """
    normalized = category.upper()
    normalized = CATEGORY_ALIASES.get(normalized, normalized)
    if normalized not in VALID_CATEGORIES:
        valid = ", ".join(sorted(VALID_CATEGORIES))
        return None, f"Invalid category. Must be one of: {valid}"
    return normalized, None


def _normalize_date(date_str: str) -> str:
    """Normalize a date string to ISO-8601 (YYYY-MM-DDTHH:MM:SS).

    Accepts YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS. Raises ValueError on bad input.
    """
    return datetime.fromisoformat(date_str).strftime("%Y-%m-%dT%H:%M:%S")


def _event_to_dict(event: Event) -> dict[str, Any]:
    """Build the canonical tool response dict for an Event."""
    result: dict[str, Any] = {
        "id": event.id,
        "start_date": event.start_date_local,
        "name": event.name,
        "category": event.category,
    }

    if event.end_date_local:
        result["end_date"] = event.end_date_local
    if event.description:
        result["description"] = event.description
    if event.type:
        result["type"] = event.type
    if event.moving_time:
        result["duration_seconds"] = event.moving_time
    if event.distance:
        result["distance_meters"] = event.distance
    if event.icu_training_load:
        result["training_load"] = event.icu_training_load
    if event.training_availability:
        result["training_availability"] = event.training_availability
    if event.max_training_time is not None:
        result["max_training_seconds"] = event.max_training_time
    if event.can_train_sports:
        result["can_train_sports"] = event.can_train_sports
    if event.tags:
        result["tags"] = event.tags
    if event.indoor is not None:
        result["indoor"] = event.indoor
    if event.carbs_per_hour is not None:
        result["carbs_per_hour"] = event.carbs_per_hour
    if event.external_id:
        result["external_id"] = event.external_id
    if event.color:
        result["color"] = event.color
    if event.show_as_note is not None:
        result["show_as_note"] = event.show_as_note
    if event.not_on_fitness_chart is not None:
        result["not_on_fitness_chart"] = event.not_on_fitness_chart
    if event.show_on_ctl_line is not None:
        result["show_on_ctl_line"] = event.show_on_ctl_line

    parse_info = _workout_parse_info(event)
    if parse_info:
        result.update(parse_info)

    return result


async def preview_workout(
    description: Annotated[
        str,
        "Workout description in Intervals.icu syntax — the same text you would "
        "put in icu_create_event's description. Parses locally; does not write "
        "to the calendar. Use to verify steps and total duration before creating.",
    ],
    ctx: Context | None = None,
) -> str:
    """PREVIEW how a workout description parses — steps and duration, no calendar write.

    Use before icu_create_event / icu_update_event / icu_bulk_create_events to
    check intent against the parse. Duration ranges ('3-4h', '15-20m') are
    rejected; other silent-parse traps (blank line after an Nx header, dropped
    targets) surface as warnings. The sibling write tools actually create or
    update events.
    """
    assert ctx is not None

    if not description or not description.strip():
        return ResponseBuilder.build_error_response(
            "description is required.",
            error_type="validation_error",
        )

    lint = lint_workout_description(description)
    if lint.errors:
        return ResponseBuilder.build_error_response(
            " ".join(lint.errors),
            error_type="validation_error",
            suggestions=_LINT_SUGGESTIONS,
        )

    data: dict[str, Any] = {
        "steps": lint.steps,
        "total_duration_seconds": lint.total_duration_seconds,
    }
    if lint.warnings:
        data["warnings"] = lint.warnings
        if any("ignores the repeat" in warning for warning in lint.warnings):
            data["intervals_as_written"] = "blank_line_after_Nx_header_runs_1x"
    if lint.rewritten:
        data["normalized_description"] = lint.normalized_description
    return ResponseBuilder.build_response(data, query_type="preview_workout")


async def create_event(
    start_date: Annotated[str, "Start date in YYYY-MM-DD format"],
    name: Annotated[str, "Event name"],
    category: Annotated[
        str,
        "Event category enum. Common: WORKOUT, NOTE, RACE_A/B/C, TARGET, PLAN, "
        "HOLIDAY, SICK, INJURED. Full list with use-case guidance and the "
        "training_availability enum: intervals-icu://event-categories resource. "
        "Legacy aliases RACE→RACE_A, GOAL→TARGET accepted.",
    ],
    description: Annotated[
        str | None,
        "Event description (plain text for non-workouts). " + WORKOUT_SYNTAX_HINT,
    ] = None,
    event_type: Annotated[
        str | None,
        "Activity discipline (NOT the category): Ride, Run, Swim, Walk, Hike, "
        "VirtualRide, VirtualRun, Other. Required for RACE_A/B/C events.",
    ] = None,
    duration_seconds: Annotated[int | None, "Planned duration in seconds"] = None,
    distance_meters: Annotated[float | None, "Planned distance in meters"] = None,
    training_load: Annotated[int | None, "Planned training load"] = None,
    end_date: Annotated[
        str | None,
        "End date in YYYY-MM-DD format. Use for ranged categories (INJURED, "
        "SICK, HOLIDAY, SEASON_START) to mark a multi-day block.",
    ] = None,
    training_availability: Annotated[
        str | None,
        "Training availability: NORMAL, LIMITED, or UNAVAILABLE. Typical for "
        "INJURED/SICK/HOLIDAY blocks.",
    ] = None,
    max_training_seconds: Annotated[
        int | None, "Availability: most training time per day in the block, seconds"
    ] = None,
    can_train_sports: Annotated[
        list[str] | None,
        "Availability: disciplines possible in the block, e.g. ['WeightTraining'] "
        "for hotel gym only",
    ] = None,
    purpose: Annotated[
        str | None, "Session layout: one line on what the session is for (first line)"
    ] = None,
    fallback: Annotated[
        str | None, "Session layout: what to do instead if it is not going well (last line)"
    ] = None,
    carbs_per_hour: Annotated[
        int | None, "Fuelling in g/h; also written as a 'Fuel:' line in the description"
    ] = None,
    role: Annotated[
        str | None,
        f"Session role ({SESSION_ROLES_HINT}): adds a role:<x> tag, sets the calendar "
        "colour, and a coach- external_id",
    ] = None,
    tags: Annotated[list[str] | None, "Tags, e.g. stimulus ['threshold']"] = None,
    indoor: Annotated[bool | None, "True when the session is meant for the trainer"] = None,
    external_id: Annotated[str | None, "Your own id for finding this event later"] = None,
    color: Annotated[str | None, "Custom display color (hex string)"] = None,
    show_as_note: Annotated[bool | None, "Show event as a note marker on the fitness chart"] = None,
    not_on_fitness_chart: Annotated[
        bool | None, "Hide event entirely from the fitness chart"
    ] = None,
    show_on_ctl_line: Annotated[bool | None, "Render event on the CTL line"] = None,
    athlete_id: Annotated[str | None, "Athlete ID (for coaches managing multiple athletes)"] = None,
    ctx: Context | None = None,
) -> str:
    """Create ONE new calendar event from scratch.

    For two or more events in a single call, prefer icu_bulk_create_events
    over a loop. For copying existing events forward in time (repeating
    a workout for N weeks), use icu_duplicate_events — that tool reuses an
    existing event's payload instead of taking new fields.

    For category guidance and the training_availability enum, read the
    intervals-icu://event-categories resource. For structured WORKOUT events,
    put workout-syntax text in `description` — see intervals-icu://workout-syntax.
    Call icu_preview_workout first to verify steps and duration before writing.
    """
    assert ctx is not None
    config: ICUConfig = await ctx.get_state("config")

    normalized_category, category_error = _normalize_category(category)
    if category_error or normalized_category is None:
        return ResponseBuilder.build_error_response(
            category_error or "Invalid category",
            error_type="validation_error",
        )

    if normalized_category in RACE_CATEGORIES and not event_type:
        return ResponseBuilder.build_error_response(
            f"event_type is required for {normalized_category} events. "
            f"Provide the activity discipline: {ACTIVITY_TYPES_HINT}.",
            error_type="validation_error",
        )

    availability, availability_error = _availability_fields(
        training_availability=training_availability,
        max_training_seconds=max_training_seconds,
        can_train_sports=can_train_sports,
    )
    if availability_error:
        return ResponseBuilder.build_error_response(
            availability_error, error_type="validation_error"
        )

    session, session_error = _session_fields(
        role=role,
        tags=tags,
        indoor=indoor,
        carbs_per_hour=carbs_per_hour,
        external_id=external_id,
        color=color,
        is_create=True,
    )
    if session_error:
        return ResponseBuilder.build_error_response(session_error, error_type="validation_error")
    description = _compose_session_description(description, purpose, carbs_per_hour, fallback)

    try:
        start_date = _normalize_date(start_date)
    except ValueError:
        return ResponseBuilder.build_error_response(
            "Invalid date format. Please use YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS format.",
            error_type="validation_error",
        )

    if end_date is not None:
        try:
            end_date = _normalize_date(end_date)
        except ValueError:
            return ResponseBuilder.build_error_response(
                "Invalid end_date format. Please use YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS format.",
                error_type="validation_error",
            )

    lint = _lint_description(description)
    if lint is not None:
        lint_error = _lint_error_response(lint)
        if lint_error is not None:
            return lint_error
        description = lint.normalized_description

    try:
        event_data: dict[str, Any] = {
            "start_date_local": start_date,
            "name": name,
            "category": normalized_category,
        }

        if description:
            event_data["description"] = description
        if event_type:
            event_data["type"] = event_type
        if duration_seconds:
            event_data["moving_time"] = duration_seconds
        if distance_meters:
            event_data["distance"] = distance_meters
        if training_load:
            event_data["icu_training_load"] = training_load
        if end_date is not None:
            event_data["end_date_local"] = end_date
        event_data.update(availability)
        event_data.update(session)
        if show_as_note is not None:
            event_data["show_as_note"] = show_as_note
        if not_on_fitness_chart is not None:
            event_data["not_on_fitness_chart"] = not_on_fitness_chart
        if show_on_ctl_line is not None:
            event_data["show_on_ctl_line"] = show_on_ctl_line

        async with ICUClient(config) as client:
            event = await client.create_event(event_data, athlete_id=athlete_id)

            return ResponseBuilder.build_response(
                data=_attach_workout_warnings(_event_to_dict(event), event, lint),
                query_type="create_event",
                metadata={"message": f"Successfully created {normalized_category.lower()}: {name}"},
            )

    except ICUAPIError as e:
        return ResponseBuilder.build_error_response(e.message, error_type="api_error")
    except Exception as e:
        return ResponseBuilder.build_error_response(
            f"Unexpected error: {str(e)}", error_type="internal_error"
        )


async def update_event(
    event_id: Annotated[int, "Event ID to update"],
    name: Annotated[str | None, "Updated event name"] = None,
    description: Annotated[str | None, "Updated description. " + WORKOUT_SYNTAX_HINT] = None,
    start_date: Annotated[str | None, "Updated start date (YYYY-MM-DD)"] = None,
    event_type: Annotated[str | None, "Updated activity type"] = None,
    category: Annotated[
        str | None,
        "Updated event category enum. Common: WORKOUT, NOTE, RACE_A/B/C, TARGET. "
        "See intervals-icu://event-categories. Legacy RACE→RACE_A, GOAL→TARGET.",
    ] = None,
    duration_seconds: Annotated[int | None, "Updated duration in seconds"] = None,
    distance_meters: Annotated[float | None, "Updated distance in meters"] = None,
    training_load: Annotated[int | None, "Updated training load"] = None,
    end_date: Annotated[str | None, "Updated end date (YYYY-MM-DD)"] = None,
    training_availability: Annotated[
        str | None, "Updated training availability: NORMAL, LIMITED, or UNAVAILABLE"
    ] = None,
    max_training_seconds: Annotated[
        int | None, "Availability: most training time per day in the block, seconds"
    ] = None,
    can_train_sports: Annotated[
        list[str] | None, "Availability: disciplines possible in the block"
    ] = None,
    purpose: Annotated[
        str | None, "Session layout first line; needs `description` in the same call"
    ] = None,
    fallback: Annotated[
        str | None, "Session layout last line; needs `description` in the same call"
    ] = None,
    carbs_per_hour: Annotated[
        int | None, "Fuelling in g/h; rewrites the 'Fuel:' line when description is passed"
    ] = None,
    role: Annotated[
        str | None, f"Session role ({SESSION_ROLES_HINT}): role:<x> tag and colour"
    ] = None,
    tags: Annotated[list[str] | None, "Replaces the event's tags"] = None,
    indoor: Annotated[bool | None, "True when the session is meant for the trainer"] = None,
    external_id: Annotated[str | None, "Your own id for finding this event later"] = None,
    color: Annotated[str | None, "Updated color (hex string)"] = None,
    show_as_note: Annotated[bool | None, "Show event as a note on the fitness chart"] = None,
    not_on_fitness_chart: Annotated[bool | None, "Hide event from the fitness chart"] = None,
    show_on_ctl_line: Annotated[bool | None, "Render event on the CTL line"] = None,
    athlete_id: Annotated[str | None, "Athlete ID (for coaches managing multiple athletes)"] = None,
    ctx: Context | None = None,
) -> str:
    """Update an existing calendar event.

    Only fields you pass are sent — other fields remain unchanged. For category
    and training_availability semantics, see intervals-icu://event-categories.
    For WORKOUT `description` syntax, see intervals-icu://workout-syntax.
    """
    assert ctx is not None
    config: ICUConfig = await ctx.get_state("config")

    if start_date is not None:
        try:
            start_date = _normalize_date(start_date)
        except ValueError:
            return ResponseBuilder.build_error_response(
                "Invalid date format. Please use YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS format.",
                error_type="validation_error",
            )

    if end_date is not None:
        try:
            end_date = _normalize_date(end_date)
        except ValueError:
            return ResponseBuilder.build_error_response(
                "Invalid end_date format. Please use YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS format.",
                error_type="validation_error",
            )

    availability, availability_error = _availability_fields(
        training_availability=training_availability,
        max_training_seconds=max_training_seconds,
        can_train_sports=can_train_sports,
    )
    if availability_error:
        return ResponseBuilder.build_error_response(
            availability_error, error_type="validation_error"
        )

    session, session_error = _session_fields(
        role=role,
        tags=tags,
        indoor=indoor,
        carbs_per_hour=carbs_per_hour,
        external_id=external_id,
        color=color,
        is_create=False,
    )
    if session_error:
        return ResponseBuilder.build_error_response(session_error, error_type="validation_error")
    if description is None and (purpose is not None or fallback is not None):
        return ResponseBuilder.build_error_response(
            "purpose and fallback rewrite the description, so pass the full description "
            "(the workout steps) in the same call. Read it with icu_get_event first.",
            error_type="validation_error",
        )
    if description is not None:
        description = _compose_session_description(description, purpose, carbs_per_hour, fallback)

    normalized_category: str | None = None
    if category is not None:
        normalized_category, category_error = _normalize_category(category)
        if category_error or normalized_category is None:
            return ResponseBuilder.build_error_response(
                category_error or "Invalid category",
                error_type="validation_error",
            )

    lint = _lint_description(description)
    if lint is not None:
        lint_error = _lint_error_response(lint)
        if lint_error is not None:
            return lint_error
        description = lint.normalized_description

    try:
        event_data: dict[str, Any] = {}

        if name is not None:
            event_data["name"] = name
        if description is not None:
            event_data["description"] = description
        if start_date is not None:
            event_data["start_date_local"] = start_date
        if event_type is not None:
            event_data["type"] = event_type
        if normalized_category is not None:
            event_data["category"] = normalized_category
        if duration_seconds is not None:
            event_data["moving_time"] = duration_seconds
        if distance_meters is not None:
            event_data["distance"] = distance_meters
        if training_load is not None:
            event_data["icu_training_load"] = training_load
        if end_date is not None:
            event_data["end_date_local"] = end_date
        event_data.update(availability)
        event_data.update(session)
        if show_as_note is not None:
            event_data["show_as_note"] = show_as_note
        if not_on_fitness_chart is not None:
            event_data["not_on_fitness_chart"] = not_on_fitness_chart
        if show_on_ctl_line is not None:
            event_data["show_on_ctl_line"] = show_on_ctl_line

        if not event_data:
            return ResponseBuilder.build_error_response(
                "No fields provided to update. Please specify at least one field to change.",
                error_type="validation_error",
            )

        async with ICUClient(config) as client:
            event = await client.update_event(event_id, event_data, athlete_id=athlete_id)

            return ResponseBuilder.build_response(
                data=_attach_workout_warnings(_event_to_dict(event), event, lint),
                query_type="update_event",
                metadata={"message": f"Successfully updated event {event_id}"},
            )

    except ICUAPIError as e:
        return ResponseBuilder.build_error_response(e.message, error_type="api_error")
    except Exception as e:
        return ResponseBuilder.build_error_response(
            f"Unexpected error: {str(e)}", error_type="internal_error"
        )


async def delete_event(
    event_id: Annotated[int, "Event ID to delete"],
    athlete_id: Annotated[str | None, "Athlete ID (for coaches managing multiple athletes)"] = None,
    ctx: Context | None = None,
) -> str:
    """Permanently delete ONE calendar event by ID. Destructive — cannot be undone.

    In `safe` delete mode (default), past events are refused and reported
    in the `skipped` envelope with a hint about INTERVALS_ICU_DELETE_MODE=full.
    Returns a `deleted` / `skipped` envelope either way.
    """
    assert ctx is not None
    config: ICUConfig = await ctx.get_state("config")

    try:
        async with ICUClient(config) as client:
            if config.intervals_icu_delete_mode == "safe":
                event = await client.get_event(event_id, athlete_id=athlete_id)
                if _classify_event_date(event.start_date_local) != "future":
                    return ResponseBuilder.build_response(
                        data=_delete_envelope(
                            deleted=[],
                            skipped=[_skipped_entry_for(event_id, event)],
                        ),
                        query_type="delete_event",
                        metadata={"message": f"Skipped event {event_id} in safe mode"},
                    )

            success = await client.delete_event(event_id, athlete_id=athlete_id)
            if not success:
                return ResponseBuilder.build_error_response(
                    f"Failed to delete event {event_id}",
                    error_type="api_error",
                )
            return ResponseBuilder.build_response(
                data=_delete_envelope(deleted=[event_id], skipped=[]),
                query_type="delete_event",
                metadata={"message": f"Successfully deleted event {event_id}"},
            )

    except ICUAPIError as e:
        return ResponseBuilder.build_error_response(e.message, error_type="api_error")
    except Exception as e:
        return ResponseBuilder.build_error_response(
            f"Unexpected error: {str(e)}", error_type="internal_error"
        )


# icu_create_event's parameter names -> Intervals.icu API field names. Bulk takes the
# same vocabulary as the singular tool and as every event response (#5.0.0 unification).
_BULK_FIELD_MAP = {
    "event_type": "type",
    "duration_seconds": "moving_time",
    "distance_meters": "distance",
    "training_load": "icu_training_load",
}

# Raw API names accepted before 5.0.0. They are rejected rather than ignored: every one
# of them would otherwise pass straight through to the API and keep working, leaving two
# undocumented vocabularies alive. A named error tells the caller exactly what to change.
_BULK_RENAMED_FIELDS = {api: friendly for friendly, api in _BULK_FIELD_MAP.items()}


async def bulk_create_events(
    events: Annotated[
        str,
        "JSON array of event objects, each shaped exactly like an icu_create_event "
        "call. Required per event: start_date_local, name, category. Optional: "
        "description, event_type (activity discipline Ride/Run/Swim/…), "
        "duration_seconds, distance_meters, training_load, "
        "end_date_local, training_availability, max_training_seconds, "
        "can_train_sports, purpose, fallback, carbs_per_hour, role, tags, indoor, "
        "external_id, color, show_as_note, not_on_fitness_chart, show_on_ctl_line "
        "(same meaning as icu_create_event). See "
        "intervals-icu://event-categories for the category enum. " + WORKOUT_SYNTAX_HINT,
    ],
    athlete_id: Annotated[str | None, "Athlete ID (for coaches managing multiple athletes)"] = None,
    ctx: Context | None = None,
) -> str:
    """Create MANY new calendar events in a single batch call (more efficient than looping create_event).

    Accepts a JSON array of event objects, each shaped like an icu_create_event
    payload. For copying existing events forward use icu_duplicate_events
    instead — that reuses payloads rather than taking new fields. See
    intervals-icu://event-categories and intervals-icu://workout-syntax
    for the referenced enums and DSL.
    """
    assert ctx is not None
    config: ICUConfig = await ctx.get_state("config")

    try:
        import json

        try:
            parsed_data = json.loads(events)
        except json.JSONDecodeError as e:
            return ResponseBuilder.build_error_response(
                f"Invalid JSON format: {str(e)}", error_type="validation_error"
            )

        if not isinstance(parsed_data, list):
            return ResponseBuilder.build_error_response(
                "Events must be a JSON array", error_type="validation_error"
            )

        events_data: list[dict[str, Any]] = parsed_data  # type: ignore[assignment]
        lints: list[WorkoutLint | None] = []

        for i, event_data in enumerate(events_data):
            if "start_date_local" not in event_data:
                return ResponseBuilder.build_error_response(
                    f"Event {i}: Missing required field 'start_date_local'",
                    error_type="validation_error",
                )
            if "name" not in event_data:
                return ResponseBuilder.build_error_response(
                    f"Event {i}: Missing required field 'name'", error_type="validation_error"
                )
            if "category" not in event_data:
                return ResponseBuilder.build_error_response(
                    f"Event {i}: Missing required field 'category'",
                    error_type="validation_error",
                )

            normalized_category, category_error = _normalize_category(event_data["category"])
            if category_error or normalized_category is None:
                return ResponseBuilder.build_error_response(
                    f"Event {i}: {category_error or 'Invalid category'}",
                    error_type="validation_error",
                )
            event_data["category"] = normalized_category

            # Bulk payloads use the same vocabulary as icu_create_event and as every
            # event response. Translate to the API's field names here. The raw names
            # (type, moving_time, distance, icu_training_load) were accepted until
            # 5.0.0; they silently dropped whenever a model reused the singular
            # interface, which is why the schemes were unified.
            removed = [f for f in _BULK_RENAMED_FIELDS if f in event_data]
            if removed:
                renames = ", ".join(f"{f} -> {_BULK_RENAMED_FIELDS[f]}" for f in removed)
                return ResponseBuilder.build_error_response(
                    f"Event {i}: raw Intervals.icu field name(s) {', '.join(removed)} are no "
                    f"longer accepted. Bulk payloads use the same names as icu_create_event: "
                    f"{renames}.",
                    error_type="validation_error",
                )
            for friendly, api_field in _BULK_FIELD_MAP.items():
                if friendly in event_data:
                    event_data[api_field] = event_data.pop(friendly)

            if normalized_category in RACE_CATEGORIES and not event_data.get("type"):
                return ResponseBuilder.build_error_response(
                    f"Event {i}: 'event_type' is required for {normalized_category} events. "
                    f"Provide the activity discipline: {ACTIVITY_TYPES_HINT}.",
                    error_type="validation_error",
                )

            try:
                event_data["start_date_local"] = _normalize_date(event_data["start_date_local"])
            except ValueError:
                return ResponseBuilder.build_error_response(
                    f"Event {i}: Invalid date format. Please use YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS format.",
                    error_type="validation_error",
                )

            if "end_date_local" in event_data and event_data["end_date_local"] is not None:
                try:
                    event_data["end_date_local"] = _normalize_date(event_data["end_date_local"])
                except ValueError:
                    return ResponseBuilder.build_error_response(
                        f"Event {i}: Invalid end_date_local format. Please use YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS format.",
                        error_type="validation_error",
                    )

            availability, availability_error = _availability_fields(
                training_availability=event_data.pop("training_availability", None),
                max_training_seconds=event_data.pop("max_training_seconds", None),
                can_train_sports=event_data.pop("can_train_sports", None),
            )
            if availability_error:
                return ResponseBuilder.build_error_response(
                    f"Event {i}: {availability_error}", error_type="validation_error"
                )
            event_data.update(availability)

            carbs = event_data.pop("carbs_per_hour", None)
            session, session_error = _session_fields(
                role=event_data.pop("role", None),
                tags=event_data.pop("tags", None),
                indoor=event_data.pop("indoor", None),
                carbs_per_hour=carbs,
                external_id=event_data.pop("external_id", None),
                color=event_data.pop("color", None),
                is_create=True,
            )
            if session_error:
                return ResponseBuilder.build_error_response(
                    f"Event {i}: {session_error}", error_type="validation_error"
                )
            event_data.update(session)

            desc_raw = event_data.get("description")
            desc = desc_raw if isinstance(desc_raw, str) else None
            desc = _compose_session_description(
                desc, event_data.pop("purpose", None), carbs, event_data.pop("fallback", None)
            )
            if desc is not None:
                event_data["description"] = desc
            lint = _lint_description(desc)
            if lint is not None:
                if lint.errors:
                    return ResponseBuilder.build_error_response(
                        f"Event {i}: {' '.join(lint.errors)}",
                        error_type="validation_error",
                        suggestions=_LINT_SUGGESTIONS,
                    )
                event_data["description"] = lint.normalized_description
            lints.append(lint)

        async with ICUClient(config) as client:
            created_events = await client.bulk_create_events(events_data, athlete_id=athlete_id)

            events_result = [
                _attach_workout_warnings(_event_to_dict(event), event, lint)
                for event, lint in zip(created_events, lints, strict=True)
            ]

            return ResponseBuilder.build_response(
                data={"events": events_result},
                query_type="bulk_create_events",
                metadata={
                    "message": f"Successfully created {len(created_events)} events",
                    "count": len(created_events),
                },
            )

    except ICUAPIError as e:
        return ResponseBuilder.build_error_response(e.message, error_type="api_error")
    except Exception as e:
        return ResponseBuilder.build_error_response(
            f"Unexpected error: {str(e)}", error_type="internal_error"
        )


async def bulk_delete_events(
    event_ids: Annotated[str, "JSON array of event IDs to delete (e.g., '[123, 456, 789]')"],
    athlete_id: Annotated[str | None, "Athlete ID (for coaches managing multiple athletes)"] = None,
    ctx: Context | None = None,
) -> str:
    """Delete MANY calendar events in a single batch call. Destructive — cannot be undone.

    In `safe` delete mode (default), the call partitions the input list
    into `deleted` (future) and `skipped` (past or undated) and returns
    both. INTERVALS_ICU_DELETE_MODE=full disables the partition.

    Args:
        event_ids: JSON array of event IDs (integers)

    Returns:
        JSON string with `deleted` / `skipped` envelope
    """
    assert ctx is not None
    config: ICUConfig = await ctx.get_state("config")

    try:
        import json

        try:
            parsed_data = json.loads(event_ids)
        except json.JSONDecodeError as e:
            return ResponseBuilder.build_error_response(
                f"Invalid JSON format: {str(e)}", error_type="validation_error"
            )

        if not isinstance(parsed_data, list):
            return ResponseBuilder.build_error_response(
                "Event IDs must be a JSON array", error_type="validation_error"
            )

        if not parsed_data:
            return ResponseBuilder.build_error_response(
                "Must provide at least one event ID to delete", error_type="validation_error"
            )

        ids_list: list[int] = parsed_data  # type: ignore[assignment]

        async with ICUClient(config) as client:
            if config.intervals_icu_delete_mode == "safe":
                fetched = await asyncio.gather(
                    *(client.get_event(eid, athlete_id=athlete_id) for eid in ids_list),
                    return_exceptions=True,
                )

                ids_to_delete: list[int] = []
                skipped: list[dict[str, Any]] = []
                for eid, fetched_event in zip(ids_list, fetched, strict=True):
                    if isinstance(fetched_event, BaseException):
                        if isinstance(fetched_event, ICUAPIError):
                            return ResponseBuilder.build_error_response(
                                fetched_event.message, error_type="api_error"
                            )
                        raise fetched_event
                    if _classify_event_date(fetched_event.start_date_local) == "future":
                        ids_to_delete.append(eid)
                    else:
                        skipped.append(_skipped_entry_for(eid, fetched_event))

                if ids_to_delete:
                    await client.bulk_delete_events(ids_to_delete, athlete_id=athlete_id)

                return ResponseBuilder.build_response(
                    data=_delete_envelope(deleted=ids_to_delete, skipped=skipped),
                    query_type="bulk_delete_events",
                    metadata={
                        "message": (
                            f"Deleted {len(ids_to_delete)} event(s); "
                            f"skipped {len(skipped)} in safe mode"
                        ),
                    },
                )

            await client.bulk_delete_events(ids_list, athlete_id=athlete_id)
            return ResponseBuilder.build_response(
                data=_delete_envelope(deleted=ids_list, skipped=[]),
                query_type="bulk_delete_events",
                metadata={"message": f"Successfully deleted {len(ids_list)} events"},
            )

    except ICUAPIError as e:
        return ResponseBuilder.build_error_response(e.message, error_type="api_error")
    except Exception as e:
        return ResponseBuilder.build_error_response(
            f"Unexpected error: {str(e)}", error_type="internal_error"
        )


async def duplicate_events(
    event_ids: Annotated[str, "JSON array of event IDs to duplicate (e.g., '[123, 456]')"],
    num_copies: Annotated[int, "Number of copies to create"] = 1,
    weeks_between: Annotated[int, "Weeks between each copy"] = 1,
    athlete_id: Annotated[str | None, "Athlete ID (for coaches managing multiple athletes)"] = None,
    ctx: Context | None = None,
) -> str:
    """COPY existing events forward in time by N weeks.

    Use when the user says "repeat this workout for the next 4 weeks",
    "duplicate Monday's run on the next 3 Mondays". Reuses the existing
    events' payloads — different from icu_create_event / icu_bulk_create_events,
    which both build NEW events from scratch.
    """
    assert ctx is not None
    config: ICUConfig = await ctx.get_state("config")

    import json

    try:
        parsed = json.loads(event_ids)
        if not isinstance(parsed, list) or not all(
            isinstance(v, int) for v in cast(list[Any], parsed)
        ):
            return ResponseBuilder.build_error_response(
                "event_ids must be a JSON array of integers (e.g., '[123, 456]')",
                error_type="validation_error",
            )
        ids_list = cast(list[int], parsed)

        if num_copies < 1:
            return ResponseBuilder.build_error_response(
                "num_copies must be at least 1",
                error_type="validation_error",
            )

        if weeks_between < 1:
            return ResponseBuilder.build_error_response(
                "weeks_between must be at least 1",
                error_type="validation_error",
            )

        async with ICUClient(config) as client:
            duplicated = await client.duplicate_events(
                event_ids=ids_list,
                num_copies=num_copies,
                weeks_between=weeks_between,
                athlete_id=athlete_id,
            )

            events_result: list[dict[str, Any]] = []
            for event in duplicated:
                event_item: dict[str, Any] = {
                    "id": event.id,
                    "start_date": event.start_date_local,
                    "name": event.name,
                    "category": event.category,
                }
                if event.type:
                    event_item["type"] = event.type
                if event.moving_time:
                    event_item["duration_seconds"] = event.moving_time
                if event.icu_training_load:
                    event_item["training_load"] = event.icu_training_load
                events_result.append(event_item)

            return ResponseBuilder.build_response(
                data={"events": events_result, "duplicated_count": len(events_result)},
                query_type="duplicate_events",
                metadata={
                    "message": f"Duplicated {len(ids_list)} event(s), {num_copies} copies each",
                    "original_event_ids": ids_list,
                    "num_copies": num_copies,
                    "weeks_between": weeks_between,
                },
            )

    except ICUAPIError as e:
        return ResponseBuilder.build_error_response(e.message, error_type="api_error")
    except json.JSONDecodeError:
        return ResponseBuilder.build_error_response(
            "Invalid JSON format for event_ids. Use format: '[123, 456]'",
            error_type="validation_error",
        )
    except Exception as e:
        return ResponseBuilder.build_error_response(
            f"Unexpected error: {str(e)}", error_type="internal_error"
        )


async def apply_training_plan(
    folder_id: Annotated[int, "Folder ID of the training plan to apply"],
    start_date_local: Annotated[str, "Start date in ISO-8601 format (YYYY-MM-DD)"],
    extra_workouts_json: Annotated[str | None, "Optional JSON array of additional workouts"] = None,
    athlete_id: Annotated[str | None, "Athlete ID (for coaches managing multiple athletes)"] = None,
    ctx: Context | None = None,
) -> str:
    """Schedule an entire training plan (workout-library folder) onto the athlete's calendar starting on a chosen date.

    Use after icu_get_workout_library to find a plan's folder_id. Different
    from icu_create_event / icu_bulk_create_events (which build new events) and
    from icu_duplicate_events (which copies existing).
    """
    assert ctx is not None
    config: ICUConfig = await ctx.get_state("config")

    # Validate and normalize date format
    try:
        start_date_local = datetime.fromisoformat(start_date_local).strftime("%Y-%m-%dT00:00:00")
    except ValueError:
        return ResponseBuilder.build_error_response(
            "Invalid date format. Please use YYYY-MM-DD format.",
            error_type="validation_error",
        )

    # Parse extra workouts if provided
    extra_workouts: list[dict[str, Any]] | None = None
    if extra_workouts_json:
        import json

        try:
            extra_workouts = json.loads(extra_workouts_json)
            if not isinstance(extra_workouts, list):
                return ResponseBuilder.build_error_response(
                    "extra_workouts_json must be a JSON array",
                    error_type="validation_error",
                )
        except json.JSONDecodeError as e:
            return ResponseBuilder.build_error_response(
                f"Invalid JSON format for extra_workouts_json: {str(e)}",
                error_type="validation_error",
            )

    try:
        async with ICUClient(config) as client:
            response = await client.apply_training_plan(
                folder_id=folder_id,
                start_date_local=start_date_local,
                extra_workouts=extra_workouts,
                athlete_id=athlete_id,
            )

            return ResponseBuilder.build_response(
                data=response,
                query_type="apply_training_plan",
                metadata={"message": f"Successfully applied training plan folder {folder_id}"},
            )

    except ICUAPIError as e:
        return ResponseBuilder.build_error_response(e.message, error_type="api_error")
    except Exception as e:
        return ResponseBuilder.build_error_response(
            f"Unexpected error: {str(e)}", error_type="internal_error"
        )


# ---- Logging what no device records (backlog 1.9) ---------------------------

DEFAULT_LOGGED_TYPE = "WeightTraining"


def _logged_session_to_dict(activity: Any) -> dict[str, Any]:
    """Compact echo of a logged manual activity."""
    result: dict[str, Any] = {
        "activity_id": activity.id,
        "start_date": activity.start_date_local.isoformat(),
        "name": activity.name,
        "type": activity.type,
    }
    if activity.moving_time:
        result["duration_seconds"] = activity.moving_time
    if activity.perceived_exertion is not None:
        result["rpe"] = activity.perceived_exertion
    if activity.kg_lifted:
        result["kg_lifted"] = activity.kg_lifted
    if activity.icu_training_load is not None:
        result["training_load"] = activity.icu_training_load
    if activity.paired_event_id:
        result["paired_event_id"] = activity.paired_event_id
    if not activity.icu_training_load:
        result["training_load_hint"] = (
            "Intervals did not compute a load for this session. Pass training_load "
            "to set one, or add an RPE so the session counts in load."
        )
    return result


async def log_session(
    duration_seconds: Annotated[
        int | None, "How long the session took, seconds. Required without event_id"
    ] = None,
    rpe: Annotated[int | None, "Session RPE 1-10 (drives the load when no HR/power)"] = None,
    event_id: Annotated[
        int | None,
        "Planned event this session completes; pairs the activity to it so it counts "
        "in compliance. Find it with icu_get_calendar_events.",
    ] = None,
    start_date: Annotated[
        str | None,
        "YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS. Required without event_id; with "
        "event_id the planned date is used",
    ] = None,
    event_type: Annotated[
        str, f"Activity discipline, default {DEFAULT_LOGGED_TYPE}. {ACTIVITY_TYPES_HINT}"
    ] = DEFAULT_LOGGED_TYPE,
    name: Annotated[str | None, "Activity name (default: the planned event's name)"] = None,
    kg_lifted: Annotated[float | None, "Total kg lifted, when the athlete gives it"] = None,
    notes: Annotated[str | None, "What was done (sets, moves), stored as description"] = None,
    training_load: Annotated[int | None, "Override the computed training load"] = None,
    athlete_id: Annotated[str | None, "Athlete ID (for coaches managing multiple athletes)"] = None,
    ctx: Context | None = None,
) -> str:
    """LOG a session no device recorded (gym, yoga, a ride without a head unit).

    "Did the gym session, 50 minutes, RPE 7" → a manual activity with that
    duration and RPE. With `event_id` it is paired to the planned event
    (mark-done), so compliance and load include it. Not for editing activities
    that came from a device.
    """
    assert ctx is not None
    config: ICUConfig = await ctx.get_state("config")

    if rpe is not None and not 1 <= rpe <= 10:
        return ResponseBuilder.build_error_response(
            "rpe must be between 1 and 10.", error_type="validation_error"
        )
    if duration_seconds is not None and duration_seconds <= 0:
        return ResponseBuilder.build_error_response(
            "duration_seconds must be positive.", error_type="validation_error"
        )
    if kg_lifted is not None and kg_lifted < 0:
        return ResponseBuilder.build_error_response(
            "kg_lifted must be 0 or more.", error_type="validation_error"
        )
    if event_id is None and (start_date is None or duration_seconds is None):
        return ResponseBuilder.build_error_response(
            "Without event_id, pass start_date and duration_seconds. To complete a "
            "planned session, pass its event_id instead.",
            error_type="validation_error",
        )
    normalized_start: str | None = None
    if start_date is not None:
        try:
            normalized_start = _normalize_date(start_date)
        except ValueError:
            return ResponseBuilder.build_error_response(
                "Invalid date format. Please use YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS format.",
                error_type="validation_error",
            )

    fields: dict[str, Any] = {}
    if duration_seconds is not None:
        fields["moving_time"] = duration_seconds
        fields["elapsed_time"] = duration_seconds
    if rpe is not None:
        fields["icu_rpe"] = rpe
    if kg_lifted is not None:
        fields["kg_lifted"] = kg_lifted
    if notes:
        fields["description"] = notes
    if training_load is not None:
        fields["icu_training_load"] = training_load
    if name:
        fields["name"] = name

    try:
        async with ICUClient(config) as client:
            if event_id is not None:
                activity = await client.mark_event_done(event_id, athlete_id=athlete_id)
                if normalized_start is not None:
                    fields["start_date_local"] = normalized_start
                if fields:
                    activity = await client.update_activity(activity.id, fields)
                if activity.paired_event_id is None:
                    activity.paired_event_id = event_id
                message = f"Logged session and marked event {event_id} done"
            else:
                payload: dict[str, Any] = {
                    "start_date_local": normalized_start,
                    "type": event_type,
                    "name": name
                    or ("Strength" if event_type == DEFAULT_LOGGED_TYPE else event_type),
                    **fields,
                }
                activity = await client.create_manual_activity(payload, athlete_id=athlete_id)
                message = "Logged session as a manual activity"

            return ResponseBuilder.build_response(
                data=_logged_session_to_dict(activity),
                query_type="log_session",
                metadata={"message": message},
            )

    except ICUAPIError as e:
        return ResponseBuilder.build_error_response(e.message, error_type="api_error")
    except Exception as e:
        return ResponseBuilder.build_error_response(
            f"Unexpected error: {str(e)}", error_type="internal_error"
        )
