"""Watch the agent work.   From the backend folder:   python -m agentic.run_demo DEMO-001"""
import sys, json
from .loop import run_agent
from .llm import ScriptedBrain


def short(x, n=170):
    s = json.dumps(x, default=str)
    return s if len(s) <= n else s[:n] + " ..."


def main(study_id):
    out = run_agent("Prepare a pre-visit brief for the doctor", study_id, ScriptedBrain())
    print(f"\nGOAL: prepare a pre-visit brief for {study_id}\n")
    for i, t in enumerate(out["trace"], 1):
        if t["kind"] == "tool":
            print(f"STEP {i}  ACT      call tool: {t['tool']}  {t['args'] or ''}")
            print(f"         OBSERVE  {short(t['result'])}  ({t['ms']} ms)\n")
        elif t["kind"] == "blocked":
            print(f"STEP {i}  BLOCKED  {t['tool']}: {t['reason']}\n")
        elif t["kind"] == "final":
            print(f"STEP {i}  FINAL ANSWER\n")
            print(t["text"])
        else:
            print(f"STEP {i}  STOPPED  {t['reason']}")
    print(f"\nfinished={out['finished']}  steps={out['steps']}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "DEMO-001")
