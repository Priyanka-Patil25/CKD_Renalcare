"""STEP 7: THE VERIFIER (a second, independent check on the agent's answer).

Plain code, not an LLM, so it cannot be talked into agreeing. It checks:
  1. Every number in the answer also appears in some tool result (no invented numbers).
  2. Every [citation] in the answer matches a guideline page or care-gap source the tools returned.
  3. The answer is not empty, and does not claim the agent changed the record.
It returns a verdict; the UI shows it next to the answer.
"""
import json, re

CHANGE_CLAIMS = re.compile(r"\b(i (have )?(updated|changed|saved|prescribed|ordered|stopped)|has been (updated|prescribed|ordered))\b", re.I)


def _numbers(text):
    return {n.lstrip("+-").rstrip(".") for n in re.findall(r"[-+]?\d+(?:\.\d+)?", text)}


def verify(answer, history):
    problems = []
    if not answer or len(answer.strip()) < 20:
        return {"ok": False, "problems": ["empty answer"], "checked": {}}
    evidence = json.dumps([h["result"] for h in history], default=str)
    ev_numbers = _numbers(evidence)
    # citations that the tools actually returned
    allowed = set()
    for h in history:
        r = h["result"]
        for p in r.get("passages", []) if isinstance(r, dict) else []:
            allowed.add(f"{p['doc']} {p['page']}".lower())
        for f in r.get("flags", []) if isinstance(r, dict) else []:
            allowed.add(str(f.get("source", "")).lower())

    # 1. numbers (skip tiny numbers like list markers and years)
    unknown = [n for n in _numbers(answer) if n not in ev_numbers and float(n) >= 10 and not 1900 <= float(n) <= 2100]
    if unknown:
        problems.append(f"numbers not found in any tool result: {sorted(unknown)[:5]}")
    # 2. citations
    cites = re.findall(r"\[([^\]]{3,120})\]", answer)
    bad = [c for c in cites if c.lower() not in allowed and not any(c.lower() in a or a in c.lower() for a in allowed if a)]
    if bad:
        problems.append(f"citations not backed by a tool result: {bad[:3]}")
    # 3. claims of action
    if CHANGE_CLAIMS.search(answer):
        problems.append("the answer claims an action was taken; agents only suggest")
    return {"ok": not problems, "problems": problems,
            "checked": {"numbers": len(_numbers(answer)), "citations": len(cites)}}
