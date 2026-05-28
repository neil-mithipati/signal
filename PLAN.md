# signal — Planning Conversation

## Overview
Planning session for **signal**, an agentic product review app that aggregates and synthesizes research from verified sources (Wirecutter, CNET, Amazon, Reddit) to answer: *"Should I buy this?"*

---

## Initial Concept

**User:** You are an expert AI app developer. I want to create an app for reviewing products by only leveraging verified sources, particularly Wirecutter, RTINGS, Amazon, and Reddit. The app will initially take a user input for a product to review. Then, for each of the verified sources, a specialized agent will complete their review of the product using their verified source. Lastly, an orchestration agent will compile everyone's review into a final recommendation for the user. Feel free to create skills and MCP connectors where appropriate for any agentic workflows. Before we begin I need to refine a plan for building this app across multiple dimensions: recommendation, input channel, automation, and UI.

**Claude:** Proposed plan across 4 dimensions:

### Recommendation Engine
- 1 orchestrator + 4 specialized source agents running in parallel
- Each source agent returns: `{ summary, verdict, pros[], cons[], score, key_quotes[], source_url }`
- Source roles:
  - **Wirecutter** — Expert editorial pick
  - **RTINGS** — Objective benchmark scores
  - **Amazon** — Crowd sentiment, price, availability
  - **Reddit** — Real-world long-term experience

### Input Channel
- Product name, product URL, or category query
- Clarifying questions for ambiguous input

### Automation
- Claude Agents SDK
- Firecrawl MCP for scraping
- Parallel execution
- Caching layer

### UI
- Next.js 15 + React
- Two-panel layout: source cards + final recommendation
- SSE streaming for real-time updates

---

## Dimension 1 — Recommendation

**User:** Let's refine this plan one dimension at a time.

**Claude:** Starting with Recommendation. Questions:
1. Final output format?
2. Source weighting?
3. Disagreement handling?
4. Scope?

**User:**
1. Single clear verdict
2. RTINGS and Wirecutter should carry the most weight, then Reddit, then Amazon
3. Surface conflicts as a note below the recommendation
4. Strictly "should I buy?"

**Claude:** Locked in. Added `{ verdict, confidence }` schema per agent.

**User:** What does confidence mean here?

**Claude:** Confidence = data quality/coverage per source. Not "how certain is the verdict" but "how much signal does this source actually have on this product?" Low signal sources are skipped or flagged rather than factored in.

**User:** This works.

**User:** Make sure each agent knows how to review their source. For example, Amazon uses a 5 star rating, RTINGS uses a decimal rating, Wirecutter uses semantic rating such as "Our Pick", Reddit is purely sentiment analysis.

**Claude:** Source-specific literacy defined:
- **Wirecutter:** Semantic tiers — Our Pick > Also Great > Upgrade Pick > Budget Pick > No Longer Recommended > Not Listed
- **RTINGS:** Decimal 0–10, bands: 8.0+ strong Buy, 6.0–7.9 Consider, below 6.0 Skip
- **Amazon:** 5-star + review count + complaint patterns + badges
- **Reddit:** Sentiment analysis, weights newer posts higher

**User:** Rename signal_strength to confidence.

**Claude:** Done. Schema per agent: `{ verdict, confidence }`.

### Locked — Recommendation
- **Verdict:** Buy / Consider / Skip
- **Weighting:** Wirecutter = RTINGS > Reddit > Amazon
- **Conflicts:** "Notable disagreements" note below verdict
- **Scope:** Single product only
- **Agent schema:** `{ verdict, confidence }`
- **Confidence:** Data quality/coverage — low confidence sources skipped or flagged

---

## Dimension 2 — Input Channel

**User:** Yes (move to Input Channel).

**Claude:** Questions:
1. Primary input mode?
2. Ambiguity handling?
3. Category queries?
4. Input history?

**User:**
1. Either (name or URL)
2. Yes, ask clarification
3. Support it
4. No, standalone queries

