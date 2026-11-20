"""Where every methodology number comes from.

Each module-level constant in `coaching.methodology` has an entry in
`PARAMETER_SOURCES`; `tests/test_methodology_sources.py` fails when one is
missing. The basis says how the value was chosen:

- ``sourced``: the value is taken from the cited references.
- ``derived``: computed from a sourced value or from the load model's maths.
- ``default``: a coaching choice. The rationale says why this value, and the
  references (if any) are the evidence that bounds it. Defaults are the
  candidates for replacement when better evidence is found.

`REFERENCES` status follows the assessment's evidence table
(docs/coaching-architecture-assessment.md, section 7): ``confirmed`` means the
citation and finding were checked against a PubMed or publisher record,
``partly`` means the paper exists but the finding was read only in an abstract
or a secondary source.
"""

from typing import Any

REFERENCES: dict[str, dict[str, str]] = {
    "allen_coggan_2010": {
        "short": "Allen & Coggan 2010",
        "citation": "Allen H, Coggan A. Training and Racing with a Power Meter, 2nd ed. "
        "VeloPress, 2010",
        "finding": "FTP estimated as 95% of a 20-minute best effort",
        "status": "partly",
    },
    "bosquet_2007": {
        "short": "Bosquet 2007",
        "citation": "Bosquet L et al. Med Sci Sports Exerc 2007;39(8):1358-1365, PMID 17762369",
        "finding": "Taper of about two weeks, volume cut 41-60% exponentially, intensity "
        "and frequency held",
        "status": "confirmed",
    },
    "coyle_1984": {
        "short": "Coyle 1984",
        "citation": "Coyle EF et al. J Appl Physiol 1984;57(6):1857-1864, PMID 6511559",
        "finding": "VO2max -7% after 21 days of inactivity, stable at -16% by day 56",
        "status": "confirmed",
    },
    "eichner_neck_check": {
        "short": "Eichner neck check",
        "citation": "Eichner ER, 'neck check', as reported by secondary sources",
        "finding": "Above-the-neck cold symptoms allow light exercise; fever or chest "
        "symptoms mean rest. A clinical heuristic, not a trial result",
        "status": "partly",
    },
    "mujika_padilla_2000": {
        "short": "Mujika & Padilla 2000",
        "citation": "Mujika I, Padilla S. Sports Med 2000;30(2):79-87, PMID 10966148",
        "finding": "Short-term (<= 4 weeks) detraining cuts VO2max and blood volume quickly "
        "in highly trained athletes",
        "status": "partly",
    },
    "plews_2013": {
        "short": "Plews 2013",
        "citation": "Plews DJ et al. Sports Med 2013;43(9):773-781",
        "finding": "Rolling weekly ln(RMSSD) tracks adaptation better than single-day HRV",
        "status": "partly",
    },
    "rosenblat_2019": {
        "short": "Rosenblat 2019",
        "citation": "Rosenblat MA et al. J Strength Cond Res 2019;33(12):3491-3500, PMID 29863593",
        "finding": "Moderate time-trial advantage for polarized over threshold training, "
        "from three low-quality trials",
        "status": "confirmed",
    },
    "rosenblat_2025": {
        "short": "Rosenblat 2025",
        "citation": "Rosenblat MA et al. 2025, network meta-analysis of individual data, "
        "13 studies, 348 athletes",
        "finding": "No overall difference polarized vs pyramidal; recreational athletes "
        "gained more VO2max on pyramidal, competitive athletes on polarized",
        "status": "confirmed",
    },
    "schwellnus_2022": {
        "short": "IOC 2022",
        "citation": "Schwellnus M et al. IOC consensus on acute respiratory illness in "
        "athletes, Br J Sports Med 2022;56:1066-1088",
        "finding": "About 20% of illnesses cost training days; mean symptoms about 7 days; "
        "no established return-to-sport timelines",
        "status": "partly",
    },
    "seiler_2010": {
        "short": "Seiler 2010",
        "citation": "Seiler S. Int J Sports Physiol Perform 2010;5(3):276-291",
        "finding": "Endurance athletes do about 80% of sessions at low intensity",
        "status": "partly",
    },
}

