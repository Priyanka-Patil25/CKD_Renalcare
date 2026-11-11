"""Writer agent: drafts a visit summary. Template-based for now.
Input : {"reader": <reader output>, "flags": [...], "hits": [...]}
Output: {"draft": str, "citations": [str]}
The doctor edits or deletes the draft; nothing is saved until they press Save notes."""


def run(inp):
    lines = list(inp.get("reader", {}).get("lines", []))
    open_flags = [f for f in inp.get("flags", []) if f.get("status") in ("pending", "accepted", "edited")]
    out = ["HISTORY"] + [f"- {l}" for l in lines]
    if open_flags:
        out += ["", "POINTS TO REVIEW (suggestions, doctor to decide)"]
        for f in open_flags:
            out.append(f"- [{f['level'].upper()}] {f.get('edited_text') or f['title']}")
    cites = [f"{h['doc']}" + (f", {h['section']}" if h.get("section") else "") + (f", p.{h['page']}" if h.get("page") else "")
             for h in inp.get("hits", [])]
    if cites:
        out += ["", "GUIDELINE PASSAGES FOUND: " + "; ".join(cites)]
    return {"draft": "\n".join(out), "citations": cites}
