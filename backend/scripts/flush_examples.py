"""Flush the pcdc_filter_examples ChromaDB collection by deleting all docs."""
import httpx

BASE = "http://localhost:8100/api/v1"
COLL = "pcdc_filter_examples"

# Get / create collection
r = httpx.post(f"{BASE}/collections", json={"name": COLL, "get_or_create": True})
r.raise_for_status()
cid = r.json()["id"]
print(f"Collection ID: {cid}")

cnt = httpx.get(f"{BASE}/collections/{cid}/count")
print(f"Current count: {cnt.json()}")

# Batch-delete all existing documents
BATCH = 500
deleted = 0
while True:
    get_r = httpx.post(
        f"{BASE}/collections/{cid}/get",
        json={"limit": BATCH, "include": []},
        timeout=60,
    )
    get_r.raise_for_status()
    ids = get_r.json().get("ids", [])
    if not ids:
        break
    del_r = httpx.post(
        f"{BASE}/collections/{cid}/delete",
        json={"ids": ids},
        timeout=60,
    )
    del_r.raise_for_status()
    deleted += len(ids)
    print(f"  Deleted batch of {len(ids)} (total: {deleted})")

cnt2 = httpx.get(f"{BASE}/collections/{cid}/count")
print(f"Final count after flush: {cnt2.json()}")
