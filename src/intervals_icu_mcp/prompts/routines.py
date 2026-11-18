"""Named routines: one MCP prompt per thing a coached athlete asks for.

Each prompt is an entry point, not a second copy of the rules. It names the
playbook routine to run and the tools that routine uses; the routine's text
lives in `coaching_playbook.py`. `ROUTINES` is the index the tests and the
Claude Skill builder read, so a routine cannot point at a heading or a tool
that does not exist.
"""

from collections.abc import Callable, Coroutine
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Routine:
    """One named routine: where it lives in the playbook and what it calls."""

    title: str
    heading: str  # exact text in COACHING_PLAYBOOK that starts the routine
    says: str  # what the athlete typically says; used by the skill's index
    tools: tuple[str, ...]  # called after the state and guide reads, in order


ROUTINES: dict[str, Routine] = {
    "morning_check": Routine(
        title="Morning check",
        heading="**Morning check**",
        says="What should I do today?",
        tools=(),
    ),
    "review_my_week": Routine(
        title="Review my week",
        heading="**Review my week**",
        says="How did my week go?",
        tools=(),
    ),
    "plan_next_week": Routine(
        title="Plan next week",
        heading="**Plan next week**",
        says="Plan my next week",
        tools=("icu_bulk_create_events",),
    ),
    "race_week": Routine(
        title="Race week",
        heading="**Race week**",
        says="It's race week",
        tools=("icu_bulk_create_events", "icu_update_event"),
    ),
    "after_the_race": Routine(
        title="After the race",
        heading="**After the race**",
        says="I raced yesterday",
        tools=(
            "icu_get_activities_by_date",
            "icu_get_activity_details",
            "icu_get_activity_intervals",
            "icu_delete_event",
            "icu_bulk_create_events",
        ),
    ),
    "im_sick": Routine(
        title="I'm sick or injured",
        heading="## 7. Illness and injury protocol",
        says="I'm sick / I hurt my knee",
        tools=(
            "icu_create_event",
            "icu_get_calendar_events",
            "icu_delete_event",
            "icu_update_event",
            "icu_bulk_create_events",
        ),
    ),
    "i_have_45_minutes": Routine(
        title="I have N minutes",
        heading="**I have N minutes**",
        says="I have 45 minutes",
        tools=("icu_create_event", "icu_update_event"),
    ),
}

_STATE_STEPS = (
    "1. Call icu_get_athlete_state, unless it was already called in this conversation.\n"
    "2. Call icu_get_coaching_guide, unless the playbook is already loaded in this "
    "conversation."
)
_CLOSE = (
    "Keep the routine's answer shape. Propose in chat first; write to the Intervals "
    "calendar only after a yes, in that same turn."
)


def _body(name: str, ask: str, detail: str = "") -> str:
    routine = ROUTINES[name]
    where = routine.heading.strip("*# ")
    step = f'3. Run "{where}" from the playbook.'
    if routine.tools:
        step += f" Tools it uses, as needed: {', '.join(routine.tools)}."
    parts = [ask, _STATE_STEPS + "\n" + step]
    if detail:
        parts.append(detail)
    parts.append(_CLOSE)
    return "\n\n".join(parts)


async def morning_check() -> str:
    """Morning check: today's session, why, the rest of the week, and at most two flags."""
    return _body("morning_check", "What should I do today?")


async def review_my_week() -> str:
    """Review my week: planned against done, what it achieved, one change for next week."""
    return _body("review_my_week", "Review my training week.")


async def plan_next_week() -> str:
    """Plan next week: a Monday-to-Sunday table inside the load target, written on a yes."""
    return _body("plan_next_week", "Plan my next training week.")


async def race_week() -> str:
    """Race week: the days into the race, openers, fuelling and pacing."""
    return _body("race_week", "It is race week. Set up the days into my race.")


async def after_the_race() -> str:
    """After the race: a short debrief, clear the leftover peak sessions, plan recovery."""
    return _body("after_the_race", "I have raced. Debrief it and sort out what comes next.")


async def im_sick(what: str = "") -> str:
    """I'm sick or injured: block the days, replace the sessions with rest, plan the return.

    Args:
        what: What is wrong, in your own words (e.g. "head cold", "sore left knee"). Optional.
    """
    ask = "I am sick or injured."
    if what.strip():
        ask += f" What is wrong: {what.strip()}."
    return _body(
        "im_sick",
        ask,
        "Start with the safety check and the one question that sets the window. "
        "This is not medical advice and must not read like it.",
    )


async def i_have_45_minutes(minutes: str = "45", location: str = "") -> str:
    """I have N minutes: the best single session for the time available today.

    Args:
        minutes: Minutes available, including warm-up and cool-down (default "45").
        location: Where you are training, e.g. "trainer", "outside", "hotel gym". Optional.
    """
    ask = f"I have {minutes.strip() or '45'} minutes to train today."
    if location.strip():
        ask += f" Location: {location.strip()}."
    return _body("i_have_45_minutes", ask)


ROUTINE_PROMPTS: tuple[Callable[..., Coroutine[Any, Any, str]], ...] = (
    morning_check,
    review_my_week,
    plan_next_week,
    race_week,
    after_the_race,
    im_sick,
    i_have_45_minutes,
)
