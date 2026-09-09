"""
NEPSE Ninja - Custom Theme & UI Components
"""
import datetime as _dt
from urllib.parse import quote as _urlquote
from zoneinfo import ZoneInfo

# ── Ninja SVG icon (parameterized size) ───────
NINJA_SVG = '''<svg viewBox="0 0 48 48" xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}">
<circle cx="24" cy="20" r="14" fill="#1a1a2e"/>
<rect x="10" y="15" width="28" height="9" rx="4" fill="#0f0f23"/>
<path d="M16 18.5l5 1.5-5 1.5z" fill="#e8e8ff"/>
<path d="M32 18.5l-5 1.5 5 1.5z" fill="#e8e8ff"/>
<path d="M38 16c2.5-1.5 4.5-3.5 5.5-5.5" stroke="#e63946" stroke-width="2.2" stroke-linecap="round" fill="none"/>
<path d="M38 19.5c2-1 4-3 5-5" stroke="#e63946" stroke-width="1.6" stroke-linecap="round" fill="none"/>
<path d="M18 34l6 10 6-10" fill="#1a1a2e"/>
<rect x="17" y="33" width="14" height="4" rx="2" fill="#1a1a2e"/>
</svg>'''

NINJA_SVG_SM = NINJA_SVG.format(w=32, h=32)
NINJA_SVG_LG = NINJA_SVG.format(w=56, h=56)


# ── Theme helpers ──────────────────────────────
def get_theme(query_params=None):
    """
    Resolve the active theme ('light' | 'dark') from Streamlit's query params.
    """
    if query_params is None:
        return "light"
    val = query_params.get("theme", "light")
    if isinstance(val, list):  # older st.experimental_get_query_params() shape
        val = val[0] if val else "light"
    return "dark" if val == "dark" else "light"


def is_dark_mode(query_params=None) -> bool:
    """
    Returns True if dark mode is active, otherwise False.
    """
    return get_theme(query_params) == "dark"


def toggle_theme(current_theme="light") -> str:
    """
    Swaps and returns the opposite theme string.
    """
    return "light" if current_theme == "dark" else "dark"


