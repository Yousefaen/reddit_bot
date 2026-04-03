import os
import time
from dotenv import load_dotenv
import praw
import prawcore

load_dotenv()


def get_reddit() -> praw.Reddit:
    """Initialize a read-only Reddit instance from environment variables."""
    client_id = os.getenv("REDDIT_CLIENT_ID")
    client_secret = os.getenv("REDDIT_CLIENT_SECRET")
    user_agent = os.getenv("REDDIT_USER_AGENT", "reddit-analyzer/1.0")

    if not client_id or not client_secret:
        raise RuntimeError(
            "Missing Reddit API credentials.\n"
            "Set REDDIT_CLIENT_ID and REDDIT_CLIENT_SECRET in your .env file.\n"
            "See .env.example for details."
        )

    return praw.Reddit(
        client_id=client_id,
        client_secret=client_secret,
        user_agent=user_agent,
        ratelimit_seconds=300,
    )


def fetch_subreddit_posts(
    reddit: praw.Reddit, subreddit_name: str, limit: int = 100
) -> tuple[list, dict]:
    """
    Fetch posts and metadata from a subreddit.

    Returns (posts, sub_meta) where sub_meta has subscriber count etc.
    Raises SystemExit with a friendly message for private/banned subs.
    """
    try:
        sub = reddit.subreddit(subreddit_name)
        # Force a network call to validate the subreddit exists
        _ = sub.id
    except prawcore.exceptions.NotFound:
        raise SystemExit(f"Subreddit r/{subreddit_name} not found.")
    except prawcore.exceptions.Forbidden:
        raise SystemExit(f"Subreddit r/{subreddit_name} is private.")
    except prawcore.exceptions.Redirect:
        raise SystemExit(f"Subreddit r/{subreddit_name} has been banned or doesn't exist.")

    sub_meta = {
        "name": sub.display_name,
        "title": sub.title,
        "subscribers": sub.subscribers,
        "description": sub.public_description or "",
        "over18": sub.over18,
        "created_utc": sub.created_utc,
    }

    # Fetch hot + top/week, then dedupe by id for better coverage
    half = limit // 2
    seen = {}

    for post in sub.hot(limit=half):
        seen[post.id] = post

    time.sleep(0.5)  # be gentle between batch calls

    for post in sub.top(time_filter="week", limit=half):
        seen[post.id] = post

    posts = list(seen.values())

    if len(posts) < 20:
        # Fall through with a warning flag in meta
        sub_meta["low_sample"] = True
    else:
        sub_meta["low_sample"] = False

    return posts, sub_meta


def fetch_user_submissions(
    reddit: praw.Reddit, username: str, limit: int = 100
) -> tuple[list, object]:
    """
    Fetch recent submissions for a user.

    Returns (submissions, redditor).
    Raises SystemExit for suspended/deleted users.
    """
    try:
        redditor = reddit.redditor(username)
        # Force network call to validate
        _ = redditor.id
    except prawcore.exceptions.NotFound:
        raise SystemExit(f"User u/{username} not found or has been deleted.")
    except AttributeError:
        # Suspended accounts raise AttributeError when accessing .id
        raise SystemExit(f"User u/{username} is suspended.")

    try:
        submissions = list(redditor.submissions.new(limit=limit))
    except prawcore.exceptions.Forbidden:
        raise SystemExit(f"User u/{username} profile is not accessible.")

    return submissions, redditor
