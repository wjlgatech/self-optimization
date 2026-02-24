# Social Posts: Marketing Eval Engine

5 promotional posts for the marketing eval engine article and feature. Each is self-contained.

---

## Post 1: The Meta Confession (Twitter/X)

Built a system that optimizes AI agents. Detects idle states. Scores performance. Auto-escalates on degradation. 377 tests. Zero dependencies.

Then I looked at the marketing for this system and realized:

- No impressions tracked
- No engagement measured
- No feedback loop
- Content published and forgotten

I had optimized everything except how I tell people about it.

So I built a marketing eval engine using the same architecture.

The system that optimizes AI agents now optimizes its own marketing.

Full story: [link]

#Python #OpenSource #MarketingAnalytics

---

## Post 2: The Engineer's Marketing Stack (LinkedIn)

Engineers love feedback loops in code but ship marketing content into the void.

I just built a zero-dependency marketing analytics engine in Python stdlib. No Google Analytics. No Hootsuite. No SaaS. Here's what it does:

```
COLLECT → ANALYZE → ADVISE → EXECUTE → EVALUATE → REPEAT
```

5 sub-scores (engagement, reach, conversion, quality, freshness) with channel-normalized benchmarks. A tweet with 3K impressions and a LinkedIn post with 3K impressions get different scores because the baselines are different.

6 recommendation types: channel optimization, attribute correlation, cadence analysis, underperformer diagnosis, content suggestions, 10x signal detection.

Auto-creates GitHub Issues when your content grade drops below B.

The whole thing runs alongside our AI agent monitor. Same weekly CI. Same daily review. Same escalation tiers.

Marketing analytics for people who'd rather `git push` than open a dashboard.

github.com/wjlgatech/self-optimization

#SoftwareEngineering #ContentStrategy #Python #DevTools

---

## Post 3: The Channel Arbitrage Pitch (Reddit/Product Hunt)

Open-sourced a marketing analytics engine that runs on Python stdlib. Zero dependencies. Zero SaaS accounts. Zero cost.

What it does:

- Scans your `marketing/` directory and auto-discovers content (articles, social posts, multi-post files)
- Scores across 5 dimensions: engagement rate, reach, conversion, content quality, freshness
- Normalizes cross-platform with channel benchmarks (LinkedIn 2K "good" vs Twitter 5K "good")
- Detects 10x signals: any post with 3x average engagement gets flagged for replication
- Generates 6 types of recommendations (channel optimization, cadence, underperformer diagnosis, etc.)
- Weekly CI workflow auto-creates GitHub Issues on grade degradation
- Integrates into existing daily review alongside code quality and agent performance metrics

Built it because I had an optimization system for AI agents but was publishing marketing content with zero feedback. The system that scores AI agent performance now scores its own marketing.

CLI-first. State files in JSON. Works offline. Runs in CI.

Repo: github.com/wjlgatech/self-optimization

---

## Post 4: The Hot Take (Twitter/X)

Your content strategy has more dependencies than your codebase.

Google Analytics → requires account + cookie consent
Hootsuite → requires subscription + OAuth
Buffer → requires subscription + OAuth
Mixpanel → requires account + SDK

My marketing analytics: `python src/__main__.py marketing-eval`

Zero dependencies. Channel-normalized scoring. Auto-recommendations. GitHub Issues on degradation.

The bar for "I don't know what's working" just dropped to zero. You have no excuse anymore. Neither do I — that's why I built it.

github.com/wjlgatech/self-optimization

---

## Post 5: The Recursion Joke (Dev Twitter)

The self-optimization system now optimizes its own marketing.

Let me explain:

1. Built a system to catch idle AI agents → worked
2. Built a cost governor to cut AI bills 94.7% → worked
3. Built self-eval to score code quality → worked
4. Wrote marketing content about 1-3 → published it
5. Never measured if the marketing worked → ironic
6. Applied the same DISCOVER → SCORE → RECOMMEND → REPORT pattern to marketing → it works

The marketing eval engine uses the same architecture, same grade scale, same GitHub Issue automation, same daily review integration.

It's optimization all the way down.

Next step: marketing content about the marketing eval engine, evaluated by the marketing eval engine.

We are approaching levels of self-reference that shouldn't be possible in a system with zero dependencies.

github.com/wjlgatech/self-optimization

#Python #AI #OpenSource #RecursionIsNotJustForInterviews
