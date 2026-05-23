# review-me

**Should I buy this?** — Signal is a multi-agent product research tool that finds the signal in all the noise, synthesizing only the four most credible sources — Wirecutter, CNET, Amazon, and Reddit — into a single Buy / Consider / Skip verdict.

---

## The Problem

Product reviews are full of noise — paid placements, outdated roundups, incentivized five-stars. The credible signal exists across Wirecutter, CNET, Amazon, and Reddit, but no one has time to triangulate four sources for every purchase. Signal does it in seconds.

---

## The Solution

Enter a product name. Four agents run in parallel, each extracting a structured verdict from its source. An orchestrator synthesizes them into a single Buy / Consider / Skip recommendation that streams to the UI in real-time and gets a shareable link.

**Stack:** FastAPI + Next.js 15 + Claude (Opus/Sonnet/Haiku) + Firecrawl + SQLite

![Review page streaming results in real-time](docs/screenshot-review.png)
*↑ Add a screenshot of the review page here*

---

## Tradeoffs and Decisions

| Decision | What I considered | What I chose and why |
|---|---|---|
| Amazon verdict logic | Use Claude to interpret star ratings and review counts | Pure Python rules — Amazon data is deterministic; no ambiguity worth an API call |
| Source weighting | Treat all four sources equally in the orchestrator | Wirecutter ≈ CNET > Amazon > Reddit — expert methodology with known rubrics outweighs crowd volume |
| Dropping RTINGS | Build a scraper for their rigorous lab-grade measurement data | Cut it — they block scraping and have no public API; source accessibility matters as much as source quality |

---

## What I Learned

*Coming soon.*

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

```mermaid
flowchart TD
    Q([User Query])

    subgraph agents[Source Agents — run in parallel]
        W[Wirecutter]
        C[CNET]
        A[Amazon]
        R[Reddit]
    end

    Q --> W & C & A & R
    W & C & A & R --> O[Orchestrator]

    O --> B[Buy → Open Amazon]
    O --> Co[Consider → Save to Wishlist]
    O --> S[Skip → New Search]

    style Q fill:#e8eaf6,stroke:#9fa8da,color:#000
    style O fill:#ede7f6,stroke:#b39ddb,color:#000
    style agents fill:#f5f5f5,stroke:#ddd,color:#000
    style B fill:#dcf0dd,stroke:#9ecba1,color:#000
    style Co fill:#fdf4d3,stroke:#e8cb7a,color:#000
    style S fill:#fde8e9,stroke:#f0a8aa,color:#000
```

Results are cached for 72 hours keyed on `(product, source)`. Completed reviews are persisted with a short shareable URL (`/review/{8hex}/{slug}`).
