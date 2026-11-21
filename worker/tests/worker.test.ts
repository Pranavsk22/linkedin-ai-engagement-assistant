import { describe, expect, it } from "vitest";
import { verifyBearerToken } from "../src/auth";
import worker from "../src/index";
import { isValidLinkedInUrl, isValidStatus } from "../src/schemas";
import { MCP_TOOLS } from "../src/tools";

describe("Worker Authentication & Schema Validation", () => {
  it("verifies bearer tokens accurately and rejects invalid tokens", async () => {
    const valid = "super-secret-high-entropy-token-12345";
    expect(await verifyBearerToken(`Bearer ${valid}`, valid)).toBe(true);
    expect(await verifyBearerToken("Bearer wrong-token", valid)).toBe(false);
    expect(await verifyBearerToken("Basic 12345", valid)).toBe(false);
    expect(await verifyBearerToken(null, valid)).toBe(false);
    expect(await verifyBearerToken("", valid)).toBe(false);
  });

  it("validates post statuses according to the allowed lifecycle list", () => {
    expect(isValidStatus("NEW")).toBe(true);
    expect(isValidStatus("REVIEWED")).toBe(true);
    expect(isValidStatus("DRAFTED")).toBe(true);
    expect(isValidStatus("APPROVED")).toBe(true);
    expect(isValidStatus("POSTED")).toBe(true);
    expect(isValidStatus("SKIPPED")).toBe(true);
    expect(isValidStatus("INVALID_STATUS")).toBe(false);
    expect(isValidStatus("PUBLISHED")).toBe(false);
  });

  it("validates LinkedIn URLs and rejects external/invalid URLs", () => {
    expect(isValidLinkedInUrl("https://www.linkedin.com/posts/activity-12345")).toBe(true);
    expect(isValidLinkedInUrl("https://linkedin.com/feed/update/urn:li:activity:67890")).toBe(true);
    expect(isValidLinkedInUrl("https://malicious-site.com/linkedin.com")).toBe(false);
    expect(isValidLinkedInUrl("https://twitter.com/post/12345")).toBe(false);
    expect(isValidLinkedInUrl("not-a-url")).toBe(false);
  });
});

describe("Worker HTTP Endpoints", () => {
  const dummyEnv: any = {
    DB: {} as any,
    INGEST_BEARER_TOKEN: "ingest-secret-123",
    MCP_BEARER_TOKEN: "mcp-secret-456",
  };

  it("returns 200 OK on /health", async () => {
    const req = new Request("http://localhost/health", { method: "GET" });
    const res = await worker.fetch(req, dummyEnv);
    expect(res.status).toBe(200);
    const body = (await res.json()) as any;
    expect(body.status).toBe("ok");
    expect(body.service).toBe("linkedin-ai-engagement-assistant");
    expect(body.timestamp).toBeDefined();
  });

  it("rejects unauthenticated requests to /internal/ingest with 401", async () => {
    const req = new Request("http://localhost/internal/ingest", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ posts: [] }),
    });
    const res = await worker.fetch(req, dummyEnv);
    expect(res.status).toBe(401);
  });

  it("rejects unauthenticated requests to /mcp with 401", async () => {
    const req = new Request("http://localhost/mcp", { method: "GET" });
    const res = await worker.fetch(req, dummyEnv);
    expect(res.status).toBe(401);
  });

  it("handles authenticated MCP initialize and tools/list requests", async () => {
    // initialize
    const initReq = new Request("http://localhost/mcp", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: "Bearer mcp-secret-456",
      },
      body: JSON.stringify({
        jsonrpc: "2.0",
        id: 1,
        method: "initialize",
        params: {},
      }),
    });
    const initRes = await worker.fetch(initReq, dummyEnv);
    expect(initRes.status).toBe(200);
    const initData = (await initRes.json()) as any;
    expect(initData.result.serverInfo.name).toBe("linkedin-ai-engagement-assistant");

    // tools/list
    const listReq = new Request("http://localhost/mcp", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: "Bearer mcp-secret-456",
      },
      body: JSON.stringify({
        jsonrpc: "2.0",
        id: 2,
        method: "tools/list",
        params: {},
      }),
    });
    const listRes = await worker.fetch(listReq, dummyEnv);
    expect(listRes.status).toBe(200);
    const listData = (await listRes.json()) as any;
    expect(listData.result.tools).toHaveLength(MCP_TOOLS.length);
    const toolNames = listData.result.tools.map((t: any) => t.name);
    expect(toolNames).toContain("get_review_queue");
    expect(toolNames).toContain("get_post_details");
    expect(toolNames).toContain("add_manual_linkedin_post");
    expect(toolNames).toContain("save_comment_drafts");
    expect(toolNames).toContain("update_post_status");
    expect(toolNames).toContain("get_profile_context");
    expect(toolNames).toContain("get_topic_configuration");
  });
});