# ── Full CSS (theme-aware) ────────────────────
def get_ninja_css(theme="light", active_nav="home"):
    if theme == "dark":
        vars_block = """
    --bg0: #0b0b14; --bg1: #12121c;
    --card: rgba(26,26,42,.72);
    --surface: #1b1b2b;
    --tp: #f1f1f7; --tm: #9a9ab3;
    --ac: #5b7cfa; --ar: #ff6b73; --ag: #3fd9c7;
    --nav-bg: rgba(15,15,24,.82);
    --border: rgba(255,255,255,.08);
    --tag-bg: #1b1b2b; --tag-border: #2a2a3d; --tag-tx: #cfcfe0;
    --r: 14px;
"""
    else:
        vars_block = """
    --bg0: #ffffff; --bg1: #ffffff;
    --card: rgba(255,255,255,.9);
    --surface: #ffffff;
    --tp: #1a1a2e; --tm: #666;
    --ac: #4361ee; --ar: #e63946; --ag: #2ec4b6;
    --nav-bg: rgba(255,255,255,.85);
    --border: rgba(67,97,238,.08);
    --tag-bg: #ffffff; --tag-border: #e4e4e4; --tag-tx: #555;
    --r: 14px;
"""

    # These force every native Streamlit widget (buttons, inputs, selects,
    # radios, dataframes) to stay legible against our custom --tp/--surface
    # palette, regardless of what theme the *browser* auto-detected for
    # Streamlit's own built-in styling (which otherwise can leave e.g.
    # white button text sitting on our white background). Applied for
    # BOTH themes — not just light — since the same white-on-white /
    # dark-on-dark mismatch can happen either direction.
    widget_contrast_overrides = f"""
    [data-testid="stWidgetLabel"], [data-testid="stWidgetLabel"] p,
    [data-testid="stTextInput"] label, [data-testid="stTextInput"] label p,
    [data-testid="stSelectbox"] label, [data-testid="stSelectbox"] label p,
    [data-testid="stMultiSelect"] label, [data-testid="stMultiSelect"] label p,
    [data-testid="stDateInput"] label, [data-testid="stDateInput"] label p,
    [data-testid="stNumberInput"] label, [data-testid="stNumberInput"] label p {{
        color: var(--tp) !important;
    }}
    [data-testid="stTextInput"] input,
    [data-testid="stNumberInput"] input {{
        color: var(--tp) !important;
        -webkit-text-fill-color: var(--tp) !important;
        background: transparent !important;
    }}
    [data-testid="stTextInput"] input::placeholder,
    [data-testid="stNumberInput"] input::placeholder {{
        color: var(--tm) !important;
        opacity: 1 !important;
        -webkit-text-fill-color: var(--tm) !important;
    }}
    [data-baseweb="select"] > div {{
        background: var(--surface) !important;
        border-color: var(--border) !important;
    }}
    [data-baseweb="select"] input,
    [data-baseweb="select"] div,
    [data-baseweb="select"] span {{
        color: var(--tp) !important;
    }}
    /* BaseWeb renders the dropdown menu / date picker in a portal
       appended to <body>, outside our normal CSS scope, so it needs
       its own explicit background + text rules. */
    [data-baseweb="popover"] [data-baseweb="menu"],
    [data-baseweb="popover"] ul[role="listbox"] {{
        background: var(--surface) !important;
    }}
    [data-baseweb="popover"] li,
    [data-baseweb="popover"] li *,
    [data-baseweb="calendar"],
    [data-baseweb="calendar"] * {{
        color: var(--tp) !important;
    }}
    .stButton > button, .stButton > button p, .stButton > button span {{
        color: var(--tp) !important;
    }}
    .stButton > button {{
        background: var(--surface) !important;
        border-color: var(--border) !important;
    }}
    [data-testid="stDataFrame"] * {{
        color: var(--tp);
    }}
    """

    return f"""<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800;900&family=Outfit:wght@300;400;500;600;700;800;900&display=swap');

#MainMenu, header, footer, .stDeployButton {{ display: none !important; }}
[data-testid="stSidebar"] {{ display: none; }}

:root {{{vars_block}}}
{widget_contrast_overrides}

html, body, .stApp {{
    background: var(--bg1) !important;
    color: var(--tp);
    animation: appFadeIn .25s ease-out;
}}

@keyframes appFadeIn {{
    from {{ opacity: 0; }}
    to   {{ opacity: 1; }}
}}


.ninja-nav {{
    position: fixed; top: 0; left: 0; right: 0; z-index: 1000;
    height: 56px; display: flex; align-items: center; justify-content: space-between;
    padding: 0 2rem;
    background: var(--nav-bg);
    backdrop-filter: blur(18px); -webkit-backdrop-filter: blur(18px);
    border-bottom: 1px solid var(--border);
    box-shadow: 0 1px 4px rgba(0,0,0,.03);
}}
.nav-brand {{ display: flex; align-items: center; gap: 10px; flex: 1 1 0; }}
.nav-brand-text {{
    font-family: 'Outfit', sans-serif; font-weight: 800;
    font-size: 1.15rem; color: var(--tp);
}}
.nav-brand-text em {{ font-style: normal; color: var(--ag); }}
.nav-links {{ display: flex; gap: 4px; align-items: center; flex: 1 1 0; justify-content: center; }}
.nav-links a {{
    font-size: .82rem; font-weight: 500;
    padding: 7px 16px; border-radius: 8px; color: var(--tm);
    text-decoration: none !important; white-space: nowrap;
    transition: background .18s ease, color .18s ease;
}}
.nav-links {{ display: flex; gap: 4px; align-items: center; flex: 1 1 0; justify-content: center; }}
.nav-right {{ display: flex; align-items: center; gap: 10px; flex: 1 1 0; justify-content: flex-end; }}
.nav-avatar {{
    width: 32px; height: 32px; border-radius: 50%;
    background: linear-gradient(135deg, var(--ac), #7b2cbf);
    display: flex; align-items: center; justify-content: center;
    color: #fff; font-weight: 700; font-size: .8rem;
}}
.theme-toggle {{
    width: 32px; height: 32px; border-radius: 50%;
    background: var(--surface);
    border: 1px solid var(--border);
    display: flex; align-items: center; justify-content: center;
    font-size: 1rem; cursor: pointer; text-decoration: none;
    transition: transform .2s ease;
}}

/* ── Nav tabs (real st.button widgets, not <a> links) ──
   A click just triggers Streamlit's fast in-place rerun over the
   already-open connection — no browser navigation, no full-page
   reload, no flash. Streamlit gives every keyed container/widget a
   stable ".st-key-<key>" class, which is the supported hook for
   targeting one specific widget with CSS (far more reliable than
   sibling-selector tricks). */
.st-key-nepse_nav_row {{
    position: fixed !important; top: 14px; left: 50vw !important;
    right: auto !important; z-index: 1001;
    transform: translateX(-50%) !important;
    width: max-content !important; max-width: none !important;
    height: 56px; display: flex !important; align-items: center;
    margin: 0 !important; padding: 0 !important;
}}
.st-key-nepse_nav_row [data-testid="stHorizontalBlock"] {{
    display: flex !important; align-items: center; gap: 4px;
    width: max-content !important; max-width: none !important;
    margin: 0 !important; padding: 0 !important;
}}
.st-key-nepse_nav_row [data-testid="stColumn"] {{
    width: auto !important; flex: 0 0 auto !important; min-width: 0 !important;
    max-width: max-content !important; margin: 0 !important; padding: 0 !important;
}}
.st-key-nepse_nav_row .stButton > button {{
    background: transparent !important;
    border: none !important;
    box-shadow: none !important;
    color: var(--tm) !important;
    font-size: .82rem !important;
    font-weight: 500 !important;
    padding: 7px 16px !important;
    border-radius: 8px !important;
    white-space: nowrap !important;
    transition: background .18s ease, color .18s ease !important;
}}
.st-key-nepse_nav_row .stButton > button:hover {{
    background: var(--bg1) !important;
    color: var(--tp) !important;
    transform: none !important;
    box-shadow: none !important;
}}

/* ── Theme toggle (also a real button now — instant, no reload) ── */
.st-key-theme_toggle_btn {{
    position: fixed; top: 12px; right: 32px; z-index: 1001;
    width: 32px !important;
}}
.st-key-theme_toggle_btn button {{
    width: 32px !important; height: 32px !important; min-height: 32px !important;
    border-radius: 50% !important; padding: 0 !important;
    background: var(--surface) !important; border: 1px solid var(--border) !important;
    display: flex !important; align-items: center; justify-content: center;
    font-size: 1rem !important; box-shadow: none !important;
    transition: transform .2s ease !important;
}}
.st-key-theme_toggle_btn button:hover {{
    transform: translateY(-1px) scale(1.05) !important;
}}
.st-key-theme_toggle_btn button p {{ margin: 0; }}
.theme-toggle:hover {{ transform: translateY(-1px) scale(1.05); }}

.block-container {{ padding-top: 76px !important; max-width: 1200px; }}

/* ── Hero ── */
.hero {{
    text-align: center; padding: 1rem 1rem 1rem;
    animation: fadeUp .55s ease-out;
}}
.hero-logo {{ margin-bottom: .6rem; }}
.hero-title {{
    font-family: 'Outfit', sans-serif;
    font-size: clamp(2.8rem, 6vw, 4.8rem);
    font-weight: 900; color: var(--tp);
    margin: 0; line-height: 1.05; letter-spacing: -2.5px;
}}
.hero-title em {{ font-style: normal; color: var(--ag); }}
.hero-sub {{
    font-size: 1rem; color: var(--tm);
    letter-spacing: 5px; margin-top: .35rem;
}}

/* ── Market badge ── */
.mkt-badge {{
    display: inline-flex; align-items: center; gap: 16px;
    margin-top: 1rem; font-size: .82rem; color: var(--tm);
    
}}
.mkt-badge .dot {{
    width: 7px; height: 7px; border-radius: 50%;
    display: inline-block; margin-right: 5px;
}}
.dot-red {{ background: var(--ar); }}
.dot-green {{ background: var(--ag); animation: blink 1.8s infinite; }}
@keyframes blink {{ 0%,100% {{opacity:1}} 50% {{opacity:.35}} }}
.mkt-badge .sep {{ width: 1px; height: 14px; background: var(--border); }}
.mkt-index {{ color: var(--tp); font-weight: 600; white-space: nowrap; }}
.mkt-index strong {{ color: var(--ac); font-weight: 800; }}
.mkt-index-change {{ font-weight: 700; white-space: nowrap; }}
.mkt-index-change.up {{ color: var(--ag); }}
.mkt-index-change.down {{ color: var(--ar); }}
.ai-tag {{ color: var(--ac); font-weight: 600; }}

/* ── Popular tags ── */
.pop-row {{
    text-align: center; margin: .8rem auto;
    max-width: 700px; animation: fadeUp .55s ease-out .22s both;
}}
.pop-label {{
    font-size: .68rem; font-weight: 600;
    letter-spacing: 3px; text-transform: uppercase; color: #aaa;
    margin-right: 6px;
}}
.stock-tag {{
    display: inline-block; padding: 5px 14px; margin: 3px;
    background: var(--tag-bg); border: 1px solid var(--tag-border); border-radius: 18px;
    font-size: .78rem; font-weight: 500; color: var(--tag-tx);
    transition: all .2s ease; text-decoration: none !important;
}}
.stock-tag:hover {{ transform: translateY(-2px); border-color: var(--ac); color: var(--ac); }}

/* ── Sector pills ── */
.pill-row {{
    text-align: center; margin: .6rem auto;
    max-width: 780px; animation: fadeUp .55s ease-out .32s both;
}}
.pill {{
    display: inline-block; padding: 5px 15px; margin: 3px;
    border-radius: 18px; font-size: .76rem; font-weight: 500;
    border: 1.4px solid; transition: all .22s ease;
    text-decoration: none !important;
}}
.pill:hover {{ transform: translateY(-2px); box-shadow: 0 4px 14px rgba(0,0,0,.08); }}
.pill {{ cursor: pointer; }}
.pill-active {{ box-shadow: 0 0 0 2px currentColor inset; font-weight: 700; }}

/* ── Sector company-list modal ── */
.sector-modal-backdrop {{
    position: fixed; inset: 0; z-index: 2000;
    background: rgba(10,10,20,.42);
    backdrop-filter: blur(3px); -webkit-backdrop-filter: blur(3px);
    display: block; cursor: default;
    animation: fadeIn .18s ease-out;
}}
.sector-modal {{
    position: fixed; top: 50%; left: 50%; transform: translate(-50%, -50%);
    z-index: 2001; width: min(560px, 92vw); max-height: 76vh;
    background: var(--surface); border: 1px solid var(--border);
    border-radius: 18px; box-shadow: 0 24px 70px rgba(0,0,0,.28);
    display: flex; flex-direction: column; overflow: hidden;
    animation: fadeUp .22s ease-out;
}}
.sector-modal-header {{
    display: flex; align-items: center; justify-content: space-between;
    padding: 1rem 1.3rem; border-bottom: 1px solid var(--border);
    flex-shrink: 0;
}}
.sector-modal-title {{
    font-family: 'Outfit', sans-serif; font-weight: 700;
    font-size: 1.05rem; color: var(--tp);
}}
.sector-modal-count {{ color: var(--tm); font-weight: 500; font-size: .85rem; }}
.sector-modal-close {{
    width: 28px; height: 28px; border-radius: 50%;
    display: flex; align-items: center; justify-content: center;
    background: var(--bg1); border: 1px solid var(--border);
    text-decoration: none; color: var(--tm); font-size: .85rem;
    transition: all .18s ease;
}}
.sector-modal-close:hover {{ background: var(--ar); color: #fff; border-color: var(--ar); }}
.sector-modal-body {{ overflow-y: auto; }}
.company-row {{
    display: flex; align-items: center; gap: 14px;
    padding: .85rem 1.3rem; border-bottom: 1px solid var(--border);
    text-decoration: none !important; transition: background .15s ease;
}}
.company-row * {{
    text-decoration: none !important;
}}
.company-row:last-child {{ border-bottom: none; }}
.company-row:hover {{ background: var(--bg1); }}
.company-symbol {{
    font-family: 'Outfit', sans-serif; font-weight: 800;
    min-width: 64px; color: var(--tp); font-size: .92rem;
}}
.company-name {{ flex: 1; color: var(--tp); font-size: .88rem; }}
.company-tag {{
    padding: 4px 11px; border-radius: 12px; font-size: .64rem;
    font-weight: 700; letter-spacing: .4px; text-transform: uppercase;
    border: 1.3px solid; white-space: nowrap; flex-shrink: 0;
}}
.company-row-empty {{ padding: 1.5rem 1.3rem; color: var(--tm); font-size: .88rem; text-align: center; }}
@keyframes fadeIn {{ from {{ opacity: 0; }} to {{ opacity: 1; }} }}

/* ── Live search suggestions (home search box) ── */
.search-suggest-wrap {{
    max-width: 640px; margin: 10px auto 0;
    animation: fadeUp .25s ease-out;
}}
.search-suggest-panel {{
    background: var(--surface); border: 1px solid var(--border);
    border-radius: 14px; overflow: hidden; text-align: left;
    box-shadow: 0 12px 34px rgba(0,0,0,.10);
}}
.search-suggest-empty {{
    padding: 1.1rem 1.3rem; color: var(--tm);
    font-size: .88rem; text-align: center;
}}
.search-suggest-footer {{
    padding: .55rem 1.3rem; text-align: center;
    font-size: .74rem; color: var(--tm);
    border-top: 1px solid var(--border);
    background: var(--bg1);
}}

/* ── NEPSE Index snapshot card ── */
.nepse-index-card {{
    background: var(--surface); border: 1px solid var(--border);
    border-radius: var(--r); padding: 1.15rem 1.4rem 1rem;
    margin: 0 0 1.4rem; box-shadow: 0 2px 16px rgba(0,0,0,.04);
    animation: fadeUp .35s ease-out;
}}
.nic-top {{
    display: flex; align-items: center; justify-content: space-between;
    margin-bottom: .6rem;
}}
.nic-label {{
    display: flex; align-items: center; gap: 7px;
    font-size: .72rem; font-weight: 700; letter-spacing: 1.3px;
    text-transform: uppercase; color: var(--tm);
}}
.nic-label .dot {{
    width: 7px; height: 7px; border-radius: 50%;
    background: var(--tm); display: inline-block;
}}
.nic-top-right {{ display: flex; align-items: center; gap: 8px; }}
.nic-status-pill {{
    display: inline-flex; align-items: center; gap: 6px;
    padding: 4px 12px; border-radius: 14px;
    font-size: .72rem; font-weight: 600; color: var(--tm);
    background: var(--bg1); border: 1px solid var(--border);
}}
.nic-status-pill .dot {{ width: 7px; height: 7px; border-radius: 50%; }}
.nic-status-pill .dot.open {{ background: var(--ag); animation: blink 1.8s infinite; }}
.nic-status-pill .dot.closed {{ background: var(--ar); }}
.nic-expand {{
    width: 30px; height: 30px; border-radius: 8px;
    display: flex; align-items: center; justify-content: center;
    background: var(--bg1); border: 1px solid var(--border);
    color: var(--tm); font-size: .8rem;
    text-decoration: none !important; cursor: pointer;
    transition: all .18s ease;
}}
.nic-expand:hover {{ border-color: var(--ac); color: var(--ac); background: var(--surface); }}
.nic-mid {{
    display: flex; align-items: center; gap: 12px;
    flex-wrap: wrap; margin-bottom: .25rem;
}}
.nic-value {{
    font-family: 'Outfit', sans-serif; font-weight: 800;
    font-size: 2.35rem; color: var(--tp); letter-spacing: -1px;
}}
.nic-change-col {{ display: flex; flex-direction: column; gap: 2px; }}
.nic-change-pill {{
    display: inline-flex; align-items: center; gap: 5px;
    padding: 4px 11px; border-radius: 13px;
    font-weight: 700; font-size: .8rem; width: fit-content;
}}
.nic-change-pill.up {{ color: var(--ag); background: rgba(46,196,182,.12); }}
.nic-change-pill.down {{ color: var(--ar); background: rgba(230,57,70,.12); }}
.nic-points {{ font-size: .8rem; font-weight: 600; padding-left: 2px; }}
.nic-points.up {{ color: var(--ag); }}
.nic-points.down {{ color: var(--ar); }}
.nic-bottom {{
    display: flex; align-items: center; justify-content: space-between;
    flex-wrap: wrap; gap: 8px; margin-top: .65rem;
}}
.nic-sentiment-pill {{
    display: inline-flex; align-items: center; gap: 6px;
    padding: 5px 13px; border-radius: 14px;
    font-size: .74rem; font-weight: 600;
    background: var(--bg1); border: 1px solid var(--border); color: var(--tm);
}}
.nic-sentiment-pill .dot {{ width: 7px; height: 7px; border-radius: 50%; }}
.nic-sentiment-pill.bullish .dot {{ background: var(--ag); }}
.nic-sentiment-pill.bearish .dot {{ background: var(--ar); }}
.nic-sentiment-pill.neutral .dot {{ background: var(--tm); }}
.nic-breadth {{ font-size: .82rem; color: var(--tm); display: inline-flex; align-items: center; gap: 6px; }}
.nic-breadth-sep {{ color: var(--border); }}
.nic-breadth .dot {{
    width: 7px; height: 7px; border-radius: 50%;
    display: inline-block; margin-right: 5px;
}}
.nic-breadth .dot.up {{ background: var(--ag); }}
.nic-breadth .dot.flat {{ background: #f0b429; }}
.nic-breadth .dot.down {{ background: var(--ar); }}

/* ── AI Recommendation card (per-symbol fundamentals verdict) ── */
.ai-rec-card {{
    display: flex; align-items: stretch;
    background: var(--surface); border: 1px solid var(--border);
    border-radius: var(--r); overflow: hidden;
    margin: .3rem 0 1.4rem; box-shadow: 0 2px 16px rgba(0,0,0,.04);
    animation: fadeUp .35s ease-out;
}}
.ai-rec-left {{
    flex: 0 0 180px; display: flex; flex-direction: column;
    align-items: center; justify-content: center; gap: 8px;
    padding: 1.3rem 1rem; text-align: center;
    border-right: 1px solid var(--border);
    background: var(--bg1);
}}
.ai-rec-left.buy {{ border-right: 3px solid var(--ag); }}
.ai-rec-left.sell {{ border-right: 3px solid var(--ar); }}
.ai-rec-left.hold {{ border-right: 3px solid #f0b429; }}
.ai-rec-eyebrow {{
    font-size: .64rem; font-weight: 700; letter-spacing: 1.4px;
    text-transform: uppercase; color: var(--tm);
}}
.ai-rec-verdict {{
    font-family: 'Outfit', sans-serif; font-weight: 800;
    font-size: 1.7rem; letter-spacing: .5px;
}}
.ai-rec-verdict.buy {{ color: var(--ag); }}
.ai-rec-verdict.sell {{ color: var(--ar); }}
.ai-rec-verdict.hold {{ color: #f0b429; }}
.ai-rec-body {{
    flex: 1; padding: 1.2rem 1.4rem;
    display: flex; flex-direction: column; justify-content: center; gap: .5rem;
}}
.ai-rec-summary {{ color: var(--tp); font-size: .92rem; line-height: 1.55; }}
.ai-rec-reasons {{
    display: flex; flex-wrap: wrap; gap: 6px; margin-top: .1rem;
}}
.ai-rec-chip {{
    padding: 3px 10px; border-radius: 12px; font-size: .7rem;
    font-weight: 600; background: var(--bg1); border: 1px solid var(--border);
    color: var(--tm);
}}
.ai-rec-disclaimer {{
    font-size: .68rem; color: var(--tm); margin-top: .4rem;
}}
.p-cb{{color:#e63946;border-color:#e63946;background:rgba(230,57,70,.08)}}
.p-db{{color:#e76f51;border-color:#e76f51;background:rgba(231,111,81,.08)}}
.p-hp{{color:#4361ee;border-color:#4361ee;background:rgba(67,97,238,.08)}}
.p-li{{color:#7b2cbf;border-color:#7b2cbf;background:rgba(123,44,191,.08)}}
.p-ni{{color:#2ec4b6;border-color:#2ec4b6;background:rgba(46,196,182,.08)}}
.p-fi{{color:#e63946;border-color:#e63946;background:rgba(230,57,70,.08)}}
.p-mf{{color:#f77f00;border-color:#f77f00;background:rgba(247,127,0,.08)}}
.p-ht{{color:#e76f51;border-color:#e76f51;background:rgba(231,111,81,.08)}}
.p-mg{{color:#888;border-color:#ccc;background:rgba(136,136,136,.08)}}
.p-tr{{color:#e63946;border-color:#e63946;background:rgba(230,57,70,.08)}}
.p-ot{{color:#888;border-color:#ccc;background:rgba(136,136,136,.08)}}
.p-in{{color:#4361ee;border-color:#4361ee;background:rgba(67,97,238,.08)}}

/* ── Sector pill BUTTONS (real st.button, not <a>) ──
   Streamlit doesn't allow a custom class on a button, so each pill
   button is preceded by a tiny marker span carrying the color class,
   and we style the button immediately after it via an adjacent-sibling
   selector. This keeps the colored-pill look while using a real
   Streamlit widget (no full-page reload on click). ── */
span.pill-mark {{
    display: block; height: 0; margin: 0; padding: 0;
}}
span.pill-mark + div[data-testid="stButton"] {{
    display: inline-block !important;
    width: auto !important;
}}
span.pill-mark + div[data-testid="stButton"] > button {{
    border-radius: 20px !important;
    padding: 6px 17px !important;
    font-size: .8rem !important;
    font-weight: 700 !important;
    white-space: nowrap !important;
    width: auto !important;
    min-width: 0 !important;
    border: 2px solid transparent !important;
    color: #fff !important;
    box-shadow: 0 2px 10px rgba(0,0,0,.12) !important;
    transition: transform .18s ease, box-shadow .18s ease, border-color .18s ease !important;
}}
span.pill-mark + div[data-testid="stButton"] > button:hover {{
    transform: translateY(-3px) scale(1.04) !important;
    box-shadow: 0 8px 20px rgba(0,0,0,.22) !important;
    filter: brightness(1.08);
    border-color: #fff !important;
}}
span.pill-mark + div[data-testid="stButton"] > button:active {{
    transform: translateY(-1px) scale(0.99) !important;
}}
span.pill-mark.p-cb + div[data-testid="stButton"] > button {{background: linear-gradient(135deg,#ff5f6d,#e63946) !important; border-color:#ff8a90 !important}}
span.pill-mark.p-db + div[data-testid="stButton"] > button {{background: linear-gradient(135deg,#ff9a6c,#e76f51) !important; border-color:#ffb996 !important}}
span.pill-mark.p-hp + div[data-testid="stButton"] > button {{background: linear-gradient(135deg,#5b7cfa,#4361ee) !important; border-color:#93a9ff !important}}
span.pill-mark.p-li + div[data-testid="stButton"] > button {{background: linear-gradient(135deg,#a75cf0,#7b2cbf) !important; border-color:#c99bf5 !important}}
span.pill-mark.p-ni + div[data-testid="stButton"] > button {{background: linear-gradient(135deg,#4fe0cc,#2ec4b6) !important; border-color:#8ff0e2 !important}}
span.pill-mark.p-fi + div[data-testid="stButton"] > button {{background: linear-gradient(135deg,#ff5f6d,#e63946) !important; border-color:#ff8a90 !important}}
span.pill-mark.p-mf + div[data-testid="stButton"] > button {{background: linear-gradient(135deg,#ffab40,#f77f00) !important; border-color:#ffcb84 !important}}
span.pill-mark.p-ht + div[data-testid="stButton"] > button {{background: linear-gradient(135deg,#ff9a6c,#e76f51) !important; border-color:#ffb996 !important}}
span.pill-mark.p-mg + div[data-testid="stButton"] > button {{background: linear-gradient(135deg,#9aa0a6,#6c7075) !important; border-color:#c2c6ca !important}}
span.pill-mark.p-tr + div[data-testid="stButton"] > button {{background: linear-gradient(135deg,#ff5f6d,#e63946) !important; border-color:#ff8a90 !important}}
span.pill-mark.p-ot + div[data-testid="stButton"] > button {{background: linear-gradient(135deg,#9aa0a6,#6c7075) !important; border-color:#c2c6ca !important}}
span.pill-mark.p-in + div[data-testid="stButton"] > button {{background: linear-gradient(135deg,#5b7cfa,#4361ee) !important; border-color:#93a9ff !important}}

/* Let the row of pill buttons wrap naturally and sit centered,
   instead of stretching into equal-width, text-wrapping boxes. */
div[data-testid="stHorizontalBlock"]:has(span.pill-mark) {{
    flex-wrap: wrap !important;
    row-gap: 10px !important;
    justify-content: center !important;
}}
div[data-testid="stHorizontalBlock"]:has(span.pill-mark) > div {{
    width: auto !important;
    flex: 0 0 auto !important;
}}


/* Global underline fix — applies to every link in the app regardless
   of load order, overriding Streamlit's own default anchor styling. */
a, a:link, a:visited, a:hover, a:active {{
    text-decoration: none !important;
}}


[data-testid="stMetric"] {{
    background: var(--card); backdrop-filter: blur(12px);
    border: 1px solid var(--border);
    border-radius: var(--r); padding: 1rem 1.1rem;
    box-shadow: 0 2px 14px rgba(0,0,0,.03);
    transition: transform .2s, box-shadow .2s;
}}
[data-testid="stMetric"]:hover {{
    transform: translateY(-2px);
    box-shadow: 0 6px 22px rgba(0,0,0,.08);
}}
[data-testid="stMetricLabel"] {{
    font-size: .78rem !important; font-weight: 600;
    color: var(--tm); letter-spacing: .4px; text-transform: uppercase;
}}
[data-testid="stMetricValue"] {{
    font-family: 'Outfit', sans-serif;
    font-size: 1.55rem !important; font-weight: 700; color: var(--tp);
}}

/* ── Tabs (hide bar – navbar handles navigation visually) ── */
.stTabs [data-baseweb="tab-list"] {{
    display: none !important;
}}
.stTabs [data-baseweb="tab-panel"] {{
    padding-top: 0 !important;
}}

/* ── Buttons ── */
.stButton > button {{
    font-family: 'Inter', sans-serif; font-weight: 500;
    border-radius: 10px; transition: all .2s ease;
    background: var(--surface); color: var(--tp);
    border: 1px solid var(--border);
}}
.stButton > button:hover {{
    transform: translateY(-1px);
    box-shadow: 0 4px 14px rgba(0,0,0,.07);
}}
.stDownloadButton > button {{
    background: linear-gradient(135deg, var(--ac), #7b2cbf) !important;
    color: #fff !important; border: none !important;
    border-radius: 10px; font-weight: 500; transition: all .25s ease;
}}
.stDownloadButton > button:hover {{
    transform: translateY(-2px);
    box-shadow: 0 6px 22px rgba(67,97,238,.28);
}}

/* ── Data / Inputs ── */
[data-testid="stDataFrame"] {{
    border-radius: var(--r); overflow: hidden;
    border: 1px solid var(--border);
}}
.stSelectbox > div > div, .stMultiSelect > div > div {{
    border-radius: 10px; border-color: var(--border);
    background: var(--surface); color: var(--tp);
}}
/* Selected-option chips inside multiselect (e.g. "SMA 20" tag) —
   rectangular instead of the BaseWeb default rounded-pill shape. */
.stMultiSelect span[data-baseweb="tag"] {{
    border-radius: 5px !important;
}}
[data-testid="stTextInput"] > div > div {{
    border-radius: 14px !important;
    border: 1px solid var(--border) !important;
    background: var(--surface) !important;
    box-shadow: 0 2px 16px rgba(67,97,238,.04);
    padding: 2px 8px; transition: all .25s ease;
}}
[data-testid="stTextInput"] > div > div:focus-within {{
    border-color: var(--ac) !important;
    box-shadow: 0 4px 24px rgba(67,97,238,.10);
}}
[data-testid="stTextInput"] input {{ font-size: .95rem; padding: 10px 6px; color: var(--tp); }}

/* ── Typography ── */
h1, h2, h3 {{ font-family: 'Outfit', sans-serif !important; color: var(--tp); }}
p, span, div {{ color: inherit; }}
hr {{ border: none; border-top: 1px solid var(--border); margin: 1.5rem 0; }}

/* ── Footer ── */
.ninja-footer {{
    text-align: center; padding: 2rem 1rem; margin-top: 2.5rem;
    border-top: 1px solid var(--border);
    font-size: .8rem; color: var(--tm);
}}

/* ── Animation ── */
@keyframes fadeUp {{
    from {{ opacity: 0; transform: translateY(18px); }}
    to   {{ opacity: 1; transform: translateY(0); }}
}}

/* Active nav tab — highlighted as a solid pill, same treatment as the
   popular-stock tags / sector pills elsewhere in the app. */
.st-key-nav_btn_{active_nav} .stButton > button {{
    background: rgba(67, 97, 238, .14) !important;
    color: var(--ac) !important;
    font-weight: 600 !important;
}}
.st-key-nav_btn_{active_nav} .stButton > button:hover {{
    background: rgba(67, 97, 238, .20) !important;
    color: var(--ac) !important;
}}
</style>"""


