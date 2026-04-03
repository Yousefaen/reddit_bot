import math
import time
from dataclasses import dataclass, field
from collections import Counter


@dataclass
class SubredditReport:
    name: str
    title: str
    subscribers: int
    low_sample: bool
    post_count: int

    # Raw metrics (0-100 normalized where applicable)
    avg_score: float
    score_consistency: float       # 1 - coefficient_of_variation (capped)
    avg_upvote_ratio: float        # 0.0–1.0
    engagement_ratio: float        # comments/score normalized
    community_diversity: float     # unique_authors / total_posts
    freshness: float               # fraction of posts < 7 days old
    original_content: float        # 1 - crosspost_fraction

    # Aggregated
    weighted_score: float          # 0–100
    grade: str                     # A/B/C/D/F

    # Extra breakdowns for display
    content_type_dist: dict = field(default_factory=dict)   # type -> count
    top_flairs: list = field(default_factory=list)          # [(flair, count), ...]
    score_distribution: dict = field(default_factory=dict)  # bucket -> count


# Metric weights — must sum to 1.0
WEIGHTS = {
    "avg_score": 0.25,
    "score_consistency": 0.15,
    "avg_upvote_ratio": 0.15,
    "engagement_ratio": 0.15,
    "community_diversity": 0.15,
    "freshness": 0.10,
    "original_content": 0.05,
}


def _log_normalize(value: float, reference: float = 1000.0) -> float:
    """Normalize a score using log scale. reference is the 'good' baseline."""
    if value <= 0:
        return 0.0
    return min(100.0, (math.log1p(value) / math.log1p(reference)) * 100)


def _coefficient_of_variation(values: list[float]) -> float:
    if not values:
        return 1.0
    mean = sum(values) / len(values)
    if mean == 0:
        return 1.0
    variance = sum((v - mean) ** 2 for v in values) / len(values)
    return math.sqrt(variance) / mean


def _classify_post_type(post) -> str:
    if post.is_self:
        return "self-text"
    url = post.url.lower()
    if any(ext in url for ext in (".jpg", ".jpeg", ".png", ".gif", ".webp", "imgur.com", "i.redd.it")):
        return "image"
    if any(ext in url for ext in ("youtube.com", "youtu.be", "v.redd.it", ".mp4", ".webm")):
        return "video"
    return "link"


def _score_bucket(score: int) -> str:
    if score < 10:
        return "<10"
    elif score < 100:
        return "10-99"
    elif score < 1000:
        return "100-999"
    elif score < 10000:
        return "1k-9.9k"
    else:
        return "10k+"


def analyze_subreddit(posts: list, sub_meta: dict) -> SubredditReport:
    now = time.time()

    scores = [max(1, p.score) for p in posts]
    upvote_ratios = [p.upvote_ratio for p in posts if hasattr(p, "upvote_ratio")]
    comment_counts = [p.num_comments for p in posts]
    authors = [str(p.author) for p in posts if p.author is not None]
    ages_days = [(now - p.created_utc) / 86400 for p in posts]
    crosspost_count = sum(1 for p in posts if getattr(p, "crosspost_parent", None))

    n = len(posts)

    # --- Metric: avg_score (log-normalized, 1000 upvotes = 100 pts) ---
    avg_raw_score = sum(scores) / n if n else 0
    avg_score_norm = _log_normalize(avg_raw_score, reference=1000.0)

    # --- Metric: score_consistency (lower CV = more consistent) ---
    cv = _coefficient_of_variation(scores)
    score_consistency = max(0.0, min(1.0, 1.0 - cv / 3.0)) * 100  # CV of 3 → 0 pts

    # --- Metric: avg_upvote_ratio (already 0-1, scale to 0-100) ---
    avg_ratio = (sum(upvote_ratios) / len(upvote_ratios)) if upvote_ratios else 0.5
    avg_upvote_ratio_norm = avg_ratio * 100

    # --- Metric: engagement_ratio (comments per upvote, log-normalized) ---
    # Healthy engagement ≈ 0.1 comments/upvote → normalize so 0.1 = 80 pts
    if avg_raw_score > 0:
        avg_comments = sum(comment_counts) / n
        raw_engagement = avg_comments / avg_raw_score
    else:
        raw_engagement = 0
    engagement_norm = _log_normalize(raw_engagement * 1000, reference=100.0)

    # --- Metric: community_diversity (unique authors / total posts, capped) ---
    unique_authors = len(set(authors))
    diversity = min(1.0, unique_authors / max(1, n)) * 100

    # --- Metric: freshness (% of posts < 7 days old) ---
    fresh_count = sum(1 for age in ages_days if age < 7)
    freshness = (fresh_count / n) * 100 if n else 0

    # --- Metric: original_content (1 - crosspost fraction) ---
    original_content = (1 - crosspost_count / max(1, n)) * 100

    # --- Weighted score ---
    metrics = {
        "avg_score": avg_score_norm,
        "score_consistency": score_consistency,
        "avg_upvote_ratio": avg_upvote_ratio_norm,
        "engagement_ratio": engagement_norm,
        "community_diversity": diversity,
        "freshness": freshness,
        "original_content": original_content,
    }
    weighted_score = sum(metrics[k] * WEIGHTS[k] for k in WEIGHTS)

    # --- Grade ---
    grade = _score_to_grade(weighted_score)

    # --- Extra breakdowns ---
    type_counter: Counter = Counter(_classify_post_type(p) for p in posts)
    content_type_dist = dict(type_counter.most_common())

    flair_counter: Counter = Counter(
        p.link_flair_text for p in posts if p.link_flair_text
    )
    top_flairs = flair_counter.most_common(5)

    bucket_counter: Counter = Counter(_score_bucket(p.score) for p in posts)
    score_distribution = dict(bucket_counter)

    return SubredditReport(
        name=sub_meta["name"],
        title=sub_meta.get("title", ""),
        subscribers=sub_meta.get("subscribers", 0),
        low_sample=sub_meta.get("low_sample", False),
        post_count=n,
        avg_score=avg_score_norm,
        score_consistency=score_consistency,
        avg_upvote_ratio=avg_upvote_ratio_norm,
        engagement_ratio=engagement_norm,
        community_diversity=diversity,
        freshness=freshness,
        original_content=original_content,
        weighted_score=weighted_score,
        grade=grade,
        content_type_dist=content_type_dist,
        top_flairs=top_flairs,
        score_distribution=score_distribution,
    )


def _score_to_grade(score: float) -> str:
    if score >= 80:
        return "A"
    elif score >= 65:
        return "B"
    elif score >= 50:
        return "C"
    elif score >= 35:
        return "D"
    else:
        return "F"
