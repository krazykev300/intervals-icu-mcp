# Coaching data store: design

Companion to [coaching-architecture-assessment.md](coaching-architecture-assessment.md)
(recommendation R1). It covers what the server stores about each athlete, where,
and how that data is protected, backed up and deleted.

## 1. The governing rule

**Intervals.icu is the interface and the record. The server is the coach.**

Intervals plays the role TrainingPeaks would: it is where the athlete looks at
the plan, the sessions and the data. So:

- Anything the athlete should see or edit lives in Intervals.
- The server's database holds only what Intervals has no place for.
- When the two disagree, Intervals wins. An athlete who drags a workout to
  another day in the Intervals calendar has changed the plan; the coach adapts.
- If the database is lost, the athlete loses the coach's memory and history.
  The plan, the sessions and all training data are still in Intervals.

| Lives in Intervals.icu | Lives in the coach database |
|---|---|
| Races, planned sessions, phases, weekly targets | The standing profile: weekly availability, fixed sessions, equipment, sport roles, preferences |
| One-off availability: holidays, travel, limited-time days | Coach notes and corrections, with expiry |
| Illness and injury periods | The decision log: what was proposed, approved, moved, and why |
| Wellness, including coach-computed custom fields | Plan metadata: parameters and version of each approved plan |
| Activities, coach comments on activities | Session verdicts and progression history |
| FTP, zones, thresholds | Identities, hashed link tokens, encrypted Intervals credentials |
| The coach's workout library folder | Operational records: job state, tool-call log, webhook inbox |

Never stored in the database: fitness numbers that Intervals computes (CTL,
ATL, form), race dates, and activity data. They are read live or cached in
memory.

## 2. Engine and layout

**SQLite, one file, on the home server.**

- Path from `INTERVALS_ICU_COACH_DB`, default `data/coach.db`. The directory is
  mode 700 and the file 600, owned by the service user. `data/` is gitignored.
- WAL journal mode, `foreign_keys=ON`, `busy_timeout=5000`,
  `synchronous=NORMAL`.
- Accessed through one small module, `coaching/store/`, with typed functions
  and Pydantic models. No ORM. Calls run off the event loop (`aiosqlite` or
  `asyncio.to_thread`).
- One process writes. Write transactions are short.

Why this and not the alternatives:

- **Postgres:** a second service to run, back up and upgrade, for fewer than
  twenty users on one host.
- **JSON files:** no safe concurrent writes, no history, no queries. Two chats
  open at once would overwrite each other.
- **Storing the profile inside Intervals** (a far-future note event, the
  athlete bio): fragile, visible in odd places, and editable by accident.
- **Only the owner's separate knowledge store:** friends do not have one, and
  the engine cannot read it. That store keeps identity and the story of why;
  this one keeps what the engine computes with.

## 3. Schema

Times are UTC ISO-8601 text. Dates are the athlete's local date. JSON columns
are validated by Pydantic before every write.

### Tenancy and access

```sql
CREATE TABLE athletes (
  athlete_id    TEXT PRIMARY KEY,           -- Intervals id, e.g. i12345
  display_name  TEXT NOT NULL,
  timezone      TEXT,                       -- cached from the Intervals profile
  role          TEXT NOT NULL DEFAULT 'athlete'
                CHECK (role IN ('owner','athlete')),
  status        TEXT NOT NULL DEFAULT 'active'
                CHECK (status IN ('active','paused','deleted')),
  consent_at    TEXT,                       -- when they agreed to storage
  created_at    TEXT NOT NULL,
  updated_at    TEXT NOT NULL
);

CREATE TABLE credentials (
  athlete_id        TEXT PRIMARY KEY REFERENCES athletes ON DELETE CASCADE,
  kind              TEXT NOT NULL CHECK (kind IN ('api_key','oauth')),
  secret_ciphertext BLOB NOT NULL,          -- AES-GCM; key is not in the DB
  scopes            TEXT,
  created_at        TEXT NOT NULL,
  rotated_at        TEXT
);

CREATE TABLE link_tokens (
  token_hash    TEXT PRIMARY KEY,           -- SHA-256 of the token
  athlete_id    TEXT NOT NULL REFERENCES athletes ON DELETE CASCADE,
  label         TEXT NOT NULL,              -- 'claude-ios', 'cursor-laptop'
  created_at    TEXT NOT NULL,
  last_used_at  TEXT,
  revoked_at    TEXT
);
```

Notes:

- Link tokens are 256-bit random values, so a plain SHA-256 is enough; a slow
  password hash adds nothing. The token itself is shown once, at issue.
