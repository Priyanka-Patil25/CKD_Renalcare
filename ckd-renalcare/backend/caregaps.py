"""
Care-gap and medication-safety rules for the CKD doctor dashboard.

Plain code, no ML. Each rule looks at ONE patient's visit history and returns
flags that the doctor can accept, edit or dismiss. Nothing here orders a drug
or a test; it only points out what the guideline says may be missing.

Thresholds follow KDIGO 2024 (CKD), KDIGO 2022 (Diabetes in CKD) and
KDIGO 2021 (BP in CKD). Recommendation numbers must still be checked against
the PDFs before the final report (see SOURCES).
"""
from dataclasses import dataclass, field
from datetime import date, datetime
import re

SOURCES = {
    "monitoring": "KDIGO 2024 CKD, Practice Points 2.1.1-2.1.2 and Figure 13 (S197)",
    "rasi":       "KDIGO 2024 CKD, Recommendations 3.6.1-3.6.3 (S158)",
    "sglt2i":     "KDIGO 2024 CKD, Recommendations 3.7.1-3.7.3 (S159); KDIGO 2022 Diabetes, Rec 1.3.1",
    "nsaid":      "KDIGO 2024 CKD, Chapter 4 (OTC medicines, nephrotoxic drug table). The eGFR <60 cut-off is a project rule",
    "metformin":  "KDIGO 2022 Diabetes in CKD, Rec 4.1.1, Practice Point 4.1.3 and Figure 27",
    "progress":   "Project rule (>5 per year). Not in the KDIGO 2024 text; believed to come from KDIGO 2012. Verify",
    "drop20":     "KDIGO 2024 CKD, Practice Point 2.1.3 (change in eGFR >20% warrants evaluation)",
    "referral":   "KDIGO 2024 CKD, Practice Point 5.1.1 and Figure 48 (eGFR <30; ACR >700; sustained eGFR fall >20%)",
    "bp":         "KDIGO 2024 CKD Rec 3.4.1 and KDIGO 2021 BP Rec 3.1.1 (target SBP <120, standardized measurement). The 140 alert level is a project rule",
    "confirm":    "KDIGO 2024 CKD, Practice Points 1.1.3.1-1.1.3.2 (chronicity: at least 3 months)",
}


@dataclass
class Flag:
    code: str
    level: str          # "high", "medium", "info"
    title: str
    detail: str
    source: str


@dataclass
class Visit:
    date: date
    egfr: float | None = None
    uacr: float | None = None      # mg/g
    sbp: float | None = None
    meds: set = field(default_factory=set)   # lower-case words, e.g. {"acei", "nsaid"}
    diabetes: bool = False
    htn: bool = False


# ---------- helpers ----------

def parse_uacr(x):
    """'1+ / 150' -> 150.0 ; 'neg / 18' -> 18.0 ; 150 -> 150.0 ; blank -> None"""
    if x is None:
        return None
    if isinstance(x, (int, float)):
        return None if x != x else float(x)
    m = re.search(r"([\d.]+)\s*$", str(x).strip())
    return float(m.group(1)) if m else None


def parse_meds(x):
    if x is None or (isinstance(x, float) and x != x):
        return set()
    return {w for w in re.split(r"[^a-z0-9]+", str(x).lower()) if w}


from kdigo import g_cat, a_cat, risk_of, MONITOR_MONTHS as _MONTHS, monitor_months  # noqa: E402


def last_with(visits, attr):
    for v in sorted(visits, key=lambda v: v.date, reverse=True):
        if getattr(v, attr) is not None:
            return v
    return None


def egfr_slope(visits, min_points=3, min_days=180):
    """Least-squares slope in mL/min/1.73m2 per year, or None if too little data."""
    pts = sorted((v.date, v.egfr) for v in visits if v.egfr is not None)
    if len(pts) < min_points or (pts[-1][0] - pts[0][0]).days < min_days:
        return None
    xs = [(d - pts[0][0]).days / 365.25 for d, _ in pts]
    ys = [e for _, e in pts]
    mx, my = sum(xs) / len(xs), sum(ys) / len(ys)
    den = sum((x - mx) ** 2 for x in xs)
    return None if den == 0 else sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / den


