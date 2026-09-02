"""Brain-agnostic overlay prompt: Intervals is WHEN; a goals MCP is WHY."""


async def coach_with_goals() -> str:
    """Plan training using this server plus a separate goals/identity MCP if connected.

    Use when the user wants a coaching turn that combines racing identity or
    constraints from another MCP with calendar, fitness, and wellness here.
    """
    return """When another MCP in this conversation holds goals, constraints, or racing identity:

1. Search that store for why the athlete is training (primary sport, physiological
   limiter, racing profile, intent). Do not treat a date stored there as the race date.
2. Pull calendar, CTL/ATL/form, 1–5 min power curve, and wellness from this server:
   icu_get_calendar_events, icu_get_fitness_summary, icu_get_power_curves,
   icu_get_wellness_data. Read intervals-icu://event-categories before creating races.
3. Cross-reference a named race against Intervals events (category RACE_A / RACE_B /
   RACE_C, with event_type Ride or Run), not against a date in the goals store.
4. Propose sessions in chat. Write planned workouts with icu_create_event
   (category=WORKOUT, description = Intervals workout syntax from
   intervals-icu://workout-syntax) only after the user agrees.
5. The Intervals.icu calendar UI is the review point before execution.

Never write an Intervals API key, athlete id, race date, or CTL/ATL/TSB number
into a goals/knowledge store. A link token in that store (if present) only names
which HTTP identity this MCP should use; clients send it as Authorization:
Bearer, not as a tool argument. Named goals elsewhere are WHY they matter.
WHEN and A/B/C priority are Intervals events.
"""
