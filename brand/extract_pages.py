import sys
from pypdf import PdfReader

path = sys.argv[1]
start = int(sys.argv[2])
end = int(sys.argv[3])
reader = PdfReader(path)
for i in range(start - 1, min(end, len(reader.pages))):
    print(f"\n===== Seite {i+1} =====")
    try:
        print((reader.pages[i].extract_text() or "").strip())
    except Exception as e:
        print("[err]", e)
