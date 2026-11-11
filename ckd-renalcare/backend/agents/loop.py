"""The agent loop. This is the whole idea of an agent in about 40 lines:

    ask the LLM what to do  ->  run the tool it chose  ->  show it the result  ->  repeat
    until the LLM says it is finished (or we hit the step limit).
"""
import json
import db
from agents import tools as T

MAX_STEPS = 8


def run(study_id, llm, goal="Prepare a short, source-based briefing for the doctor about this patient."):
    messages = [{"role": "user", "content": goal, "study_id": study_id}]
    steps, final, seen = [], None, set()
    specs = T.specs()

    for n in range(1, MAX_STEPS + 1):
        decision = llm.next(messages, specs)

        if "final" in decision:                       # the LLM says it is done
            final = decision["final"]
            break

        name, args = decision.get("tool"), decision.get("args", {})
        key = (name, json.dumps(args, sort_keys=True))
        if key in seen:                               # same call twice = it is stuck in a loop
            final = "Stopped: the agent repeated itself."
            break
        seen.add(key)

        tool = T.TOOLS.get(name)
        if tool is None:                              # the LLM asked for a tool that does not exist
            result = {"error": f"unknown tool {name}"}
            brief = f"unknown tool '{name}' (ignored)"
        else:
            try:
                result = tool.fn(**args)
                brief = tool.brief(result)
            except Exception as e:                    # a tool failing must not crash the agent
                result = {"error": str(e)[:200]}
                brief = f"tool failed: {str(e)[:80]}"

        steps.append({"step": n, "tool": name, "args": args, "summary": brief})
        messages.append({"role": "assistant", "tool": name, "args": args})
        messages.append({"role": "tool", "name": name, "result": result})
    else:
        final = "Stopped: too many steps."

    out = {"steps": steps, "final": final, "mode": getattr(llm, "mode", "unknown")}
    pid = db.one("SELECT id FROM patients WHERE study_id=%s", (study_id,))
    db.run("INSERT INTO agent_runs(patient_id, agent, input, output, status) VALUES (%s,%s,%s,%s,'ok')",
           (pid["id"] if pid else None, "briefing_agent", json.dumps({"study_id": study_id, "goal": goal}), json.dumps(out, default=str)))
    return out
