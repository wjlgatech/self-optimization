"""Tests for the marketing effectiveness monitor."""

import json
import os
from datetime import datetime, timedelta, timezone

import pytest

from marketing_eval import MarketingEvalEngine

# ── Fixtures ────────────────────────────────────────────────────────────


@pytest.fixture()
def engine(tmp_path):
    """Create a MarketingEvalEngine with temp dirs."""
    marketing_dir = tmp_path / "marketing"
    marketing_dir.mkdir()
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    return MarketingEvalEngine(
        project_root=str(tmp_path),
        state_dir=str(state_dir),
        marketing_dir=str(marketing_dir),
    )


@pytest.fixture()
def multi_post_file(engine):
    """Create a multi-post markdown file."""
    content = """# Social Posts

---

## Post 1: The Confession (Twitter/X thread opener)

My AI agent ran for 6 hours and produced absolutely nothing.

Full story: https://example.com

#Python #AI #OpenSource

---

## Post 2: The Engineer's Review (LinkedIn/HN)

Code review finding:

```python
actions_taken = emergency_actions  # BUG
```

Check out the repo: github.com/example

#SoftwareEngineering #Python

---

## Post 3: The Pitch (Product Hunt / Reddit style)

What if your AI agent could fix itself?

Star if this resonated: [link]

#AI #OpenSource
"""
    filepath = os.path.join(engine.marketing_dir, "social-posts.md")
    with open(filepath, "w") as f:
        f.write(content)
    return filepath


@pytest.fixture()
def article_file(engine):
    """Create a single-article markdown file."""
    content = """# I Built a System That Catches My AI Agent

A story about idle detection and self-improvement.

```python
def detect_idle():
    pass
```

Check out the repo: https://github.com/example

#AI #SelfImprovement
"""
    filepath = os.path.join(engine.marketing_dir, "linkedin-article.md")
    with open(filepath, "w") as f:
        f.write(content)
    return filepath


@pytest.fixture()
def readme_file(engine):
    """Create a README.md that should be skipped."""
    filepath = os.path.join(engine.marketing_dir, "README.md")
    with open(filepath, "w") as f:
        f.write("# Marketing\n\nThis is a README.\n")
    return filepath


def _make_published(engine, content_id, metrics=None, days_ago=5):
    """Helper to mark content as published with optional metrics."""
    pub_date = (
        datetime.now(timezone.utc) - timedelta(days=days_ago)
    ).isoformat()
    engine.set_published(content_id, "https://example.com/post", pub_date)
    if metrics:
        engine.update_metrics(content_id, metrics)


# ── TestDiscovery ───────────────────────────────────────────────────────


