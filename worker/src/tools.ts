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
        name: "Subhashini Krishna Pranav",
        background:
          "Integrated M.Tech Computer Science and Engineering (Data Science) student at SRM Institute of Science and Technology, Chennai (2023–2028), CGPA 9.27.",
        focus_areas: [
          "RAG architectures & retrieval evaluation",
          "Speech AI & parameter-efficient fine-tuning (LoRA/PEFT)",
          "On-device & privacy-first AI models",
          "LLM application reliability and concurrency",
        ],
        verified_projects: {
          legal_ai: {
            title: "Legal AI (Hybrid RAG & Retrieval Evaluation)",
            architecture: "Hybrid FAISS (flat index, 384-d MiniLM) + BM25 with tuned 0.10 weight; 300-word windows with 50-word overlap carrying clause headings.",
            metrics: "Held-out test set (N=80) with 1,000-resample bootstrap 95% CIs: P@1: 0.900, R@3: 0.963, MRR: 0.938. Key finding: Hybrid matched dense search overall but achieved 0.975 P@1 on exact-token/keyword queries.",
            safety: "Union candidate pooling, centroid distance poisoning checks, post-hoc citation verification pass detecting 15/15 fake IDs.",
          },
          tamil_whisper: {
            title: "Tamil-Whisper (Speech AI & LoRA Fine-Tuning)",
            task: "LoRA fine-tuning of openai/whisper-small (244M params, r=32, alpha=64, 1.44% trainable params) on Google FLEURS Tamil.",
            metrics: "WER reduced from 73.85% to 46.34% (37.25% relative reduction), CER reduced from 25.90% to 13.84%, repetition rate down from 3.05% to 0.51%.",
            lessons: "Grapheme-preserving Unicode NFC normalization for Indic scripts; trained on single 8 GB GPU (RTX 4060) with fp16 and gradient checkpointing.",
          },
          everlore: {
            title: "Everlore (On-Device Foundation Models & Shipped iOS App)",
            stack: "Swift 6, SwiftUI/UIKit, Supabase, Cloudflare R2, Apple Foundation Models. Live on App Store; won Best UI Design at SRM App Fair 2026.",
            trade_offs: "Migrated from cloud Gemini 1.5 Flash to on-device Apple Foundation Models for complete privacy, $0 inference cost, and zero cloud latency.",
          },
          eskay: {
            title: "Eskay (Client-Side Vector Search & Claude Extension)",
            stack: "Manifest V3, IndexedDB, BPE tokenizer (o200k_base).",
            architecture: "Solved CSP blocking 23 MB ONNX models with pure-JS 384-d hashed n-gram vectorizer in under 2 ms. Exact BPE counting with fingerprint cache under 15 ms on 200k tokens.",
          },
          fra_atlas: {
            title: "FRA Atlas (Decision Support & Geo-RAG)",
            stack: "Smart India Hackathon 2025 finalist (team lead). Geo-contextual RAG over 11 policy documents with refusal below 0.30 confidence threshold.",
          },
          internships: [
            "Infosys: Concurrency race condition fix moving validation to server-side Postgres triggers & Edge Functions; Swift ARC retain cycle fixes.",
            "Photon Interactive: .NET Web API with JWT auth connecting to Google Cloud AI Search.",
            "NIT Trichy: Static Android APK risk classification with Apktool, Androguard, and Random Forest.",
          ],
        },
        claim_boundaries: [
          "Do NOT claim production-scale enterprise deployments with millions of users.",
          "Do NOT claim fine-tuning large LLMs (Whisper-small is a 244M speech model).",
          "Do NOT claim implementing RLHF or pre-training models from scratch.",
          "Do NOT claim production cloud LLMOps (Bedrock, SageMaker) - coursework labs only.",
          "Always state when numbers come from synthetic datasets or specific benchmark splits.",
        ],
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
