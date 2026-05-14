"""DashdarkX visual theme for Shield AI.

Call `apply_theme()` once at the top of every page.
All colors are lifted directly from the Figma design:
  Primary  #6C72FF  · Cyan    #57C3FF  · Amber   #FDB52A
  BG       #080F25  · Card    #101935  · Border  #212C4D
  Muted    #37446B  · Label   #7E89AC  · Text    #FFFFFF
"""
import streamlit as st

# ── Critical CSS injected FIRST — locks background+font before Streamlit's
#    own stylesheet loads, eliminating the white-flash / font-size jump.
#    Uses system fonts (visually identical to Inter) so there's zero layout
#    shift even before the web font downloads.
_CRITICAL_CSS = """
<style>
/* Instant dark background — prevents white flash on cold load */
html { background: #080F25 !important; }
body { background: #080F25 !important; color: #FFFFFF !important; }

/* System font stack — rendered immediately, Inter swaps in silently */
html, body, * {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto,
                 "Helvetica Neue", Arial, sans-serif;
}
</style>
<!-- Preconnect so the font domain is resolved before the stylesheet fires -->
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<!-- Non-blocking font load: display=swap means system font shows instantly,
     Inter swaps in once downloaded (cached after first visit = zero flash) -->
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap"
      rel="stylesheet">
"""