class TestDiscovery:
    def test_discover_empty_dir(self, engine):
        result = engine.discover_content()
        assert result["total"] == 0
        assert result["published"] == 0
        assert result["draft"] == 0

    def test_discover_multi_post_file(self, engine, multi_post_file):
        result = engine.discover_content()
        assert result["total"] == 3
        # All should be drafts initially
        assert result["draft"] == 3
        assert result["published"] == 0

    def test_discover_article(self, engine, article_file):
        result = engine.discover_content()
        assert result["total"] == 1
        content = result["content"][0]
        assert content["content_type"] == "article"
        assert content["content_id"] == "linkedin-article"

    def test_discover_skips_readme(self, engine, multi_post_file, readme_file):
        result = engine.discover_content()
        # Should find 3 posts but NOT the README
        assert result["total"] == 3
        ids = [c["content_id"] for c in result["content"]]
        assert "README" not in ids

    def test_detect_attributes_code_block(self, engine, multi_post_file):
        result = engine.discover_content()
        # Post 2 has a code block
        post2 = next(c for c in result["content"] if c["content_id"] == "social-posts-post-2")
        assert post2["has_code_block"] is True
        # Post 3 does not
        post3 = next(c for c in result["content"] if c["content_id"] == "social-posts-post-3")
        assert post3["has_code_block"] is False

    def test_detect_attributes_link_and_cta(self, engine, multi_post_file):
        result = engine.discover_content()
        post1 = next(c for c in result["content"] if c["content_id"] == "social-posts-post-1")
        assert post1["has_link"] is True
        assert post1["has_cta"] is True  # "Full story"

    def test_detect_attributes_hashtags(self, engine, multi_post_file):
        result = engine.discover_content()
        post1 = next(c for c in result["content"] if c["content_id"] == "social-posts-post-1")
        assert len(post1["hashtags"]) >= 2

    def test_hash_change_detection(self, engine, multi_post_file):
        # First discover — all new
        result1 = engine.discover_content()
        assert len(result1["new"]) == 3

        # Second discover — no changes
        result2 = engine.discover_content()
        assert len(result2["new"]) == 0
        assert len(result2["modified"]) == 0

        # Modify file — should detect modification
        with open(multi_post_file, "a") as f:
            f.write("\n\n## Post 4: New Post (Twitter/X)\n\nBrand new content!\n")
        result3 = engine.discover_content()
        assert len(result3["new"]) >= 1  # Post 4 is new

    def test_channel_inference(self, engine, multi_post_file):
        result = engine.discover_content()
        post1 = next(c for c in result["content"] if c["content_id"] == "social-posts-post-1")
        assert post1["channel"] == "twitter"
        post2 = next(c for c in result["content"] if c["content_id"] == "social-posts-post-2")
        assert post2["channel"] == "linkedin"
        post3 = next(c for c in result["content"] if c["content_id"] == "social-posts-post-3")
        assert post3["channel"] == "reddit"


# ── TestScoring ─────────────────────────────────────────────────────────


class TestScoring:
    def test_draft_gets_quality_only(self, engine, multi_post_file):
        engine.discover_content()
        content_list = engine._load_content()
        draft = content_list[0]
        score = engine.score_content(draft)
        assert score["is_draft"] is True
        assert score["engagement_rate"] == 0
        assert score["reach"] == 0

    def test_engagement_rate_formula(self, engine):
        metrics = {"impressions": 1000, "engagements": 50}
        rate = engine._score_engagement_rate(metrics)
        assert rate == pytest.approx(50.0)  # 50/1000 * 1000 = 50

    def test_engagement_rate_capped(self, engine):
        metrics = {"impressions": 100, "engagements": 50}
        rate = engine._score_engagement_rate(metrics)
        assert rate == 100.0  # capped

    def test_engagement_rate_zero_impressions(self, engine):
        rate = engine._score_engagement_rate({"impressions": 0, "engagements": 10})
        assert rate == 0.0

    def test_reach_scoring(self, engine):
        # Twitter: good=5000, great=20000
        assert engine._score_reach({"impressions": 0}, "twitter") == 0.0
        assert engine._score_reach({"impressions": 20000}, "twitter") == 100.0
        # At 5000 (good threshold): should be 50
        assert engine._score_reach({"impressions": 5000}, "twitter") == pytest.approx(50.0)

    def test_conversion_formula(self, engine):
        metrics = {"engagements": 100, "clicks": 20, "conversions": 5}
        conv = engine._score_conversion(metrics)
        assert conv == pytest.approx(50.0)  # (20+5)/100 * 200 = 50

    def test_conversion_capped(self, engine):
        metrics = {"engagements": 10, "clicks": 20, "conversions": 5}
        conv = engine._score_conversion(metrics)
        assert conv == 100.0

    def test_content_quality_full_score(self, engine):
        content = {
            "word_count": 100,
            "has_cta": True,
            "has_link": True,
            "has_code_block": True,
            "hashtags": ["#test"],
        }
        assert engine._score_content_quality(content) == 100.0

    def test_freshness_decay(self, engine):
        now = datetime.now(timezone.utc)
        # Published today: 100
        assert engine._score_freshness(now.isoformat()) == pytest.approx(100.0, abs=2)
        # Published 25 days ago: 100 - 25*2 = 50
        old = (now - timedelta(days=25)).isoformat()
        assert engine._score_freshness(old) == pytest.approx(50.0, abs=2)
        # Published 60 days ago: clamped to 0
        very_old = (now - timedelta(days=60)).isoformat()
        assert engine._score_freshness(very_old) == 0.0

    def test_grade_boundaries(self, engine):
        assert engine._score_to_grade(95) == "A"
        assert engine._score_to_grade(90) == "A"
        assert engine._score_to_grade(89.9) == "B"
        assert engine._score_to_grade(80) == "B"
        assert engine._score_to_grade(79.9) == "C"
        assert engine._score_to_grade(70) == "C"
        assert engine._score_to_grade(60) == "D"
        assert engine._score_to_grade(59.9) == "F"

    def test_composite_published_content(self, engine, multi_post_file):
        engine.discover_content()
        cid = "social-posts-post-1"
        pub_date = datetime.now(timezone.utc).isoformat()
        engine.set_published(cid, "https://example.com", pub_date)
        engine.update_metrics(cid, {
            "impressions": 10000,
            "engagements": 500,
            "clicks": 50,
            "conversions": 10,
        })
        content_list = engine._load_content()
        published = next(c for c in content_list if c["content_id"] == cid)
        score = engine.score_content(published)
        assert not score["is_draft"]
        assert score["composite"] > 0


