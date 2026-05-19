"""GitHub Portfolio Analyzer — Plotly Dash application."""
import logging
import os
from typing import Any

import dash
import dash_bootstrap_components as dbc
import plotly.graph_objects as go
from dash import Input, Output, State, dcc, html

from analyzer import analyze_user
from config import (
    ACCENT, BG, BLUE, BORDER, CARD_BG, EXAMPLE_USERNAMES, GREEN,
    HEATMAP_COLORSCALE, LANGUAGE_COLORS, MUTED, ORANGE, RED, TEXT, YELLOW,
)
from github_client import GitHubClient

logger = logging.getLogger(__name__)

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# ── Plotly base layout ─────────────────────────────────────────────────────────
PL: dict = dict(
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="#0d0d20",
    font=dict(color=TEXT, family="Inter, system-ui, sans-serif"),
    margin=dict(l=50, r=30, t=44, b=40),
)

# ── App ────────────────────────────────────────────────────────────────────────
app = dash.Dash(
    __name__,
    external_stylesheets=[dbc.themes.CYBORG],
    title="GitHub Portfolio Analyzer",
    suppress_callback_exceptions=True,
)

TAB_S = {"padding": "10px 22px", "border": "none", "background": "transparent",
          "color": MUTED, "fontWeight": "600", "fontSize": "0.875rem"}
TAB_A = {**TAB_S, "color": TEXT, "background": CARD_BG,
          "borderBottom": f"2px solid {ACCENT}"}


# ── UI helpers ─────────────────────────────────────────────────────────────────
def card(children: Any, extra: dict | None = None) -> html.Div:
    """Render a dark glassmorphism card."""
    s = {"background": CARD_BG, "border": f"1px solid {BORDER}",
         "borderRadius": "16px", "padding": "20px"}
    if extra:
        s.update(extra)
    return html.Div(children, style=s)


def kpi(label: str, value: Any, color: str = ACCENT) -> html.Div:
    """Render a KPI tile."""
    return html.Div([
        html.Div(str(value), style={"fontSize": "2rem", "fontWeight": "800",
                                    "color": color, "lineHeight": "1.1"}),
        html.Div(label, style={"fontSize": "0.68rem", "color": MUTED,
                               "textTransform": "uppercase", "letterSpacing": "0.05em",
                               "marginTop": "4px"}),
    ], style={"background": CARD_BG, "border": f"1px solid {BORDER}",
              "borderRadius": "12px", "padding": "16px 20px",
              "textAlign": "center", "flex": "1", "minWidth": "130px"})


def lang_color(lang: str) -> str:
    """Return hex color for a programming language."""
    return LANGUAGE_COLORS.get(lang, LANGUAGE_COLORS["Other"])


# ── Chart functions ────────────────────────────────────────────────────────────
def fig_contribution_heatmap(analysis: dict) -> go.Figure:
    """Render GitHub-style contribution heatmap (last 365 days)."""
    hm   = analysis.get("activity_heatmap", {})
    z    = hm.get("z", [])
    dates = hm.get("dates", [])
    if not z:
        return go.Figure(layout={**PL, "title": {"text": "No commit data", "x": 0.5}})

    text = [[d if d else "" for d in week] for week in dates]
    fig  = go.Figure(go.Heatmap(
        z=[[row[i] for row in z] for i in range(7)],
        x=list(range(len(z))),
        y=["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"],
        text=[[row[i] for row in text] for i in range(7)],
        hovertemplate="%{text}: %{z} commits<extra></extra>",
        colorscale=HEATMAP_COLORSCALE,
        showscale=True,
        xgap=2, ygap=2,
    ))
    fig.update_layout(**PL, height=200,
                      margin=dict(l=50, r=20, t=30, b=20),
                      title=dict(text="Contribution Activity (last 365 days)", x=0.5))
    fig.update_xaxes(showticklabels=False)
    fig.update_yaxes(tickfont=dict(size=10))
    return fig


def fig_commits_by_weekday(analysis: dict) -> go.Figure:
    """Bar chart of commits by day of week."""
    counts = analysis.get("commits_by_weekday", [0] * 7)
    days   = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    colors = [ACCENT if c == max(counts) else "rgba(124,58,237,0.45)" for c in counts]
    fig = go.Figure(go.Bar(x=days, y=counts, marker_color=colors,
                           hovertemplate="%{x}: %{y} commits<extra></extra>"))
    fig.update_layout(**PL, height=260,
                      title=dict(text="Commits by Day of Week", x=0.5),
                      xaxis=dict(showgrid=False),
                      yaxis=dict(showgrid=True, gridcolor="rgba(255,255,255,0.05)"))
    return fig


