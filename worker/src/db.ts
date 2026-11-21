/**
 * D1 database query interface and operations.
 */

import {
  Draft,
  ManualLinkedInPostInput,
  Post,
  PostStatus,
  SaveDraftsInput,
  isValidLinkedInUrl,
  isValidStatus,
} from "./schemas";

export async function recordAuditEvent(
  db: D1Database,
  postId: string | null,
  eventType: string,
  detail: string | null = null
): Promise<void> {
  const id = crypto.randomUUID();
  const now = new Date().toISOString();
  await db
    .prepare(
      "INSERT INTO audit_events (id, post_id, event_type, event_detail, created_at) VALUES (?, ?, ?, ?, ?)"
    )
    .bind(id, postId, eventType, detail, now)
    .run();
}

export async function ingestPosts(
  db: D1Database,
  posts: Array<any>
): Promise<{ received: number; inserted: number }> {
  let inserted = 0;
  const now = new Date().toISOString();

  for (const p of posts) {
    if (!p.id || !p.canonical_url || !p.post_url || !p.title || !p.post_text) {
      continue;
    }

    const res = await db
      .prepare(
        `INSERT OR IGNORE INTO posts (
          id, canonical_url, post_url, source_name, author_name,
          title, post_text, published_at, discovered_at, topic_tags,
          relevance_score, score_breakdown, status, is_manual_linkedin,
          created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`
      )
      .bind(
        p.id,
        p.canonical_url,
        p.post_url,
        p.source_name || "Unknown",
        p.author_name || null,
        p.title,
        p.post_text,
        p.published_at || null,
        p.discovered_at || now,
        typeof p.topic_tags === "string" ? p.topic_tags : JSON.stringify(p.topic_tags || []),
        p.relevance_score ?? 0,
        typeof p.score_breakdown === "string"
          ? p.score_breakdown
          : JSON.stringify(p.score_breakdown || {}),
        p.status || "NEW",
        p.is_manual_linkedin ?? 0,
        p.created_at || now,
        p.updated_at || now
      )
      .run();

    if (res.meta?.changes && res.meta.changes > 0) {
      inserted++;
    }
  }

  await recordAuditEvent(
    db,
    null,
    "FEED_INGESTION",
    `Ingested ${inserted} new items out of ${posts.length} received`
  );

  return { received: posts.length, inserted };
}

export async function getReviewQueue(
  db: D1Database,
  opts: { limit?: number; minScore?: number; topic?: string }
): Promise<Post[]> {
  const limit = Math.max(1, Math.min(20, opts.limit ?? 10));
  const minScore = opts.minScore ?? 55;

  let query = `
    SELECT * FROM posts
    WHERE status IN ('NEW', 'REVIEWED', 'DRAFTED')
      AND relevance_score >= ?
  `;
  const binds: any[] = [minScore];

  if (opts.topic && opts.topic.trim()) {
    query += " AND topic_tags LIKE ?";
    binds.push(`%${opts.topic.trim()}%`);
  }

  query += " ORDER BY relevance_score DESC, published_at DESC LIMIT ?";
  binds.push(limit);

  const { results } = await db.prepare(query).bind(...binds).all<Post>();
  return results || [];
}

export async function getPostDetails(
  db: D1Database,
  postId: string
): Promise<{ post: Post | null; drafts: Draft[] }> {
  const post = await db
    .prepare("SELECT * FROM posts WHERE id = ?")
    .bind(postId)
    .first<Post>();

  if (!post) {
    return { post: null, drafts: [] };
  }

  const { results: drafts } = await db
    .prepare("SELECT * FROM drafts WHERE post_id = ? ORDER BY created_at DESC")
    .bind(postId)
    .all<Draft>();

  return { post, drafts: drafts || [] };
}