# ── TestRecommendations ─────────────────────────────────────────────────


class TestRecommendations:
    def test_recommendations_empty(self, engine):
        recs = engine.generate_recommendations()
        assert isinstance(recs, list)

    def test_channel_optimization(self, engine, multi_post_file):
        engine.discover_content()
        # Publish posts on different channels with different metrics
        pub_date = datetime.now(timezone.utc).isoformat()
        engine.set_published("social-posts-post-1", "https://x.com/1", pub_date)
        engine.update_metrics("social-posts-post-1", {
            "impressions": 20000, "engagements": 1000, "clicks": 100, "conversions": 20,
        })
        engine.set_published("social-posts-post-2", "https://linkedin.com/2", pub_date)
        engine.update_metrics("social-posts-post-2", {
            "impressions": 500, "engagements": 10, "clicks": 1, "conversions": 0,
        })
        recs = engine.generate_recommendations()
        channel_recs = [r for r in recs if r["type"] == "channel_optimization"]
        assert len(channel_recs) >= 1

    def test_cadence_too_slow(self, engine, multi_post_file):
        engine.discover_content()
        now = datetime.now(timezone.utc)
        # Publish two posts 15 days apart
        engine.set_published(
            "social-posts-post-1", "https://x.com/1",
            (now - timedelta(days=15)).isoformat(),
        )
        engine.set_published(
            "social-posts-post-2", "https://li.com/2",
            now.isoformat(),
        )
        recs = engine.generate_recommendations()
        cadence_recs = [r for r in recs if r["type"] == "cadence"]
        assert len(cadence_recs) >= 1
        assert "publish more often" in cadence_recs[0]["message"]

    def test_cadence_too_fast(self, engine, multi_post_file):
        engine.discover_content()
        now = datetime.now(timezone.utc)
        engine.set_published(
            "social-posts-post-1", "https://x.com/1",
            (now - timedelta(hours=12)).isoformat(),
        )
        engine.set_published(
            "social-posts-post-2", "https://li.com/2",
            now.isoformat(),
        )
        recs = engine.generate_recommendations()
        cadence_recs = [r for r in recs if r["type"] == "cadence"]
        assert len(cadence_recs) >= 1
        assert "quality over quantity" in cadence_recs[0]["message"]

    def test_underperformer_flagged(self, engine, multi_post_file):
        engine.discover_content()
        pub_date = datetime.now(timezone.utc).isoformat()
        engine.set_published("social-posts-post-1", "https://x.com/1", pub_date)
        engine.update_metrics("social-posts-post-1", {
            "impressions": 50, "engagements": 1, "clicks": 0, "conversions": 0,
        })
        recs = engine.generate_recommendations()
        underperformers = [r for r in recs if r["type"] == "underperformer"]
        assert len(underperformers) >= 1

    def test_intervention_tier_mapping(self, engine, multi_post_file):
        engine.discover_content()
        # All drafts with low quality → F grade → tier 3
        recs = engine.generate_recommendations()
        intervention_recs = [r for r in recs if r["type"] == "intervention"]
        # Grade depends on draft quality scores
        assert isinstance(intervention_recs, list)

    def test_next_content_suggestion(self, engine, multi_post_file):
        engine.discover_content()
        pub_date = datetime.now(timezone.utc).isoformat()
        engine.set_published("social-posts-post-1", "https://x.com/1", pub_date)
        engine.update_metrics("social-posts-post-1", {
            "impressions": 10000, "engagements": 500, "clicks": 50, "conversions": 10,
        })
        recs = engine.generate_recommendations()
        next_recs = [r for r in recs if r["type"] == "next_content"]
        assert len(next_recs) >= 1

    def test_10x_signal_detection(self, engine, multi_post_file):
        engine.discover_content()
        # Use an old publish date so freshness doesn't inflate low-performers
        old_date = (datetime.now(timezone.utc) - timedelta(days=60)).isoformat()
        new_date = datetime.now(timezone.utc).isoformat()
        engine.set_published("social-posts-post-1", "https://x.com/1", new_date)
        engine.set_published("social-posts-post-2", "https://li.com/2", old_date)
        engine.set_published("social-posts-post-3", "https://reddit.com/3", old_date)

        # Post 1 gets massively more engagement; others get near-zero
        engine.update_metrics("social-posts-post-1", {
            "impressions": 50000, "engagements": 5000, "clicks": 500, "conversions": 100,
        })
        engine.update_metrics("social-posts-post-2", {
            "impressions": 10, "engagements": 0, "clicks": 0, "conversions": 0,
        })
        engine.update_metrics("social-posts-post-3", {
            "impressions": 10, "engagements": 0, "clicks": 0, "conversions": 0,
        })
        recs = engine.generate_recommendations()
        signals = [r for r in recs if r["type"] == "10x_signal"]
        assert len(signals) >= 1

    def test_attribute_correlation(self, engine, multi_post_file):
        engine.discover_content()
        pub_date = datetime.now(timezone.utc).isoformat()
        # Post 2 has code block, post 1 and 3 do not
        for cid in ["social-posts-post-1", "social-posts-post-2", "social-posts-post-3"]:
            engine.set_published(cid, f"https://x.com/{cid}", pub_date)

        # Give the code-block post much higher engagement
        engine.update_metrics("social-posts-post-2", {
            "impressions": 20000, "engagements": 2000, "clicks": 200, "conversions": 20,
        })
        engine.update_metrics("social-posts-post-1", {
            "impressions": 1000, "engagements": 10, "clicks": 1, "conversions": 0,
        })
        engine.update_metrics("social-posts-post-3", {
            "impressions": 1000, "engagements": 10, "clicks": 1, "conversions": 0,
        })
        recs = engine.generate_recommendations()
        attr_recs = [r for r in recs if r["type"] == "attribute_correlation"]
        assert len(attr_recs) >= 1