def fig_commits_by_hour(analysis: dict) -> go.Figure:
    """Bar chart of commits by hour of day."""
    counts = analysis.get("commits_by_hour", [0] * 24)
    hours  = [f"{h:02d}:00" for h in range(24)]
    colors = [ACCENT if c == max(counts) else "rgba(124,58,237,0.45)" for c in counts]
    fig = go.Figure(go.Bar(x=hours, y=counts, marker_color=colors,
                           hovertemplate="%{x}: %{y} commits<extra></extra>"))
    fig.update_layout(**PL, height=260,
                      title=dict(text="Peak Coding Hours", x=0.5),
                      xaxis=dict(showgrid=False, tickangle=-45),
                      yaxis=dict(showgrid=True, gridcolor="rgba(255,255,255,0.05)"))
    return fig


def fig_language_donut(analysis: dict) -> go.Figure:
    """Donut chart of language bytes."""
    lb = analysis.get("language_bytes", {})
    if not lb:
        return go.Figure(layout={**PL, "title": {"text": "No language data", "x": 0.5}})
    sorted_langs = sorted(lb.items(), key=lambda x: x[1], reverse=True)
    top10 = sorted_langs[:10]
    other = sum(v for _, v in sorted_langs[10:])
    if other:
        top10.append(("Other", other))
    labels = [l for l, _ in top10]
    values = [v for _, v in top10]
    colors = [lang_color(l) for l in labels]
    fig = go.Figure(go.Pie(
        labels=labels, values=values,
        hole=0.55, marker_colors=colors,
        textinfo="label+percent",
        hovertemplate="%{label}: %{value:,} bytes<extra></extra>",
    ))
    fig.update_layout(**PL, height=360,
                      title=dict(text="Languages by Bytes", x=0.5),
                      showlegend=False)
    return fig


def fig_language_by_repos(analysis: dict) -> go.Figure:
    """Horizontal bar of repo count per language."""
    lrc = analysis.get("language_repo_count", {})
    if not lrc:
        return go.Figure(layout={**PL})
    sorted_lrc = sorted(lrc.items(), key=lambda x: x[1])[-15:]
    langs  = [l for l, _ in sorted_lrc]
    counts = [c for _, c in sorted_lrc]
    colors = [lang_color(l) for l in langs]
    fig = go.Figure(go.Bar(
        x=counts, y=langs, orientation="h",
        marker_color=colors,
        hovertemplate="%{y}: %{x} repos<extra></extra>",
        text=counts, textposition="outside",
    ))
    fig.update_layout(**PL, height=380,
                      title=dict(text="Repos per Language", x=0.5),
                      xaxis=dict(showgrid=False, showticklabels=False),
                      yaxis=dict(showgrid=False),
                      margin=dict(l=120, r=50, t=44, b=40))
    return fig


def fig_language_evolution(analysis: dict) -> go.Figure:
    """Stacked area chart of language usage over years."""
    evo = analysis.get("language_evolution", {})
    if not evo or not evo.get("years"):
        return go.Figure(layout={**PL, "title": {"text": "Not enough data", "x": 0.5}})
    fig = go.Figure()
    for lang in evo["languages"]:
        fig.add_trace(go.Scatter(
            x=evo["years"], y=evo["counts"][lang],
            name=lang, stackgroup="one", mode="none",
            fillcolor=lang_color(lang) + "bb",
            hovertemplate=f"{lang}: %{{y}} repos (%{{x}})<extra></extra>",
        ))
    fig.update_layout(**PL, height=320,
                      title=dict(text="Language Evolution Over Time", x=0.5),
                      xaxis=dict(showgrid=False, dtick=1),
                      yaxis=dict(showgrid=True, gridcolor="rgba(255,255,255,0.05)"),
                      legend=dict(orientation="h", yanchor="bottom", y=1.02))
    return fig


