CREATE TABLE IF NOT EXISTS posts (
  id TEXT PRIMARY KEY,
  canonical_url TEXT NOT NULL UNIQUE,
  post_url TEXT NOT NULL,
  source_name TEXT NOT NULL,
  author_name TEXT,
  title TEXT NOT NULL,
  post_text TEXT NOT NULL,
  published_at TEXT,
  discovered_at TEXT NOT NULL,
  topic_tags TEXT NOT NULL DEFAULT '[]',
  relevance_score INTEGER NOT NULL DEFAULT 0,
  score_breakdown TEXT NOT NULL DEFAULT '{}',
  status TEXT NOT NULL DEFAULT 'NEW',
  is_manual_linkedin INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_posts_status_score
ON posts(status, relevance_score DESC);

CREATE INDEX IF NOT EXISTS idx_posts_discovered
ON posts(discovered_at DESC);

CREATE TABLE IF NOT EXISTS drafts (
  id TEXT PRIMARY KEY,
  post_id TEXT NOT NULL,
  technical_comment TEXT NOT NULL,
  opinion_comment TEXT NOT NULL,
  question_comment TEXT NOT NULL,
  recommended_style TEXT,
  recommended_reason TEXT,
  selected_comment TEXT,
  approved INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  FOREIGN KEY(post_id) REFERENCES posts(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_drafts_post
ON drafts(post_id);

CREATE TABLE IF NOT EXISTS audit_events (
  id TEXT PRIMARY KEY,
  post_id TEXT,
  event_type TEXT NOT NULL,
  event_detail TEXT,
  created_at TEXT NOT NULL
);
