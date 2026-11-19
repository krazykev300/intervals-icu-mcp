"""Coaching guide tool: the playbook and references as a model-callable read.

Chat clients (Claude.ai, iOS) do not let the model open MCP resources on its
own, so the same text the resources serve is returned here as a tool result.
"""

from __future__ import annotations

from typing import Annotated

from ..coaching.event_categories import EVENT_CATEGORIES_SPEC
from ..coaching.methodology import METHODOLOGY_SPEC
from ..prompts.coaching_playbook import COACHING_PLAYBOOK
from ..workout_syntax import WORKOUT_SYNTAX_SPEC

GUIDE_TOPICS: dict[str, str] = {
    "playbook": COACHING_PLAYBOOK,
    "methodology": METHODOLOGY_SPEC,
    "workout_syntax": WORKOUT_SYNTAX_SPEC,
    "event_categories": EVENT_CATEGORIES_SPEC,
}
DEFAULT_TOPICS = ("playbook", "methodology")


async def get_coaching_guide(
    topics: Annotated[
        list[str] | str | None,
        "Which sections to return. Default: playbook + methodology. Add "
        "workout_syntax before writing structured workouts and event_categories "
        "before creating races or life events. Valid: playbook, methodology, "
        "workout_syntax, event_categories.",
    ] = None,
) -> str:
    """HOW to coach from this server: playbook, methodology numbers, workout syntax, event categories.

    Call once per conversation, right after icu_get_athlete_state, before giving
    training advice or writing calendar events. This is the only way to load the
    coaching rules in chat clients; the intervals-icu:// resources hold the same
    text but the model cannot open them itself. Static text: no need to call
    again for a topic already loaded in this conversation.
    """
    if topics is None:
        names = list(DEFAULT_TOPICS)
    elif isinstance(topics, str):
        names = [part.strip() for part in topics.split(",") if part.strip()]
    else:
        names = [part.strip() for part in topics if part and part.strip()]
    if not names:
        names = list(DEFAULT_TOPICS)
    unknown = [name for name in names if name not in GUIDE_TOPICS]
    if unknown:
        valid = ", ".join(GUIDE_TOPICS)
        return f"Unknown topic(s): {', '.join(unknown)}. Valid: {valid}"
    seen: list[str] = []
    for name in names:
        if name not in seen:
            seen.append(name)
    return "\n\n---\n\n".join(GUIDE_TOPICS[name] for name in seen)