# ── TestReport ──────────────────────────────────────────────────────────


class TestReport:
    def test_markdown_report_structure(self, engine, multi_post_file):
        engine.discover_content()
        report = engine.run_full_eval()
        md = engine.generate_markdown_report(report)
        assert "# Marketing Effectiveness Report" in md
        assert "Grade:" in md
        assert "Content Inventory" in md
        assert "Content Scores" in md

    def test_json_report_structure(self, engine, multi_post_file):
        engine.discover_content()
        report = engine.run_full_eval()
        assert "timestamp" in report
        assert "composite_score" in report
        assert "grade" in report
        assert "discovery" in report
        assert "scores" in report
        assert "recommendations" in report
        assert "trend" in report

    def test_trend_section_first_run(self, engine, multi_post_file):
        engine.discover_content()
        report = engine.run_full_eval()
        assert report["trend"]["direction"] == "first_run"

    def test_github_issue_body_healthy(self, engine, multi_post_file):
        engine.discover_content()
        # Force an A grade report
        report = {"grade": "A", "composite_score": 95, "trend": {"direction": "stable"}}
        issue = engine.generate_github_issue_body(report)
        assert issue is None

    def test_github_issue_body_degraded(self, engine, multi_post_file):
        engine.discover_content()
        report = engine.run_full_eval()
        # For drafts the grade will be F (low scores)
        if report["grade"] in ("C", "D", "F"):
            issue = engine.generate_github_issue_body(report)
            assert issue is not None
            assert "marketing eval scored" in issue


