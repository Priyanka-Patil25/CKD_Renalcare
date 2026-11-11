import pytest
import db
from rag import loader, index
from rag.embedder import HashEmbedder
from rag.retrieve import retrieve, keyword_search

RAW = """front matter
Kidney International (2024) 105 (Suppl 4S), S117–S314 S117
Recommendation 3.7.1: We recommend treating adults with CKD and type 2 diabetes with an SGLT2 inhibitor when eGFR is 20 or more. This text is long enough to become a chunk of its own.
S118 Kidney International (2024) 105 (Suppl 4S), S117–S314
Figure 13 | Frequency of monitoring GFR and albuminuria in people with chronic kidney disease. More frequent monitoring may be indicated in high-risk people, as stated here.
Kidney International (2024) 105 (Suppl 4S), S117–S314 S119
"""


def test_page_labels_come_from_footers_at_page_end():
    pages = loader.pages_from_txt(RAW)
    assert [p["page"] for p in pages] == ["S117", "S118", "S119"]
    assert "Recommendation 3.7.1" in pages[1]["text"]          # text BEFORE the S118 footer is page S118
    assert "Figure 13" in pages[2]["text"]


def test_chunking_overlaps_and_respects_size():
    text = ". ".join(f"Sentence number {i} about kidney function and monitoring" for i in range(80)) + "."
    c = loader.chunk(text, size=900, overlap=150)
    assert len(c) > 3 and all(len(x) <= 900 for x in c)
    assert c[0][-60:] in c[1]                                   # overlap: the end of chunk 0 repeats in chunk 1


def test_store_and_retrieve_round_trip(tmp_path):
    f = tmp_path / "g.txt"; f.write_text(RAW)
    emb = HashEmbedder()
    import rag.index as ix
    ix.get_embedder = lambda: emb
    n = ix.ingest(str(f), "TEST DOC")
    assert n >= 2
    hits = ix.search("SGLT2 inhibitor when eGFR is 20", k=2, embedder=emb)
    assert hits[0]["doc"] == "TEST DOC" and hits[0]["page"] == "S118"
    assert keyword_search("monitoring frequency albuminuria", 2)[0]["page"] == "S119"


def test_search_never_mixes_embedders():
    class Other(HashEmbedder):
        name = "other-model"
    assert index.search("SGLT2", 2, embedder=Other()) == []
