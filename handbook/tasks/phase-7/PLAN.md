# Phase 7 · AI assistant on a free model (plan)

The owner asked on 7 Nov 2026 to go ahead with the next work "only if a free model can do it", to design the architecture first so nothing gets stuck midway, and to dry-run it before building. Decision: D-059.

**Answer: yes, with Cloudflare Workers AI's free daily allocation.**
- Empire already has a Cloudflare account, for DNS.
- On the Workers Free plan, the allocation is a hard cap: usage beyond it needs the paid plan. The assistant can therefore never create a bill.
- Cloudflare doesn't train on, keep or share the prompts.

The dry run below shows about 250 to 400 answers a day fit inside the free allocation, with a guard that stops at 80 % of it. After that, visitors are sent to WhatsApp or a call back.

## What the assistant does

A small "Ask about our projects" chat on the public site, off until the owner turns it on with the `chat_widget` flag.

- It answers only from Empire's own published content: projects, configurations, amenities, FAQs and pages. Every answer cites the page it came from.
- It never:
  - promises a price, discount, possession date or return;
  - gives legal, tax or loan advice;
  - asks for a phone number.
- For anything it can't answer, and to book a visit or a call, it shows the site's existing buttons: WhatsApp, Call, and the enquiry form with its consent boxes.
- **It has no tools and takes no actions.** It only writes text. That keeps prompt injection harmless, and keeps the consent rules (D-034) in the form, not in a model.
- **The RERA number, the QR code and prices are never written by the model.** The widget shows them from the database on the cited project's card.

## Architecture

```
Visitor ─► /api/v1/ai/chat (FastAPI, Cloud Run)                       flag chat_widget, else 404
            1. limits: message ≤ 500 chars · 12 messages / 10 min per network · daily neuron guard
            2. redact phone numbers and emails from the message (never sent to the model, never stored)
            3. embed the question ──► Workers AI  @cf/baai/bge-m3 (multilingual, 1024 dims)
            4. top 4 chunks       ──► Postgres pgvector (knowledge_chunk, HNSW cosine), live content only
            5. prompt: rules + numbered sources + last 2 turns (sent by the browser) + question
            6. answer             ──► Workers AI  @cf/qwen/qwen3-30b-a3b-fp8 (OpenAI-compatible), max 300 tokens, 7 s timeout
            7. post-check: every ₹ amount, date and RERA-looking number must appear in a cited source, else that sentence is replaced
            8. reply { answer, citations[{n, url, title}], cards[{project slug}] }   ── or { fallback: "busy" | "no_answer" }
Publish events (outbox) ─► knowledge indexer: re-chunks and re-embeds only the changed item; unpublish deletes its chunks
```

- **The provider sits behind an interface** (`ai/providers/`): `cloudflare` for real use, and `fake` for tests and CI, which is deterministic and needs no network. Another provider (Groq, Gemini, a paid model) is then one new file, with no other change.
- **No chat transcripts are stored.** The database keeps only daily counts: answers, fallbacks, "no answer" and estimated neurons, in `ai_usage_day`. Nothing a visitor typed is stored.
- **Timing:** Netlify's synchronous functions time out at 10 s by default. The 7 s model timeout plus about 0.5 s for embedding and retrieval stays inside it. On a timeout the reply is the "busy" fallback, never an error page.

## Dry run (7 Nov 2026)

**Script:** `scratchpad/ai-spike/spike.py`, not committed. It ran on a local PostgreSQL 16 with pgvector 0.6.0, against the sample content.
- It used a fake 1024-dimensional embedder.
- Workers AI was mocked with the OpenAI-compatible response format.
- Neuron rates are from Cloudflare's pricing page, read on 7 Nov 2026.

| Check | Result |
|---|---|
| Index and search sample content in pgvector (HNSW cosine) | 10 chunks; top-4 search in 1.3 ms |
| Prompt size, real-content estimate (rules + 4 × 350-token chunks + 2 turns + question) | about 2,300 tokens in, 300 out |
| Cost per answer (qwen3-30b: 4,625 in / 30,475 out neurons per million tokens; bge-m3: 1,075) | 20 neurons in English; **32 neurons** in Hinglish (×1.6, pessimistic) |
| Answers per day under the 8,000-neuron guard (80 % of 10,000) | about **250** (Hinglish) to **400** (English). A conversation is 3–4 answers, so 60–100 conversations a day |
| Full re-index of about 150,000 tokens of content (10 projects, pages, FAQs, brochure text) | about 160 neurons, once. Later, only changed items |
| Provider contract: `POST …/accounts/{id}/ai/v1/chat/completions`, `choices[0].message.content`, `usage` | parsed; a 429 or a limit error becomes the "busy" fallback |
| A day of 2,000 questions with the guard on | 251 answered, 1,749 sent to WhatsApp/call back, 7,996 neurons used, never over 10,000 |

