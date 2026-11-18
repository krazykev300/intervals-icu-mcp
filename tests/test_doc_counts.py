"""Tool / resource / prompt counts typed into the docs must match what registers.

The counts live in several files (README, CLAUDE.md, docs/tools.md,
docs/claude-ios-coaching.md) and drifted silently before this test existed.
When a tool is added or removed, this test names every line to update.
"""

import asyncio
import importlib
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


def _read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def _server(monkeypatch: pytest.MonkeyPatch, profile: str, delete_mode: str) -> object:
    monkeypatch.setenv("INTERVALS_ICU_TOOL_PROFILE", profile)
    monkeypatch.setenv("INTERVALS_ICU_DELETE_MODE", delete_mode)
    sys.modules.pop("intervals_icu_mcp.server", None)
    return importlib.import_module("intervals_icu_mcp.server")


def _count(server: object, kind: str) -> int:
    return len(asyncio.run(getattr(server.mcp, f"list_{kind}")()))  # type: ignore[attr-defined]


@pytest.fixture
def counts(monkeypatch: pytest.MonkeyPatch) -> dict[str, int]:
    coaching = _server(monkeypatch, "coaching", "safe")
    result = {
        "coaching": _count(coaching, "tools"),
        "resources": _count(coaching, "resources"),
        "prompts": _count(coaching, "prompts"),
    }
    for mode in ("safe", "full", "none"):
        result[f"full_{mode}"] = _count(_server(monkeypatch, "full", mode), "tools")
    sys.modules.pop("intervals_icu_mcp.server", None)
    return result


def _num(pattern: str, text: str, where: str) -> list[int]:
    found = [int(n) for n in re.findall(pattern, text, re.M)]
    assert found, f"{where}: pattern {pattern!r} not found; update this test with the doc"
    return found


def test_coaching_count(counts: dict[str, int]) -> None:
    n = counts["coaching"]
    assert _num(r"\((\d+) tools: calendar", _read("README.md"), "README") == [n]
    assert _num(r"profile registers (\d+)\.", _read("README.md"), "README") == [n]
    assert _num(r"\((\d+) tools with `DELETE_MODE=safe`", _read("CLAUDE.md"), "CLAUDE.md") == [n]
    tools_md = _read("docs/tools.md")
    assert _num(r"\((\d+) tools in `safe` delete mode\)", tools_md, "docs/tools.md") == [n]
    assert _num(r"\| (\d+) tools \(`DELETE_MODE=safe`\)", tools_md, "docs/tools.md") == [n]
    ios = _read("docs/claude-ios-coaching.md")
    assert _num(r"Coaching profile \((\d+) tools\)", ios, "claude-ios-coaching") == [n]


def test_full_profile_counts(counts: dict[str, int]) -> None:
    safe, full, none = counts["full_safe"], counts["full_full"], counts["full_none"]
    readme = _read("README.md")
    assert _num(r"\(up to (\d+) tools\)", readme, "README") == [full]
    assert _num(r"(\d+) tools exist in the `full` profile", readme, "README") == [full]
    triple = r"\((\d+) / (\d+) / (\d+) with delete mode\)"
    assert re.findall(triple, _read("docs/tools.md")) == [(str(safe), str(full), str(none))]
    claude_triple = r"upstream catalog \((\d+) / (\d+) / (\d+)"
    assert re.findall(claude_triple, _read("CLAUDE.md")) == [(str(safe), str(full), str(none))]
    tools_md = _read("docs/tools.md")
    assert _num(r"up to (\d+) tools across", tools_md, "docs/tools.md") == [full]
    for mode, n in (("safe` \\(default\\)", safe), ("full`", full), ("none`", none)):
        assert _num(rf"^\| `{mode} \| (\d+) \|", tools_md, "delete table") == [n]


def test_category_tables(counts: dict[str, int]) -> None:
    tools_md = _read("docs/tools.md")
    headings: dict[str, int] = {}
    for m in re.finditer(r"^### ([^\n]+?) \((\d+) tools?\)\n(.*?)(?=^##)", tools_md, re.M | re.S):
        rows = len(re.findall(r"^\| `icu_\w+`", m.group(3), re.M))
        assert int(m.group(2)) == rows, (
            f"docs/tools.md '{m.group(1)}' says {m.group(2)}, has {rows}"
        )
        headings[m.group(1)] = rows
    assert sum(headings.values()) == counts["full_full"]
    readme_rows = re.findall(r"^\| \[(.+?)\]\(.*?\) \| (\d+) \|", _read("README.md"), re.M)
    assert {name: int(n) for name, n in readme_rows} == headings


def test_resource_and_prompt_counts(counts: dict[str, int]) -> None:
    r, p = counts["resources"], counts["prompts"]
    assert _num(r"plus (\d+) MCP Resources", _read("README.md"), "README") == [r]
    assert _num(r"(\d+) MCP Prompts", _read("README.md"), "README") == [p]
    assert _num(r"(\d+) MCP Resources", _read("docs/tools.md"), "docs/tools.md") == [r]
    assert _num(r"(\d+) MCP Prompts", _read("docs/tools.md"), "docs/tools.md") == [p]
    claude = _read("CLAUDE.md")
    assert _num(r"(\d+) resources", claude, "CLAUDE.md") == [r]
    assert _num(r"(\d+) prompts", claude, "CLAUDE.md") == [p]
