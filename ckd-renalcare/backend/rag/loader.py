"""RAG STEP A+B: LOAD the guideline text and CHUNK it.

Your KDIGO .txt files have a footer at the END of every page, like:
    "Kidney International (2024) 105 (Suppl 4S), S117–S314 S197"     (odd pages)
    "S198 Kidney International (2024) 105 (Suppl 4S), S117–S314"     (even pages)
Everything above a footer belongs to that page. We use that to give every chunk a page
label such as "S197", so every answer can cite its page.
"""
import re

FOOT_A = re.compile(r"^Kidney International \(\d{4}\).*?\s(S\d+)\s*$")
FOOT_B = re.compile(r"^(S\d+) Kidney International \(\d{4}\)")


def pages_from_txt(raw):
    """Split a guideline .txt into [{'page': 'S197', 'text': ...}, ...]."""
    pages, buf = [], []
    for line in raw.splitlines():
        m = FOOT_A.match(line) or FOOT_B.match(line)
        if m:
            pages.append({"page": m.group(1), "text": "\n".join(buf)})
            buf = []
        else:
            buf.append(line)
    if "".join(buf).strip():
        pages.append({"page": "end", "text": "\n".join(buf)})
    return pages


def pages_from_pdf(path):
    from pypdf import PdfReader
    return [{"page": str(i), "text": (p.extract_text() or "").replace("\x00", "")}
            for i, p in enumerate(PdfReader(path).pages, 1)]


def chunk(text, size=900, overlap=150):
    """Cut text into ~900-character pieces, preferring to stop at a sentence end.
    Each piece repeats the last 150 characters of the previous one (overlap) so a sentence
    cut in half is still whole in one of the two pieces."""
    text = re.sub(r"\s+", " ", text).strip()
    out, i = [], 0
    while i < len(text):
        j = min(i + size, len(text))
        if j < len(text):
            k = text.rfind(". ", i + size // 2, j)
            j = k + 1 if k > 0 else j
        piece = text[i:j].strip()
        if len(piece) > 80:
            out.append(piece)
        if j >= len(text):
            break
        i = max(j - overlap, i + 1)
    return out


def chunks_for_file(path):
    """-> [{'page','text'}] for a .txt (page labels from footers) or a .pdf (page numbers)."""
    if path.lower().endswith(".pdf"):
        pages = pages_from_pdf(path)
    else:
        pages = pages_from_txt(open(path, encoding="utf-8", errors="ignore").read())
    return [{"page": p["page"], "text": c} for p in pages for c in chunk(p["text"])]