# Backwards-compatible module-level constant (light theme, default).
NINJA_CSS = get_ninja_css("light")


# ── HTML generators ───────────────────────────

NAV_ITEMS = [
    ("home", "⌂ Home"),
    ("stocks", "🗠 Stocks"),
    ("movers", "𓉱 Market Movers"),
    ("company", "🗐 Company"),
]


def get_navbar_html(theme="light"):
    return (
        '<div class="ninja-nav">'
        f'<div class="nav-brand">{NINJA_SVG_SM}'
        '<span class="nav-brand-text">Nepse<em>Ninja</em></span></div>'
        '</div>'
    )


def is_market_open():
    """
    True during NEPSE's Mon–Fri 11:00–15:00 trading window.
    Shared by get_market_status() and the NEPSE index card.
    """
    now = _dt.datetime.now(ZoneInfo("Asia/Kathmandu"))
    wd = now.weekday()  # Mon=0 ... Sun=6
    h = now.hour
    trading = wd in (0, 1, 2, 3, 4)
    return trading and 11 <= h < 15


def get_market_status(index_snapshot=None):
    now = _dt.datetime.now(ZoneInfo("Asia/Kathmandu"))
    wd = now.weekday()  # Mon=0 ... Sun=6
    h = now.hour

    # Monday through Friday trading window (11:00 to 15:00)
    trading = wd in (0, 1, 2, 3, 4)
    is_open = is_market_open()

    days = ["Monday", "Tuesday", "Wednesday", "Thursday",
            "Friday", "Saturday", "Sunday"]

    if is_open:
        dot = '<span class="dot dot-green"></span>'
        s1, s2 = "Market Open", "Trading in progress"
    else:
        dot = '<span class="dot dot-red"></span>'
        s1 = "Market Closed"
        # Days jump mapping to next weekday
        nm = {0: 1, 1: 1, 2: 1, 3: 1, 4: 3, 5: 2, 6: 1}
        if trading and h < 11:
            s2 = "Opens today at 11:00"
        else:
            nd = (wd + nm.get(wd, 1)) % 7
            s2 = f"Opens {days[nd]}"

    index_html = ""
    index_value = index_snapshot.get("value") if index_snapshot else None
    index_percent = index_snapshot.get("percent") if index_snapshot else None
    index_points = index_snapshot.get("points") if index_snapshot else None
    if isinstance(index_value, (int, float)):
        index_html = (
            '<span class="mkt-index">NEPSE '
            f'<strong>{index_value:,.2f}</strong></span>'
        )
        if isinstance(index_percent, (int, float)):
            direction = "up" if index_percent >= 0 else "down"
            arrow = "↗" if index_percent >= 0 else "↘"
            index_html += (
                f' <span class="mkt-index-change {direction}">'
                f'{arrow} {index_percent:+.2f}%</span>'
            )
        if isinstance(index_points, (int, float)):
            direction = "up" if index_points >= 0 else "down"
            arrow = "▲" if index_points >= 0 else "▼"
            index_html += (
                f' <span class="mkt-index-change {direction}">'
                f'{arrow} {index_points:+.2f} pts</span>'
            )

    return (
        f'<span>{dot}{s1}</span>'
        f'<span class="sep"></span><span>{s2}</span>'
        f'<span class="sep"></span>{index_html}'
    )


