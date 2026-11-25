# Coaching capability backlog

Ideas for expanding the coach, beyond the core recommendations in
[coaching-architecture-assessment.md](coaching-architecture-assessment.md).
Each entry says what the athlete gets, where it shows up, and what the server
has to do. Storage details are in
[coaching-data-store.md](coaching-data-store.md).

The frame for all of it: **Intervals.icu is the screen, Claude is the
conversation, this server is the coach.** A capability is finished when its
result is visible in Intervals without opening a chat.

Sizes: S under a day of agent work, M one to two days, L several.
Tags: **[now]** worth doing in the first phases, **[next]** after the core is
in, **[later]** speculative or niche. **[done]** shipped; the item's
`**Done:**` line says what. **[done, unchecked live]** shipped and tested, but
not yet confirmed against a live athlete or client; the Done line names what
to check. An item with no done tag is still to do.

## 0. Correct the numbers [now, first]

These reads disagreed with what Intervals sends. They sit above the
capabilities below, because those capabilities use these numbers. Closed:
the tools now match the API. Upstream commits are the reference for the
field names, not a design to copy into the rest of this backlog.

- **Pace curve.** `icu_get_pace_curves` indexed a distance curve as durations,
  so the peaks were empty. Peaks are now 400 m, 1 km, mile, 5 km, 10 km, half
  marathon, and marathon. A window with null arrays returns the empty result
  instead of raising.
- **Run threshold unit.** `threshold_pace` is speed in m/s for every sport.
  Reads convert run to min/km and writes convert min/km back to m/s. Swim was
  already converted.
- **Interval fields.** Laps read `start_time`, `end_time`, `elapsed_time`, and
  `weighted_average_watts`. The response still uses `start_seconds`,
  `duration_seconds`, and `normalized_power`.
- **Intensity ratio.** Activities, calendar events, and the workout library
  use the same conversion as the coach brief: a value above 2 is a percent.
- **Weight and date of birth.** The profile reads `icu_weight` and
  `icu_date_of_birth`, and falls back to `weight` and `dob`.
- **GPS longitude.** `latlng` streams pair latitude (`data`) with longitude
  (`data2`).
- **Discipline list.** The event-type hint includes `WeightTraining` and
  `Workout`, and `intervals-icu://event-categories` lists every discipline
  the API accepts. The tool still passes an unknown type through; the API
  rejects it.

## 1. Intervals as the coach's canvas

The Intervals API exposes far more display surface than the server uses. These
turn the Intervals calendar and activity pages into the coach's output.

### 1.1 Sessions that explain themselves [done, S]

Every coach-written workout carries, in a fixed layout:

