import math
import time
from collections import Counter, defaultdict
from dataclasses import dataclass, field


@dataclass
class SubredditPerf:
    subreddit: str
    post_count: int
    avg_score: float
    best_score: int
    hit_rate: float   # fraction of posts above user's personal median


@dataclass
class ContentTypePerf:
    content_type: str
    count: int
    avg_score: float
    best_score: int


@dataclass
class UserReport:
    username: str
    post_karma: int
    comment_karma: int
    account_age_days: float
    submission_count: int          # of fetched posts

    # Karma composition
    karma_source: str              # "post-heavy" | "comment-heavy" | "balanced"

    # Subreddit performance
    top_subreddits: list[SubredditPerf] = field(default_factory=list)

    # Content type breakdown
    content_type_perf: list[ContentTypePerf] = field(default_factory=list)

    # Timing insights
    best_hours: list[int] = field(default_factory=list)    # top 3 hours (UTC)
    best_days: list[str] = field(default_factory=list)     # top 2 days
    hour_avg_scores: dict = field(default_factory=dict)    # hour -> avg score
    day_avg_scores: dict = field(default_factory=dict)     # day_name -> avg score

    # Title pattern insights
    avg_title_length: float = 0.0
    question_titles_pct: float = 0.0
    numbered_titles_pct: float = 0.0
    question_vs_statement_scores: dict = field(default_factory=dict)

    # Consistency
    median_score: float = 0.0
    hit_rate: float = 0.0          # fraction of posts above own median
    viral_outliers: list = field(default_factory=list)     # top viral posts

    # Recent vs all-time
    recent_avg_score: float = 0.0  # last 30 days
    alltime_avg_score: float = 0.0


_DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def _classify_content_type(post) -> str:
    if post.is_self:
        return "self-text"
    url = post.url.lower()
    if any(x in url for x in (".jpg", ".jpeg", ".png", ".gif", ".webp", "imgur.com", "i.redd.it")):
        return "image"
    if any(x in url for x in ("youtube.com", "youtu.be", "v.redd.it", ".mp4", ".webm")):
        return "video"
    return "link"


def _median(values: list[float]) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    n = len(s)
    mid = n // 2
    return (s[mid - 1] + s[mid]) / 2 if n % 2 == 0 else s[mid]