def get_hero_html(market_html):
    return (
        f'<div class="hero"><div class="hero-logo">{NINJA_SVG_LG}</div>'
        '<h1 class="hero-title">Nepse<em>NINJA</em></h1>'
        f'<div class="mkt-badge">{market_html}</div></div>'
    )


def get_popular_tags_html(stocks, theme="light"):
    tags = "".join(
        f'<a href="?nav=home&theme={theme}&symbol={_urlquote(s)}" '
        f'target="_self" class="stock-tag">{s}</a>'
        for s in stocks
    )
    return f'<div class="pop-row"><span class="pop-label">POPULAR:</span>{tags}</div>'


_SECTOR_CLS = {
    "Commercial Banks": "cb", "Development Banks": "db",
    "Hydropower": "hp", "Life Insurance": "li",
    "Non Life Insurance": "ni", "Finance": "fi",
    "Microfinance": "mf", "Hotels And Tourism": "ht",
    "Hotels/Tourism": "ht", "Manufacturing And Processing": "mg",
    "Manufacturing": "mg", "Trading": "tr",
    "Investment": "in", "Mutual Fund": "in", "Others": "ot",
}

# Public alias so other modules (e.g. the main app) can reuse this mapping
# to color-code their own widgets (e.g. Streamlit buttons) to match.
SECTOR_CLASS_MAP = _SECTOR_CLS


