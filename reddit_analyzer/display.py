from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.columns import Columns
from rich.text import Text
from rich import box

from .subreddit_analyzer import SubredditReport
from .user_analyzer import UserReport

console = Console()


# ─── Colour helpers ──────────────────────────────────────────────────────────

def _score_color(score: float) -> str:
    if score >= 70:
        return "green"
    elif score >= 45:
        return "yellow"
    return "red"


def _grade_color(grade: str) -> str:
    return {"A": "bold green", "B": "green", "C": "yellow", "D": "orange3", "F": "bold red"}.get(grade, "white")


def _pct_color(pct: float) -> str:
    if pct >= 70:
        return "green"
    elif pct >= 40:
        return "yellow"
    return "red"


# ─── Subreddit report ─────────────────────────────────────────────────────────

def print_subreddit_report(report: SubredditReport) -> None:
    grade_color = _grade_color(report.grade)

    # Header panel
    header_lines = [
        f"[bold]r/{report.name}[/bold]  —  {report.title}",
        f"[dim]{report.subscribers:,} subscribers[/dim]",
    ]
    if report.low_sample:
        header_lines.append("[yellow]⚠  Low sample size — score may be less accurate[/yellow]")

    score_text = Text()
    score_text.append(f"  {report.weighted_score:.1f}/100  ", style=f"bold {_score_color(report.weighted_score)}")
    score_text.append(f"Grade: ", style="dim")
    score_text.append(report.grade, style=f"bold {grade_color}")

    console.print()
    console.print(Panel(
        "\n".join(header_lines) + "\n" + score_text.markup,
        title="[bold cyan]Subreddit Analysis[/bold cyan]",
        border_style="cyan",
    ))

    # Metrics table
    metrics_table = Table(
        title="Quality Metrics",
        box=box.ROUNDED,
        show_header=True,
        header_style="bold cyan",
        min_width=55,
    )
    metrics_table.add_column("Metric", style="dim", min_width=26)
    metrics_table.add_column("Score", justify="right", min_width=8)
    metrics_table.add_column("Weight", justify="right", min_width=8)
    metrics_table.add_column("Bar", min_width=12)

    metric_labels = {
        "avg_score": ("Avg Post Score", report.avg_score),
        "score_consistency": ("Score Consistency", report.score_consistency),
        "avg_upvote_ratio": ("Avg Upvote Ratio", report.avg_upvote_ratio),
        "engagement_ratio": ("Engagement (comments/score)", report.engagement_ratio),
        "community_diversity": ("Community Diversity", report.community_diversity),
        "freshness": ("Post Freshness", report.freshness),
        "original_content": ("Original Content", report.original_content),
    }

    from .subreddit_analyzer import WEIGHTS
    for key, (label, value) in metric_labels.items():
        weight = WEIGHTS[key]
        color = _score_color(value)
        bar = _bar(value)
        metrics_table.add_row(
            label,
            f"[{color}]{value:.1f}[/{color}]",
            f"{int(weight * 100)}%",
            f"[{color}]{bar}[/{color}]",
        )

    console.print(metrics_table)

    # Content type + score distribution side by side
    _print_subreddit_breakdowns(report)

    # Recommendations
    _print_subreddit_recommendations(report)
    console.print()


def _bar(value: float, width: int = 12) -> str:
    filled = int(value / 100 * width)
    return "█" * filled + "░" * (width - filled)


def _print_subreddit_breakdowns(report: SubredditReport) -> None:
    panels = []

    if report.content_type_dist:
        t = Table(box=box.SIMPLE, show_header=True, header_style="bold", title="Content Types")
        t.add_column("Type")
        t.add_column("Count", justify="right")
        total = sum(report.content_type_dist.values())
        for ctype, count in sorted(report.content_type_dist.items(), key=lambda x: -x[1]):
            pct = count / total * 100
            t.add_row(ctype, f"{count} ({pct:.0f}%)")
        panels.append(t)

    if report.score_distribution:
        order = ["<10", "10-99", "100-999", "1k-9.9k", "10k+"]
        t = Table(box=box.SIMPLE, show_header=True, header_style="bold", title="Score Distribution")
        t.add_column("Range")
        t.add_column("Count", justify="right")
        for bucket in order:
            count = report.score_distribution.get(bucket, 0)
            if count:
                t.add_row(bucket, str(count))
        panels.append(t)

    if report.top_flairs:
        t = Table(box=box.SIMPLE, show_header=True, header_style="bold", title="Top Flairs")
        t.add_column("Flair")
        t.add_column("Count", justify="right")
        for flair, count in report.top_flairs:
            t.add_row(flair or "(none)", str(count))
        panels.append(t)

    if panels:
        console.print(Columns(panels, equal=False, expand=False))


