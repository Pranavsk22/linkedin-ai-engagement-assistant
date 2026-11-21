/**
 * Data structures and validation rules for the LinkedIn AI Engagement Worker.
 */

export type PostStatus = "NEW" | "REVIEWED" | "DRAFTED" | "APPROVED" | "POSTED" | "SKIPPED";

export const ALLOWED_STATUSES: Set<PostStatus> = new Set([
  "NEW",
  "REVIEWED",
  "DRAFTED",
  "APPROVED",
  "POSTED",
  "SKIPPED",
]);

export interface Post {
  id: string;
  canonical_url: string;
  post_url: string;
  source_name: string;
  author_name: string | null;
  title: string;
  post_text: string;
  published_at: string | null;
  discovered_at: string;
  topic_tags: string; // JSON array string
  relevance_score: number;
  score_breakdown: string; // JSON object string
  status: PostStatus;
  is_manual_linkedin: number; // 0 or 1
  created_at: string;
  updated_at: string;
}

export interface Draft {
  id: string;
  post_id: string;
  technical_comment: string;
  opinion_comment: string;
  question_comment: string;
  recommended_style: string | null;
  recommended_reason: string | null;
  selected_comment: string | null;
  approved: number; // 0 or 1
  created_at: string;
  updated_at: string;
}

export interface AuditEvent {
  id: string;
  post_id: string | null;
  event_type: string;
  event_detail: string | null;
  created_at: string;
}

export interface IngestPayload {
  posts: Array<Omit<Post, "status" | "is_manual_linkedin" | "created_at" | "updated_at"> & {
    status?: PostStatus;
    is_manual_linkedin?: number;
    created_at?: string;
    updated_at?: string;
  }>;
}

export interface ManualLinkedInPostInput {
  post_url: string;
  post_text: string;
  author_name?: string;
  posted_at?: string;
  topic_hint?: string;
}

export interface SaveDraftsInput {
  post_id: string;
  technical_comment: string;
  opinion_comment: string;
  question_comment: string;
  recommended_style?: string;
  recommended_reason?: string;
}

export interface UpdateStatusInput {
  post_id: string;
  status: PostStatus;
}

export function isValidStatus(status: unknown): status is PostStatus {
  return typeof status === "string" && ALLOWED_STATUSES.has(status as PostStatus);
}

export function isValidLinkedInUrl(url: string): boolean {
  if (!url || typeof url !== "string") return false;
  try {
    const parsed = new URL(url.trim());
    const host = parsed.hostname.toLowerCase();
    return (
      (host === "linkedin.com" || host.endsWith(".linkedin.com")) &&
      (parsed.protocol === "https:" || parsed.protocol === "http:")
    );
  } catch {
    return false;
  }
}
