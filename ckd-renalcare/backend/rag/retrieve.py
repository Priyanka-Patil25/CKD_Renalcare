"""One entry point for the agents: retrieve(question, k).

  * If the real embedding model is installed  -> semantic search (rag.index.search)
  * Otherwise                                  -> keyword search in Postgres (OR of the important words)
Either way you get the same output: [{doc, page, text, score}]
"""
import re
import db
from .embedder import get_embedder, HashEmbedder

STOP = set("the and for are how what when who which should does with that this from into have has not can its their about "
           "use used using is of to in a an or on be by it as at do if than then".split())


def keyword_search(question, k=4):
    words = [w for w in re.findall(r"[a-z0-9]+", question.lower()) if len(w) > 2 and w not in STOP]
    if not words:
        return []
    q = " | ".join(dict.fromkeys(words))
    rows = db.all("""SELECT id, doc, COALESCE(section, page::text) AS page, text,
                            ts_rank_cd(tsv, to_tsquery('english', %s), 32) AS score
                     FROM guideline_chunks WHERE tsv @@ to_tsquery('english', %s)
                     ORDER BY score DESC LIMIT %s""", (q, q, k))
    return [{**r, "score": round(float(r["score"]), 3)} for r in rows]


def retrieve(question, k=4):
    emb = get_embedder()
    if not isinstance(emb, HashEmbedder):
        from .index import search
        hits = search(question, k, emb)
        if hits:
            return hits
    return keyword_search(question, k)
