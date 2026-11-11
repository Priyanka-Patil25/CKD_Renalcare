"""KDIGO calculations. Plain code, no ML. Same inputs always give the same output.

Stage grid: G (eGFR) x A (uACR). Risk colours follow the KDIGO 2024 heat map.
CKD-EPI 2021 equation (race-free) for eGFR from creatinine.
"""

G_BANDS = [(90, "G1"), (60, "G2"), (45, "G3a"), (30, "G3b"), (15, "G4")]
G_LABELS = {
    "G1": "Normal or high (90+)", "G2": "Mildly decreased (60-89)",
    "G3a": "Mild to moderate (45-59)", "G3b": "Moderate to severe (30-44)",
    "G4": "Severely decreased (15-29)", "G5": "Kidney failure (<15)",
}
A_LABELS = {"A1": "Normal to mild (<30 mg/g)", "A2": "Moderately increased (30-300)", "A3": "Severely increased (>300)"}

# risk[G][A]  -> low / moderate / high / very high   (green / yellow / orange / red)
RISK_GRID = {
    "G1":  {"A1": "low",       "A2": "moderate",  "A3": "high"},
    "G2":  {"A1": "low",       "A2": "moderate",  "A3": "high"},
    "G3a": {"A1": "moderate",  "A2": "high",      "A3": "very high"},
    "G3b": {"A1": "high",      "A2": "very high", "A3": "very high"},
    "G4":  {"A1": "very high", "A2": "very high", "A3": "very high"},
    "G5":  {"A1": "very high", "A2": "very high", "A3": "very high"},
}
# Months between checks by risk. Approximation of the KDIGO heat-map numbers (1,1,2,3,4 a year).
# TO VERIFY against the KDIGO 2024 PDF before the final report.
MONITOR_MONTHS = {"low": 12, "moderate": 12, "high": 6, "very high": 4}   # old rough fallback, used only if a cell is unknown

# KDIGO 2024 CKD guideline, Figure 13 (page S197): suggested number of GFR + albuminuria checks PER YEAR.
# Rows are GFR category, columns are A1, A2, A3.  "4+" is stored as 4.  G1/G2 with A1 = "Screen" once a year.
FIG13_PER_YEAR = {
    "G1":  {"A1": 1, "A2": 1, "A3": 3},
    "G2":  {"A1": 1, "A2": 1, "A3": 3},
    "G3a": {"A1": 1, "A2": 2, "A3": 3},
    "G3b": {"A1": 2, "A2": 3, "A3": 3},
    "G4":  {"A1": 3, "A2": 3, "A3": 4},
    "G5":  {"A1": 4, "A2": 4, "A3": 4},
}


def monitor_months(egfr, uacr):
    """Months between checks from Figure 13. If uACR is unknown, uses the lowest frequency
    in that GFR row (A1) so we never over-state urgency. None if eGFR is unknown."""
    g = g_cat(egfr)
    if g is None:
        return None
    a = a_cat(uacr) or "A1"
    return 12 / FIG13_PER_YEAR[g][a]


def egfr_ckdepi_2021(creatinine_mg_dl: float, age: float, sex: str) -> float:
    """CKD-EPI 2021. sex is 'M' or 'F'. Returns mL/min/1.73 m2, rounded to 1 decimal."""
    female = sex.upper().startswith("F")
    k = 0.7 if female else 0.9
    a = -0.241 if female else -0.302
    v = (142 * min(creatinine_mg_dl / k, 1) ** a * max(creatinine_mg_dl / k, 1) ** -1.200
         * 0.9938 ** age * (1.012 if female else 1.0))
    return round(v, 1)


def g_cat(egfr):
    if egfr is None:
        return None
    for lim, c in G_BANDS:
        if egfr >= lim:
            return c
    return "G5"


def a_cat(uacr):
    if uacr is None:
        return None
    return "A1" if uacr < 30 else ("A2" if uacr <= 300 else "A3")


def risk_of(egfr, uacr):
    """Risk level. G4 and G5 are always very high, even if uACR is missing."""
    g, a = g_cat(egfr), a_cat(uacr)
    if g in ("G4", "G5"):
        return "very high"
    if g is None or a is None:
        return None
    return RISK_GRID[g][a]


def summary(egfr, uacr):
    g, a = g_cat(egfr), a_cat(uacr)
    risk = risk_of(egfr, uacr)
    return {
        "egfr": egfr, "uacr": uacr, "g": g, "a": a,
        "g_label": G_LABELS.get(g), "a_label": A_LABELS.get(a),
        "risk": risk,
        "stage_text": (f"{g} {a}" if g and a else (g or a or "Not enough results")),
        "monitor_months": monitor_months(egfr, uacr) or MONITOR_MONTHS.get(risk),
        "ckd_range": bool((egfr is not None and egfr < 60) or (uacr is not None and uacr >= 30)),
    }


def grid():
    """For the front end: rows of G, columns of A, with the risk in each cell."""
    return {"rows": list(RISK_GRID), "cols": ["A1", "A2", "A3"], "risk": RISK_GRID,
            "g_labels": G_LABELS, "a_labels": A_LABELS}
