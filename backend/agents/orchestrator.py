import json
from urllib.parse import quote_plus
import anthropic

SYSTEM_PROMPT = """You are the final verdict synthesizer for a product review app called signal.
You receive structured results from four sources: Wirecutter, CNET, Amazon, and Reddit.

Source weighting (highest to lowest):
1. Wirecutter (equal weight with CNET)
1. CNET (equal weight with Wirecutter)
3. Amazon
4. Reddit

For each source you receive: verdict (Buy/Consider/Skip), confidence (high/medium/low), and source-specific data.
Low-confidence or errored sources should be weighted less or noted as unavailable.

Synthesize a final verdict. Be direct and opinionated — avoid hedging when sources agree.

Return a JSON object only:
{
  "verdict": "Buy" | "Consider" | "Skip",
  "summary": "2-3 sentence explanation of the recommendation",
  "notable_disagreements": "string describing any significant source conflicts, or null if sources broadly agree",
  "recommended_action": "buy" | "consider" | "skip"
}"""


async def run(
    product: str,
    source_results: dict,
    claude: anthropic.AsyncAnthropic,
) -> dict:
    sources_text = []
    for source_name, result in source_results.items():
        if result.get("error"):
            sources_text.append(f"**{source_name.upper()}**: Unavailable ({result['error']})")
        else:
            sources_text.append(
                f"**{source_name.upper()}**: verdict={result.get('verdict', 'unknown')}, "
                f"confidence={result.get('confidence', 'unknown')}\n"
                f"Data: {json.dumps({k: v for k, v in result.items() if k not in ('verdict', 'confidence')})}"
            )

    message = await claude.messages.create(
        model="claude-opus-4-7",
        max_tokens=512,
        system=[
            {
                "type": "text",
                "text": SYSTEM_PROMPT,
                "cache_control": {"type": "ephemeral"},
            }
        ],
        messages=[
            {
                "role": "user",
                "content": f"Product: {product}\n\n" + "\n\n".join(sources_text),
            }
        ],
    )

    try:
        parsed = json.loads(message.content[0].text)
    except (json.JSONDecodeError, IndexError, KeyError):
        # Fallback: majority vote
        votes = [r.get("verdict") for r in source_results.values() if not r.get("error")]
        verdict = max(set(votes), key=votes.count) if votes else "Consider"
        parsed = {
            "verdict": verdict,
            "summary": "Based on available sources.",
            "notable_disagreements": None,
            "recommended_action": verdict.lower(),
        }

    buy_link = None
    if parsed.get("verdict") == "Buy":
        buy_link = f"https://www.amazon.com/s?k={quote_plus(product)}"

    return {
        "verdict": parsed.get("verdict", "Consider"),
        "summary": parsed.get("summary", ""),
        "notable_disagreements": parsed.get("notable_disagreements"),
        "buy_link": buy_link,
        "recommended_action": parsed.get("recommended_action", "consider"),
    }
