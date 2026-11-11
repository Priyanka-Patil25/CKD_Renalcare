"""STEP 2 (part 1): THE BRAIN.

The loop asks the brain one question again and again:
      "Here is what has happened so far. What next?"
The brain answers in ONE of two ways:
      {"type": "tool_call", "name": "...", "args": {...}}      -> use a tool
      {"type": "final", "text": "..."}                         -> I am done, here is the answer

ScriptedBrain below is a FAKE brain made of if/else rules. It lets you see and test the whole
agent with no API key. Later you replace ONLY this class with a real LLM (Step 4). The tools
and the loop stay exactly the same.
"""


class ScriptedBrain:
    name = "scripted-demo-brain"

    def next_step(self, goal, history, tools):
        done = {h["tool"]: h["result"] for h in history}

        if "get_patient_summary" not in done:                         # 1. always start by looking
            return {"type": "tool_call", "name": "get_patient_summary", "args": {}}
        s = done["get_patient_summary"]

        if not s["has_kidney_labs"] and "run_screening_model" not in done:   # 2. no labs -> screening model
            return {"type": "tool_call", "name": "run_screening_model", "args": {}}
        if "get_care_gaps" not in done:                                # 3. then the rules
            return {"type": "tool_call", "name": "get_care_gaps", "args": {}}
        if "search_guidelines" not in done:                            # 4. look up the top issue
            flags = done["get_care_gaps"]["flags"]
            q = flags[0]["title"] if flags else "chronic kidney disease monitoring"
            return {"type": "tool_call", "name": "search_guidelines", "args": {"question": q}}
        return {"type": "final", "text": self._write(s, done)}          # 5. write the answer

    @staticmethod
    def _write(s, done):
        L = [f"Patient {s['study_id']}: {s['age']} y, {s['sex']}"
             + (f", with {', '.join(c.replace('_', ' ') for c in s['conditions'])}" if s["conditions"] else "") + "."]
        if s["has_kidney_labs"]:
            L.append(f"KDIGO category {s['kdigo_stage']} ({s['kdigo_risk'] or 'risk not gradable'} risk). "
                     f"eGFR {s['egfr']}, uACR {s['uacr']}."
                     + (f" eGFR trend {s['egfr_slope_per_year']:+} per year." if s["egfr_slope_per_year"] is not None else ""))
        else:
            sc = done.get("run_screening_model", {})
            L.append("No kidney labs on record. " + (f"Screening model: {sc['level'].upper()}. {sc['message']}" if "level" in sc else ""))
        flags = [f for f in done["get_care_gaps"]["flags"] if f["doctor_status"] == "pending"]
        if flags:
            L.append("Points for the doctor to review (suggestions only):")
            L += [f"  - ({f['level']}) {f['title']} [{f['source']}]" for f in flags]
        else:
            L.append("No open care gaps.")
        g = done["search_guidelines"]["passages"]
        L.append("Guideline passages: " + (" ".join(f"[{p['doc']} {p['page']}]" for p in g) if g
                                          else "none found (the guideline library may be empty)."))
        return "\n".join(L)


# ---------------------------------------------------------------------------------------------
# STEP 4: THE REAL BRAIN (a Claude model). Same method as ScriptedBrain: next_step(...).
# UNTESTED against the live API (no key in the build sandbox). The wiring is tested with a fake
# client in tests/test_agentic_llm.py. To switch it on:  pip install anthropic   and set
#     ANTHROPIC_API_KEY=sk-ant-...      (optional: CKD_CLAUDE_MODEL=claude-sonnet-5-5)
# ---------------------------------------------------------------------------------------------
import json, os

SYSTEM_PROMPT = """You are a careful clinical-support assistant for a doctor at a kidney (CKD) clinic.
Rules you must follow:
1. Start with get_patient_summary. Use run_screening_model ONLY if the patient has no kidney labs.
2. Use get_care_gaps for the rule-based findings, then search_guidelines to find the source for the most important finding.
3. Never do arithmetic or staging yourself. Quote the numbers the tools return.
4. Every clinical statement in your final answer must carry a citation in square brackets copied from a tool result,
   either a guideline page like [KDIGO 2024 CKD S197] or a care-gap source. If you have no source, say you have none.
5. You only SUGGEST. The doctor decides. Never say you changed anything. Keep the answer under 180 words, plain language."""


