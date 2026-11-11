"""Guideline finder agent: full-text search over guideline_chunks.
Input : {"question": str, "limit": int}
Output: {"hits": [{"doc","section","page","text","rank"}]}
Upgrade path: add pgvector + embeddings; keep the same output shape."""
import db


def run(inp):
    q = (inp.get("question") or "").strip()
    if not q:
        return {"hits": []}
    rows = db.all("""SELECT id, doc, section, page, left(text, 700) AS text,
                            ts_rank_cd(tsv, websearch_to_tsquery('english', %s)) AS rank
                     FROM guideline_chunks WHERE tsv @@ websearch_to_tsquery('english', %s)
                     ORDER BY rank DESC LIMIT %s""", (q, q, int(inp.get("limit", 4))))
    return {"hits": [{**r, "rank": float(r["rank"])} for r in rows]}
