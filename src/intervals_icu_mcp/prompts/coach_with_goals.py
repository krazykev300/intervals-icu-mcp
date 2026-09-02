"""Coaching prompt: race → fitness → calendar. Body is the shared playbook."""

from .coaching_playbook import COACHING_PLAYBOOK


async def coach_with_goals() -> str:
    """Coach toward a race: log it, compare fitness, write weeks around group rides, add off-season strength.

    Use when the user asks for coaching, race prep, what workouts to do, logging
    a race, planning around group rides or GCal/Drive, off-season strength, or
    structuring the Intervals calendar. Follow intervals-icu://coaching-playbook.
    A separate goals MCP is WHY they race; dates and A/B/C stay on this server.
    """
    return COACHING_PLAYBOOK