export async function addManualLinkedInPost(
  db: D1Database,
  input: ManualLinkedInPostInput
): Promise<{ post: Post; score: number }> {
  if (!isValidLinkedInUrl(input.post_url)) {
    throw new Error("Invalid LinkedIn URL. Must be an https://...linkedin.com URL.");
  }

  const text = (input.post_text || "").trim();
  if (!text) {
    throw new Error("Post text cannot be empty.");
  }

  const maxLen = 12000;
  const truncatedText = text.length > maxLen ? text.slice(0, maxLen) : text;

  // Generate deterministic ID
  const enc = new TextEncoder();
  const hash = await crypto.subtle.digest("SHA-256", enc.encode(input.post_url.trim()));
  const hex = Array.from(new Uint8Array(hash))
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("")
    .slice(0, 16);

  const now = new Date().toISOString();
  const baseScore = 75; // Manually submitted posts are pre-filtered by the user

  const topicTags = input.topic_hint ? [input.topic_hint] : ["Manual LinkedIn"];
  const scoreBreakdown = {
    total: baseScore,
    category: "High priority",
    reason: "Submitted directly by user for review",
  };

  const title = truncatedText.split("\n")[0].slice(0, 120) || "Manual LinkedIn Post";

  await db
    .prepare(
      `INSERT OR REPLACE INTO posts (
        id, canonical_url, post_url, source_name, author_name,
        title, post_text, published_at, discovered_at, topic_tags,
        relevance_score, score_breakdown, status, is_manual_linkedin,
        created_at, updated_at
      ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`
    )
    .bind(
      hex,
      input.post_url.trim(),
      input.post_url.trim(),
      "Manual LinkedIn",
      input.author_name || null,
      title,
      truncatedText,
      input.posted_at || now,
      now,
      JSON.stringify(topicTags),
      baseScore,
      JSON.stringify(scoreBreakdown),
      "NEW",
      1,
      now,
      now
    )
    .run();

  await recordAuditEvent(db, hex, "MANUAL_POST_ADDED", `URL: ${input.post_url}`);

  const post = await db
    .prepare("SELECT * FROM posts WHERE id = ?")
    .bind(hex)
    .first<Post>();

  return { post: post!, score: baseScore };
}

export async function saveCommentDrafts(
  db: D1Database,
  input: SaveDraftsInput
): Promise<Draft> {
  const post = await db
    .prepare("SELECT id FROM posts WHERE id = ?")
    .bind(input.post_id)
    .first();

  if (!post) {
    throw new Error(`Post with ID ${input.post_id} not found.`);
  }

  const maxCommentLen = 2000;
  const tech = (input.technical_comment || "").slice(0, maxCommentLen);
  const opinion = (input.opinion_comment || "").slice(0, maxCommentLen);
  const question = (input.question_comment || "").slice(0, maxCommentLen);

  const draftId = crypto.randomUUID();
  const now = new Date().toISOString();

  await db
    .prepare(
      `INSERT INTO drafts (
        id, post_id, technical_comment, opinion_comment, question_comment,
        recommended_style, recommended_reason, approved, created_at, updated_at
      ) VALUES (?, ?, ?, ?, ?, ?, ?, 0, ?, ?)`
    )
    .bind(
      draftId,
      input.post_id,
      tech,
      opinion,
      question,
      input.recommended_style || null,
      input.recommended_reason || null,
      now,
      now
    )
    .run();

  // Update post status to DRAFTED
  await db
    .prepare("UPDATE posts SET status = 'DRAFTED', updated_at = ? WHERE id = ?")
    .bind(now, input.post_id)
    .run();

  await recordAuditEvent(db, input.post_id, "DRAFTS_SAVED", `Draft ID: ${draftId}`);

  const draft = await db
    .prepare("SELECT * FROM drafts WHERE id = ?")
    .bind(draftId)
    .first<Draft>();

  return draft!;
}

export async function updatePostStatus(
  db: D1Database,
  postId: string,
  newStatus: PostStatus
): Promise<boolean> {
  if (!isValidStatus(newStatus)) {
    throw new Error(`Invalid status: ${newStatus}`);
  }

  const now = new Date().toISOString();
  const res = await db
    .prepare("UPDATE posts SET status = ?, updated_at = ? WHERE id = ?")
    .bind(newStatus, now, postId)
    .run();

  if (res.meta?.changes && res.meta.changes > 0) {
    await recordAuditEvent(db, postId, "STATUS_UPDATED", `New status: ${newStatus}`);
    return true;
  }
  return false;
}