def get_sector_pills_html(sectors, theme="light", active_sector=None):
    pills = []
    for s in sectors:
        c = _SECTOR_CLS.get(s, "ot")
        active_cls = " pill-active" if s == active_sector else ""
        href = f"?nav=home&theme={theme}&sector={_urlquote(s)}"
        pills.append(
            f'<a href="{href}" target="_self" class="pill p-{c}{active_cls}">{s}</a>'
        )
    return f'<div class="pill-row">{"".join(pills)}</div>'


def get_nepse_index_card_html(snapshot, breadth, theme="light"):
    """
    snapshot: dict or None — {"value": 2542.77, "points": 4.66, "percent": 0.18}
        `points`/`percent` may be None even if `value` is known.
    breadth: dict — {"up": int, "flat": int, "down": int}
    Renders the "NEPSE INDEX" snapshot card (value, change, market
    status, sentiment tag, breadth) shown above Stock Symbol Analysis.
    """
    is_open = is_market_open()
    status_label = "OPEN" if is_open else "CLOSED"
    status_dot_cls = "open" if is_open else "closed"

    value = snapshot.get("value") if snapshot else None
    points = snapshot.get("points") if snapshot else None
    percent = snapshot.get("percent") if snapshot else None

    value_html = f"{value:,.2f}" if isinstance(value, (int, float)) else "N/A"

    change_html = ""
    if isinstance(percent, (int, float)):
        direction = "up" if percent >= 0 else "down"
        arrow = "↗" if percent >= 0 else "↘"
        change_html += (
            f'<span class="nic-change-pill {direction}">'
            f'{arrow} {percent:+.2f}%</span>'
        )
    if isinstance(points, (int, float)):
        direction = "up" if points >= 0 else "down"
        tri = "▲" if points >= 0 else "▼"
        change_html += (
            f'<span class="nic-points {direction}">{tri} {points:+.2f} pts</span>'
        )

    up, flat, down = (
        breadth.get("up", 0),
        breadth.get("flat", 0),
        breadth.get("down", 0),
    )

    # Sentiment: prefer the actual index % change; fall back to
    # market breadth (advancers vs decliners) when no index % is known.
    if isinstance(percent, (int, float)):
        score = percent
    elif (up + down) > 0:
        score = (up - down) / (up + down) * 100
    else:
        score = 0

    if score > 3:
        sentiment_cls, sentiment_label = "bullish", "BULLISH"
    elif score > 0.05:
        sentiment_cls, sentiment_label = "bullish", "LEANING BULLISH"
    elif score < -3:
        sentiment_cls, sentiment_label = "bearish", "BEARISH"
    elif score < -0.05:
        sentiment_cls, sentiment_label = "bearish", "LEANING BEARISH"
    else:
        sentiment_cls, sentiment_label = "neutral", "NEUTRAL"

    return (
        '<div class="nepse-index-card">'
        '<div class="nic-top">'
        '<div class="nic-label"><span class="dot"></span>NEPSE INDEX</div>'
        '<div class="nic-top-right">'
        f'<span class="nic-status-pill"><span class="dot {status_dot_cls}"></span>{status_label}</span>'
        f'<a href="?nav=stocks&theme={theme}&expand_index=1" '
        f'target="_self" class="nic-expand" title="Open live NEPSE chart">⤢</a>'
        "</div>"
        "</div>"
        '<div class="nic-mid">'
        f'<span class="nic-value">{value_html}</span>'
        f'<div class="nic-change-col">{change_html}</div>'
        "</div>"
        '<div class="nic-bottom">'
        f'<span class="nic-sentiment-pill {sentiment_cls}">'
        f'<span class="dot"></span>{sentiment_label}</span>'
        f'<span class="nic-breadth">'
        f'<span class="dot up"></span>{up} up'
        f'<span class="nic-breadth-sep">·</span>'
        f'<span class="dot flat"></span>{flat} flat'
        f'<span class="nic-breadth-sep">·</span>'
        f'<span class="dot down"></span>{down} down'
        f'</span>'
        "</div>"
        "</div>"
    )


