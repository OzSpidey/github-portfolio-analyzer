"""Portfolio analysis logic — stats, streaks, heatmaps, language evolution."""
import logging
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from typing import Any

import pandas as pd

from config import LANGUAGE_COLORS, MAX_REPOS_FOR_DEEP
from github_client import GitHubClient

logger = logging.getLogger(__name__)


def analyze_user(client: GitHubClient, username: str) -> dict[str, Any]:
    """Run full portfolio analysis; return a single result dict."""
    logger.info("Starting analysis for %s", username)

    user  = client.get_user(username)
    repos = client.get_repos(username)

    if not isinstance(repos, list):
        repos = []

    # Fetch languages + commits for top repos by stars
    top_repos = sorted(repos, key=lambda r: r.get("stargazers_count", 0), reverse=True)
    top_repos = [r for r in top_repos if not r.get("fork", False)][:MAX_REPOS_FOR_DEEP]

    language_bytes: dict[str, int] = defaultdict(int)
    all_commit_dates: list[str]    = []

    for repo in top_repos:
        name = repo.get("name", "")
        try:
            langs = client.get_languages(username, name)
            for lang, nbytes in langs.items():
                language_bytes[lang] += nbytes
        except Exception as exc:
            logger.warning("Languages fetch failed for %s: %s", name, exc)

        try:
            commits = client.get_commits(username, name)
            for c in commits:
                raw = (c.get("commit", {})
                        .get("author", {})
                        .get("date", ""))
                if raw:
                    all_commit_dates.append(raw[:10])
        except Exception as exc:
            logger.warning("Commits fetch failed for %s: %s", name, exc)

    all_commit_dates.sort()

    return {
        "user":                user,
        "repos":               repos,
        "language_bytes":      dict(language_bytes),
        "language_repo_count": _count_repo_languages(repos),
        "commit_dates":        all_commit_dates,
        "commits_by_weekday":  _commits_by_weekday(all_commit_dates),
        "commits_by_hour":     _commits_by_hour(top_repos, client, username),
        "repo_timeline":       _build_repo_timeline(repos),
        "top_topics":          cluster_topics(repos),
        "streak_data":         compute_streak(all_commit_dates),
        "activity_heatmap":    compute_activity_heatmap(all_commit_dates),
        "language_evolution":  get_language_evolution(repos),
        "summary":             _build_summary(user, repos, all_commit_dates),
    }


def compute_streak(commit_dates: list[str]) -> dict[str, int]:
    """Compute current, longest streak and total active days from sorted date list."""
    if not commit_dates:
        return {"current_streak": 0, "longest_streak": 0, "total_active_days": 0}

    unique_days = sorted({d for d in commit_dates if d})
    total_active = len(unique_days)
    today        = date.today()

    # Current streak
    current = 0
    check   = today
    day_set = {datetime.strptime(d, "%Y-%m-%d").date() for d in unique_days}
    while check in day_set:
        current += 1
        check   -= timedelta(days=1)
    # also accept streak ending yesterday
    if current == 0:
        check = today - timedelta(days=1)
        while check in day_set:
            current += 1
            check   -= timedelta(days=1)

    # Longest streak
    longest = 1
    run     = 1
    for i in range(1, len(unique_days)):
        d_prev = datetime.strptime(unique_days[i - 1], "%Y-%m-%d").date()
        d_curr = datetime.strptime(unique_days[i],     "%Y-%m-%d").date()
        if (d_curr - d_prev).days == 1:
            run += 1
            longest = max(longest, run)
        else:
            run = 1

    return {
        "current_streak":   current,
        "longest_streak":   longest,
        "total_active_days": total_active,
    }


def compute_activity_heatmap(commit_dates: list[str]) -> dict[str, Any]:
    """Build last-365-days activity heatmap (week × weekday grid)."""
    today     = date.today()
    start     = today - timedelta(days=364)
    counts    = Counter(commit_dates)

    weeks: list[list[int]]  = []
    dates: list[list[str]]  = []
    cur_week_counts: list[int] = []
    cur_week_dates:  list[str] = []

    day = start - timedelta(days=start.weekday())  # align to Monday
    while day <= today:
        ds = day.strftime("%Y-%m-%d")
        cur_week_counts.append(counts.get(ds, 0))
        cur_week_dates.append(ds)
        if len(cur_week_counts) == 7:
            weeks.append(cur_week_counts)
            dates.append(cur_week_dates)
            cur_week_counts = []
            cur_week_dates  = []
        day += timedelta(days=1)

    if cur_week_counts:
        cur_week_counts += [0] * (7 - len(cur_week_counts))
        cur_week_dates  += [""] * (7 - len(cur_week_dates))
        weeks.append(cur_week_counts)
        dates.append(cur_week_dates)

    return {"z": weeks, "dates": dates}