def analyze_user(submissions: list, redditor) -> UserReport:
    now = time.time()
    post_karma = getattr(redditor, "link_karma", 0)
    comment_karma = getattr(redditor, "comment_karma", 0)
    created_utc = getattr(redditor, "created_utc", now)
    account_age_days = (now - created_utc) / 86400

    if not submissions:
        return UserReport(
            username=redditor.name,
            post_karma=post_karma,
            comment_karma=comment_karma,
            account_age_days=account_age_days,
            submission_count=0,
            karma_source=_karma_source(post_karma, comment_karma),
        )

    scores = [max(0, p.score) for p in submissions]
    alltime_avg = sum(scores) / len(scores)
    median_score = _median(scores)

    # --- Karma source ---
    karma_source = _karma_source(post_karma, comment_karma)

    # --- Subreddit performance ---
    sub_posts: dict[str, list] = defaultdict(list)
    for post in submissions:
        sub_posts[post.subreddit.display_name].append(post)

    sub_perfs = []
    for sub_name, posts in sub_posts.items():
        sub_scores = [p.score for p in posts]
        avg = sum(sub_scores) / len(sub_scores)
        hit_rate = sum(1 for s in sub_scores if s >= median_score) / len(sub_scores)
        sub_perfs.append(SubredditPerf(
            subreddit=sub_name,
            post_count=len(posts),
            avg_score=round(avg, 1),
            best_score=max(sub_scores),
            hit_rate=round(hit_rate, 2),
        ))
    sub_perfs.sort(key=lambda x: x.avg_score, reverse=True)

    # --- Content type performance ---
    type_posts: dict[str, list] = defaultdict(list)
    for post in submissions:
        ctype = _classify_content_type(post)
        type_posts[ctype].append(post)

    ct_perfs = []
    for ctype, posts in type_posts.items():
        s = [p.score for p in posts]
        ct_perfs.append(ContentTypePerf(
            content_type=ctype,
            count=len(posts),
            avg_score=round(sum(s) / len(s), 1),
            best_score=max(s),
        ))
    ct_perfs.sort(key=lambda x: x.avg_score, reverse=True)

    # --- Timing analysis ---
    hour_scores: dict[int, list] = defaultdict(list)
    day_scores: dict[str, list] = defaultdict(list)
    for post in submissions:
        import datetime
        dt = datetime.datetime.utcfromtimestamp(post.created_utc)
        hour_scores[dt.hour].append(post.score)
        day_scores[_DAYS[dt.weekday()]].append(post.score)

    hour_avg = {h: sum(v) / len(v) for h, v in hour_scores.items()}
    day_avg = {d: sum(v) / len(v) for d, v in day_scores.items()}

    best_hours = sorted(hour_avg, key=hour_avg.get, reverse=True)[:3]
    best_days = sorted(day_avg, key=day_avg.get, reverse=True)[:2]

    # --- Title patterns ---
    titles = [p.title for p in submissions]
    question_count = sum(1 for t in titles if t.strip().endswith("?"))
    numbered_count = sum(1 for t in titles if any(c.isdigit() for c in t[:10]))
    avg_title_len = sum(len(t) for t in titles) / len(titles)

    question_scores = [p.score for p in submissions if p.title.strip().endswith("?")]
    statement_scores = [p.score for p in submissions if not p.title.strip().endswith("?")]
    q_vs_s = {
        "question_avg": round(sum(question_scores) / len(question_scores), 1) if question_scores else 0,
        "statement_avg": round(sum(statement_scores) / len(statement_scores), 1) if statement_scores else 0,
    }

    # --- Consistency & viral outliers ---
    hit_rate = sum(1 for s in scores if s >= median_score) / len(scores)
    viral_threshold = alltime_avg * 3
    viral_posts = [p for p in submissions if p.score >= viral_threshold and p.score > 100]
    viral_posts.sort(key=lambda p: p.score, reverse=True)
    viral_summary = [
        {"title": p.title[:80], "score": p.score, "subreddit": p.subreddit.display_name}
        for p in viral_posts[:5]
    ]

    # --- Recent vs all-time ---
    cutoff = now - 30 * 86400
    recent = [p.score for p in submissions if p.created_utc >= cutoff]
    recent_avg = sum(recent) / len(recent) if recent else 0.0

    return UserReport(
        username=redditor.name,
        post_karma=post_karma,
        comment_karma=comment_karma,
        account_age_days=account_age_days,
        submission_count=len(submissions),
        karma_source=karma_source,
        top_subreddits=sub_perfs[:10],
        content_type_perf=ct_perfs,
        best_hours=best_hours,
        best_days=best_days,
        hour_avg_scores={h: round(v, 1) for h, v in hour_avg.items()},
        day_avg_scores={d: round(v, 1) for d, v in day_avg.items()},
        avg_title_length=round(avg_title_len, 1),
        question_titles_pct=round(question_count / len(titles) * 100, 1),
        numbered_titles_pct=round(numbered_count / len(titles) * 100, 1),
        question_vs_statement_scores=q_vs_s,
        median_score=median_score,
        hit_rate=round(hit_rate * 100, 1),
        viral_outliers=viral_summary,
        recent_avg_score=round(recent_avg, 1),
        alltime_avg_score=round(alltime_avg, 1),
    )


def _karma_source(post_karma: int, comment_karma: int) -> str:
    total = post_karma + comment_karma
    if total == 0:
        return "unknown"
    post_pct = post_karma / total
    if post_pct > 0.65:
        return "post-heavy"
    elif post_pct < 0.35:
        return "comment-heavy"
    return "balanced"
