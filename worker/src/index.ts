/**
 * Cloudflare Worker HTTP router and Remote MCP server entrypoint.
 */

import { verifyBearerToken } from "./auth";
import { ingestPosts } from "./db";
import { MCP_TOOLS, handleToolCall } from "./tools";

export interface Env {
  DB: D1Database;
  MCP_BEARER_TOKEN?: string;
  INGEST_BEARER_TOKEN?: string;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);

    // 1. Public Health Check
    if (url.pathname === "/health" && request.method === "GET") {
      return new Response(
        JSON.stringify({
          status: "ok",
          service: "linkedin-ai-engagement-assistant",
          timestamp: new Date().toISOString(),
        }),
        {
          headers: { "Content-Type": "application/json" },
        }
      );
    }

    // 2. Ingestion Endpoint (GitHub Actions -> Worker)
    if (url.pathname === "/internal/ingest" && request.method === "POST") {
      const authHeader = request.headers.get("Authorization");
      const isAuthed = await verifyBearerToken(authHeader, env.INGEST_BEARER_TOKEN);

      if (!isAuthed) {
        return new Response(JSON.stringify({ error: "Unauthorized" }), {
          status: 401,
          headers: { "Content-Type": "application/json" },
        });
      }

      try {
        const body = (await request.json()) as any;
        const posts = Array.isArray(body?.posts) ? body.posts : [];
        const result = await ingestPosts(env.DB, posts);

        return new Response(JSON.stringify({ success: true, ...result }), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      } catch (err: any) {
        return new Response(
          JSON.stringify({ error: "Ingestion failed", message: err.message }),
          { status: 400, headers: { "Content-Type": "application/json" } }
        );
      }
    }

    // 3. Remote MCP Endpoint (/mcp) for Claude Free
    if (url.pathname === "/mcp") {
      const authHeader = request.headers.get("Authorization");
      const isAuthed = await verifyBearerToken(authHeader, env.MCP_BEARER_TOKEN);

      if (!isAuthed) {
        return new Response(JSON.stringify({ error: "Unauthorized MCP access" }), {
          status: 401,
          headers: { "Content-Type": "application/json" },
        });
      }

      if (request.method === "GET") {
        // SSE / capability declaration or info
        return new Response(
          JSON.stringify({
            name: "linkedin-ai-engagement-assistant",
            version: "1.0.0",
            protocol: "mcp-streamable-http",
            tools: MCP_TOOLS.map((t) => t.name),
          }),
          { headers: { "Content-Type": "application/json" } }
        );
      }

      if (request.method === "POST") {
        try {
          const rpc = (await request.json()) as any;
          const { method, params, id } = rpc;

          if (method === "initialize") {
            return new Response(
              JSON.stringify({
                jsonrpc: "2.0",
                id,
                result: {
                  protocolVersion: "2024-11-05",
                  capabilities: { tools: {} },
                  serverInfo: {
                    name: "linkedin-ai-engagement-assistant",
                    version: "1.0.0",
                  },
                },
              }),
              { headers: { "Content-Type": "application/json" } }
            );
          }

          if (method === "tools/list") {
            return new Response(
              JSON.stringify({
                jsonrpc: "2.0",
                id,
                result: { tools: MCP_TOOLS },
              }),
              { headers: { "Content-Type": "application/json" } }
            );
          }

          if (method === "tools/call") {
            const toolName = params?.name;
            const toolArgs = params?.arguments || {};
            const callResult = await handleToolCall(toolName, toolArgs, env.DB);

            return new Response(
              JSON.stringify({
                jsonrpc: "2.0",
                id,
                result: {
                  content: [
                    {
                      type: "text",
                      text: JSON.stringify(callResult, null, 2),
                    },
                  ],
                },
              }),
              { headers: { "Content-Type": "application/json" } }
            );
          }

          return new Response(
            JSON.stringify({
              jsonrpc: "2.0",
              id,
              error: { code: -32601, message: `Method not found: ${method}` },
            }),
            { headers: { "Content-Type": "application/json" } }
          );
        } catch (err: any) {
          return new Response(
            JSON.stringify({
              jsonrpc: "2.0",
              error: { code: -32000, message: err.message },
            }),
            { status: 500, headers: { "Content-Type": "application/json" } }
          );
        }
      }

      return new Response("Method not allowed", { status: 405 });
    }

    return new Response("Not Found", { status: 404 });
  },
};