def fig_repo_timeline(analysis: dict) -> go.Figure:
    """Scatter of repos: x=created, y=stars, size=forks, color=language."""
    repos = analysis.get("repo_timeline", [])
    if not repos:
        return go.Figure(layout={**PL})
    fig = go.Figure()
    lang_groups: dict[str, list] = {}
    for r in repos:
        lang_groups.setdefault(r["language"], []).append(r)
    for lang, group in lang_groups.items():
        fig.add_trace(go.Scatter(
            x=[r["created_at"] for r in group],
            y=[r["stars"]      for r in group],
            mode="markers",
            name=lang,
            marker=dict(
                color=lang_color(lang),
                size=[max(8, min(30, r["forks"] * 2 + 8)) for r in group],
                opacity=0.8,
                line=dict(color="rgba(255,255,255,0.15)", width=1),
            ),
            customdata=[[r["name"], r["description"], r["forks"]] for r in group],
            hovertemplate=(
                "<b>%{customdata[0]}</b><br>"
                "%{customdata[1]}<br>"
                "Stars: %{y}  Forks: %{customdata[2]}<br>"
                "Created: %{x}<extra></extra>"
            ),
        ))
    fig.update_layout(**PL, height=400,
                      title=dict(text="Repository Timeline (size = forks)", x=0.5),
                      xaxis=dict(showgrid=False),
                      yaxis=dict(showgrid=True, gridcolor="rgba(255,255,255,0.05)",
                                 title="Stars"),
                      legend=dict(orientation="h", yanchor="bottom", y=1.02))
    return fig


def fig_top_repos_by_stars(analysis: dict) -> go.Figure:
    """Horizontal bar of top 12 repos by stars."""
    repos = sorted(analysis.get("repo_timeline", []),
                   key=lambda r: r["stars"], reverse=True)[:12]
    if not repos:
        return go.Figure(layout={**PL})
    repos = list(reversed(repos))
    fig = go.Figure(go.Bar(
        x=[r["stars"] for r in repos],
        y=[r["name"]  for r in repos],
        orientation="h",
        marker_color=[lang_color(r["language"]) for r in repos],
        text=[r["stars"] for r in repos],
        textposition="outside",
        hovertemplate="%{y}: %{x} stars<extra></extra>",
    ))
    fig.update_layout(**PL, height=400,
                      title=dict(text="Top Repositories by Stars", x=0.5),
                      xaxis=dict(showgrid=False, showticklabels=False),
                      yaxis=dict(showgrid=False),
                      margin=dict(l=160, r=60, t=44, b=40))
    return fig


def fig_stars_vs_forks(analysis: dict) -> go.Figure:
    """Scatter of stars vs forks per repo."""
    repos = analysis.get("repo_timeline", [])
    if not repos:
        return go.Figure(layout={**PL})
    fig = go.Figure(go.Scatter(
        x=[r["stars"]  for r in repos],
        y=[r["forks"]  for r in repos],
        mode="markers",
        marker=dict(
            color=[lang_color(r["language"]) for r in repos],
            size=10, opacity=0.75,
            line=dict(color="rgba(255,255,255,0.1)", width=1),
        ),
        customdata=[[r["name"], r["language"]] for r in repos],
        hovertemplate="<b>%{customdata[0]}</b> (%{customdata[1]})<br>Stars: %{x}  Forks: %{y}<extra></extra>",
    ))
    fig.update_layout(**PL, height=340,
                      title=dict(text="Stars vs Forks", x=0.5),
                      xaxis=dict(title="Stars", showgrid=True, gridcolor="rgba(255,255,255,0.05)"),
                      yaxis=dict(title="Forks", showgrid=True, gridcolor="rgba(255,255,255,0.05)"))
    return fig


def fig_repos_per_year(analysis: dict) -> go.Figure:
    """Bar chart of repos created per year."""
    from collections import Counter
    years = [r["created_at"][:4] for r in analysis.get("repo_timeline", []) if r.get("created_at")]
    if not years:
        return go.Figure(layout={**PL})
    counts = Counter(years)
    yr_sorted = sorted(counts.keys())
    fig = go.Figure(go.Bar(
        x=yr_sorted, y=[counts[y] for y in yr_sorted],
        marker_color=ACCENT,
        hovertemplate="%{x}: %{y} repos<extra></extra>",
    ))
    fig.update_layout(**PL, height=260,
                      title=dict(text="Repositories Created per Year", x=0.5),
                      xaxis=dict(showgrid=False, dtick=1),
                      yaxis=dict(showgrid=True, gridcolor="rgba(255,255,255,0.05)"))
    return fig