- A first line saying what the session is for ("Threshold: raise the power you
  can hold for an hour").
- The structured steps in workout syntax, so it syncs to Garmin, Wahoo and
  Zwift.
- A fuelling line, also set in `carbs_per_hour`.
- A fallback: "If legs are flat after the first interval, switch to 90 minutes
  easy."
- `tags` for role and stimulus, `color` by role so key sessions stand out in
  the calendar, and `external_id` so the coach can find its own events.
- `indoor` when the session is meant for the trainer.

**Done:** `purpose`, `fallback`, `carbs_per_hour`, `role`, `tags`, `indoor`, `external_id` on the event write tools; the playbook asks for them on every coach-written WORKOUT.

### 1.2 The weekly note [now, S]

A `NOTE` event on Monday, shown at the top of the week in the Intervals
calendar: the week's purpose, the load and hours target, the two or three
sessions that matter, and the one thing to watch. Rewritten when the week is
re-planned. It makes the plan readable by someone who never opens Claude.

### 1.3 Season plan in native objects [next, part of R2]

`PLAN` events for phases and weekly `TARGET` events with `load_target` and
`time_target`. Intervals then shows planned against actual per week with no
custom work.

### 1.4 Coach comments on activities [next, S]

After a session review, post the verdict as a message on the activity. The
athlete reads it where they look at the ride, and Intervals sends its own
notification. `icu_add_activity_message` exists in the `full` profile; add it
to `coaching`, restricted to the coach's own comments.

Format: verdict, one line of evidence, one thing for next time. Three lines.

### 1.5 Coach metrics as custom fields [next, M]

Intervals lets an app define custom wellness fields and custom activity
fields, and plot them on the fitness page.

- **Wellness fields** written daily by the morning job: `CoachReadiness`,
  `PlannedFitness` (the plan's CTL for that day), `Monotony`, `Strain`.
- **Activity fields** written by the session review: `Verdict`, `Stimulus`,
  `DoseMinutes`, `RungAfter`.
- **One chart** on the Intervals fitness page: planned fitness against actual
  fitness, with readiness underneath. This is the season at a glance.

Setup is one tool, `icu_setup_coach_dashboard`, which creates the fields. The
chart layout is built once in the owner's Intervals account, read back through
the API, and replayed as a template for friends.

Check first: that custom wellness fields accept API writes (forum reports say
fields created on the site can be updated like built-in ones), and the content
shape of a fitness chart.

### 1.6 Availability where it already lives [done, unchecked live, S]

Intervals has native availability on `HOLIDAY`-type events:
`training_availability` (normal, limited, unavailable), `max_training_time`
and `can_train_sports`. The coach should read these and write them when the
athlete says "I'm travelling Thursday to Sunday, hotel gym only". The standing
weekly template stays in the profile.

**Done:** `max_training_seconds` and `can_train_sports` on the write tools, read back on events and in `coach_brief.away`. The seconds unit follows the other duration fields and is not yet confirmed against a live event.

### 1.7 Illness and injury as events [done, S]

`SICK` and `INJURED` events start the matching protocol: sessions inside the
window are replaced with rest, the return ramp is planned from the end date,
and the decision log records it. Today the playbook only mentions the
categories.

**Done:** a protocol, not an endpoint. Playbook section 7 covers the safety
screen, the one question that sets the window, the `SICK` / `INJURED` event
with native availability, replacing the sessions inside the window, the
return week, and extending or shortening. The return numbers are "Return from
a break" in the methodology (`RETURN_FROM_BREAK`, the assessment's M6).
Until the data store (R1) exists there is no decision log: the event's
description is the record. Not checked live: that Intervals drops the planned
load when today's `WORKOUT` is changed to a `NOTE` (the step used where
safe-mode delete refuses today's event). The brief does not yet surface a
window that has ended; the playbook reads the calendar back 14 days instead.
Both points are since closed: 8.1 confirmed the NOTE drops the planned load,
and 8.3 surfaces the ended window as `coach_brief.returning`.

### 1.8 A coach folder in the workout library [next, M]

Sync the server's template ladders into an Intervals library folder named for
the coach. The athlete can then drag a coach workout onto the calendar by hand
in the Intervals UI, and the coach recognises it by its id. Reusable blocks
(an eight-week strength base, a three-week VO2 block) become `PLAN` folders,
which Intervals can share between athletes.

### 1.9 Logging what no device records [done, S]

"Did the gym session, 50 minutes, RPE 7" becomes a manual activity paired to
the planned event (`mark-done` or the manual-activity endpoint), with session
RPE load and `kg_lifted` when given. Strength then counts in compliance and
load.

**Done:** `icu_log_session` (mark-done with `event_id`, else the manual-activity endpoint).

**Done:** strength logs merge with the upload. With a watch or Strava recording on the day, `icu_log_session` writes the log onto it and pairs it (`paired_event_id`) instead of creating a manual twin; a re-run merges an earlier manual log. Checked live: the API refuses any edit to a Strava-sourced activity (422 "Cannot update Strava activities via the API"), so on a Strava day the log goes onto the plan's description instead and Intervals pairs the upload itself; RPE then does not set load. Not yet checked live: the watch-upload path.

### 1.10 Threshold and zone updates [next, S]

When estimated and configured FTP diverge, propose the new value and, on
approval, write it to sport settings. This needs `icu_update_sport_settings`
in the coaching profile, limited to thresholds.

### 1.11 Race events with a plan attached [next, S]

The race event's description holds the pacing plan, fuelling plan, kit and
logistics checklist. Expected duration and load are set on the event so the
forecast includes the race.

### 1.12 Weather-aware scheduling [done, S]

Intervals exposes a weather forecast for the athlete's location. Use it to put
the long ride on the dry day, flag heat for hard sessions, and choose the
indoor or outdoor version.

**What the API returns** (checked live 2026-11-24):

- `GET /athlete/{id}/weather-config`: the forecast locations, each with
  `label`, `location` ("Leeds,England,GB"), `lat`, `lon` and `enabled`.
  The athlete can change them in Intervals and the API reflects it at once.
- `GET /athlete/{id}/weather-forecast`: per location, `daily` (14 days) and
  `hourly` (40 rows, 3-hour steps, about 5 days), plus an `error` field.
  Fields are temperature and feels-like (°C, morning/day/evening/night in
  daily), humidity, dew point, `rain` and `snow` (mm), wind speed, gust and
  direction (m/s), clouds, a description, and sunrise and sunset.
  There is no chance-of-rain figure, only an amount, and no UV or air quality.
- `GET /activity/{id}/weather-summary`: past-ride temperature, feels-like,
  wind, headwind and tailwind %, and rain. Used later with 3.3, not in this item.

**Design:**

- `icu_get_athlete_state` adds `coach_brief.weather`. No new tool, so the
  tool counts stay the same. It flags only planned outdoor sessions in the
  next 5 days (the hourly window). Days 6–14 give an early heads-up only;
  sessions are never moved because of them.
- Rain is judged by amount, since the API has no chance-of-rain figure. The
  rain, heat (feels-like or dew point), cold or ice, and gust thresholds go
  in `coaching/methodology.py`, each with a source in `coaching/sources.py`.
- The coach proposes the change: move the session to a drier day in the same
  week, keeping the hard/easy pattern and never two key sessions back to back,
  or use the indoor version (3.12). It writes nothing until the athlete agrees.
- If there is no enabled location or `error` is set, the brief says so and the
  coach does not guess.
- The coach asks once whether the athlete has a trainer or treadmill, and
  keeps the answer in the chat client's memory, not in Intervals.

**Name the city.** Every time the coach gives a reason based on weather, it
names the forecast city: "Rain is forecast in Leeds on Thursday, so...".
The athlete can then say they will be somewhere else. In that case the coach
plans that day without the forecast, or asks what the weather looks like there.
If the athlete wants to change their default city, the coach tells them how
to do it in Intervals: open **Options → Weather** (from the calendar or an
activity view), choose **Add location**, add the new city, and turn off or
delete the old one. Multiple locations can be saved and turned on or off,
which suits a trip or a race. The coach does not change the location itself.
If more than one location is turned on, the brief lists each one and the
coach asks which applies.

Out of scope: heat and altitude blocks (3.11), air quality, and weather on
past rides (with 3.3).

**Done:** `coaching/weather.py` builds `coach_brief.weather` from
`/weather-forecast` whenever the state call includes the calendar: city,
`how_to_change_location`, the next five days, and `flagged_sessions` (wet,
snow, ice risk, heat, cold, frostbite risk, windy) with clear days this week,
clear daylight hours and `indoor_version`. Sessions within two days also reach
`coach_brief.flags`. Thresholds are `WEATHER` in the methodology with sources
(KB 1.3.0). Checked live 2026-11-24: the brief reads a real forecast, hourly
`id` times are local to the forecast city, and a wet day flags a ride with its
clear days and hours (against a synthetic event; nothing was written). Not yet
checked: what an account without weather access gets (the brief then says
`unavailable`).

### 1.13 Sync failures surfaced [next, S]

Planned events carry `push_errors` when a workout failed to reach a device.
The brief should say so before the athlete finds out at the start of a ride.

## 2. The chat experience in Claude

### 2.1 Interactive cards in the conversation [next, L]

Claude renders interactive UI from connectors (MCP Apps), inline on mobile and
in a side panel on web and desktop. FastMCP 3.2, already installed, accepts an
`app` on tools and resources.

Start with one read-only card and grow:

- **Week card.** Seven days, planned and done, load against target, readiness
  colour. Shown by the state call.
- **Proposal card.** A draft week with validator warnings beside it and an
  Approve button that sends "yes, write it" to the chat.
- **Forecast chart.** Planned and actual fitness to race day.
- **Session review card.** Planned against actual intervals as bars.

Cards are for looking and approving. Intervals remains where the plan lives.

### 2.2 A Claude Skill for the coach [done, unchecked live, S]

Package the playbook as a Claude Skill in the repo. A skill loads when the
conversation turns to training, which is a more reliable trigger than server
instructions, and it can tell Claude to call the state tool first. The owner
and each friend install it once. Keep the tool-delivered guide as well, for
clients without skills.

**Done:** `skills/intervals-coach/`, generated by `make skill` from the
playbook, methodology and routine index, with a test that fails when the
committed copy is stale. The skill triggers on training talk, calls
`icu_get_athlete_state` first, then loads the guide from the server so an old
install never coaches from old rules; the bundled playbook is the fallback.
Install steps are in `user-setup.md`. Not checked: uploading the zip to
Claude and that it triggers on a phone.

### 2.3 Named routines [done, unchecked live, S]

Trim the ten prompts to the ones a coached athlete uses, and make each a
single entry point that calls the right tools: morning check, review my week,
plan next week, race week, after the race, I'm sick, I have 45 minutes.

**Done:** seven prompts (`morning_check`, `review_my_week`, `plan_next_week`,
`race_week`, `after_the_race`, `im_sick`, `i_have_45_minutes`), each pointing
at one playbook routine and the tools it uses. The coaching profile lists
those plus `coach_with_goals` and `verify_setup`; upstream's analysis prompts
remain in `full`. "I have 45 minutes" is a playbook routine for now; the
`icu_suggest_session` tool is still 2.8. Not checked with a live model.

### 2.4 Onboarding in ten minutes [now, M]

For a new athlete, in order:

1. Consent and what is stored.
2. A data audit: is there power, heart rate, sleep and HRV; are thresholds
   set; how many weeks of history; any Strava-only activities.
3. The interview, one question per turn, skipping what the data already
   answers.
4. A first week proposed and, on approval, written.

### 2.5 Tool results built for two readers [next, M]

Return structured content with a declared output schema for cards and clients,
and a short text summary for the model. The state call's text can then drop to
a few hundred tokens.

### 2.6 Coaching style as a setting [next, S]

Tone, length and how much physiology to explain, stored in the profile and
returned with the brief.

### 2.7 "What if" questions [next, M]

`icu_simulate(changes)`: "what if I take next week off", "what if I add a
five-hour ride on Saturday". Returns the effect on race-day fitness and form
and on the lowest form in between. Built on the same simulator as the season
plan.

### 2.8 "I have 45 minutes" [next, S]

`icu_suggest_session(minutes, location, equipment)` returns the best use of
the time given the week so far, readiness and progression, with a ready
workout.

## 3. Coaching intelligence

### 3.1 Race toolkit [next, L]

- **Pacing.** From critical power and W′, a power plan for the course's
  decisive efforts, with the W′ balance it implies.
- **Fuelling.** Carbohydrate per hour by duration and intensity, written into
  the race event.
- **Race week.** Opener session, taper check, sleep and travel notes.
- **Debrief.** Power distribution against plan, where durability gave out,
  what to carry into the next block. Lessons go to the decision log.

### 3.2 Durability as a tracked quality [next, M]

The state already bins best power by prior kilojoules. Extend it:

- Trend the drop from fresh to fatigued power over months.
- Weight prior work by intensity. A 2025 systematic review found intensity,
  not kilojoules alone, determines how much prior work degrades power.
- For long events, prescribe efforts late in long rides and track them as
  their own progression.

### 3.3 Aerobic efficiency [next, S]

Trend power-to-heart-rate and decoupling on easy rides
(`icu_power_hr_z2`, `decoupling`, the power–HR curve endpoint). A rising
trend is the clearest sign base training is working, and it needs no test.

### 3.4 Credit for unstructured rides [next, part of R3]

Classify outdoor and group rides by time in zone and count them toward
progression. TrainerRoad treats this as a headline feature.

### 3.5 Knowing what the group ride really is [next, S]

For each fixed session in the profile, look at its past instances and report
its real profile: typical load, time above threshold, variability. Plan the
rest of the week around what it is, not what it is called.

### 3.6 Adherence patterns [next, M]

From the decision log and compliance: which weekdays and session types get
skipped, moved or cut short. Then reshape the plan ("Thursday intervals happen
four times in ten; Wednesday ones nine in ten").

### 3.7 What this athlete responds to [later, M]

Across the athlete's own history, compare six-week blocks by composition
(volume, time at threshold, time at VO2) with the change in estimated FTP and
durability that followed. Report it as an observation with its sample size,
never as a law. This is personalisation that can be explained, with no model
to train.

### 3.8 Early warning for illness and overreach [next, part of R8]

Resting heart rate up, HRV down and sleep disturbed together, sustained over
days, alongside monotony and strain. The coach says "back off for 48 hours"
before the athlete feels ill.

### 3.9 Low energy availability flags [later, S]

Weight trending down while load trends up, with poor sleep or mood, prompts a
conservative conversation and a pointer to a clinician. Screening only, using
the IOC consensus criteria. No diagnosis.

### 3.10 Age and sex adjustments [later, S]

- Masters athletes: wider spacing of hard days, two loading weeks to one easy,
  strength given priority.
- Menstrual cycle: Intervals tracks phase. The evidence for phase-based
  prescription is weak, so adjust only on reported symptoms.

### 3.11 Heat and altitude protocols [later, M]

For the top volume tier or a specific hot or high event: a dated protocol
block before the race, flagged as advanced.

### 3.12 Indoor and outdoor versions [done, S]

Each key session has a trainer version (exact steps) and a road version
(fewer, longer efforts tied to terrain). The coach picks by the `indoor`
preference, day and weather.

**Done:** the playbook asks for an indoor version in the `fallback` of key
road sessions, terrain-tied efforts on the road, and `indoor`: true on trainer
sessions; `coach_brief.weather.flagged_sessions` says when to offer the switch.

### 3.13 Fuelling day by day [later, M]

Mark each day low, medium or high carbohydrate from its planned load, in the
weekly note. The idea is Hexis's, which integrates with Intervals; the light
version needs no nutrition logging.

### 3.14 Testing without tests [next, S]

Prefer estimated thresholds from normal riding. When data is too thin (no
maximal effort in six weeks at some duration), schedule one targeted effort
inside a normal session instead of a test day.

### 3.15 Running as a real second sport [later, L]

For a friend who runs, or the owner's occasional runs growing into more:
threshold pace and critical speed from the pace curve, run progression
ladders, pace-based workout syntax, and brick sessions for multisport.

### 3.16 Strength as a real programme [next, M]

Beyond the phase table in the assessment: an exercise library with
progressions and substitutions by equipment, loading by reps in reserve,
home and bodyweight variants, and a short prehab set tied to injury notes.
Starts after 3.18 settles where the rules live and how rigid they are.

### 3.17 Season review [later, M]

Once a year: what was planned, what happened, which blocks produced gains,
what to change. Written as a note in Intervals and into the decision log as
the starting point for the next season.

### 3.18 Strength rules: research and the architecture decision [now, M]

Decide how strength is prescribed before building 3.16 on top of it. Today
every strength number is prose, so `tests/test_methodology_sources.py` checks
none of them:

- Playbook section 5: two sessions a week, not the day after VO2, start after
  A-race recovery, never in peak or taper.
- Methodology session menu: "strength x2" in base, no strength the day before
  a key session.
- Assessment section 6: a phase table (technique 2–3 weeks; heavy 3–4 × 4–10
  for 8–12 weeks; once a week in build; stop heavy lifting 7–10 days before an
  A-race) and placement rules (lift on hard days at least 3 hours after the
  ride; no heavy legs within 24 hours of a key session, 48 in the first weeks).

Confirmed evidence covers only part of it: Rønnestad 2010 and 2011 (twice
weekly, then once weekly in season, in well-trained cyclists) and Schumann
2022 (no interference with maximal strength; explosive strength suffers in the
same session, not three hours apart). Unsourced so far: the pre-race stop,
the 24 / 48-hour gaps, the technique-phase sets and reps, "not the day after
VO2", and the 2–3 weeks of heavy legs when starting.

Research and decide three things, and write the decisions here before any code:

1. **Architecture.** Where strength rules live, and who applies them.
   - Constants in `coaching/methodology.py`, beside the endurance numbers;
     a per-sport module (the assessment's `sports/` config); or rule records
     (the assessment's section 7 `knowledge/` package).
   - Whether the brief computes strength (sessions due this week by phase,
     placement against key sessions, done vs prescribed) the way it computes
     the load target, or the guide only describes it and the model applies it.
   - How strength sessions count in load (session RPE × minutes, `kg_lifted`)
     and whether they feed compliance, the ramp and readiness.
2. **Sources: merge or separate.** One registry or two.
   - Merge: strength entries go into `coaching/sources.py`
     `PARAMETER_SOURCES` and `REFERENCES`, under the same test and the same
     sourced / derived / default tally.
   - Separate: a strength registry with fields the endurance one lacks
     (population, training age, exercise, load scheme), rendered as its own
     section.
   - Either way, keep the assessment's section 7 evidence table in step.
3. **How rigid.** For each rule, decide whether it is:
   - a hard boundary the server enforces (refuses or warns on a calendar
     write, e.g. heavy legs the day before a key session, lifting inside the
     pre-race stop);
   - a default the model may adapt with a stated reason (frequency, sets and
     reps, exercise choice); or
   - guidance only (exercise selection, equipment substitutions).

   Also decide which values the athlete can override (equipment, days
   available, training age) and which stay fixed.

Research to do: read on PubMed (status `confirmed` only when read) for the
unsourced values above, concurrent-training placement and order, and
strength cessation before endurance events. Also note how current systems
(TrainerRoad, TrainingPeaks plans, coaching literature) set rigidity, and
the population limits of cyclist-only trials.

**Finished when** the three decisions are written here with their reasons, every
strength number has a basis and references in the chosen registry, and 3.16
is rescoped to build on them.

## 4. Proactive and event-driven

### 4.1 Morning brief [next, part of R10]

Computed by the server, no model call. Written to today's note in Intervals
and optionally pushed. Three lines: readiness, today's session, anything
changed.

### 4.2 Automatic session review [next, M]

When Intervals reports an activity analysed (webhook after OAuth, polling
otherwise): review it, post the comment (1.4), set the fields (1.5), update
progression. The athlete finishes a ride and finds the coach's note waiting.

### 4.3 Reacting to calendar edits [next, S]

When the athlete moves or deletes a coach session in Intervals: re-run the
week validator, log it as their decision, and mention consequences at the next
chat or in the next morning brief. Never undo it.

### 4.4 Nudges for missing data [next, S]

No HRV for three days, no RPE on the last key session, thresholds older than
three months, a race with no duration set. One nudge each, then silence.

### 4.5 Countdown messages [later, S]

At six weeks, two weeks and three days from an A-race: where things stand
against the plan and what the remaining time is for.

### 4.6 Weekly review written by a model [later, M]

A scheduled Claude task that calls the server on Sunday evening and writes a
fuller weekly review than the deterministic summary. Optional, since it
depends on a Claude client being available to run it.

## 5. Platform

### 5.1 Sign in with Intervals [next, M]

See the data-store design. Friends add the connector and log in; no API keys
or tokens are exchanged by hand.

### 5.2 Data-quality sentinel [done, unchecked live, M]

The hardest practical problem people report with LLM coaching on Intervals
data is bad input. Check and report, in `gaps`:

- Activities that came only through Strava (the API returns stubs for these).
- Rides without power for an athlete who has a power meter.
- Heart-rate or power dropouts and implausible spikes.
- Duplicate activities.
- Thresholds missing for a sport the athlete does.
- Days with load but no activity, and the reverse.

Exclude flagged activities from models and say that they were excluded.

**Done:** `analysis.gaps` now reports all six checks in the existing gap
shape. The newest 12 sensor-bearing activities get bounded stream checks;
flagged activity ids are named, excluded from coach computations, and recorded
in `coach_brief.provenance.data_quality`. Not yet checked against a live
athlete response.

### 5.3 Provenance on every number [done, S]

Each figure in the brief carries where it came from: an Intervals field, or a
computed value with its rule id. Missing inputs are named, never filled in
silently. Same inputs give the same output, and a test asserts it.

**Done:** `coach_brief.provenance.values` maps each numeric subtree to its
Intervals inputs and a versioned rule id. It names missing inputs, and a
determinism test compares two briefs built from identical inputs.

### 5.4 Versioning of the coach [done, S]

`engine_version` and `kb_version` in every state response and stored with
every brief, plan and verdict. When advice changes, the reason is traceable.

**Done:** the same provenance envelope carries `engine_version` and
`kb_version`; both begin at `1.0.0` and are stored with the brief.

### 5.5 Coach quality report [next, S]

Weekly, from the tool-call log: how often the state call came first, how often
writes skipped the dry run, how many validator warnings were returned and
overruled, error rates by tool. This is the eval harness running on real use.

### 5.6 Rate limits and resilience [next, S]

Back off and retry on Intervals rate-limit and server errors, cap concurrent
requests per athlete, and degrade to a partial brief with the failure named.

### 5.7 Other clients [later, S]

The same server and cards work in ChatGPT and other MCP hosts. Keep the
ChatGPT connector doc current and run the conversation evals against one
non-Claude model.

### 5.8 Owner's view of the group [later, M]

With each friend's consent: one summary of how everyone is doing, from
Intervals' athlete-summary endpoint. Useful for a group training toward the
same event. Off by default.

### 5.9 Staying close to upstream [done, S]

Keep fork code in `coaching/`. Offer upstream the fixes that are not
coach-specific: athlete-timezone dates and the percent-scale intensity
handling, if upstream has the same assumptions.

**Done:** fork-owned athlete-state assembly and computation, coach brief,
data-quality checks, methodology, and event-category reference logic live in
`src/intervals_icu_mcp/coaching/`; `tools/athlete_state.py` is a thin MCP
surface. The move changes no tool inputs, outputs, or side effects.

## 6. Safety

Rules the coach follows regardless of what is asked, stored as knowledge-base
entries with sources:

- Chest pain, fainting, unexplained breathlessness, or palpitations: stop
  training advice and point to a doctor.
- Illness: symptoms above the neck only, easy movement at most; fever or
  chest symptoms, rest. Return ramps follow the break rule.
- Pain that alters movement: no training through it; suggest assessment.
- Weight loss goals: no aggressive deficits during hard blocks; watch the
  low-energy flags.
- Under-18s and pregnancy: decline to prescribe intensity; general guidance
  and a pointer to qualified supervision.
- The coach states that it is not a medical service, once, at onboarding.

## 7. Suggested order

Folded into the phases of the assessment's roadmap:

| Phase | Add from this backlog |
|---|---|
| 0 Corrections | Closed. Pace curve, run threshold unit, interval fields, intensity ratio, weight and date of birth, GPS longitude, discipline list. |
| 1 Foundation | Closed. 1.1, 1.6, 1.7, 1.9, 2.2, 2.3, 5.2, 5.3, 5.4, 5.9; 1.6, 2.2, 2.3 and 5.2 still need a live check. |
| 2 Strength, cross-training, rule base | 1.2, 2.4, 3.18 then 3.16, section 6 |
| 3 Session quality | 1.4, 1.8, 1.10, 3.3, 3.4, 3.5, 3.14, 4.2; 1.12 and 3.12 done |
| 4 Planning | 1.3, 1.5, 1.11, 2.7, 2.8, 3.6, 3.8 |
| 5 Reach | 2.1, 2.5, 4.1, 4.3, 4.4, 5.1, 5.5, 5.6 |
| Later | 3.1, 3.2, 3.7, 3.9–3.11, 3.13, 3.15, 3.17, 4.5, 4.6, 5.7, 5.8 |

## 8. Technical follow-ups

Open checks and loose ends left by shipped items. Each names what to find out
and what to change once it is known. Close them with a `**Done:**` line.

### 8.1 Does a WORKOUT turned into a NOTE drop its planned load? [done, S]

The illness protocol (1.7) turns today's session into a rest `NOTE` with
`icu_update_event`, because safe-mode delete refuses today's event. This
server stops counting it (compliance and the brief read `WORKOUT` only), but
it is not confirmed that Intervals clears `icu_training_load` and the
structured steps, so the planned load may still show on the fitness chart.
Check on a future-dated event and delete it afterwards. If the load stays,
send `training_load` 0 and an empty description in the same update, and say
so in playbook section 7.

**Done:** checked live on 2026-11-19 with a future-dated Ride WORKOUT (load
59, 56 minutes, 8 steps) on 2027-01-31, deleted afterwards. After
`icu_update_event` with category NOTE and name "Rest", Intervals returned no
`icu_training_load`, no duration and no sport type, so the planned load is gone
and nothing extra is needed. The workout text stayed in the description, so
playbook section 7 now also replaces the description with the reason.

### 8.2 Source the return-from-break numbers [done, S]

`RETURN_FROM_BREAK` uses 67% of pre-break load after 3-7 days missed, 50%
after 8 or more, and a 45-minute cap for above-the-neck illness. They are
defaults chosen inside the assessment's M6 rule ("half to two thirds"), not
sourced figures. Check them against the detraining literature the assessment
lists as not checked (Mujika & Padilla 2000) and a return-to-sport-after-
illness source, then adjust the table and record the sources.

**Done:** values kept. No source gives a load share for the first week back.
Detraining over 3-14 days is small (Coyle et al. 1984: VO2max −7% at 21
days), so 67% / 50% are cautious recovery defaults rather than fitness-based
figures. The IOC 2022 consensus finds no established return timelines, and the
45-minute cap matches the "neck check" advice to keep it light. Sources are in the
assessment's evidence table, the `RETURN_FROM_BREAK` comment and the
methodology text, which now says these are coaching defaults.

### 8.3 Surface an ended illness window in the brief [done, unchecked live, S]

`coach_brief.away` lists `SICK` / `INJURED` windows that are open or start
in the next 14 days. One that ended yesterday disappears, so the return week
depends on the model reading the calendar back 14 days, as the playbook tells
it to. Add the last window that ended within 14 days to the brief (dates,
days missed, the return rule that applies) and let `next_week_target` follow
the return rule while the rebuild lasts. Touches `coaching/coach_brief.py`.

**Done:** `coach_brief.returning` carries the latest SICK / INJURED window that
ended in the last 14 days: days missed, rule, rebuild weeks, and this week's
share of the last full pre-break week, which `load.next_week_target` follows
while the rebuild lasts. Playbook section 7 points at it. Not checked live.

### 8.4 Move the illness record into the decision log [next, with R1]

1.7 asks for the decision log to record the illness. The data store (R1) is
not built, so the event's description is the record. When the store exists,
write the entry there and keep the description as the athlete-facing copy.

### 8.5 Run the routines and the skill with a live model [now, S]

Not yet checked: an "I'm sick" conversation end to end (question, event,
sessions replaced, return week written), the answer shape of each named
routine, and whether the skill uploads to Claude and triggers on web and on
a phone. Add an `icu_get_athlete_state`-first case per routine to
`tests/smoke_eval.json`; `make smoke-eval` costs money, so run it on purpose.

### 8.6 Classify the prompt trim for the next release [done, S]

The coaching profile stopped listing upstream's eight analysis prompts
(2.3). The versioned contract in the CHANGELOG header names tools,
parameters, env vars and responses, and says nothing about prompts. Decide
whether removing a prompt from the default profile is breaking, and write
the answer into the contract before the release is cut.

**Done:** breaking. The contract in the CHANGELOG header and CLAUDE.md now
names prompts next to tools (removing, renaming, or changing default
registration is major; rewording is not), and the trim is marked BREAKING.

### 8.7 Formatting drift on main [done, S]

`make format` rewrites four files that `make lint` accepts as they are:
`client.py`, `tools/event_management.py`, `tests/test_athlete_state.py` and
`tests/test_session_layout_and_logging.py`. Any agent that runs
`make format` picks up unrelated diffs in another lane's files. Neither
`make lint` nor CI runs `ruff format --check`. Format the four files in one
commit when no lane has them open, and add the check to both.

**Done:** the three files still drifting are formatted (`test_athlete_state.py`
had already been fixed), and `ruff format --check` runs in `make lint` and in CI.

### 8.8 Ramp cap with no reference week [now, S]

The 1.3x weekly cap (#23) is a multiple of the reference week: the larger of
the last completed week and the mean of the last three. When every recent week
is zero (an unplanned break with no SICK / INJURED event, or a new athlete), the
reference is 0 and the cap is skipped. The target then falls back to
`7 x (CTL + 6.51 x r)`, the full jump the cap exists to prevent. The
return-from-break rule (8.3) only covers logged SICK / INJURED windows.

Find out how often this happens (weeks with zero load in the lookback while CTL
is above, say, 10), then choose a fallback and give it a source entry. Options:
treat N zero weeks as a break and apply `RETURN_FROM_BREAK` by weeks missed;
use the last non-zero week as the reference; or cap from a CTL floor
(`7 x CTL x 1.3`). Touches `coaching/coach_brief.py`, `coaching/methodology.py`
and `coaching/sources.py`.


### 8.9 Data-driven coaching numbers [done, unchecked live, M]

Every methodology number says where it comes from, and the endurance defaults
are checked against peer-reviewed evidence.

**Done:** #20 added `coaching/sources.py`: each constant in
`coaching/methodology.py` has a basis (sourced, derived or default), a
rationale and reference ids, enforced by `tests/test_methodology_sources.py`
and rendered into the methodology text. #22 read the evidence for every
default on PubMed and added per-value `parts` for mixed constants. #23 added
two more; the registry now holds 25 confirmed and 5 partly-checked references. #23 applied the owner's decisions: zone shares from the trial
arms, polarized from 8 h a week, the 1.3x week-over-week ramp cap, and the
runs-only long-run flag. Rules are in CLAUDE.md under "Coaching numbers are
data-driven". Not checked against a live athlete. Open follow-ups: 8.8, 8.10,
3.18.

### 8.10 Move the remaining inline thresholds into methodology [now, M]

#22 listed numbers that still live in code instead of `methodology.py`, so they
have no source entry. Move each into a named constant with a `sources.py`
entry, or decide it is a sensor-sanity limit that belongs in its own table.

- `coach_brief.py`: hard sessions per week (3 at 12 h and over, else 2, 1 in a
  recovery week); the target range ×0.9 / ×1.1 and the p90 ×1.1 warning; the
  14-day B/C-race window; `_AWAY_WINDOW_DAYS` and `_RETURN_LOOKBACK_DAYS`.
- `athlete_state_compute.py`: `INTENSITY_BINS` IF 0.75 / 0.85 / 0.95 (0.85
  repeats `HARD_SESSION_INTENSITY_FACTOR`); the 60-day readiness baseline and
  the ±1.0 ms HRV trend; the 10% `60m_to_ftp_gap`; the 1.15 compliance flag
  and `COMPLIANCE_WEEKS`; the 14-day empty-subjective flag;
  `DURABILITY_BINS_KJ`.
- `data_quality.py`: dropout lengths, power and heart-rate ceilings, the
  600 s minimum ride, the 0.8 active share and the dedupe rounding. These are
  likely sensor-sanity limits rather than coaching numbers.

## Sources

- [Get started with MCP Apps, Claude docs](https://claude.com/docs/connectors/building/mcp-apps/getting-started)
- [MCP Apps announcement](https://blog.modelcontextprotocol.io/posts/2026-01-26-mcp-apps/)
- [What are Claude connectors, sunpeak](https://sunpeak.ai/blogs/what-are-claude-connectors/)
- [Intervals.icu API integration cookbook](https://forum.intervals.icu/t/intervals-icu-api-integration-cookbook/80090)
- [Intervals.icu OAuth support](https://forum.intervals.icu/t/intervals-icu-oauth-support/2759)
- [Custom wellness fields, Intervals forum](https://forum.intervals.icu/t/custom-wellness-fields/23188)
- [Hexis integration with Intervals.icu](https://forum.intervals.icu/t/hexis-fuelling-plans-has-integrated-with-intervals-icu/78679.md)
- [Integrated LLMs vs algorithmic coaching, Intervals forum](https://forum.intervals.icu/t/integrated-llms-vs-algorithmic-coaching-utility-guardrails-and-safety/132885)
- [Section 11 open protocol](https://forum.intervals.icu/t/section-11-open-protocol-for-ai-endurance-coaching-chatgpt-claude-grok-mistral/120602)
- [Xert Predictive Mode, the5krunner](https://the5krunner.com/2026/11/10/quick-read-xert-predictive-mode/)
- [JOIN: how it works](https://join.cc/how-join-works/)
- [TrainingPeaks Fueling Insights](https://trainingpeaks.com/fueling-insights)
- [Durability and intensity, Eur J Appl Physiol 2025](https://link.springer.com/article/10.1007/s00421-025-05885-0)