# ── Full CSS ──────────────────────────────────────────────────────────────────
_CSS = """
<style>
/* ── Base ───────────────────────────────────────────────────────────────── */
html, body, [class*="css"] {
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, "Segoe UI",
                 Roboto, "Helvetica Neue", Arial, sans-serif !important;
}
.stApp {
    background-color: #080F25 !important;
}
.main .block-container {
    padding-top: 1.25rem !important;
    padding-bottom: 3rem !important;
    max-width: 1440px !important;
}

/* ── Top header bar ─────────────────────────────────────────────────────── */
header[data-testid="stHeader"] {
    background: #080F25 !important;
    border-bottom: 1px solid #212C4D !important;
}
header[data-testid="stHeader"]::after {
    display: none !important;
}

/* ── Sidebar ────────────────────────────────────────────────────────────── */
[data-testid="stSidebar"] {
    background: #101935 !important;
    border-right: 1px solid #212C4D !important;
}
[data-testid="stSidebar"] > div:first-child {
    background: #101935 !important;
}
[data-testid="stSidebarNav"] a {
    color: #AEB9E1 !important;
    border-radius: 8px !important;
    padding: 0.45rem 0.75rem !important;
    transition: background 0.2s, color 0.2s !important;
}
[data-testid="stSidebarNav"] a:hover {
    background: rgba(108,114,255,0.12) !important;
    color: #FFFFFF !important;
}
[data-testid="stSidebarNav"] a[aria-current="page"] {
    background: rgba(108,114,255,0.18) !important;
    color: #6C72FF !important;
    font-weight: 600 !important;
}
[data-testid="stSidebar"] p,
[data-testid="stSidebar"] label,
[data-testid="stSidebar"] span {
    color: #AEB9E1 !important;
}
[data-testid="stSidebar"] hr { border-color: #212C4D !important; }

/* ── Metric cards ───────────────────────────────────────────────────────── */
[data-testid="metric-container"] {
    background: #101935 !important;
    border: 1px solid #212C4D !important;
    border-radius: 14px !important;
    padding: 1.25rem 1.5rem !important;
    transition: border-color 0.25s !important;
}
[data-testid="metric-container"]:hover {
    border-color: #343B4F !important;
}
[data-testid="stMetricValue"] {
    font-size: 1.75rem !important;
    font-weight: 700 !important;
    color: #FFFFFF !important;
}
[data-testid="stMetricLabel"] {
    font-size: 0.72rem !important;
    font-weight: 600 !important;
    color: #7E89AC !important;
    text-transform: uppercase !important;
    letter-spacing: 0.06em !important;
}
[data-testid="stMetricDelta"] { font-size: 0.78rem !important; }

/* ── Buttons ────────────────────────────────────────────────────────────── */
.stButton > button {
    border-radius: 8px !important;
    font-weight: 600 !important;
    font-size: 0.875rem !important;
    transition: all 0.2s !important;
}
.stButton > button[kind="primary"] {
    background: linear-gradient(135deg, #6C72FF 0%, #9A91FB 100%) !important;
    border: none !important;
    color: #FFFFFF !important;
    box-shadow: 0 4px 15px rgba(108,114,255,0.3) !important;
}
.stButton > button[kind="primary"]:hover {
    box-shadow: 0 6px 20px rgba(108,114,255,0.45) !important;
    transform: translateY(-1px) !important;
}
.stButton > button:not([kind="primary"]) {
    background: #101935 !important;
    border: 1px solid #343B4F !important;
    color: #AEB9E1 !important;
}
.stButton > button:not([kind="primary"]):hover {
    border-color: #6C72FF !important;
    color: #FFFFFF !important;
    background: rgba(108,114,255,0.08) !important;
}

/* ── Text inputs, selects ───────────────────────────────────────────────── */
.stSelectbox > div > div,
.stTextInput > div > div > input,
.stTextArea > div > div > textarea,
.stNumberInput > div > div > input {
    background-color: #101935 !important;
    border: 1px solid #212C4D !important;
    color: #FFFFFF !important;
    border-radius: 8px !important;
}
.stSelectbox > div > div:hover,
.stTextInput > div > div > input:focus,
.stTextArea > div > div > textarea:focus,
.stNumberInput > div > div > input:focus {
    border-color: #6C72FF !important;
    box-shadow: 0 0 0 2px rgba(108,114,255,0.15) !important;
}
.stSelectbox [data-testid="stMarkdownContainer"] p { color: #FFFFFF !important; }

/* ── Sliders ────────────────────────────────────────────────────────────── */
[data-baseweb="slider"] [data-testid="stThumb"] {
    background: #6C72FF !important;
    border: 2px solid #FFFFFF !important;
}
[data-baseweb="slider"] [class*="Track"] { background: #212C4D !important; }
[data-baseweb="slider"] [class*="InnerTrack"] { background: #6C72FF !important; }

/* ── Expanders ──────────────────────────────────────────────────────────── */
[data-testid="stExpander"] {
    background: #101935 !important;
    border: 1px solid #212C4D !important;
    border-radius: 12px !important;
    overflow: hidden !important;
}
[data-testid="stExpander"] summary {
    color: #AEB9E1 !important;
    font-weight: 500 !important;
}
[data-testid="stExpander"] summary:hover { color: #FFFFFF !important; }
[data-testid="stExpander"] svg { color: #7E89AC !important; }

/* ── Containers with border ─────────────────────────────────────────────── */
[data-testid="stVerticalBlockBorderWrapper"] > div {
    background: #101935 !important;
    border: 1px solid #212C4D !important;
    border-radius: 14px !important;
}

/* ── DataFrames / Tables ────────────────────────────────────────────────── */
[data-testid="stDataFrame"] {
    border-radius: 12px !important;
    overflow: hidden !important;
    border: 1px solid #212C4D !important;
}
[data-testid="stDataFrame"] th {
    background: #0D1628 !important;
    color: #7E89AC !important;
    font-size: 0.72rem !important;
    text-transform: uppercase !important;
    letter-spacing: 0.06em !important;
    font-weight: 600 !important;
}
[data-testid="stDataFrame"] td { border-color: #212C4D !important; }

/* ── Tabs ───────────────────────────────────────────────────────────────── */
[data-testid="stTabs"] [data-baseweb="tab-list"] {
    border-bottom: 1px solid #212C4D !important;
    background: transparent !important;
    gap: 0 !important;
}
[data-testid="stTabs"] [data-baseweb="tab"] {
    color: #7E89AC !important;
    background: transparent !important;
    border-radius: 0 !important;
    padding: 0.5rem 1.25rem !important;
    font-weight: 500 !important;
    font-size: 0.875rem !important;
    border-bottom: 2px solid transparent !important;
    transition: color 0.2s !important;
}
[data-testid="stTabs"] [aria-selected="true"] {
    color: #6C72FF !important;
    border-bottom-color: #6C72FF !important;
    font-weight: 600 !important;
}

/* ── Progress bar ───────────────────────────────────────────────────────── */
.stProgress > div > div > div > div {
    background: linear-gradient(90deg, #6C72FF, #57C3FF) !important;
}

/* ── Alert / callout boxes ──────────────────────────────────────────────── */
div[data-testid="stAlert"] {
    border-radius: 10px !important;
    border-left-width: 3px !important;
}

/* ── Dividers ───────────────────────────────────────────────────────────── */
hr { border-color: #212C4D !important; margin: 1.25rem 0 !important; }

/* ── File uploader ──────────────────────────────────────────────────────── */
[data-testid="stFileUploader"] {
    background: #101935 !important;
    border-radius: 14px !important;
}
[data-testid="stFileUploaderDropzone"] {
    background: #101935 !important;
    border: 2px dashed #343B4F !important;
    border-radius: 12px !important;
    transition: border-color 0.2s, background 0.2s !important;
    min-height: 130px !important;
    padding: 1.5rem 1.25rem !important;
}
[data-testid="stFileUploaderDropzone"]:hover {
    border-color: #6C72FF !important;
    background: rgba(108,114,255,0.05) !important;
}
/* Instructions text — prevent clipping, allow wrap */
[data-testid="stFileUploaderDropzoneInstructions"] {
    color: #AEB9E1 !important;
    white-space: normal !important;
    overflow: visible !important;
    text-overflow: unset !important;
    line-height: 1.65 !important;
    text-align: center !important;
    font-size: 0.95rem !important;
}
[data-testid="stFileUploaderDropzoneInstructions"] span {
    color: #AEB9E1 !important;
    white-space: normal !important;
}
[data-testid="stFileUploaderDropzoneInstructions"] small {
    color: #37446B !important;
    font-size: 0.78rem !important;
}
/* "Browse files" button inside dropzone */
[data-testid="stFileUploaderDropzone"] button {
    background: rgba(108,114,255,0.15) !important;
    border: 1px solid #6C72FF !important;
    color: #9A91FB !important;
    border-radius: 8px !important;
    font-weight: 600 !important;
    margin-top: 0.5rem !important;
}
[data-testid="stFileUploaderDropzone"] button:hover {
    background: rgba(108,114,255,0.28) !important;
    color: #FFFFFF !important;
}

/* ── Scrollbar ──────────────────────────────────────────────────────────── */
::-webkit-scrollbar { width: 5px; height: 5px; }
::-webkit-scrollbar-track { background: #101935; }
::-webkit-scrollbar-thumb { background: #37446B; border-radius: 3px; }
::-webkit-scrollbar-thumb:hover { background: #6C72FF; }

/* ── Animations ─────────────────────────────────────────────────────────── */
@keyframes fadeInUp {
    from { opacity: 0; transform: translateY(20px); }
    to   { opacity: 1; transform: translateY(0); }
}
@keyframes fadeIn {
    from { opacity: 0; } to { opacity: 1; }
}
@keyframes gradientShift {
    0%   { background-position: 0% 50%; }
    50%  { background-position: 100% 50%; }
    100% { background-position: 0% 50%; }
}
@keyframes pulse {
    0%, 100% { box-shadow: 0 0 0 0 rgba(108,114,255,0.4); }
    50%       { box-shadow: 0 0 0 8px rgba(108,114,255,0); }
}
@keyframes float {
    0%, 100% { transform: translateY(0px); }
    50%       { transform: translateY(-6px); }
}

/* ── Hero banner (About page) ───────────────────────────────────────────── */
.hero-banner {
    background: linear-gradient(-45deg, #080F25, #0e163a, #1a1060, #0a1a45, #101935);
    background-size: 400% 400%;
    animation: gradientShift 10s ease infinite;
    border-radius: 20px;
    padding: 3.5rem 3rem;
    border: 1px solid #212C4D;
    margin-bottom: 2rem;
    text-align: center;
    position: relative;
    overflow: hidden;
}
.hero-banner::before {
    content: '';
    position: absolute;
    top: -50%;
    left: -50%;
    width: 200%;
    height: 200%;
    background: radial-gradient(circle at 30% 40%, rgba(108,114,255,0.08) 0%, transparent 50%),
                radial-gradient(circle at 70% 60%, rgba(87,195,255,0.06) 0%, transparent 50%);
    pointer-events: none;
}
.hero-badge {
    display: inline-block;
    background: rgba(108,114,255,0.15);
    border: 1px solid rgba(108,114,255,0.4);
    border-radius: 999px;
    padding: 0.3rem 1.1rem;
    font-size: 0.8rem;
    color: #9A91FB;
    font-weight: 500;
    margin-bottom: 1.25rem;
    animation: fadeInUp 0.6s ease 0.1s both;
}
.hero-title {
    font-size: 3rem;
    font-weight: 800;
    background: linear-gradient(135deg, #FFFFFF 20%, #9A91FB 60%, #57C3FF 100%);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
    line-height: 1.15;
    margin: 0 0 1rem 0;
    animation: fadeInUp 0.6s ease 0.2s both;
}
.hero-subtitle {
    font-size: 1.1rem;
    color: #7E89AC;
    line-height: 1.7;
    max-width: 620px;
    margin: 0 auto 1.75rem auto;
    animation: fadeInUp 0.6s ease 0.3s both;
}
.hero-stats {
    display: flex;
    justify-content: center;
    gap: 2.5rem;
    flex-wrap: wrap;
    animation: fadeInUp 0.6s ease 0.4s both;
}
.hero-stat {
    text-align: center;
}
.hero-stat-value {
    font-size: 1.8rem;
    font-weight: 700;
    color: #6C72FF;
}
.hero-stat-label {
    font-size: 0.78rem;
    color: #7E89AC;
    text-transform: uppercase;
    letter-spacing: 0.05em;
}

/* ── Agent cards (About page) ───────────────────────────────────────────── */
.agent-card {
    background: #101935;
    border: 1px solid #212C4D;
    border-radius: 16px;
    padding: 1.75rem 1.5rem;
    height: 100%;
    transition: border-color 0.25s, transform 0.25s, box-shadow 0.25s;
    animation: fadeInUp 0.5s ease both;
    position: relative;
    overflow: hidden;
}
.agent-card::before {
    content: '';
    position: absolute;
    top: 0; left: 0; right: 0;
    height: 2px;
    border-radius: 16px 16px 0 0;
}
.agent-card.a1::before { background: linear-gradient(90deg, #6C72FF, #9A91FB); }
.agent-card.a2::before { background: linear-gradient(90deg, #ef4444, #f97316); }
.agent-card.a3::before { background: linear-gradient(90deg, #22c55e, #57C3FF); }
.agent-card.a4::before { background: linear-gradient(90deg, #FDB52A, #f97316); }
.agent-card.a5::before { background: linear-gradient(90deg, #9A91FB, #57C3FF); }
.agent-card:hover {
    border-color: #6C72FF;
    transform: translateY(-4px);
    box-shadow: 0 12px 40px rgba(108,114,255,0.15);
}
.agent-num {
    font-size: 0.7rem;
    font-weight: 700;
    letter-spacing: 0.12em;
    text-transform: uppercase;
    color: #7E89AC;
    margin-bottom: 0.5rem;
}
.agent-name {
    font-size: 1.05rem;
    font-weight: 700;
    color: #FFFFFF;
    margin-bottom: 0.35rem;
}
.agent-model {
    font-size: 0.75rem;
    color: #6C72FF;
    background: rgba(108,114,255,0.1);
    border-radius: 4px;
    padding: 0.15rem 0.5rem;
    display: inline-block;
    margin-bottom: 0.75rem;
    font-weight: 500;
}
.agent-desc {
    font-size: 0.85rem;
    color: #7E89AC;
    line-height: 1.6;
}

/* ── Status pills ───────────────────────────────────────────────────────── */
.pill {
    display: inline-block;
    padding: 0.2em 0.8em;
    border-radius: 999px;
    font-size: 0.72rem;
    font-weight: 600;
    letter-spacing: 0.04em;
    white-space: nowrap;
}
.pill-approved      { background:rgba(34,197,94,0.15);  color:#22c55e;  border:1px solid rgba(34,197,94,0.3); }
.pill-rejected      { background:rgba(239,68,68,0.15);  color:#ef4444;  border:1px solid rgba(239,68,68,0.3); }
.pill-legal_review  { background:rgba(87,195,255,0.15); color:#57C3FF;  border:1px solid rgba(87,195,255,0.3); }
.pill-manager_review{ background:rgba(253,181,42,0.15); color:#FDB52A;  border:1px solid rgba(253,181,42,0.3); }
.pill-processed     { background:rgba(154,145,251,0.15);color:#9A91FB;  border:1px solid rgba(154,145,251,0.3); }
.pill-quarantined   { background:rgba(239,68,68,0.18);  color:#ef4444;  border:1px solid rgba(239,68,68,0.35);}
.pill-extracted     { background:rgba(253,181,42,0.12); color:#FDB52A;  border:1px solid rgba(253,181,42,0.25);}
.pill-uploaded      { background:rgba(126,137,172,0.12);color:#7E89AC;  border:1px solid rgba(126,137,172,0.25);}
.pill-pipeline_failed { background:rgba(100,100,100,0.15); color:#7E89AC; border:1px solid rgba(100,100,100,0.25);}

/* ── Topbar row ─────────────────────────────────────────────────────────── */
.topbar-title {
    font-size: 1.6rem;
    font-weight: 700;
    color: #FFFFFF;
    line-height: 1.2;
}
.topbar-subtitle {
    font-size: 0.8rem;
    color: #7E89AC;
}

/* ── Score bar ──────────────────────────────────────────────────────────── */
.score-bar-wrap {
    background: #0D1628;
    border-radius: 8px;
    height: 10px;
    overflow: hidden;
    margin: 0.4rem 0;
}
.score-bar-fill {
    height: 100%;
    border-radius: 8px;
    transition: width 0.6s ease;
}

/* ── Spinner ────────────────────────────────────────────────────────────── */
.stSpinner > div { border-top-color: #6C72FF !important; }
</style>
"""