def fig_radar_comparison(data: dict) -> go.Figure:
    """Radar chart comparing two users across 6 normalised metrics."""
    u1 = data.get("user1", {})
    u2 = data.get("user2", {})
    if not u1 or not u2:
        return go.Figure(layout={**PL})

    s1, s2 = u1.get("summary", {}), u2.get("summary", {})
    categories = ["Stars", "Repos", "Commits", "Streak", "Languages", "Forks"]

    def norm(v1: float, v2: float) -> tuple[float, float]:
        m = max(v1, v2, 1)
        return round(v1 / m * 100, 1), round(v2 / m * 100, 1)

    pairs = [
        norm(s1.get("total_stars", 0),        s2.get("total_stars", 0)),
        norm(s1.get("total_repos", 0),         s2.get("total_repos", 0)),
        norm(s1.get("total_commits", 0),        s2.get("total_commits", 0)),
        norm(u1.get("streak_data", {}).get("longest_streak", 0),
             u2.get("streak_data", {}).get("longest_streak", 0)),
        norm(s1.get("languages_used", 0),      s2.get("languages_used", 0)),
        norm(s1.get("total_forks", 0),         s2.get("total_forks", 0)),
    ]
    v1 = [p[0] for p in pairs] + [pairs[0][0]]
    v2 = [p[1] for p in pairs] + [pairs[0][1]]
    cats = categories + [categories[0]]
    n1 = u1.get("user", {}).get("login", "User 1")
    n2 = u2.get("user", {}).get("login", "User 2")

    fig = go.Figure()
    fig.add_trace(go.Scatterpolar(r=v1, theta=cats, fill="toself",
                                   name=n1, line_color=ACCENT,
                                   fillcolor="rgba(124,58,237,0.2)"))
    fig.add_trace(go.Scatterpolar(r=v2, theta=cats, fill="toself",
                                   name=n2, line_color=BLUE,
                                   fillcolor="rgba(59,130,246,0.2)"))
    fig.update_layout(**PL, height=400,
                      title=dict(text="Portfolio Comparison", x=0.5),
                      polar=dict(
                          bgcolor="#0d0d20",
                          radialaxis=dict(visible=True, range=[0, 100],
                                          gridcolor="rgba(255,255,255,0.1)"),
                          angularaxis=dict(gridcolor="rgba(255,255,255,0.1)"),
                      ),
                      legend=dict(orientation="h", yanchor="bottom", y=-0.1))
    return fig


# ── Layout ─────────────────────────────────────────────────────────────────────
def make_layout() -> html.Div:
    """Build the full app layout."""
    return html.Div([
        # Header
        html.Div([
            html.Div([
                html.H1("GitHub Portfolio Analyzer",
                        style={"fontSize": "1.9rem", "fontWeight": "900",
                               "margin": "0 0 4px", "color": TEXT,
                               "letterSpacing": "-0.02em"}),
                html.P("Visualise any public GitHub profile — activity, languages, repos, streaks & more",
                       style={"margin": 0, "color": MUTED, "fontSize": "0.82rem"}),
            ]),
        ], style={
            "background": f"linear-gradient(135deg,rgba(124,58,237,0.22),rgba(59,130,246,0.08))",
            "borderBottom": f"1px solid {BORDER}",
            "padding": "22px 36px",
        }),

        # Search bar
        html.Div([
            html.Div([
                dcc.Input(
                    id="username-input",
                    type="text",
                    placeholder="Enter GitHub username (e.g. torvalds)",
                    debounce=False,
                    style={"flex": "1", "background": "rgba(18,18,42,0.95)",
                           "border": f"1px solid {BORDER}", "borderRadius": "10px",
                           "padding": "10px 16px", "color": TEXT, "fontSize": "0.95rem",
                           "outline": "none"},
                ),
                html.Button("Analyze", id="analyze-btn", n_clicks=0,
                            style={"marginLeft": "12px", "padding": "10px 28px",
                                   "background": ACCENT, "color": "white",
                                   "border": "none", "borderRadius": "10px",
                                   "fontWeight": "700", "fontSize": "0.9rem",
                                   "cursor": "pointer"}),
            ], style={"display": "flex", "alignItems": "center"}),
            html.Div(id="status-message",
                     style={"marginTop": "8px", "color": MUTED, "fontSize": "0.78rem"}),
        ], style={"padding": "20px 36px", "borderBottom": f"1px solid {BORDER}"}),

        dcc.Store(id="analysis-data"),
        dcc.Store(id="compare-data"),

        html.Div(id="main-content", style={"padding": "0 36px 40px", "minHeight": "80vh"}),

        html.Div("GitHub Portfolio Analyzer  ·  Data from GitHub REST API v3  ·  Cached for 1 hour",
                 style={"textAlign": "center", "color": MUTED, "fontSize": "0.72rem",
                        "padding": "14px", "borderTop": f"1px solid {BORDER}"}),
    ], style={"background": BG, "minHeight": "100vh",
              "fontFamily": "Inter, system-ui, sans-serif", "color": TEXT})


app.layout = make_layout


