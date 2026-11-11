"""The 'brain' of an agent. Everything goes through ONE method:

    next(messages, tool_specs) -> {"tool": name, "args": {...}}      # "I want to use this tool"
                               or {"final": "text for the doctor"}   # "I am done"

MockLLM follows fixed rules, so the demo works offline and tests are exact.
It still makes real choices (different patients get different tools), which is the
point of an agent. In Step 2 we add a RealLLM with the same method; the loop in
loop.py does not change.
"""
import os


class MockLLM:
    mode = "demo logic (no AI model connected yet)"

    @staticmethod
    def _results(messages):
        return {m["name"]: m["result"] for m in messages if m["role"] == "tool"}

    def next(self, messages, tool_specs):
        sid = messages[0]["study_id"]
        got = self._results(messages)

        # 1. always look at the patient first
        if "get_patient_summary" not in got:
            return {"tool": "get_patient_summary", "args": {"study_id": sid}}
        summ = got["get_patient_summary"]

        # 2. choose the path from what we saw
        if summ["has_kidney_labs"]:
            if "get_care_gaps" not in got:
                return {"tool": "get_care_gaps", "args": {"study_id": sid}}
            flags = got["get_care_gaps"]["flags"]
            if flags and "search_guidelines" not in got:
                return {"tool": "search_guidelines", "args": {"question": flags[0]["title"]}}
        else:
            if "run_screening_model" not in got:
                return {"tool": "run_screening_model", "args": {"study_id": sid}}
            if "search_guidelines" not in got:
                return {"tool": "search_guidelines", "args": {"question": "when to test eGFR and albuminuria in diabetes or hypertension"}}

        # 3. write the answer using ONLY what the tools returned
        return {"final": self._write(got)}

    @staticmethod
    def _write(got):
        s = got["get_patient_summary"]
        who = f"{s['age'] or '?'} y {({'M': 'male', 'F': 'female'}).get(s['sex'], 'patient')}"
        lines = []
        if s["has_kidney_labs"]:
            lines.append(f"{who}: KDIGO {s['stage']}, {s['risk'] or 'risk not gradable'} risk (eGFR {s['egfr']}, uACR {s['uacr']}).")
            if s["egfr_slope_per_year"] is not None:
                lines.append(f"eGFR trend {s['egfr_slope_per_year']:+.1f} per year.")
            flags = got.get("get_care_gaps", {}).get("flags", [])
            if flags:
                lines.append("Points for the doctor to review:")
                lines += [f"  - [{f['level']}] {f['title']}" for f in flags]
            else:
                lines.append("No care gaps found by the rules.")
        else:
            lines.append(f"{who}: no eGFR or uACR on record, so the KDIGO stage cannot be worked out.")
            r = got.get("run_screening_model")
            if r:
                lines.append(f"Screening model level: {r['level']}. {r['message']}")
                if r["top_factors"]:
                    lines.append("Main factors: " + ", ".join(r["top_factors"]) + ".")
            lines.append("Suggestion: consider ordering serum creatinine (eGFR) and urine ACR.")
        g = got.get("search_guidelines", {}).get("hits", [])
        lines.append("Guideline passages found: " + ("; ".join(f"{h['doc']} p.{h['page']}" for h in g) if g else "none (guideline text not loaded yet)."))
        lines.append("These are suggestions. The doctor decides.")
        return "\n".join(lines)


def get_llm():
    provider = os.getenv("LLM_PROVIDER", "mock").lower()
    if provider == "mock":
        return MockLLM()
    raise RuntimeError(f"LLM_PROVIDER={provider} is not set up yet (Step 2).")
