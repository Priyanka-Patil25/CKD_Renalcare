"""Reader agent: turns the structured patient payload into a short factual history.
Input : {"patient": <payload from service.build>}
Output: {"lines": [str], "facts": {...}}
Replace with an LLM later; keep the rule that it may only restate what is in the payload."""


def run(inp):
    p = inp["patient"]
    k = p["kdigo"]
    cond = [n.replace("_", " ") for n, v in p["conditions"].items() if v]
    lines = [f"{p['age'] or '?'} y {({'M': 'male', 'F': 'female'}).get(p['sex'], 'patient')}"
             + (f" with {', '.join(cond)}." if cond else ".")]
    if k["egfr"] is not None or k["uacr"] is not None:
        lines.append(f"Latest kidney results: eGFR {k['egfr'] if k['egfr'] is not None else 'not recorded'}"
                     f" ({k['egfr_date'] or '-'}), uACR {k['uacr'] if k['uacr'] is not None else 'not recorded'}"
                     f" ({k['uacr_date'] or '-'}).")
        lines.append(f"KDIGO category {k['stage_text']}, risk {k['risk'] or 'cannot be graded'}.")
    else:
        lines.append("No eGFR or uACR on record.")
    if k["egfr_slope"] is not None:
        lines.append(f"eGFR trend {k['egfr_slope']:+.1f} mL/min/1.73m2 per year.")
    if p["medicines"]:
        lines.append("Current medicines: " + ", ".join(m["drug"] for m in p["medicines"]) + ".")
    return {"lines": lines, "facts": {"stage": k["stage_text"], "risk": k["risk"], "slope": k["egfr_slope"]}}
