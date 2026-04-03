import os
import sys
import datetime

import streamlit as st
from dotenv import load_dotenv

load_dotenv()

# ─── Page config ─────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="Reddit Analyzer",
    page_icon="🔍",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─── Sidebar — credentials ────────────────────────────────────────────────────

with st.sidebar:
    st.title("🔍 Reddit Analyzer")
    st.markdown("---")
    st.subheader("API Credentials")
    st.caption("Get credentials at reddit.com/prefs/apps (create a 'script' app)")

    client_id = st.text_input(
        "Client ID",
        value=os.getenv("REDDIT_CLIENT_ID", ""),
        type="password",
        placeholder="e.g. abc123XYZ",
    )
    client_secret = st.text_input(
        "Client Secret",
        value=os.getenv("REDDIT_CLIENT_SECRET", ""),
        type="password",
        placeholder="e.g. secretvalue",
    )
    user_agent = st.text_input(
        "User Agent",
        value=os.getenv("REDDIT_USER_AGENT", "reddit-analyzer/1.0"),
    )

    credentials_ok = bool(client_id and client_secret)
    if not credentials_ok:
        st.warning("Enter your Reddit API credentials to get started.")

    st.markdown("---")
    st.caption("Or set REDDIT_CLIENT_ID / REDDIT_CLIENT_SECRET in a `.env` file.")


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _get_reddit():
    """Return a PRAW Reddit instance using sidebar credentials."""
    import praw
    return praw.Reddit(
        client_id=client_id,
        client_secret=client_secret,
        user_agent=user_agent,
        ratelimit_seconds=300,
    )


def _grade_color(grade: str) -> str:
    return {"A": "🟢", "B": "🟢", "C": "🟡", "D": "🟠", "F": "🔴"}.get(grade, "⚪")


def _metric_delta_color(value: float, threshold_good=65, threshold_bad=40) -> str:
    if value >= threshold_good:
        return "normal"   # green in Streamlit
    elif value >= threshold_bad:
        return "off"      # grey
    return "inverse"      # red


# ─── Subreddit tab ────────────────────────────────────────────────────────────

def render_subreddit_tab():
    st.header("Subreddit Quality Scorer")
    st.caption("Scan a subreddit and find out if it's worth your time.")

    col1, col2 = st.columns([3, 1])
    with col1:
        subreddit_name = st.text_input(
            "Subreddit name",
            placeholder="e.g. learnpython",
            label_visibility="collapsed",
        )
    with col2:
        limit = st.select_slider("Posts to sample", options=[50, 100, 250], value=100)

    analyze_btn = st.button("Analyze Subreddit", type="primary", disabled=not credentials_ok, key="sub_btn")

    if analyze_btn and subreddit_name:
        subreddit_name = subreddit_name.strip().lstrip("r/")
        _run_subreddit_analysis(subreddit_name, limit)
    elif analyze_btn:
        st.warning("Please enter a subreddit name.")


def _run_subreddit_analysis(subreddit_name: str, limit: int):
    from reddit_analyzer.reddit_client import fetch_subreddit_posts
    from reddit_analyzer.subreddit_analyzer import analyze_subreddit, WEIGHTS

    with st.spinner(f"Fetching posts from r/{subreddit_name}…"):
        try:
            reddit = _get_reddit()
            posts, sub_meta = fetch_subreddit_posts(reddit, subreddit_name, limit=limit)
        except SystemExit as e:
            st.error(str(e))
            return
        except Exception as e:
            st.error(f"Unexpected error: {e}")
            return

    with st.spinner("Scoring…"):
        report = analyze_subreddit(posts, sub_meta)

    if report.low_sample:
        st.warning("Low sample size — fewer than 20 posts found. Score may be less accurate.")

    # ── Score header ──
    grade_icon = _grade_color(report.grade)
    st.markdown(f"## r/{report.name}")
    st.caption(report.title)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Quality Score", f"{report.weighted_score:.1f} / 100")
    c2.metric("Grade", f"{grade_icon} {report.grade}")
    c3.metric("Posts Analyzed", report.post_count)
    c4.metric("Subscribers", f"{report.subscribers:,}")

    st.markdown("---")

    # ── Metrics breakdown ──
    st.subheader("Metric Breakdown")

    metric_rows = [
        ("Avg Post Score",          report.avg_score,           WEIGHTS["avg_score"],           "How well posts score on average (log-normalized, 1k upvotes ≈ 100%)"),
        ("Score Consistency",       report.score_consistency,   WEIGHTS["score_consistency"],   "How predictable success is (low = lottery-like)"),
        ("Avg Upvote Ratio",        report.avg_upvote_ratio,    WEIGHTS["avg_upvote_ratio"],    "Average community approval per post"),
        ("Engagement",              report.engagement_ratio,    WEIGHTS["engagement_ratio"],    "Comments relative to upvotes"),
        ("Community Diversity",     report.community_diversity, WEIGHTS["community_diversity"], "How many different people are posting"),
        ("Post Freshness",          report.freshness,           WEIGHTS["freshness"],           "Fraction of posts < 7 days old"),
        ("Original Content",        report.original_content,    WEIGHTS["original_content"],    "How little of the content is crossposts"),
    ]

    for label, value, weight, help_text in metric_rows:
        col_label, col_bar, col_score, col_weight = st.columns([2.5, 4, 1, 1])
        col_label.markdown(f"**{label}**", help=help_text)
        col_bar.progress(int(value))
        col_score.markdown(f"`{value:.0f}`")
        col_weight.caption(f"{int(weight * 100)}%")

    st.markdown("---")

    # ── Breakdowns ──
    b1, b2, b3 = st.columns(3)

    with b1:
        st.subheader("Content Types")
        if report.content_type_dist:
            total = sum(report.content_type_dist.values())
            for ctype, count in sorted(report.content_type_dist.items(), key=lambda x: -x[1]):
                st.markdown(f"**{ctype}** — {count} posts ({count/total*100:.0f}%)")
        else:
            st.caption("No data")

    with b2:
        st.subheader("Score Distribution")
        order = ["<10", "10-99", "100-999", "1k-9.9k", "10k+"]
        for bucket in order:
            count = report.score_distribution.get(bucket, 0)
            if count:
                st.markdown(f"**{bucket}** — {count} posts")

    with b3:
        st.subheader("Top Flairs")
        if report.top_flairs:
            for flair, count in report.top_flairs:
                st.markdown(f"**{flair or '(none)'}** — {count}")
        else:
            st.caption("No flairs found")

    st.markdown("---")

    # ── Recommendations ──
    st.subheader("Insights & Recommendations")
    _render_subreddit_recommendations(report)