def get_ai_recommendation_card_html(verdict, summary, reasons=None, theme="light"):
    """
    verdict: "BUY" | "SELL" | "HOLD"
    summary: short paragraph explaining the call (plain text, no HTML).
    reasons: optional list of short strings shown as chips, e.g.
        ["Negative EPS", "P/E 42.1x", "ROE -3.2%"]
    Renders the split "AI RECOMMENDATION" card used on the Company /
    Symbol Analysis tab, directly under the fundamentals the verdict
    was derived from.
    """
    verdict = (verdict or "HOLD").upper()
    cls = {"BUY": "buy", "SELL": "sell"}.get(verdict, "hold")

    reasons_html = ""
    if reasons:
        chips = "".join(f'<span class="ai-rec-chip">{r}</span>' for r in reasons)
        reasons_html = f'<div class="ai-rec-reasons">{chips}</div>'

    return (
        '<div class="ai-rec-card">'
        f'<div class="ai-rec-left {cls}">'
        '<span class="ai-rec-eyebrow">AI Recommendation</span>'
        f'<span class="ai-rec-verdict {cls}">{verdict}</span>'
        "</div>"
        '<div class="ai-rec-body">'
        f'<div class="ai-rec-summary">{summary}</div>'
        f"{reasons_html}"
        '<div class="ai-rec-disclaimer">'
        "Auto-generated from reported fundamentals — not financial advice. "
        "Verify independently before trading."
        "</div>"
        "</div>"
        "</div>"
    )


