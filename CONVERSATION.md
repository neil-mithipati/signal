# signal — Planning Conversation (Raw)

---

**Neil:** You are an expert AI app developer. I want to create an app for reviewing products by only leveraging verified sources, particularly Wirecutter, RTINGS, Amazon, and Reddit. The app will initially take a user input for a product to review. Then, for each of the verified sources, a specialized agent will complete their review of the product using their verified source. Lastly, an orchestration agent will compile everyone's review into a final recommendation for the user. Feel free to create skills and MCP connectors where appropriate for any agentic workflows. Before we begin I need to refine a plan for building this app across multiple dimensions: recommendation, input channel, automation, and UI.

**Claude:** Good, clean slate. Here's a structured plan across all four dimensions:

**Plan: signal**

**Dimension 1 — Recommendation Engine**

Agent architecture:
- 1 orchestrator + 4 specialized source agents running in parallel
- Each source agent returns a structured payload: `{ summary, verdict, pros[], cons[], score, key_quotes[], source_url }`
- Orchestrator synthesizes into a final recommendation with:
  - Overall verdict: Buy / Consider / Skip
  - Confidence score (how much sources agree)
  - Category-aware weighting (e.g. RTINGS gets higher weight for AV gear, Wirecutter for general consumer goods)
  - Top 3 reasons + notable dissents

Source roles:

| Source | Role |
|---|---|
| Wirecutter | Expert editorial pick — is it recommended at all? |
| RTINGS | Objective benchmark scores (great for electronics) |
| Amazon | Crowd sentiment, price, availability, complaint patterns |
| Reddit | Real-world long-term experience, edge cases, alternatives |

**Dimension 2 — Input Channel**

Three input modes, in priority order:
1. Product name — "Sony WH-1000XM5" (most common)
2. Product URL — paste any Amazon/Wirecutter link; agents infer the product and fan out to all sources
3. Category query — "best noise-cancelling headphones under $300" → orchestrator first resolves to top candidates, then reviews them

Each agent uses web search + scraping tools (Firecrawl MCP) to locate the product on their source. No hardcoded URLs.

**Dimension 3 — Automation**

Stack:
- Claude Agents SDK (multi-agent with `claude-sonnet-4-6` for source agents, `claude-opus-4-6` for orchestrator)
- Firecrawl MCP for scraping — handles JS-rendered pages, rate limits, and returns clean markdown
- Parallel execution — all 4 source agents fire simultaneously; orchestrator waits on all then synthesizes
- Streaming — each agent streams partial results back so the UI can populate progressively

MCP servers to build:
- `firecrawl` — already exists; handles all 4 scraping targets
- Optionally: a thin `reddit-search` MCP using Reddit's JSON API (no scraping needed — `reddit.com/r/.../.json`)

