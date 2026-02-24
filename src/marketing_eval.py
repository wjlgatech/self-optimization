"""Marketing effectiveness monitor: discovers, scores, recommends, and reports.

Applies the same DISCOVER → SCORE → RECOMMEND → REPORT pattern used by
SelfEvalEngine to marketing content in the marketing/ directory.

Four loops:
  1. DISCOVER — scan marketing/**/*.md, parse multi-post files, detect attributes
  2. SCORE — weighted composite per-content and aggregate scoring (0-100)
  3. RECOMMEND — rule-based improvement recommendations (LLM-enhanced when available)
  4. REPORT — generate markdown, track trends, assign grade, create GitHub issues
"""

import glob
import hashlib
import json
import logging
import os
import re
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

# Grade thresholds (composite score 0-100)
GRADE_THRESHOLDS = {"A": 90, "B": 80, "C": 70, "D": 60}

# Channel benchmarks for reach normalization (configurable)
CHANNEL_BENCHMARKS: dict[str, dict[str, int]] = {
    "twitter": {"good": 5000, "great": 20000},
    "linkedin": {"good": 2000, "great": 10000},
    "reddit": {"good": 1000, "great": 5000},
}

# Word count range for content quality scoring
IDEAL_WORD_COUNT = {"min": 50, "max": 500}

# Channel inference patterns
CHANNEL_PATTERNS: dict[str, list[str]] = {
    "twitter": ["twitter", "x thread", "twitter/x", "dev twitter"],
    "linkedin": ["linkedin", "hn", "hacker news"],
    "reddit": ["reddit", "product hunt"],
}