**Claude:** Follow-up:
1. Category query resolution — present 2–3 candidates or auto-pick?
2. URL input — extract product and search all 4 normally, or treat pasted source as pre-answered?

**User:**
1. 2–3 candidates
2. Agent extracts product and searches all 4 sources normally

**User:** I also wanted to see different inputs as in: CLI, web app input, iMessage.

**Claude:** iMessage has no public API. Options: Mac Shortcuts, AppleScript, or SMS via Twilio.

**User:** Instead, what are some other popular messaging apps?

**Claude:** Options: Slack, Telegram, Discord, WhatsApp, SMS via Twilio.

**User:** Let's go with Telegram.

### Locked — Input Channel
- **Interfaces:** Web app, CLI, Telegram bot — all call the same shared backend
- **Input modes:** Product name or URL
- **Ambiguity:** App asks clarifying question before proceeding
- **Category queries:** Orchestrator resolves to 2–3 candidates, user picks one
- **URL input:** Product extracted, all 4 agents search normally
- **History:** Standalone queries, no session memory

---

## Dimension 3 — Automation

**User:** Yes (move to Automation).

**Claude:** Questions:
1. Agent framework preference?
2. Web scraping approach?
3. Parallelism constraints?
4. Caching?

**User:**
1. No preference
2. What is the most popular resource to use?
3. No constraints
4. Yes, 24h works

**Claude:** Firecrawl is the most popular choice in the AI/agent space — purpose-built for LLM apps, returns clean markdown, has an official MCP server.

**User:** *(Firecrawl API key)*

**Claude:** Noted — will store in `.env`. Locked in: Claude Agents SDK, Firecrawl MCP, full parallelism, 24h SQLite cache.

**User:** For the agent framework, is that the correct LLM model for each responsibility? Shouldn't Opus do the research since it's a compute heavy task?

**Claude:** The distinction: source agents do focused structured extraction (Sonnet is sufficient), orchestrator does nuanced multi-source synthesis and judgment (Opus earns its place here). The compute intensity of research is in tool calls (Firecrawl), not model reasoning.

**User:** Makes sense. Also, what are all the types of cost for this project?

**Claude:** Cost types:
- **Per-query (variable):** Orchestrator tokens (Opus), source agent tokens (Sonnet ×4), Firecrawl credits ×4 — cache hits eliminate all
- **Infrastructure (fixed/tiered):** Hosting, database (SQLite = free), Telegram bot (free)
- **Hidden/variable:** Token inflation from long Firecrawl markdown, retry costs, ambiguity resolution round-trips
- **One-time:** Development time
- **Dominant runtime cost:** Claude API tokens, especially Opus + Firecrawl markdown size

**User:** For Firecrawl, it would be great to stop the crawl once we know the rating from a source except for Reddit in which we should always scrape the whole page. Is that possible?

**Claude:** Firecrawl doesn't support true mid-scrape termination. Better solution: **Firecrawl Extract mode** for structured sources — define a schema, Firecrawl returns only those fields. Reddit uses standard Scrape mode for full page sentiment analysis.

**User:** Makes sense, except for Wirecutter in which the product could be 'Our Pick', 'Upgrade Pick', 'Budget Pick', etc... does the schema you provided cover that nuance?

**Claude:** Updated Wirecutter schema with explicit enum and position handling:
```json
{
  "product_found": "boolean",
  "verdict": "Our Pick | Also Great | Upgrade Pick | Budget Pick | No Longer Recommended",
  "is_primary_recommendation": "boolean",
  "blurb": "string"
}
```

**User:** Yes. For RTINGS some pages are blurred behind a paywall.

**Claude:** Options:
1. Accept partial data, reduce confidence when sub-scores missing
2. RTINGS premium subscription (~$5/mo) + authenticated scraping
3. Overall score only (reliably public)

**User:** If I do Option 2, how will you access it on my behalf?

**Claude:** Store credentials in `.env`, use Firecrawl browser actions to automate login. But flagged: RTINGS ToS likely prohibits automated scraping of premium content.

**User:** Can't Claude for Chrome use my browser session?