def _print_subreddit_recommendations(report: SubredditReport) -> None:
    tips = []

    if report.avg_score < 40:
        tips.append("[red]Low avg post score[/red] — posts here don't get much traction")
    if report.score_consistency < 40:
        tips.append("[yellow]High score variance[/yellow] — success here is unpredictable / lottery-like")
    if report.community_diversity < 40:
        tips.append("[yellow]Low diversity[/yellow] — a few power users dominate; hard to break through")
    if report.freshness < 30:
        tips.append("[yellow]Low freshness[/yellow] — mostly evergreen/old posts at the top; slow sub")
    if report.engagement_ratio > 70:
        tips.append("[green]High engagement[/green] — posts spark good discussion")
    if report.original_content < 60:
        tips.append("[yellow]High crosspost rate[/yellow] — sub relies on content from elsewhere")
    if report.weighted_score >= 75:
        tips.append("[green]Great subreddit[/green] — high quality, worth engaging with")
    elif report.weighted_score >= 55:
        tips.append("[yellow]Decent subreddit[/yellow] — average quality, selective engagement recommended")
    else:
        tips.append("[red]Low quality subreddit[/red] — may not be worth your time")

    if tips:
        console.print(Panel(
            "\n".join(f"• {t}" for t in tips),
            title="[bold]Insights & Recommendations[/bold]",
            border_style="dim",
        ))


# ─── User report ──────────────────────────────────────────────────────────────

def print_user_report(report: UserReport) -> None:
    console.print()

    total_karma = report.post_karma + report.comment_karma

    # Header
    header = (
        f"[bold]u/{report.username}[/bold]\n"
        f"[dim]Account age: {report.account_age_days:.0f} days  |  "
        f"Total karma: {total_karma:,}[/dim]\n"
        f"Post karma: [cyan]{report.post_karma:,}[/cyan]   "
        f"Comment karma: [cyan]{report.comment_karma:,}[/cyan]   "
        f"Source: [bold]{report.karma_source}[/bold]\n"
        f"Analyzed: [green]{report.submission_count}[/green] most recent submissions"
    )
    console.print(Panel(header, title="[bold cyan]User Karma Analysis[/bold cyan]", border_style="cyan"))

    if report.submission_count == 0:
        console.print("[yellow]No submissions found for this user.[/yellow]")
        return

    # Subreddit performance table
    if report.top_subreddits:
        t = Table(
            title="Top Subreddits by Performance",
            box=box.ROUNDED,
            header_style="bold cyan",
        )
        t.add_column("Subreddit", min_width=18)
        t.add_column("Posts", justify="right")
        t.add_column("Avg Score", justify="right")
        t.add_column("Best Score", justify="right")
        t.add_column("Hit Rate", justify="right")

        for sp in report.top_subreddits:
            hr_color = _pct_color(sp.hit_rate * 100)
            t.add_row(
                f"r/{sp.subreddit}",
                str(sp.post_count),
                f"[{_score_color(min(sp.avg_score / 10, 100))}]{sp.avg_score:,.0f}[/]",
                f"{sp.best_score:,}",
                f"[{hr_color}]{sp.hit_rate * 100:.0f}%[/{hr_color}]",
            )
        console.print(t)

    # Content type table
    if report.content_type_perf:
        t = Table(
            title="Performance by Content Type",
            box=box.ROUNDED,
            header_style="bold cyan",
        )
        t.add_column("Type", min_width=12)
        t.add_column("Count", justify="right")
        t.add_column("Avg Score", justify="right")
        t.add_column("Best", justify="right")

        for ctp in report.content_type_perf:
            t.add_row(
                ctp.content_type,
                str(ctp.count),
                f"{ctp.avg_score:,.0f}",
                f"{ctp.best_score:,}",
            )
        console.print(t)

    # Timing insights
    _print_timing_insights(report)

    # Title insights
    _print_title_insights(report)

    # Consistency + viral
    _print_consistency(report)

    # Key takeaways
    _print_user_takeaways(report)
    console.print()


