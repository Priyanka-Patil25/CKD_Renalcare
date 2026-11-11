"""STEP 2 (part 2): THE LOOP.

    ask the brain  ->  it picks a tool  ->  we run the tool  ->  give the result back  ->  repeat
                  ...until the brain says 'final', or we run out of steps.

Guard rails (these are the 'safe agent' part, keep them):
  * max_steps        the agent cannot loop forever
  * allow-list       the brain may only use tools that exist in TOOLS
  * fixed patient    ctx comes from us, not from the brain
  * every step is saved in the agent_runs table, so you can show what happened
"""
import json, time
import db
from .tools import TOOLS
from .verify import verify


def run_agent(goal, study_id, brain, max_steps=6, save=True):
    ctx = {"study_id": study_id}
    patient_row = db.one("SELECT id FROM patients WHERE study_id=%s", (study_id,))
    pid = patient_row["id"] if patient_row else None
    history, trace = [], []
    tool_list = [t.schema() for t in TOOLS.values()]

    def log(kind, data):
        trace.append({"kind": kind, **data})
        if save:
            db.run("INSERT INTO agent_runs(patient_id, agent, input, output, status) VALUES (%s,%s,%s,%s,%s)",
                   (pid, "orchestrator", json.dumps({"goal": goal, "brain": brain.name, "step": len(history)}, ensure_ascii=False),
                    json.dumps(data, default=str, ensure_ascii=False)[:15000], data.get("status", "ok")))

    for step in range(1, max_steps + 1):
        decision = brain.next_step(goal, history, tool_list)

        if decision["type"] == "final":
            check = verify(decision["text"], history)            # independent plain-code check
            log("final", {"text": decision["text"], "verification": check})
            return {"answer": decision["text"], "trace": trace, "steps": step, "finished": True,
                    "verification": check, "brain": brain.name}

        name, args = decision.get("name"), decision.get("args", {})
        if name not in TOOLS:                                    # allow-list check
            log("blocked", {"tool": name, "reason": "unknown tool", "status": "blocked"})
            history.append({"tool": name, "args": args, "result": {"error": "unknown tool"}})
            continue
        t0 = time.time()
        try:
            result = TOOLS[name].fn(ctx, **args)
        except Exception as e:                                   # a tool failure must not crash the agent
            result = {"error": str(e)[:200]}
        history.append({"tool": name, "args": args, "result": result})
        log("tool", {"tool": name, "args": args, "result": result, "ms": round((time.time() - t0) * 1000),
                     "status": "error" if "error" in result else "ok"})

    log("stopped", {"reason": f"reached max_steps={max_steps}", "status": "stopped"})
    return {"answer": None, "trace": trace, "steps": max_steps, "finished": False}
