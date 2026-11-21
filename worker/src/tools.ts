/**
 * Remote MCP tools definition and handlers.
 */

import {
  addManualLinkedInPost,
  getPostDetails,
  getReviewQueue,
  saveCommentDrafts,
  updatePostStatus,
} from "./db";
import { isValidStatus } from "./schemas";

export const MCP_TOOLS = [
  {
    name: "get_review_queue",
    description:
      "Retrieve high-relevance discovered posts waiting for review, sorted by score and recency.",
    inputSchema: {
      type: "object",
      properties: {
        limit: {
          type: "number",
          description: "Max number of items to return (1-20, default: 10)",
        },
        minimum_score: {
          type: "number",
          description: "Minimum relevance score filter (default: 55)",
        },
        topic: {
          type: "string",
          description: "Optional topic filter (e.g. 'RAG', 'Agentic AI')",
        },
      },
    },
  },
  {
    name: "get_post_details",
    description: "Get full details and existing comment drafts for a specific post by ID.",
    inputSchema: {
      type: "object",
      properties: {
        post_id: {
          type: "string",
          description: "The unique 16-character post ID",
        },
      },
      required: ["post_id"],
    },
  },
  {
    name: "add_manual_linkedin_post",
    description:
      "Add a LinkedIn post supplied manually by the user. Does NOT scrape or fetch LinkedIn URLs.",
    inputSchema: {
      type: "object",
      properties: {
        post_url: {
          type: "string",
          description: "Valid LinkedIn post URL (e.g. https://www.linkedin.com/posts/...)",
        },
        post_text: {
          type: "string",
          description: "The copied text body of the LinkedIn post",
        },
        author_name: {
          type: "string",
          description: "Author name if known",
        },
        posted_at: {
          type: "string",
          description: "ISO publication date if known",
        },
        topic_hint: {
          type: "string",
          description: "Topic category hint (e.g. 'RAG', 'LLMs')",
        },
      },
      required: ["post_url", "post_text"],
    },
  },
  {
    name: "save_comment_drafts",
    description:
      "Save three distinct comment drafts for a post and move status to DRAFTED. Does not approve or post.",
    inputSchema: {
      type: "object",
      properties: {
        post_id: {
          type: "string",
          description: "The target post ID",
        },
        technical_comment: {
          type: "string",
          description: "Technical insight comment draft (2-5 sentences)",
        },
        opinion_comment: {
          type: "string",
          description: "Constructive opinion comment draft (2-5 sentences)",
        },
        question_comment: {
          type: "string",
          description: "Thought-provoking question comment draft (2-5 sentences)",
        },
        recommended_style: {
          type: "string",
          description: "Which draft is recommended ('technical', 'opinion', or 'question')",
        },
        recommended_reason: {
          type: "string",
          description: "Explanation for why this style was recommended",
        },
      },
      required: [
        "post_id",
        "technical_comment",
        "opinion_comment",
        "question_comment",
      ],
    },
  },
  {
    name: "update_post_status",
    description:
      "Update a post's status (NEW, REVIEWED, DRAFTED, APPROVED, POSTED, SKIPPED). Never publishes to LinkedIn.",
    inputSchema: {
      type: "object",
      properties: {
        post_id: {
          type: "string",
          description: "The unique post ID",
        },
        status: {
          type: "string",
          enum: ["NEW", "REVIEWED", "DRAFTED", "APPROVED", "POSTED", "SKIPPED"],
          description: "The new review status",
        },
      },
      required: ["post_id", "status"],
    },
  },
  {
    name: "get_profile_context",
    description:
      "Retrieve the student's verified experience, background, and boundaries to ground comments.",
    inputSchema: {
      type: "object",
      properties: {},
    },
  },
  {
    name: "get_topic_configuration",
    description: "Get the active topics, priority weighting, and scoring definitions.",
    inputSchema: {
      type: "object",
      properties: {},
    },
  },
];

export async function handleToolCall(
  name: string,
  args: any,
  db: D1Database
): Promise<any> {
  switch (name) {
    case "get_review_queue": {
      const posts = await getReviewQueue(db, {
        limit: args.limit,
        minScore: args.minimum_score,
        topic: args.topic,
      });
      return {
        count: posts.length,
        posts: posts.map((p) => ({
          id: p.id,
          title: p.title,
          source: p.source_name,
          author: p.author_name,
          score: p.relevance_score,
          topics: JSON.parse(p.topic_tags || "[]"),
          status: p.status,
          published_at: p.published_at,
          canonical_url: p.canonical_url,
          text_snippet: p.post_text.slice(0, 300) + (p.post_text.length > 300 ? "..." : ""),
        })),
      };
    }

    case "get_post_details": {
      if (!args.post_id) throw new Error("post_id is required");
      const details = await getPostDetails(db, args.post_id);
      if (!details.post) throw new Error(`Post not found with ID: ${args.post_id}`);
      return details;
    }

    case "add_manual_linkedin_post": {
      return await addManualLinkedInPost(db, {
        post_url: args.post_url,
        post_text: args.post_text,
        author_name: args.author_name,
        posted_at: args.posted_at,
        topic_hint: args.topic_hint,
      });
    }

    case "save_comment_drafts": {
      return await saveCommentDrafts(db, {
        post_id: args.post_id,
        technical_comment: args.technical_comment,
        opinion_comment: args.opinion_comment,
        question_comment: args.question_comment,
        recommended_style: args.recommended_style,
        recommended_reason: args.recommended_reason,
      });
    }

    case "update_post_status": {
      if (!isValidStatus(args.status)) {
        throw new Error(`Invalid status: ${args.status}`);
      }
      const updated = await updatePostStatus(db, args.post_id, args.status);
      return { success: updated, post_id: args.post_id, status: args.status };
    }

    case "get_profile_context": {
      return {
        background: "Integrated M.Tech Computer Science student specialising in Data Science.",
        verified_projects: [
          "Building RAG applications with FAISS and BM25 hybrid search.",
          "Evaluating retrieval pipelines with Precision@K and Recall@K.",
          "Legal document AI workflow (OCR fallback, parser, citation tracing).",
          "Exploring local LLM memory, retrieval, and compression.",
          "On-device Apple Foundation Models.",
          "Software engineering collaboration.",
        ],
        boundaries: "Do NOT claim senior production scale or invented metrics.",
      };
    }

    case "get_topic_configuration": {
      return {
        topics: [
          "RAG (priority 10)",
          "AI Engineering (priority 10)",
          "LLM Evaluation (priority 10)",
          "LLMs (priority 9)",
          "Agentic AI (priority 9)",
          "AI Startups (priority 8)",
          "Fine-tuning and Transformers (priority 8)",
          "Multimodal AI (priority 7)",
        ],
      };
    }

    default:
      throw new Error(`Unknown MCP tool: ${name}`);
  }
}
