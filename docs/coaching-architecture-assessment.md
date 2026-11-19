# Coaching architecture assessment and roadmap

Written 2026-11-16 as a handoff: the owner decides the open questions in
[section 9](#9-decisions-for-the-owner), then an implementing agent works
through [section 8](#8-roadmap). Based on the code at commit `7c624b4`, one live
`icu_get_athlete_state` call, the Intervals.icu OpenAPI spec in this repo, and a
survey of competing products (sources at the end).

Companion documents:

- [coaching-data-store.md](coaching-data-store.md): what the server stores
  per athlete, the schema, sign-in, privacy and backups.
- [coaching-capability-backlog.md](coaching-capability-backlog.md): some
  sixty further capabilities, each mapped to where it appears in Intervals.

## 0. The division of labour

**Intervals.icu is the screen and the record. Claude is the conversation. This
server is the coach.**

Intervals does for this project what TrainingPeaks does for a human coach: it
is where the athlete sees the plan, the sessions and the data. That sets three
rules for everything below.

- **Show the work in Intervals.** A capability is finished when its result is
  visible in the Intervals calendar or activity page without opening a chat:
  sessions that state their purpose, a weekly note, phases and weekly targets,
  coach comments on rides, a planned-versus-actual fitness chart.
- **Intervals wins.** When the athlete edits the calendar by hand, that is a
  decision. The coach adapts and never reverts it.
- **Store little.** The server keeps only what Intervals has no place for: the
  standing profile, the coach's notes, and the log of decisions.

The server uses a fraction of what Intervals offers as a display surface. The
unused parts are listed in section 2 and turned into features in section 1 of
the backlog.

## 1. Bottom line

The server is a good data connector with a thin coaching layer on top. The top
products are the reverse: a coaching engine with a data connector underneath.
Five changes close most of the gap, in this order:

1. **Give the coach a memory.** A small per-athlete store on the server for
   availability, fixed sessions, equipment, sports, injuries and corrections.
   Every chat currently starts knowing the numbers but not the person.
2. **Make the plan a persisted object, not a per-chat recomputation.** Write
   phases and weekly load targets to the Intervals calendar, forecast fitness
   forward, and coach against plan-versus-actual.
3. **Prescribe at session level, not only weekly load.** Track the athlete's
   recent best dose per energy system and have the server build the next
   workout from a ladder of templates. This is the core of what TrainerRoad
   sells.
4. **Model sports separately where the body does.** Keep one combined fitness
   number, but add per-sport guardrails for running and a periodized strength
   track, both switchable per athlete.
5. **Turn the methodology into a cited, tiered rule base.** Every number
   carries a source, an evidence grade, the population it was measured on, and
   which volume tier it applies to. The server hands the model only the rules
   that fit this athlete.

Two supporting pieces make the rest trustworthy: a **validator** that checks a
proposed week on the server before it is written, and an **evaluation harness**
that measures whether the coach behaves, so changes stop being judged by feel.

Things I recommend against are in [section 10](#10-what-not-to-build).

## 2. Where the tool stands

What works today:

- One grounding call (`icu_get_athlete_state`) with fitness trajectory, TSB
  tolerance, races, readiness and a computed `coach_brief`.
- The guide is reachable from chat clients through `icu_get_coaching_guide`.
- Propose-then-approve writes, delete safety, a workout-syntax linter.
- Link-token identities, so friends can share one server.

What is missing, measured against the products in section 3:

| Capability | Top products | This server today |
|---|---|---|
| Athlete context that persists between chats | Profile and goals stored | None. Relies on a separate knowledge store only the owner has |
| A plan that exists as data | Stored plan, adapts to what happened | Target recomputed from CTL on every call; undertraining silently lowers the target |
| Forecast | TrainerRoad shows a 28-day simulation; AI Endurance predicts race-day performance | None |
| Session-level progression | TrainerRoad workout levels; Xert fitness signature | None. Only weekly load and a text session menu |
| Feedback after a session | Post-workout survey or automatic scoring feeds the next session | Compliance matched by calendar date only |
| Readiness | HRV, RHR, check-in, wearable scores | Single-day z-score; `unknown` whenever today's row is empty |
| Strength and cross-training | Athletica plans multi-sport; most cycling apps ignore strength | Mentioned in prose only; load model ignores them |
| Evidence trail | Mostly opaque | Numbers in `coaching/methodology.py` with no sources |
| Proactive contact | Daily readiness and plan changes pushed to the phone | Pull only |
| Guardrails on writes | The engine cannot produce an invalid week | Rules are prompt text the model may ignore |
| Measured behaviour | Internal | A routing eval with 36 cases, many for tools outside the coaching profile |

Fields the Intervals API already returns that the server ignores:

- `paired_event_id` and `compliance` on activities (which planned session an
  activity fulfilled).
- `icu_zone_times`, `icu_hr_zone_times`, `polarization_index` (actual time in
  zone).
- `decoupling`, `icu_efficiency_factor`, `icu_power_hr_z2` (aerobic quality of
  a ride).
- `icu_rpe`, `feel`, `session_rpe`, `kg_lifted` (subjective load, strength).
- `sportInfo.eftp`, `/mmp-model` (estimated FTP, critical power, W′, peak
  power).
- `load_target`, `time_target`, `distance_target`, `tags`, `external_id`,
  `carbs_per_hour` on events.
- `/athlete-summary` (weekly totals including time in zones and sRPE).
- `readiness`, `sleepScore` on wellness when a wearable supplies them.

## 3. What the leading products do

Vendor descriptions, not independent tests. The pattern matters more than any
one feature.

- **TrainerRoad.** Classifies every workout by energy system and difficulty,
  tracks the athlete's level per system, and picks the next workout one step
  up. The 2026 "TrainerRoad AI" release added a 28-day training simulation,
  variable-length endurance rides and a fatigue detector that turns days red or
  yellow. No chat coach. Little strength support.
- **Xert.** Replaces FTP with a three-number fitness signature (threshold
  power, high-intensity energy, peak power) updated from every ride, splits
  load into low, high and peak strain, and recommends a workout by the focus
  the athlete needs.
- **JOIN.** Re-plans the week when availability changes and takes readiness
  from a check-in or from Oura and WHOOP.
- **Athletica.** Built by Paul Laursen and Martin Buchheit on their HIIT
  research. Multi-sport, HRV traffic light, and since March 2026 a chat coach
  that reads the athlete's data.
- **AI Endurance.** Trains a model per athlete, searches training futures
  across volume and intensity, and picks the plan with the best predicted
  race-day result. Needs 100+ activities.
- **Vekta.** Adopted by Lidl-Trek, TotalEnergies and Decathlon CMA CGM. Models
  critical power and W′ instead of FTP, tracks durability (power after hours
  of work), detects intervals automatically. Positioned as a tool for coaches.
- **Chat-first tools and MCP peers** (LeCoach, IntervalCoach, Athmex,
  garmin-coach-mcp, several Claude Code coach repos). The common shape is a
  data connector plus a stored athlete profile plus a rules document. Athmex
  exists only to supply the profile, because its author found that activity
  connectors give the model data but not the athlete.

The shared loop is: athlete model → stored plan → prescribed session →
completed session scored → model and plan updated. This server has the first
half of the first step.

Where this server can be better than all of them: the rules are open, each one
can carry its source, the athlete owns the data, and the coach can explain and
change the calendar in conversation.

## 4. Target architecture

Split the code by what decides, not by API endpoint. The model's job becomes
conversation, judgment on things the server cannot see, and scheduling inside
limits the server enforces.

```
Claude Chat (explains, asks, schedules, proposes)
        │  tools
┌───────┴────────────────────────────────────────────────┐
│ tools/            thin MCP wrappers, no coaching logic │
├────────────────────────────────────────────────────────┤
│ coaching/                                              │
│   store.py        per-athlete profile + decision log   │
│   state/          athlete model from Intervals data    │
│   knowledge/      cited rules, tiers, renderer         │
│   planner/        season skeleton, week targets, sim   │
│   progression.py  per-system dose tracking             │
│   workouts/       template ladders → Intervals syntax  │
│   sports/         per-sport load rules and menus       │
│   validator.py    week lint run on every write         │
│   review.py       planned vs done, session verdict     │
│   brief.py        the per-chat summary (exists)        │
├────────────────────────────────────────────────────────┤
│ client.py         Intervals API, cached per identity   │
└────────────────────────────────────────────────────────┘
        │
  Intervals.icu (calendar = the plan; activities; wellness)
  data/coach.db  (profile, decisions; never keys or fitness numbers)
```

Rules for the split:

- Anything numeric is computed on the server and returned as a fact.
- Anything the athlete will see in Intervals lives in Intervals (plan phases,
  weekly targets, sessions, tags). The local store holds only what Intervals
  has no place for.
- `coaching/` is fork-owned code. Keeping it out of `server.py` and `tools/`
  keeps rebases against upstream cheap.

## 5. Recommendations

Sizes: S is under a day of agent work, M is one to two days, L is several.

### R1. Athlete profile and decision log (M)

**Problem.** The playbook says "ask (or recall) fixed sessions". There is
nothing to recall from. Friends have no knowledge store at all.

Full design, including schema, sign-in, privacy and backups:
[coaching-data-store.md](coaching-data-store.md). In outline:

**Design.**
- One-off availability (travel, a short week) is a `HOLIDAY` event in
  Intervals with `training_availability` and `max_training_time`; only the
  standing weekly template lives in the profile.
- SQLite at `data/coach.db`, keyed by Intervals athlete id, not link token.
- `profile`: one JSON document per athlete, validated by a Pydantic model,
  with history rows on every change.
  - `goals`: free text plus priority.
  - `availability`: per weekday, maximum minutes, indoor-only flag.
  - `fixed_sessions`: name, weekday, sport, typical duration, what it really
    is (endurance, tempo, VO2, race-like).
  - `sports`: primary, secondary, and toggles for strength and running with a
    stated purpose.
  - `equipment`: power meter, trainer, HR strap, gym or home weights.
  - `health`: injuries, conditions, age band, anything that changes advice.
  - `preferences`: tone, units, how much detail.
  - `corrections`: standing rules created when the athlete tells the coach it
    got something wrong.
- `decisions`: dated log of approved plans, deferred key sessions, swaps and
  the reason. This is what makes "a key session deferred twice" detectable.
- Read path: `icu_get_athlete_state` returns `coach_profile` and lists missing
  profile fields in `gaps`. An empty profile triggers a short onboarding
  interview, one question per turn.
- Write path: one tool, `icu_update_coach_profile(patch, reason)`, merge-patch
  semantics, annotated as a write.

**Boundary with the owner's knowledge store.** The server keeps training
constraints the engine needs to compute. Identity and the story of why stay
wherever they are. API keys, CTL and race dates never go in the store.

**Done when.** A new chat for an athlete with a filled profile plans a week
around the fixed sessions without asking; an empty profile produces the
interview; `data/coach.db` is gitignored and covered by the host backup.

### R2. Persisted plan and forward simulation (L)

**Problem.** `coach_brief.load.next_week_target` is derived from today's CTL.
Miss a week and the target drops with you. Nothing shows where the season is
going.

**Design.**
- `planner/season.py`, pure functions: from A-race date, current CTL, ramp
  tier, tolerance and availability, produce a week-by-week skeleton with
  phase, load target, recovery weeks, B-race adjustments and taper.
- `planner/simulate.py`: project CTL, ATL and TSB across the skeleton with the
  same 42-day and 7-day averages Intervals uses. Report predicted CTL and TSB
  on race day and the lowest planned TSB. Reject skeletons that plan below the
  athlete's observed TSB floor.
- Two tools: `icu_propose_season_plan` (read-only, returns skeleton plus
  simulation) and `icu_apply_season_plan` (writes after approval).
- Storage is the Intervals calendar: `PLAN` events for phases and weekly
  `TARGET` events carrying `load_target` and `time_target`, tagged as
  coach-written. The athlete sees and can edit the plan in the Intervals UI.
- The brief then reports `plan_target` (from the calendar) beside
  `computed_target`, plus drift: actual CTL versus planned CTL for this week.
- Re-plan triggers, surfaced as a brief action, never applied silently: CTL
  more than about 5 points off plan, two missed key sessions in a week,
  illness or injury events, a new or moved A-race.

**Verify first.** Confirm against the live API how the ATP builder stores
weekly targets (`for_week`, `load_target`) before writing any.

**Done when.** A season can be proposed, approved, seen in the Intervals
calendar, and a later chat reports drift against it.

### R3. Session progression and a workout builder (L)

**Problem.** Weekly load says how much, not what. The model invents interval
sessions from a text menu, with varying structure and occasional syntax
errors.

**Design.**
- `progression.py`: for each completed session, read `icu_zone_times` and
  intervals and credit the dominant stimulus. Track per system the best
  recent dose over six weeks:
  - endurance: longest ride and its kilojoules.
  - tempo and sweet spot: minutes in one session.
  - threshold: minutes at 95–105% FTP.
  - VO2max: minutes above 105%.
  - anaerobic and sprint: count of efforts.
- Next-step rule: after a successful session move one rung up; after a failed
  one (cut short, power more than 5% under target, RPE 9–10) repeat; after two
  weeks without that stimulus step back one rung, after four step back two.
- `workouts/`: ladders of templates per system that render to valid Intervals
  syntax and pass the existing linter. Examples: threshold 3×10 → 4×10 → 3×15
  → 2×20 → 3×20 → 2×30; VO2 5×3 → 6×3 → 5×4 → 5×5 → 4×8; short intervals
  2×(10×30/15) → 3×(10×30/15) → 3×(13×30/15).
- Tool: `icu_build_workout(kind, sport, minutes_available, rung?)` returns the
  description text, expected load and duration. The model chooses kind and
  day; the server builds the structure.
- The brief gains `progression`: current rung and next session per system.

**Done when.** Two chats on the same day propose the same next threshold
session, and every coach-built workout parses without warnings.

### R4. Session review that closes the loop (M)

**Problem.** Compliance matches a planned workout to any activity on the same
date. Nothing scores whether the session did its job.

**Design.**
- `review.py` and tool `icu_review_session(activity_id | date)`.
- Pair by `paired_event_id`; fall back to date and sport.
- Compare each planned interval with the detected one: duration, power or
  pace against target, heart-rate drift.
- Add ride quality: `decoupling`, efficiency factor, power-to-HR in zone 2 for
  endurance rides.
- Add the subjective side: `icu_rpe` and `feel`. If missing, the tool's
  response asks for them.
- Return a verdict (hit, partial, missed, overdone), one-line reason, and the
  progression update it implies.
- Rebuild `compliance` in the state on the same pairing.
- Post the verdict as a comment on the activity in Intervals, so the athlete
  reads it on the ride page. With webhooks (after Intervals OAuth) this runs
  automatically when a ride finishes analysing.

**Done when.** "How did that go?" yields the same verdict on repeat calls and
moves the progression rung.

### R5. Week validator and event tags (M)

**Problem.** Hard-day spacing, load range and rest days are prompt text. The
model follows them most of the time.

**Design.**
- `validator.py`, pure: given the existing calendar, proposed events, the
  profile and the brief, return findings.
  - weekly planned load outside the target range.
  - two hard sessions less than 48 hours apart, unless tagged as a block.
  - a session longer than that weekday's availability.
  - no full rest or very easy day in the week.
  - a single day far above the largest day the athlete has ever done.
  - heavy lower-body strength in the 24 hours before a key session.
  - a run longer than 110% of the longest run in the last 30 days.
  - training scheduled on a sick, injured or holiday day.
- Run it inside `icu_create_event`, `icu_update_event` and
  `icu_bulk_create_events`. Findings come back as `warnings` with a
  `week_summary`. Add `dry_run=true` so the model can check a draft before
  showing it.
- Warnings do not block. The athlete can overrule the coach; the coach cannot
  miss the problem.
- On every coach write, set `tags`: `coach`, a role (`key`, `support`,
  `optional`) and a stimulus (`vo2`, `threshold`, `endurance`, `strength`,
  …). Tags make hard-session detection exact (see M4 below) and let the
  decision log track a key session that keeps moving.

**Done when.** A draft week with back-to-back hard days returns a warning in
the tool result, covered by tests.

### R6. Strength and cross-training

See [section 6](#6-strength-and-cross-training).

### R7. Cited, tiered knowledge base

See [section 7](#7-research-knowledge-base).

### R8. Readiness, second version (M)

**Problem.** One morning's HRV against a 60-day mean is noisy, and the state is
`unknown` whenever today's row has not synced.

**Design.**
- Use the 7-day rolling mean of ln(RMSSD) against the 60-day baseline with a
  band of half a standard deviation, plus the 7-day coefficient of variation.
  This is the monitoring method from Plews and Buchheit. The one cycling trial
  of HRV-guided prescription found gains in the guided group but no
  significant difference from a fixed plan, so treat readiness as a reason to
  swap days, not as a performance method.
- Use the wearable's own `readiness` and `sleepScore` when present.
- Fold in subjective scores from wellness and the previous session's RPE.
- Add Foster's monotony and strain from daily load as an overreach flag.
- Time-aware states: before mid-morning local time with no row, report
  `pending`; later in the day, fall back to the trend with lower confidence.
- Count consecutive amber or red days in the decision log so the "two red
  days, cut the week" rule can fire.

### R9. Performance model and stale-zone detection (M)

**Design.**
- Read estimated FTP from `sportInfo.eftp` and critical power, W′ and peak
  power from `/mmp-model`.
- Flag stale zones when estimated and configured FTP differ by more than about
  4%, in either direction. Wrong zones corrupt every load number downstream.
- With body weight, classify the power profile (sprint, anaerobic, VO2,
  threshold) and name the weakest relative to the A-race.
- Store race demands in the profile (duration, kilojoules, decisive efforts)
  and compare with the durability block.
- For athletes without a power meter, fall back to pace or heart-rate
  thresholds. `power_profile` currently fetches `Ride` only.

On the owner's data today: best 20 minutes is 331 W, so 95% is 314 W against a
configured FTP of 300 W, while best 60 minutes is 274 W. That pattern suggests
a threshold that may be set low and limited time at threshold. The engine
should say so.

### R10. Proactive layer (M)

**Problem.** Claude Chat only answers. Competitors push.

**Design.**
- A scheduled job on the home server (systemd timer or in-process scheduler)
  runs the deterministic brief each morning after wellness syncs. No model
  call is needed.
- Delivery, in order of effort: update a `NOTE` event on today's Intervals
  calendar with the day's call; send a push through ntfy or Pushover; send a
  Sunday summary of the week and next week's plan.
- Notifications inform. Calendar changes still happen in chat with approval.

### R11. Efficiency and reliability (S–M)

- One shared `athlete_clock` helper. Only `icu_get_athlete_state` uses the
  athlete's timezone today; wellness, events and activity windows still use
  the server clock.
- Per-identity cache for Intervals reads with a one-to-five-minute lifetime,
  cleared by any write. A planning chat currently refetches the same data
  several times.
- `detail` parameter on the state: `brief` by default (brief, current fitness,
  races, readiness, profile, gaps) and `full` for series, curves and weekly
  compliance.
- A smaller `coach` tool profile of about 15 composite tools for friends.
  Tool descriptions are paid for in every chat.
- Structured per-identity log of tool calls and errors. It shows which tools
  the model actually reaches for and where it stumbles.

### R12. Evaluation harness (M)

- **Engine golden tests.** Fixture athletes: 6 hours a week, 10 hours with
  mixed sport, 18 hours, a runner with no power meter, a return from a break,
  a taper, an illness. Assert the brief, plan and validator output for each.
- **Conversation evals.** Scripted multi-turn chats through the Anthropic API
  with the real tool definitions and mocked Intervals data. Checked in code:
  - first tool call is the state.
  - guide loaded before any write.
  - no write before the scripted "yes".
  - proposed week total inside the target range.
  - every date's weekday is right.
  - written events carry tags.
- A model-graded rubric for advice quality against the rule base.
- Run on Sonnet and Haiku as well as the top model. Friends may be on smaller
  models, and a design that only works on the best one is not robust.
- Refresh `tests/smoke_eval.json`: many cases expect tools that are not in the
  coaching profile, and none covers `icu_get_athlete_state`.

### Methodology corrections found during review

| # | Issue | Fix |
|---|---|---|
| M1 | Ramp tiers are 3, 5 and 7 CTL points a week regardless of CTL. At CTL 40, 7 points is 17% a week | Cap the ramp as a share of current CTL as well as in points |
| M2 | Readiness scores a single day | R8 |
| M3 | Intensity distribution is prescribed but never measured | Collapse `icu_zone_times` to three zones over four weeks and report actual versus prescribed; this makes "living in the middle" detectable |
| M4 | A hard session is defined as intensity factor ≥ 0.85. A VO2 session often averages below that | Use tags, planned zone times or `workout_doc` |
| M5 | The playbook tells the model to create gym sessions as type `Other`; the live calendar uses `WeightTraining` | Change the playbook |
| M6 | No rule for returning after a break or illness | Add one: restart at roughly half to two thirds of pre-break load and rebuild over about as many weeks as were missed |
| M7 | One loading pattern (three weeks on, one off) for everyone | Allow two-on-one-off for masters athletes and low tolerance |
| M8 | Taper length ignores how much fatigue there is to shed | Shorter taper at low CTL |
| M9 | Phase windows are the same for every event type | Let the event duration shift build and peak length |

## 6. Strength and cross-training

**Principle.** Keep Intervals' combined load as the one systemic number, as the
methodology already says. Add per-sport rules beside it, because load points do
not measure what running does to tendons or what lifting does to legs.

### Sport roles

Each athlete's profile assigns a role per sport, with observed activity as the
default:

- **Primary:** drives the performance model and the A-race.
- **Secondary:** trained with intent, such as running for a cyclist.
- **Support:** strength, mobility.
- **Incidental:** hikes, walks, commutes. Counted, never prescribed.

`sports/` holds one config per sport: how load is measured, ramp limits, the
session menu, how targets are written in workout syntax.

### Strength track

Switchable in the profile. Periodized against the season phase:

| Phase | Frequency | Content |
|---|---|---|
| Post-season and early base | 2 a week, 2–3 weeks | Technique and tolerance: 2–3 sets of 10–15, moderate load |
| Base | 2 a week, 8–12 weeks | Heavy: 3–4 sets of 4–10 on squat or leg press, hip hinge, single-leg work, calf raise; plus trunk and upper-body pulling |
| Build | 1 a week | Maintenance: 2–3 heavy sets of 4–6, low volume |
| Peak and taper | Stop heavy lifting 7–10 days before an A-race | Optional short activation only |

Placement rules, enforced by the validator:

- Lift on hard days, at least three hours after the bike session and ideally
  six, so easy days stay easy. Three hours is the separation at which the
  meta-analysis found no interference.
- No heavy lower-body lifting in the 24 hours before a key session; 48 hours
  in the first weeks while soreness is high.
- Expect heavy legs for two to three weeks when starting; lower bike intensity
  targets in that window.

Load accounting: heart-rate load under-reads lifting. Record session RPE times
minutes, and `kg_lifted` when logged. The brief reports sessions done against
sessions prescribed for the phase.

Evidence, all from small samples of well-trained cyclists:

- Heavy strength twice a week for 12 weeks, then once a week in season,
  improved 40-minute all-out power more than endurance training alone
  (Rønnestad 2010).
- Five-minute power after 185 minutes of riding rose from 371 to 400 W with
  strength work and did not change without it (Rønnestad 2011).
- A meta-analysis of 43 studies found concurrent training does not blunt
  maximal strength or muscle growth; explosive strength suffers when both are
  done in one session (Schumann 2022).

### Running for a cyclist

Switchable, with a stated purpose (enjoyment, bone health, travel, a secondary
event). Rules:

- Start with run-walk and at least 48 hours between runs for the first four to
  six weeks, whatever the athlete's aerobic fitness. The engine is ahead of the
  chassis.
- No single run more than 10% longer than the longest in the last 30 days; a
  2025 cohort study of about 5,200 runners tied injury risk to that
  single-session spike more than to weekly totals.
- Cap weekly running growth, and track weekly distance and longest run in the
  brief.
- In a cycling build, running replaces easy volume, never a key session.

Reason to offer it at all: cyclists show low bone density, since cycling is not
weight-bearing (Olmedillas 2012 review).

### Other cross-training

Hiking, skiing, rowing, swimming. Counted by time and RPE. In base, up to about
a quarter of easy volume can be cross-training; in build and peak, keep it to
recovery and enjoyment.

### What changes in the tools

- The brief gains `modalities`: per sport, what was prescribed, what was done,
  and the next cap.
- The workout builder gains strength templates (plain text) and run templates
  (pace or heart-rate targets).
- The session menu in the knowledge base is keyed by sport and role.

## 7. Research knowledge base

**Problem.** The numbers in `coaching/methodology.py` are reasonable but unsourced, and
the same numbers apply to a six-hour and a twenty-hour athlete.

### Structure

A `coaching/knowledge/` package of rule records:

- `id`, `topic`, and the `prescription` in one or two sentences.
- `applies_when`: sport, phase, weekly-hours range, training age, age band.
- `evidence`: A (meta-analysis), B (controlled trials), C (observational data
  from professionals), D (expert practice).
- `population`: who was studied.
- `transfer`: how the finding scales to other volumes.
- `sources`: authors, year, journal, DOI, and a `verified` flag.
- `last_reviewed`.

Enforced in CI:

- Every numeric constant used by the engine references a rule id.
- Every rule has at least one source with a DOI.
- No rule ships with `verified: false`.

Delivery: the server already knows the athlete's hours, phase and sports. The
guide tool renders only the matching rules, and the brief cites rule ids next
to its numbers. The model gets a short, relevant, sourced slice instead of the
whole document.

### Volume tiers

Tier by sustainable weekly hours, adjusted by training age: under 6, 6–10,
10–15, over 15.

How professional practice transfers down:

- **Transfers nearly intact:** the dose of a hard session. Thirty to forty
  minutes at threshold or fifteen to twenty-five at VO2max is a hard session
  for an amateur and for a professional. Also the 48-hour spacing of hard
  days, taper shape, and strength work.
- **Transfers by session count, not time share.** Professionals' 80–90%
  low-intensity time is what two or three hard sessions look like inside 20–30
  hours. At eight hours, the same two or three hard sessions are a much larger
  share. A 2025 network meta-analysis of individual data (Rosenblat et al.)
  found recreational athletes gained more VO2max from pyramidal training and
  competitive athletes more from polarized, with no overall winner. A 2025
  review of zone 2 training concluded that higher intensities matter most when
  volume is low.
- **Does not transfer below the top tier:** block periodization of VO2 work,
  double-threshold days, heat and altitude protocols, back-to-back long days.
  Offer these only in the top tier and label them as advanced.
- **Changes direction:** recovery. An amateur's limit is usually sleep and life
  stress, so readiness gating matters more, not less.

Professional data is evidence grade C by definition. Each such rule states the
population and the transfer explicitly, so the coach never presents "what
WorldTour riders do" as a prescription for a ten-hour athlete.

### Seed rules

Status after this review: **Confirmed** means the citation and the stated
finding were checked against a PubMed or publisher record. **Partly** means
the paper exists as cited but the specific finding was not read in the
source. Even confirmed rows were checked from abstracts, so whoever writes the
rule records should read the methods of anything a prescription rests on.

| Topic | Finding and its limits | Source | Status |
|---|---|---|---|
| Taper | Two weeks, volume cut 41–60% exponentially, intensity and frequency held; overall effect 0.72 | Bosquet et al. 2007, Med Sci Sports Exerc, PMID 17762369; Wang et al. 2023, PMID 37163550 | Confirmed |
| Strength, in season | Twice weekly for 12 weeks then once weekly kept strength and improved 40-minute power more than endurance alone. Twelve cyclists in total | Rønnestad, Hansen, Raastad 2010, Eur J Appl Physiol, PMID 20799042 | Confirmed |
| Strength, late-ride power | 5-minute all-out power after 185 minutes rose from 371 to 400 W with strength work; no change without. Twenty cyclists | Rønnestad, Hansen, Raastad 2011, Scand J Med Sci Sports 21(2):250–259, PMID 19903319 | Confirmed |
| Concurrent training | No loss of maximal strength or muscle growth. Explosive strength reduced (effect −0.28), mainly when both are done in one session; separating by three hours removed it. 43 studies | Schumann et al. 2022, Sports Med 52(3):601–612, doi 10.1007/s40279-021-01587-7 | Confirmed |
| Long intervals | 4×8 minutes at about 90% of peak heart rate beat 4×4 and 4×16 over seven weeks. Nine per group | Seiler et al. 2013, Scand J Med Sci Sports 23(1):74–83, PMID 21812820 | Confirmed |
| Short intervals | 3×(13×30 s on, 15 s off) beat effort-matched 4×5 minutes: 20-minute power +4.7% against −1.4%. Nine elite cyclists per group, three weeks | Rønnestad et al. 2020, Scand J Med Sci Sports 30(5):849–857, PMID 31977120 | Confirmed |
| Polarized vs threshold | Moderate time-trial advantage for polarized (effect −0.66), from three low-quality trials | Rosenblat et al. 2019, J Strength Cond Res 33(12):3491–3500, PMID 29863593 | Confirmed |
| Distribution by level | No overall difference between polarized and pyramidal. For VO2max, recreational athletes did better on pyramidal and competitive on polarized. 13 studies, 348 athletes | Rosenblat et al. 2025, Sports Med 55(3):655–673, doi 10.1007/s40279-024-02149-3 | Confirmed |
| Distribution sequencing | All groups improved; pyramidal for eight weeks then polarized for eight gave the largest gains. Sixty well-trained male runners | Filipas et al. 2022, Scand J Med Sci Sports 32(3):498–511, PMID 34792817 | Confirmed |
| Zone 2 at low volume | Evidence does not support zone 2 as the best intensity for the general population; higher intensities matter most at low volume. Narrative review | Storoschuk et al. 2025, Sports Med 55(7):1611–1624, PMID 40560504 | Confirmed |
| Professional distribution | 28 male WorldTour riders: pyramidal in every phase, high-intensity share rising toward competition, load peaking in the competitive phase | Scand J Med Sci Sports 2025, 35(11):e70153, doi 10.1111/sms.70153 (authors not yet confirmed) | Confirmed |
| Professional volume | Two Tour de France riders: 22.5 and 18.2 hours a week, about 81–89% of time in the lowest zone | Related case study found in search; full citation needed | Partly |
| Block periodization | Small pooled benefit for VO2max (0.40) and peak power (0.28); studies small and low quality | Mølmen et al. 2019, Open Access J Sports Med | Confirmed |
| HRV-guided training | Guided group improved peak power, threshold and 40-minute power; fixed-plan group did not; no significant difference between groups. Seventeen cyclists | Javaloyes et al. 2019, Int J Sports Physiol Perform 14:23–32, PMID 29809080 | Confirmed |
| HRV monitoring | Weekly rolling ln(RMSSD) and its variation track adaptation better than single days; at least three readings a week | Plews et al. 2013, Sports Med 43(9):773–781, and related 2012–13 papers | Partly |
| Recovery time by intensity | Parasympathetic recovery depends on intensity more than duration | Stanley, Peake, Buchheit 2013, Sports Med, doi 10.1007/s40279-013-0083-4 | Partly |
| Running load spikes | Injury rate rose when a single run exceeded the longest of the last 30 days by more than 10% (hazard ratios 1.64, 1.52, 2.28 by band). No relation for week-to-week ratios. 5,205 runners | Frandsen et al. 2025, Br J Sports Med 59(17):1203–1210 | Confirmed |
| Acute-to-chronic ratio | Conceptually flawed as an injury predictor; do not gate on it | Impellizzeri et al. 2020, Int J Sports Physiol Perform 15:907–913 | Confirmed |
| Monotony and strain | Daily-load variability as an overreach marker | Foster 1998, Med Sci Sports Exerc | Partly |
| Bone health | Road cycling gives no significant bone-building stimulus; add impact loading | Olmedillas et al. 2012, BMC Med, doi 10.1186/1741-7015-10-168 | Confirmed |
| Durability | Deterioration of physiological markers during prolonged exercise as a performance factor | Maunder et al. 2021, Sports Med 51(8):1619–1628 | Confirmed |
| Durability and intensity | Intensity of prior work, not kilojoules alone, determines the decline | Sánchez-Jiménez et al. 2025, Eur J Appl Physiol, doi 10.1007/s00421-025-05885-0 | Confirmed |
| Session count rule | About 80% of sessions easy | Seiler 2010, Int J Sports Physiol Perform | Not checked |
| Detraining | Rate of loss after stopping, basis for return-from-break rules | Mujika & Padilla 2000, Sports Med | Not checked |
| Fuelling | Carbohydrate per hour by duration and intensity | Jeukendrup 2014, Sports Med | Not checked |
| Low energy availability | Screening flags | IOC REDs consensus 2023, Br J Sports Med | Not checked |
| Heat training | Haemoglobin mass and performance gains in elite cyclists | Rønnestad et al. 2021–22 | Not checked |

What the check changed, and why the `verified` flag is not optional:

- The 2010 Rønnestad paper is often cited for cycling economy. Its abstract
  reports power, not economy.
- The HRV-guided trial is often cited as proving HRV guidance works better.
  It found no significant difference between groups.
- The short-interval result comes from nine riders per group over three
  weeks. It supports offering 30/15 sessions, not replacing long intervals.
- The polarized-versus-threshold meta-analysis rests on three trials. The
  2025 analysis is the better basis for the tier rule.
- "Zone 2" should not be prescribed to low-volume athletes as the main
  stimulus.

### Keeping it current

- A scheduled quarterly job searches a fixed topic list for new meta-analyses
  and professional-data papers, and opens a pull request with proposed rule
  changes and citations. A person approves.
- Prescriptions never come from a web search during a chat. That would be
  unrepeatable and unverifiable. Chat-time search is for course profiles and
  event logistics.

## 8. Roadmap

Each phase leaves the server deployable. Run `make can-release` at the end of
each item. "B" numbers refer to
[coaching-capability-backlog.md](coaching-capability-backlog.md); store steps
refer to the build order in [coaching-data-store.md](coaching-data-store.md).

**Phase 1 — foundation.**
1. Move fork-owned logic into `coaching/` (mechanical; no behaviour change).
2. R11 timezone helper and read cache.
3. R1 store steps 1–2: profile, notes, decision log, hashed tokens, encrypted
   credentials, admin commands, nightly backup.
4. R5 validator, tags and `external_id` on writes, `dry_run`; store step 3
   (coach events and reconciliation with edits made in Intervals).
5. Self-explaining sessions (B1.1), native availability and illness events
   (B1.6, B1.7), logging gym sessions (B1.9).
6. Data-quality checks, provenance and versioning (B5.2–B5.4).
7. R12 engine golden tests and first conversation evals; refresh the smoke
   eval.
8. Claude Skill and named routines (B2.2, B2.3).
9. Corrections M1, M4, M5.

**Phase 2 — the owner's stated priorities.**
1. R7 knowledge-base schema, tiers, renderer, CI checks; migrate
   `coaching/methodology.py` constants to rule ids; write the seed rules from the table
   in section 7; safety rules (backlog section 6).
2. R6 sport roles, strength track and programme (B3.16), running guardrails,
   `modalities` in the brief.
3. Weekly note in Intervals (B1.2) and the onboarding flow (B2.4).
4. Corrections M3, M6.

**Phase 3 — session quality.**
1. R3 progression tracking and the workout builder, with credit for
   unstructured rides (B3.4) and indoor and outdoor versions (B3.12).
2. R4 session review, paired compliance, coach comment on the activity (B1.4).
3. R9 performance model, stale-zone flag and threshold updates (B1.10).
4. Coach library folder in Intervals (B1.8); aerobic efficiency trend (B3.3);
   group-ride profiling (B3.5).

**Phase 4 — planning.**
1. R2 season planner, simulation, calendar persistence (B1.3), drift.
2. Coach metrics as custom fields and the planned-versus-actual chart (B1.5).
3. "What if" and "I have 45 minutes" tools (B2.7, B2.8).
4. R8 readiness, second version, with early warning (B3.8).
5. Adherence patterns (B3.6); corrections M7–M9.

**Phase 5 — reach.**
1. R10 morning job and notifications (B4.1, B4.4).
2. Sign in with Intervals and webhooks (store step 6, B5.1); automatic
   session review and reaction to calendar edits (B4.2, B4.3).
3. Interactive cards in Claude, starting with the week card (B2.1, B2.5).
4. Coach quality report, rate-limit handling, smaller `coach` tool profile,
   `detail` parameter (B5.5, B5.6).

**Later.** Race toolkit, durability programme, response analysis, fuelling,
heat and altitude, running as a full second sport, season review (backlog
section 7).

Dependencies:

- R5 tags before R3 and R4.
- R1 before R5's availability checks and R6's toggles.
- R7 schema before R6, so strength and running rules land as cited records.
- R3 before R2, so planned weeks can be filled with real sessions.
- Intervals OAuth before webhooks; webhooks before automatic review.

To confirm against the live API before building on them:

- How weekly `TARGET` events store `load_target` and `for_week`.
- What the activity `compliance` field contains.
- Whether `tags`, `color` and `external_id` survive a round trip on events.
- What `/mmp-model` returns for an athlete without a power meter.
- Whether custom wellness and activity fields accept API writes, and the
  content shape of a fitness chart.
- Which OAuth scopes exist for calendar and wellness writes, and whether a
  personal-use OAuth app is permitted.
- How Claude's connector sign-in behaves behind a Funnel path prefix.

## 9. Decisions for the owner

1. **Server-side profile store. Decided 2026-11-16: yes.** Training
   constraints move onto the server (R1). When R1 lands, update the project
   overview in `CLAUDE.md`, which still says goals and constraints belong in a
   separate knowledge store: constraints the engine computes with live here;
   identity and the story of why stay in the separate store; API keys, CTL
   and race dates still go in neither.
2. **Notification channel** for R10: a calendar note only, or a push service
   as well.
3. **Who the friends are.** If any is primarily a runner or has no power
   meter, R9's fallback and run templates move into Phase 2.
4. **Readiness swaps.** Always propose, or allow the morning job to move an
   easy and a hard day on its own within the same week. Recommended: always
   propose.
5. **Strength setup.** Gym, home weights or bodyweight changes the templates.
6. **Model for evals.** Conversation evals cost API money; choose a monthly
   ceiling.
7. **Register an Intervals OAuth app.** Needed for friends to sign in without
   sharing API keys and for webhooks. Recommended: yes, in Phase 5.

None of items 2–7 blocks Phase 1. Where no answer is given, the implementing
agent should take the recommended option, or the cheaper one where none is
stated (calendar note only; cyclists with power meters; gym access; the
smallest eval set), and record the assumption in the pull request.

## 10. What not to build

- **A per-athlete machine-learning model.** AI Endurance needs 100+ activities
  per athlete and a retraining pipeline. With a handful of users, cited rules
  plus the athlete's own history are more accurate and can be explained.
- **A custom load metric.** Xert and Vekta have their own. Intervals' numbers
  are what the athlete sees in the app; a second scale creates arguments, not
  insight. Add guardrails beside the load number instead.
- **Silent calendar changes.** TrainerRoad users complain about opaque
  adaptations. Propose-then-approve is a feature.
- **Research fetched live in chat** as the basis for prescriptions.
- **In-ride heart-rate-variability thresholds (DFA alpha 1).** Needs a chest
  strap and clean data, and its threshold estimates run high in some
  protocols.
- **A custom chat interface.** Claude Chat is the interface; effort belongs in
  the engine.

## Sources

- [TrainerRoad AI guide (forum)](https://www.trainerroad.com/forum/t/new-trainerroad-ai-is-here-ultimate-guide-to-trainerroad-ai-ask-a-cycling-coach-podcast-568/110228?page=8)
- [TrainerRoad AI: what we're working on](https://www.trainerroad.com/forum/t/trainerroad-ai-what-we-re-working-on/110296)
- [Red Light Green Light announcement](https://bicycleretailer.com/announcements/2024/03/20/introducing-red-light-green-light-next-generation-fatigue-management)
- [Athletica FAQ](https://athletica.ai/frequently-asked-questions) and [AI Coach announcement](https://athletica.ai/blog/meet-your-new-24-7-training-partner-athletica-ai-coach)
- [AI Endurance review, SensAI](https://www.sensai.fit/blog/ai-endurance-review-2026)
- [Vekta adopted by WorldTour teams](https://insider.fitt.co/press-release/vekta-adopted-by-multiple-worldtour-teams-as-ai-powered-coaching-platform-gains-momentum-in-pro-cycling/) and [Cyclingnews on Vekta](https://www.cyclingnews.com/news/new-ai-coaching-app-wants-to-work-with-coaches-not-replace-them)
- [Best AI cycling coach apps 2026, restortrain](https://restortrain.com/best-ai-cycling-coach-apps) and [aitoolsbakery](https://aitoolsbakery.com/blog/best-ai-cycling-coach-apps/) (written by competitors)
- [Athmex: persistent athlete context](https://forum.intervals.icu/t/athmex-persistent-athlete-context-for-chatgpt-claude/132283)
- [psca/coach](https://github.com/psca/coach) and [garmin-coach-mcp](https://pypi.org/project/garmin-coach-mcp)
- [Rønnestad et al. 2011, strength and late-ride power](https://pubmed.ncbi.nlm.nih.gov/19903319/)
- [Schumann et al. 2022, concurrent training](https://pubmed.ncbi.nlm.nih.gov/34757594/)
- [Seiler et al. 2013, interval duration](https://pubmed.ncbi.nlm.nih.gov/21812820/)
- [Rønnestad et al. 2020, short intervals](https://zendy.io/title/10.1111/sms.13627)
- [Rosenblat et al. 2019, polarized vs threshold](https://pubmed.ncbi.nlm.nih.gov/29863593/)
- [Rosenblat et al. 2025, distribution by level](https://www.fisiologiadelejercicio.com/wp-content/uploads/2025/02/Which-Training-Intensity-Distribution-Intervention-will.pdf)
- [Filipas et al. 2022, pyramidal and polarized](https://pubmed.ncbi.nlm.nih.gov/34792817/)
- [Storoschuk et al. 2025, zone 2 review](https://pubmed.ncbi.nlm.nih.gov/40560504/)
- [Javaloyes et al. 2019, HRV-guided training](https://pubmed.ncbi.nlm.nih.gov/29809080/)
- [Frandsen et al. 2025, running session spikes](https://pure.au.dk/portal/en/publications/how-much-running-is-too-much-identifying-high-risk-running-sessio/)
- [Olmedillas et al. 2012, cycling and bone](https://pmc.ncbi.nlm.nih.gov/articles/PMC3554602)
- [Mølmen et al. 2019, block periodization](https://www.dovepress.com/block-periodization-of-endurance-training-a-systematic-review-and-meta-peer-reviewed-article-OAJSM)
- [Impellizzeri et al. 2020, workload ratio](https://pmc.ncbi.nlm.nih.gov/articles/PMC7534938)
- [Stanley, Peake, Buchheit 2013](https://link.springer.com/doi/10.1007/s40279-013-0083-4)
- [Sánchez-Jiménez et al. 2025, durability and intensity](https://link.springer.com/article/10.1007/s00421-025-05885-0)
- [Bosquet et al. 2007, taper meta-analysis](https://pubmed.ncbi.nlm.nih.gov/17762369/) and [Wang et al. 2023](https://pubmed.ncbi.nlm.nih.gov/37163550/)
- [Rønnestad et al. 2010, in-season strength](https://pubmed.ncbi.nlm.nih.gov/20799042/)
- [Maunder et al. 2021, durability](https://openrepository.aut.ac.nz/items/e4ed557d-8c56-44ba-9eac-520fc0ae1aae/full)
- [Training strategies of World Tour cyclists, 2025](https://lida.sport-iat.de/ta/Record/4096292?lng=en)