**Claude:** Firecrawl runs in the cloud — no access to local Chrome session. Would need local Playwright to tap into existing session, adding complexity. Recommended Option 3 (overall score only, always public).

**User:** Let's go with Option 3.

**Claude:** RTINGS schema: `{ product_found, overall_score (0-10), blurb }`

**User:** Also, for RTINGS, check out this update to their membership... *(pasted RTINGS article)*

**Claude:** The article reveals: (1) overall score is likely gated under "full test results", (2) they explicitly call out AI scraping as the reason for the change. Recommended dropping RTINGS entirely and exploring a fourth source.

**User:** Let's remove and explore a fourth source.

**Claude:** Options: Tom's Guide, CNET, PCMag, YouTube, Consumer Reports (paywalled).

**User:** I prefer CNET. Can you double-check the correct schema to use when scraping it?

**Claude:** *(Attempted WebFetch — CNET blocked Anthropic crawler. Used WebSearch instead.)*

CNET uses 0–10 scale. Score bands: 8.0+ Excellent, 7.0–7.9 Very Good, 5.0–5.9 Average. Flagged that ClaudeBot block is Anthropic-specific and unrelated to Firecrawl.

**User:** What does Anthropic use to crawl websites?

**Claude:** Anthropic uses **ClaudeBot**. Firecrawl is a completely separate third-party service — CNET blocking ClaudeBot has no bearing on Firecrawl.

**User:** Yes (keep CNET). But we only need the overall_score in terms of score properties.

**Claude:** CNET schema: `{ product_found, overall_score (0-10), verdict, pros[], cons[] }`

**User:** Schema: add product_found to both Amazon and Reddit. Caching: update TTL to 72h. Weighting: Wirecutter = CNET > Amazon > Reddit.

### Locked — Automation
- **Agent framework:** Claude Agents SDK — Sonnet for source agents, Opus for orchestrator
- **Web scraping:** Firecrawl
  - Extract mode: Wirecutter, CNET, Amazon
  - Scrape mode: Reddit (full page)
- **Schemas:**
  - Wirecutter: `{ product_found, verdict (enum), is_primary_recommendation, blurb }`
  - CNET: `{ product_found, overall_score (0–10), verdict, pros[], cons[] }`
  - Amazon: `{ product_found, star_rating, review_count, common_complaints[] }`
  - Reddit: `{ product_found }` + full page sentiment analysis
- **Parallelism:** All 4 agents simultaneously
- **Caching:** SQLite, 72h TTL, keyed on `(product, source)`
- **Weighting:** Wirecutter = CNET > Amazon > Reddit
- **Firecrawl key:** stored in `.env`

---

## Dimension 4 — UI

**User:** Yes (move to UI).

**Claude:** Questions:
1. Interface style?
2. Results layout?
3. Progressive loading?
4. Tech stack?

**User:**
1. Search-engine for web app, chat-like for Telegram
2. Verdict is the hero, sources secondary/expandable
3. Populate as they complete, loading spinner GIF + funny verb tagline (e.g. "deciphering Amazon")
4. Default (Next.js 15 + Tailwind)

**Claude:** Follow-ups:
1. Verdict timing — loading state while sources complete, or only appear when ready?
2. Loading verbs — curated fixed list or AI-generated?

**User:**
1. Loading state with orchestrator-themed verbs (orchestrating, traveling to another dimension, etc.)
2. Fixed list — any ideas?

**Claude:** Proposed verb lists per source.

**User:** For orchestrator add ones related to traveling to another dimension, black holes, Rick & Morty, and Star Wars. For source cards, make each verb related to the source card (Amazon = Jeff Bezos/bookstore, etc.).

**Claude:** Updated lists:

**Orchestrator:** portal to C-137, Citadel of Ricks, dark side, black hole, hyperspace, schwifty, etc.

**Wirecutter:** snipping, cutting, trimming...

**CNET:** booting mainframe, dial-up, defragmenting...

**Amazon:** warehouse boxes, Jeff's bookshelf, Seattle shipping...