def _render_subreddit_recommendations(report):
    from reddit_analyzer.subreddit_analyzer import SubredditReport

    if report.avg_score < 40:
        st.warning("**Low avg post score** — posts here don't get much traction.")
    if report.score_consistency < 40:
        st.warning("**High score variance** — success here is unpredictable / lottery-like.")
    if report.community_diversity < 40:
        st.warning("**Low diversity** — a few power users dominate; hard to break through.")
    if report.freshness < 30:
        st.info("**Low freshness** — mostly evergreen/old posts at the top; slow-moving sub.")
    if report.engagement_ratio > 70:
        st.success("**High engagement** — posts spark good discussion here.")
    if report.original_content < 60:
        st.warning("**High crosspost rate** — sub relies on content from elsewhere.")

    if report.weighted_score >= 75:
        st.success(f"**Great subreddit (Grade {report.grade})** — high quality, worth engaging with.")
    elif report.weighted_score >= 55:
        st.info(f"**Decent subreddit (Grade {report.grade})** — average quality, selective engagement recommended.")
    else:
        st.error(f"**Low quality subreddit (Grade {report.grade})** — may not be worth your time.")


# ─── User tab ─────────────────────────────────────────────────────────────────

def render_user_tab():
    st.header("High-Karma User Analyzer")
    st.caption("Find out exactly why a user has high karma.")

    col1, col2 = st.columns([3, 1])
    with col1:
        username = st.text_input(
            "Reddit username",
            placeholder="e.g. spez",
            label_visibility="collapsed",
        )
    with col2:
        limit = st.select_slider("Submissions to fetch", options=[50, 100, 250], value=100)

    analyze_btn = st.button("Analyze User", type="primary", disabled=not credentials_ok, key="user_btn")

    if analyze_btn and username:
        username = username.strip().lstrip("u/")
        _run_user_analysis(username, limit)
    elif analyze_btn:
        st.warning("Please enter a username.")