**What the dry run found:**
1. **Migration 0001 fails when pgvector is installed but the database user can't create extensions.** The condition checks only that the extension is available. Neon, CI and the Docker image are fine, because their user may create it. A local setup with a non-superuser fails. Task 7.1 makes the check permission-aware and documents the one-line superuser fix in SETUP.
2. **The free allocation is per Cloudflare account.** If anything else on the account uses Workers AI later, it shares the 10,000. The guard counts our own use, and the "busy" fallback covers the rest.
3. **Not yet proven, needs a live run:** answer quality in Hindi and Hinglish, real latency from Mumbai, and Workers AI's exact error body when the allocation runs out. These are covered by the live dry run in task 7.4, before the flag is turned on.

## Tasks

| Task | Track (D-040) | What | Depends on | Status |
|---|---|---|---|---|
| **7.1** Knowledge index and provider | A (Claude) | `knowledge_chunk` and `ai_usage_day` (migration); a permission-aware pgvector check; chunker for live projects, configurations, amenities, FAQs and pages; outbox consumer on publish events; `ai/providers` (`cloudflare`, `fake`); `empire-api ai reindex` | — | **In progress** |
| **7.2** Chat API | A (Claude) | `/api/v1/ai/chat` exactly as in the architecture above: flag, limits, redaction, retrieval, prompt, post-check, fallbacks, counts only | 7.1 | After 7.1 |
| **7.3** Chat widget | B (developer agent) | A lazy-loaded "Ask about our projects" button and panel, built against the contract below with a mock. Citations, project cards from the API, WhatsApp/Call/enquiry buttons, "AI answers can be wrong" note, accessible, no Lighthouse cost (the code loads on click) | contract only | **Ready**, [7.3-chat-widget.md](7.3-chat-widget.md) |
| **7.4** Live dry run and switch-on | Owner + Claude | The owner makes a Workers AI token on the Free plan; Claude runs `empire-api ai smoke` (20 questions in English, Hindi and Hinglish) on the owner's computer or on staging; the legal reviewer approves the chat note; then the flag goes on | 7.1–7.3, go-live | After launch |

## API contract (7.2 builds it; 7.3 uses it with a mock)

`POST /api/v1/ai/chat`. Same-origin only, through the website's proxy like every public call.

Request:
```json
{ "message": "2 BHK ka carpet area?", "history": [{"role": "user", "text": "…"}, {"role": "assistant", "text": "…"}], "page": "/projects/empire-heights" }
```
- `history`: at most the last 2 turns, each at most 1,000 characters.
- `page`: the visitor's current page, used to prefer that project's sources.

Replies:
- `200 { "answer": "…[1]…", "citations": [{"n": 1, "url": "/projects/empire-heights", "title": "Empire Heights"}], "cards": [{"slug": "empire-heights"}] }`
- `200 { "fallback": "no_answer" }`: nothing in Empire's content answers it.
- `200 { "fallback": "busy" }`: the daily guard was reached, the model timed out, or the model returned an error.
- `404` while `chat_widget` is off.
- `422` for a message that is too long or a malformed body.
- `429` when the rate limit is reached. The body has `retry_after_seconds`.

`answer` is plain text. Only `[n]` markers have meaning, and they are links to `citations[n].url`. The widget renders no HTML or Markdown from the model.

## Owner's part (later, task 7.4)

1. **Check the Cloudflare plan:** Workers & Pages → Plans should show **Free**. That is what makes the allocation a hard cap with no bill.
2. **Create the API token** with only "Workers AI: Read" and "Workers AI: Edit" for the account, and put it in Secret Manager as `CLOUDFLARE_AI_TOKEN`, with the account id as `CLOUDFLARE_ACCOUNT_ID`. Never paste it in chat.
3. **Legal:** the legal reviewer approves the privacy-policy line for the chat. Messages go to Cloudflare to be answered and are not stored, and phone numbers and emails are removed first.
4. **Turn it on:** after the live dry run, turn on `chat_widget` in CMS → Settings → Feature flags.