**Reddit:** rabbit hole, hive mind, sorting by controversial...

**User:** For orchestrator, remove several; add two Star Wars. For Wirecutter, make them related to New York Times.

**Claude:** Updated. Wirecutter: checking front page, solving Wordle, Sunday edition, Connections, Mini crossword.

**User:** For Wirecutter, make them all related to NY Times, can also relate to their games.

**Claude:**
- checking the front page
- solving the Wordle
- publishing the Sunday edition
- hunting for the Connections
- playing the Mini crossword

**User:** Perfect.

**User:** Let's add three user buttons after orchestrator completes — Buy, Consider, Skip — all three always present. Buy = Amazon Pay → revised to Amazon deep link. Consider = add to Wishlist (SQLite). Skip = clear search.

**Claude:** Follow-ups:
1. Visual treatment of recommended action?
2. Amazon Pay or deep link?
3. Wishlist experience?
4. Skip on Telegram?

**User:**
1. Visually emphasized, others muted
2. Deep link (no merchant setup)
3. Modal accessible via star icon in header
4. Yes ("Got it, search cleared")

### Locked — UI
- **Web app:** Next.js 15 + Tailwind, search-engine style
- **Telegram:** Chat-like conversational interface
- **Results layout:** Verdict hero, source cards secondary/expandable
- **Progressive loading:** Cards populate as agents complete
- **Loading verbs:** Curated fixed lists (see below)
- **Post-verdict actions:** Buy / Consider / Skip always present
  - Recommended action visually emphasized, others muted
  - **Buy** → Amazon deep link (or "search the internet for nearest retailer")
  - **Consider** → Wishlist modal (SQLite)
  - **Skip** → Clear search / "Got it, search cleared" (Telegram)
- **Wishlist:** Modal via star icon in header, backed by SQLite

### Final Loading Verb Lists

**Orchestrator:**
- opening a portal to dimension C-137
- consulting the Citadel of Ricks
- crossing to the dark side
- collapsing into a black hole
- warping through hyperspace
- getting schwifty with the data
- may the data be with you
- activating the Death Star

**Wirecutter:**
- checking the front page
- solving the Wordle
- publishing the Sunday edition
- hunting for the Connections
- playing the Mini crossword

**CNET:**
- booting up the mainframe
- loading the dial-up
- connecting to the internet
- defragmenting the results
- buffering at 56k

**Amazon:**
- stacking boxes in the warehouse
- checking Jeff's bookshelf
- reading between the pages
- shipping from Seattle
- two-day priming the data

**Reddit:**
- diving into the rabbit hole
- asking the hive mind
- sorting by controversial
- waiting for karma
- scrolling past the memes

---

## Additional Variations Discussed

**Claude proposed:**
1. Head-to-head comparison
2. Deal Validator → **Deal Score** (v2)
3. Upgrade advisor
4. Gift finder
5. **Bundle Advisor** → **Bundler** (v2)

**User:** Keep Deal Score and Bundler as v2 backlog.

**User:** It would also be neat to execute the purchase if the recommendation is a buy. → Resolved as Buy button (Amazon deep link).

---

## V2 Backlog
- **Deal Score** — validates whether a current price is a good deal, adds CamelCamelCamel as price history source
- **Bundler** — recommends and reviews a coherent set of products for a use case

---

## Full App Summary

| Dimension | Decision |
|---|---|
| Sources | Wirecutter, CNET, Amazon, Reddit |
| Interfaces | Next.js web app, CLI, Telegram bot |
| Agent models | Sonnet ×4 (source agents), Opus (orchestrator) |
| Scraping | Firecrawl Extract (Wirecutter/CNET/Amazon), Scrape (Reddit) |
| Caching | SQLite, 72h TTL, keyed on (product, source) |
| Weighting | Wirecutter = CNET > Amazon > Reddit |
| Verdict | Buy / Consider / Skip |
| Actions | Buy (Amazon link) / Consider (Wishlist) / Skip (clear) |
| Wishlist | SQLite-backed modal via header star icon |