class MarketingEvalEngine:
    """Evaluates marketing content effectiveness using the self-eval pattern."""

    def __init__(
        self,
        project_root: str = "",
        state_dir: str = "",
        marketing_dir: str = "",
    ) -> None:
        if not project_root:
            project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        if not state_dir:
            state_dir = os.path.join(project_root, "state")
        if not marketing_dir:
            marketing_dir = os.path.join(project_root, "marketing")

        self.project_root = project_root
        self.state_dir = state_dir
        self.marketing_dir = marketing_dir
        os.makedirs(state_dir, exist_ok=True)

        self._history_file = os.path.join(state_dir, "marketing_eval_history.json")
        self._content_file = os.path.join(state_dir, "marketing_content.json")
        self._hash_file = os.path.join(state_dir, "marketing_content_hashes.json")

    # ── DISCOVER ────────────────────────────────────────────────────────

    def discover_content(self) -> dict[str, Any]:
        """Scan marketing/**/*.md, parse multi-post files, detect attributes.

        Returns: {"total": N, "published": N, "draft": N, "new": [...],
                  "modified": [...], "content": [...]}
        """
        if not os.path.isdir(self.marketing_dir):
            return {
                "total": 0, "published": 0, "draft": 0,
                "new": [], "modified": [], "content": [],
            }

        # Find all markdown files
        pattern = os.path.join(self.marketing_dir, "**", "*.md")
        md_files = sorted(glob.glob(pattern, recursive=True))

        # Load previous hashes for change detection
        previous_hashes = self._load_hashes()
        current_hashes: dict[str, str] = {}

        # Load existing content records (preserves metrics/status)
        existing_content = self._load_content()
        existing_by_id: dict[str, dict[str, Any]] = {
            c["content_id"]: c for c in existing_content
        }

        all_content: list[dict[str, Any]] = []
        new_ids: list[str] = []
        modified_ids: list[str] = []

        for filepath in md_files:
            # Skip README files
            if os.path.basename(filepath).lower() == "readme.md":
                continue

            try:
                with open(filepath, "rb") as f:
                    raw = f.read()
                file_hash = hashlib.sha256(raw).hexdigest()[:16]
                text = raw.decode("utf-8", errors="replace")
            except OSError as e:
                logger.warning("Failed to read %s: %s", filepath, e)
                continue

            rel_path = os.path.relpath(filepath, self.project_root)
            current_hashes[rel_path] = file_hash

            # Detect if this is a multi-post file or single article
            items = self._parse_content_items(filepath, rel_path, text)

            for item in items:
                cid = item["content_id"]

                # Check for change detection
                prev_hash = previous_hashes.get(cid)
                if prev_hash is None:
                    new_ids.append(cid)
                elif prev_hash != item["hash"]:
                    modified_ids.append(cid)

                # Merge with existing record (preserves metrics, status, url)
                if cid in existing_by_id:
                    existing = existing_by_id[cid]
                    item["metrics"] = existing.get("metrics", {})
                    item["status"] = existing.get("status", "draft")
                    item["url"] = existing.get("url", "")
                    item["published_date"] = existing.get("published_date", "")
                else:
                    item["metrics"] = {}
                    item["status"] = "draft"
                    item["url"] = ""
                    item["published_date"] = ""

                all_content.append(item)

            # Track per-item hashes
            for item in items:
                current_hashes[item["content_id"]] = item["hash"]

        # Save updated content and hashes
        self._save_content(all_content)
        self._save_hashes(current_hashes)

        published = sum(1 for c in all_content if c["status"] == "published")
        draft = sum(1 for c in all_content if c["status"] == "draft")

        return {
            "total": len(all_content),
            "published": published,
            "draft": draft,
            "new": new_ids,
            "modified": modified_ids,
            "content": all_content,
        }

    def _parse_content_items(
        self, filepath: str, rel_path: str, text: str
    ) -> list[dict[str, Any]]:
        """Parse a markdown file into content items (handles multi-post files)."""
        items: list[dict[str, Any]] = []

        # Detect multi-post format: ## Post N: Title
        post_pattern = re.compile(r"^## Post \d+:\s*(.+)", re.MULTILINE)
        post_matches = list(post_pattern.finditer(text))

        if post_matches:
            # Multi-post file — split on headers
            base_name = os.path.splitext(os.path.basename(filepath))[0]
            for i, match in enumerate(post_matches):
                start = match.start()
                end = post_matches[i + 1].start() if i + 1 < len(post_matches) else len(text)
                section = text[start:end].strip()
                title = match.group(1).strip()
                post_num = i + 1
                content_id = f"{base_name}-post-{post_num}"
                body = section[match.end() - match.start():].strip()

                items.append(self._build_content_item(
                    content_id=content_id,
                    title=title,
                    body=body,
                    source_file=rel_path,
                    content_type="social_post",
                ))
        else:
            # Single content item (article)
            base_name = os.path.splitext(os.path.basename(filepath))[0]
            # Extract title from first H1
            h1_match = re.search(r"^#\s+(.+)", text, re.MULTILINE)
            title = h1_match.group(1).strip() if h1_match else base_name
            items.append(self._build_content_item(
                content_id=base_name,
                title=title,
                body=text,
                source_file=rel_path,
                content_type="article",
            ))

        return items

    def _build_content_item(
        self,
        content_id: str,
        title: str,
        body: str,
        source_file: str,
        content_type: str,
    ) -> dict[str, Any]:
        """Build a content item dict with detected attributes."""
        word_count = len(body.split())
        has_code_block = "```" in body
        has_link = bool(re.search(r"https?://|github\.com|\[link\]", body))
        has_cta = bool(re.search(
            r"(check out|star if|share|link|repo:|full (?:story|article))",
            body, re.IGNORECASE,
        ))
        hashtags = re.findall(r"#\w+", body)
        channel = self._infer_channel(title)
        content_hash = hashlib.sha256(body.encode("utf-8")).hexdigest()[:16]

        return {
            "content_id": content_id,
            "title": title,
            "source_file": source_file,
            "content_type": content_type,
            "word_count": word_count,
            "has_code_block": has_code_block,
            "has_link": has_link,
            "has_cta": has_cta,
            "hashtags": hashtags,
            "channel": channel,
            "hash": content_hash,
        }

    def _infer_channel(self, title: str) -> str:
        """Infer channel from header text."""
        title_lower = title.lower()
        for channel, patterns in CHANNEL_PATTERNS.items():
            for pattern in patterns:
                if pattern in title_lower:
                    return channel
        return "unknown"

    # ── SCORE ───────────────────────────────────────────────────────────

    def score_content(self, content: dict[str, Any]) -> dict[str, Any]:
        """Score a single content item. Returns sub-scores and composite."""
        metrics = content.get("metrics", {})
        is_published = content.get("status") == "published"

        # Content quality (always available, rule-based)
        quality = self._score_content_quality(content)

        if not is_published or not metrics:
            # Drafts get content_quality only
            return {
                "content_id": content["content_id"],
                "engagement_rate": 0,
                "reach": 0,
                "conversion": 0,
                "content_quality": quality,
                "freshness": 0,
                "composite": quality * 0.15,
                "is_draft": True,
            }

        # Published content — full scoring
        engagement = self._score_engagement_rate(metrics)
        reach = self._score_reach(metrics, content.get("channel", "unknown"))
        conversion = self._score_conversion(metrics)
        freshness = self._score_freshness(content.get("published_date", ""))

        composite = (
            engagement * 0.30
            + reach * 0.20
            + conversion * 0.20
            + quality * 0.15
            + freshness * 0.15
        )

        return {
            "content_id": content["content_id"],
            "engagement_rate": round(engagement, 1),
            "reach": round(reach, 1),
            "conversion": round(conversion, 1),
            "content_quality": round(quality, 1),
            "freshness": round(freshness, 1),
            "composite": round(composite, 1),
            "is_draft": False,
        }

    def _score_engagement_rate(self, metrics: dict[str, Any]) -> float:
        """engagements / impressions * 1000, capped at 100."""
        impressions: int = int(metrics.get("impressions", 0))
        engagements: int = int(metrics.get("engagements", 0))
        if impressions <= 0:
            return 0.0
        return min(100.0, engagements / impressions * 1000)

    def _score_reach(self, metrics: dict[str, Any], channel: str) -> float:
        """Impressions normalized against channel benchmarks."""
        impressions: int = int(metrics.get("impressions", 0))
        benchmarks = CHANNEL_BENCHMARKS.get(channel, {"good": 2000, "great": 10000})
        good = benchmarks["good"]
        great = benchmarks["great"]
        if impressions <= 0:
            return 0.0
        if impressions >= great:
            return 100.0
        if impressions >= good:
            return 50.0 + 50.0 * (impressions - good) / max(1, great - good)
        return 50.0 * impressions / max(1, good)

    def _score_conversion(self, metrics: dict[str, Any]) -> float:
        """(clicks + conversions) / engagements * 200, capped at 100."""
        engagements: int = int(metrics.get("engagements", 0))
        clicks: int = int(metrics.get("clicks", 0))
        conversions: int = int(metrics.get("conversions", 0))
        if engagements <= 0:
            return 0.0
        return min(100.0, (clicks + conversions) / engagements * 200)

    def _score_content_quality(self, content: dict[str, Any]) -> float:
        """Rule-based quality score: 20 pts each for 5 attributes."""
        score = 0.0
        wc = content.get("word_count", 0)
        if IDEAL_WORD_COUNT["min"] <= wc <= IDEAL_WORD_COUNT["max"]:
            score += 20
        if content.get("has_cta"):
            score += 20
        if content.get("has_link"):
            score += 20
        if content.get("has_code_block"):
            score += 20
        if content.get("hashtags"):
            score += 20
        return score

    def _score_freshness(self, published_date: str) -> float:
        """max(0, 100 - days_since_published * 2)."""
        if not published_date:
            return 0.0
        try:
            pub = datetime.fromisoformat(published_date.replace("Z", "+00:00"))
            now = datetime.now(timezone.utc)
            days = (now - pub).days
            return max(0.0, 100.0 - days * 2)
        except (ValueError, TypeError):
            return 0.0

    def score_all(self) -> dict[str, Any]:
        """Score all content. Returns per-content scores and aggregate."""
        content_list = self._load_content()
        scores: list[dict[str, Any]] = []
        published_scores: list[float] = []

        for content in content_list:
            s = self.score_content(content)
            scores.append(s)
            if not s["is_draft"]:
                published_scores.append(s["composite"])

        # Aggregate: weighted average of published content (drafts contribute quality only)
        if published_scores:
            aggregate = sum(published_scores) / len(published_scores)
        else:
            # All drafts — use quality-only scores
            draft_scores = [s["composite"] for s in scores]
            aggregate = sum(draft_scores) / max(1, len(draft_scores))

        grade = self._score_to_grade(aggregate)

        return {
            "scores": scores,
            "aggregate_score": round(aggregate, 1),
            "grade": grade,
            "published_count": len(published_scores),
            "draft_count": len(scores) - len(published_scores),
        }

    def _score_to_grade(self, score: float) -> str:
        """Convert composite score to letter grade."""
        for grade, threshold in GRADE_THRESHOLDS.items():
            if score >= threshold:
                return grade
        return "F"

    # ── RECOMMEND ───────────────────────────────────────────────────────

    def generate_recommendations(self) -> list[dict[str, Any]]:
        """Generate rule-based improvement recommendations."""
        content_list = self._load_content()
        scores_data = self.score_all()
        scores = scores_data["scores"]
        recommendations: list[dict[str, Any]] = []

        # Build score lookup
        score_by_id: dict[str, dict[str, Any]] = {
            s["content_id"]: s for s in scores
        }

        # 1. Channel optimization — compare per-channel average scores
        channel_scores: dict[str, list[float]] = {}
        for content in content_list:
            cid = content["content_id"]
            ch = content.get("channel", "unknown")
            s = score_by_id.get(cid, {})
            if not s.get("is_draft", True):
                channel_scores.setdefault(ch, []).append(s.get("composite", 0))

        if len(channel_scores) >= 2:
            channel_avgs = {
                ch: sum(v) / len(v) for ch, v in channel_scores.items() if v
            }
            if channel_avgs:
                best_ch = max(channel_avgs, key=lambda k: channel_avgs[k])
                worst_ch = min(channel_avgs, key=lambda k: channel_avgs[k])
                if channel_avgs[best_ch] - channel_avgs[worst_ch] > 10:
                    recommendations.append({
                        "type": "channel_optimization",
                        "priority": "high",
                        "message": (
                            f"Shift content to {best_ch} "
                            f"(avg score {channel_avgs[best_ch]:.0f}) "
                            f"over {worst_ch} "
                            f"(avg score {channel_avgs[worst_ch]:.0f})"
                        ),
                    })

        # 2. Content attribute correlation
        published_with_scores = [
            (c, score_by_id.get(c["content_id"], {}))
            for c in content_list
            if c.get("status") == "published"
        ]
        if len(published_with_scores) >= 2:
            for attr in ("has_code_block", "has_cta", "has_link"):
                with_attr = [
                    s.get("composite", 0)
                    for c, s in published_with_scores if c.get(attr)
                ]
                without_attr = [
                    s.get("composite", 0)
                    for c, s in published_with_scores if not c.get(attr)
                ]
                if with_attr and without_attr:
                    avg_with = sum(with_attr) / len(with_attr)
                    avg_without = sum(without_attr) / len(without_attr)
                    if avg_with > avg_without * 1.3:
                        label = attr.replace("has_", "").replace("_", " ")
                        recommendations.append({
                            "type": "attribute_correlation",
                            "priority": "medium",
                            "message": (
                                f"Posts with {label}s score "
                                f"{avg_with / max(0.01, avg_without):.1f}x higher — "
                                f"include {label}s in future content"
                            ),
                        })

        # 3. Cadence analysis
        published_dates = []
        for c in content_list:
            if c.get("published_date"):
                try:
                    dt = datetime.fromisoformat(
                        c["published_date"].replace("Z", "+00:00")
                    )
                    published_dates.append(dt)
                except (ValueError, TypeError):
                    pass

        if len(published_dates) >= 2:
            published_dates.sort()
            gaps = [
                (published_dates[i + 1] - published_dates[i]).days
                for i in range(len(published_dates) - 1)
            ]
            avg_gap = sum(gaps) / len(gaps)
            if avg_gap > 7:
                recommendations.append({
                    "type": "cadence",
                    "priority": "medium",
                    "message": (
                        f"Average gap between posts is {avg_gap:.0f} days — "
                        f"publish more often (target: weekly)"
                    ),
                })
            elif avg_gap < 2:
                recommendations.append({
                    "type": "cadence",
                    "priority": "low",
                    "message": (
                        f"Average gap is only {avg_gap:.1f} days — "
                        f"consider quality over quantity"
                    ),
                })

        # 4. Underperformer flags — any content < 40 composite
        for s in scores:
            if not s.get("is_draft") and s.get("composite", 0) < 40:
                content_rec = next(
                    (c for c in content_list if c["content_id"] == s["content_id"]),
                    None,
                )
                if content_rec:
                    # Diagnose why
                    weak = []
                    if s.get("engagement_rate", 0) < 20:
                        weak.append("low engagement")
                    if s.get("reach", 0) < 20:
                        weak.append("low reach")
                    if s.get("conversion", 0) < 20:
                        weak.append("low conversion")
                    if s.get("freshness", 0) < 20:
                        weak.append("stale content")
                    diagnosis = ", ".join(weak) if weak else "overall low performance"
                    recommendations.append({
                        "type": "underperformer",
                        "priority": "high",
                        "content_id": s["content_id"],
                        "message": (
                            f"'{content_rec.get('title', s['content_id'])}' "
                            f"scored {s['composite']:.0f} — {diagnosis}"
                        ),
                    })

        # 5. Next content suggestion
        if published_with_scores:
            best = max(published_with_scores, key=lambda x: x[1].get("composite", 0))
            best_content, best_score = best
            best_ch = best_content.get("channel", "unknown")
            attrs = []
            if best_content.get("has_code_block"):
                attrs.append("code snippets")
            if best_content.get("has_cta"):
                attrs.append("clear CTAs")
            if best_content.get("has_link"):
                attrs.append("links")
            attr_str = ", ".join(attrs) if attrs else "the same style"
            recommendations.append({
                "type": "next_content",
                "priority": "medium",
                "message": (
                    f"Next post: target {best_ch} with {attr_str} — "
                    f"your best performer '{best_content.get('title', '')}' "
                    f"scored {best_score.get('composite', 0):.0f}"
                ),
            })

        # 6. 10x signal detection — any post with engagement > 3x average of others
        published_composites = [
            s.get("composite", 0)
            for s in scores if not s.get("is_draft")
        ]
        if len(published_composites) >= 2:
            for s in scores:
                if s.get("is_draft"):
                    continue
                this_score = s.get("composite", 0)
                others = [c for c in published_composites if c != this_score]
                if not others:
                    others = published_composites  # all same score, use full list
                avg_others = sum(others) / len(others)
                if avg_others > 0 and this_score > avg_others * 3:
                    content_rec = next(
                        (c for c in content_list if c["content_id"] == s["content_id"]),
                        None,
                    )
                    if content_rec:
                        recommendations.append({
                            "type": "10x_signal",
                            "priority": "critical",
                            "content_id": s["content_id"],
                            "message": (
                                f"'{content_rec.get('title', s['content_id'])}' "
                                f"scored {s['composite']:.0f} "
                                f"(3x+ above average {avg_others:.0f}) — "
                                f"replicate this messaging style"
                            ),
                        })

        # Intervention tier based on grade
        grade = scores_data["grade"]
        if grade == "C":
            recommendations.append({
                "type": "intervention",
                "tier": 1,
                "priority": "medium",
                "message": "Grade C: refresh weak posts, add CTAs to those missing them",
            })
        elif grade == "D":
            recommendations.append({
                "type": "intervention",
                "tier": 2,
                "priority": "high",
                "message": "Grade D: A/B test top posts, consider switching channels",
            })
        elif grade == "F":
            recommendations.append({
                "type": "intervention",
                "tier": 3,
                "priority": "critical",
                "message": "Grade F: full content audit needed, rebuild messaging strategy",
            })

        return recommendations

    # ── METRICS ENTRY ───────────────────────────────────────────────────

    def update_metrics(
        self, content_id: str, metrics: dict[str, Any]
    ) -> dict[str, Any]:
        """Update metrics for a content item. Partial updates OK."""
        content_list = self._load_content()
        found = False
        for item in content_list:
            if item["content_id"] == content_id:
                existing_metrics = item.get("metrics", {})
                existing_metrics.update(metrics)
                item["metrics"] = existing_metrics
                found = True
                break

        if not found:
            return {"success": False, "error": f"Unknown content_id: {content_id}"}

        self._save_content(content_list)
        return {"success": True, "content_id": content_id, "metrics": metrics}

    def set_published(
        self,
        content_id: str,
        url: str,
        date: str = "",
    ) -> dict[str, Any]:
        """Mark content as published with URL and optional date."""
        if not date:
            date = datetime.now(timezone.utc).isoformat()

        content_list = self._load_content()
        found = False
        for item in content_list:
            if item["content_id"] == content_id:
                item["status"] = "published"
                item["url"] = url
                item["published_date"] = date
                found = True
                break

        if not found:
            return {"success": False, "error": f"Unknown content_id: {content_id}"}

        self._save_content(content_list)
        return {
            "success": True,
            "content_id": content_id,
            "status": "published",
            "url": url,
            "published_date": date,
        }

    # ── REPORT ──────────────────────────────────────────────────────────

    def run_full_eval(self) -> dict[str, Any]:
        """Run full marketing evaluation: discover + score + recommend + report."""
        now = datetime.now(timezone.utc).isoformat()

        # Discover
        discovery = self.discover_content()

        # Score
        scoring = self.score_all()

        # Recommend
        recommendations = self.generate_recommendations()

        report: dict[str, Any] = {
            "timestamp": now,
            "discovery": {
                "total": discovery["total"],
                "published": discovery["published"],
                "draft": discovery["draft"],
                "new": discovery["new"],
                "modified": discovery["modified"],
            },
            "composite_score": scoring["aggregate_score"],
            "grade": scoring["grade"],
            "scores": scoring["scores"],
            "recommendations": recommendations,
        }

        # Trend (compare to last eval)
        previous = self._load_last_eval()
        if previous:
            prev_score = previous.get("composite_score", 0)
            report["trend"] = {
                "previous_score": prev_score,
                "delta": round(scoring["aggregate_score"] - prev_score, 1),
                "direction": "improving" if scoring["aggregate_score"] > prev_score + 1
                else "declining" if scoring["aggregate_score"] < prev_score - 1
                else "stable",
                "previous_timestamp": previous.get("timestamp", ""),
            }
        else:
            report["trend"] = {"previous_score": None, "direction": "first_run"}

        # Save to history
        self._save_eval(report)

        return report

    def generate_markdown_report(self, report: dict[str, Any]) -> str:
        """Generate a human-readable markdown marketing report."""
        lines: list[str] = []
        grade = report.get("grade", "?")
        score = report.get("composite_score", 0)
        ts = report.get("timestamp", "")

        lines.append("# Marketing Effectiveness Report")
        lines.append("")
        lines.append(f"**Grade: {grade}** ({score}/100) | {ts}")
        lines.append("")

        # Discovery summary
        disc = report.get("discovery", {})
        lines.append("## Content Inventory")
        lines.append("")
        lines.append(
            f"- **Total**: {disc.get('total', 0)} items "
            f"({disc.get('published', 0)} published, "
            f"{disc.get('draft', 0)} drafts)"
        )
        new = disc.get("new", [])
        if new:
            lines.append(f"- **New**: {', '.join(new)}")
        modified = disc.get("modified", [])
        if modified:
            lines.append(f"- **Modified**: {', '.join(modified)}")

        # Per-content scores
        scores = report.get("scores", [])
        if scores:
            lines.append("")
            lines.append("## Content Scores")
            lines.append("")
            lines.append(
                "| Content | Engagement | Reach | Conversion "
                "| Quality | Freshness | **Composite** |"
            )
            lines.append(
                "|---------|-----------|-------|-----------|"
                "---------|-----------|---------------|"
            )
            for s in scores:
                status = "DRAFT" if s.get("is_draft") else ""
                lines.append(
                    f"| {s['content_id']} {status} "
                    f"| {s.get('engagement_rate', 0)} "
                    f"| {s.get('reach', 0)} "
                    f"| {s.get('conversion', 0)} "
                    f"| {s.get('content_quality', 0)} "
                    f"| {s.get('freshness', 0)} "
                    f"| **{s.get('composite', 0)}** |"
                )

        # Trend
        trend = report.get("trend", {})
        if trend.get("previous_score") is not None:
            lines.append("")
            lines.append("## Trend")
            lines.append("")
            delta = trend.get("delta", 0)
            arrow = "+" if delta > 0 else ""
            lines.append(
                f"- **Direction**: {trend.get('direction', '?')} "
                f"({arrow}{delta} from {trend.get('previous_score')})"
            )

        # Recommendations
        recs = report.get("recommendations", [])
        if recs:
            lines.append("")
            lines.append("## Recommendations")
            lines.append("")
            for r in recs:
                priority = r.get("priority", "medium")
                lines.append(f"- [{priority.upper()}] {r.get('message', '')}")

        lines.append("")
        lines.append(
            f"---\n*Generated by marketing-eval at {ts}*"
        )

        return "\n".join(lines) + "\n"

    def generate_github_issue_body(self, report: dict[str, Any]) -> str | None:
        """Generate a GitHub Issue body if grade is C/D/F. Returns None if healthy."""
        grade = report.get("grade", "?")
        if grade in ("A", "B"):
            return None

        body = self.generate_markdown_report(report)
        trend = report.get("trend", {})
        direction = trend.get("direction", "?")

        header = (
            f"The marketing eval scored **{grade}** "
            f"({report.get('composite_score', 0)}/100), "
            f"trend: {direction}.\n\n"
            "This issue was created automatically by the marketing-eval workflow. "
            "Review the report below and close when resolved.\n\n---\n\n"
        )
        return header + body

    # ── HISTORY ─────────────────────────────────────────────────────────

    def _load_last_eval(self) -> dict[str, Any] | None:
        """Load the most recent evaluation from history."""
        history = self._load_history()
        return history[-1] if history else None

    def _load_history(self) -> list[dict[str, Any]]:
        """Load evaluation history."""
        try:
            with open(self._history_file, encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, list) else []
        except (OSError, json.JSONDecodeError):
            return []

    def _save_eval(self, report: dict[str, Any]) -> None:
        """Append evaluation to history (capped at 90 entries)."""
        history = self._load_history()
        history.append(report)
        history = history[-90:]
        try:
            tmp = self._history_file + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(history, f, indent=2, default=str)
            os.replace(tmp, self._history_file)
        except OSError as e:
            logger.warning("Failed to save marketing eval history: %s", e)

    def get_trend_summary(self) -> dict[str, Any]:
        """Summarize trends from evaluation history."""
        history = self._load_history()
        if len(history) < 2:
            return {"evaluations": len(history), "trend": "insufficient_data"}

        scores = [h.get("composite_score", 0) for h in history]
        return {
            "evaluations": len(history),
            "latest_score": scores[-1],
            "best_score": max(scores),
            "worst_score": min(scores),
            "average_score": round(sum(scores) / len(scores), 1),
            "scores_last_7": scores[-7:],
        }

    # ── STATE PERSISTENCE ───────────────────────────────────────────────

    def _load_content(self) -> list[dict[str, Any]]:
        """Load content records from state."""
        try:
            with open(self._content_file, encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, list) else []
        except (OSError, json.JSONDecodeError):
            return []

    def _save_content(self, content: list[dict[str, Any]]) -> None:
        """Save content records to state."""
        try:
            tmp = self._content_file + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(content, f, indent=2, default=str)
            os.replace(tmp, self._content_file)
        except OSError as e:
            logger.warning("Failed to save marketing content: %s", e)

    def _load_hashes(self) -> dict[str, str]:
        """Load content hashes for change detection."""
        try:
            with open(self._hash_file, encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, dict) else {}
        except (OSError, json.JSONDecodeError):
            return {}

    def _save_hashes(self, hashes: dict[str, str]) -> None:
        """Save content hashes."""
        try:
            tmp = self._hash_file + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(hashes, f, indent=2)
            os.replace(tmp, self._hash_file)
        except OSError as e:
            logger.warning("Failed to save marketing content hashes: %s", e)
