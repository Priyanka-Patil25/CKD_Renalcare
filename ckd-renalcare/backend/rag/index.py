"""RAG STEP D+E: STORE the vectors in Postgres and RETRIEVE the closest chunks.

Vectors live in guideline_chunks.embedding (a real[] column). Because the vectors are
normalised (length 1), cosine similarity is just a dot product. With a few thousand chunks
numpy does the search instantly, so no vector extension is needed.
Search = semantic score + a small boost for exact keyword matches (hybrid search), because
medical terms like "SGLT2" or "eGFR" should match exactly too.
"""
import re, sys
import numpy as np
import db
from . import loader
from .embedder import get_embedder

MIGRATE = """ALTER TABLE guideline_chunks ADD COLUMN IF NOT EXISTS embedding real[];
ALTER TABLE guideline_chunks ADD COLUMN IF NOT EXISTS embedder TEXT;"""


def ensure_columns():
    for s in MIGRATE.split(";"):
        if s.strip():
            db.run(s)


def ingest(path, doc, batch=64):
    """Load -> chunk -> embed -> store.  Re-running for the same doc replaces its chunks."""
    ensure_columns()
    items = loader.chunks_for_file(path)
    emb = get_embedder()
    db.run("DELETE FROM guideline_chunks WHERE doc=%s", (doc,))
    for i in range(0, len(items), batch):
        part = items[i:i + batch]
        vecs = emb.embed([p["text"] for p in part])
        for p, v in zip(part, vecs):
            db.run("INSERT INTO guideline_chunks(doc, page, section, text, embedding, embedder) VALUES (%s,%s,%s,%s,%s,%s)",
                   (doc, None, p["page"], p["text"], [float(x) for x in v], emb.name))
    print(f"{doc}: {len(items)} chunks stored (embedder: {emb.name})")
    return len(items)


def _keywords(q):
    return {w for w in re.findall(r"[a-z0-9]+", q.lower()) if len(w) > 2}


def search(question, k=4, embedder=None):
    """Return the k chunks closest in meaning to the question."""
    rows = db.all("SELECT id, doc, COALESCE(section, page::text) AS page, text, embedding, embedder FROM guideline_chunks WHERE embedding IS NOT NULL")
    if not rows:
        return []
    emb = embedder or get_embedder()
    rows = [r for r in rows if r["embedder"] == emb.name]      # never mix vectors from different models
    if not rows:
        return []
    q = emb.embed([question])[0]
    M = np.asarray([r["embedding"] for r in rows], dtype="float32")
    sem = M @ q
    kw = _keywords(question)
    boost = np.array([len(kw & _keywords(r["text"])) / max(len(kw), 1) for r in rows]) * 0.15
    score = sem + boost
    top = np.argsort(-score)[:k]
    return [{"id": rows[i]["id"], "doc": rows[i]["doc"], "page": rows[i]["page"], "text": rows[i]["text"],
             "score": round(float(score[i]), 3)} for i in top]


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit("usage: python -m rag.index <file.txt|file.pdf> \"KDIGO 2024 CKD\"")
    ingest(sys.argv[1], sys.argv[2])
