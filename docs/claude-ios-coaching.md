# Claude iOS: race → fitness → calendar

The **coaching skill lives on the MCP**, not in a kickoff you paste:

- FastMCP **server instructions** (every session that has this connector on)
- Resource `intervals-icu://coaching-playbook`
- Prompt `coach_with_goals` (same text; invoke if the client lists prompts)

On iOS: new chat → enable this connector (and Drive/GCal/Strava/goals if you
use them) → say what you need (“help me coach toward my next race”). You do
not have to manage the four-step loop; the model should. Writes still go
**straight to Intervals.icu** — glance at the calendar before you ride.

Connector URL/Funnel: [claude-connector.md](claude-connector.md). Source of
the skill text: `src/intervals_icu_mcp/prompts/coaching_playbook.py`.

## One chat, all the tools

On iOS, connectors are **per conversation**. Start a new chat and enable:

| Connector | Role |
| --- | --- |
| **This server** (`intervals-icu`) | Dates, A/B/C races, planned workouts, CTL/ATL/form, curves, wellness, activities |
| Google Drive / Sheets | Race list or season spreadsheet *if you keep one* |
| Google Calendar | Life conflicts, travel, “I already blocked Tuesday” |
| Strava (if you have an MCP) | Course, elevation, past efforts on that route — **not** the planned calendar |
| Goals / identity MCP (optional) | *Why* this race matters, limiter, constraints. Never the race date or CTL |

If a connector is missing, say so in the first message (“no Strava this
week”) so the model does not pretend it pulled a route.

The kickoff below is a **fallback** if the client ignores server instructions.
Prefer a plain ask: “Coach me toward my next race.”

## Isolation (do not skip)

| Lives in Intervals | Lives in Drive / GCal / goals MCP / chat |
| --- | --- |
| Race **date**, A/B/C, planned workouts, CTL/ATL/TSB, curves | Intent, “this is the A race because…”, family/work constraints |
| Strength and group-ride **sessions** once you agree | The spreadsheet row *before* it is logged here |

Do **not** ask the model to save Intervals API keys, athlete ids, or CTL
numbers into Drive or a knowledge store. After a race exists here, **this
calendar is WHEN**. A date in a sheet is a hint until it is an Intervals
event.

## Kickoff (paste into a new iOS chat)

```
You are coaching from my phone. Use intervals-icu for calendar, fitness,
curves, wellness, and activities. Use Drive/GCal if they are connected for
hints only. Use Strava if connected for course/history. Use a goals MCP
for why I race, not for dates.

Do this in order. Propose in chat. Do not write Intervals events until I
say yes.

1. Upcoming race: find it (sheet, GCal, or this chat). Check
   icu_get_calendar_events so we do not duplicate. If it is not on
   Intervals, ask A/B/C and Ride vs Run, then icu_create_event
   (RACE_A/B/C + event_type). Dates stay here, not in a knowledge store.

2. Fitness vs that race: icu_get_fitness_summary, icu_get_fitness_chart,
   icu_get_sport_settings, icu_get_power_curves (and HR/pace if relevant),
   recent similar activities. Pull race demands from Strava or the web
   (distance, elevation, duration). Tell me the gap in plain language.

3. Schedule: first list immovable sessions I already do (e.g. Tuesday VO2
   group ride, Saturday long ride). Read the Intervals calendar for that
   range. Draft the other days around those. After I approve, write
   WORKOUT events (workout syntax in description for structured bike/run;
   group rides can be named sessions with duration). Prefer
   icu_bulk_create_events for a week; icu_duplicate_events to repeat a
   group ride across weeks.

4. Off-season strength: after the A-race recovery (or a date I name),
   propose 2×/week strength as WORKOUT event_type=Other, not on VO2 days.
   After I approve, add them. Optional SEASON_START block if I want the
   chart marked.

Then remind me to review the Intervals calendar UI. Check wellness before
stacking load. Flag travel as HOLIDAY. Taper into an A race. Never put
CTL or race dates into Drive or a goals store.
```

## 1. Log the race

1. Ask where the race lives: sheet, GCal, or “I just told you.”
2. `icu_get_calendar_events` for a window around that date (duplicates are
   common when a sheet and chat both mention it).
