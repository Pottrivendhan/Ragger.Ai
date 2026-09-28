import json
import time
import urllib.request
import urllib.error

TOKEN = "c545d143530d5ccdb930ddaaee25d9ccb33fc2c4176cb839e141d5409e49a746"
URL = "http://127.0.0.1:8000/api/v1/chat/generate"

TEST_QUERIES = [
    ("Test 1", "The Grumble Family auther name?"),
    ("Test 2", "who is Dr. Ashok T. Krishnan’s"),
    ("Test 3", "why was the young seagull afraid to fly?"),
    ("Test 4", "what happened when the young seagull finally flew?"),
    ("Test 5", "what is the capital of france?"),
    ("Test 6", "Give me a comprehensive summary of this document."),
]

def run_query(test_name: str, query: str):
    print("=" * 70, flush=True)
    print(f"RUNNING {test_name}: {query}", flush=True)
    print("=" * 70, flush=True)
    payload = {"query": query}
    req = urllib.request.Request(
        URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {TOKEN}",
            "Content-Type": "application/json"
        },
        method="POST"
    )
    start = time.time()
    try:
        with urllib.request.urlopen(req, timeout=300) as resp:
            elapsed = time.time() - start
            data = json.loads(resp.read().decode())
            print(f"Status: {resp.status} in {elapsed:.2f}s", flush=True)
            print(f"Original Query: {data.get('original_query')}", flush=True)
            print(f"Normalized Query: {data.get('normalized_query')}", flush=True)
            print(f"Provider: {data.get('generation_provider')}", flush=True)
            print(f"Model: {data.get('generation_model')}", flush=True)
            print(f"Citation Validation Status: {data.get('citation_validation_status')}", flush=True)
            print(f"Retrieved Chunks Count: {data.get('retrieved_chunk_count')}", flush=True)
            print(f"Has Insufficient Evidence: {data.get('has_insufficient_evidence')}", flush=True)
            citations = data.get("valid_citations", [])
            print(f"Valid Citations: {len(citations)}", flush=True)
            for c in citations:
                s_name = c.get('source_name', '').encode('ascii', errors='replace').decode('ascii')
                print(f"  * [{c.get('chunk_id')}] {s_name} (Page {c.get('page_number')})", flush=True)
            print("\nGenerated Answer:", flush=True)
            safe_answer = data.get("answer", "").encode('ascii', errors='replace').decode('ascii')
            print(safe_answer, flush=True)
            print("\n", flush=True)
            return data
    except urllib.error.HTTPError as e:
        print(f"HTTPError {e.code}: {e.read().decode('utf-8', errors='replace')}", flush=True)
    except Exception as e:
        print(f"Error: {e}", flush=True)
    return None

if __name__ == "__main__":
    for name, q in TEST_QUERIES:
        run_query(name, q)
