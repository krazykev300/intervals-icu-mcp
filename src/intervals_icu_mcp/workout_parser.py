"""Local Intervals.icu workout-syntax linter and duration estimator.

The Intervals.icu API parses a WORKOUT event's ``description`` server-side and
returns HTTP 200 even when it silently drops tokens — duration ranges such as
``3-4h``, a blank line between an ``Nx`` header and its steps (the repeat
collapses to 1x), unrecognized targets, and similar traps. This module catches
those cases *before* a calendar write, and powers ``icu_preview_workout``.

It is a linter + duration estimator, not a reimplementation of the live parser:
target/zone resolution and training-load math still happen on Intervals.icu.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

# Duration/distance *ranges* — Intervals.icu drops these instead of erroring.
# Longer units first so ``15-20mtr`` is not read as ``15-20m`` + leftover ``tr``.
_RANGE_UNIT = r"(?:mtr|yrd|km|mi|h|m|s)"
_DURATION_RANGE = re.compile(rf"(?i)(?<!\w)(\d+(?:\.\d+)?)\s*-\s*(\d+(?:\.\d+)?)\s*{_RANGE_UNIT}\b")
_DURATION_RANGE_BOTH_UNITS = re.compile(
    rf"(?i)(?<!\w)(\d+(?:\.\d+)?)\s*{_RANGE_UNIT}\s*-\s*"
    rf"(\d+(?:\.\d+)?)\s*{_RANGE_UNIT}\b"
)

# Single time durations. ``m(?!tr)`` so ``400mtr`` is not 400 minutes.
_TIME_DURATION = re.compile(
    r"(?i)(?<!\w)(?:"
    r"\d+(?:\.\d+)?h\d+m(?:\d+s)?"
    r"|\d+m\d+s"
    r"|\d+(?:\.\d+)?h"
    r"|\d+(?:\.\d+)?m(?!tr)"
    r"|\d+(?:\.\d+)?s"
    r"|\d+:\d{2}(?::\d{2})?(?!/)"
    r"|\d+'(?:\d+\")?"
    r"|\d+\""
    r")"
)

_DISTANCE = re.compile(r"(?i)(?<!\w)(\d+(?:\.\d+)?)\s*(mtr|km|mi|yrd)\b")

_REPEAT_HEADER = re.compile(r"^(?:(.+?)\s+)?(\d+)x$", re.IGNORECASE)
_INLINE_REPS = re.compile(r"^(\d+)x\s+", re.IGNORECASE)
_REST = re.compile(r"(?i)\b(\d+(?:\.\d+)?)s\s+rest\b")
_BARE_PACE = re.compile(r"(?i)\d+:\d{2}/(?:km|mi|100m|100y)\b")
_PACE_WORD = re.compile(r"(?i)/\S+\s+pace\b")
_CSS_WORDS = re.compile(r"(?i)\b(CSS|threshold|5K pace|marathon pace)\b")
_TARGET_FIRST = re.compile(r"(?i)^-\s*(?:Z\d|\d+%|\d+w)\b")
_BRACKET_REPEAT = re.compile(r"(?i)\[(?:repeat\b|[^\]]*\d+x)")

# Distances commonly written with a bare ``m`` (parsed as minutes).
_TRACK_DISTANCES = {50, 100, 200, 400, 800, 1500, 1600, 3000, 5000}

_METERS_PER_UNIT: dict[str, float] = {
    "mtr": 1.0,
    "km": 1000.0,
    "mi": 1609.344,
    "yrd": 0.9144,
}


@dataclass
class WorkoutLint:
    """Result of locally inspecting a workout description."""

    errors: list[str] = field(default_factory=list[str])
    warnings: list[str] = field(default_factory=list[str])
    steps: list[dict[str, Any]] = field(default_factory=list[dict[str, Any]])
    total_duration_seconds: int = 0
    original_description: str = ""
    normalized_description: str = ""

    @property
    def rewritten(self) -> bool:
        return self.normalized_description != self.original_description


def looks_like_workout_syntax(description: str) -> bool:
    """True when the text has step lines or ``Nx`` headers worth linting."""
    for raw in description.splitlines():
        stripped = raw.strip()
        if not stripped:
            continue
        if _REPEAT_HEADER.match(stripped) and not stripped.startswith("-"):
            return True
        if stripped.startswith("-") and (
            _TIME_DURATION.search(stripped)
            or _DISTANCE.search(stripped)
            or _DURATION_RANGE.search(stripped)
            or _DURATION_RANGE_BOTH_UNITS.search(stripped)
            or "lap press" in stripped.lower()
        ):
            return True
    return False


def lint_workout_description(description: str) -> WorkoutLint:
    """Parse ``description`` into steps, a duration estimate, errors, and warnings.

    Duration ranges are errors (Intervals.icu silently drops them). A blank line
    between an ``Nx`` header and its steps is a warning; the lint still applies
    the repeat, and ``normalized_description`` collapses that blank line so a
    subsequent write matches the intended total.
    """
    result = WorkoutLint(
        original_description=description,
        normalized_description=description,
    )
    lines = description.splitlines()
    out_lines: list[str] = []
    collapsed_any = False
    i = 0

    while i < len(lines):
        stripped = lines[i].strip()

        if not stripped:
            out_lines.append(lines[i])
            i += 1
            continue

        header_match = _REPEAT_HEADER.match(stripped)
        if header_match and not stripped.startswith("-"):
            reps = int(header_match.group(2))
            j = i + 1
            skipped_blanks = 0
            while j < len(lines) and not lines[j].strip():
                skipped_blanks += 1
                j += 1

            block_raw: list[str] = []
            while j < len(lines):
                nxt = lines[j].strip()
                if not nxt or not nxt.startswith("-"):
                    break
                block_raw.append(lines[j])
                j += 1

            if block_raw:
                if skipped_blanks:
                    collapsed_any = True
                    result.warnings.append(
                        f"Line {i + 1}: '{stripped}' is followed by a blank line before "
                        "its steps. Intervals.icu ignores the repeat count in that form "
                        f"(treats it as 1x, not {reps}x). Put steps on the line immediately "
                        "after the Nx header. The blank line was collapsed so the repeat "
                        "applies."
                    )
                nested: list[dict[str, Any]] = []
                nested_duration = 0
                for offset, raw_step in enumerate(block_raw):
                    step = _parse_step_line(raw_step, i + skipped_blanks + 2 + offset, result)
                    nested.append(step)
                    nested_duration += int(step.get("duration_seconds") or 0)
                block_duration = nested_duration * reps
                result.steps.append(
                    {
                        "text": stripped,
                        "reps": reps,
                        "steps": nested,
                        "duration_seconds": block_duration,
                    }
                )
                result.total_duration_seconds += block_duration
                out_lines.append(stripped)
                out_lines.extend(raw_step.strip() for raw_step in block_raw)
                i = j
                continue

            result.warnings.append(
                f"Line {i + 1}: '{stripped}' has no steps beneath it, so the "
                f"{reps}x repeat does nothing. Put '- <duration> <target>' lines "
                "immediately after the header."
            )

        if stripped.startswith("-"):
            step = _parse_step_line(stripped, i + 1, result)
            result.steps.append(step)
            result.total_duration_seconds += int(step.get("duration_seconds") or 0)

        out_lines.append(stripped if collapsed_any else lines[i])
        i += 1

    if collapsed_any:
        normalized = "\n".join(out_lines)
        if description.endswith("\n"):
            normalized += "\n"
        result.normalized_description = normalized

    if description.strip() and not result.steps and not result.errors:
        result.warnings.append(
            "No steps parsed. Use '- <duration> <target>' lines under "
            "Warmup/Main/Cooldown headers. See intervals-icu://workout-syntax."
        )

    return result


def _parse_step_line(raw: str, line_no: int, result: WorkoutLint) -> dict[str, Any]:
    """Parse one ``- duration target`` line into a step dict; record errors/warnings."""
    stripped = raw.strip()
    step: dict[str, Any] = {"text": stripped}

    range_match = _DURATION_RANGE.search(stripped) or _DURATION_RANGE_BOTH_UNITS.search(stripped)
    if range_match:
        token = range_match.group(0).strip()
        result.errors.append(
            f"Line {line_no}: duration range '{token}' is not parsed by Intervals.icu "
            "(the step is silently dropped from the total). Supply a single fixed "
            f"value instead of a range — e.g. replace '{token}' with one duration."
        )
        _collect_step_warnings(stripped, line_no, result)
        return step

    body = stripped[1:].strip() if stripped.startswith("-") else stripped
    rest_of = body
    inline = _INLINE_REPS.match(body)
    reps = 1
    if inline:
        reps = int(inline.group(1))
        rest_of = body[inline.end() :]
        step["reps"] = reps

    rest_seconds = 0
    work_text = rest_of
    rest_match = _REST.search(rest_of)
    if rest_match:
        rest_seconds = int(float(rest_match.group(1)))
        work_text = rest_of[: rest_match.start()] + rest_of[rest_match.end() :]
        step["rest_seconds"] = rest_seconds

    dist_match = _DISTANCE.search(work_text)
    if dist_match:
        meters = float(dist_match.group(1)) * _METERS_PER_UNIT[dist_match.group(2).lower()]
        step["distance_meters"] = meters

    time_match = _TIME_DURATION.search(work_text)
    duration = 0
    if time_match:
        token = time_match.group(0)
        duration = _time_to_seconds(token)
        minutes_as_meters = _bare_m_track_distance(token)
        if minutes_as_meters is not None:
            result.warnings.append(
                f"Line {line_no}: '{minutes_as_meters}m' is minutes, not meters. "
                f"For {minutes_as_meters} meters write '{minutes_as_meters}mtr'."
            )

    duration += rest_seconds
    duration *= reps
    if duration:
        step["duration_seconds"] = duration
    elif "lap press" not in stripped.lower() and "distance_meters" not in step:
        result.warnings.append(
            f"Line {line_no}: '{stripped}' has no parseable duration or distance, "
            "so it contributes 0 to the total."
        )

    _collect_step_warnings(stripped, line_no, result)
    return step


def _collect_step_warnings(stripped: str, line_no: int, result: WorkoutLint) -> None:
    if _BARE_PACE.search(stripped) and not _PACE_WORD.search(stripped):
        result.warnings.append(
            f"Line {line_no}: absolute pace is missing the trailing 'pace' word "
            "(e.g. '5:00/km pace'); without it the target is silently dropped."
        )
    css = _CSS_WORDS.search(stripped)
    if css:
        word = css.group(1)
        result.warnings.append(
            f"Line {line_no}: '{word}' is not parsed as a target. Write threshold "
            "as '100% pace' or a zone ('Z3 Pace')."
        )
    if _TARGET_FIRST.search(stripped):
        result.warnings.append(
            f"Line {line_no}: target appears before duration. Intervals.icu expects "
            "'- <duration> <target>' (e.g. '- 3m Z5', not '- Z5 3m')."
        )
    if _BRACKET_REPEAT.search(stripped):
        result.warnings.append(
            f"Line {line_no}: bracket-style repeats like '[repeat 5x ...]' are not "
            "parsed. Put 'Nx' on the section header instead."
        )


def _bare_m_track_distance(token: str) -> int | None:
    """Return N when ``token`` is ``Nm`` for a common track distance, else None."""
    match = re.fullmatch(r"(\d+(?:\.\d+)?)m", token, re.IGNORECASE)
    if not match or "." in match.group(1):
        return None
    value = int(match.group(1))
    return value if value in _TRACK_DISTANCES else None


def _time_to_seconds(token: str) -> int:
    """Convert a matched time-duration token to seconds (rounded)."""
    t = token.strip()
    clock = re.fullmatch(r"(\d+):(\d{2})(?::(\d{2}))?", t)
    if clock:
        if clock.group(3) is not None:
            return int(clock.group(1)) * 3600 + int(clock.group(2)) * 60 + int(clock.group(3))
        return int(clock.group(1)) * 60 + int(clock.group(2))

    prime = re.fullmatch(r"(\d+)'(?:(\d+)\")?", t)
    if prime:
        seconds = int(prime.group(1)) * 60
        if prime.group(2):
            seconds += int(prime.group(2))
        return seconds

    quote = re.fullmatch(r"(\d+)\"", t)
    if quote:
        return int(quote.group(1))

    hms = re.fullmatch(
        r"(?:(\d+(?:\.\d+)?)h)?(?:(\d+)m)?(?:(\d+(?:\.\d+)?)s)?",
        t,
        re.IGNORECASE,
    )
    if hms and any(hms.group(i) for i in (1, 2, 3)):
        hours = float(hms.group(1) or 0)
        minutes = float(hms.group(2) or 0)
        seconds = float(hms.group(3) or 0)
        return int(round(hours * 3600 + minutes * 60 + seconds))
    return 0