# ── Callbacks ──────────────────────────────────────────────────────────────────
@app.callback(
    Output("analysis-data",  "data"),
    Output("status-message", "children"),
    Input("analyze-btn",     "n_clicks"),
    State("username-input",  "value"),
    prevent_initial_call=True,
)
def run_analysis(n_clicks: int, username: str) -> tuple:
    """Validate username, run full portfolio analysis, store result."""
    if not username or not username.strip():
        return dash.no_update, "Please enter a GitHub username."
    username = username.strip().lstrip("@")
    try:
        client   = GitHubClient()
        analysis = analyze_user(client, username)
        user     = analysis.get("user", {})
        if user.get("message") == "Not Found":
            return dash.no_update, f"User '{username}' not found on GitHub."
        name = user.get("name") or user.get("login", username)
        repo_count = analysis.get("summary", {}).get("total_repos", 0)
        return analysis, f"Loaded {name} — {repo_count} repositories analysed."
    except Exception as exc:
        logger.exception("Analysis failed for %s", username)
        return dash.no_update, f"Error: {exc}"


@app.callback(
    Output("main-content", "children"),
    Input("analysis-data",  "data"),
)
def render_report(data: dict | None) -> html.Div:
    """Render landing page or full report depending on whether data is loaded."""
    if not data:
        return _render_landing()
    return _render_full_report(data)


@app.callback(
    Output("tab-content", "children"),
    Input("report-tabs",    "value"),
    State("analysis-data",  "data"),
)
def render_tab(tab: str, data: dict | None) -> html.Div:
    """Render selected tab content."""
    if not data:
        return html.P("No data loaded.", style={"color": MUTED, "padding": "20px"})
    if tab == "overview":
        return _tab_overview(data)
    if tab == "languages":
        return _tab_languages(data)
    if tab == "repos":
        return _tab_repos(data)
    if tab == "productivity":
        return _tab_productivity(data)
    if tab == "compare":
        return _tab_compare()
    return html.Div()


@app.callback(
    Output("compare-data",    "data"),
    Output("compare-status",  "children"),
    Input("compare-btn",      "n_clicks"),
    State("compare-user1",    "value"),
    State("compare-user2",    "value"),
    prevent_initial_call=True,
)
def run_comparison(n_clicks: int, user1: str, user2: str) -> tuple:
    """Fetch and analyse both users for side-by-side comparison."""
    if not user1 or not user2:
        return dash.no_update, "Please enter two usernames."
    try:
        client = GitHubClient()
        a1     = analyze_user(client, user1.strip())
        a2     = analyze_user(client, user2.strip())
        return {"user1": a1, "user2": a2}, f"Comparing {user1} vs {user2}"
    except Exception as exc:
        logger.exception("Comparison failed")
        return dash.no_update, f"Error: {exc}"


@app.callback(
    Output("compare-results", "children"),
    Input("compare-data",     "data"),
)
def render_comparison(data: dict | None) -> html.Div:
    """Render comparison charts when both user analyses are available."""
    if not data:
        return html.Div()
    u1, u2 = data.get("user1", {}), data.get("user2", {})
    s1, s2 = u1.get("summary", {}), u2.get("summary", {})
    n1 = u1.get("user", {}).get("login", "User 1")
    n2 = u2.get("user", {}).get("login", "User 2")

    metrics = [
        ("Total Repos",    s1.get("total_repos", 0),    s2.get("total_repos", 0)),
        ("Total Stars",    s1.get("total_stars", 0),    s2.get("total_stars", 0)),
        ("Total Forks",    s1.get("total_forks", 0),    s2.get("total_forks", 0)),
        ("Languages Used", s1.get("languages_used", 0), s2.get("languages_used", 0)),
        ("Total Commits",  s1.get("total_commits", 0),  s2.get("total_commits", 0)),
        ("Longest Streak", u1.get("streak_data", {}).get("longest_streak", 0),
                           u2.get("streak_data", {}).get("longest_streak", 0)),
        ("Account Age (days)", s1.get("account_age_days", 0), s2.get("account_age_days", 0)),
        ("Avg Stars/Repo", s1.get("avg_stars_per_repo", 0), s2.get("avg_stars_per_repo", 0)),
    ]

    rows = []
    for metric, v1, v2 in metrics:
        winner = GREEN if v1 > v2 else (RED if v1 < v2 else MUTED)
        rows.append(html.Tr([
            html.Td(metric, style={"color": MUTED, "padding": "8px 16px",
                                    "fontSize": "0.85rem"}),
            html.Td(str(v1), style={"color": GREEN if v1 >= v2 else TEXT,
                                     "fontWeight": "700", "padding": "8px 16px",
                                     "textAlign": "center"}),
            html.Td(str(v2), style={"color": GREEN if v2 >= v1 else TEXT,
                                     "fontWeight": "700", "padding": "8px 16px",
                                     "textAlign": "center"}),
        ], style={"borderBottom": f"1px solid {BORDER}"}))

    table = html.Table([
        html.Thead(html.Tr([
            html.Th("Metric", style={"color": MUTED, "padding": "8px 16px",
                                      "fontSize": "0.72rem", "textTransform": "uppercase"}),
            html.Th(n1, style={"color": ACCENT, "padding": "8px 16px",
                                "textAlign": "center", "fontWeight": "700"}),
            html.Th(n2, style={"color": BLUE, "padding": "8px 16px",
                                "textAlign": "center", "fontWeight": "700"}),
        ])),
        html.Tbody(rows),
    ], style={"width": "100%", "borderCollapse": "collapse"})

    return html.Div([
        html.Div([
            card([table], {"flex": "1"}),
            card([dcc.Graph(figure=fig_radar_comparison(data),
                            config={"displayModeBar": False})],
                 {"flex": "1"}),
        ], style={"display": "flex", "gap": "20px", "flexWrap": "wrap",
                  "marginTop": "20px"}),
    ])


