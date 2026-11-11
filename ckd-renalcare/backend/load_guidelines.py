"""Load the KDIGO guideline PDFs from backend/guidelines/ into the RAG knowledge base (run once, safe to re-run).
    python load_guidelines.py
Uses the semantic embedder when sentence-transformers is installed (else keyword search is used)."""
import os, sys
from rag import index
DOCS = [("guidelines/KDIGO-2024-CKD-Guideline.pdf", "KDIGO 2024 CKD"),
        ("guidelines/KDIGO-2026-AKI-AKD-Public-Review-Draft.pdf", "KDIGO 2026 AKI-AKD (public review draft)"),
        ("guidelines/KDIGO-2021-Blood-Pressure-in-CKD-Guideline.pdf", "KDIGO-2021-Blood-Pressure-in-CKD-Guideline"),
        ("guidelines/KDIGO-2022-Diabetes-Guideline.pdf", "KDIGO-2022-Diabetes-Guideline"),]
if __name__ == "__main__":
    here = os.path.dirname(os.path.abspath(__file__)); os.chdir(here)
    for path, name in DOCS:
        if os.path.exists(path): index.ingest(path, name)
        else: print("missing:", path, file=sys.stderr)