- Several tokens per athlete, each labelled and separately revocable. Today
  one token per identity lives in plaintext in `identities.json`.
- The encryption key comes from `INTERVALS_ICU_COACH_KEY` or a key file with
  mode 600, outside the database and outside backups of the database.
- `.env` single-identity mode keeps working for stdio and for the simplest
  install. The database is used when it exists.

### Profile

```sql
CREATE TABLE profiles (
  athlete_id      TEXT PRIMARY KEY REFERENCES athletes ON DELETE CASCADE,
  schema_version  INTEGER NOT NULL,
  doc             TEXT NOT NULL,            -- JSON, see below
  revision        INTEGER NOT NULL,
  updated_at      TEXT NOT NULL,
  updated_by      TEXT NOT NULL             -- 'chat', 'admin', 'import'
);

CREATE TABLE profile_revisions (
  athlete_id  TEXT NOT NULL REFERENCES athletes ON DELETE CASCADE,
  revision    INTEGER NOT NULL,
  doc         TEXT NOT NULL,
  patch       TEXT NOT NULL,                -- the merge patch applied
  reason      TEXT NOT NULL,                -- why, in the athlete's words
  created_at  TEXT NOT NULL,
  PRIMARY KEY (athlete_id, revision)
);
```

One JSON document per athlete, with every change kept. Updates carry the
revision they were based on; a stale revision is rejected, so two open chats
cannot silently overwrite each other.

The document:

```json
{
  "goals": [
    {"text": "Finish the gravel 200 strong", "priority": 1,
     "event_id": 133432723}
  ],
  "weekly_hours": {"typical": 10, "max": 14},
  "availability": {
    "mon": {"max_minutes": 60, "indoor_only": true},
    "tue": {"max_minutes": 120},
    "sat": {"max_minutes": 360}
  },
  "fixed_sessions": [
    {"name": "Tuesday group ride", "weekday": "tue", "sport": "Ride",
     "minutes": 110, "really_is": "vo2", "negotiable": false}
  ],
  "sports": {
    "primary": "Ride",
    "secondary": [{"sport": "Run", "purpose": "enjoyment", "enabled": true}],
    "strength": {"enabled": true, "access": "gym", "experience": "returning"}
  },
  "equipment": {"power_meter": true, "smart_trainer": true, "hr_strap": true},
  "health": {
    "age_band": "30-39",
    "notes": [{"text": "Left knee: avoid deep single-leg work",
               "review_by": "2027-01-15"}]
  },
  "preferences": {"tone": "direct", "detail": "short", "units": "metric"},
  "race_demands": [
    {"event_id": 133432723, "duration_h": 8, "kilojoules": 5500,
     "decisive": "repeated 5-10 minute climbs late"}
  ]
}
```

Rules for the document:

- Every field is optional. Missing fields appear in `gaps` on
  `icu_get_athlete_state` and drive the onboarding interview.
- One-off changes do not go here. A week away is a `HOLIDAY` event in
  Intervals with `training_availability` and `max_training_time`; the engine
  reads both and the event overrides the weekly template.
- No fitness numbers, no thresholds, no dates of races. Those are read from
  Intervals; the profile references events by id.

### Coach notes

```sql
CREATE TABLE coach_notes (
  id             INTEGER PRIMARY KEY,
  athlete_id     TEXT NOT NULL REFERENCES athletes ON DELETE CASCADE,
  kind           TEXT NOT NULL CHECK (kind IN
                 ('correction','preference','observation','context')),
  text           TEXT NOT NULL,             -- one or two sentences
  source         TEXT NOT NULL CHECK (source IN
                 ('athlete_said','coach_inferred')),
  valid_from     TEXT NOT NULL,
  valid_until    TEXT,                      -- NULL means until superseded
  superseded_by  INTEGER REFERENCES coach_notes,
  created_at     TEXT NOT NULL
);
```

