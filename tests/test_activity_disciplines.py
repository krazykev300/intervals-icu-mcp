"""The activity discipline enum stays aligned with the OpenAPI spec."""

import json
from pathlib import Path
from typing import get_args

from intervals_icu_mcp.event_categories import EVENT_CATEGORIES_SPEC
from intervals_icu_mcp.models import ACTIVITY_DISCIPLINES, ActivityType
from intervals_icu_mcp.tools.event_management import COMMON_ACTIVITY_TYPES

SPEC_PATH = Path(__file__).resolve().parent.parent / "openapi-spec.json"
IMPORT_WORKOUT_PATH = "/api/v1/athlete/{id}/folders/{folderId}/import-workout"


def _spec_discipline_enum() -> set[str]:
    spec = json.loads(SPEC_PATH.read_text())
    for param in spec["paths"][IMPORT_WORKOUT_PATH]["post"]["parameters"]:
        schema = param.get("schema") or {}
        if param.get("name") == "type" and "enum" in schema:
            return set(schema["enum"])
    raise AssertionError("import-workout type enum not found in openapi-spec.json")


def test_activity_type_matches_openapi_spec():
    assert set(get_args(ActivityType)) == _spec_discipline_enum()


def test_common_hint_is_subset_of_full_enum():
    assert set(COMMON_ACTIVITY_TYPES) <= set(ACTIVITY_DISCIPLINES)
    assert "WeightTraining" in COMMON_ACTIVITY_TYPES
    assert "Workout" in COMMON_ACTIVITY_TYPES


def test_resource_lists_every_discipline():
    for discipline in ACTIVITY_DISCIPLINES:
        assert f"`{discipline}`" in EVENT_CATEGORIES_SPEC