3. If it is missing here: A/B/C (**ask** — it weights the fitness chart)
   and discipline (`Ride`, `Run`, …). Then:

   `icu_create_event` — `category=RACE_A|RACE_B|RACE_C`, `event_type`
   required, `start_date=YYYY-MM-DD`, name as you will recognize it.

4. Optional: a `TARGET` on a date (“hold X watts for 20 min by race week”)
   — a goal number, not a substitute for the race event.

Chat context is enough. You do not need a spreadsheet to log a race.

## 2. Fitness vs the race

Pull **here** first, then enrich:

- `icu_get_fitness_summary` / `icu_get_fitness_chart` — CTL, ATL, form,
  trajectory into race week
- `icu_get_sport_settings` — FTP / FTHR / pace you are actually training to
- `icu_get_power_curves` (cycling) or HR/pace curves — 1–5 min vs 20 min vs
  longer, matching the event
- Recent activities, intervals, best efforts if the race is like a past
  effort
- Strava MCP: route, elevation, prior rides on that course
- Web: official distance and climbing if neither calendar has it

What you want back: race demand (duration, climbing, intensity), current
ability, and the **gap** (aerobic engine, repeats, durability, heat,
technical descending — only what the data supports). Wellness
(`icu_get_wellness_data`) before you prescribe a big load week.

## 3. Structure weeks around sessions you already do

1. You name the immovables (“Tuesday 6pm VO2 group”, “Saturday club long”).
2. Model reads Intervals for that span so it does not double-book.
3. **Draft in chat** (table: day, session, why). You approve.
4. Writes:
   - Group rides: `WORKOUT`, `event_type=Ride`, duration, a short name.
     Structure optional — the group sets the work.
   - Prescribed sessions: `description` = Intervals workout syntax
     (`intervals-icu://workout-syntax`). Load and device sync come from
     that text.
   - Several days: `icu_bulk_create_events`
   - Same group ride for N weeks: create once, `icu_duplicate_events`
   - Saved library workouts: `icu_get_workout_library` /
     `icu_get_workouts_in_folder` then copy description onto a date

Place hard days **away** from the VO2 group unless that group *is* the
VO2 day. Long ride owns Saturday; do not stack a second long session
unless you said so.

Into an **A** race: taper (usually 7–14 days). Do not invent new VO2
the week of the event.

## 4. Off-season strength

Start after a real recovery block post A-race (often 7–14 easy days), or
on a date you name as off-season — not in peak or taper.

Typical pattern: **two** strength sessions per week, not the morning after
VO2, not instead of the Saturday long until you choose to.

Create as `WORKOUT`, `event_type=Other` (gym is not Ride/Run in the
enum), duration, a simple description (sets/movements). Workout power
syntax is for bike/run/swim; do not force `%FTP` on a deadlift.

Optional: `SEASON_START` with `start_date` / `end_date` so the fitness
chart shows the block. That is a marker, not a substitute for the gym
appointments.

## 5. Always do these (easy to forget)

- **Review in Intervals** (phone app or web) after every write batch.
- **Wellness** before a load jump (sleep, HRV, rest days).
- **Travel / family**: `HOLIDAY` + `training_availability` (`UNAVAILABLE`
  or `LIMITED`), not silent skipped workouts.
- **Illness**: `SICK` / `INJURED`, not deleted history. Safe-mode delete
  only removes **future** events.
- **Indoor vs outdoor**: `VirtualRide` when it matters for the file.
- **After the race**: pull the activity here (and Strava if useful), then
  plan the next block. Do not leave the A-race sitting with a peak week
  still on the calendar.
- **Conflicts**: sheet vs GCal vs Intervals — confirm, then Intervals
  wins.
- **Timezone**: the host `TZ` should match how you think of “today.”

## Tools this profile actually has

Coaching profile (~32 tools): calendar CRUD (including bulk + duplicate),
fitness summary/chart, sport settings **read**, power/HR/pace curves,
wellness, activities + streams/histograms, workout library.

Not in coaching: gear, custom charts, ATP apply, sport-settings writes.
Do not ask for `icu_get_annual_training_plan` on this profile — use the
fitness chart + calendar instead.

## If something is missing in the phone chat

- Connector not enabled for **this** chat → tools never appear.
- Strava MCP not connected → say “no route file; use the race site.”
- Drive/GCal empty → log from the message you just typed.
- Model wrote events you did not want → `icu_delete_event` on **future**
  dates, then fix. Check the Intervals UI.
