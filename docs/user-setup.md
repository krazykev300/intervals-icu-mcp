# MCP user setup (share this with friends)

How to run the same Intervals.icu coaching workflow on **your** account. This
page is for people who want to talk to Claude (or another MCP client) about
their own training — not for people contributing code.

Developer install, tests, and adding tools live in the [README](../README.md)
and [CONTRIBUTING.md](../CONTRIBUTING.md).

## What you get

A local MCP server that your chat client starts on demand. It calls the
Intervals.icu API with **your** key and answers questions about **your**
activities, wellness, fitness (CTL/ATL/TSB), calendar, and workouts.

| This repo is | This repo is not |
| --- | --- |
| Open-source MCP server code + docs | A hosted service, or anyone else's Intervals.icu data |
| Started by *your* Claude / Cursor / ChatGPT | A home-automation stack, second "brain" MCP, or shared knowledge graph |
| Stateless — each tool call hits Intervals.icu live | A store of race calendars, CTL numbers, or API keys |

Friends share **this guide and the repo**. They do not share API keys, `.env`
files, athlete IDs, or a running HTTP URL.

## What you need

1. An [Intervals.icu](https://intervals.icu) account (free tier is enough to try).
2. An MCP client: [Claude Desktop](https://claude.ai/download), [Claude Code](https://docs.anthropic.com/en/docs/claude-code), [Cursor](https://cursor.com), or ChatGPT with Developer Mode (paid plan).
3. [uv](https://github.com/astral-sh/uv) — `brew install uv` on macOS/Linux, or the PowerShell installer on Windows. `uvx` ships with it and downloads the server the first time the client launches it.

No extra home server, tunnel, or second MCP is required for the usual workflow.

## 1. Get your Intervals.icu credentials

1. Open https://intervals.icu/settings → **Developer** → **Create API Key**.
2. Copy the key.
3. Copy your **Athlete ID** from your profile URL (looks like `i123456`).

Keep both on your machine only. Treat the API key like a password: it can read
and write your calendar, wellness, and activities.

## 2. Point your client at the server

The recommended path is `uvx` — nothing to clone. Paste one of the snippets
from the README [Client Configuration](../README.md#client-configuration)
section (Claude Desktop, Claude Code, or Cursor) and put **your** key and
athlete ID in the `env` block.

Claude Desktop (macOS:
`~/Library/Application Support/Claude/claude_desktop_config.json`; Windows:
`%APPDATA%\Claude\claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "intervals-icu": {
      "command": "uvx",
      "args": ["intervals-icu-mcp"],
      "env": {
        "INTERVALS_ICU_API_KEY": "your-api-key-here",
        "INTERVALS_ICU_ATHLETE_ID": "i123456"
      }
    }
  }
}
```

Restart the client. In Claude Code, run `/mcp` and confirm `intervals-icu` is
connected. In Cursor, open **Settings → MCP**.

Want to run from a git checkout or Docker instead? Use the matching snippet in
the same README section.

## 3. Confirm it works

In a new chat, ask:

```
Show me my activities from the last 7 days.
```

You should get a list from *your* Intervals.icu account. If the client offers
MCP prompts, run **`verify_setup`** — it walks the core tools (profile, fitness,
activities, calendar, wellness, a create/update/delete note) and prints a
pass/fail table.

If something fails, the usual causes are a typo in the API key, the wrong
athlete ID, or the client not restarted after the config change.

## The shared workflow

Once the server is connected, talk in plain language. The model calls tools; you
do not have to name them.

```
"Am I overtraining? Check my CTL, ATL, and TSB"
"How's my recovery this week? Show HRV and sleep trends"
"What's on my calendar this week?"
"Create a sweet spot cycling workout for tomorrow"
"What's my 20-minute power and FTP?"
```

For training questions the server steers the model to read your current state
first (`icu_get_athlete_state`), then follow its coaching guide: race →
fitness → calendar. It proposes changes in chat and writes them to your
Intervals.icu calendar only when you say yes.

Named routines (listed as prompts if your client shows them; the plain
phrase works too): `morning_check`, `review_my_week`, `plan_next_week`,
`race_week`, `after_the_race`, `im_sick`, `i_have_45_minutes`. Also
`coach_with_goals` (the whole playbook) and `verify_setup`.

### Install the coach skill (optional)

A Claude Skill makes Claude start coaching the moment the conversation turns
to training, and read your current state before it answers. It is a more
reliable trigger than the server's own instructions. Install it once; the
server still delivers the full, current coaching guide through a tool, so
clients without skills lose nothing.

- **Claude web or desktop app:** get `intervals-coach.zip` (from a checkout,
  `make skill` writes it to `build/`; or zip the
  [`skills/intervals-coach`](../skills/intervals-coach) folder so the folder
  is at the top of the zip). In Claude's settings, find **Skills** (under
  Capabilities or Customize, depending on the version), upload the zip, and
  switch it on.
- **Claude Code:** copy the folder to `~/.claude/skills/intervals-coach/`.

The skill holds no credentials and nothing about you. It only works in a chat
where the Intervals.icu connector is enabled.

More examples: [examples.md](examples.md). Full tool list: [tools.md](tools.md).

The default tool profile is `coaching` (calendar, fitness, wellness,
activities, curves, workout library). Set `INTERVALS_ICU_TOOL_PROFILE=full` in
the `env` block for the whole catalog (gear, custom items, activity edits) —
see [tools.md](tools.md#tool-profile).

Writes (calendar events, wellness) go **straight to Intervals.icu**. Glance at
the Intervals calendar before you ride. Destructive tools default to
`INTERVALS_ICU_DELETE_MODE=safe` (future events only) — see
[tools.md](tools.md#delete-safety-mode).

## Where your personal context lives

This server does not remember you between chats. Fitness data is fetched from
Intervals.icu when the model calls a tool. That is enough for most questions.

For goals, constraints, and "who I am as an athlete," pick one of these — all
are local to **your** client, and none of them are part of this repository:

| Approach | When to use | What to put there |
| --- | --- | --- |
| **Fetch every prompt** (default) | Starting out, or you want numbers that cannot go stale | Nothing extra. Ask, and the model pulls Intervals.icu. |
| **Chat client memory** | Claude / ChatGPT / Cursor already remember facts you told them | Goals, immovable sessions, injuries, "I race as a runner who also rides." Not API keys. Not CTL/ATL — those change; ask the MCP. |
| **A notes file you keep** | You want the same brief in every new chat | A short markdown file on your machine (or a paste at the top of the chat). Same rule: intent and constraints, not secrets or live fitness numbers. |

You do not need another MCP, a shared memory service, or anyone else's
knowledge store. If a friend runs this, they use their own Intervals.icu key
and their own client memory.

## What not to share

- `INTERVALS_ICU_API_KEY`, athlete IDs used as credentials, or a `.env` file
- A screenshot of your Claude config that still has the real key in it
- An HTTP / tunnel URL that reaches a server running *your* credentials, or the
  link token that unlocks it — anyone with both can read and write your
  Intervals.icu account (see [identities.md](identities.md))

Sharing the git repo, this page, and example *prompts* is the intended way to
pass the workflow along.

## Optional: phone or ChatGPT (HTTP)

Claude Desktop, Claude Code, and Cursor speak **stdio** and keep the server on
your laptop. Claude.ai, Claude iOS, and ChatGPT call a **public HTTPS URL**
from their cloud, so you must run HTTP yourself and put a tunnel in front.

That is a different, easier-to-get-wrong setup. Read
[remote-deployment.md](remote-deployment.md) before you bind anything except
`127.0.0.1`, then [self-host.md](self-host.md) and
[identities.md](identities.md) for link-token auth, and
[claude-connector.md](claude-connector.md) or
[chatgpt-connector.md](chatgpt-connector.md) for the client side. Do not
publish an HTTP server without a link token.

## This repository vs your data (public-GitHub checklist)

`main` is source code, tests with fake IDs, and docs. It is safe to keep public
when all of the following stay true:

- `.env` and `.env.local` stay gitignored (they already are)
- No real API key, link token, or athlete credential is committed — tests use
  placeholders such as `i123456` / `your_api_key_here`
- No training logs, wellness exports, race lists, or home hostnames live in
  the tree
- Deploy overlays (systemd units with real `User=` / paths, Tailscale
  MagicDNS names, identity files) stay on the machine that runs the server,
  not in git — only the `deploy/*.example` templates are committed, and
  `deploy/host.local/` is gitignored
- A personal knowledge store, home-lab layout, or other MCP you use privately
  is **not** a dependency of this project; the server only defers to a goals
  MCP if you connect one yourself

If you add a branch that describes a private home layout, treat that branch as
sensitive even when `main` is clean — GitHub shows every pushed branch on a
public repo.
