"""Versioned coaching methodology parameters for LLM consumption.

Exposed as the `intervals-icu://methodology` MCP Resource. Helpers in
`athlete_state_compute` import the same tables so derived phase and readiness
stay consistent with the resource the coach is told to read.
"""

from typing import Any

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

DISTRIBUTION_MODELS: dict[str, dict[str, Any]] = {
    "polarized": {"z1": 0.80, "z2": 0.05, "z3": 0.15, "min_weekly_hours": 14},
    "pyramidal": {"z1": 0.75, "z2": 0.18, "z3": 0.07, "min_weekly_hours": 6},
    "threshold": {"z1": 0.65, "z2": 0.28, "z3": 0.07, "min_weekly_hours": 4},
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

METHODOLOGY_SPEC = """\
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

## Intensity distribution (by observed weekly hours)

```
under 8h:     threshold or pyramidal
8–14h:        pyramidal (polarized only in base)
over 14h:     polarized
```

Polarized: z1 0.80 / z2 0.05 / z3 0.15 (min ~14h).
Pyramidal: z1 0.75 / z2 0.18 / z3 0.07.
Threshold-weighted: z1 0.65 / z2 0.28 / z3 0.07.
Anti-pattern: living in the middle (endurance rides creeping into tempo).

## Taper (A-race)

Duration 8–14 days optimal (max 21). Cut volume exponentially 41–60% \
(cluster ~50%). Hold intensity. Cut frequency at most ~20%.

## Ramp

CTL/week: conservative 3 / standard 5 / aggressive 7. Pick from \
`fitness_form.tsb_tolerance`, not a fixed ceiling. Max 3 consecutive build \
weeks; recovery week ~60% load.

## Readiness gating (daily swap, not rewrite-the-week)

Hold weekly structure; swap session type. Threshold moves, it does not vanish. \
If a key session is deferred twice, surface the conflict — do not drop it.

```
green: hrv_z >= -0.5 AND rhr_z <= 1.0 AND sleep_debt_h < 2
amber: hrv_z in [-1.5, -0.5) OR rhr_z in (1.0, 2.0] OR sleep_debt_h >= 2
  → if today is high-intensity, swap with nearest endurance/recovery day
red:   hrv_z < -1.5 OR consecutive_days_below_baseline >= 3 OR rhr_z > 2.0
  → recovery/rest; 2 consecutive red: propose 20–30% week load cut (wait for yes)
  → 4 consecutive red: flag for human review
```

Subjective fields (mood, motivation, fatigue, soreness, stress) on Intervals \
wellness. Empty → lower-confidence state; prompt `icu_update_wellness`. \
There is no `wellbeing` field.

## Mixed-sport load

Intervals combined TSS is the CTL the charts use. Do not invent \
sport-weighted load. Flag mixed-sport weeks in analysis.
"""