PARAMETER_SOURCES: dict[str, dict[str, Any]] = {
    "PHASE_FROM_A_RACE": {
        "basis": "default",
        "rationale": "Taper window follows the two-week optimum; peak 4 weeks and build "
        "12 weeks out are common periodization practice, not trial results",
        "refs": ["bosquet_2007"],
    },
    "READINESS_THRESHOLDS": {
        "basis": "default",
        "rationale": "z-score cut-offs at 0.5 and 1.5 SD are coaching choices; the cited "
        "work favours rolling HRV over the single-day score used here (assessment R8)",
        "refs": ["plews_2013"],
    },
    "TSB_EXCURSION_THRESHOLD": {
        "basis": "default",
        "rationale": "TSB -25 marks a deep fatigue excursion when measuring this athlete's "
        "own tolerance; the tolerance, not the cut-off, drives the ramp",
        "refs": [],
    },
    "TSB_RECOVERED_THRESHOLD": {
        "basis": "default",
        "rationale": "TSB back above -10 counts as recovered from an excursion",
        "refs": [],
    },
    "DISTRIBUTION_MODELS": {
        "basis": "default",
        "rationale": "Shapes follow the polarized / pyramidal literature and the ~80% easy "
        "session count; the exact zone shares and hour cut-offs are coaching choices",
        "refs": ["seiler_2010", "rosenblat_2019", "rosenblat_2025"],
    },
    "TAPER": {
        "basis": "sourced",
        "rationale": "Duration, volume cut, exponential shape and held intensity and "
        "frequency are the meta-analysis findings",
        "refs": ["bosquet_2007"],
    },
    "RAMP": {
        "basis": "default",
        "rationale": "3 / 5 / 7 CTL a week, three-week blocks and a 60% recovery week are "
        "common coaching practice; not scaled to CTL yet (assessment M1)",
        "refs": [],
    },
    "CTL_WEEK_GAIN_FACTOR": {
        "basis": "derived",
        "rationale": "Daily load that moves a 42-day EWMA by r in 7 days is "
        "CTL + r / (1 - e^(-7/42)); 1 / 0.1535 = 6.51",
        "refs": [],
    },
    "RAMP_SELECTION": {
        "basis": "default",
        "rationale": "Tier from the athlete's own TSB history: how deep and how often they "
        "went and how fast they came back; thresholds are coaching choices",
        "refs": [],
    },
    "RECOVERY_WEEK_RATIO": {
        "basis": "default",
        "rationale": "A week at or under 75% of the three before it is treated as a "
        "recovery week when counting loading weeks",
        "refs": [],
    },
    "TAPER_WEEK_LOAD_PCT": {
        "basis": "derived",
        "rationale": "65% then 45% of the pre-taper week averages a ~55% volume cut, "
        "inside the 41-60% taper range",
        "refs": ["bosquet_2007"],
    },
    "POST_A_RECOVERY_LOAD_PCT": {
        "basis": "default",
        "rationale": "At most half of recent load for 7-14 days after an A-race",
        "refs": [],
    },
    "HARD_SESSION_INTENSITY_FACTOR": {
        "basis": "default",
        "rationale": "IF >= 0.85 counts as hard; misses VO2 sessions that average lower "
        "(assessment M4)",
        "refs": [],
    },
    "FTP_CHECK": {
        "basis": "default",
        "rationale": "20m x 0.95 is the textbook estimate; the 1.15 short-bias ratio and "
        "5% change threshold are coaching choices to avoid chasing noise",
        "refs": ["allen_coggan_2010"],
    },
    "RETURN_FROM_BREAK": {
        "basis": "default",
        "rationale": "No study gives a first-week load share. Fitness lost in 3-14 days is "
        "small, so 67% / 50% protect recovery rather than replace lost fitness; return "
        "timelines after illness are not established; the 45-minute cap keeps "
        "above-the-neck colds light",
        "refs": ["coyle_1984", "mujika_padilla_2000", "schwellnus_2022", "eichner_neck_check"],
    },
}


def render_sources_section() -> str:
    """Markdown section appended to the methodology text."""
    lines = [
        "## Where these numbers come from",
        "",
        "basis: sourced = taken from the references; derived = computed from a sourced "
        "value or the load model; default = a coaching choice, bounded by the references. "
        "Say which when an athlete asks why.",
        "",
        "```",
    ]
    for name, entry in PARAMETER_SOURCES.items():
        refs = ", ".join(REFERENCES[r]["short"] for r in entry["refs"])
        lines.append(f"{name}: {entry['basis']}" + (f" ({refs})" if refs else ""))
    lines.append("```")
    return "\n".join(lines) + "\n"