def get_search_suggestions_html(matches, total_count, theme="light"):
    """
    matches: list of dicts like
        {"symbol": "NABIL", "name": "Nabil Bank Limited", "sector": "Commercial Banks"}
    Renders a live suggestions card under the home search box, showing
    each match's full company name and sector tag, plus a footer with
    the total number of stocks loaded — matching the sector-modal
    row style so the whole app stays visually consistent.
    """
    rows = []
    for m in matches:
        sym = (m.get("symbol") or "").strip()
        name = (m.get("name") or "").strip()
        sector = (m.get("sector") or "").strip()
        c = _SECTOR_CLS.get(sector, "ot")
        href = f"?nav=home&theme={theme}&symbol={_urlquote(sym)}"
        tag_html = (
            f'<span class="company-tag p-{c}">{sector.upper()}</span>'
            if sector
            else ""
        )
        rows.append(
            f'<a href="{href}" target="_self" class="company-row">'
            f'<span class="company-symbol">{sym}</span>'
            f'<span class="company-name">{name}</span>'
            f"{tag_html}"
            f"</a>"
        )

    body = (
        "".join(rows)
        if rows
        else '<div class="search-suggest-empty">No matching stocks found.</div>'
    )

    footer = (
        f'<div class="search-suggest-footer">'
        f"{total_count} stocks loaded · Type to filter"
        f"</div>"
    )

    return (
        '<div class="search-suggest-wrap">'
        f'<div class="search-suggest-panel">{body}{footer}</div>'
        "</div>"
    )


