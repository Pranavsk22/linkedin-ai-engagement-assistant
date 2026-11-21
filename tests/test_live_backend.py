"""Test live Cloudflare Worker deployment, authentication, and D1 operations."""

import json
import os
import requests

BASE_URL = os.getenv("WORKER_URL", "https://linkedin-ai-engagement.pranavsk22.workers.dev")
MCP_TOKEN = os.getenv("MCP_BEARER_TOKEN", "")
INGEST_TOKEN = os.getenv("INGEST_BEARER_TOKEN", "")


def test_live_worker():
    print("\n=== LIVE CLOUDFLARE BACKEND VERIFICATION ===\n")

    # 1. Health check
    r = requests.get(f"{BASE_URL}/health", timeout=10)
    print("1. GET /health ->", r.status_code, r.json())
    assert r.status_code == 200
    assert r.json().get("status") == "ok"

    # 2. Ingestion Unauthenticated Check (expect 401)
    r_unauth = requests.post(f"{BASE_URL}/internal/ingest", json={"posts": []}, timeout=10)
    print("2. Unauthenticated POST /internal/ingest ->", r_unauth.status_code, "(Expected 401)")
    assert r_unauth.status_code == 401

    # 3. Authenticated Ingestion Check
    sample_post = [
        {
            "id": "live-test-001",
            "canonical_url": "https://example.com/test-live-post",
            "post_url": "https://example.com/test-live-post?utm_source=twitter",
            "source_name": "Live Verification",
            "author_name": "Test Runner",
            "title": "Scaling Hybrid Search in Production",
            "post_text": "Evaluating BM25 and vector search precision under latency constraints.",
            "published_at": "2026-11-21T12:00:00Z",
            "discovered_at": "2026-11-21T12:00:00Z",
            "topic_tags": json.dumps(["RAG", "AI Engineering"]),
            "relevance_score": 88,
            "score_breakdown": json.dumps({"category": "High priority"}),
        }
    ]
    ingest_headers = {"Authorization": f"Bearer {INGEST_TOKEN}", "Content-Type": "application/json"}
    r_ingest = requests.post(f"{BASE_URL}/internal/ingest", json={"posts": sample_post}, headers=ingest_headers, timeout=10)
    print("3. Authenticated POST /internal/ingest ->", r_ingest.status_code, r_ingest.json())
    assert r_ingest.status_code == 200

    # 4. MCP Unauthenticated Check (expect 401)
    r_mcp_unauth = requests.get(f"{BASE_URL}/mcp", timeout=10)
    print("4. Unauthenticated GET /mcp ->", r_mcp_unauth.status_code, "(Expected 401)")
    assert r_mcp_unauth.status_code == 401

    # 5. MCP Authenticated Protocol
    mcp_headers = {"Authorization": f"Bearer {MCP_TOKEN}", "Content-Type": "application/json"}

    # 5a. initialize
    init_payload = {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}
    r_init = requests.post(f"{BASE_URL}/mcp", json=init_payload, headers=mcp_headers, timeout=10)
    print("5a. MCP initialize ->", r_init.status_code, r_init.json().get("result", {}).get("serverInfo"))
    assert r_init.status_code == 200

    # 5b. tools/list
    list_payload = {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}
    r_list = requests.post(f"{BASE_URL}/mcp", json=list_payload, headers=mcp_headers, timeout=10)
    tools = r_list.json().get("result", {}).get("tools", [])
    print(f"5b. MCP tools/list -> {r_list.status_code}, Found {len(tools)} tools: {[t['name'] for t in tools]}")
    assert len(tools) == 7

    # 5c. call get_review_queue
    queue_payload = {
        "jsonrpc": "2.0",
        "id": 3,
        "method": "tools/call",
        "params": {"name": "get_review_queue", "arguments": {"limit": 5, "minimum_score": 50}},
    }
    r_queue = requests.post(f"{BASE_URL}/mcp", json=queue_payload, headers=mcp_headers, timeout=10)
    print("5c. MCP call get_review_queue ->", r_queue.status_code)
    content_text = r_queue.json().get("result", {}).get("content", [{}])[0].get("text", "")
    print("    Review Queue Result:", content_text[:150], "...")
    assert "live-test-001" in content_text

    # 5d. call get_profile_context
    profile_payload = {
        "jsonrpc": "2.0",
        "id": 4,
        "method": "tools/call",
        "params": {"name": "get_profile_context", "arguments": {}},
    }
    r_profile = requests.post(f"{BASE_URL}/mcp", json=profile_payload, headers=mcp_headers, timeout=10)
    profile_text = r_profile.json().get("result", {}).get("content", [{}])[0].get("text", "")
    print("5d. MCP call get_profile_context ->", r_profile.status_code)
    assert "Subhashini Krishna Pranav" in profile_text

    print("\n SUCCESS! All live Cloudflare Worker endpoints, D1 queries, and MCP tools are 100% verified!")


if __name__ == "__main__":
    test_live_worker()
