# RAG step 1: read a PDF and get the text of every page.
# Run from the backend folder:   python learn/rag1_read_pdf.py guidelines/KDIGO-2024-CKD.pdf
import sys
from pypdf import PdfReader

path = sys.argv[1]                      # the PDF file you give on the command line
reader = PdfReader(path)                # open the PDF

pages = []                              # we will collect one entry per page
for number, page in enumerate(reader.pages, start=1):     # page numbers start at 1
    text = page.extract_text() or ""    # the text on this page ("" if there is none)
    text = text.replace("\x00", "")     # remove a character that breaks the database later
    pages.append({"page": number, "text": text})

# ---- look at what we got ----
print("total pages:", len(pages))
empty = [p["page"] for p in pages if len(p["text"].strip()) < 50]
print("pages with almost no text:", empty, "(a scanned PDF would show up here)")
print("average characters per page:", sum(len(p["text"]) for p in pages) // len(pages))

look = int(sys.argv[2]) if len(sys.argv) > 2 else 1
print(f"\n--- first 600 characters of page {look} ---")
print(pages[look - 1]["text"][:600])