Free-text memory that does not fit a profile field. The important kind is
`correction`: when the athlete says the coach got something wrong ("stop
scheduling intervals the day after my long ride"), it becomes a standing rule
returned in every brief.

Lifecycle:

- `athlete_said` notes are trusted. `coach_inferred` notes are shown to the
  athlete for confirmation before they are stored.
- Notes about temporary states carry `valid_until`. Expired notes stop being
  returned and are listed once as "still true?".
- The state call returns at most the ten most relevant active notes, capped in
  length, so memory cannot grow the prompt without bound.

### Decision log

```sql
CREATE TABLE decisions (
  id          INTEGER PRIMARY KEY,
  athlete_id  TEXT NOT NULL REFERENCES athletes ON DELETE CASCADE,
  ts          TEXT NOT NULL,
  local_date  TEXT NOT NULL,
  kind        TEXT NOT NULL,   -- plan_approved, week_written, session_moved,
                               -- session_skipped, target_overridden,
                               -- readiness_call, replan, profile_changed
  actor       TEXT NOT NULL CHECK (actor IN ('coach','athlete','job')),
  summary     TEXT NOT NULL,
  payload     TEXT,            -- JSON detail
  rule_ids    TEXT,            -- JSON: knowledge-base rules that applied
  event_ids   TEXT             -- JSON: Intervals events touched
);
CREATE INDEX decisions_by_athlete ON decisions (athlete_id, local_date);
```

Append-only. It answers "why is this on my calendar?" and makes multi-day
rules computable: a key session moved twice, two red days in a row, an
overruled warning.

### Plans and coach-written events

```sql
CREATE TABLE plans (
  id             INTEGER PRIMARY KEY,
  athlete_id     TEXT NOT NULL REFERENCES athletes ON DELETE CASCADE,
  status         TEXT NOT NULL CHECK (status IN
                 ('proposed','active','superseded','completed')),
  goal_event_id  INTEGER,
  start_date     TEXT NOT NULL,
  end_date       TEXT NOT NULL,
  params         TEXT NOT NULL,   -- JSON: ramp tier, hours cap, tolerance,
                                  -- engine and knowledge-base versions
  created_at     TEXT NOT NULL,
  approved_at    TEXT,
  superseded_at  TEXT
);

CREATE TABLE plan_weeks (
  plan_id          INTEGER NOT NULL REFERENCES plans ON DELETE CASCADE,
  week_start       TEXT NOT NULL,
  phase            TEXT NOT NULL,
  kind             TEXT NOT NULL CHECK (kind IN
                   ('load','recovery','taper','race','transition')),
  load_target      INTEGER NOT NULL,
  hours_target     REAL,
  planned_ctl      REAL,          -- from the simulation
  target_event_id  INTEGER,       -- the Intervals TARGET event
  PRIMARY KEY (plan_id, week_start)
);

CREATE TABLE coach_events (
  event_id       INTEGER PRIMARY KEY,   -- Intervals event id
  athlete_id     TEXT NOT NULL REFERENCES athletes ON DELETE CASCADE,
  plan_id        INTEGER REFERENCES plans ON DELETE SET NULL,
  external_id    TEXT NOT NULL UNIQUE,  -- also set on the Intervals event
  role           TEXT NOT NULL,         -- key, support, optional
  stimulus       TEXT NOT NULL,         -- vo2, threshold, endurance, ...
  original_date  TEXT NOT NULL,
  scheduled_date TEXT NOT NULL,         -- where it sits now
  moves          INTEGER NOT NULL DEFAULT 0,
  content_hash   TEXT NOT NULL,         -- to detect edits made in Intervals
  status         TEXT NOT NULL CHECK (status IN
                 ('planned','done','skipped','deleted')),
  written_at     TEXT NOT NULL
);
```

The plan's content is in Intervals. These tables record what was approved and
what the coach wrote, so the engine can tell:

- which calendar entries are the coach's and which the athlete added;
- that an event was moved or edited in the Intervals UI since it was written;
- how the season looked when it was approved, after later re-plans.

`coach_events` can be rebuilt from Intervals by listing events whose
`external_id` starts with the coach prefix. It is a convenience, not a second
source of truth.

### Session outcomes and progression

```sql
CREATE TABLE session_reviews (
  activity_id     TEXT PRIMARY KEY,
  athlete_id      TEXT NOT NULL REFERENCES athletes ON DELETE CASCADE,
  event_id        INTEGER,
  local_date      TEXT NOT NULL,
  sport           TEXT NOT NULL,
  stimulus        TEXT NOT NULL,
  dose            REAL,            -- minutes in the target zone, or km, or sets
  verdict         TEXT NOT NULL CHECK (verdict IN
                  ('hit','partial','missed','overdone','unplanned')),
  rpe             INTEGER,
  feel            INTEGER,
  metrics         TEXT,            -- JSON: decoupling, drift, interval table
  engine_version  TEXT NOT NULL,
  reviewed_at     TEXT NOT NULL
);

CREATE TABLE progression (
  athlete_id     TEXT NOT NULL REFERENCES athletes ON DELETE CASCADE,
  sport          TEXT NOT NULL,
  system         TEXT NOT NULL,    -- endurance, tempo, threshold, vo2, ...
  as_of          TEXT NOT NULL,
  rung           INTEGER NOT NULL,
  best_dose      REAL NOT NULL,
  last_stimulus  TEXT,
  PRIMARY KEY (athlete_id, sport, system, as_of)
);
```

These are derived from Intervals data, but kept because a verdict should not
change retroactively when the engine's rules change, and because a level
history is what shows the athlete they are progressing.

### Daily record and operations

```sql
CREATE TABLE daily_briefs (
  athlete_id      TEXT NOT NULL REFERENCES athletes ON DELETE CASCADE,
  local_date      TEXT NOT NULL,
  readiness       TEXT,
  brief           TEXT NOT NULL,   -- JSON as returned
  engine_version  TEXT NOT NULL,
  kb_version      TEXT NOT NULL,
  delivered       TEXT,            -- JSON: which channels, when
  PRIMARY KEY (athlete_id, local_date)
);

CREATE TABLE tool_calls (
  id           INTEGER PRIMARY KEY,
  athlete_id   TEXT,
  ts           TEXT NOT NULL,
  tool         TEXT NOT NULL,
  ok           INTEGER NOT NULL,
  duration_ms  INTEGER,
  error_type   TEXT,
  warnings     INTEGER             -- validator findings returned
);

CREATE TABLE jobs (
  name        TEXT NOT NULL,
  athlete_id  TEXT NOT NULL,
  last_run    TEXT,
  last_status TEXT,
  PRIMARY KEY (name, athlete_id)
);

CREATE TABLE webhook_inbox (
  id            INTEGER PRIMARY KEY,
  received_at   TEXT NOT NULL,
  athlete_id    TEXT,
  type          TEXT NOT NULL,
  payload       TEXT NOT NULL,
  processed_at  TEXT
);
```

- `daily_briefs` records what the coach said each day, which makes "two red
  days in a row" a query and lets a later audit see the advice given.
- `tool_calls` holds no arguments and no free text, only shape and outcome.
- The read cache for Intervals data stays in memory. It is not worth
  persisting.

## 4. How the model reads and writes memory

**Read.** `icu_get_athlete_state` returns `coach_profile`, active notes, and
standing corrections. The model never asks for memory separately, so it cannot
forget to.

**Write.** Two tools, both annotated as writes:

- `icu_update_coach_profile(patch, reason, based_on_revision)` for structured
  fields.
- `icu_remember(text, kind, valid_until?)` for notes.

Rules given to the model, and enforced where they can be:

- Save only durable facts the athlete stated. Not moods, not today's legs.
- Say what was saved in the reply, in one line, so the athlete can object.
- Never save fitness numbers, thresholds, race dates or credentials. The
  server rejects patches containing fields outside the schema.
- Temporary conditions get an end date.
- Text from the profile and notes is returned to the model marked as
  athlete-supplied data, length-capped, never as instructions.

**Forget.** `icu_forget(note_id)` and profile patches that set a field to
null. Deletions are logged in `decisions` without the deleted content.

## 5. Identity and sign-in

### Today

A link token in the Claude connector header selects an identity. Tokens and
Intervals API keys sit in plaintext in `.env` or `identities.json`.

### Step 1: move identities into the database

- Admin commands on the existing CLI entry point:
  - `admin add-athlete <intervals-id> --name ...` (prompts for the API key).
  - `admin issue-token <intervals-id> --label claude-ios` (prints once).
  - `admin revoke-token`, `admin list`, `admin pause`.
  - `admin import-identities deploy/host.local/identities.json`.
- The HTTP gate looks up `SHA-256(token)` and updates `last_used_at`.
- An unused-token report shows which devices are still live.

### Step 2: sign in with Intervals (for friends)

Intervals.icu supports OAuth apps, and its access tokens do not use refresh
tokens. Registering this server as a personal OAuth app gives two things:

- Friends authorize in their own Intervals account instead of pasting an API
  key to the owner.
- Webhooks, which Intervals delivers only to OAuth apps.

The cleanest form is the standard connector sign-in: the server acts as an
OAuth server to Claude and delegates to Intervals (FastMCP ships an OAuth
proxy for this). A friend adds the connector URL, clicks sign in, logs in to
Intervals, and is done. No tokens are pasted anywhere. Link tokens remain as
the simple path for the owner and for other MCP clients.

Check before building: the scopes an OAuth app can request cover calendar
writes and wellness; whether a personal-use app is acceptable under the API
terms; and how Claude's connector sign-in behaves behind a Tailscale Funnel
path prefix.

### Tenancy rule

Every store function takes the athlete id from the authenticated request,
never from a tool argument. The optional `athlete_id` parameter on existing
tools keeps its meaning for Intervals calls (Intervals enforces access there),
but the coach database ignores it unless the caller's role is `owner` and the
target athlete has agreed to be viewed.

## 6. Privacy

The database will hold health notes about other people. Keep that small and
under their control.

- **Consent.** The onboarding interview states what is stored and where, and
  records `consent_at`. Without it the coach works statelessly, as today.
- **Minimum necessary.** Health notes are what the coach needs to avoid harm,
  in the athlete's own words, with a review date. No diagnoses are inferred.
- **Export.** `admin export <athlete>` writes everything held about one person
  as JSON. A tool, `icu_export_my_coach_data`, gives the athlete the same from
  chat.
- **Delete.** `admin delete <athlete>` removes every row through the foreign
  keys and revokes tokens. It does not touch Intervals.
- **Owner visibility.** The owner can administer but should not read friends'
  notes by default. Admin commands that print profile content say so and are
  logged.
- **Logs.** No profile text, note text or credentials in application logs or
  in `tool_calls`.
- **At rest.** Credentials are encrypted in the database. For the rest, rely
  on full-disk encryption on the host; a database-level cipher adds operational
  risk for little gain at this scale.

## 7. Backup, migration, retention

**Backup.**

- A nightly timer runs SQLite's online backup to `data/backups/coach-YYYYMMDD.db`
  and keeps fourteen days.
- Optional off-host copy with Litestream or restic. The encryption key is
  backed up separately from the database.
- A restore is rehearsed once: stop the service, copy a backup into place,
  start, run `admin check`.

**Migrations.**

- Numbered SQL files in `coaching/store/migrations/`, applied at startup in a
  transaction, tracked with `PRAGMA user_version`.
- The service takes a backup before applying any migration.
- Forward-only. Profile documents carry `schema_version` and are upgraded on
  read.

**Retention.**

| Data | Kept |
|---|---|
| Profile, revisions, notes, decisions, plans | Until the athlete is deleted |
| Session reviews, progression | Until the athlete is deleted |
| Daily briefs | Two years |
| Tool-call log | Ninety days |
| Webhook inbox | Thirty days after processing |

## 8. Syncing with Intervals

The server writes to Intervals and remembers what it wrote. Drift is expected,
because the athlete edits the calendar by hand.

- **On every state call:** list coach events in the window, compare
  `content_hash` and date with `coach_events`, and record moves, edits and
  deletions as athlete decisions. The brief mentions them ("you moved Thursday's
  threshold session to Friday; Saturday's long ride is now the day after").
- **With webhooks** (after OAuth): `CALENDAR_UPDATED` triggers the same
  reconciliation immediately, and `ACTIVITY_ANALYZED` triggers the session
  review. Verify the shared secret, store the payload in `webhook_inbox`,
  answer 2xx at once, process afterwards, and tolerate duplicates.
- **Without webhooks:** a job polls every fifteen minutes for API-key
  athletes. Intervals does not send activity webhooks for Strava-sourced
  activities, so polling stays as the fallback either way.
- **Idempotent writes:** every coach write sets `external_id`. A retry looks
  the event up by that id and updates it instead of creating a duplicate.

## 9. Tests

- Tenancy: athlete A's token cannot read or change athlete B's rows through
  any tool, including with an explicit `athlete_id` argument.
- No plaintext secrets: a scan of the database file after a full test run
  finds neither the API key nor a link token.
- Concurrency: two profile updates on the same revision; one is rejected.
- Migrations: every migration applies to a copy of the previous schema with
  data in it.
- Delete: after `admin delete`, no row mentions the athlete id.
- Loss: with an empty database and a populated Intervals calendar,
  `coach_events` is rebuilt and the coach keeps working.

## 10. Build order

1. Store module, migrations, `athletes`, `profiles`, `profile_revisions`,
   `coach_notes`, `decisions`. State integration and the two write tools.
   Backup timer.
2. `link_tokens` and `credentials` with the admin commands; import the
   identities file; retire plaintext tokens.
3. `coach_events` with `external_id` on every write and reconciliation on the
   state call.
4. `session_reviews`, `progression`, `daily_briefs` as the features that use
   them arrive.
5. `plans`, `plan_weeks` with the season planner.
6. Intervals OAuth, connector sign-in, `webhook_inbox`.