def apply_theme() -> None:
    """Inject the DashdarkX CSS theme. Call once at the top of every page.

    Injects in two passes:
      1. _CRITICAL_CSS — instant dark background + system font, prevents flash.
      2. _CSS — full stylesheet + Inter web font (non-blocking, swaps in silently).
    """
    # Critical CSS first — eliminates the white background / font-size flash
    st.markdown(_CRITICAL_CSS, unsafe_allow_html=True)
    # Full stylesheet second — overrides everything once the font loads
    st.markdown(_CSS, unsafe_allow_html=True)


def status_pill(status: str) -> str:
    """Return an HTML status pill for the given contract status string."""
    label = status.replace("_", " ").title()
    cls = f"pill-{status.lower().replace(' ', '_')}"
    return f'<span class="pill {cls}">{label}</span>'


def score_color(score: float) -> str:
    """Return the hex colour that matches the composite score band."""
    if score >= 82:  return "#22c55e"
    if score >= 63:  return "#FDB52A"
    if score >= 38:  return "#f97316"
    return "#ef4444"


def score_bar_html(score: float, label: str = "") -> str:
    """Return an inline HTML progress-bar for a 0–100 score."""
    color = score_color(score)
    pct   = min(max(score, 0), 100)
    lbl   = f"<div style='font-size:0.78rem;color:#7E89AC;margin-bottom:4px;'>{label}</div>" if label else ""
    return (
        f"{lbl}"
        f"<div class='score-bar-wrap'>"
        f"  <div class='score-bar-fill' style='width:{pct}%;background:{color};'></div>"
        f"</div>"
        f"<div style='font-size:0.8rem;color:{color};font-weight:600;margin-top:2px;'>{score:.0f}/100</div>"
    )
