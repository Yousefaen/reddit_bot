import sys
import click
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn

from .reddit_client import get_reddit, fetch_subreddit_posts, fetch_user_submissions
from .subreddit_analyzer import analyze_subreddit
from .user_analyzer import analyze_user
from .display import print_subreddit_report, print_user_report

console = Console()


@click.group()
def cli():
    """Reddit Analyzer — score subreddits and decode high-karma users."""
    pass


@cli.command("analyze-subreddit")
@click.argument("subreddit")
@click.option("--limit", default=100, show_default=True, help="Number of posts to sample.")
def cmd_analyze_subreddit(subreddit: str, limit: int):
    """Score a subreddit's post quality.

    SUBREDDIT is the subreddit name (without r/).

    Example:

      python -m reddit_analyzer.cli analyze-subreddit learnpython
    """
    try:
        reddit = get_reddit()
    except RuntimeError as e:
        console.print(f"[bold red]Error:[/bold red] {e}")
        sys.exit(1)

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        transient=True,
    ) as progress:
        task = progress.add_task(f"Fetching posts from r/{subreddit}…", total=None)
        try:
            posts, sub_meta = fetch_subreddit_posts(reddit, subreddit, limit=limit)
        except SystemExit as e:
            progress.stop()
            console.print(f"[bold red]{e}[/bold red]")
            sys.exit(1)

        progress.update(task, description=f"Analyzing {len(posts)} posts…")
        report = analyze_subreddit(posts, sub_meta)

    print_subreddit_report(report)


@cli.command("analyze-user")
@click.argument("username")
@click.option("--limit", default=100, show_default=True, help="Number of recent submissions to fetch.")
def cmd_analyze_user(username: str, limit: int):
    """Analyze why a user has high karma.

    USERNAME is the Reddit username (without u/).

    Example:

      python -m reddit_analyzer.cli analyze-user spez
    """
    try:
        reddit = get_reddit()
    except RuntimeError as e:
        console.print(f"[bold red]Error:[/bold red] {e}")
        sys.exit(1)

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        transient=True,
    ) as progress:
        task = progress.add_task(f"Fetching submissions for u/{username}…", total=None)
        try:
            submissions, redditor = fetch_user_submissions(reddit, username, limit=limit)
        except SystemExit as e:
            progress.stop()
            console.print(f"[bold red]{e}[/bold red]")
            sys.exit(1)

        progress.update(task, description=f"Analyzing {len(submissions)} submissions…")
        report = analyze_user(submissions, redditor)

    print_user_report(report)


if __name__ == "__main__":
    cli()