# ── Page section builders ──────────────────────────────────────────────────────
def _render_landing() -> html.Div:
    """Render the landing page shown before any analysis."""
    features = [
        "Contribution heatmap — GitHub-style activity grid for the last 365 days",
        "Language breakdown by bytes and repo count with evolution over time",
        "Repository timeline — stars, forks, size visualised across your whole career",
        "Commit patterns — peak hours, most active day, longest streak",
        "Compare Mode — radar chart + side-by-side metrics for any two users",
        "File-based caching — re-analysis of the same user loads instantly",
    ]
    return html.Div([
        html.Div([
            html.H2("What this tool does", style={"fontWeight": "700",
                                                   "marginBottom": "16px"}),
            html.Ul([html.Li(f, style={"marginBottom": "8px", "color": MUTED,
                                        "fontSize": "0.9rem"}) for f in features]),
            html.Div([
                html.P("Try these well-known profiles:", style={"color": MUTED,
                                                                  "marginBottom": "8px",
                                                                  "fontSize": "0.85rem"}),
                html.Div([
                    html.Span(u, style={
                        "background": "rgba(124,58,237,0.2)", "color": ACCENT,
                        "border": f"1px solid rgba(124,58,237,0.4)",
                        "borderRadius": "6px", "padding": "4px 12px",
                        "marginRight": "8px", "fontSize": "0.82rem",
                        "fontWeight": "600", "cursor": "pointer",
                    }) for u in EXAMPLE_USERNAMES
                ]),
            ], style={"marginTop": "24px"}),
            html.P([
                "Tip: set ",
                html.Code("GITHUB_TOKEN", style={"background": "rgba(255,255,255,0.08)",
                                                   "padding": "1px 6px", "borderRadius": "4px"}),
                " in a .env file to raise the rate limit from 60 to 5,000 requests/hour.",
            ], style={"marginTop": "24px", "color": MUTED, "fontSize": "0.8rem"}),
        ], style={"maxWidth": "640px", "margin": "60px auto"}),
    ])


