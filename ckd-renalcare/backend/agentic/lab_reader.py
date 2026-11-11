"""STEP 6: THE LAB-REPORT READER AGENT (propose only, never saves).

The doctor pastes the text of a lab report. This reads it and PROPOSES values. Nothing is
written to the patient record until the doctor looks at the proposal and presses Confirm
(that button calls the normal add-results endpoint). It is deliberately plain code:
a wrong number in a medical record is worse than a missed one, so every proposal shows the
exact line it came from and a plausibility check.
"""
import re

# code -> (regex for the label, allowed range, unit note)
PATTERNS = {
    "creatinine": (r"(?:serum\s+)?creatinine", (0.1, 20), "mg/dL"),
    "egfr":       (r"e\.?gfr", (1, 200), "mL/min/1.73m2"),
    "uacr":       (r"(?:u\.?acr|albumin\s*[/:-]?\s*creatinine\s*ratio|acr)", (0, 10000), "mg/g"),
    "hba1c":      (r"hba1c|glycated\s+h(?:a)?emoglobin", (3, 20), "%"),
    "potassium":  (r"potassium|k\+", (1.5, 9), "mEq/L"),
    "bun":        (r"blood\s+urea\s+nitrogen|bun", (1, 300), "mg/dL"),
    "sodium":     (r"sodium|na\+", (100, 180), "mEq/L"),
}
NUM = r"[:=\-\s]*([<>]?\s*\d+(?:\.\d+)?)"
DATE = re.compile(r"(\d{4}-\d{2}-\d{2})|(\d{1,2})[/-](\d{1,2})[/-](\d{4})")


def propose(text):
    out, seen = [], set()
    for line in text.splitlines():
        for code, (label, (lo, hi), unit) in PATTERNS.items():
            m = re.search(rf"\b(?:{label})\b{NUM}", line, re.I)
            if not m or code in seen:
                continue
            raw = m.group(1).replace(" ", "")
            val = float(raw.lstrip("<>"))
            note = None
            if raw[0] in "<>":
                note = f"report says '{raw}': an exact value is needed, please type it"
            elif not lo <= val <= hi:
                note = f"{val} is outside the believable range {lo}-{hi}; check the report"
            seen.add(code)
            out.append({"code": code, "value": None if note and raw[0] in "<>" else val, "unit": unit,
                        "from_line": line.strip()[:120], "warning": note})
    d = DATE.search(text)
    date = None
    if d:
        date = d.group(1) or f"{d.group(4)}-{int(d.group(3)):02d}-{int(d.group(2)):02d}"
    return {"proposed": out, "report_date": date,
            "note": "PROPOSAL ONLY. Nothing has been saved. The doctor must confirm."}
