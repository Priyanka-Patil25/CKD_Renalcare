"""Load guideline PDFs into guideline_chunks so the guideline finder can search them.
Put PDFs in backend/guidelines/ (e.g. KDIGO-2024-CKD.pdf) and run:

    python ingest_guidelines.py guidelines/KDIGO-2024-CKD.pdf "KDIGO 2024 CKD"

Needs: pip install pypdf.   Each PDF page is cut into chunks of about 900 characters.
Re-running for the same doc name replaces its old chunks."""
import re, sys
import db


def chunks(text, size=900):
    text = re.sub(r"\s+", " ", text).strip()
    out, i = [], 0
    while i < len(text):
        j = min(i + size, len(text))
        if j < len(text):
            k = text.rfind(". ", i + size // 2, j)
            j = k + 1 if k > 0 else j
        out.append(text[i:j].strip()); i = j
    return [c for c in out if len(c) > 80]


def main(path, doc):
    from pypdf import PdfReader
    r = PdfReader(path)
    db.run("DELETE FROM guideline_chunks WHERE doc=%s", (doc,))
    n = 0
    for pno, page in enumerate(r.pages, 1):
        for c in chunks((page.extract_text() or "").replace("\x00", "")):
            db.run("INSERT INTO guideline_chunks(doc, page, text) VALUES (%s,%s,%s)", (doc, pno, c)); n += 1
    print(f"{doc}: {n} chunks from {len(r.pages)} pages")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    main(sys.argv[1], sys.argv[2])
