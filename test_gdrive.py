import asyncio, os, time
os.chdir(r"E:\rag sys\medical-chatbot-refactored")
from gdrive_service import get_all_curriculum
start = time.time()
result = asyncio.run(get_all_curriculum())
print(f"Fetched in {time.time()-start:.1f}s")
for c in result:
    label = c["label"]
    count = len(c["subjects"])
    print(f"{label}: {count} PDFs")
    for s in c["subjects"][:2]:
        print(f"  - {s['file']}")
