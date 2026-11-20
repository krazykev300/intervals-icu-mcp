"""Versioned coaching methodology parameters for LLM consumption.

Exposed as the `intervals-icu://methodology` MCP Resource. Helpers in
`coaching.athlete_state_compute` imports the same tables so derived phase and
readiness stay consistent with the resource the coach is told to read.
"""

from typing import Any

from .sources import render_sources_section

KB_VERSION = "1.2.0"

# Days-out from the nearest RACE_A (or days after it for recovery).
PHASE_FROM_A_RACE: dict[str, dict[str, int]] = {
    "recovery_post_a": {"days_after_a_max": 14},
    "taper": {"days_out_max": 14},
    "peak": {"days_out_max": 28},
    "build": {"days_out_max": 84},
    "base": {"days_out_min": 85},
}

READINESS_THRESHOLDS: dict[str, Any] = {
    "green": {"hrv_z_min": -0.5, "rhr_z_max": 1.0, "sleep_debt_h_max": 2.0},
    "amber": {"hrv_z_min": -1.5, "rhr_z_max": 2.0},
    "red": {"hrv_z_below": -1.5, "consecutive_days_below_baseline": 3, "rhr_z_above": 2.0},
}

TSB_EXCURSION_THRESHOLD = -25.0
TSB_RECOVERED_THRESHOLD = -10.0

# Zone 1 / 2 / 3 time shares from the trial arms, and the observed weekly hours
# at which each model applies. Selection takes the first model in
# `min_weekly_hours` order whose floor the athlete's median week reaches.
DISTRIBUTION_MODELS: dict[str, dict[str, Any]] = {
    "shares": {
        "polarized": {"z1": 0.75, "z2": 0.08, "z3": 0.17},
        "pyramidal": {"z1": 0.80, "z2": 0.12, "z3": 0.08},
        "threshold": {"z1": 0.67, "z2": 0.25, "z3": 0.08},
    },
    "min_weekly_hours": {"polarized": 8, "pyramidal": 6, "threshold": 0},
}

TAPER: dict[str, Any] = {
    "duration_days": {"min": 8, "optimal": 14, "max": 21},
    "volume_reduction_pct": {"min": 41, "optimal": 50, "max": 60},
    "reduction_curve": "exponential",
    "intensity": "preserve",
    "frequency_reduction_pct_max": 20,
}

RAMP: dict[str, Any] = {
    "ctl_per_week": {"conservative": 3, "standard": 5, "aggressive": 7},
    "selection": "by_tsb_tolerance",
    "consecutive_build_weeks_max": 3,
    "recovery_week_load_pct": 60,
}

# Daily load that moves a 42-day EWMA (CTL) by `r` points in 7 days is
# CTL + r / (1 - e^(-7/42)); the divisor is ~0.1535, so the multiplier is ~6.51.
CTL_WEEK_GAIN_FACTOR = 6.51

# A ramp or peak week's target is at most this multiple of the reference week:
# the larger of the last completed week and the mean of the last three, so a
# planned recovery week does not hold the next week below normal load.
RAMP_WEEK_OVER_WEEK_MAX = 1.30

# Runs only: flag a planned run longer (distance, else moving time) than this
# multiple of the longest run in the window before today.
LONG_RUN_SPIKE: dict[str, float] = {"max_ratio": 1.10, "window_days": 30, "horizon_days": 14}

# Ramp tier from empirical TSB tolerance (first matching rule wins).
RAMP_SELECTION: dict[str, Any] = {
    "aggressive": {"excursions_min": 2, "median_days_to_recover_max": 10},
    "conservative_if_recover_days_over": 14,
    "standard_if_min_tsb_at_or_below": -15.0,
    "default": "conservative",
}

# A week is a recovery week when its load is at most this share of the mean
# of the (up to) three weeks before it.
RECOVERY_WEEK_RATIO = 0.75

# Weekly load as a share of the pre-taper reference week (race day excluded).
TAPER_WEEK_LOAD_PCT: dict[str, int] = {"days_out_8_to_14": 65, "days_out_0_to_7": 45}
POST_A_RECOVERY_LOAD_PCT = 50
HARD_SESSION_INTENSITY_FACTOR = 0.85

# FTP check: one server verdict on the configured Ride FTP.
FTP_CHECK: dict[str, float] = {
    # 20-minute best x this factor is the textbook FTP estimate.
    "twenty_min_factor": 0.95,
    # Above this 20m / 60m ratio the 20m rule overstates FTP for this athlete.
    "short_bias_ratio": 1.15,
    # Suggest a change only when the estimate is at least this far from the setting.
    "change_pct": 5.0,
}

