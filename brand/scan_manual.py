"""Sucht im (vom Nutzer bereitgestellten) Handbuch nach Modus-Beschreibungen."""
import sys
from pypdf import PdfReader

path = sys.argv[1]
terms = ["E-Heater", "E-heater", "Electric", "Elektro", "Heizstab", "Boost",
         "ECO", "AUTO", "Vacation", "Urlaub", "Betriebsart", "Modus", "mode"]
reader = PdfReader(path)
print("pages:", len(reader.pages))
hits = {}
for i, page in enumerate(reader.pages):
    try:
        txt = page.extract_text() or ""
    except Exception:
        continue
    for t in terms:
        if t in txt:
            hits.setdefault(t, []).append(i + 1)
for t in terms:
    pages = hits.get(t, [])
    print(f"{t:12} -> {len(pages)} pages; first: {pages[:8]}")
