"""
NEPSE Ninja - Custom Theme & UI Components
"""
import datetime as _dt

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
def get_ninja_css(theme="light"):
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

    return f"""<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800;900&family=Outfit:wght@300;400;500;600;700;800;900&display=swap');

#MainMenu, header, footer, .stDeployButton {{ display: none !important; }}
[data-testid="stSidebar"] {{ display: none; }}

:root {{{vars_block}}}

html, body, .stApp {{
    background: var(--bg1) !important;
    color: var(--tp);
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
.nav-brand {{ display: flex; align-items: center; gap: 10px; }}
.nav-brand-text {{
    font-family: 'Outfit', sans-serif; font-weight: 800;
    font-size: 1.15rem; color: var(--tp);
}}
.nav-brand-text em {{ font-style: normal; color: var(--ag); }}
.nav-links {{ display: flex; gap: 4px; align-items: center; }}
.nav-links a {{
    font-size: .82rem; font-weight: 500;
    padding: 6px 14px; border-radius: 8px; color: var(--tm);
    text-decoration: none;
}}
.nav-links a.nav-active {{ background: var(--ac); color: #fff; }}
[data-testid="stRadio"] {{
    position: fixed; top: 0; left: 50%; z-index: 1001;
    transform: translateX(-50%);
    height: 56px; display: flex; align-items: center;
}}
[data-testid="stRadio"] > label {{ display: none !important; }}
[data-testid="stRadio"] [role="radiogroup"] {{ gap: 4px; }}
[data-testid="stRadio"] [role="radio"] {{
    min-height: 30px; padding: 6px 14px; border-radius: 8px;
    color: var(--tm); font-size: .82rem; font-weight: 500;
}}
[data-testid="stRadio"] [role="radio"][aria-checked="true"] {{
    background: var(--ac); color: #fff;
}}
[data-testid="stRadio"] [role="radio"] > div:first-child {{ display: none; }}
[data-testid="stRadio"] [role="radio"] p {{ margin: 0; }}
.nav-right {{ display: flex; align-items: center; gap: 10px; }}
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
.theme-toggle:hover {{ transform: translateY(-1px) scale(1.05); }}

.block-container {{ padding-top: 76px !important; max-width: 1200px; }}

/* ── Hero ── */
.hero {{
    text-align: center; padding: 2.5rem 1rem 1rem;
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
    transition: all .2s ease;
}}

/* ── Sector pills ── */
.pill-row {{
    text-align: center; margin: .6rem auto;
    max-width: 780px; animation: fadeUp .55s ease-out .32s both;
}}
.pill {{
    display: inline-block; padding: 5px 15px; margin: 3px;
    border-radius: 18px; font-size: .76rem; font-weight: 500;
    border: 1.4px solid; transition: all .22s ease;
}}
.pill:hover {{ transform: translateY(-2px); box-shadow: 0 4px 14px rgba(0,0,0,.08); }}
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

/* ── Metric cards ── */
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
</style>"""


# Backwards-compatible module-level constant (light theme, default).
NINJA_CSS = get_ninja_css("light")


# ── HTML generators ───────────────────────────

def get_navbar_html(active_nav="home", theme="light"):
    links = [
        ("home", "🏠 Home"),
        ("stocks", "📊 Stocks"),
        ("company", "🏢 Company"),
    ]
    # Added target="_self" to keep tabs in the same window
    nav_links = "".join(
        f'<a href="?nav={key}&theme={theme}" target="_self" class="{"nav-active" if active_nav == key else ""}">{label}</a>'
        for key, label in links
    )
    next_theme = toggle_theme(theme)
    toggle_icon = "🌙" if theme == "light" else "☀️"
    return (
        '<div class="ninja-nav">'
        f'<div class="nav-brand">{NINJA_SVG_SM}'
        '<span class="nav-brand-text">Nepse<em>Ninja</em></span></div>'
        f'<div class="nav-links">{nav_links}</div>'
        '<div class="nav-right">'
        f'<a href="?nav={active_nav}&theme={next_theme}" target="_self" class="theme-toggle" title="Toggle theme">{toggle_icon}</a>'
        '</div></div>'
    )


def get_market_status():
    now = _dt.datetime.now()
    wd = now.weekday()  # Mon=0 ... Sun=6
    h = now.hour

    # Monday through Friday trading window (11:00 to 15:00)
    trading = wd in (0, 1, 2, 3, 4)
    is_open = trading and 11 <= h < 15

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

    return (
        f'<span>{dot}{s1}</span>'
        f'<span class="sep"></span><span>{s2}</span>'
        f'<span class="sep"></span>'
    )


def get_hero_html(market_html):
    return (
        f'<div class="hero"><div class="hero-logo">{NINJA_SVG_LG}</div>'
        '<h1 class="hero-title">Nepse<em>NINJA</em></h1>'
        f'<div class="mkt-badge">{market_html}</div></div>'
    )


def get_popular_tags_html(stocks):
    tags = "".join(f'<span class="stock-tag">{s}</span>' for s in stocks)
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


def get_sector_pills_html(sectors):
    pills = []
    for s in sectors:
        c = _SECTOR_CLS.get(s, "ot")
        pills.append(f'<span class="pill p-{c}">{s}</span>')
    return f'<div class="pill-row">{"".join(pills)}</div>'