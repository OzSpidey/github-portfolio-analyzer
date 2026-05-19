"""Central configuration for GitHub Portfolio Analyzer."""
import os
from pathlib import Path

# ── Paths ─────────────────────────────────────────────────────────────────────
CACHE_DIR    = Path("cache")
CACHE_TTL_S  = 3600          # 1-hour cache TTL

# ── GitHub API ────────────────────────────────────────────────────────────────
GITHUB_API_BASE    = "https://api.github.com"
RATE_LIMIT_BUFFER  = 5       # pause when remaining requests < this
MAX_REPOS_FOR_DEEP = 30      # fetch commits+languages for top N repos by stars
MAX_COMMIT_PAGES   = 3       # pages of commits per repo (100/page)
REQUEST_TIMEOUT    = 15      # seconds

# ── UI ────────────────────────────────────────────────────────────────────────
BG        = "#0a0a1a"
CARD_BG   = "rgba(18,18,42,0.95)"
BORDER    = "rgba(255,255,255,0.08)"
TEXT      = "#e2e2f0"
MUTED     = "#6b7280"
ACCENT    = "#7c3aed"
GREEN     = "#22c55e"
RED       = "#ef4444"
YELLOW    = "#f59e0b"
BLUE      = "#3b82f6"
ORANGE    = "#f97316"

# GitHub contribution heatmap colorscale (mirrors github.com)
HEATMAP_COLORSCALE = [
    [0.00, "#0d1117"],
    [0.01, "#0e4429"],
    [0.25, "#006d32"],
    [0.55, "#26a641"],
    [1.00, "#39d353"],
]

LANGUAGE_COLORS: dict[str, str] = {
    "Python":     "#3572A5",
    "JavaScript": "#f1e05a",
    "TypeScript": "#2b7489",
    "Java":       "#b07219",
    "Go":         "#00ADD8",
    "Rust":       "#dea584",
    "C++":        "#f34b7d",
    "C":          "#555555",
    "C#":         "#178600",
    "Ruby":       "#701516",
    "PHP":        "#4F5D95",
    "Swift":      "#ffac45",
    "Kotlin":     "#F18E33",
    "Shell":      "#89e051",
    "HTML":       "#e34c26",
    "CSS":        "#563d7c",
    "Scala":      "#c22d40",
    "R":          "#198CE7",
    "Dart":       "#00B4AB",
    "Other":      "#6b7280",
}

EXAMPLE_USERNAMES = ["torvalds", "gvanrossum", "antirez"]
