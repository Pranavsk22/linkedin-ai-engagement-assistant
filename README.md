# LinkedIn AI Engagement Assistant

A zero-cost, cloud-hosted research and drafting assistant. Discovers high-signal AI engineering discussions twice weekly and prepares thoughtful, grounded LinkedIn comments for human review.

## Hard Constraints
- **$0 Recurring Cost:** Built entirely on free tiers (GitHub Actions public runners, Cloudflare Workers Free, Cloudflare D1 Free, Claude Free via Remote MCP).
- **Safety & Policy First:** Zero automated LinkedIn interaction. No scraping, no session hijack, no automatic comments, likes, or follows. All comments are drafted for human review and manual posting.
- **Untrusted Input Defense:** All RSS items and post texts are treated as untrusted data.
- **No LLM API Bills:** Claude Free is used interactively via MCP tool calls, never as a paid API.

---

## Architecture Overview

```text
               GITHUB ACTIONS (Cron: Tue/Fri 03:30 UTC)
                                |
             Python RSS Discovery, Deduplication & Scoring
                                |
                                v
                CLOUDFLARE WORKER & D1 DATABASE
                     /                    \
              /internal/ingest           /mcp (Remote MCP)
                                          |
                                          v
                                     Claude Free
                                          |
                               Three Draft Comments
                                          |
                               Manual User Review
```

---

## Milestone Progress

- [x] **Milestone 0: Repository & Architecture Planning**
  - Project directory layout and task checklist
  - Environment configuration (`config/topics.json`, `config/feeds.json`)
  - Claude persona & engagement guidelines
  - Database schema (`worker/migrations/0001_init.sql`)
  - GitHub Actions definitions (`.github/workflows/`)
- [x] **Milestone 1: Discovery Engine**
  - Canonicalisation with tracking parameter removal
  - HTML stripping and safe text normalisation
  - Deterministic 0-100 relevance scoring rubric
  - RSS parser with timeout and failure resilience
  - Local JSON/CSV export runner and unit test suite
- [x] **Milestone 2: Cloudflare Worker & D1 Backend**
- [x] **Milestone 3: Remote MCP Tools Implementation**
- [x] **Milestone 4: Cloud Deployment & Claude Connection**
- [x] **Milestone 5: GitHub Actions Cloud Automation**
- [ ] **Milestone 6: Prompt Tuning & Evaluation**

---

## Local Development & Testing

### Python Setup
```bash
pip install -r requirements.txt
```

### Run Discovery Engine Locally
```bash
python -m discovery.upload --output-json output.json --output-csv output.csv
```

### Run Unit Tests
```bash
pytest tests/ -v
```
