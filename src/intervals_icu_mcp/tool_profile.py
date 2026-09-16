"""Tool-profile gate: which tools register for a given INTERVALS_ICU_TOOL_PROFILE.

The gate sits outside the model's reach — a prompt cannot summon a tool that
was never registered. `coaching` is the daily training surface (calendar,
fitness, curves, wellness, activities, streams/histograms, workout library).
`full` is the upstream catalog (gear, custom items, sport-settings writes, …).

Delete-safety still applies on top: a name in COACHING_TOOLS is only registered
when INTERVALS_ICU_DELETE_MODE also allows it (e.g. icu_delete_event).
"""

from typing import Any, Literal

from fastmcp import FastMCP

ToolProfile = Literal["coaching", "full"]
VALID_TOOL_PROFILES: tuple[ToolProfile, ...] = ("coaching", "full")

# Daily coaching / management surface. Keep this list explicit so a new
# upstream tool does not appear in coaching until someone opts it in.
COACHING_TOOLS: frozenset[str] = frozenset(
    {
        "icu_get_calendar_events",
        "icu_get_upcoming_workouts",
        "icu_get_event",
        "icu_create_event",
        "icu_update_event",
        "icu_delete_event",
        "icu_bulk_create_events",
        "icu_duplicate_events",
        "icu_preview_workout",
        "icu_get_athlete_profile",
        "icu_get_fitness_summary",
        "icu_get_fitness_chart",
        "icu_get_sport_settings",
        "icu_get_power_curves",
        "icu_get_hr_curves",
        "icu_get_pace_curves",
        "icu_get_wellness_data",
        "icu_get_wellness_for_date",
        "icu_update_wellness",
        "icu_get_recent_activities",
        "icu_get_activities_by_date",
        "icu_get_activity_details",
        "icu_search_activities",
        "icu_get_activity_intervals",
        "icu_get_best_efforts",
        "icu_get_activity_streams",
        "icu_get_power_histogram",
        "icu_get_hr_histogram",
        "icu_get_pace_histogram",
        "icu_get_gap_histogram",
        "icu_get_workout_library",
        "icu_get_workouts_in_folder",
    }
)


def should_register_tool(name: str, profile: ToolProfile) -> bool:
    """Return True if `name` should be offered under this profile."""
    if profile == "full":
        return True
    return name in COACHING_TOOLS


def install_tool_profile_filter(mcp: FastMCP, profile: ToolProfile) -> None:
    """Wrap `mcp.tool` so registrations not in the profile become no-ops.

    Existing `mcp.tool(name=..., annotations=...)(fn)` call sites in server.py
    stay untouched, so upstream merges that add tools do not need a rebase
    conflict — they simply stay out of coaching until added to COACHING_TOOLS.
    """
    bound_tool = mcp.tool

    def profiled_tool(
        name_or_fn: Any = None,
        *args: Any,
        name: str | None = None,
        **kwargs: Any,
    ) -> Any:
        resolved = (
            name if name is not None else (name_or_fn if isinstance(name_or_fn, str) else None)
        )
        if resolved is not None and not should_register_tool(resolved, profile):
            if callable(name_or_fn) and name is None:
                return name_or_fn

            def skip(fn: Any) -> Any:
                return fn

            return skip
        return bound_tool(name_or_fn, *args, name=name, **kwargs)

    mcp.tool = profiled_tool  # type: ignore[method-assign]


def coaching_tools_for_delete_mode(delete_mode: str) -> frozenset[str]:
    """Coaching names that survive the delete-mode gate."""
    if delete_mode == "none":
        return COACHING_TOOLS - {"icu_delete_event"}
    return COACHING_TOOLS
