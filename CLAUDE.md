# CLAUDE.md

This file provides guidance to Claude Code when working with this repository.

## Project Overview

MCP (Model Context Protocol) server for Intervals.icu — this fork defaults to
`INTERVALS_ICU_TOOL_PROFILE=coaching` (36 tools with `DELETE_MODE=safe`: calendar,
fitness, athlete-state, ATP read, curves, wellness, activities, streams/histograms,
workout library).
`full` restores the upstream catalog (63 / 66 / 60 with delete mode). 6 resources
and 9 prompts (the named routines, `coach_with_goals`, `verify_setup`; `full`
adds upstream's analysis set). Server `instructions` plus
`intervals-icu://coaching-playbook` carry the coaching playbook (race → fitness
→ calendar); `coach_with_goals` returns the same text, and
`skills/intervals-coach/` packages it as a Claude Skill for athletes.

This repository is the source of truth for calendar, wellness, and fitness
numbers. Goals, racing identity, and constraints belong in a separate knowledge
store if you use one. Do not put Intervals API keys, athlete ids, or CTL numbers
there. A **link token** (HTTP bearer that selects an identity on this server) may
be stored as a personal secret; it is not the Intervals API key. See
`docs/identities.md`.

- **Language**: Python 3.11+
- **Framework**: FastMCP
- **API Client**: httpx (async)
- **Validation**: Pydantic v2
- **Auth**: pydantic-settings + `.env`

## Development Commands

```bash
make install          # Install dependencies
make auth             # Set up Intervals.icu credentials (.env)
make run              # Run the MCP server
make test             # Run tests
make test/athlete     # Run tests matching "athlete"
make test/verbose     # Verbose test output
make skill            # Rebuild skills/intervals-coach/ and zip it to build/
make smoke            # In-process MCP smoke of the coaching write tools (stubbed HTTP, free)
make lint             # Lint (ruff + pyright)
make format           # Auto-format code
make can-release      # Full pre-release check (same as CI)
make docker/build     # Build Docker image
make docker/run       # Run Docker container
```

## Architecture (Quick Reference)

| Component | File | Role |
|---|---|---|
| Server | `server.py` | Entry point, registers tools/resources/prompts |
| Middleware | `middleware.py` | Validates config, injects `ICUConfig` into context |
| Client | `client.py` | Async HTTP client (Basic Auth, 30s timeout) |
| Auth | `auth.py` | Loads credentials from `.env` |
| Response | `response_builder.py` | Consistent JSON structure (data/analysis/metadata) |
| Models | `models.py` | Pydantic models for API responses |
| Workout syntax | `workout_syntax.py` | Intervals.icu workout DSL reference for LLMs |
| Workout parser | `workout_parser.py` | Local linter/preview for workout descriptions |
| Tool profile | `tool_profile.py` | `INTERVALS_ICU_TOOL_PROFILE` allow-lists + `mcp.tool` / `mcp.prompt` filters |
| Identity | `identity.py` / `http_auth.py` | Link token → Intervals credentials; ASGI 401 without a bearer |
| Prompts | `prompts/` | Coaching playbook (`coaching_playbook.py`), named routines (`routines.py`), Claude Skill renderer (`skill.py`); kept out of `server.py` for rebases |
| Tools | `tools/` | 16 tool modules plus the `_strava.py` helper (see below) |

**For detailed architecture**: see `docs/architecture.md`

### Tool Categories

1. `activities.py` — Query/manage activities
2. `activity_analysis.py` — Streams, intervals, best efforts, histograms
3. `activity_messages.py` — Notes/comments on activities
4. `athlete.py` — Profile, fitness metrics (CTL/ATL/TSB)
5. `athlete_state.py` — Composite grounding read (`icu_get_athlete_state`)
6. `coaching_guide.py` — Playbook and references as a tool (`icu_get_coaching_guide`)
7. `wellness.py` — HRV, sleep, recovery
8. `events.py` — Calendar queries
9. `event_management.py` — Create/update/delete events, session layout, availability, `icu_log_session`
10. `periodization.py` — Annual Training Plan read (`icu_get_annual_training_plan`)
11. `performance.py` — Power/HR/pace curves
12. `curves.py` — HR and pace curve analysis
13. `workout_library.py` — Browse workout folders and plans
14. `gear.py` — Manage gear and reminders
15. `sport_settings.py` — FTP, FTHR, pace thresholds
16. `custom_items.py` — Charts, custom fields, zones, etc.

`_strava.py` is a helper, not a tool module: it detects Strava-synced activity stubs.

## Code Style

- **Ruff** for linting and formatting
- Line length: 100 characters
- Target: Python 3.11+
- Allow unused imports in `__init__.py` files
- Run `make format` to auto-fix style issues

## Type Checking

- **Pyright** with basic type checking mode
- Strict mode only for `src/` directory
- Run `make lint` or `uv run pyright`

## Testing

Tests use pytest + pytest-asyncio with `respx` for HTTP mocking.

**For testing conventions and examples**: see `docs/testing.md`

- **Doc counts are tested.** Tool, resource and prompt counts are typed into
  README.md, this file, `docs/tools.md` and `docs/claude-ios-coaching.md`.
  `tests/test_doc_counts.py` compares them with what the server registers, so
  adding or removing a tool fails CI until every count is updated; the failure
  names the file and pattern.
- **Playbook wording is tested.** `tests/test_coaching_playbook.py` asserts
  exact phrases in `prompts/coaching_playbook.py`. Rewording the playbook means
  updating those needles in the same change.
- **The athlete skill is generated.** `skills/intervals-coach/` is rendered
  from the playbook, the methodology and `prompts/routines.py`. After changing
  any of them run `make skill`; `tests/test_routines_and_skill.py` fails while
  the committed copy is stale. Do not edit the files under `skills/` by hand.
- **Smoke before merge.** For changes to a write tool, run `make smoke` and
  extend `scripts/smoke_mcp.py` with the new path. It drives the real server
  through a FastMCP client with the Intervals API stubbed, so it needs no
  credentials and costs nothing. `make smoke-eval` is different: it measures
  tool routing with the Anthropic API and costs money.
- **Live checks.** Worktrees have no `.env`. For a live check run `make auth`
  in the worktree (or export `INTERVALS_ICU_API_KEY` / `INTERVALS_ICU_ATHLETE_ID`).
  Prefer read tools. A live write goes on a future date and is deleted
  afterwards, which safe delete mode allows. Never write to a past date. If no
  live check was possible, say so in the PR test plan as an unchecked item.

## Further Documentation

- `docs/architecture.md` — Detailed architecture and design decisions
- `docs/tools.md` — Reference for all registered tools (and the Delete Safety Mode spec)
- `docs/examples.md` — Usage examples
- `docs/testing.md` — Testing conventions
- `docs/chatgpt-connector.md` — ChatGPT custom-connector setup walkthrough
- `docs/coaching-architecture-assessment.md` — Coaching engine assessment, recommendations R1–R12 and the phased roadmap
- `docs/coaching-data-store.md` — Design of the per-athlete coach database (schema, sign-in, privacy, backups)
- `docs/coaching-capability-backlog.md` — Further capabilities, each mapped to where it appears in Intervals.icu
- `docs/user-setup.md` — friend-facing setup: own credentials, chat-client memory, public-repo privacy boundary

### README discipline

**Keep README.md under 300 lines.** It is the front door for new users — onboarding, install, basic config, links out. Reference material (full tool inventory, deep architectural notes, exhaustive examples) belongs in `docs/`, not the README. If a new section grows past ~30 lines and isn't core onboarding, extract it to `docs/` and link from the README. The README has been trimmed before (PR #6) — don't let it bloat back.

## Working across Claude and Cursor

Both tools work in this repo, often in parallel on separate branches.

- **The backlog is the work queue.** `docs/coaching-capability-backlog.md`
  holds the items; lanes in a request name which items one agent owns, in
  order. Do only the items named.
- **Mark items done in the backlog** with a `**Done:**` line under the item:
  what shipped and anything not yet checked live. Section 0 shows the closed
  form.
- **One writer per file set.** Lanes are split so two agents do not edit the
  same files. `tools/event_management.py` and `prompts/coaching_playbook.py`
  are the usual collision points; if a lane needs a file another lane owns,
  stop and ask.
- **Each lane ships as its own PR** from a branch off the latest `main`.

## Skills

The following developer skills are available in `.claude/skills/` (the
athlete-facing coach skill is separate, in `skills/intervals-coach/`):

| Skill | Description |
|---|---|
| `/commit` | Analyze changes and create conventional commits |
| `/add-tool` | Step-by-step workflow for adding new MCP tools |
| `/release-check` | Run pre-release verification and summarize results |
| `/release-write` | Draft GitHub Release notes from CHANGELOG, tag, and publish |

## Verification

**Always run `make can-release` before finishing any feature work.** This runs the full test and lint suite, matching what CI checks on every push.

## Merging PRs

PRs are **squash-merged only** (repo setting: commit title from `PR_TITLE`, body `BLANK`). The PR title becomes the single `main` commit subject with ` (#N)` appended — write PR titles as single-line conventional commits (≤ ~70 chars), and edit non-conforming community PR titles before merging.

## Releases

CHANGELOG.md is **manual** — there is no automated changelog generation. Entries are the **maintainer's responsibility**: community PRs deliberately do not include them (CONTRIBUTING.md and the PR template say so, to avoid `[Unreleased]` merge conflicts and keep SemVer classification in one place). Add the `[Unreleased]` bullet at merge time, while the PR context is fresh. When the maintainer has an agent (Claude or Cursor) build and merge a change, the agent writes that bullet in the same PR; `/release-check` verifies every user-facing commit since the last tag has an entry before a release is cut. The only release-related automation:
- Package version comes from the git tag via `hatch-vcs` (no `pyproject.toml` bump needed)
- `publish.yml` syncs `server.json` version from the tag and publishes to PyPI + MCP Registry
- `release.yml` builds and pushes the Docker image

To cut a release:
1. Rename `## [Unreleased]` → `## [X.Y.Z] — YYYY-MM-DD` in CHANGELOG.md
2. Commit (e.g., `chore(release): X.Y.Z`)
3. Tag and push: `git tag vX.Y.Z && git push origin main vX.Y.Z`

Follow SemVer with the narrowed contract defined in the CHANGELOG header. **Major** (breaking): removing or renaming a tool or tool parameter, changing config env var semantics, changing which tools register by default, or removing information from a response. **Minor**: response-shape changes that preserve the information (key renames, restructuring, added fields) — MCP responses are read dynamically by LLMs, not parsed by typed clients. Releases ≤ 4.0.0 predate this policy and treated any response-shape change as breaking.

### Deferred breaking changes (batch into the next major)

**Prefer non-breaking fixes and ship them continuously** — add fields, or accept aliases (e.g. `icu_bulk_create_events` accepts `event_type` as an alias for the API's `type`). Most interface inconsistencies can be fixed this way; don't defer a fix that can be non-breaking. Only when a change *must* break the contract (renaming/removing a tool or parameter with no alias path, dropping an accepted alias, changing env-var semantics or default registration) do we **defer it and batch all such changes into one planned major** — so consumers migrate once and the cleaned-up interface is designed holistically, not dribbled out across majors.

Running list of deferred breaking cleanups (do together in the next major; keep this list current as more are found):

- _(empty — the accumulated items were drained in 5.0.0: create/bulk field-name unification, the no-op gear params, and the synthesized curve zone blocks. Add new entries here as they are found.)_

## Important Files

- `.env` — Local credentials (not in git)
- `.env.example` — Template for credentials
- `openapi-spec.json` — Intervals.icu API specification. Kept up to date automatically via `.github/workflows/update-openapi.yml` (or run `curl -s https://intervals.icu/api/v1/docs > openapi-spec.json` to update locally).
- `uv.lock` — Locked dependencies (commit this)
- `.github/workflows/test.yml` — CI tests
- `.github/workflows/release.yml` — Docker release automation
- `.github/workflows/deploy-host.yml` — optional self-hosted `host-pull.sh` after the live branch is green