def has(meds, *names):
    return any(n in meds for n in names)


# ---------- the rules ----------

def evaluate(visits, today=None):
    """visits: list[Visit] for one patient. Returns list[Flag], most urgent first."""
    flags = []
    if not visits:
        return flags
    visits = sorted(visits, key=lambda v: v.date)
    today = today or visits[-1].date
    cur = visits[-1]
    diabetes = any(v.diabetes for v in visits)
    htn = any(v.htn for v in visits)
    meds = cur.meds

    e_v, u_v = last_with(visits, "egfr"), last_with(visits, "uacr")
    egfr = e_v.egfr if e_v else None
    uacr = u_v.uacr if u_v else None
    ckd_range = (egfr is not None and egfr < 60) or (uacr is not None and uacr >= 30)

    # 1. No kidney labs at all in a patient at risk
    if egfr is None and uacr is None:
        if diabetes or htn:
            flags.append(Flag("NO_LABS", "high", "No eGFR or uACR on record",
                "Patient has diabetes/hypertension but no kidney tests are recorded. Consider ordering serum creatinine (eGFR) and urine ACR.",
                SOURCES["monitoring"]))
        return flags   # nothing else can be judged without labs (BP rule still useful, see below)

    # 2. Overdue tests
    risk = risk_of(egfr, uacr) or ("moderate" if ckd_range else "low")
    gap = monitor_months(egfr, uacr) or _MONTHS[risk]      # Figure 13 (KDIGO 2024, S197)
    if u_v is None and (diabetes or htn or ckd_range):
        flags.append(Flag("UACR_MISSING", "high", "uACR never recorded",
            "eGFR is on record but urine albumin-creatinine ratio is not. uACR is needed for the KDIGO stage and risk.",
            SOURCES["monitoring"]))
    elif u_v is not None:
        m = (today - u_v.date).days / 30.4
        if m > gap:
            flags.append(Flag("UACR_OVERDUE", "medium", f"uACR overdue ({m:.0f} months)",
                f"Last uACR was {u_v.date}. For '{risk}' risk, KDIGO suggests checking about every {gap} months.",
                SOURCES["monitoring"]))
    if e_v is not None:
        m = (today - e_v.date).days / 30.4
        if m > gap:
            flags.append(Flag("EGFR_OVERDUE", "medium", f"eGFR overdue ({m:.0f} months)",
                f"Last eGFR was {e_v.date}. For '{risk}' risk, KDIGO suggests checking about every {gap} months.",
                SOURCES["monitoring"]))

    # 3. First abnormal result, not yet confirmed over 3 months
    if ckd_range:
        abn = [v for v in visits if (v.egfr is not None and v.egfr < 60) or (v.uacr is not None and v.uacr >= 30)]
        if (abn[-1].date - abn[0].date).days < 90:
            flags.append(Flag("CONFIRM", "info", "Abnormal result not yet confirmed",
                "CKD needs the abnormality to persist for more than 3 months. Repeat eGFR/uACR after 3 months before labelling CKD.",
                SOURCES["confirm"]))

    # 4. RAS inhibitor for albuminuria
    if uacr is not None and uacr >= 30 and not has(meds, "acei", "arb", "ramipril", "enalapril", "lisinopril",
                                                   "telmisartan", "losartan", "olmesartan", "valsartan"):
        strong = uacr > 300 or diabetes
        flags.append(Flag("NO_RASI", "high" if strong else "medium",
            "Albuminuria but no ACEi/ARB on record",
            f"uACR is {uacr:g} mg/g. KDIGO recommends an ACEi or ARB for albuminuria with diabetes or when uACR is above 300; "
            "for A2 without diabetes it is a suggestion. Doctor to decide (check BP, potassium, creatinine first).",
            SOURCES["rasi"]))

    # 5. SGLT2 inhibitor
    if egfr is not None and egfr >= 20 and not has(meds, "sglt2i", "dapagliflozin", "empagliflozin", "canagliflozin"):
        if (diabetes and ckd_range) or (uacr is not None and uacr >= 200):
            flags.append(Flag("NO_SGLT2I", "medium", "Consider SGLT2 inhibitor",
                f"eGFR {egfr:g}, uACR {uacr if uacr is not None else 'not recorded'}. KDIGO recommends an SGLT2i for CKD with type 2 diabetes, "
                "or uACR 200 mg/g or more, when eGFR is 20 or above. Doctor to decide.",
                SOURCES["sglt2i"]))

    # 6. NSAID with low eGFR
    if has(meds, "nsaid", "ibuprofen", "diclofenac", "naproxen", "aceclofenac") and egfr is not None and egfr < 60:
        flags.append(Flag("NSAID", "high", "NSAID on the medicine list with eGFR below 60",
            f"eGFR is {egfr:g}. KDIGO says chronic NSAID use in CKD should be discouraged and lists acetaminophen as a non-nephrotoxic alternative; "
            "careful NSAID use under a nephrologist's supervision can still be better than opioids. The eGFR <60 trigger is this project's own rule.",
            SOURCES["nsaid"]))

    # 7. Metformin and eGFR
    if has(meds, "metformin") and egfr is not None:
        if egfr < 30:
            flags.append(Flag("METFORMIN_STOP", "high", "Metformin with eGFR below 30",
                f"eGFR is {egfr:g}. Metformin should be stopped when eGFR is below 30.", SOURCES["metformin"]))
        elif egfr < 45:
            flags.append(Flag("METFORMIN_DOSE", "medium", "Metformin with eGFR 30-44",
                f"eGFR is {egfr:g}. Review the dose; KDIGO suggests reducing it when eGFR is below 45.", SOURCES["metformin"]))

    # 8. eGFR falling: (a) project slope rule, (b) KDIGO 2024 PP 2.1.3: a change of more than 20% needs evaluation
    s = egfr_slope(visits)
    if s is not None and s < -5:
        flags.append(Flag("RAPID_DECLINE", "high", f"eGFR falling fast ({s:.1f} per year)",
            "The eGFR is falling by more than 5 mL/min/1.73m2 a year (project rule). Look for causes (BP, NSAIDs, dehydration, obstruction).",
            SOURCES["progress"]))
    egfrs = [v.egfr for v in visits if v.egfr is not None]
    drop = None
    if len(egfrs) >= 2 and egfrs[-2] > 0:
        drop = (egfrs[-2] - egfrs[-1]) / egfrs[-2] * 100
        if drop > 20:
            flags.append(Flag("EGFR_DROP20", "medium", f"eGFR fell {drop:.0f}% since the previous test",
                f"eGFR went from {egfrs[-2]:g} to {egfrs[-1]:g}. KDIGO says a change of more than 20% exceeds expected variability and warrants evaluation. Repeat to confirm.",
                SOURCES["drop20"]))

    # 9. Nephrology referral (KDIGO 2024 Figure 48)
    reasons = []
    if egfr is not None and egfr < 30: reasons.append(f"eGFR {egfr:g} (below 30)")
    if uacr is not None and uacr > 700: reasons.append(f"uACR {uacr:g} (above 700)")
    if drop is not None and drop > 20: reasons.append(f"eGFR fell {drop:.0f}% (if sustained)")
    if reasons:
        flags.append(Flag("REFER", "high", "Consider nephrology referral",
            "Reasons: " + ", ".join(reasons) + ". Other KDIGO referral reasons (5-year kidney failure risk above 3-5%, uACR 300+ with blood in urine, "
            "doubling of uACR, four or more BP drugs) are not checked yet.", SOURCES["referral"]))

    # 10. BP above goal on the last two readings
    sbps = [v.sbp for v in visits if v.sbp is not None][-2:]
    if len(sbps) == 2 and min(sbps) >= 140 and (ckd_range or diabetes or htn):
        flags.append(Flag("BP_HIGH", "medium", "BP above goal on last two visits",
            f"Systolic BP was {sbps[0]:g} then {sbps[1]:g}. KDIGO suggests a target below 120 when measured the standard way; "
            "this alert fires at 140 or more to avoid noise.", SOURCES["bp"]))

    order = {"high": 0, "medium": 1, "info": 2}
    return sorted(flags, key=lambda f: order[f.level])