def _run_user_analysis(username: str, limit: int):
    from reddit_analyzer.reddit_client import fetch_user_submissions
    from reddit_analyzer.user_analyzer import analyze_user

    with st.spinner(f"Fetching submissions for u/{username}…"):
        try:
            reddit = _get_reddit()
            submissions, redditor = fetch_user_submissions(reddit, username, limit=limit)
        except SystemExit as e:
            st.error(str(e))
            return
        except Exception as e:
            st.error(f"Unexpected error: {e}")
            return

    with st.spinner("Analyzing karma patterns…"):
        report = analyze_user(submissions, redditor)

    if report.submission_count == 0:
        st.warning("No submissions found for this user.")
        return

    total_karma = report.post_karma + report.comment_karma

    # ── Header ──
    st.markdown(f"## u/{report.username}")
    st.caption(f"Account age: {report.account_age_days:.0f} days  |  Karma source: **{report.karma_source}**")

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total Karma", f"{total_karma:,}")
    c2.metric("Post Karma", f"{report.post_karma:,}")
    c3.metric("Comment Karma", f"{report.comment_karma:,}")
    c4.metric("Submissions Analyzed", report.submission_count)

    st.markdown("---")

    # ── Subreddit performance ──
    st.subheader("Where They Win: Subreddit Performance")
    if report.top_subreddits:
        import pandas as pd
        rows = [
            {
                "Subreddit": f"r/{sp.subreddit}",
                "Posts": sp.post_count,
                "Avg Score": sp.avg_score,
                "Best Score": sp.best_score,
                "Hit Rate": f"{sp.hit_rate * 100:.0f}%",
            }
            for sp in report.top_subreddits
        ]
        df = pd.DataFrame(rows)
        st.dataframe(df, use_container_width=True, hide_index=True)

    st.markdown("---")

    left, right = st.columns(2)

    with left:
        # ── Content type performance ──
        st.subheader("Best Content Type")
        if report.content_type_perf:
            import pandas as pd
            rows = [
                {
                    "Type": ctp.content_type,
                    "Count": ctp.count,
                    "Avg Score": ctp.avg_score,
                    "Best": ctp.best_score,
                }
                for ctp in report.content_type_perf
            ]
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

        st.markdown("---")

        # ── Title patterns ──
        st.subheader("Title Patterns")
        q_avg = report.question_vs_statement_scores.get("question_avg", 0)
        s_avg = report.question_vs_statement_scores.get("statement_avg", 0)
        winner = "Questions ✅" if q_avg > s_avg else "Statements ✅"

        st.markdown(f"- Avg title length: **{report.avg_title_length:.0f} chars**")
        st.markdown(f"- Question titles: **{report.question_titles_pct:.0f}%** (avg score: {q_avg:,.0f})")
        st.markdown(f"- Statement titles: **{100 - report.question_titles_pct:.0f}%** (avg score: {s_avg:,.0f})")
        st.markdown(f"- Titles with numbers: **{report.numbered_titles_pct:.0f}%**")
        st.markdown(f"- Better performing style: **{winner}**")

    with right:
        # ── Timing insights ──
        st.subheader("Best Posting Times (UTC)")
        if report.best_hours:
            for h in report.best_hours:
                avg = report.hour_avg_scores.get(h, 0)
                st.markdown(f"- **{h:02d}:00 UTC** — avg score {avg:,.0f}")

        st.markdown(f"**Best days:**")
        for d in report.best_days:
            avg = report.day_avg_scores.get(d, 0)
            st.markdown(f"- **{d}** — avg score {avg:,.0f}")

        # Recent vs all-time
        st.markdown("---")
        trend = report.recent_avg_score - report.alltime_avg_score
        trend_label = "↑ Trending up" if trend > 0 else "↓ Trending down"
        st.metric(
            "Recent avg (last 30d)",
            f"{report.recent_avg_score:,.0f}",
            delta=f"{trend:+.0f} vs all-time ({report.alltime_avg_score:,.0f})  {trend_label}",
        )

        st.markdown("---")

        # ── Consistency ──
        st.subheader("Consistency")
        st.metric("Median post score", f"{report.median_score:,.0f}")
        st.metric("Hit rate (≥ own median)", f"{report.hit_rate:.0f}%")

    # ── Viral outliers ──
    if report.viral_outliers:
        st.markdown("---")
        st.subheader("Viral Outliers (3× average)")
        import pandas as pd
        rows = [
            {
                "Subreddit": f"r/{v['subreddit']}",
                "Score": v["score"],
                "Title": v["title"],
            }
            for v in report.viral_outliers
        ]
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    st.markdown("---")

    # ── Key takeaways ──
    st.subheader("Why This User Has High Karma")
    _render_user_takeaways(report)


def _render_user_takeaways(report):
    if report.karma_source == "post-heavy":
        st.info("**Karma is post-driven** — success comes from submissions, not comments.")
    elif report.karma_source == "comment-heavy":
        st.info("**Karma is comment-driven** — success comes from engaging in discussions.")
    else:
        st.info("**Balanced karma** — active in both posting and commenting.")

    if report.top_subreddits:
        best = report.top_subreddits[0]
        st.success(
            f"**Strongest sub:** r/{best.subreddit} — "
            f"avg {best.avg_score:,.0f} per post, {best.hit_rate*100:.0f}% hit rate"
        )

    if report.content_type_perf:
        best_type = report.content_type_perf[0]
        st.success(f"**Best content type:** {best_type.content_type} (avg {best_type.avg_score:,.0f} per post)")

    if report.hit_rate >= 60:
        st.success("**Consistent poster** — most posts perform at or above their own median.")
    elif report.viral_outliers:
        st.warning("**Hit-or-miss style** — relies on occasional viral posts to boost karma.")

    if report.best_hours:
        st.success(f"**Best posting time:** {report.best_hours[0]:02d}:00 UTC")


# ─── Main layout ─────────────────────────────────────────────────────────────

tab_sub, tab_user = st.tabs(["📊 Subreddit Scorer", "👤 User Analyzer"])

with tab_sub:
    render_subreddit_tab()

with tab_user:
    render_user_tab()