def _render_full_report(data: dict) -> html.Div:
    """Render profile card + tab report for a loaded user."""
    user    = data.get("user", {})
    summary = data.get("summary", {})
    streak  = data.get("streak_data", {})

    avatar  = user.get("avatar_url", "")
    name    = user.get("name") or user.get("login", "")
    login   = user.get("login", "")
    bio     = user.get("bio") or ""
    loc     = user.get("location") or ""
    company = user.get("company") or ""
    url     = user.get("html_url", f"https://github.com/{login}")

    profile_card = card([
        html.Div([
            html.Img(src=avatar, style={"width": "80px", "height": "80px",
                                         "borderRadius": "50%",
                                         "border": f"3px solid {ACCENT}",
                                         "marginRight": "20px"}) if avatar else html.Div(),
            html.Div([
                html.H2(name, style={"margin": "0 0 2px", "fontSize": "1.4rem",
                                      "fontWeight": "800"}),
                html.Div(f"@{login}", style={"color": ACCENT, "fontSize": "0.85rem",
                                               "marginBottom": "4px"}),
                html.Div(bio,         style={"color": MUTED, "fontSize": "0.82rem"}),
                html.Div(
                    " · ".join(filter(None, [loc, company])),
                    style={"color": MUTED, "fontSize": "0.78rem", "marginTop": "4px"},
                ),
            ]),
            html.A("View on GitHub", href=url, target="_blank",
                   style={"marginLeft": "auto", "padding": "8px 18px",
                          "background": ACCENT, "color": "white",
                          "borderRadius": "8px", "textDecoration": "none",
                          "fontWeight": "600", "fontSize": "0.82rem",
                          "alignSelf": "center"}),
        ], style={"display": "flex", "alignItems": "flex-start",
                  "marginBottom": "20px"}),
        html.Div([
            kpi("Public Repos",    summary.get("total_repos", 0),      ACCENT),
            kpi("Total Stars",     summary.get("total_stars", 0),      YELLOW),
            kpi("Total Forks",     summary.get("total_forks", 0),      BLUE),
            kpi("Longest Streak",  f"{streak.get('longest_streak',0)}d", GREEN),
            kpi("Languages",       summary.get("languages_used", 0),   ORANGE),
            kpi("Account Age",     f"{summary.get('account_age_days',0)}d", MUTED),
        ], style={"display": "flex", "gap": "12px", "flexWrap": "wrap"}),
    ], {"marginTop": "24px", "marginBottom": "4px"})

    tabs = dcc.Tabs(id="report-tabs", value="overview", children=[
        dcc.Tab(label="Overview & Activity", value="overview",
                style=TAB_S, selected_style=TAB_A),
        dcc.Tab(label="Languages & Stack",   value="languages",
                style=TAB_S, selected_style=TAB_A),
        dcc.Tab(label="Repository Deep Dive", value="repos",
                style=TAB_S, selected_style=TAB_A),
        dcc.Tab(label="Productivity Metrics", value="productivity",
                style=TAB_S, selected_style=TAB_A),
        dcc.Tab(label="Compare Mode",         value="compare",
                style=TAB_S, selected_style=TAB_A),
    ], style={"background": BG, "borderBottom": f"1px solid {BORDER}",
              "padding": "0", "marginTop": "16px"})

    return html.Div([
        profile_card,
        tabs,
        html.Div(id="tab-content",
                 style={"padding": "20px 0", "minHeight": "60vh"}),
    ])


def _tab_overview(data: dict) -> html.Div:
    """Render Overview & Activity tab."""
    summary = data.get("summary", {})
    streak  = data.get("streak_data", {})
    dates   = data.get("commit_dates", [])
    wd      = data.get("commits_by_weekday", [0] * 7)
    days    = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    busiest_day = days[wd.index(max(wd))] if any(wd) else "N/A"
    hours   = data.get("commits_by_hour", [0] * 24)
    peak_hr = f"{hours.index(max(hours)):02d}:00" if any(hours) else "N/A"
    weeks   = round(summary.get("account_age_days", 1) / 7, 1)
    avg_cpw = round(len(dates) / max(weeks, 1), 1)

    return html.Div([
        html.Div([
            kpi("Commits Analysed",  len(dates),                     ACCENT),
            kpi("Most Active Day",   busiest_day,                    GREEN),
            kpi("Peak Hour",         peak_hr,                        YELLOW),
            kpi("Avg Commits/Week",  avg_cpw,                        BLUE),
            kpi("Current Streak",    f"{streak.get('current_streak',0)}d",  ORANGE),
            kpi("Total Active Days", streak.get("total_active_days", 0),    MUTED),
        ], style={"display": "flex", "gap": "12px", "flexWrap": "wrap",
                  "marginBottom": "20px"}),
        card([dcc.Graph(figure=fig_contribution_heatmap(data),
                        config={"displayModeBar": False})],
             {"marginBottom": "20px"}),
        html.Div([
            card([dcc.Graph(figure=fig_commits_by_weekday(data),
                            config={"displayModeBar": False})],
                 {"flex": "1"}),
            card([dcc.Graph(figure=fig_commits_by_hour(data),
                            config={"displayModeBar": False})],
                 {"flex": "1"}),
        ], style={"display": "flex", "gap": "20px", "flexWrap": "wrap"}),
    ])


def _tab_languages(data: dict) -> html.Div:
    """Render Languages & Tech Stack tab."""
    topics = data.get("top_topics", [])
    badges = [
        html.Span(t, style={
            "background": "rgba(124,58,237,0.18)", "color": ACCENT,
            "border": f"1px solid rgba(124,58,237,0.35)",
            "borderRadius": "20px", "padding": "4px 12px",
            "marginRight": "8px", "marginBottom": "8px",
            "fontSize": "0.78rem", "fontWeight": "600",
            "display": "inline-block",
        }) for t, _ in topics
    ]
    return html.Div([
        html.Div([
            card([dcc.Graph(figure=fig_language_donut(data),
                            config={"displayModeBar": False})],
                 {"flex": "1"}),
            card([dcc.Graph(figure=fig_language_by_repos(data),
                            config={"displayModeBar": False})],
                 {"flex": "1"}),
        ], style={"display": "flex", "gap": "20px", "flexWrap": "wrap",
                  "marginBottom": "20px"}),
        card([dcc.Graph(figure=fig_language_evolution(data),
                        config={"displayModeBar": False})],
             {"marginBottom": "20px"}),
        card([
            html.H3("Tech Stack Topics", style={"margin": "0 0 14px",
                                                  "fontSize": "0.9rem", "fontWeight": "700"}),
            html.Div(badges if badges else
                     html.P("No topics found.", style={"color": MUTED})),
        ]),
    ])


