"""
LLM-as-a-judge evaluations for each source agent result.

Three judges fire for every source:
  - faithfulness  : is the verdict grounded in source_data?
  - correctness   : was the mapping rule applied correctly?
  - relevance     : did the source return data about the right product?

Results are stored in the `evals` SQLite table.
"""

import asyncio
import json
import logging
from pathlib import Path

import anthropic
import aiosqlite

import db.database as dbmod

logger = logging.getLogger(__name__)

# ── Prompt templates ──────────────────────────────────────────────────────────
# Kept in sync with ~/.claude/agents/{judge}.md

FAITHFULNESS_PROMPT = """You are a faithfulness evaluator for the signal product review app.

Determine whether the source agent's verdict and extracted data are faithful to (grounded in) the source_data — nothing fabricated or contradicting the raw facts.

FAITHFUL when: verdict is logically consistent with source_data fields; confidence reflects data quality.
UNFAITHFUL when: verdict contradicts source_data; confidence is overstated; product_found=false but treated as found.

Source grounding rules:
- Wirecutter: verdict_tier is ground truth. "Our Pick" must map to Buy.
- CNET: overall_score is ground truth. Score 9.0 claiming Consider is unfaithful.
- Amazon: star_rating + review_count are ground truth.
- Reddit: product_found + sentiment_summary are ground truth.

Respond with ONLY a JSON object: {"label": "faithful"|"unfaithful", "score": 1.0|0.0, "explanation": "..."}"""

CORRECTNESS_PROMPT = """You are a correctness evaluator for the signal product review app.

Determine whether the source agent correctly applied source-specific mapping rules to derive its verdict.

Mapping rules:
Wirecutter: Our Pick/Also Great → Buy high | Upgrade/Budget Pick → Consider medium | No Longer Recommended → Skip high | Not Listed → Consider low
CNET: 8.0+ → Buy high | 7.0-7.9 → Consider high | 5.0-6.9 → Consider low | <5.0 → Skip high | null → Consider low
Amazon: ≥4.5 + ≥500 reviews → Buy high | ≥4.0 + ≥100 → Consider medium | ≥4.0 + <100 → Consider low | <4.0 → Skip medium | null → Consider low
Reddit: no rigid rule — verdict should match sentiment (positive→Buy, mixed→Consider, complaints→Skip)

CORRECT: verdict matches expected mapping for the given data values.
INCORRECT: verdict clearly deviates from the mapping (e.g., CNET 9.2 → Consider, Amazon 2.8 → Buy).

Respond with ONLY a JSON object: {"label": "correct"|"incorrect", "score": 1.0|0.0, "explanation": "..."}"""

RELEVANCE_PROMPT = """You are a document relevance evaluator for the signal product review app.

Determine whether the data retrieved from a review source is actually about the product the user searched for.

RELEVANT: product_found=true AND data fields contain substantive info about the specific product.
UNRELATED: product_found=false, OR all fields are null/empty, OR data refers to a different product or generic category.

Source signals:
- Wirecutter: relevant if verdict_tier is a known tier AND product_found=true
- CNET: relevant if overall_score is non-null AND product_found=true
- Amazon: relevant if star_rating + review_count are non-null AND product_found=true
- Reddit: relevant if product_found=true AND sentiment_summary is non-empty and references the product

Respond with ONLY a JSON object: {"label": "relevant"|"unrelated", "score": 1.0|0.0, "explanation": "..."}"""

JUDGES = {
    "faithfulness": FAITHFULNESS_PROMPT,
    "correctness":  CORRECTNESS_PROMPT,
    "relevance":    RELEVANCE_PROMPT,
}


# ── DB helpers ────────────────────────────────────────────────────────────────

async def _ensure_evals_table():
    async with aiosqlite.connect(dbmod.DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS evals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                review_id TEXT NOT NULL,
                product TEXT NOT NULL,
                source TEXT NOT NULL,
                judge TEXT NOT NULL,
                label TEXT NOT NULL,
                score REAL NOT NULL,
                explanation TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.commit()


async def _store_eval(review_id: str, product: str, source: str,
                      judge: str, label: str, score: float, explanation: str):
    async with aiosqlite.connect(dbmod.DB_PATH) as db:
        await db.execute(
            "INSERT INTO evals (review_id, product, source, judge, label, score, explanation) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (review_id, product, source, judge, label, score, explanation),
        )
        await db.commit()


# ── Single judge call ─────────────────────────────────────────────────────────

async def _run_judge(
    judge_name: str,
    system_prompt: str,
    payload: dict,
    claude: anthropic.AsyncAnthropic,
) -> dict:
    message = await claude.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=256,
        system=[
            {
                "type": "text",
                "text": system_prompt,
                "cache_control": {"type": "ephemeral"},
            }
        ],
        messages=[
            {
                "role": "user",
                "content": json.dumps(payload),
            }
        ],
    )
    try:
        return json.loads(message.content[0].text)
    except (json.JSONDecodeError, IndexError, KeyError):
        return {"label": "unknown", "score": 0.0, "explanation": "Eval parse error."}


# ── Public API ────────────────────────────────────────────────────────────────

async def run_evals(
    review_id: str,
    product: str,
    source: str,
    source_data: dict,
    verdict: str,
    confidence: str,
    claude: anthropic.AsyncAnthropic,
) -> dict[str, dict]:
    """
    Runs all three judges for a single source agent result.
    Stores results in SQLite. Returns dict keyed by judge name.
    Non-blocking on failure — logs errors and continues.
    """
    await _ensure_evals_table()

    faithfulness_payload = {
        "product": product,
        "source": source,
        "source_data": source_data,
        "verdict": verdict,
        "confidence": confidence,
    }
    correctness_payload = faithfulness_payload.copy()
    relevance_payload = {
        "product": product,
        "source": source,
        "source_data": source_data,
    }

    payloads = {
        "faithfulness": faithfulness_payload,
        "correctness":  correctness_payload,
        "relevance":    relevance_payload,
    }

    results: dict[str, dict] = {}

    async def _judge_and_store(name: str):
        try:
            result = await _run_judge(name, JUDGES[name], payloads[name], claude)
            await _store_eval(
                review_id, product, source, name,
                result.get("label", "unknown"),
                float(result.get("score", 0.0)),
                result.get("explanation", ""),
            )
            results[name] = result
        except Exception as e:
            logger.warning("Eval %s/%s/%s failed: %s", source, name, product, e)
            results[name] = {"label": "error", "score": 0.0, "explanation": str(e)}

    await asyncio.gather(*[_judge_and_store(name) for name in JUDGES])
    return results


async def get_evals_for_review(review_id: str) -> list[dict]:
    """Returns all eval rows for a given review_id."""
    await _ensure_evals_table()
    async with aiosqlite.connect(dbmod.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT source, judge, label, score, explanation, created_at "
            "FROM evals WHERE review_id = ? ORDER BY source, judge",
            (review_id,),
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]