def _print_timing_insights(report: UserReport) -> None:
    lines = []

    if report.best_hours:
        hour_strs = [f"{h:02d}:00 UTC (avg {report.hour_avg_scores.get(h, 0):,.0f})" for h in report.best_hours]
        lines.append(f"[bold]Best posting hours:[/bold] {', '.join(hour_strs)}")

    if report.best_days:
        day_strs = [f"{d} (avg {report.day_avg_scores.get(d, 0):,.0f})" for d in report.best_days]
        lines.append(f"[bold]Best posting days:[/bold]  {', '.join(day_strs)}")

    if report.recent_avg_score and report.alltime_avg_score:
        trend = report.recent_avg_score - report.alltime_avg_score
        trend_str = (
            f"[green]+{trend:,.0f} (trending up)[/green]"
            if trend > 0
            else f"[red]{trend:,.0f} (trending down)[/red]"
        )
        lines.append(
            f"[bold]Recent vs all-time avg:[/bold] "
            f"{report.recent_avg_score:,.0f} vs {report.alltime_avg_score:,.0f}  {trend_str}"
        )

    if lines:
        console.print(Panel("\n".join(lines), title="[bold]Timing Insights[/bold]", border_style="dim"))


def _print_title_insights(report: UserReport) -> None:
    q_avg = report.question_vs_statement_scores.get("question_avg", 0)
    s_avg = report.question_vs_statement_scores.get("statement_avg", 0)

    winner = "questions" if q_avg > s_avg else "statements"
    winner_color = "green"

    lines = [
        f"Avg title length:      [cyan]{report.avg_title_length:.0f} chars[/cyan]",
        f"Question titles:       [cyan]{report.question_titles_pct:.0f}%[/cyan]  (avg score: {q_avg:,.0f})",
        f"Statement titles:      [cyan]{100 - report.question_titles_pct:.0f}%[/cyan]  (avg score: {s_avg:,.0f})",
        f"Titles with numbers:   [cyan]{report.numbered_titles_pct:.0f}%[/cyan]",
        f"[bold]Better performing:[/bold] [{winner_color}]{winner}[/{winner_color}]",
    ]
    console.print(Panel("\n".join(lines), title="[bold]Title Patterns[/bold]", border_style="dim"))


def _print_consistency(report: UserReport) -> None:
    hit_color = _pct_color(report.hit_rate)
    lines = [
        f"Median post score:   [cyan]{report.median_score:,.0f}[/cyan]",
        f"Hit rate (≥ median): [{hit_color}]{report.hit_rate:.0f}%[/{hit_color}]",
    ]

    if report.viral_outliers:
        lines.append("")
        lines.append("[bold]Viral outliers (3× avg):[/bold]")
        for v in report.viral_outliers:
            lines.append(
                f"  • [{v['subreddit']}] [dim]{v['title']}[/dim]  [green]{v['score']:,} pts[/green]"
            )

    console.print(Panel("\n".join(lines), title="[bold]Consistency & Viral Posts[/bold]", border_style="dim"))


def _print_user_takeaways(report: UserReport) -> None:
    tips = []

    if report.karma_source == "post-heavy":
        tips.append("[cyan]Karma is post-driven[/cyan] — success comes from submissions, not comments")
    elif report.karma_source == "comment-heavy":
        tips.append("[cyan]Karma is comment-driven[/cyan] — success comes from engaging in discussions")
    else:
        tips.append("[cyan]Balanced karma[/cyan] — active in both posting and commenting")

    if report.top_subreddits:
        best_sub = report.top_subreddits[0]
        tips.append(
            f"[green]Strongest sub:[/green] r/{best_sub.subreddit} "
            f"(avg {best_sub.avg_score:,.0f} per post, {best_sub.hit_rate*100:.0f}% hit rate)"
        )

    if report.content_type_perf:
        best_type = report.content_type_perf[0]
        tips.append(f"[green]Best content type:[/green] {best_type.content_type} (avg {best_type.avg_score:,.0f})")

    if report.hit_rate >= 60:
        tips.append("[green]Consistent poster[/green] — most posts perform at or above their own median")
    elif report.viral_outliers:
        tips.append("[yellow]Hit-or-miss style[/yellow] — relies on occasional viral posts to boost karma")

    if report.best_hours:
        tips.append(f"[green]Best posting time:[/green] {report.best_hours[0]:02d}:00 UTC")

    if tips:
        console.print(Panel(
            "\n".join(f"• {t}" for t in tips),
            title="[bold]Why This User Has High Karma[/bold]",
            border_style="green",
        ))
