"""Every methodology number states where it comes from."""

from __future__ import annotations

from intervals_icu_mcp.coaching import methodology
from intervals_icu_mcp.coaching.sources import BASIS_STRENGTH, PARAMETER_SOURCES, REFERENCES

# Module-level names in methodology.py that are not coaching parameters.
_NOT_PARAMETERS = {"KB_VERSION", "METHODOLOGY_SPEC"}
_BASES = {"sourced", "derived", "default"}
_STATUSES = {"confirmed", "partly"}


def _parameters() -> set[str]:
    return {
        name
        for name, value in vars(methodology).items()
        if name.isupper()
        and not name.startswith("_")
        and name not in _NOT_PARAMETERS
        and not callable(value)
    }


def test_every_parameter_has_a_source_entry():
    missing = _parameters() - PARAMETER_SOURCES.keys()
    assert not missing, f"add these to coaching/sources.py PARAMETER_SOURCES: {sorted(missing)}"


def test_no_stale_source_entries():
    stale = PARAMETER_SOURCES.keys() - _parameters()
    assert not stale, f"no such constant in methodology.py: {sorted(stale)}"


def test_entries_are_complete():
    for name, entry in PARAMETER_SOURCES.items():
        assert entry["basis"] in _BASES, name
        assert entry["rationale"].strip(), name
        for ref in entry["refs"]:
            assert ref in REFERENCES, f"{name} cites unknown reference {ref}"
        if entry["basis"] == "sourced":
            assert entry["refs"], f"{name} is sourced but cites nothing"


def test_parts_name_real_keys_and_set_the_weakest_basis():
    for name, entry in PARAMETER_SOURCES.items():
        parts = entry.get("parts")
        if not parts:
            continue
        value = getattr(methodology, name)
        assert isinstance(value, dict), f"{name} has parts but is not a dict"
        assert set(parts) == set(value), f"{name} parts must cover exactly its keys"
        assert set(parts.values()) <= _BASES, name
        weakest = min(parts.values(), key=BASIS_STRENGTH.__getitem__)
        assert entry["basis"] == weakest, f"{name} basis must be its weakest part ({weakest})"
        for key, basis in parts.items():
            if basis == "sourced":
                assert entry["refs"], f"{name}.{key} is sourced but {name} cites nothing"


def test_references_are_complete_and_used():
    cited = {ref for entry in PARAMETER_SOURCES.values() for ref in entry["refs"]}
    for ref_id, ref in REFERENCES.items():
        assert ref["short"] and ref["citation"] and ref["finding"], ref_id
        assert ref["status"] in _STATUSES, ref_id
        assert ref_id in cited, f"{ref_id} is not cited by any parameter"


def test_methodology_text_lists_every_parameter():
    section = methodology.METHODOLOGY_SPEC.split("## Where these numbers come from", 1)[1]
    for name, entry in PARAMETER_SOURCES.items():
        assert f"{name}: {entry['basis']}" in section