# Return after a SICK / INJURED window or any unplanned break, by days missed.
# Load is a share of the last full training week before the break. Coaching
# defaults from the assessment's M6 rule; not a medical protocol. Checked
# against (backlog 8.2): Coyle et al. 1984 (VO2max -7% after 21 days off,
# -16% by day 56), Mujika & Padilla 2000 (short-term detraining is <= 4
# weeks), the IOC 2022 respiratory-infection consensus (mean symptoms about
# 7 days, no established return-to-sport timelines) and the "neck check"
# heuristic for above-the-neck colds. None gives a load share; fitness lost
# in 3-14 days is small, so the cuts protect recovery, not lost fitness.
RETURN_FROM_BREAK: dict[str, Any] = {
    "resume_plan_days_missed_max": 2,
    "short": {"days_missed_max": 7, "first_week_load_pct": 67, "easy_days_first": 2},
    "long": {"days_missed_min": 8, "first_week_load_pct": 50, "easy_days_first": 3},
    "rebuild_weeks": "weeks_missed_rounded_up",
    "limited_illness_max_training_seconds": 2700,
}

_METHODOLOGY_TEXT = """\
# Coaching methodology parameters (this server)

Versioned numbers the coach reasons over. Not prose advice. Per-athlete \
overrides (limiter, stated hours, event demands) live in a goals store if \
connected — never CTL, race dates, athlete ids, or Intervals API keys.

After `icu_get_athlete_state`, read this resource before drafting a season \
or week. Writes stay propose-then-approve.

## Phase from nearest RACE_A (ATP optional)

If Annual Training Plan PLAN blocks cover today, use those (`source: atp`). \
Else derive from days_out to the nearest RACE_A (`source: derived_from_race`). \
Missing ATP is not a gap. No RACE_A and no ATP → `source: unspecified`: \
search this calendar (365d), then goals MCP / Drive / GCal / chat, then ask. \
Do not invent a year-out plan without an Intervals A-date.

```
recovery_post_a: days after A-race <= 14
taper:  days_out <= 14
peak:   days_out <= 28
build:  days_out <= 84
base:   days_out >= 85
```

{distribution}
## Taper (A-race)

Duration 8–14 days optimal (max 21). Cut volume exponentially 41–60% \
(cluster ~50%). Hold intensity. Cut frequency at most ~20%.

## Ramp

CTL/week: conservative 3 / standard 5 / aggressive 7. Pick from \
`fitness_form.tsb_tolerance`, not a fixed ceiling. Max 3 consecutive build \
weeks; recovery week ~60% load.

Tier rule (first match): aggressive = 2+ excursions below -25 TSB with median \
recovery <= 10 days; conservative = median recovery > 14 days; standard = min \
observed TSB <= -15; else conservative. Red readiness drops one tier.

Weekly load for a CTL gain of r: 7 x (CTL + 6.51 x r). Peak holds CTL (r = 0). \
Cap a ramp or peak week at 1.3x the reference week (the larger of the last \
completed week and the mean of the last three); at low CTL the cap, not the \
tier, sets the first weeks. \
Taper week load vs the pre-taper reference: 65% at 8-14 days out, 45% in race \
week. Post-A recovery: <= 50%, no intensity. A recovery week is one at or \
under 75% of the mean of the three weeks before it.

`icu_get_athlete_state` already applies these rules in `analysis.coach_brief`. \
Use those numbers; do not re-derive different ones.

## Session menu (pick by phase; durations scale with available hours)

```
base:    long Z2 ride (the week's anchor), tempo / sweet spot 2-3 x 15-20m
         at 84-92% FTP, one neuromuscular set (6-8 x 10s sprints), strength x2
build:   threshold 2 x 20m or 3 x 15m at 95-100% FTP; VO2 5 x 5m or 4 x 8m
         at 105-115% FTP (or 3 sets of 13 x 30s/15s); long ride with tempo late
peak:    race-specific: efforts at race power and duration, shorter recoveries,
         volume flat or slightly down
taper:   same intensities, half the reps, short openers 1-2 days out
recovery / general_fitness: Z1-Z2 only for recovery; for general fitness one
         threshold-type and one VO2-type session a week on a Z2 base
```

Runs: a planned run more than 10% longer than the longest run of the last 30 \
days is flagged; shorten it or build to it. Single-run spikes, not weekly \
ratios, carried the injury signal in runners; rides are not checked.

Rules: hard sessions at least 48h apart; never two hard days before the long \
ride; a group ride counts as the hard session it actually is; strength not \
the day before a key session; if `60m_to_ftp_gap` is flagged, bias toward \
longer threshold intervals over more VO2. B race: 2-3 easy days before, no \
full taper. C race: train through.

## FTP check

`analysis.ftp_check` is the only FTP verdict (keep / raise / lower). Do not \
estimate FTP yourself (no 20m x 0.95 in chat). Estimate = Intervals eFTP, else \
20m best x 0.95 — unless 20m / 60m best > 1.15: then the 20m rule overstates \
this athlete and only eFTP counts. Change suggested only when the estimate is \
5%+ from the setting. A 60m best below FTP is a durability limiter, not a \
reason to change FTP.

## Readiness gating (daily swap, not rewrite-the-week)

Hold weekly structure; swap session type. Threshold moves, it does not vanish. \
If a key session is deferred twice, surface the conflict — do not drop it.

```
unknown: today's HRV AND sleep both missing (RHR or CTL on a training day
         does not count). Do not treat as green. Do not run the amber/red
         swap. Wait for overnight sync or ask; log via icu_update_wellness.
green: hrv_z >= -0.5 AND rhr_z <= 1.0 AND sleep_debt_h < 2
       (only after at least one of HRV or sleep is present today)
amber: hrv_z in [-1.5, -0.5) OR rhr_z in (1.0, 2.0] OR sleep_debt_h >= 2
  → if today is high-intensity, swap with nearest endurance/recovery day
red:   hrv_z < -1.5 OR consecutive_days_below_baseline >= 3 OR rhr_z > 2.0
  → recovery/rest; 2 consecutive red: propose 20–30% week load cut (wait for yes)
  → 4 consecutive red: flag for human review
```

Subjective fields (mood, motivation, fatigue, soreness, stress) on Intervals \
wellness. Empty → lower-confidence state; prompt `icu_update_wellness`. \
There is no `wellbeing` field.

## Return from a break (illness, injury, unplanned time off)

Days missed = the SICK / INJURED window, start to end inclusive. Pre-break \
load = the last full week before it in `coach_brief.load.last_completed_weeks`. \
This overrides `load.next_week_target` until the rebuild is done; say so.

```
1-2 days:  resume the plan as written. Missed sessions are gone, not moved.
3-7 days:  first week back at 67% of pre-break load, first 2 days easy (Z1-Z2)
8+ days:   first week back at 50% of pre-break load, first 3 days easy
rebuild:   back to pre-break load in even steps over as many weeks as were
           missed (rounded up, at least 1), then the normal ramp resumes
```

No intensity until the easy days felt normal. One hard session in the first \
week back at most, shortened. Never make up missed key sessions. Illness: the \
first session back comes after a full symptom-free day; fever or chest \
symptoms mean rest, not easy riding. Above-the-neck symptoms only: easy \
movement at most (Z1, up to 45 minutes). Injury: pain-free sports first, the \
injured sport last and easy; pain that changes how they move stops the session.

These are coaching defaults, not a medical protocol. Fitness lost in 3-14 \
days off is small (VO2max about 7% down after three weeks: Coyle et al. \
1984), so the cuts protect recovery from the illness or injury rather than \
make up lost fitness. Return-to-sport timelines after respiratory illness are \
not established (IOC consensus 2022). Anything beyond a mild illness, or \
symptoms that come back, is a question for a doctor.

## Mixed-sport load

Intervals combined TSS is the CTL the charts use. Do not invent \
sport-weighted load. Flag mixed-sport weeks in analysis.
"""


