# I Built a System That Optimizes AI Agents. Then Realized the Marketing Had Zero Feedback Loops.

*How the architecture that catches lazy AI agents turned into a marketing analytics engine — with zero dependencies and uncomfortable self-awareness.*

---

I've spent months building a system that monitors AI agent performance. It detects idle states, dispatches interventions, tracks scores, escalates on degradation, and auto-creates GitHub Issues when things go south.

377 tests. Zero dependencies. The thing practically runs itself.

And then one day I looked at the marketing for this system and realized: **I had no idea if any of it was working.**

Five social posts. One LinkedIn article. Published and forgotten. No impressions tracked. No engagement measured. No feedback loop. Nothing.

I had built an optimization system for everything *except how I tell people about it*.

## The Irony That Broke Me

Here's the timeline:

1. Build system that detects when AI agents are unproductive
2. Build system that scores agent performance across 5 dimensions
3. Build system that auto-escalates on score degradation
4. Write marketing content about systems 1-3
5. Publish marketing content
6. Never look at it again

Step 6 is the "log-only" pattern I wrote an entire article about. Detection without action. The exact bug I fixed in my AI agent, reproduced perfectly in my own behavior.

My agent used to detect idle states and write them to a journal. I built handler-dispatch to fix that. Then I did the same thing with my marketing: identified the problem ("I should promote this project"), took one action (wrote content), and never closed the loop.

The content equivalent of `actions_proposed: 5, actions_executed: 0`.

## So I Applied My Own Architecture

If the self-eval engine works for code quality — DISCOVER, HEAL, EVALUATE, REPORT — why not marketing?

```
COLLECT → ANALYZE → ADVISE → EXECUTE → EVALUATE → REPEAT
```

Here's what each step actually looks like:

### COLLECT: What content exists?

```bash
make marketing-discover
```

The engine scans `marketing/` for content. It parses multi-post files (splits on `## Post N:` headers), detects articles, skips READMEs, and builds an inventory. Each content item gets fingerprinted with SHA-256 for drift detection.

**Current automation level:** Manual. You run the CLI. But discovery itself is automatic — it finds and parses everything.

### ANALYZE: How good is it?

Five sub-scores, weighted composite:

| Sub-score | Weight | What it measures |
|-----------|--------|------------------|
| Engagement rate | 30% | engagements / impressions (normalized) |
| Reach | 20% | impressions vs channel benchmarks |
| Conversion | 20% | clicks + conversions relative to engagement |
| Content quality | 15% | structural: word count, CTAs, links, code blocks, hashtags |
| Freshness | 15% | decay function: 100 - (days_old * 2) |

Draft content gets scored on quality only. Published content gets the full composite. Grades: A ≥ 90, B ≥ 80, C ≥ 70, D ≥ 60, F < 60.

The channel benchmarks are the clever part. Twitter "good" is 5,000 impressions. LinkedIn "good" is 2,000. Reddit "good" is 1,000. Same score formula, different baselines. So you can compare a tweet against a LinkedIn post without apples-to-oranges noise.

### ADVISE: What should change?

Six recommendation types, generated automatically:

1. **Channel optimization** — "Your LinkedIn posts average 72. Your Twitter posts average 48. Lean into LinkedIn."
2. **Attribute correlation** — "Posts with code blocks score 23% higher. Add more code examples."
3. **Cadence analysis** — "7+ day gap between posts. Publish more often." (Or: "< 2 day gap. Quality over quantity.")
4. **Underperformer diagnosis** — "Post 3 scores 38. Specific problem: no CTA, no links."
5. **Next content suggestion** — "Based on your highest-scoring attributes: write a LinkedIn post with code blocks and a CTA."
6. **10x signal detection** — "Post 2 has 3x the average engagement. Study what made it work and replicate."

Plus intervention tiers, just like the agent performance system:

| Grade | Tier | Action |
|-------|------|--------|
| C | Tier 1 | Refresh weak posts, add CTAs |
| D | Tier 2 | A/B test top posts, switch channels |
| F | Tier 3 | Full content audit, rebuild messaging |