# ── TestHistory ─────────────────────────────────────────────────────────


class TestHistory:
    def test_save_and_load(self, engine, multi_post_file):
        engine.discover_content()
        report = engine.run_full_eval()
        history = engine._load_history()
        assert len(history) == 1
        assert history[0]["composite_score"] == report["composite_score"]

    def test_fifo_cap_at_90(self, engine):
        # Manually write 95 entries
        history = [{"composite_score": i, "timestamp": f"t{i}"} for i in range(95)]
        with open(engine._history_file, "w") as f:
            json.dump(history, f)
        # Save one more
        engine._save_eval({"composite_score": 999, "timestamp": "t999"})
        loaded = engine._load_history()
        assert len(loaded) == 90
        assert loaded[-1]["composite_score"] == 999

    def test_trend_summary_insufficient(self, engine):
        summary = engine.get_trend_summary()
        assert summary["trend"] == "insufficient_data"

    def test_trend_summary_with_data(self, engine):
        history = [
            {"composite_score": 50, "timestamp": "t1"},
            {"composite_score": 60, "timestamp": "t2"},
            {"composite_score": 70, "timestamp": "t3"},
        ]
        with open(engine._history_file, "w") as f:
            json.dump(history, f)
        summary = engine.get_trend_summary()
        assert summary["evaluations"] == 3
        assert summary["latest_score"] == 70
        assert summary["best_score"] == 70
        assert summary["worst_score"] == 50
        assert summary["average_score"] == pytest.approx(60.0)


# ── TestMetricsEntry ────────────────────────────────────────────────────


class TestMetricsEntry:
    def test_update_metrics(self, engine, multi_post_file):
        engine.discover_content()
        result = engine.update_metrics("social-posts-post-1", {
            "impressions": 5000, "engagements": 200,
        })
        assert result["success"] is True
        # Verify persisted
        content = engine._load_content()
        post = next(c for c in content if c["content_id"] == "social-posts-post-1")
        assert post["metrics"]["impressions"] == 5000

    def test_set_published(self, engine, multi_post_file):
        engine.discover_content()
        result = engine.set_published(
            "social-posts-post-1", "https://twitter.com/post/1", "2025-06-01T00:00:00+00:00"
        )
        assert result["success"] is True
        assert result["status"] == "published"
        content = engine._load_content()
        post = next(c for c in content if c["content_id"] == "social-posts-post-1")
        assert post["status"] == "published"
        assert post["url"] == "https://twitter.com/post/1"

    def test_unknown_id_error(self, engine, multi_post_file):
        engine.discover_content()
        result = engine.update_metrics("nonexistent-id", {"impressions": 100})
        assert result["success"] is False
        assert "Unknown" in result["error"]

    def test_partial_update(self, engine, multi_post_file):
        engine.discover_content()
        engine.update_metrics("social-posts-post-1", {"impressions": 5000})
        engine.update_metrics("social-posts-post-1", {"engagements": 200})
        content = engine._load_content()
        post = next(c for c in content if c["content_id"] == "social-posts-post-1")
        assert post["metrics"]["impressions"] == 5000
        assert post["metrics"]["engagements"] == 200