def _tab_repos(data: dict) -> html.Div:
    """Render Repository Deep Dive tab."""
    return html.Div([
        card([dcc.Graph(figure=fig_repo_timeline(data),
                        config={"displayModeBar": False})],
             {"marginBottom": "20px"}),
        html.Div([
            card([dcc.Graph(figure=fig_top_repos_by_stars(data),
                            config={"displayModeBar": False})],
                 {"flex": "1"}),
            card([dcc.Graph(figure=fig_stars_vs_forks(data),
                            config={"displayModeBar": False})],
                 {"flex": "1"}),
        ], style={"display": "flex", "gap": "20px", "flexWrap": "wrap"}),
    ])


def _tab_productivity(data: dict) -> html.Div:
    """Render Productivity Metrics tab."""
    summary = data.get("summary", {})
    streak  = data.get("streak_data", {})
    dates   = data.get("commit_dates", [])
    wd      = data.get("commits_by_weekday", [0] * 7)
    days    = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    busiest = days[wd.index(max(wd))] if any(wd) else "N/A"
    return html.Div([
        html.Div([
            kpi("Total Repos",      summary.get("total_repos", 0),                  ACCENT),
            kpi("Total Stars",      summary.get("total_stars", 0),                  YELLOW),
            kpi("Total Forks",      summary.get("total_forks", 0),                  BLUE),
            kpi("Avg Stars/Repo",   summary.get("avg_stars_per_repo", 0),            GREEN),
            kpi("Longest Streak",   f"{streak.get('longest_streak', 0)} days",      ORANGE),
            kpi("Current Streak",   f"{streak.get('current_streak', 0)} days",      RED),
            kpi("Most Active Day",  busiest,                                         MUTED),
            kpi("Account Age",      f"{summary.get('account_age_days', 0)} days",   MUTED),
        ], style={"display": "flex", "gap": "12px", "flexWrap": "wrap",
                  "marginBottom": "20px"}),
        html.Div([
            card([dcc.Graph(figure=fig_repos_per_year(data),
                            config={"displayModeBar": False})],
                 {"flex": "1"}),
            card([dcc.Graph(figure=fig_commits_by_weekday(data),
                            config={"displayModeBar": False})],
                 {"flex": "1"}),
        ], style={"display": "flex", "gap": "20px", "flexWrap": "wrap"}),
    ])


def _tab_compare() -> html.Div:
    """Render Compare Mode tab (inputs + results placeholder)."""
    return html.Div([
        card([
            html.H3("Compare Two GitHub Users", style={"margin": "0 0 16px",
                                                         "fontWeight": "700"}),
            html.Div([
                dcc.Input(id="compare-user1", type="text",
                          placeholder="First username",
                          style={"flex": "1", "background": "rgba(18,18,42,0.95)",
                                 "border": f"1px solid {BORDER}", "borderRadius": "8px",
                                 "padding": "9px 14px", "color": TEXT,
                                 "fontSize": "0.9rem"}),
                html.Span("vs", style={"color": MUTED, "margin": "0 12px",
                                        "fontWeight": "700", "alignSelf": "center"}),
                dcc.Input(id="compare-user2", type="text",
                          placeholder="Second username",
                          style={"flex": "1", "background": "rgba(18,18,42,0.95)",
                                 "border": f"1px solid {BORDER}", "borderRadius": "8px",
                                 "padding": "9px 14px", "color": TEXT,
                                 "fontSize": "0.9rem"}),
                html.Button("Compare", id="compare-btn", n_clicks=0,
                            style={"marginLeft": "12px", "padding": "9px 24px",
                                   "background": BLUE, "color": "white",
                                   "border": "none", "borderRadius": "8px",
                                   "fontWeight": "700", "cursor": "pointer"}),
            ], style={"display": "flex", "alignItems": "center"}),
            html.Div(id="compare-status",
                     style={"marginTop": "8px", "color": MUTED, "fontSize": "0.78rem"}),
        ], {"marginBottom": "20px"}),
        html.Div(id="compare-results"),
    ])


# ── Entry point ────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    logger.info("Starting GitHub Portfolio Analyzer on http://localhost:8054")
    app.run(debug=False, port=8054, host="0.0.0.0")