### EXECUTE: Do the thing

This is where it breaks. Execution is manual — a human reads the recommendations and acts on them. No auto-posting. No API integrations with Twitter or LinkedIn.

And honestly? That's fine for now. The bottleneck was never "I can't post fast enough." It was "I have no idea what's working."

### EVALUATE: Track over time

90-entry FIFO history. Grade trends. Score trends. The CI workflow runs weekly and auto-creates a GitHub Issue if the grade drops below B.

```yaml
# .github/workflows/marketing-eval.yml
on:
  schedule:
    - cron: '0 9 * * 1'  # Monday 9 AM UTC
  push:
    paths: ['marketing/**']
```

If your marketing grade drops from B to C, you'll see a GitHub Issue titled "Marketing eval degradation: C (was B)" with specific recommendations. Same pattern as the self-eval engine for code quality.

### REPEAT: The daily review picks it up

The orchestrator's `daily_review()` already includes marketing eval if `marketing/` exists. So every night at 11 PM, alongside code quality and agent performance, you also get a marketing health check.

## What "Zero-Dependency Marketing Analytics" Looks Like

No Google Analytics. No Mixpanel. No Hootsuite. No Buffer.

The entire marketing eval engine runs on Python stdlib. Same as the rest of the system. The metrics come from you — you record impressions, engagements, clicks via CLI:

```bash
python src/__main__.py marketing-metrics \
  --content-id social-posts-post-1 \
  --impressions 5000 \
  --engagements 200 \
  --clicks 45
```

Yes, that's manual data entry. Yes, that's friction. But it means:

- **Zero accounts to create.** No SaaS signups, no OAuth flows, no data sharing.
- **Zero cost.** The analytics platform is your terminal.
- **Zero dependencies.** No API that breaks, no service that gets acquired, no pricing page that changes.
- **Full data ownership.** Your metrics live in `state/marketing_content.json`. Git-tracked if you want. Portable. Yours.

Is this the optimal long-term solution? No. Platform API integrations would eliminate the manual step. But this is the *starting* solution — the one that gets the feedback loop running today, not after a weekend of OAuth debugging.

## Channel Arbitrage: The Discovery I Didn't Expect

Here's something the scoring system surfaced immediately: my content was performing unevenly across platforms, and I had no way to know without cross-platform benchmarks.

The channel benchmarks normalize everything to a common scale. A post with 3,000 LinkedIn impressions scores higher than one with 3,000 Twitter impressions, because LinkedIn's "good" threshold is 2,000 while Twitter's is 5,000.

This means the system can tell you: "Stop spending time on Platform A where your reach is below average. Double down on Platform B where you're outperforming."

Channel arbitrage for content. Found by the same scoring architecture that finds underperforming AI agents.

## The Meta-Lesson

Here's the thing I keep coming back to:

**Optimization systems should optimize themselves.**

The self-optimization repo started with agent monitoring. Then we added cost governance. Then self-eval for code quality. Then marketing eval for content. Each one uses the same pattern:

```
DISCOVER → SCORE → RECOMMEND → REPORT → REPEAT
```

The marketing eval engine isn't a separate project. It's the same architecture applied to a different domain. The scoring weights change. The benchmarks change. The recommendations change. But the loop is identical.

And the uncomfortable truth is: if you build an optimization system and don't apply it to your own marketing, your own processes, your own habits — you haven't learned what the system is teaching you.

My system taught me that detection without action is logging. That proposed actions aren't executed actions. That the gap between knowing and doing is a wiring problem.

Then it caught me making the same mistake with the marketing.

So I fixed the wiring.

---

*The self-optimization framework is open source. 377 tests. Zero dependencies. Now with marketing analytics built in. The system that optimizes AI agents optimizes its own marketing too.*

*Because if your optimization system doesn't optimize itself, who's optimizing the optimizer?*

[Check out the repo](https://github.com/wjlgatech/self-optimization) | Star if this resonated | Share if you know someone shipping content into the void

#MarketingAnalytics #AIAgents #Python #OpenSource #SoftwareEngineering #ContentStrategy #DevTools #SelfImprovement
