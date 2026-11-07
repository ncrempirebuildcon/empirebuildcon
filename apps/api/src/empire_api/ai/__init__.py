"""The AI assistant (Phase 7, D-059; handbook/tasks/phase-7/PLAN.md).

- providers/: the model behind an interface (`cloudflare` for Workers AI's free allocation,
  `fake` for tests and CI). Off unless AI_PROVIDER is set.
- knowledge.py: turns live public content into text chunks (only what the public API shows,
  minus prices and RERA numbers, which the assistant never writes).
- store.py: the pgvector table (`knowledge_chunk`) and daily counts (`ai_usage_day`).
- indexer.py: re-indexes one item on its publish events, or everything (`empire-api ai reindex`).

COMPLIANCE: nothing a visitor types is stored; the usage table holds counts only.
"""
