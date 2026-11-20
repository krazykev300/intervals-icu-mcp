"""Where every methodology number comes from.

Each module-level constant in `coaching.methodology` has an entry in
`PARAMETER_SOURCES`; `tests/test_methodology_sources.py` fails when one is
missing. The basis says how the value was chosen:

- ``sourced``: the value is taken from the cited references.
- ``derived``: computed from a sourced value or from the load model's maths.
- ``default``: a coaching choice. The rationale says why this value, and the
  references (if any) are the evidence that bounds it. Defaults are the
  candidates for replacement when better evidence is found.

A dict constant whose values differ in basis lists them in ``parts``; the
entry's own basis is then the weakest of its parts, so the tally never
overstates the evidence.

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
    "borszcz_2018": {
        "short": "Borszcz 2018",
        "citation": "Borszcz FK et al. Int J Sports Med 2018;39(10):737-742, PMID 29801189",
        "finding": "95% of 20-minute power matched 60-minute time-trial power on average "
        "(bias -1 to -5 W) but limits of agreement were wide (up to about +-60 W); "
        "23 trained cyclists",
        "status": "confirmed",
    },
    "borszcz_2019": {
        "short": "Borszcz 2019",
        "citation": "Borszcz FK et al. Int J Sports Physiol Perform 2019;14(8):1029-1035, "
        "PMID 30676826",
        "finding": "FTP (95% of 20-minute power) vs MLSS: bias 1.4% +- 9.2%, typical error "
        "of the estimate 4.7% (3.0% well-trained, 6.4% trained); 15 cyclists",
        "status": "confirmed",
    },
    "borszcz_2020": {
        "short": "Borszcz 2020",
        "citation": "Borszcz FK et al. Int J Sports Med 2020;41(3):175-181, PMID 31952081",
        "finding": "The 20-minute FTP test is reliable: CV 2.9%, ICC 0.97; 25 trained cyclists",
        "status": "confirmed",
    },
    "bosquet_2007": {
        "short": "Bosquet 2007",
        "citation": "Bosquet L et al. Med Sci Sports Exerc 2007;39(8):1358-1365, PMID 17762369",
        "finding": "Taper of about two weeks, volume cut 41-60% exponentially, intensity "
        "and frequency held",
        "status": "confirmed",
    },
    "buist_2008": {
        "short": "Buist 2008",
        "citation": "Buist I et al. Am J Sports Med 2008;36(1):33-39, PMID 17940147",
        "finding": "A graded 13-week program built on the 10% rule did not reduce injuries "
        "(20.8% vs 20.3%) in 532 novice runners",
        "status": "confirmed",
    },
    "coyle_1984": {
        "short": "Coyle 1984",
        "citation": "Coyle EF et al. J Appl Physiol 1984;57(6):1857-1864, PMID 6511559",
        "finding": "VO2max -7% after 21 days of inactivity, stable at -16% by day 56",
        "status": "confirmed",
    },
    "craven_2022": {
        "short": "Craven 2022",
        "citation": "Craven J et al. Sports Med 2022;52(11):2669-2690, PMID 35708888",
        "finding": "Sleep of 6 h or less in 24 h cut exercise performance by 7.6% on average "
        "(69 studies); endurance affected; morning sessions largely spared",
        "status": "confirmed",
    },
    "eichner_neck_check": {
        "short": "Eichner neck check",
        "citation": "Eichner ER, 'neck check', as reported by secondary sources",
        "finding": "Above-the-neck cold symptoms allow light exercise; fever or chest "
        "symptoms mean rest. A clinical heuristic, not a trial result",
        "status": "partly",
    },
    "esteve_lanao_2007": {
        "short": "Esteve-Lanao 2007",
        "citation": "Esteve-Lanao J et al. J Strength Cond Res 2007;21(3):943-949, PMID 17685689",
        "finding": "Over 5 months, 80/12/8 (zone 1/2/3 time) improved 10.4 km more than "
        "67/25/8; 12 sub-elite runners",
        "status": "confirmed",
    },
    "frandsen_2025": {
        "short": "Frandsen 2025",
        "citation": "Schuster Brandt Frandsen J et al. Br J Sports Med 2025;59(17):1203-1210, PMID 40623829",
        "finding": "Injury rate rose when one run exceeded the longest of the last 30 days "
        "by more than 10%; no relation for the week-to-week ratio; 5,205 runners",
        "status": "confirmed",
    },
    "gabbett_2016": {
        "short": "Gabbett 2016",
        "citation": "Gabbett TJ. Br J Sports Med 2016;50(5):273-280, PMID 26758673",
        "finding": "Rapid load increases blamed for soft-tissue injury; acute:chronic ratio "
        "0.8-1.3 called the 'sweet spot', >= 1.5 the 'danger zone' (team sports, full text)",
        "status": "confirmed",
    },
    "impellizzeri_2020": {
        "short": "Impellizzeri 2020",
        "citation": "Impellizzeri FM et al. Int J Sports Physiol Perform 2020;15(6):907-913, "
        "PMID 32502973",
        "finding": "No evidence supports using the acute:chronic workload ratio to manage load "
        "or reduce injury; the ratio is an inaccurate metric",
        "status": "confirmed",
    },
    "javaloyes_2019": {
        "short": "Javaloyes 2019",
        "citation": "Javaloyes A et al. Int J Sports Physiol Perform 2019;14(1):23-32, "
        "PMID 29809080",
        "finding": "HRV-guided cyclists improved 40-minute power and VT2 power, the fixed "
        "plan did not; no significant difference between groups; 17 cyclists",
        "status": "confirmed",
    },
    "kiviniemi_2007": {
        "short": "Kiviniemi 2007",
        "citation": "Kiviniemi AM et al. Eur J Appl Physiol 2007;101(6):743-751, PMID 17849143",
        "finding": "Hard sessions unless HRV fell below the 10-day mean minus 1 SD (or fell "
        "2 days running); guided group gained more maximal running speed",
        "status": "confirmed",
    },
    "lillo_bevia_2022": {
        "short": "Lillo-Bevia 2022",
        "citation": "Lillo-Bevia JR et al. J Strength Cond Res 2022;36(1):167-173, PMID 31714462",
        "finding": "95% of 20-minute power overestimated MLSS by 12 +- 7 W; 91% fitted; "
        "20-minute test smallest detectable change +-9 W; 11 cyclists",
        "status": "confirmed",
    },
    "macinnis_2019": {
        "short": "MacInnis 2019",
        "citation": "MacInnis MJ et al. Int J Sports Physiol Perform 2019;14(1):38-45, "
        "PMID 29809063",
        "finding": "20-minute power 342-344 W vs 60-minute power 309 W (ratio about 1.11); "
        "20-minute test typical error 4.6 W; 8 trained cyclists",
        "status": "confirmed",
    },
    "martinez_navarro_2021": {
        "short": "Martinez-Navarro 2021",
        "citation": "Martinez-Navarro I et al. Eur J Sport Sci 2021;21(12):1668-1674, "
        "PMID 33251988",
        "finding": "Three 40-minute moderate sessions from 48 h after a marathon did not "
        "slow muscle-damage recovery and sped neuromuscular recovery vs rest; 64 runners",
        "status": "confirmed",
    },
    "mujika_padilla_2000": {
        "short": "Mujika & Padilla 2000",
        "citation": "Mujika I, Padilla S. Sports Med 2000;30(2):79-87, PMID 10966148",
        "finding": "Short-term (<= 4 weeks) detraining cuts VO2max and blood volume quickly "
        "in highly trained athletes",
        "status": "partly",
    },
    "neal_2013": {
        "short": "Neal 2013",
        "citation": "Neal CM et al. J Appl Physiol 2013;114(4):461-471, PMID 23264537",
        "finding": "Polarized 80/0/20 at 6.4 h/week beat threshold 57/43/0 for peak power, "
        "lactate threshold and high-intensity capacity over 6 weeks; 12 trained cyclists",
        "status": "confirmed",
    },
    "nielsen_2014": {
        "short": "Nielsen 2014",
        "citation": "Nielsen RO et al. J Orthop Sports Phys Ther 2014;44(10):739-747, "
        "PMID 25155475",
        "finding": "Novice runners progressing weekly distance more than 30% had more "
        "distance-related injuries than those under 10% (HR 1.59, p = 0.07); 874 runners",
        "status": "confirmed",
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
        "citation": "Seiler S. Int J Sports Physiol Perform 2010;5(3):276-291, PMID 20861519",
        "finding": "Endurance athletes training 10-13 times a week do about 80% of sessions "
        "at low intensity",
        "status": "confirmed",
    },
    "seiler_kjerland_2006": {
        "short": "Seiler & Kjerland 2006",
        "citation": "Seiler KS, Kjerland GO. Scand J Med Sci Sports 2006;16(1):49-56, "
        "PMID 16430681",
        "finding": "Junior skiers' sessions by heart rate: 75% zone 1, 8% zone 2, 17% zone 3",
        "status": "confirmed",
    },
    "treff_2019": {
        "short": "Treff 2019",
        "citation": "Treff G et al. Front Physiol 2019;10:707, PMID 31249533",
        "finding": "Polarization index log10(z1 / z2 x z3 x 100), shares in fractions; "
        "above 2.00 marks a polarized distribution",
        "status": "confirmed",
    },
    "vesterinen_2016": {
        "short": "Vesterinen 2016",
        "citation": "Vesterinen V et al. Med Sci Sports Exerc 2016;48(7):1347-1354, PMID 26909534",
        "finding": "Hard sessions only when morning HRV was within the individual smallest "
        "worthwhile change: fewer hard sessions, 3000 m improved; 40 recreational runners",
        "status": "confirmed",
    },
    "wang_2023": {
        "short": "Wang 2023",
        "citation": "Wang Z et al. PLoS One 2023;18(5):e0282838, PMID 37163550",
        "finding": "Tapers of up to 21 days cutting volume 41-60% progressively, intensity "
        "and frequency held, improved time-trial performance; 14 studies",
        "status": "confirmed",
    },
}

# Order used to give a mixed constant the basis of its weakest value.
BASIS_STRENGTH = {"default": 0, "derived": 1, "sourced": 2}

PARAMETER_SOURCES: dict[str, dict[str, Any]] = {
    "PHASE_FROM_A_RACE": {
        "basis": "default",
        "parts": {
            "recovery_post_a": "default",
            "taper": "sourced",
            "peak": "default",
            "build": "default",
            "base": "default",
        },
        "rationale": "Taper window is the two-week optimum; recovery 14 days, peak 4 weeks "
        "and build 12 weeks out are common periodization practice; no trial sets them",
        "refs": ["bosquet_2007"],
    },
    "READINESS_THRESHOLDS": {
        "basis": "default",
        "rationale": "Trials swapped hard days when HRV fell below the 10-day mean - 1 SD "
        "or left the smallest worthwhile change; amber at -0.5 SD swaps earlier, red at "
        "-1.5 SD later. Those trials used 7-10 day baselines, this uses 60 days and one "
        "day's z (assessment R8). Sleep debt 2 h against the athlete's mean puts most "
        "athletes near the 6 h line where performance fell. RHR cut-offs have no trial",
        "refs": [
            "kiviniemi_2007",
            "vesterinen_2016",
            "javaloyes_2019",
            "plews_2013",
            "craven_2022",
        ],
    },
    "TSB_EXCURSION_THRESHOLD": {
        "basis": "default",
        "rationale": "TSB -25 marks a deep fatigue excursion when measuring this athlete's "
        "own tolerance; the tolerance, not the cut-off, drives the ramp. No peer-reviewed "
        "TSB cut-off was found",
        "refs": [],
    },
    "TSB_RECOVERED_THRESHOLD": {
        "basis": "default",
        "rationale": "TSB back above -10 counts as recovered from an excursion. No "
        "peer-reviewed TSB cut-off was found",
        "refs": [],
    },
    "DISTRIBUTION_MODELS": {
        "basis": "default",
        "parts": {"shares": "sourced", "min_weekly_hours": "default"},
        "rationale": "Shares are trial arms: pyramidal 80/12/8 and threshold 67/25/8 "
        "(Esteve-Lanao), polarized 75/8/17 observed (Seiler & Kjerland); polarization "
        "index 2.20 for polarized, under 2 for the others. Polarized from 8 h follows "
        "Neal's gains at 6.4 h/week; pyramidal below, and offered to recreational "
        "athletes (Rosenblat 2025); threshold under 6 h is a coaching choice",
        "refs": [
            "seiler_2010",
            "seiler_kjerland_2006",
            "esteve_lanao_2007",
            "neal_2013",
            "treff_2019",
            "rosenblat_2019",
            "rosenblat_2025",
        ],
    },
    "TAPER": {
        "basis": "sourced",
        "rationale": "Duration, volume cut, exponential shape and held intensity and "
        "frequency are the meta-analysis findings",
        "refs": ["bosquet_2007", "wang_2023"],
    },
    "RAMP": {
        "basis": "default",
        "rationale": "No trial sets a CTL ramp. In a steady ramp weekly load grows by "
        "r / (CTL + 6.51 r) a week: 4-7% at CTL 50, under the 10% band where running "
        "cohorts saw no added injury from weekly progression. Three-week blocks and a 60% "
        "recovery week are common practice; not scaled to CTL yet (assessment M1)",
        "refs": ["nielsen_2014", "buist_2008", "frandsen_2025"],
    },
    "CTL_WEEK_GAIN_FACTOR": {
        "basis": "derived",
        "rationale": "Daily load that moves a 42-day EWMA by r in 7 days is "
        "CTL + r / (1 - e^(-7/42)); 1 / 0.1535 = 6.51",
        "refs": [],
    },
    "RAMP_WEEK_OVER_WEEK_MAX": {
        "basis": "default",
        "rationale": "Weekly increases over 30% carried the only injury signal (novice "
        "runners, p = 0.07) and 1.3 tops the acute:chronic band, which is not itself a valid "
        "gate; 10% was not protective. Reference is the larger of last week and the 3-week "
        "mean so a recovery week does not lower the next one",
        "refs": ["nielsen_2014", "buist_2008", "gabbett_2016", "impellizzeri_2020"],
    },
    "LONG_RUN_SPIKE": {
        "basis": "default",
        "parts": {"max_ratio": "sourced", "window_days": "sourced", "horizon_days": "default"},
        "rationale": "A run more than 10% longer than the longest of the last 30 days raised "
        "the injury rate in 5,205 runners; the 14-day look-ahead is the brief's planning "
        "window. Runs only: no cycling study links load spikes to injury",
        "refs": ["frandsen_2025"],
    },
    "RAMP_SELECTION": {
        "basis": "default",
        "rationale": "Tier from the athlete's own TSB history: how deep and how often they "
        "went and how fast they came back; thresholds are coaching choices, no study found",
        "refs": [],
    },
    "RECOVERY_WEEK_RATIO": {
        "basis": "default",
        "rationale": "A week at or under 75% of the three before it is treated as a "
        "recovery week when counting loading weeks; set above the 60% recovery-week "
        "target plus its 10% range (66%) so a prescribed recovery week counts",
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
        "rationale": "At most half of recent load for 7-14 days after an A-race. Easy "
        "sessions from 48 h after a marathon did not slow recovery, so easy riding is "
        "allowed; no study sets the share",
        "refs": ["martinez_navarro_2021"],
    },
    "HARD_SESSION_INTENSITY_FACTOR": {
        "basis": "default",
        "rationale": "IF >= 0.85 counts as hard; misses VO2 sessions that average lower "
        "(assessment M4). No study classifies sessions by IF",
        "refs": [],
    },
    "FTP_CHECK": {
        "basis": "default",
        "parts": {
            "twenty_min_factor": "sourced",
            "short_bias_ratio": "default",
            "change_pct": "derived",
        },
        "rationale": "0.95 x 20m matched 60-minute power on average (Borszcz 2018) though "
        "other groups ran 20m / 60m about 1.11 (MacInnis) and 0.91 fitted MLSS "
        "(Lillo-Bevia); 1.15 flags riders well past the published ratios; 5% exceeds the "
        "20m test's 2.9% CV and 4.7% typical error against MLSS",
        "refs": [
            "borszcz_2018",
            "borszcz_2019",
            "borszcz_2020",
            "macinnis_2019",
            "lillo_bevia_2022",
            "allen_coggan_2010",
        ],
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
        line = f"{name}: {entry['basis']}"
        parts = entry.get("parts", {})
        stronger = [f"{key} {basis}" for key, basis in parts.items() if basis != "default"]
        if stronger:
            line += f" [{', '.join(stronger)}]"
        lines.append(line + (f" ({refs})" if refs else ""))
    lines.append("```")
    return "\n".join(lines) + "\n"