Caching:
- Cache agent results by `(product_name, source)` with a 24h TTL (reviews don't change hourly)
- SQLite or Redis for cache store

**Dimension 4 — UI**

Framework: Next.js 15 (App Router) with React

Layout — two-panel:
```
┌─────────────────────────────────────────────┐
│  [Search bar: product name or URL]  [Go]    │
├──────────────┬──────────────────────────────┤
│ Source Cards │  Final Recommendation        │
│              │                              │
│ ◉ Wirecutter │  Verdict: ✅ Buy             │
│ ◉ RTINGS     │  Confidence: High (3/4 agree)│
│ ◉ Amazon     │  Top reasons...              │
│ ◉ Reddit     │  Notable caveats...          │
│              │                              │
│ (each card   │  [View sources]              │
│  populates   │                              │
│  as agent    │                              │
│  completes)  │                              │
└──────────────┴──────────────────────────────┘
```

UX details:
- Source cards show a spinner → then populate with verdict + key points as each agent finishes (SSE streaming)
- Color-coded verdict badges (green/yellow/red) per source
- Expandable card for full source details + direct link
- Mobile: stack cards vertically above final recommendation

Key Decisions to Make Before Building:
1. Firecrawl API key — do you have one, or should we use Playwright/Puppeteer for scraping instead?
2. Reddit access — Reddit's public JSON API (`/search.json`) vs. official Reddit API (requires OAuth app)?
3. Hosting target — local dev only, or deploy to Vercel/Railway?
4. Auth — single-user local app, or multi-user with accounts?
5. Caching — SQLite (simple, no dependencies) or Redis (if you want distributed)?

Once you answer those, I can scaffold the full project: Next.js app, agent orchestration layer, MCP config, and the source-specific agent prompts.

---

**Neil:** Let's refine this plan one dimension at a time.

**Claude:** Sounds good. Let's start with Recommendation — the core of the app.

A few questions to sharpen the design:

1. Final output format — do you want a single clear verdict (Buy / Consider / Skip), a ranked comparison if multiple products come up, or something more nuanced like a scorecard?
2. Source weighting — should all 4 sources carry equal weight, or should weight vary by product category (e.g. RTINGS matters more for TVs/headphones, Reddit more for software/services)?
3. Disagreement handling — if Wirecutter says "top pick" but Reddit says "avoid after 6 months", how should the orchestrator handle that? Surface the conflict explicitly, or try to resolve it into one verdict?
4. Scope — strictly "should I buy this specific product", or also "what should I buy instead" (i.e. alternatives)?

---

**Neil:** 1: single clear verdict. 2: RTINGS and Wirecutter should carry the most weight, then Reddit, then Amazon. 3: surface conflicts as a note below the recommendation. 4: strictly "should I buy?"

**Claude:** Locked in for Recommendation:

- Verdict: Buy / Consider / Skip — one clear answer
- Weighting: Wirecutter = RTINGS > Reddit > Amazon
- Conflicts: Surfaced as a "Notable disagreements" note below the verdict, not folded into it
- Scope: Single product only — "should I buy this?"

Ready to move to Input Channel.

The core question here is what the user types into the app and how the agents interpret it. A few things to nail down:

1. Primary input mode — product name only (e.g. "Sony WH-1000XM5"), or also support pasting a URL (Amazon link, Wirecutter article, etc.) as a starting point?
2. Ambiguity handling — if someone types "AirPods" (multiple models exist), should the app ask a clarifying question, or just pick the most recent/popular variant and proceed?
3. Category queries — do you want to support "best headphones under $200" style queries, or is this strictly one specific product at a time?
4. Input history — should the app remember past searches within a session, or is each query standalone?

---

**Neil:** Back to Recommendation.

**Claude:** Of course. What do you want to revisit?

---

**Neil:** Make sure each agent knows how to review their source. For example, Amazon uses a 5 star rating, RTINGS uses a decimal rating, Wirecutter uses semantic rating such as "Our Pick", Reddit is purely sentiment analysis.

**Claude:** Good call — each agent needs source-specific literacy. Here's what I'm thinking for each:

**Wirecutter agent**
- Knows the semantic tiers: Our Pick → Also Great → Budget Pick → Upgrade Pick → No Longer Recommended → not listed
- Our Pick maps strongest to Buy; No Longer Recommended or absence maps to Skip

**RTINGS agent**
- Reads the overall decimal score (0–10) plus relevant sub-scores by category (e.g. sound quality, build, value)
- Knows score bands: 8.0+ strong Buy, 6.0–7.9 Consider, below 6.0 Skip

**Amazon agent**
- Reads star rating (1–5) + review count (low count = low confidence) + common complaint patterns from review text
- Also flags: Amazon's Choice, Best Seller, or verified purchase ratio

**Reddit agent**
- No structured score — does sentiment analysis across top posts and comments
- Flags recurring themes (e.g. "build quality issues after 6 months" appearing frequently = a conflict note)
- Weights newer posts higher than old ones

Two follow-up questions:

1. Normalization — each agent should translate their source-specific signal into the shared `{ verdict, confidence }` schema before handing off to the orchestrator. Should the orchestrator do the translation, or should each agent own it?
2. RTINGS sub-scores — should the agent pull category-specific sub-scores (useful for surfacing "great sound, poor build") or just the overall score?

---

**Neil:** What does confidence mean here?

**Claude:** Good question. I used it loosely — let me be more precise.

What I meant was: how much signal does the source actually have on this product?

For example:
- RTINGS hasn't tested it → low signal, don't factor it in
- Amazon has 12 reviews → low signal, weight it less
- Amazon has 4,200 reviews → high signal, weight it normally
- Reddit has one 3-year-old thread → low signal
- Wirecutter reviewed it but it's 2 years old → moderate signal

So it's less about "confidence in the verdict" and more about data quality / coverage — did the source actually have enough to go on?

This matters for the orchestrator: if RTINGS has no data, it shouldn't drag down the recommendation or create a false "conflict". It should just be skipped.

Does that framing work, or do you want to handle missing/thin sources differently — like flagging to the user that the recommendation is based on fewer sources than usual?

---

**Neil:** This works.

**Claude:** Recommendation dimension is fully locked:

- Verdict: Buy / Consider / Skip
- Weighting: Wirecutter = RTINGS > Reddit > Amazon
- Conflicts: Surfaced as a note below the verdict
- Scope: Single product only
- Source literacy: Each agent knows its own rating system and translates to a shared `{ verdict, signal_strength }` schema
- Signal strength: Measures data quality/coverage per source — low signal sources are skipped or flagged rather than factored in
- Orchestrator: Weighs verdicts by source weight × signal strength, then synthesizes final Buy / Consider / Skip

Ready to move to Input Channel?

---

**Neil:** Let's rename signal_strength to confidence.

**Claude:** Done — it's `confidence` throughout. The schema each agent returns is `{ verdict, confidence }`.

Ready to move to Input Channel?

---

**Neil:** Yes.

**Claude:** Input Channel — how users tell the app what to review.

Four things to nail down:

1. Primary input mode — product name only (e.g. "Sony WH-1000XM5"), or also support pasting a URL (Amazon link, Wirecutter article, etc.) as a starting point?
2. Ambiguity handling — if someone types "AirPods" (multiple models exist), should the app ask a clarifying question, or just pick the most recent/popular variant and proceed?
3. Category queries — support "best headphones under $200" style queries, or strictly one specific product at a time?
4. Input history — remember past searches within a session, or is each query standalone?

---

**Neil:** 1: either. 2: yes, ask clarification. 3: support it. 4: no, standalone queries.

**Claude:** Two follow-up questions before locking this down:

1. Category query resolution — if someone asks "best headphones under $200", the app needs to pick a specific product before agents can fan out. Should it present the top 2–3 candidates and ask the user to choose, or should the orchestrator just pick the strongest candidate automatically and proceed?
2. URL input — when a URL is pasted, the agent extracts the product and then searches all 4 sources normally. Or should it treat the pasted source as pre-answered (e.g. paste an Amazon URL → Amazon agent skips search and reads that page directly)?

---

**Neil:** 1: 2-3 candidates. 2: agent extracts product and then searches all 4 sources normally.

**Claude:** Locked in for Input Channel:

- Input modes: Product name or URL — both supported
- Ambiguity: App asks a clarifying question before proceeding
- Category queries: Orchestrator resolves to 2–3 candidates, user picks one, then full review runs
- URL input: Product extracted from URL, then all 4 source agents search normally (no source skipping)
- History: Standalone queries, no session memory

Ready to move to Automation?

---

**Neil:** I also wanted to see different inputs as in: CLI, web app input, iMessage.

**Claude:** Good addition. Before locking this in, one clarifying question on iMessage specifically:

iMessage — Apple has no public API for this, so it requires a Mac-specific workaround. A few approaches:

- Mac Shortcuts — a Shortcut triggers the app when you share a product name/URL via iMessage to yourself or a dedicated contact
- AppleScript — a background process monitors a specific iMessage conversation and responds automatically
- Dedicated phone number — use SMS (Twilio) instead of iMessage proper, which has a real API

Which direction fits what you're imagining? And is this Mac-only, or do you need it to work on iPhone too?

---

**Neil:** Instead, what are some other popular messaging apps?

**Claude:** Popular options with real APIs that are much easier to integrate:

- Slack — webhook or bot; great if you're already in a workspace
- Telegram — clean bot API, very popular for personal automation
- Discord — bot API; good if you have a server
- WhatsApp — official Cloud API (Meta), requires business account setup
- SMS via Twilio — universal, no app required, just a phone number

Which of these appeal to you, or do you want to support more than one?

---

**Neil:** Let's go with Telegram.

**Claude:** Good choice — Telegram's bot API is clean and well-documented.

So the updated Input Channel picture is:

- Interfaces: Web app, CLI, Telegram bot
- Input modes: Product name or URL — both supported
- Ambiguity: App asks a clarifying question before proceeding (works naturally in Telegram's conversational flow)
- Category queries: Resolves to 2–3 candidates, user picks one
- URL input: Product extracted, all 4 source agents search normally
- History: Standalone queries, no session memory

All three interfaces call the same shared backend — the review logic lives once, the interfaces are just different entry points.

Ready to move to Automation?

---

**Neil:** Yes.

**Claude:** Automation — how the agents are built, orchestrated, and run.

Four things to nail down:

1. Agent framework — this is a multi-agent app with an orchestrator + 4 source agents. Are you comfortable building on the Claude API directly (Agents SDK), or do you have a preference for a framework like LangChain, LangGraph, or CrewAI?
2. Web scraping — agents need to fetch content from Wirecutter, RTINGS, Amazon, and Reddit. Do you have a Firecrawl API key, or should we use a different approach (Playwright, direct HTTP + parsing)?
3. Parallelism — all 4 source agents should run simultaneously. Any constraints on concurrency, or run them fully in parallel?
4. Caching — should results be cached so repeated queries on the same product don't re-run all agents? If yes, how long should results stay fresh (e.g. 24h)?

---

**Neil:** 1: no preference. 2: what is the most popular resource to use? 3: no constraints. 4: yes, 24h works.

**Claude:** Firecrawl is the most popular choice in the AI/agent space right now. It's purpose-built for LLM apps — returns clean markdown instead of raw HTML, handles JavaScript-rendered pages, and has an official MCP server. It works well for all 4 of our sources.

Do you have a Firecrawl API key, or do you need to sign up for one?

---

**Neil:** *(Firecrawl API key)*

**Claude:** Got it — I'll use that when we build. A word of caution: avoid sharing that key publicly (GitHub, etc.) — we'll store it in a `.env` file and make sure it's gitignored.

Locking in Automation:

- Agent framework: Claude API (Agents SDK) — `claude-sonnet-4-6` for source agents, `claude-opus-4-6` for orchestrator
- Web scraping: Firecrawl MCP — clean markdown output, handles JS rendering, works for all 4 sources
- Parallelism: All 4 source agents run simultaneously, orchestrator waits then synthesizes
- Caching: 24h TTL keyed on `(product, source)` — SQLite for simplicity

Ready to move to UI?

---

**Neil:** For the agent framework, is that the correct LLM model for each responsibility? Shouldn't Opus do the research since it's a compute heavy task?

**Claude:** Good challenge. The distinction is worth clarifying:

Source agents are doing focused, structured work — find the product on one site, extract specific fields (rating, verdict, review text), return a structured payload. This is well-defined extraction, not deep reasoning. Sonnet handles this well and is faster and cheaper at scale.

Orchestrator is doing the harder reasoning — weighing 4 conflicting signals, applying source weights × confidence, deciding between Buy/Consider/Skip, and identifying which conflicts are worth surfacing to the user. That judgment and synthesis is where Opus earns its place.

So the original assignment stands:
- Source agents → Sonnet (structured extraction)
- Orchestrator → Opus (nuanced multi-source synthesis)

The compute intensity of research is mostly in the tool calls (Firecrawl fetching pages) — that's infrastructure cost, not model cost. The hard reasoning lives in the orchestrator.

Does that logic hold for you, or do you still want to swap them?

---

**Neil:** Makes sense. Also, what are all the types of cost for this project if you had to label each?

**Claude:** Here are all the cost types for this project:

**Per-query (variable — scales with usage)**
- Orchestrator tokens — Opus input/output per synthesis (most expensive per call)
- Source agent tokens — Sonnet input/output × 4 agents per query
- Firecrawl credits — per page scraped × 4 sources per query
- Cache hits eliminate all of the above for repeat queries within 24h

**Infrastructure (fixed or tiered)**
- Hosting — web app + backend server (Vercel free tier likely covers light usage)
- Database — SQLite is free/local; only costs if you move to a managed DB
- Telegram bot — free, no API cost

**Hidden/variable**
- Token inflation — Firecrawl returns full page markdown; long pages = more tokens fed into source agents. Wirecutter and RTINGS pages can be verbose.
- Retry costs — failed scrapes that retry burn both Firecrawl credits and agent tokens
- Ambiguity resolution — category queries and clarifying questions add extra LLM round-trips before the main review even starts

**One-time (development)**
- Engineer time to build and integrate

The dominant runtime cost will be Claude API tokens — specifically Opus for the orchestrator and the size of Firecrawl's markdown output fed into Sonnet. Caching aggressively is the main lever for controlling this.

Want to set any cost guardrails (e.g. max tokens per agent, truncating Firecrawl output)?

---

**Neil:** For Firecrawl, it would be great to stop the crawl once we know the rating from a source except for Reddit in which we should always scrape the whole page. Is that possible?

**Claude:** Firecrawl doesn't support true mid-scrape termination — it always fetches the full page server-side. But there's a better solution that achieves the same goal:

Firecrawl Extract mode — instead of returning full page markdown, you define a schema and Firecrawl uses an LLM to pull only those fields. For example:

- Wirecutter: extract `{ verdict, tier, blurb }`
- RTINGS: extract `{ overall_score, sub_scores, verdict }`
- Amazon: extract `{ star_rating, review_count, common_complaints }`

This means the source agent never sees the full page — just the structured fields. Cheaper on tokens, faster, and cleaner.

Reddit stays on full scrape mode — sentiment analysis needs the full comment thread, so it uses standard Firecrawl scrape and the agent processes the whole page.

So the revised approach:
- Wirecutter, RTINGS, Amazon → Firecrawl Extract (schema-defined, minimal output)
- Reddit → Firecrawl Scrape (full page, sentiment analysis)

This also reduces token inflation significantly for the structured sources. Want to lock this in?

---

**Neil:** Makes sense, except for Wirecutter in which the product could be 'Our Pick', 'Upgrade Pick', 'Budget Pick', etc... does the schema you provided cover that nuance?

**Claude:** Good catch — it does, but only if we're explicit about it. The `tier` field in the schema needs to be an enum so the agent knows exactly what values to expect:

```json
{
  "verdict": "Our Pick | Also Great | Upgrade Pick | Budget Pick | No Longer Recommended | Not Listed",
  "tier": "primary | secondary | budget | upgrade | deprecated | none",
  "blurb": "string"
}
```

But there's a subtlety — Wirecutter sometimes lists multiple products per article (e.g. "Our Pick" AND "Also Great"). The schema also needs to handle which position the specific product holds in that article, not just what tiers exist on the page.

So the fuller schema:

```json
{
  "product_found": "boolean",
  "verdict": "Our Pick | Also Great | Upgrade Pick | Budget Pick | No Longer Recommended",
  "is_primary_recommendation": "boolean",
  "blurb": "string"
}
```

`product_found: false` maps directly to low confidence in the orchestrator — Wirecutter simply hasn't reviewed it.

Does this cover what you had in mind?

---

**Neil:** Yes. For RTINGS some pages are blurred behind a paywall.

**Claude:** This is a real constraint. On RTINGS, the overall score is typically public but detailed sub-scores and some measurements are blurred behind their premium tier.

A few ways to handle it:

1. Accept partial data — extract only what's publicly visible (usually the overall score), mark confidence as lower when sub-scores are missing, and proceed
2. RTINGS premium subscription — pay for access, use authenticated scraping to get full data. RTINGS premium is ~$5/month
3. Overall score only — deliberately scope the RTINGS schema to just the overall score since that's reliably public, skip sub-scores entirely

Option 1 feels fragile — confidence becomes a proxy for "how much of the paywall did we hit" which is hard to reason about consistently.

Option 3 is clean but loses the nuance of sub-scores (e.g. great sound, poor build quality).

Option 2 gets you full data reliably, and at $5/month it's likely the cheapest line item in this whole project.

Which direction do you want to go?

---

**Neil:** If I do Option 2, how will you access it on my behalf?

**Claude:** Good question to ask upfront. The practical approach:

1. You store your RTINGS credentials in the project's `.env` file (`RTINGS_EMAIL`, `RTINGS_PASSWORD`)
2. Firecrawl supports browser actions — it can automate a login sequence (fill email, fill password, click submit) before scraping the page
3. The RTINGS agent passes those actions to Firecrawl on each request, scraping the authenticated page

So your credentials never leave your environment — they go from `.env` → your backend → Firecrawl's browser, and Firecrawl returns the full page content.

One thing worth flagging: RTINGS' Terms of Service likely prohibit automated scraping of premium content, even if you're a paying subscriber. You'd be in a grey area.

Two cleaner alternatives if that's a concern:
- Option 1 (revised) — accept partial public data, reduce confidence when sub-scores are missing
- Option 3 — overall score only, reliably public, no ToS risk

Do you want to proceed with the authenticated approach knowing that, or pivot to one of the alternatives?

---

**Neil:** Can't Claude for Chrome use my browser session?

**Claude:** The idea is right but Firecrawl can't do it — it runs its browser in the cloud, so it has no access to your local Chrome session.

To use your existing logged-in browser session, you'd need a local browser automation tool like Playwright connecting to your actual Chrome instance. That approach works but means replacing Firecrawl with Playwright specifically for RTINGS — adding complexity we wanted to avoid.

The cleaner path is probably to drop the RTINGS sub-scores ambition and go with Option 3 — overall score only, always public, no ToS risk, no credential management, Firecrawl works as-is.

The overall score (e.g. 8.3/10) is actually the most useful signal anyway — sub-scores add nuance but the orchestrator has Reddit and Wirecutter to fill in that texture.

Want to go with Option 3 and keep Firecrawl consistent across all sources?

---

**Neil:** Let's go with Option 3.

**Claude:** Locked in. Updating the RTINGS schema to:

```json
{
  "product_found": "boolean",
  "overall_score": "number (0-10)",
  "blurb": "string"
}
```

Simple, reliable, no auth complexity.

Full Automation dimension locked:

- Agent framework: Claude Agents SDK — Sonnet for source agents, Opus for orchestrator
- Web scraping: Firecrawl — Extract mode for Wirecutter/RTINGS/Amazon, Scrape mode for Reddit
- Wirecutter schema: `product_found`, `verdict` (enum), `is_primary_recommendation`, `blurb`
- RTINGS schema: `product_found`, `overall_score` (0–10, public only), `blurb`
- Amazon schema: `star_rating`, `review_count`, `common_complaints`
- Reddit: full page scrape, sentiment analysis by source agent
- Parallelism: all 4 agents run simultaneously
- Caching: 24h TTL, keyed on `(product, source)`, SQLite
- Firecrawl key: stored in `.env`

Ready to move to UI?

---

**Neil:** Also, for RTINGS, check out this update to their membership, I believe we should be good for scraping their overall score now? https://www.rtings.com/company/revamping-our-membership-program

**Claude:** *(Fetched URL — page returned `"has_paywall":true` for TVs, Headphones, and Monitors but did not return the full article content.)*

The page didn't return the article content clearly, but I did notice it returned `"has_paywall":true` for TVs, Headphones, and Monitors — their main categories.

I'd recommend verifying this yourself by visiting the page directly. The key question is: is the overall score (the single top-line number) freely visible without login?

If yes, we're fine — Option 3 stays as-is and Firecrawl Extract will get it. If the overall score itself is paywalled, we're back to the earlier decision point.

Can you check and confirm what's gated?

---

**Neil:** Okay I'll paste the article below:

> In a world filled with marketing claims, sponsored reviews, and AI-generated content, independent and real product testing done by humans matters more than ever.
>
> Today, we're launching an important update to our membership program, previously called Insider Access, now simply RTINGS.com Membership.
>
> While much of RTINGS.com remains free, our full test results and in-depth product analysis are now available only to members. We'll continue to iterate on what that looks like over time as we refine the model across different product categories.
>
> We've had a soft paywall for a few years now, with a limited number of free pageviews on most product categories. We are now moving to a more membership-supported model to ensure RTINGS.com can remain independent, sustainable, and focused on helping you, the consumers, buy the best product for your needs.
>
> **Why We're Making This Change**
> RTINGS.com has historically relied heavily on organic search traffic from Google and affiliate links. That model is becoming less reliable. Fewer people click through from Google organic results than they used to. At the same time, AI actively scrapes and reuses our test results, often without attribution and without the context needed to interpret them correctly.
>
> Meanwhile, performing lab-based and in-depth testing is expensive. We buy every product ourselves, like normal consumers (no paid or sponsored reviews), test them using standardized, repeatable methods, and publish the full results transparently.
>
> A membership-supported model reduces our dependence on Google, limits unrestricted AI scraping of our test results, and gives us incentives that are more sustainable and aligned with consumers.
>
> **Why Independent Testing Matters More Than Ever**
> More than ever, consumers need a trusted source of product reviews for their buying decisions.
>
> Customer reviews and forums like Reddit are increasingly astroturfed. Brands manipulate sentiment and blur the line between real user experience and marketing. At the same time, AI-generated summaries are now a major source of product information, but they frequently hallucinate details or present incorrect information with high confidence.
>
> RTINGS.com exists specifically to avoid that. We buy and test products ourselves, using the same methodology, so people can see the test results and make up their own minds about how the products perform in real life, without being biased by brands.
>
> **Why Membership Aligns Incentives Better**
> Affiliate revenue isn't perfectly aligned with consumers. Without explicit safeguards, it naturally creates incentives to recommend higher-priced products or those with higher commissions. At RTINGS.com, we've done a great job building a strong wall between our editorial independence and monetization (for example, we don't shy away from recommending a DIY air purifier), but this incentive structure is not ideal.
>
> Membership aligns incentives more cleanly. If the information isn't useful, accurate, and worth paying for, people won't subscribe. This is the incentive structure we want to help consumers directly to stay unbiased and continuously improve the quality of our test results.
>
> **A Note To Longtime Users**
> RTINGS.com started in 2011 with televisions and has grown into the worldwide leader in data-driven reviews. We now cover 28 product categories, including electronics, home appliances, refrigerators, running shoes, and mattresses. Throughout that time, we've never accepted paid or sponsored reviews, and we continue to buy every product we test ourselves.
>
> A large part of that growth, and many of the improvements to our testing methodology, scoring systems, and site features, came directly from users' feedback over the years.
>
> We understand that these changes will frustrate some longtime users. However, the alternative is relying more heavily on platforms and monetization models that don't align well with independent lab test data to help consumers.
>
> Independent product testing matters more than ever. If you value real, comparable data rather than marketing claims, become a member to support our work and our mission to help you, the consumers, buy the best product for your needs.
>
> Thank you for your support.

**Claude:** This actually raises a red flag beyond just paywalls. Two things stand out:

1. Overall score is likely gated — "full test results and in-depth product analysis are now available only to members" almost certainly includes the overall score.
2. They explicitly call out AI scraping — *"AI actively scrapes and reuses our test results, often without attribution and without the context needed to interpret them correctly"* is the direct reason they're moving to this model. Our app would be exactly what they're describing, even with a paid membership.

So even Option 2 (authenticated scraping with a subscription) is ethically grey here — they're not just paywalling for revenue, they're specifically trying to prevent what we'd be doing.

My honest recommendation: drop RTINGS as a source. The timing is bad and the intent is clear.

The remaining three sources still give strong coverage:
- Wirecutter — expert editorial verdict
- Amazon — crowd sentiment + pricing
- Reddit — real-world long-term experience

And the weighting would adjust to: Wirecutter > Reddit > Amazon.

Want to remove RTINGS and rebalance, or explore a different fourth source?

---

**Neil:** Let's remove and explore a fourth source.

**Claude:** Good candidates to replace RTINGS' objective scoring role:

| Source | What it adds | Rating format | Freely scrapable |
|---|---|---|---|
| Tom's Guide | Expert editorial + numeric scores, broad category coverage | Numeric (0–10) | Yes |
| CNET | Expert reviews + numeric scores, very broad coverage | Numeric (0–10) | Yes |
| PCMag | Strong for tech/electronics, editors' choice awards | Numeric (0–100) + award tier | Yes |
| YouTube | Video reviews from trusted creators (MKBHD, LTT, etc.) | Sentiment from transcript | Complex — transcripts vary by creator |
| Consumer Reports | Gold standard for appliances/cars | Numeric score | Paywalled — same problem as RTINGS |

Tom's Guide and CNET are the most natural fits — both provide structured numeric scores across broad categories, freely accessible, and complement Wirecutter's editorial role without overlapping too much.

PCMag is strong specifically for tech but thinner outside that category.

YouTube is powerful but unpredictable — transcript quality and creator coverage varies too much to rely on.

Which direction interests you?

---

**Neil:** I prefer CNET, used it more historically, can you double-check the correct schema to use when scraping it?

**Claude:** *(Attempted WebFetch on cnet.com — blocked. Ran WebSearch instead.)*

Good news and a flag:

Schema confirmed — CNET uses a clean 0–10 scale with consistent structure:

```json
{
  "product_found": "boolean",
  "overall_score": "number (0-10)",
  "design_score": "number (0-10)",
  "features_score": "number (0-10)",
  "performance_score": "number (0-10)",
  "verdict": "string",
  "pros": ["string"],
  "cons": ["string"]
}
```

Score bands: 8.0+ = Excellent, 7.0–7.9 = Very Good, 5.0–5.9 = Average — the CNET agent can map these to Buy / Consider / Skip accordingly.

The flag — CNET is blocking Anthropic's crawler specifically. Firecrawl uses its own infrastructure so it may still work, but CNET could be blocking scrapers broadly. Worth testing early in the build before committing to it.

If Firecrawl gets blocked, Tom's Guide would be the natural fallback — same numeric format, same broad coverage.

Want to keep CNET as the plan with Tom's Guide as a stated fallback, or swap now?

---

**Neil:** What does Anthropic use to crawl websites?

**Claude:** Anthropic uses a web crawler called ClaudeBot (user agent: `ClaudeBot`). It's used to gather training data.

The block we hit is CNET blocking ClaudeBot specifically — that's Anthropic's data crawler, not Claude Code or Firecrawl. They're completely separate:

- ClaudeBot — Anthropic's training data crawler, commonly blocked by publishers
- Firecrawl — independent third-party service with its own infrastructure and user agent, unrelated to Anthropic

So CNET blocking ClaudeBot has no bearing on whether Firecrawl can scrape it. Firecrawl will almost certainly work fine.

Want to keep CNET as the confirmed fourth source?

---

**Neil:** Yes, but we only need the overall_score in terms of score properties.

**Claude:** Agreed — keeping it simple and consistent with how we handled RTINGS. Updated CNET schema:

```json
{
  "product_found": "boolean",
  "overall_score": "number (0-10)",
  "verdict": "string",
  "pros": ["string"],
  "cons": ["string"]
}
```

Automation dimension fully locked:

- Agent framework: Claude Agents SDK — Sonnet for source agents, Opus for orchestrator
- Web scraping: Firecrawl — Extract mode for Wirecutter/CNET/Amazon, Scrape mode for Reddit
- Wirecutter schema: `product_found`, `verdict` (enum), `is_primary_recommendation`, `blurb`
- CNET schema: `product_found`, `overall_score` (0–10), `verdict`, `pros[]`, `cons[]`
- Amazon schema: `star_rating`, `review_count`, `common_complaints[]`
- Reddit: full page scrape, sentiment analysis by source agent
- Parallelism: all 4 agents run simultaneously
- Caching: 24h TTL, keyed on `(product, source)`, SQLite
- Weighting: Wirecutter = CNET > Reddit > Amazon
- Firecrawl key: stored in `.env`

Ready to move to UI?

---

**Neil:** Schema: add product_found to both Amazon and Reddit. Caching: update TTL to 72h. Weighting: Wirecutter = CNET > Amazon > Reddit.

**Claude:** Updated. Automation dimension fully locked:

- Agent framework: Claude Agents SDK — Sonnet for source agents, Opus for orchestrator
- Web scraping: Firecrawl — Extract mode for Wirecutter/CNET/Amazon, Scrape mode for Reddit
- Wirecutter schema: `product_found`, `verdict` (enum), `is_primary_recommendation`, `blurb`
- CNET schema: `product_found`, `overall_score` (0–10), `verdict`, `pros[]`, `cons[]`
- Amazon schema: `product_found`, `star_rating`, `review_count`, `common_complaints[]`
- Reddit schema: `product_found`, full page scrape, sentiment analysis by source agent
- Parallelism: all 4 agents run simultaneously
- Caching: 72h TTL, keyed on `(product, source)`, SQLite
- Weighting: Wirecutter = CNET > Amazon > Reddit
- Firecrawl key: stored in `.env`

Ready to move to UI?

---

**Neil:** Yes.

**Claude:** UI — what the user sees and interacts with.

Four things to nail down:

1. Interface style — clean search-engine style (single input, results below), or a chat-like conversational interface where clarifying questions feel natural?
2. Results layout — should all 4 source cards and the final verdict appear on the same page, or should the verdict be the hero and sources be secondary/expandable?
3. Progressive loading — since agents run in parallel and finish at different times, should source cards populate as they complete (live), or should the page wait and show everything at once?
4. Tech stack — any preference, or should I pick what fits best? (I'd default to Next.js 15 + Tailwind)

---

**Neil:** 1: search-engine for web app but chat-like for Telegram. 2: latter suggestion. 3: populate as they complete but add a loading spinner GIF to each source card loading and a tagline with a random funny verb and the source name `<loading_verb> <source_name>` such as deciphering Amazon. 4: default sounds great.

**Claude:** Good instincts on all of these. Two quick follow-ups:

1. Verdict timing — since the orchestrator can only run after all 4 source agents finish, the verdict will always appear last. Should it show a loading state while sources are still completing, or only appear once it's ready?
2. Loading verbs — should the funny verbs be curated (a fixed list we write), or AI-generated fresh each time?

---

**Neil:** 1: should also have a loading state but the funny loading verb should be related to words like orchestrating. 2: fixed list so it's not taxing, any ideas?

**Claude:** For the orchestrator tagline, something like:

- *orchestrating the chaos*
- *assembling the council*
- *consulting the algorithm*
- *deliberating furiously*
- *weighing the evidence*

For source cards, verbs by source:

- Wirecutter: dissecting, scrutinizing, interrogating, analyzing, combing through
- CNET: decoding, investigating, parsing, unpacking, examining
- Amazon: sifting through, wading through, filtering, excavating, mining
- Reddit: lurking, diving into, scrolling through, deciphering, surviving

Do these feel right, or want to tweak the tone — more absurd, more technical, more playful?

---

**Neil:** For the orchestrator add ones related to traveling to another dimension, black holes, Rick & Morty, and Star Wars. For the source cards, make each verb related to the source card, as in, the verbs for Amazon should be related to Jeff Bezos or Amazon starting off as a book store, etc...

**Claude:** Love it. Here's the updated list:

**Orchestrator:**
- *orchestrating the chaos*
- *assembling the council*
- *opening a portal to dimension C-137*
- *traveling through a wormhole*
- *consulting the Citadel of Ricks*
- *calculating the Kessel Run*
- *crossing to the dark side*
- *collapsing into a black hole*
- *warping through hyperspace*
- *getting schwifty with the data*

**Wirecutter:**
- *snipping through the noise*
- *cutting to the truth*
- *trimming the fat*
- *clipping the competition*
- *sharpening the verdict*

**CNET:**
- *booting up the mainframe*
- *loading the dial-up*
- *connecting to the internet*
- *defragmenting the results*
- *buffering at 56k*

**Amazon:**
- *stacking boxes in the warehouse*
- *checking Jeff's bookshelf*
- *reading between the pages*
- *shipping from Seattle*
- *two-day priming the data*

**Reddit:**
- *diving into the rabbit hole*
- *asking the hive mind*
- *sorting by controversial*
- *waiting for karma*
- *scrolling past the memes*

Tone feel right, or want to push any of these further?

---

**Neil:** For orchestrator, remove "orchestrating the chaos", "assembling the council", "traveling through a wormhole", "calculating the Kessel Run", and add two related to Star Wars. For Wirecutter, make them related to the New York Times since that is their parent company or related to NYC.

**Claude:** **Orchestrator:**
- *opening a portal to dimension C-137*
- *consulting the Citadel of Ricks*
- *crossing to the dark side*
- *collapsing into a black hole*
- *warping through hyperspace*
- *getting schwifty with the data*
- *may the data be with you*
- *activating the Death Star*

**Wirecutter:**
- *hailing a NYC cab*
- *grabbing a slice in Brooklyn*
- *printing the Sunday edition*
- *fact-checking on 8th Ave*
- *filing the story*

Want any changes before we lock UI in?

---

**Neil:** For Wirecutter, make them all related to NY Times, can also relate to their games.

**Claude:** **Wirecutter:**
- *checking the front page*
- *solving the Wordle*
- *publishing the Sunday edition*
- *hunting for the Connections*
- *playing the Mini crossword*

Better? Any other tweaks before we lock UI in?

---

**Neil:** Perfect.

**Claude:** UI dimension fully locked:

- Web app: search-engine style interface
- Telegram: chat-like conversational interface
- Results layout: verdict is the hero, source cards are secondary/expandable
- Progressive loading: source cards populate as agents complete, each with a loading spinner and funny verb tagline
- Verdict: shows a loading state with orchestrator taglines while sources complete, populates last
- Tech stack: Next.js 15 + Tailwind
- Orchestrator taglines: portal/black hole/Rick & Morty/Star Wars themed
- Source taglines:
  - Wirecutter: NYT/NYT Games themed
  - CNET: retro internet/dial-up themed
  - Amazon: Jeff Bezos/bookstore themed
  - Reddit: Reddit culture themed

All four dimensions are locked. Ready to start building?

---

**Neil:** Before we begin, can you think of any other variations of this app that would be helpful to the end user? The main pain point we're trying to solve is gathering and synthesizing research quickly to inform a purchase decision.

**Claude:** Here are the most compelling variations, each solving a distinct slice of the same pain point:

**1. Head-to-head comparison**
*"Should I get the Sony WH-1000XM5 or the Bose QC45?"*
Same agents, but run in parallel for two products and the orchestrator outputs a side-by-side verdict rather than a single Buy/Skip.

**2. Deal validator**
*"This is $189 on Prime Day — is it actually a good deal?"*
Adds a price history source (CamelCamelCamel) to the existing agents. Orchestrator answers: good deal + good product, good deal + mediocre product, bad deal, etc.

**3. Upgrade advisor**
*"I have the AirPods Pro 1st gen — is the 2nd gen worth upgrading to?"*
Same agents but framed around delta — what actually changed, is the improvement worth the cost.

**4. Gift finder**
*"I need a gift for a home cook with a $100 budget"*
Different input paradigm — recipient profile + budget + occasion. Orchestrator resolves to a specific product recommendation then runs the full review.

**5. Bundle advisor**
*"I'm setting up a home office"*
Multi-product — orchestrator recommends a coherent set of products (monitor, chair, keyboard, webcam) and reviews each.

The ones with the highest ROI for lowest added complexity are 1 (compare) and 2 (deal validator) — they reuse almost everything already built.

Which of these resonate, and should any become part of v1?

---

**Neil:** It would also be neat to execute the purchase if the recommendation is a buy.

**Claude:** That's a great idea — closing the loop from research to action. A few things to think through:

1. Purchase channel — Amazon is the most practical since we're already scraping it and they have a well-documented affiliate/API program. Should we limit purchasing to Amazon only, or support others (Best Buy, direct brand sites)?
2. Authorization flow — how should the app handle purchasing on your behalf? Options:
   - Amazon affiliate link — simplest, just redirects you to Amazon with one click, you complete the purchase yourself
   - Amazon Pay / saved credentials — app executes the purchase fully autonomously, no redirect
   - Confirmation step — app prepares the order, shows you a summary, you approve before it fires
3. Scope — is this a "take me to buy it" button, or true autonomous purchasing where the app buys it without you returning to a browser?

The autonomous path is powerful but carries real risk — wrong product variant, wrong quantity, accidental double-purchase. What level of autonomy feels right?

---

**Neil:** Let's add three user links or buttons that map to actions after the orchestrator is complete, the actions will be the same names as what the orchestrator recommends (buy, consider, skip), however, all three will always be present regardless of what the orchestrator recommends. Buy will map to Amazon Pay, but if the product is not found on Amazon then it will mention to search the internet for the nearest retailer. Consider will add the item to a Wishlist, which we'll need to persist with our DB. Skip will clear the current search.

**Claude:** Clean pattern — three actions always present, orchestrator verdict just informs which one the user should pick, not which ones are available.

A few things to nail down:

1. Visual treatment — should the recommended action be visually emphasized (e.g. highlighted button, bold border) while the other two are muted, or all three equal weight?
2. Amazon Pay — this requires a merchant integration with credentials. Do you have an Amazon Pay merchant account, or should we treat "Buy" as a deep link to the Amazon product page instead (simpler, no merchant setup)?
3. Wishlist — since we're already using SQLite, this fits naturally. But what does the wishlist experience look like? Is there a dedicated page to view and manage saved items, or is it just a background save with no UI to browse it yet?
4. Skip on Telegram — clearing a search makes sense in the web app, but in Telegram's conversational flow, should Skip just send a message like "Got it, search cleared" and return to the prompt?

---

**Neil:** 1: visually emphasized. 2: latter option. 3: just a modal that's always accessible by a star icon in the header. 4: yes.

**Claude:** Locked. Full UI dimension:

- Web app: search-engine style interface
- Telegram: chat-like conversational interface
- Results layout: verdict is the hero, source cards are secondary/expandable
- Progressive loading: source cards populate as agents complete with spinner + funny verb tagline
- Verdict: loading state with orchestrator taglines, populates last
- Tech stack: Next.js 15 + Tailwind
- Post-verdict actions: three buttons always present — Buy, Consider, Skip
  - Recommended action visually emphasized, other two muted
  - Buy → deep link to Amazon product page; if not found on Amazon, message to search for nearest retailer
  - Consider → adds to Wishlist, persisted in SQLite
  - Skip → clears search (web) / "Got it, search cleared" (Telegram)
- Wishlist → modal accessible via star icon in header, backed by SQLite
- Loading verbs: curated fixed lists per source + orchestrator

All four dimensions fully locked. Here's the complete app at a glance:

- Sources: Wirecutter, CNET, Amazon, Reddit
- Interfaces: Next.js web app, CLI, Telegram bot
- Agents: Sonnet × 4 (parallel) → Opus orchestrator
- Scraping: Firecrawl Extract (Wirecutter/CNET/Amazon) + Scrape (Reddit)
- Caching: SQLite, 72h TTL
- Actions: Buy / Consider / Skip with Wishlist persistence

Ready to build?

---

**Neil:** Lastly, keep Deal Validator (change name to Deal Score) and Bundle Advisor (change name to Bundler) to a v2 todo list.

**Claude:** Noted. V2 backlog:

- Deal Score — validates whether a current price is actually a good deal, adds price history source (CamelCamelCamel)
- Bundler — recommends and reviews a coherent set of products for a use case (e.g. home office setup)

Now, ready to build?
