"""RAG STEP C: EMBED.  Turn a piece of text into a list of numbers (a vector) so that texts
with similar MEANING get similar vectors.

Real embedder : sentence-transformers "all-MiniLM-L6-v2" (384 numbers, runs on your laptop,
                free, nothing leaves your machine).  pip install sentence-transformers
Fallback      : HashEmbedder, a crude word-counting stand-in. It is NOT semantic. It only lets
                tests and demos run when the real model is not installed.
"""
import hashlib, re
import numpy as np

MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"


class MiniLMEmbedder:
    name = "minilm-l6-v2"

    def __init__(self):
        from sentence_transformers import SentenceTransformer
        self.model = SentenceTransformer(MODEL_NAME)

    def embed(self, texts):
        return np.asarray(self.model.encode(list(texts), normalize_embeddings=True), dtype="float32")


class HashEmbedder:
    name = "hash-fallback"
    DIM = 384

    def embed(self, texts):
        out = np.zeros((len(texts), self.DIM), dtype="float32")
        for r, t in enumerate(texts):
            for w in re.findall(r"[a-z0-9]+", t.lower()):
                out[r, int(hashlib.md5(w.encode()).hexdigest(), 16) % self.DIM] += 1
        n = np.linalg.norm(out, axis=1, keepdims=True)
        return out / np.where(n == 0, 1, n)


_cached = None


def get_embedder():
    global _cached
    if _cached is None:
        try:
            _cached = MiniLMEmbedder()
        except Exception as e:                         # not installed / model not downloadable
            print("NOTE: using the non-semantic fallback embedder:", str(e)[:80])
            _cached = HashEmbedder()
    return _cached
