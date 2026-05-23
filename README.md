# review-me

**Should I buy this?** — Signal is a multi-agent product research tool that finds the signal in all the noise, synthesizing only the four most credible sources — Wirecutter, CNET, Amazon, and Reddit — into a single Buy / Consider / Skip verdict.

---

## The Problem

Product reviews are drowning in noise. SEO-optimized "best of" lists that haven't been updated since 2021. Amazon review sections flooded with incentivized five-stars and unverifiable complaints. YouTube unboxings that never mention long-term reliability. Sponsored content dressed up as editorial.

The signal exists — Wirecutter does rigorous hands-on testing, CNET applies a structured scoring rubric, Amazon surfaces aggregate owner experience at scale, Reddit captures what power users discover after months of real use. But those four sources are scattered, speak different languages (semantic tiers vs. decimal scores vs. star ratings vs. raw sentiment), and no one has time to triangulate all of them for every purchase.

That's what Signal is for. Buyers making mid-to-high consideration purchases — electronics, appliances, gear — shouldn't need 45 minutes of browser tabs to get a defensible answer. They don't need more reviews. They need less noise.

---

## The Solution

review-me runs four specialized agents in parallel — one per source — and feeds their verdicts to an orchestrator that synthesizes a final recommendation.

**How it works:**

1. Enter a product name. If the query is ambiguous ("headphones"), the app surfaces 2–3 candidates to clarify intent.
2. Four agents execute concurrently: Wirecutter, CNET, Amazon, and Reddit.
3. Results stream to the UI in real-time as each agent completes — no waiting for the slowest one before seeing anything.
4. An orchestrator (running on Opus) reads all four verdicts and writes a synthesis: final verdict, confidence, notable disagreements between sources, and a recommended action.
5. The review is persisted and gets a shareable short URL.

Each source agent has its own extraction schema and verdict mapping logic tuned to that source's conventions — Wirecutter uses semantic tiers ("Our Pick", "Also Great"), CNET uses a 0–10 decimal scale, Amazon uses star rating + review volume + badge signals, and Reddit uses weighted sentiment analysis where higher-scored posts carry more weight.

**Stack:** FastAPI + Next.js 15 + Claude (Opus/Sonnet/Haiku) + Firecrawl + SQLite

![Review page streaming results in real-time](docs/screenshot-review.png)
*↑ Add a screenshot of the review page here*

---

## Tradeoffs and Decisions

### Replacing the Amazon Claude call with pure Python rules

Early on, the Amazon agent used Claude to interpret star ratings and review counts and produce a verdict. I replaced it with a pure Python function:

```python
if star_rating >= 4.5 and review_count >= 500:
    verdict, confidence = "Buy", "high"
elif star_rating >= 4.0 and review_count >= 100:
    verdict, confidence = "Consider", "medium"
...
```

The tradeoff: this is less flexible — it can't reason about edge cases the way a model can — but the Amazon verdict is the most deterministic of the four sources. A 4.7-star product with 3,000 reviews is a Buy. There's no ambiguity worth paying an API call to resolve. Keeping model calls for tasks that actually need reasoning (Reddit sentiment, cross-source synthesis) and eliminating them where a lookup table suffices cuts cost and latency without sacrificing quality.

### Source weighting in the orchestrator

The orchestrator doesn't treat all four sources equally. The weighting is: Wirecutter ≈ CNET > Amazon > Reddit.

The intuition: Wirecutter and CNET represent structured expert review with known methodology. Amazon tells you what the median buyer thinks after owning it for two weeks. Reddit tells you what power users think after six months — valuable, but noisy and biased toward vocal enthusiasts and people who had problems.

I considered weighting Reddit higher because it surfaces long-term reliability signals that expert reviews miss (firmware issues, build quality degradation over time). I kept it lowest because Reddit community coverage is inconsistent — some products have rich threads, others have almost nothing. The orchestrator prompt flags notable disagreements between sources rather than burying them in a consensus, which surfaces those cases where Reddit's long-term signal contradicts the initial expert verdict.

### Cutting RTINGS as a source

RTINGS was in the original design. For display and audio hardware especially, their measurement-based methodology is the most rigorous available — they test TVs, headphones, and monitors against objective lab benchmarks rather than subjective impressions. They would have been the strongest signal in the stack.

I cut them because the data wasn't accessible. Their site blocks scraping effectively, and they have no public API. Every approach I tried — Firecrawl, direct HTTP — returned either a wall or incomplete fragments that couldn't be reliably parsed into a structured verdict. Investing further in reverse-engineering their anti-scraping would have been fragile: any site update could silently break the agent with no warning.

The lesson: source quality and source accessibility are independent variables, and you need both. RTINGS is high quality and low accessibility. Reddit is medium quality and high accessibility (public JSON API, no auth). The final four sources are the intersection of credible and reliably reachable — which is itself a product decision worth being explicit about.

---

## What I Learned

**Confidence is a data quality signal, not a certainty signal.** I initially modeled confidence as "how sure is the agent about its verdict." That turned out to be the wrong frame. An agent can be very confident it found the wrong product. The right question is: did the source have enough signal to render a verdict at all? A Wirecutter agent that finds a well-written review is high confidence. One that finds a three-sentence blurb in a roundup is low confidence. Reframing confidence as data coverage — not verdict certainty — made the orchestrator's synthesis logic much cleaner: skip or flag low-confidence sources rather than averaging them in.

**Reddit bypasses conventional scraping entirely.** Firecrawl can't scrape Reddit reliably — Reddit blocks it. The Reddit agent uses the public Reddit JSON API directly (`/r/.../.json`), with appropriate user-agent headers. This actually returns cleaner data than scraping would (structured JSON, post scores included), but it means the agent is on a fundamentally different technical path than the other three. Worth knowing before assuming your scraping infrastructure is universal.

**Streaming the UI as agents complete changes the perceived speed more than actual latency does.** With four parallel agents, the wall-clock time is dominated by the slowest one. But users experience the app as fast because Wirecutter typically completes in 3–4 seconds and its card appears immediately — before Reddit finishes. The progress state is real (not fake), which matters. A fake progress bar that hides 8 seconds of loading feels slower than 8 real seconds of watching real data arrive.

---

## Setup

### Prerequisites

- Python 3.11+
- Node.js 18+
- Anthropic API key
- Firecrawl API key

### Backend

```bash
cd backend
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # fill in API keys
uvicorn main:app --reload
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

The frontend runs on `http://localhost:3000`, the backend on `http://localhost:8000`.

---

## Architecture

```
User query
    │
    ▼
FastAPI /review (SSE stream)
    │
    ├── Wirecutter agent (Sonnet + Firecrawl)
    ├── CNET agent       (Sonnet + Firecrawl)
    ├── Amazon agent     (Python rules + Firecrawl)
    └── Reddit agent     (Sonnet + Reddit JSON API)
    │
    ▼
Orchestrator (Opus) — synthesizes verdicts
    │
    ▼
Final verdict streamed to UI + persisted to SQLite
    │
    └── Eval judges (Haiku) — faithfulness / correctness / relevance [async, non-blocking]
```

Results are cached for 72 hours keyed on `(product, source)`. Completed reviews are persisted with a short shareable URL (`/review/{8hex}/{slug}`).