def get_company_list_modal_html(sector, companies, theme="light"):
    """
    companies: list of dicts like {"symbol": "ADBL", "name": "Agriculture Development Bank Limited"}
    Renders a centered modal (click backdrop or the ✕ to close) listing the companies in `sector`.
    """
    c = _SECTOR_CLS.get(sector, "ot")
    close_href = f"?nav=home&theme={theme}"

    rows = []
    for comp in companies:
        sym = (comp.get("symbol") or "").strip()
        name = (comp.get("name") or "").strip()
        row_href = f"?nav=stocks&theme={theme}&symbol={_urlquote(sym)}"
        rows.append(
            f'<a href="{row_href}" target="_self" class="company-row">'
            f'<span class="company-symbol">{sym}</span>'
            f'<span class="company-name">{name}</span>'
            f'<span class="company-tag p-{c}">{sector.upper()}</span>'
            
            f"</a>"
        )

    rows_html = (
        "".join(rows)
        if rows
        else '<div class="company-row-empty">No companies found for this sector.</div>'
    )

    return (
        f'<a href="{close_href}" target="_self" class="sector-modal-backdrop"></a>'
        '<div class="sector-modal">'
        '<div class="sector-modal-header">'
        f'<span class="sector-modal-title">{sector} '
        f'<span class="sector-modal-count">({len(companies)})</span></span>'
        f'<a href="{close_href}" target="_self" class="sector-modal-close">✕</a>'
        "</div>"
        f'<div class="sector-modal-body">{rows_html}</div>'
        "</div>"
    )