class ClaudeBrain:
    name = "claude-llm-brain"

    def __init__(self, client=None, model=None):
        if client is None:
            import anthropic                                   # pip install anthropic
            client = anthropic.Anthropic()                     # reads ANTHROPIC_API_KEY
        self.client = client
        self.model = model or os.getenv("CKD_CLAUDE_MODEL", "claude-sonnet-5-5")

    def next_step(self, goal, history, tools):
        # Rebuild the conversation from our own history each turn (simple and easy to inspect).
        messages = [{"role": "user", "content": goal}]
        for i, h in enumerate(history):
            tid = f"call_{i}"
            messages.append({"role": "assistant", "content": [
                {"type": "tool_use", "id": tid, "name": h["tool"], "input": h["args"]}]})
            messages.append({"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": tid, "content": json.dumps(h["result"], default=str)[:6000]}]})
        resp = self.client.messages.create(model=self.model, max_tokens=900, system=SYSTEM_PROMPT,
                                           tools=tools, messages=messages)
        for block in resp.content:
            if block.type == "tool_use":
                return {"type": "tool_call", "name": block.name, "args": dict(block.input)}
        text = "".join(b.text for b in resp.content if b.type == "text").strip()
        return {"type": "final", "text": text or "(the model returned no text)"}


class OpenAICompatBrain:
    """Brain for ANY open-source model served with an OpenAI-style API: Ollama (local, free),
    LM Studio, vLLM, or hosted ones like Groq / Together / OpenRouter.
    Default = Ollama on your own laptop:  ollama pull qwen2.5:7b-instruct   (then it just works).
    Env: CKD_LLM_URL (default http://localhost:11434/v1)   CKD_LLM_MODEL (default qwen2.5:7b-instruct)
         CKD_LLM_KEY  (only for hosted services; Ollama needs none)
    UNTESTED against a real model here; the wiring is tested with a fake server."""
    name = "open-source-llm-brain"

    def __init__(self, post=None, url=None, model=None, key=None):
        import httpx
        self.url = (url or os.getenv("CKD_LLM_URL", "http://localhost:11434/v1")).rstrip("/")
        self.model = model or os.getenv("CKD_LLM_MODEL", "qwen2.5:7b-instruct")
        self.key = key or os.getenv("CKD_LLM_KEY", "none")
        self.post = post or (lambda path, body: httpx.post(self.url + path, json=body, timeout=180,
                             headers={"Authorization": f"Bearer {self.key}"}).json())

    def next_step(self, goal, history, tools):
        msgs = [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": goal}]
        for i, h in enumerate(history):
            tid = f"call_{i}"
            msgs.append({"role": "assistant", "content": None, "tool_calls": [
                {"id": tid, "type": "function", "function": {"name": h["tool"], "arguments": json.dumps(h["args"])}}]})
            msgs.append({"role": "tool", "tool_call_id": tid, "content": json.dumps(h["result"], default=str)[:6000]})
        fn_tools = [{"type": "function", "function": {"name": t["name"], "description": t["description"],
                     "parameters": t["input_schema"]}} for t in tools]
        out = self.post("/chat/completions", {"model": self.model, "messages": msgs, "tools": fn_tools, "temperature": 0.1})
        m = out["choices"][0]["message"]
        if m.get("tool_calls"):
            c = m["tool_calls"][0]["function"]
            args = c.get("arguments") or {}
            return {"type": "tool_call", "name": c["name"], "args": json.loads(args) if isinstance(args, str) else args}
        return {"type": "final", "text": (m.get("content") or "").strip() or "(the model returned no text)"}


def get_brain():
    """Pick the brain from environment variables (first match wins):
       ANTHROPIC_API_KEY  -> Claude (paid)
       CKD_LLM_URL        -> open-source model through Ollama / LM Studio / Groq ... (free)
       nothing set        -> the scripted demo brain (no AI, always works)"""
    if os.getenv("ANTHROPIC_API_KEY"):
        try:
            return ClaudeBrain()
        except Exception as e:
            print("NOTE: Claude brain unavailable:", str(e)[:80])
    if os.getenv("CKD_LLM_URL") or os.getenv("CKD_LLM", "").lower() in ("ollama", "open", "local"):
        try:
            return OpenAICompatBrain()
        except Exception as e:
            print("NOTE: open-source brain unavailable:", str(e)[:80])
    return ScriptedBrain()