def _render_distribution() -> str:
    """Distribution section, rendered from DISTRIBUTION_MODELS so text and code agree."""
    floors: dict[str, float] = DISTRIBUTION_MODELS["min_weekly_hours"]
    shares: dict[str, dict[str, float]] = DISTRIBUTION_MODELS["shares"]
    lines = ["## Intensity distribution (by observed weekly hours)", "", "```"]
    upper: float | None = None
    for model, floor in floors.items():
        if upper is None:
            band = f"{floor:g}h and over"
        elif floor:
            band = f"{floor:g}h to under {upper:g}h"
        else:
            band = f"under {upper:g}h"
        lines.append(f"{band + ':':<20}{model}")
        upper = floor
    lines.append("```")
    lines.append("")
    for model, share in shares.items():
        lines.append(
            f"{model.capitalize()}: z1 {share['z1']:.2f} / z2 {share['z2']:.2f} / "
            f"z3 {share['z3']:.2f}."
        )
    lines += [
        "",
        "Polarized from 8h assumes a competitive athlete; for a recreational one, "
        "pyramidal gave more VO2max (Rosenblat 2025), so offer it as the alternative.",
        "Anti-pattern: living in the middle (endurance rides creeping into tempo).",
        "",
    ]
    return "\n".join(lines)


METHODOLOGY_SPEC = (
    _METHODOLOGY_TEXT.replace("{distribution}", _render_distribution())
    + "\n"
    + render_sources_section()
)