def cluster_topics(repos: list[dict]) -> list[tuple[str, int]]:
    """Extract and count all topics across repositories."""
    counter: Counter = Counter()
    for repo in repos:
        for topic in repo.get("topics", []):
            counter[topic] += 1
    return counter.most_common(20)


def get_language_evolution(repos: list[dict]) -> dict[str, Any]:
    """Build language usage by year from repo creation dates."""
    year_lang: dict[int, Counter] = defaultdict(Counter)
    for repo in repos:
        if repo.get("fork"):
            continue
        lang = repo.get("language") or "Other"
        created = repo.get("created_at", "")
        if created:
            try:
                yr = int(created[:4])
                year_lang[yr][lang] += 1
            except ValueError:
                pass

    if not year_lang:
        return {}

    years    = sorted(year_lang.keys())
    all_langs = {l for c in year_lang.values() for l in c}
    top_langs = sorted(all_langs, key=lambda l: sum(year_lang[y].get(l, 0) for y in years), reverse=True)[:8]

    return {
        "years": years,
        "languages": top_langs,
        "counts": {lang: [year_lang[y].get(lang, 0) for y in years] for lang in top_langs},
    }


# ── Private helpers ────────────────────────────────────────────────────────────

def _count_repo_languages(repos: list[dict]) -> dict[str, int]:
    """Count repos per primary language."""
    counter: Counter = Counter()
    for repo in repos:
        if not repo.get("fork"):
            lang = repo.get("language") or "Other"
            counter[lang] += 1
    return dict(counter)


def _commits_by_weekday(dates: list[str]) -> list[int]:
    """Return commit counts indexed Mon=0 … Sun=6."""
    counts = [0] * 7
    for d in dates:
        try:
            counts[datetime.strptime(d, "%Y-%m-%d").weekday()] += 1
        except ValueError:
            pass
    return counts


def _commits_by_hour(repos: list[dict], client: GitHubClient, username: str) -> list[int]:
    """Return commit counts by hour of day (0-23) from detailed commit objects."""
    counts = [0] * 24
    for repo in repos[:10]:
        try:
            commits = client.get_commits(username, repo.get("name", ""))
            for c in commits:
                raw = c.get("commit", {}).get("author", {}).get("date", "")
                if len(raw) >= 13:
                    counts[int(raw[11:13])] += 1
        except Exception:
            pass
    return counts


def _build_repo_timeline(repos: list[dict]) -> list[dict]:
    """Flatten repos into a list of dicts for the timeline scatter."""
    rows = []
    for r in repos:
        if r.get("fork"):
            continue
        rows.append({
            "name":       r.get("name", ""),
            "created_at": (r.get("created_at") or "")[:10],
            "pushed_at":  (r.get("pushed_at")  or "")[:10],
            "stars":      r.get("stargazers_count", 0),
            "forks":      r.get("forks_count", 0),
            "language":   r.get("language") or "Other",
            "size_kb":    r.get("size", 0),
            "topics":     r.get("topics", []),
            "description": r.get("description") or "",
            "url":        r.get("html_url", ""),
        })
    return sorted(rows, key=lambda x: x["created_at"])


def _build_summary(user: dict, repos: list[dict], commit_dates: list[str]) -> dict:
    """Compute high-level summary statistics."""
    own_repos = [r for r in repos if not r.get("fork")]
    created   = user.get("created_at", "")
    age_days  = 0
    if created:
        try:
            age_days = (date.today() - datetime.strptime(created[:10], "%Y-%m-%d").date()).days
        except ValueError:
            pass

    most_starred = max(own_repos, key=lambda r: r.get("stargazers_count", 0), default={})
    most_forked  = max(own_repos, key=lambda r: r.get("forks_count", 0), default={})

    total_stars = sum(r.get("stargazers_count", 0) for r in own_repos)
    total_forks = sum(r.get("forks_count", 0)      for r in own_repos)

    commits_per_week = 0.0
    if commit_dates and age_days > 7:
        commits_per_week = round(len(commit_dates) / (age_days / 7), 1)

    return {
        "total_repos":        len(own_repos),
        "total_stars":        total_stars,
        "total_forks":        total_forks,
        "total_commits":      len(commit_dates),
        "avg_stars_per_repo": round(total_stars / max(len(own_repos), 1), 1),
        "commits_per_week":   commits_per_week,
        "account_age_days":   age_days,
        "public_gists":       user.get("public_gists", 0),
        "most_starred_repo":  most_starred.get("name", "N/A"),
        "most_forked_repo":   most_forked.get("name", "N/A"),
        "languages_used":     len({r.get("language") for r in own_repos if r.get("language")}),
    }
