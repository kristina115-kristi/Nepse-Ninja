from __future__ import annotations

from pathlib import Path
from io import StringIO
import re

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components
import requests
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import datetime as _dt
import importlib
import ninja_theme as _ninja_theme

importlib.reload(_ninja_theme)

from ninja_theme import (
    get_ninja_css,
    get_theme,
    toggle_theme,
    get_navbar_html,
    get_hero_html,
    get_market_status,
    get_popular_tags_html,
    get_sector_pills_html,
    get_company_list_modal_html,
    get_search_suggestions_html,
    get_nepse_index_card_html,
    get_ai_recommendation_card_html,
    SECTOR_CLASS_MAP,
    NAV_ITEMS,
)


# ============================================================
# PAGE CONFIG
# ============================================================

st.set_page_config(
    page_title="NEPSE Ninja – Nepal Stock Analysis",
    page_icon="🥷",
    layout="wide",
    initial_sidebar_state="collapsed",
)


# ============================================================
# DEBUG FLAG
# ============================================================
# Set this to True locally (or drive it from an env var / secrets)
# to see full technical error details. Keep False in production
# so end users never see file paths or shell commands.

DEBUG_MODE = False

try:
    import os
    DEBUG_MODE = os.environ.get("NEPSE_DEBUG", "false").lower() == "true"
except Exception:
    DEBUG_MODE = False


# ============================================================
# THEME + NAVIGATION
# ============================================================
# Both live in session_state so switching tabs or the color theme is
# a real Streamlit widget interaction — an in-place script rerun over
# the already-open connection — instead of a browser navigation.
# session_state is only seeded from the URL once per session (e.g. on
# first load, or after a full reload triggered by an in-page link
# like a stock/sector tag), so deep links still work.

_nav_key_list = [key for key, _ in NAV_ITEMS]

if "active_nav" not in st.session_state:
    _seed_nav = st.query_params.get("nav", "home")
    if isinstance(_seed_nav, list):
        _seed_nav = _seed_nav[0] if _seed_nav else "home"
    st.session_state["active_nav"] = (
        _seed_nav if _seed_nav in _nav_key_list else "home"
    )

if "active_theme" not in st.session_state:
    st.session_state["active_theme"] = get_theme(st.query_params)

active_nav = st.session_state["active_nav"]
active_theme = st.session_state["active_theme"]

st.markdown(
    get_ninja_css(active_theme, active_nav),
    unsafe_allow_html=True,
)

st.markdown(
    get_navbar_html(active_theme),
    unsafe_allow_html=True,
)

# Nav tabs + theme toggle as real st.button widgets, wrapped in
# st.container(key=...) so Streamlit's own ".st-key-<key>" class (see
# ninja_theme.py) can fixed-position them to sit inside the navbar
# above. A click updates session_state and calls st.rerun() — an
# in-place rerun over the already-open connection, no full page
# reload, no flash.
with st.container(key="nepse_nav_row"):
    _nav_cols = st.columns(len(NAV_ITEMS))
    for _nav_col, (_nav_key, _nav_label) in zip(_nav_cols, NAV_ITEMS):
        with _nav_col:
            if st.button(_nav_label, key=f"nav_btn_{_nav_key}"):
                st.session_state["active_nav"] = _nav_key
                st.query_params["nav"] = _nav_key
                st.rerun()

_theme_icon = "🌙" if active_theme == "light" else "☀️"
if st.button(_theme_icon, key="theme_toggle_btn", help="Toggle theme"):
    _next_theme = toggle_theme(active_theme)
    st.session_state["active_theme"] = _next_theme
    st.query_params["theme"] = _next_theme
    st.rerun()


# ============================================================
# PATH SETTINGS
# ============================================================

# FIX #1: Anchor BASE_DIR to the script's own location instead of
# the process's current working directory. Path.cwd() depends on
# *where the app was launched from*, which can vary (VS Code run
# button, terminal, service manager, Docker, hosting platform),
# causing the data file to "not be found" and dumping raw file
# paths / commands onto the page via the old error branch.
BASE_DIR = Path(__file__).resolve().parent

DEFAULT_PROCESSED_DIR = (
    BASE_DIR / "nepse_data" / "processed"
)

ALL_DATA_FILE = "NEPSE_ALL_DATA.csv"
LATEST_DAY_FILE = "NEPSE_LATEST_DAY.csv"
RECENT_FILE = "NEPSE_RECENT_30_DAYS.csv"
COVERAGE_FILE = "NEPSE_SYMBOL_COVERAGE.csv"
DAILY_SUMMARY_FILE = "NEPSE_DAILY_SUMMARY.csv"
LIVE_MARKET_URL = "https://www.sharesansar.com/today-share-price"
LIVE_INDEX_URL = "https://www.sharesansar.com/market"

# These are now optional/legacy.
# Financial fundamentals come from the online API.
FINANCIAL_FILE = "nepsealpha_financials.csv"
RATIO_FILE = "nepsealpha_output/nepsealpha_ratios.csv"
DIVIDEND_FILE = "dividends.csv"

processed_dir = DEFAULT_PROCESSED_DIR

all_data_path = (
    processed_dir / ALL_DATA_FILE
)


# ============================================================
# HELPER FUNCTIONS
# ============================================================

@st.cache_data(show_spinner=False)
def load_csv(path: str, parse_dates=None) -> pd.DataFrame:

    file_path = Path(path)

    if not file_path.exists():
        return pd.DataFrame()

    return pd.read_csv(
        file_path,
        parse_dates=parse_dates,
        low_memory=False,
    )


def extract_market_date(page_html: str) -> str:
    for marker in re.finditer(r"As\s+(?:on|of)", page_html, flags=re.IGNORECASE):
        nearby = page_html[marker.start(): marker.start() + 500]
        date_match = re.search(r"20\d{2}-\d{2}-\d{2}", nearby)
        if date_match:
            return date_match.group(0)
    return _dt.date.today().isoformat()


@st.cache_data(show_spinner=False)
def load_prepared_csv(path: str, modified_ns: int) -> pd.DataFrame:
    return prepare_all_data(load_csv(path))


# ------------------------------------------------------------
# Live-fetch failure backoff
# ------------------------------------------------------------
# Root cause of "everything feels slow": these live scrapes are
# decorated with @st.cache_data, which only caches *successful*
# calls. When ShareSansar is slow/unreachable, every single rerun
# of the app (literally any button click anywhere) re-attempts the
# same 30-second-timeout request before failing — so one flaky
# endpoint stalls the entire UI. This records recent failures in
# session_state and skips straight to raising for a short cooldown
# instead of hitting the network again on every rerun.
_LIVE_FETCH_TIMEOUT = 8
_LIVE_FETCH_BACKOFF_SECONDS = 5 * 60


def _call_with_backoff(name: str, fetch_fn):
    state_key = f"_live_fetch_backoff::{name}"
    now = _dt.datetime.now().timestamp()
    retry_after = st.session_state.get(state_key, 0)

    if now < retry_after:
        raise RuntimeError(
            f"{name} failed recently; skipping retry for "
            f"{int(retry_after - now)}s to keep the app responsive."
        )

    try:
        return fetch_fn()
    except Exception:
        st.session_state[state_key] = now + _LIVE_FETCH_BACKOFF_SECONDS
        raise


@st.cache_data(ttl=15 * 60, show_spinner=False)
def load_live_market_data() -> pd.DataFrame:
    """Load the latest NEPSE trading table published by ShareSansar."""
    response = requests.get(
        LIVE_MARKET_URL,
        headers={"User-Agent": "Mozilla/5.0"},
        timeout=_LIVE_FETCH_TIMEOUT,
    )
    response.raise_for_status()

    tables = pd.read_html(StringIO(response.text))
    if not tables:
        raise ValueError("The live market page did not contain a price table.")

    live = tables[0].rename(
        columns={
            "Symbol": "symbol",
            "Open": "open",
            "High": "high",
            "Low": "low",
            "Close": "close",
            "Vol": "traded_quantity",
            "Turnover": "traded_amount",
            "Diff %": "per_change",
        }
    )
    required = {
        "symbol",
        "open",
        "high",
        "low",
        "close",
        "traded_quantity",
        "traded_amount",
        "per_change",
    }
    missing = required.difference(live.columns)
    if missing:
        raise ValueError(f"Live market table is missing: {', '.join(sorted(missing))}")

    live = live[list(required)].copy()
    live["published_date"] = extract_market_date(response.text)
    live["status"] = pd.NA
    live["return"] = pd.NA
    live["return_percent"] = pd.NA
    live["return_gap_pp"] = pd.NA
    return live

@st.cache_data(ttl=15 * 60, show_spinner=False)
def load_live_nepse_index() -> dict:
    """Load the latest NEPSE index value published by ShareSansar."""
    response = requests.get(
        LIVE_INDEX_URL,
        headers={"User-Agent": "Mozilla/5.0"},
        timeout=_LIVE_FETCH_TIMEOUT,
    )
    response.raise_for_status()

    for table in pd.read_html(StringIO(response.text)):
        if table.empty:
            continue

        if "Index" not in table.columns or "Close" not in table.columns:
            continue

        for _, row in table.iterrows():
            if str(row.get("Index", "")).strip().lower() != "nepse index":
                continue

            value = pd.to_numeric(
                pd.Series([row["Close"]]), errors="coerce"
            ).iloc[0]
            points = pd.to_numeric(
                pd.Series([row.get("Point Change")]), errors="coerce"
            ).iloc[0]
            if pd.isna(value):
                continue

            value = float(value)
            points = None if pd.isna(points) else float(points)
            previous = value - points if points is not None else None
            percent = (
                points / previous * 100
                if previous not in (None, 0)
                else None
            )
            return {
                "value": value,
                "points": points,
                "percent": percent,
            }

    raise ValueError("The live page did not contain a NEPSE Index row.")


@st.cache_data(ttl=15 * 60, show_spinner=False)
def load_live_nepse_index_history() -> pd.DataFrame:
    """Load recent NEPSE OHLC history from ShareSansar."""
    response = requests.get(
        "https://www.sharesansar.com/index-history-data",
        headers={"User-Agent": "Mozilla/5.0"},
        timeout=_LIVE_FETCH_TIMEOUT,
    )
    response.raise_for_status()

    for table in pd.read_html(StringIO(response.text)):
        def normalize_column(column):
            if isinstance(column, tuple):
                parts = [
                    str(part).strip()
                    for part in column
                    if str(part).strip()
                    and not str(part).lower().startswith("unnamed")
                ]
                column = parts[-1] if parts else ""
            return re.sub(r"[^a-z]+", " ", str(column).lower()).strip()

        normalized = {
            column: normalize_column(column)
            for column in table.columns
        }
        required = {"open", "high", "low", "close"}
        if not required.issubset(set(normalized.values())):
            continue

        source_columns = {value: key for key, value in normalized.items()}
        date_column = next(
            (
                key
                for key, value in normalized.items()
                if value in {"date", "published date", "trading date"}
            ),
            None,
        )
        turnover_column = next(
            (key for key, value in normalized.items() if "turnover" in value), None
        )
        if date_column is None:
            continue

        history = pd.DataFrame(
            {
                "published_date": pd.to_datetime(
                    table[date_column], errors="coerce"
                ),
                "open": pd.to_numeric(table[source_columns["open"]], errors="coerce"),
                "high": pd.to_numeric(table[source_columns["high"]], errors="coerce"),
                "low": pd.to_numeric(table[source_columns["low"]], errors="coerce"),
                "close": pd.to_numeric(table[source_columns["close"]], errors="coerce"),
                "volume": (
                    pd.to_numeric(table[turnover_column], errors="coerce")
                    if turnover_column is not None
                    else pd.NA
                ),
            }
        )
        return history.dropna(subset=["published_date", "close"]).sort_values(
            "published_date"
        ).reset_index(drop=True)

    return pd.DataFrame()


def merge_live_market_data(
    historical: pd.DataFrame,
    live: pd.DataFrame,
) -> pd.DataFrame:
    if live.empty:
        return historical

    merged = pd.concat([historical, live], ignore_index=True, sort=False)
    merged["published_date"] = pd.to_datetime(
        merged["published_date"], errors="coerce"
    )
    merged = merged.drop_duplicates(
        subset=["published_date", "symbol"], keep="last"
    )
    return prepare_all_data(merged)


def safe_numeric(series: pd.Series) -> pd.Series:

    return pd.to_numeric(
        series,
        errors="coerce",
    )


def format_number(value, decimals=2):

    if value is None:
        return "N/A"

    try:

        if pd.isna(value):
            return "N/A"

    except Exception:
        pass

    try:
        return f"{float(value):,.{decimals}f}"

    except Exception:
        return str(value)


def format_integer(value):

    if value is None:
        return "N/A"

    try:

        if pd.isna(value):
            return "N/A"

    except Exception:
        pass

    try:
        return f"{int(value):,}"

    except Exception:
        return str(value)


def csv_bytes(df: pd.DataFrame) -> bytes:

    return df.to_csv(
        index=False
    ).encode("utf-8-sig")


def prepare_all_data(
    df: pd.DataFrame,
) -> pd.DataFrame:

    if df.empty:
        return df

    df = df.copy()

    if "published_date" in df.columns:

        df["published_date"] = pd.to_datetime(
            df["published_date"],
            errors="coerce",
        )

    numeric_columns = [
        "open",
        "high",
        "low",
        "close",
        "per_change",
        "traded_quantity",
        "traded_amount",
        "status",
        "return",
        "return_percent",
        "return_gap_pp",
    ]

    for column in numeric_columns:

        if column in df.columns:

            df[column] = safe_numeric(
                df[column]
            )

    if "symbol" in df.columns:

        df["symbol"] = (
            df["symbol"]
            .astype(str)
            .str.strip()
            .str.upper()
        )

    # The live ShareSansar scrape (load_live_market_data) never fills in
    # return/return_percent — it sets them to NA and leaves it at that
    # (see the comment there). Since the live row is usually the most
    # recent trading day for a symbol, that NA was surfacing as "N/A"
    # for "Latest Return %" on the Company/Symbol Analysis page even
    # though we have everything needed (yesterday's close from history)
    # to compute it ourselves. Backfill any missing return/return_percent
    # from the day-over-day close change, per symbol, without touching
    # values that already came from the source data.
    if {"symbol", "published_date", "close"}.issubset(df.columns):
        df = df.sort_values(["symbol", "published_date"])
        prev_close = df.groupby("symbol")["close"].shift(1)
        safe_prev_close = prev_close.replace(0, pd.NA)
        computed_return = df["close"] - prev_close
        computed_return_percent = (
            (df["close"] - safe_prev_close) / safe_prev_close * 100
        )

        if "return" in df.columns:
            df["return"] = df["return"].where(
                df["return"].notna(), computed_return
            )
        else:
            df["return"] = computed_return

        if "return_percent" in df.columns:
            df["return_percent"] = df["return_percent"].where(
                df["return_percent"].notna(), computed_return_percent
            )
        else:
            df["return_percent"] = computed_return_percent

    return (
        df
        .sort_values(
            ["symbol", "published_date"]
        )
        .reset_index(drop=True)
    )


def calculate_summary(df: pd.DataFrame):

    if df.empty:

        return {
            "symbols": 0,
            "rows": 0,
            "earliest": None,
            "latest": None,
        }

    return {

        "symbols":
            df["symbol"].nunique()
            if "symbol" in df.columns
            else 0,

        "rows":
            len(df),

        "earliest":
            df["published_date"].min()
            if "published_date" in df.columns
            else None,

        "latest":
            df["published_date"].max()
            if "published_date" in df.columns
            else None,
    }


def get_6month_data(
    df: pd.DataFrame,
    symbol: str,
) -> pd.DataFrame:

    if (
        df.empty
        or "published_date" not in df.columns
    ):
        return pd.DataFrame()

    symbol = str(symbol).strip().upper()

    df_filtered = df[
        df["symbol"] == symbol
    ].copy()

    if df_filtered.empty:
        return df_filtered

    latest_date = (
        df_filtered["published_date"].max()
    )

    six_months_ago = (
        latest_date
        - pd.Timedelta(days=180)
    )

    return (
        df_filtered[
            df_filtered["published_date"]
            >= six_months_ago
        ]
        .sort_values("published_date")
        .reset_index(drop=True)
    )


def calculate_moving_averages(
    df: pd.DataFrame,
    close_col: str = "close",
) -> pd.DataFrame:

    df = df.copy()

    if close_col in df.columns:

        df["ma_20"] = (
            df[close_col]
            .rolling(window=20)
            .mean()
        )

        df["ma_50"] = (
            df[close_col]
            .rolling(window=50)
            .mean()
        )

    return df


def calculate_metrics(
    df: pd.DataFrame,
) -> dict:

    if df.empty:

        return {
            "current_price": None,
            "total_return": None,
            "avg_daily_return": None,
            "highest": None,
            "lowest": None,
        }

    if "published_date" in df.columns:

        df = df.sort_values(
            "published_date"
        )

    metrics = {}

    if "close" in df.columns:

        latest_close = df["close"].iloc[-1]

        earliest_close = df["close"].iloc[0]

        metrics["current_price"] = (
            latest_close
        )

        metrics["highest"] = (
            df["close"].max()
        )

        metrics["lowest"] = (
            df["close"].min()
        )

        if (
            pd.notna(earliest_close)
            and earliest_close > 0
        ):

            metrics["total_return"] = (
                (
                    latest_close
                    - earliest_close
                )
                / earliest_close
            ) * 100

        else:

            metrics["total_return"] = 0

    if "return_percent" in df.columns:

        returns = (
            df["return_percent"]
            .dropna()
        )

        metrics["avg_daily_return"] = (
            returns.mean()
            if not returns.empty
            else 0
        )

    else:

        metrics["avg_daily_return"] = 0

    return metrics


def generate_buy_sell_signals(
    df: pd.DataFrame,
) -> pd.DataFrame:

    df = df.copy()

    df["signal"] = None

    if not all(
        col in df.columns
        for col in ["ma_20", "ma_50"]
    ):

        return df

    for i in range(1, len(df)):

        prev_ma20 = df.iloc[i - 1]["ma_20"]
        prev_ma50 = df.iloc[i - 1]["ma_50"]

        curr_ma20 = df.iloc[i]["ma_20"]
        curr_ma50 = df.iloc[i]["ma_50"]

        if (
            pd.notna(prev_ma20)
            and pd.notna(prev_ma50)
            and pd.notna(curr_ma20)
            and pd.notna(curr_ma50)
        ):

            if (
                prev_ma20 <= prev_ma50
                and curr_ma20 > curr_ma50
            ):

                df.at[i, "signal"] = "BUY"

            elif (
                prev_ma20 >= prev_ma50
                and curr_ma20 < curr_ma50
            ):

                df.at[i, "signal"] = "SELL"

    return df


def price_n_days_ago(
    df: pd.DataFrame,
    as_of_date,
    days_ago: int,
):

    target_date = (
        as_of_date
        - pd.Timedelta(days=days_ago)
    )

    past = df[
        df["published_date"]
        <= target_date
    ]

    if past.empty:
        return None

    row = (
        past
        .sort_values("published_date")
        .iloc[-1]
    )

    return (
        row["close"],
        row["published_date"],
    )


def show_period_changes(
    symbol_data: pd.DataFrame,
    symbol_name: str,
):

    symbol_data = (
        symbol_data
        .sort_values("published_date")
    )

    latest_row = symbol_data.iloc[-1]

    latest_price = latest_row["close"]

    latest_date = (
        latest_row["published_date"]
    )

    st.subheader(
        f"{symbol_name} — Profit / Loss"
    )

    st.caption(
        f"Latest close: "
        f"{latest_price:,.2f} "
        f"on {latest_date.date()}"
    )

    periods = {
        "2 Days": 2,
        "1 Week": 7,
        "1 Month": 30,
    }

    if "pl_period" not in st.session_state:

        st.session_state.pl_period = (
            "1 Week"
        )

    button_cols = st.columns(
        len(periods)
    )

    for col, label in zip(
        button_cols,
        periods.keys(),
    ):

        is_selected = (
            st.session_state.pl_period
            == label
        )

        button_type = (
            "primary"
            if is_selected
            else "secondary"
        )

        if col.button(
            label,
            key=f"btn_{label}",
            type=button_type,
            use_container_width=True,
        ):

            st.session_state.pl_period = (
                label
            )

    selected_label = (
        st.session_state.pl_period
    )

    days = periods[selected_label]

    result = price_n_days_ago(
        symbol_data,
        latest_date,
        days,
    )

    if result is None:

        st.info(
            f"No trading data available "
            f"from {selected_label.lower()} ago."
        )

        return

    past_price, past_date = result

    change = (
        latest_price
        - past_price
    )

    pct_change = (
        (change / past_price) * 100
        if past_price
        else 0
    )

    st.metric(
        label=(
            f"Change vs "
            f"{selected_label} ago "
            f"({past_date.date()})"
        ),
        value=f"{latest_price:,.2f}",
        delta=(
            f"{change:+,.2f} "
            f"({pct_change:+.2f}%)"
        ),
    )

    st.caption(
        "Green = profit if bought on that date. "
        "Red = loss if bought on that date."
    )


def create_candlestick_chart(
    df: pd.DataFrame,
) -> go.Figure:

    if (
        df.empty
        or not all(
            col in df.columns
            for col in [
                "open",
                "high",
                "low",
                "close",
            ]
        )
    ):

        return None

    df_chart = df.copy()

    if "published_date" in df_chart.columns:

        df_chart = (
            df_chart
            .sort_values("published_date")
        )

    df_chart = (
        calculate_moving_averages(
            df_chart
        )
    )

    df_chart = (
        generate_buy_sell_signals(
            df_chart
        )
    )

    fig = make_subplots(
        rows=2,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.08,
        row_heights=[0.7, 0.3],
    )

    candlestick_trace = go.Candlestick(

        x=df_chart["published_date"],

        open=df_chart["open"],

        high=df_chart["high"],

        low=df_chart["low"],

        close=df_chart["close"],

        name="OHLC",
    )

    fig.add_trace(
        candlestick_trace,
        row=1,
        col=1,
    )

    if "ma_20" in df_chart.columns:

        fig.add_trace(

            go.Scatter(

                x=df_chart[
                    "published_date"
                ],

                y=df_chart["ma_20"],

                name="20-day MA",

                line=dict(
                    color="orange",
                    width=2,
                ),
            ),

            row=1,
            col=1,
        )

    if "ma_50" in df_chart.columns:

        fig.add_trace(

            go.Scatter(

                x=df_chart[
                    "published_date"
                ],

                y=df_chart["ma_50"],

                name="50-day MA",

                line=dict(
                    color="red",
                    width=2,
                ),
            ),

            row=1,
            col=1,
        )

    buy_signals = df_chart[
        df_chart["signal"] == "BUY"
    ]

    if not buy_signals.empty:

        fig.add_trace(

            go.Scatter(

                x=buy_signals[
                    "published_date"
                ],

                y=buy_signals["low"],

                mode="markers",

                marker=dict(
                    size=12,
                    color="green",
                    symbol="triangle-up",
                ),

                name="BUY Signal",

                text=buy_signals[
                    "published_date"
                ].dt.strftime(
                    "%Y-%m-%d"
                ),

                hovertemplate=(
                    "<b>BUY</b>"
                    "<br>Date: %{text}"
                    "<extra></extra>"
                ),
            ),

            row=1,
            col=1,
        )

    sell_signals = df_chart[
        df_chart["signal"] == "SELL"
    ]

    if not sell_signals.empty:

        fig.add_trace(

            go.Scatter(

                x=sell_signals[
                    "published_date"
                ],

                y=sell_signals["high"],

                mode="markers",

                marker=dict(
                    size=12,
                    color="red",
                    symbol="triangle-down",
                ),

                name="SELL Signal",

                text=sell_signals[
                    "published_date"
                ].dt.strftime(
                    "%Y-%m-%d"
                ),

                hovertemplate=(
                    "<b>SELL</b>"
                    "<br>Date: %{text}"
                    "<extra></extra>"
                ),
            ),

            row=1,
            col=1,
        )

    if "traded_quantity" in df_chart.columns:

        fig.add_trace(

            go.Bar(

                x=df_chart[
                    "published_date"
                ],

                y=df_chart[
                    "traded_quantity"
                ],

                name="Volume",

                marker=dict(
                    color="lightblue"
                ),

                showlegend=False,
            ),

            row=2,
            col=1,
        )

    fig.update_yaxes(
        title_text="Price",
        row=1,
        col=1,
    )

    fig.update_yaxes(
        title_text="Volume",
        row=2,
        col=1,
    )

    fig.update_xaxes(
        title_text="Date",
        row=2,
        col=1,
    )

    fig.update_layout(
        title=(
            "Stock Price with "
            "Moving Averages & Volume"
        ),
        template="plotly_white",
        height=700,
        hovermode="x unified",
        xaxis_rangeslider_visible=False,
    )

    return fig


def get_trend_insights(
    df: pd.DataFrame,
) -> str:

    if (
        df.empty
        or "close" not in df.columns
    ):

        return (
            "Insufficient data "
            "for trend analysis."
        )

    latest_row = df.iloc[-1]

    latest_close = latest_row.get(
        "close"
    )

    insights = []

    if (
        "ma_20" in df.columns
        and pd.notna(
            latest_row.get("ma_20")
        )
    ):

        ma_20 = latest_row.get(
            "ma_20"
        )

        if latest_close > ma_20:

            insights.append(
                f"✓ Trading **above** "
                f"20-day MA "
                f"(Close: {latest_close:.2f}, "
                f"MA20: {ma_20:.2f})"
            )

        else:

            insights.append(
                f"✗ Trading **below** "
                f"20-day MA "
                f"(Close: {latest_close:.2f}, "
                f"MA20: {ma_20:.2f})"
            )

    if (
        "ma_50" in df.columns
        and pd.notna(
            latest_row.get("ma_50")
        )
    ):

        ma_50 = latest_row.get(
            "ma_50"
        )

        if latest_close > ma_50:

            insights.append(
                f"✓ Trading **above** "
                f"50-day MA "
                f"(Close: {latest_close:.2f}, "
                f"MA50: {ma_50:.2f})"
            )

        else:

            insights.append(
                f"✗ Trading **below** "
                f"50-day MA "
                f"(Close: {latest_close:.2f}, "
                f"MA50: {ma_50:.2f})"
            )

    recent = df["close"].tail(10)

    if len(recent) >= 2:

        recent_trend = (
            recent.iloc[-1]
            - recent.iloc[0]
        )

        if recent_trend > 0:

            insights.append(
                "📈 **Bullish** - "
                "Last 10 days trending upward"
            )

        elif recent_trend < 0:

            insights.append(
                "📉 **Bearish** - "
                "Last 10 days trending downward"
            )

        else:

            insights.append(
                "➡️ **Neutral** - "
                "Last 10 days relatively flat"
            )

    return (
        "\n\n".join(insights)
        if insights
        else
        "Insufficient data for trend analysis."
    )


# ============================================================
# ONLINE NEPSE FINANCIAL DATA
# ============================================================

FINANCIAL_API_URL = (
    "https://shubhamnpk.github.io/"
    "yonepse/data/company/financials.json"
)


@st.cache_data(ttl=60 * 60 * 6)
def load_online_financials():

    try:

        response = requests.get(
            FINANCIAL_API_URL,
            timeout=_LIVE_FETCH_TIMEOUT,
        )

        response.raise_for_status()

        data = response.json()

        if not isinstance(data, list):

            st.warning(
                "Financial data is temporarily "
                "unavailable in an unexpected format."
            )

            return []

        return data

    except Exception as e:

        st.warning(
            "Could not load online financial data "
            "right now. Some fundamentals may be "
            "unavailable."
        )

        if DEBUG_MODE:
            st.caption(f"Debug detail: {e}")

        return []


def get_company_financials(
    data,
    symbol: str,
):

    if not data:
        return None

    symbol = (
        str(symbol)
        .strip()
        .upper()
    )

    for company in data:

        company_symbol = (
            str(
                company.get(
                    "symbol",
                    "",
                )
            )
            .strip()
            .upper()
        )

        if company_symbol == symbol:

            return company

    return None


def get_latest_financial_report(
    company_data,
):

    if not company_data:
        return None

    reports = company_data.get(
        "reports",
        [],
    )

    if not reports:
        return None

    # API normally places recent reports
    # first. Keep first report as latest.
    return reports[0]


def financial_value(
    report,
    key,
):

    if not report:
        return None

    value = report.get(key)

    if value is None:
        return None

    try:

        if pd.isna(value):
            return None

    except Exception:
        pass

    try:

        return float(value)

    except Exception:

        return value


def get_ratio_value(
    report: dict,
    ratio_data: pd.DataFrame,
    symbol: str,
    names: tuple[str, ...],
):
    """Read a ratio from the online report or the local ratio export."""
    for name in names:
        value = financial_value(report, name)
        if value is not None:
            return value

    if ratio_data.empty or "Particular" not in ratio_data.columns:
        return None

    matching = ratio_data[
        ratio_data["symbol"].astype(str).str.upper().eq(symbol.upper())
        & ratio_data["Particular"].astype(str).str.lower().isin(
            {name.lower() for name in names}
        )
    ]
    if matching.empty:
        return None

    row = matching.iloc[0]
    for column in reversed(ratio_data.columns):
        if column in {"symbol", "Particular"}:
            continue
        value = pd.to_numeric(
            pd.Series([str(row[column]).replace("%", "").replace(",", "")]),
            errors="coerce",
        ).iloc[0]
        if pd.notna(value):
            return float(value)

    return None


def generate_ai_recommendation(
    *,
    eps=None,
    pe=None,
    pb=None,
    roe=None,
    roa=None,
    net_margin=None,
    symbol: str = "",
):
    """
    Simple, transparent rule-based verdict from the fundamentals already
    shown on the Company / Symbol Analysis tab (EPS, P/E, P/B, ROE, ROA,
    net margin). This intentionally stays rule-based rather than a
    black-box model, so every reason chip traces back to a number the
    user can already see on the page above it.

    Returns (verdict, summary_text, reason_chips).
    """
    score = 0
    reasons: list[str] = []

    if eps is not None:
        if eps < 0:
            score -= 2
            reasons.append(f"Negative EPS ({eps:.2f})")
        else:
            score += 1
            reasons.append(f"Positive EPS ({eps:.2f})")

    if pe is not None:
        if pe < 0:
            score -= 1
            reasons.append("Negative P/E (loss-making)")
        elif pe > 40:
            score -= 1
            reasons.append(f"High P/E ({pe:.1f}x) — looks overvalued")
        elif pe < 15:
            score += 1
            reasons.append(f"Low P/E ({pe:.1f}x) — looks attractively valued")

    if pb is not None:
        if pb > 5:
            score -= 1
            reasons.append(f"High P/B ({pb:.1f}x)")
        elif 0 < pb < 1.5:
            score += 1
            reasons.append(f"Low P/B ({pb:.1f}x)")

    if roe is not None:
        if roe < 0:
            score -= 1
            reasons.append(f"Negative ROE ({roe:.1f}%)")
        elif roe > 15:
            score += 1
            reasons.append(f"Strong ROE ({roe:.1f}%)")

    if net_margin is not None:
        if net_margin < 0:
            score -= 1
            reasons.append(f"Negative net margin ({net_margin:.1f}%)")
        elif net_margin > 15:
            score += 1
            reasons.append(f"Healthy net margin ({net_margin:.1f}%)")

    if not reasons:
        return (
            "HOLD",
            f"Not enough reported fundamentals for {symbol or 'this stock'} "
            "to form a confident call yet — check back once more financial "
            "data is available.",
            [],
        )

    if score <= -2:
        verdict = "SELL"
        summary = (
            f"Based on the reported fundamentals, {symbol or 'this stock'} "
            "screens as overvalued relative to its earnings quality. "
            "Investors should exercise caution and weigh the risks before "
            "adding to a position, and monitor upcoming results for signs "
            "of improvement before re-entering."
        )
    elif score >= 2:
        verdict = "BUY"
        summary = (
            f"{symbol or 'This stock'}'s reported fundamentals look "
            "comparatively healthy — reasonable valuation alongside "
            "positive earnings and profitability. As always, this is one "
            "input among many; confirm with recent price action and news "
            "before acting."
        )
    else:
        verdict = "HOLD"
        summary = (
            f"{symbol or 'This stock'}'s fundamentals are mixed — some "
            "supportive signals and some concerns, without a clear edge "
            "either way. Worth monitoring rather than acting on "
            "immediately."
        )

    return verdict, summary, reasons


def render_financial_report_readable(report: dict, title: str = "Report Details"):
    """
    Render a financial report dict as a clean, human-readable
    table instead of a raw st.json() dump. Keys are prettified
    (e.g. 'net_worth_per_share' -> 'Net Worth Per Share') and
    values are formatted where numeric.
    """

    if not report:
        st.info("No details available for this report.")
        return

    st.markdown(f"**{title}**")

    rows = []

    for key, value in report.items():

        label = key.replace("_", " ").strip().title()

        # Try to format numeric-looking values nicely
        display_value = value

        try:
            if value is not None and not isinstance(value, (dict, list, bool)):
                if pd.notna(value):
                    numeric_val = float(value)
                    display_value = format_number(numeric_val, 2)
        except Exception:
            display_value = value

        if isinstance(value, (dict, list)):
            # Skip nested structures in the summary table;
            # keep the raw expander below for full detail.
            continue

        rows.append({"Field": label, "Value": display_value})

    if rows:
        summary_df = pd.DataFrame(rows)
        st.dataframe(
            summary_df,
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.info("No displayable fields found in this report.")


# ============================================================
# CHECK MAIN FILE
# ============================================================

if not all_data_path.exists():

    # FIX #2: Clean, user-facing fallback instead of exposing
    # raw shell commands and file paths via st.code(). Full
    # technical details are only shown when DEBUG_MODE is on
    # (set NEPSE_DEBUG=true as an environment variable locally).

    st.warning(
        "⚠️ Data is currently unavailable. "
        "Please try again later or contact the site administrator."
    )

    if DEBUG_MODE:

        st.divider()
        st.caption("Developer debug info (DEBUG_MODE is ON):")
        st.write("Run the downloader first:")
        st.code("python download_nepse_data.py")
        st.write("Then make sure this file exists:")
        st.code(str(all_data_path))

    st.stop()


# ============================================================
# LOAD MAIN DATA
# ============================================================

with st.spinner(
    "Loading NEPSE historical data..."
):

    all_data = load_prepared_csv(
        str(all_data_path),
        all_data_path.stat().st_mtime_ns,
    )


if st.sidebar.button("Refresh live market data"):
    load_live_market_data.clear()
    load_live_nepse_index.clear()
    load_live_nepse_index_history.clear()
    for _k in list(st.session_state.keys()):
        if _k.startswith("_live_fetch_backoff::"):
            del st.session_state[_k]
    st.rerun()


live_market_data = pd.DataFrame()
try:
    with st.spinner("Loading latest NEPSE market prices..."):
        live_market_data = _call_with_backoff(
            "load_live_market_data", load_live_market_data
        )
    live_date = (
        str(live_market_data["published_date"].iloc[0])
        if not live_market_data.empty
        else ""
    )
    live_fingerprint = (
        f"{live_date}:{len(live_market_data)}:"
        f"{live_market_data['close'].sum()}"
        if not live_market_data.empty
        else "empty"
    )
    data_cache_key = f"{all_data_path.stat().st_mtime_ns}:{live_fingerprint}"
    if st.session_state.get("_all_data_cache_key") != data_cache_key:
        all_data = merge_live_market_data(all_data, live_market_data)
        st.session_state["_all_data_cache_key"] = data_cache_key
        st.session_state["_all_data_cached"] = all_data
    else:
        all_data = st.session_state["_all_data_cached"]
    st.sidebar.success(
        f"Live prices loaded: {len(live_market_data):,} symbols"
    )
except Exception as exc:
    st.sidebar.warning(
        "Live prices are unavailable; showing the last saved dataset."
    )
    if DEBUG_MODE:
        st.sidebar.caption(f"Debug detail: {exc}")


if all_data.empty:

    st.warning(
        "⚠️ The NEPSE dataset is currently empty. "
        "Please try again later."
    )

    st.stop()


# ============================================================
# LOAD ONLINE FINANCIAL DATA ONLY FOR COMPANY TAB
# ============================================================

online_financial_data = []
if active_nav == "company":
    with st.spinner("Loading online financial data..."):
        online_financial_data = load_online_financials()


# ============================================================
# LOAD OPTIONAL SUMMARY ONLY WHEN NEEDED
# ============================================================

@st.cache_data(show_spinner=False)
def load_optional_files(
    processed_dir_str: str,
):

    processed = Path(
        processed_dir_str
    )

    latest_day = load_csv(
        str(
            processed
            / LATEST_DAY_FILE
        )
    )

    recent_data = load_csv(
        str(
            processed
            / RECENT_FILE
        )
    )

    coverage = load_csv(
        str(
            processed
            / COVERAGE_FILE
        )
    )

    daily_summary = load_csv(
        str(
            processed
            / DAILY_SUMMARY_FILE
        )
    )

    for optional_df in [
        latest_day,
        recent_data,
        coverage,
        daily_summary,
    ]:

        if (
            not optional_df.empty
            and
            "published_date"
            in optional_df.columns
        ):

            optional_df[
                "published_date"
            ] = pd.to_datetime(
                optional_df[
                    "published_date"
                ],
                errors="coerce",
            )

    return (
        latest_day,
        recent_data,
        coverage,
        daily_summary,
    )


latest_day = pd.DataFrame()
recent_data = pd.DataFrame()
coverage = pd.DataFrame()
daily_summary = pd.DataFrame()

if active_nav == "stocks":
    (
        latest_day,
        recent_data,
        coverage,
        daily_summary,
    ) = load_optional_files(str(processed_dir))


# ============================================================
# LOAD LEGACY OPTIONAL DATA
# ============================================================

# These are retained for compatibility with
# the rest of your project.
# Financial Fundamentals DOES NOT depend on this CSV.

financial_path = (
    BASE_DIR / FINANCIAL_FILE
)

dividend_path = (
    BASE_DIR / DIVIDEND_FILE
)

financial_data = pd.DataFrame()
dividend_data = pd.DataFrame()
if active_nav == "company":
    ratio_path = BASE_DIR / RATIO_FILE
    financial_data = load_csv(str(ratio_path)) if ratio_path.exists() else pd.DataFrame()
    if financial_data.empty:
        financial_data = load_csv(str(financial_path))


# ============================================================
# SECTOR MAPPING
# ============================================================

_sector_path = (
    BASE_DIR / "sector_mapping.csv"
)

sector_mapping = load_csv(
    str(_sector_path)
)


# ============================================================
# LIVE SEARCH SUGGESTIONS (symbol + full company name + sector)
# ============================================================

@st.cache_data(show_spinner=False)
def build_stock_directory(mapping: pd.DataFrame):
    """
    Flattens sector_mapping into a list of
    {"symbol", "name", "sector"} dicts used to power the
    live search-suggestions dropdown on the home page.
    """

    if mapping.empty:
        return []

    symbol_col = next(
        (c for c in ["symbol", "Symbol", "SYMBOL"] if c in mapping.columns),
        None,
    )

    name_col = next(
        (
            c
            for c in [
                "name",
                "company_name",
                "Name",
                "Company Name",
                "company",
            ]
            if c in mapping.columns
        ),
        None,
    )

    sector_col = "sector" if "sector" in mapping.columns else None

    if not symbol_col:
        return []

    directory = []

    for _, row in mapping.iterrows():

        symbol = str(row.get(symbol_col, "")).strip().upper()

        if not symbol:
            continue

        directory.append(
            {
                "symbol": symbol,
                "name": (
                    str(row.get(name_col, "")).strip()
                    if name_col
                    else ""
                ),
                "sector": (
                    str(row.get(sector_col, "")).strip()
                    if sector_col
                    else ""
                ),
            }
        )

    return sorted(directory, key=lambda d: d["symbol"])


def filter_stock_matches(query: str, directory, limit: int = 6):
    """
    Ranks directory entries against `query`: symbol/name prefix
    matches first, then any substring match, de-duplicated by symbol.
    """

    q = query.strip().lower()

    if not q:
        return []

    starts, contains = [], []
    seen = set()

    for entry in directory:

        symbol_l = entry["symbol"].lower()

        if symbol_l in seen:
            continue

        name_l = entry["name"].lower()

        if symbol_l.startswith(q) or name_l.startswith(q):
            starts.append(entry)
            seen.add(symbol_l)

        elif q in symbol_l or q in name_l:
            contains.append(entry)
            seen.add(symbol_l)

    return (starts + contains)[:limit]


def disable_search_autofill():
    """
    Streamlit's text inputs are plain <input> elements, so browsers
    offer their own saved-value autofill suggestions (e.g. a stray
    "kristina" from an unrelated form on the same browser profile)
    on top of them. This reaches into the parent document and turns
    native autocomplete off for every Streamlit text input across
    the whole app — home search, stock symbol search, etc — and
    re-applies itself whenever new inputs appear (tab switches,
    reruns) via a MutationObserver.
    """

    components.html(
        """
        <script>
        (function () {
            function killAutofill() {
                try {
                    const doc = window.parent.document;
                    doc.querySelectorAll(
                        '.stTextInput input, input[type="text"]'
                    ).forEach((el) => {
                        el.setAttribute('autocomplete', 'off');
                        el.setAttribute('autocorrect', 'off');
                        el.setAttribute('autocapitalize', 'off');
                        el.setAttribute('spellcheck', 'false');
                        if (!el.dataset.ninjaNamed) {
                            el.setAttribute('name', 'ninja-field-' + Math.random().toString(36).slice(2));
                            el.dataset.ninjaNamed = '1';
                        }
                    });
                } catch (e) {}
            }
            killAutofill();
            setTimeout(killAutofill, 300);
            const target = window.parent.document.body;
            if (target) {
                new MutationObserver(killAutofill).observe(target, {
                    childList: true,
                    subtree: true,
                });
            }
        })();
        </script>
        """,
        height=0,
    )


disable_search_autofill()


# ============================================================
# NEPSE INDEX SNAPSHOT (value / change / breadth)
# ============================================================

def get_market_breadth(df: pd.DataFrame) -> dict:
    """
    Counts advancers / unchanged / decliners on the latest trading
    day, from whichever per-stock % change column is available.
    """
    if df.empty or "published_date" not in df.columns:
        return {"up": 0, "flat": 0, "down": 0}

    latest_date = df["published_date"].max()
    latest = df[df["published_date"] == latest_date]

    change_col = next(
        (c for c in ["per_change", "return_percent"] if c in latest.columns),
        None,
    )

    if not change_col:
        return {"up": 0, "flat": 0, "down": 0}

    changes = safe_numeric(latest[change_col]).dropna()

    return {
        "up": int((changes > 0).sum()),
        "flat": int((changes == 0).sum()),
        "down": int((changes < 0).sum()),
    }


def get_nepse_index_snapshot(summary_df: pd.DataFrame):
    """
    Pulls the latest overall NEPSE index value / points change /
    percent change out of the daily-summary file, tolerating a
    range of likely column names. Returns None when the summary
    file doesn't carry recognizable index columns (in which case
    the index card falls back to showing "N/A" for the value while
    still showing live market breadth and status).
    """
    if summary_df.empty:
        return None

    df = summary_df.copy()

    if "published_date" in df.columns:
        df = df.sort_values("published_date")

    row = df.iloc[-1]

    index_col = next(
        (
            c
            for c in [
                "index_value",
                "nepse_index",
                "close_index",
                "index_close",
                "current_index",
                "index",
            ]
            if c in df.columns
        ),
        None,
    )

    if not index_col:
        return None

    points_col = next(
        (
            c
            for c in [
                "point_change",
                "points_change",
                "change_points",
                "net_change",
                "index_point_change",
            ]
            if c in df.columns
        ),
        None,
    )

    percent_col = next(
        (
            c
            for c in [
                "percent_change",
                "change_percent",
                "index_percent_change",
                "per_change",
            ]
            if c in df.columns
        ),
        None,
    )

    def _num(col):
        if not col:
            return None
        val = safe_numeric(pd.Series([row.get(col)])).iloc[0]
        return None if pd.isna(val) else float(val)

    return {
        "value": _num(index_col),
        "points": _num(points_col),
        "percent": _num(percent_col),
    }


def get_nepse_index_history(summary_df: pd.DataFrame) -> pd.DataFrame:
    """
    Builds a published_date / open / high / low / close / volume
    frame for the overall NEPSE index out of the daily-summary file,
    used to power the expandable index chart. Falls back to a
    close-only line series when full OHLC columns aren't present.
    """
    if summary_df.empty or "published_date" not in summary_df.columns:
        return pd.DataFrame()

    df = summary_df.sort_values("published_date").copy()

    # If the file has a "symbol" column it's per-stock data, not a
    # market-level summary — plain open/high/low/close would then
    # belong to individual stocks, not the index, so only use them
    # as a fallback when there's no symbol column at all.
    has_symbol_col = any(
        c in df.columns for c in ["symbol", "Symbol", "SYMBOL"]
    )

    def _pick(names, fallback_plain=None):
        col = next((c for c in names if c in df.columns), None)
        if (
            not col
            and not has_symbol_col
            and fallback_plain
            and fallback_plain in df.columns
        ):
            col = fallback_plain
        return col

    open_col = _pick(["index_open", "nepse_open"], "open")
    high_col = _pick(["index_high", "nepse_high"], "high")
    low_col = _pick(["index_low", "nepse_low"], "low")
    close_col = _pick(
        [
            "index_value",
            "nepse_index",
            "close_index",
            "index_close",
            "current_index",
            "index",
        ],
        "close",
    )
    volume_col = next(
        (
            c
            for c in ["turnover", "total_turnover", "traded_amount"]
            if c in df.columns
        ),
        None,
    )

    if not close_col:
        return pd.DataFrame()

    history = pd.DataFrame(
        {
            "published_date": df["published_date"],
            "close": safe_numeric(df[close_col]),
            "open": safe_numeric(df[open_col]) if open_col else pd.NA,
            "high": safe_numeric(df[high_col]) if high_col else pd.NA,
            "low": safe_numeric(df[low_col]) if low_col else pd.NA,
            "volume": safe_numeric(df[volume_col]) if volume_col else pd.NA,
        }
    )

    history = history.dropna(subset=["close"]).reset_index(drop=True)

    if history.empty:
        return history

    six_months_ago = (
        history["published_date"].max() - pd.Timedelta(days=180)
    )

    return (
        history[history["published_date"] >= six_months_ago]
        .sort_values("published_date")
        .reset_index(drop=True)
    )


def create_index_chart(history: pd.DataFrame, indicators=()):
    """
    Candlestick chart for the overall NEPSE index when open/high/low
    are available, falling back to a close-price line chart. Adds a
    turnover panel underneath when volume data is present.
    """
    if history.empty:
        return None

    has_ohlc = (
        history[["open", "high", "low"]].notna().all().all()
    )
    has_volume = (
        "volume" in history.columns and history["volume"].notna().any()
    )

    rows = 2 if has_volume else 1
    row_heights = [0.7, 0.3] if has_volume else [1.0]

    fig = make_subplots(
        rows=rows,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.08,
        row_heights=row_heights,
    )

    if has_ohlc:
        fig.add_trace(
            go.Candlestick(
                x=history["published_date"],
                open=history["open"],
                high=history["high"],
                low=history["low"],
                close=history["close"],
                name="NEPSE Index",
            ),
            row=1,
            col=1,
        )
    else:
        fig.add_trace(
            go.Scatter(
                x=history["published_date"],
                y=history["close"],
                mode="lines",
                name="NEPSE Index",
                line=dict(width=2, color="#2ec4b6"),
            ),
            row=1,
            col=1,
        )

    if has_volume:
        fig.add_trace(
            go.Bar(
                x=history["published_date"],
                y=history["volume"],
                name="Turnover",
                marker=dict(color="lightblue"),
                showlegend=False,
            ),
            row=2,
            col=1,
        )

    close = history["close"]
    if "SMA 20" in indicators:
        fig.add_trace(
            go.Scatter(
                x=history["published_date"],
                y=close.rolling(20).mean(),
                name="SMA 20",
                line=dict(color="#f4a261", width=2),
            ),
            row=1,
            col=1,
        )
    if "SMA 50" in indicators:
        fig.add_trace(
            go.Scatter(
                x=history["published_date"],
                y=close.rolling(50).mean(),
                name="SMA 50",
                line=dict(color="#e76f51", width=2),
            ),
            row=1,
            col=1,
        )

    if "RSI 14" in indicators:
        delta = close.diff()
        gain = delta.clip(lower=0).rolling(14).mean()
        loss = (-delta.clip(upper=0)).rolling(14).mean()
        rsi = 100 - (100 / (1 + gain / loss.replace(0, pd.NA)))
        fig.add_trace(
            go.Scatter(
                x=history["published_date"], y=rsi, name="RSI 14",
                line=dict(color="#2a9d8f", width=2),
            ),
            row=1,
            col=1,
        )
    if "MACD" in indicators:
        macd = close.ewm(span=12, adjust=False).mean() - close.ewm(
            span=26, adjust=False
        ).mean()
        fig.add_trace(
            go.Scatter(
                x=history["published_date"], y=macd, name="MACD",
                line=dict(color="#9b5de5", width=2),
            ),
            row=1,
            col=1,
        )

    fig.update_yaxes(title_text="Index", row=1, col=1)
    if has_volume:
        fig.update_yaxes(title_text="Turnover", row=2, col=1)

    fig.update_layout(
        title=(
            "NEPSE Index — 6 Month Trend"
            if has_ohlc
            else "NEPSE Index — 6 Month Trend (close only)"
        ),
        template="plotly_white",
        height=560,
        hovermode="x unified",
        xaxis_rangeslider_visible=False,
    )

    return fig


def build_index_proxy_history(
    all_data: pd.DataFrame,
    live_snapshot: dict | None = None,
) -> pd.DataFrame:
    """
    Fallback market-trend series used when neither the live ShareSansar
    scrape nor NEPSE_DAILY_SUMMARY.csv provide a real index-level OHLC
    history. Built from data the app already has: a turnover-weighted
    average of each day's per-stock % change, compounded into an
    index-style level and anchored to today's live NEPSE index value
    when known.

    IMPORTANT: this is an approximation of overall market direction,
    NOT a recomputation of the official market-cap-weighted NEPSE
    Index — it exists purely so the chart always shows *something*
    useful instead of a dead end.
    """
    if all_data.empty or "published_date" not in all_data.columns:
        return pd.DataFrame()

    change_col = next(
        (
            c
            for c in ["return_percent", "per_change"]
            if c in all_data.columns
        ),
        None,
    )

    if not change_col:
        return pd.DataFrame()

    df = all_data.dropna(subset=["published_date"]).copy()
    df[change_col] = safe_numeric(df[change_col])
    df = df.dropna(subset=[change_col])

    if df.empty:
        return pd.DataFrame()

    weight_col = (
        "traded_amount" if "traded_amount" in df.columns else None
    )

    def _daily_avg(day_df: pd.DataFrame) -> float:
        if weight_col:
            weights = safe_numeric(day_df[weight_col]).fillna(0)
            if weights.sum() > 0:
                return (day_df[change_col] * weights).sum() / weights.sum()
        return day_df[change_col].mean()

    daily = (
        df.groupby("published_date")
        .apply(_daily_avg)
        .rename("avg_change_pct")
        .reset_index()
        .sort_values("published_date")
    )

    if daily.empty:
        return pd.DataFrame()

    six_months_ago = (
        daily["published_date"].max() - pd.Timedelta(days=180)
    )
    daily = (
        daily[daily["published_date"] >= six_months_ago]
        .reset_index(drop=True)
    )

    if daily.empty:
        return pd.DataFrame()

    growth = (1 + daily["avg_change_pct"].fillna(0) / 100).cumprod()

    anchor_value = (
        live_snapshot.get("value")
        if live_snapshot
        else None
    )

    if isinstance(anchor_value, (int, float)) and growth.iloc[-1]:
        level = growth * (anchor_value / growth.iloc[-1])
    else:
        level = growth * 100  # relative index, base 100

    return pd.DataFrame(
        {
            "published_date": daily["published_date"],
            "close": level,
            "open": pd.NA,
            "high": pd.NA,
            "low": pd.NA,
            "volume": pd.NA,
        }
    )


POPULAR_STOCKS = [
    "NABIL",
    "GBIME",
    "UPPER",
    "NICA",
    "SCB",
    "EBL",
    "NLIC",
    "BPCL",
    "ADBL",
]


# ============================================================
# TAB: HOME
# ============================================================

if active_nav == "home":

    home_index_snapshot = None
    try:
        home_index_snapshot = _call_with_backoff(
            "load_live_nepse_index", load_live_nepse_index
        )
    except Exception:
        pass

    st.markdown(
        get_hero_html(
            get_market_status(home_index_snapshot)
        ),
        unsafe_allow_html=True,
    )

    _qp_symbol = st.query_params.get(
        "symbol",
        "",
    )

    if isinstance(
        _qp_symbol,
        list,
    ):

        _qp_symbol = (
            _qp_symbol[0]
            if _qp_symbol
            else ""
        )

    _qp_symbol = (
        _qp_symbol
        .strip()
        .upper()
    )

    if (
        _qp_symbol
        and
        st.session_state.get(
            "_home_qp_symbol_applied"
        )
        != _qp_symbol
    ):

        st.session_state[
            "home_search_input"
        ] = _qp_symbol

        st.session_state[
            "_home_qp_symbol_applied"
        ] = _qp_symbol


    (
        _pad1,
        _search_col,
        _pad2,
    ) = st.columns(
        [1.2, 3, 1.2]
    )


    with _search_col:

        _search_raw = st.text_input(

            "Search",

            placeholder=(
                "Search NEPSE stocks "
                "by symbol, name or sector..."
            ),

            label_visibility="collapsed",

            key="home_search_input",
        )

        home_symbol = _search_raw.strip().upper()


    _stock_directory = build_stock_directory(
        sector_mapping
    )

    if _search_raw.strip():

        _search_matches = filter_stock_matches(
            _search_raw,
            _stock_directory,
            limit=6,
        )

        st.markdown(
            get_search_suggestions_html(
                _search_matches,
                len(_stock_directory),
                active_theme,
            ),
            unsafe_allow_html=True,
        )


    st.markdown(
        get_popular_tags_html(
            POPULAR_STOCKS,
            active_theme,
        ),
        unsafe_allow_html=True,
    )


    if (
        "active_sector"
        not in st.session_state
    ):

        st.session_state[
            "active_sector"
        ] = None


    if (
        not sector_mapping.empty
        and
        "sector"
        in sector_mapping.columns
    ):

        unique_sectors = sorted(
            sector_mapping[
                "sector"
            ]
            .dropna()
            .unique()
            .tolist()
        )

        st.markdown(
            '<div class="pill-row">',
            unsafe_allow_html=True,
        )

        _pill_cols = st.columns(
            len(unique_sectors)
        )

        for (
            _col,
            _sector_name,
        ) in zip(
            _pill_cols,
            unique_sectors,
        ):

            with _col:

                _cls = (
                    SECTOR_CLASS_MAP.get(
                        _sector_name,
                        "ot",
                    )
                )

                st.markdown(
                    f'<span class="pill-mark '
                    f'p-{_cls}"></span>',
                    unsafe_allow_html=True,
                )

                if st.button(
                    _sector_name,
                    key=(
                        f"pill_"
                        f"{_sector_name}"
                    ),
                ):

                    st.session_state[
                        "active_sector"
                    ] = _sector_name

        st.markdown(
            "</div>",
            unsafe_allow_html=True,
        )


        active_sector = (
            st.session_state[
                "active_sector"
            ]
        )


        if active_sector:

            symbol_col = next(

                (
                    c
                    for c in [
                        "symbol",
                        "Symbol",
                        "SYMBOL",
                    ]

                    if c
                    in sector_mapping.columns
                ),

                None,
            )


            name_col = next(

                (
                    c
                    for c in [
                        "name",
                        "company_name",
                        "Name",
                        "Company Name",
                        "company",
                    ]

                    if c
                    in sector_mapping.columns
                ),

                None,
            )


            sector_rows = (
                sector_mapping[
                    sector_mapping[
                        "sector"
                    ]
                    == active_sector
                ]
            )


            sector_companies = []


            if symbol_col:

                for (
                    _,
                    _row,
                ) in sector_rows.iterrows():

                    sector_companies.append(

                        {
                            "symbol":
                                str(
                                    _row.get(
                                        symbol_col,
                                        "",
                                    )
                                ).strip(),

                            "name":
                                str(
                                    _row.get(
                                        name_col,
                                        "",
                                    )
                                ).strip()
                                if name_col
                                else "",
                        }
                    )


                sector_companies = sorted(
                    sector_companies,
                    key=lambda x:
                        x["symbol"],
                )


            @st.dialog(
                f"{active_sector} "
                f"({len(sector_companies)})"
            )

            def _show_sector_dialog(
                companies=sector_companies,
            ):

                if not companies:

                    st.write(
                        "No companies found "
                        "for this sector."
                    )

                for _comp in companies:

                    _c1, _c2 = (
                        st.columns([3, 1])
                    )

                    _c1.markdown(
                        f"**{_comp['symbol']}**  \n"
                        f"{_comp['name']}"
                    )

                    if _c2.button(
                        "View",
                        key=(
                            f"goto_"
                            f"{_comp['symbol']}"
                        ),
                        use_container_width=True,
                    ):

                        st.session_state[
                            "home_search_input"
                        ] = _comp["symbol"]

                        st.session_state[
                            "_home_qp_symbol_applied"
                        ] = _comp["symbol"]

                        st.session_state[
                            "active_sector"
                        ] = None

                        st.rerun()


            _show_sector_dialog()


    if home_symbol:

        _home_data = get_6month_data(
            all_data,
            home_symbol,
        )

        if _home_data.empty:

            st.error(
                f"No data found for symbol: "
                f"**{home_symbol}**"
            )

        else:

            _home_data = (
                calculate_moving_averages(
                    _home_data
                )
            )

            _home_metrics = (
                calculate_metrics(
                    _home_data
                )
            )

            st.markdown(
                f"### {home_symbol} "
                f"— Quick Analysis"
            )

            m1, m2, m3, m4, m5 = (
                st.columns(5)
            )

            m1.metric(
                "Current Price",
                format_number(
                    _home_metrics.get(
                        "current_price"
                    ),
                    2,
                ),
            )

            m2.metric(
                "6M Return %",
                format_number(
                    _home_metrics.get(
                        "total_return"
                    ),
                    2,
                ),
            )

            m3.metric(
                "Avg Daily Return %",
                format_number(
                    _home_metrics.get(
                        "avg_daily_return"
                    ),
                    4,
                ),
            )

            m4.metric(
                "Highest",
                format_number(
                    _home_metrics.get(
                        "highest"
                    ),
                    2,
                ),
            )

            m5.metric(
                "Lowest",
                format_number(
                    _home_metrics.get(
                        "lowest"
                    ),
                    2,
                ),
            )

            _home_fig = (
                create_candlestick_chart(
                    _home_data
                )
            )

            if _home_fig is not None:

                st.plotly_chart(
                    _home_fig,
                    use_container_width=True,
                )

            st.markdown(
                "### Trend Insights"
            )

            st.markdown(
                get_trend_insights(
                    _home_data
                )
            )


# ============================================================
# TAB: STOCKS
# ============================================================

if active_nav == "stocks":

    try:
        stocks_index_snapshot = _call_with_backoff(
            "load_live_nepse_index", load_live_nepse_index
        )
        st.caption("Live NEPSE index data · refreshed every 15 minutes")
    except Exception as exc:
        stocks_index_snapshot = get_nepse_index_snapshot(daily_summary)
        st.caption("Live NEPSE index unavailable · showing saved summary data")
        if DEBUG_MODE:
            st.caption(f"Debug detail: {exc}")

    st.markdown(
        get_nepse_index_card_html(
            stocks_index_snapshot,
            get_market_breadth(all_data),
            active_theme,
        ),
        unsafe_allow_html=True,
    )

    # Expand-icon on the index card links here with ?expand_index=1;
    # pick that up once, then drop it from the URL immediately so the
    # dialog is controlled by session_state (closable) rather than
    # reopening on every rerun while the query param lingers.
    if st.query_params.get("expand_index") == "1":

        st.session_state["show_index_chart"] = True
        del st.query_params["expand_index"]

    if st.session_state.get("show_index_chart"):

        @st.dialog("NEPSE Index — Detailed Chart")
        def _show_index_chart_dialog():

            _source_label = "Live ShareSansar NEPSE history"

            try:
                _index_history = _call_with_backoff(
                    "load_live_nepse_index_history",
                    load_live_nepse_index_history,
                )
            except Exception:
                _index_history = pd.DataFrame()

            if _index_history.empty:
                _index_history = get_nepse_index_history(daily_summary)
                _source_label = "Saved NEPSE_DAILY_SUMMARY.csv history"

            if _index_history.empty:
                _index_history = build_index_proxy_history(
                    all_data,
                    stocks_index_snapshot,
                )
                _source_label = (
                    "Approximate market-trend proxy "
                    "(turnover-weighted avg. of daily stock moves — "
                    "not the official NEPSE Index calculation)"
                )

            st.caption(
                f"{_source_label} · select indicators and zoom the chart."
            )

            selected_indicators = st.multiselect(
                "Indicators",
                ["SMA 20", "SMA 50", "RSI 14", "MACD"],
                default=["SMA 20"],
                key="nepse_index_indicators",
            )
            _index_fig = create_index_chart(
                _index_history,
                selected_indicators,
            )

            if _index_fig is None:
                st.warning(
                    "No index history is available yet — this needs "
                    "either historical OHLC data in "
                    "NEPSE_DAILY_SUMMARY.csv or per-stock data in "
                    "NEPSE_ALL_DATA.csv to build even an approximate chart."
                )
            else:
                st.plotly_chart(
                    _index_fig,
                    use_container_width=True,
                    config={
                        "displaylogo": False,
                        "scrollZoom": True,
                        "displayModeBar": True,
                    },
                )

            if st.button(
                "Close",
                use_container_width=True,
                key="close_index_chart_dialog",
            ):
                st.session_state["show_index_chart"] = False
                st.rerun()

        _show_index_chart_dialog()

    st.subheader(
        "Stock Symbol Analysis"
    )

    col1, col2 = st.columns(
        [3, 1]
    )

    with col1:

        _prefill_symbol = (
            st.query_params.get(
                "symbol",
                "",
            )
        )

        if isinstance(
            _prefill_symbol,
            list,
        ):

            _prefill_symbol = (
                _prefill_symbol[0]
                if _prefill_symbol
                else ""
            )

        user_symbol = st.text_input(

            "Enter stock symbol "
            "(e.g., NABIL, NTC, SCB)",

            value=_prefill_symbol,

            placeholder="NABIL",

            help=(
                "Type the stock symbol "
                "to analyze"
            ),

            key="core_symbol",
        ).upper()


    with col2:

        search_button = st.button(
            "🔍 Search",
            use_container_width=True,
            key="core_search_btn",
        )


    if search_button or user_symbol:

        if not user_symbol:

            st.warning(
                "Please enter a stock symbol."
            )

        else:

            symbol_data = (
                get_6month_data(
                    all_data,
                    user_symbol,
                )
            )

            if symbol_data.empty:

                st.error(
                    f"No data found for symbol: "
                    f"**{user_symbol}**"
                )

                st.write(
                    "Available symbols:"
                )

                available_symbols = sorted(
                    all_data[
                        "symbol"
                    ]
                    .dropna()
                    .unique()
                    .tolist()
                )

                st.write(
                    ", ".join(
                        available_symbols[:20]
                    )
                    +
                    (
                        "..."
                        if len(
                            available_symbols
                        ) > 20
                        else ""
                    )
                )

            else:

                symbol_data = (
                    calculate_moving_averages(
                        symbol_data
                    )
                )

                metrics = (
                    calculate_metrics(
                        symbol_data
                    )
                )

                st.markdown(
                    f"### {user_symbol} "
                    f"- 6 Month Analysis"
                )

                m1, m2, m3, m4, m5 = (
                    st.columns(5)
                )

                m1.metric(
                    "Current Price",
                    format_number(
                        metrics.get(
                            "current_price"
                        ),
                        2,
                    ),
                )

                m2.metric(
                    "6M Return %",
                    format_number(
                        metrics.get(
                            "total_return"
                        ),
                        2,
                    ),
                )

                m3.metric(
                    "Avg Daily Return %",
                    format_number(
                        metrics.get(
                            "avg_daily_return"
                        ),
                        4,
                    ),
                )

                m4.metric(
                    "Highest Price",
                    format_number(
                        metrics.get(
                            "highest"
                        ),
                        2,
                    ),
                )

                m5.metric(
                    "Lowest Price",
                    format_number(
                        metrics.get(
                            "lowest"
                        ),
                        2,
                    ),
                )

                st.markdown(
                    "### Price Chart with "
                    "Moving Averages & Volume"
                )

                fig = (
                    create_candlestick_chart(
                        symbol_data
                    )
                )

                if fig is not None:

                    st.plotly_chart(
                        fig,
                        use_container_width=True,
                    )

                else:

                    st.warning(
                        "Unable to create chart "
                        "with available data."
                    )

                st.divider()

                show_period_changes(
                    symbol_data,
                    user_symbol,
                )

                st.divider()

                st.markdown(
                    "### Trend Insights"
                )

                st.markdown(
                    get_trend_insights(
                        symbol_data
                    )
                )

                st.markdown(
                    "### Last 10 Trading Days"
                )

                last_10 = (
                    symbol_data
                    .tail(10)
                    .sort_values(
                        "published_date",
                        ascending=False,
                    )
                )

                display_cols = [

                    col

                    for col in [

                        "published_date",
                        "open",
                        "high",
                        "low",
                        "close",
                        "per_change",
                        "return_percent",
                        "traded_quantity",
                        "traded_amount",

                    ]

                    if col
                    in last_10.columns
                ]

                st.dataframe(
                    last_10[
                        display_cols
                    ],
                    use_container_width=True,
                    hide_index=True,
                )

                st.markdown(
                    "### Download "
                    "6-Month Data"
                )

                export_data = (
                    symbol_data[
                        [
                            col

                            for col in [

                                "published_date",
                                "open",
                                "high",
                                "low",
                                "close",
                                "per_change",
                                "return_percent",
                                "traded_quantity",
                                "traded_amount",
                                "ma_20",
                                "ma_50",

                            ]

                            if col
                            in symbol_data.columns
                        ]
                    ].copy()
                )

                st.download_button(

                    label=(
                        f"📥 Download "
                        f"{user_symbol} "
                        f"Full 6-Month CSV"
                    ),

                    data=csv_bytes(
                        export_data
                    ),

                    file_name=(
                        f"{user_symbol}"
                        f"_6month_data.csv"
                    ),

                    mime="text/csv",

                    use_container_width=True,
                )


# ============================================================
# TAB: MARKET MOVERS
# ============================================================

if active_nav == "movers":
    st.subheader("Market Movers by Sector")
    st.caption("Top 3 gainers, losers, and most active stocks within each sector on the latest trading day.")

    latest_date = all_data["published_date"].max()
    movers = all_data[
        all_data["published_date"] == latest_date
    ].copy()

    # Attach sector information to each stock.
    if not sector_mapping.empty and "sector" in sector_mapping.columns:
        sector_symbol_col = next(
            (
                c for c in ["symbol", "Symbol", "SYMBOL"]
                if c in sector_mapping.columns
            ),
            None,
        )

        if sector_symbol_col:
            sector_map = sector_mapping[
                [sector_symbol_col, "sector"]
            ].copy()
            sector_map.columns = ["symbol", "sector"]
            sector_map["symbol"] = (
                sector_map["symbol"].astype(str).str.strip().str.upper()
            )
            movers = movers.merge(
                sector_map.drop_duplicates("symbol"),
                on="symbol",
                how="left",
            )

    if "sector" not in movers.columns:
        movers["sector"] = "Other"

    movers["sector"] = movers["sector"].fillna("Other")

    change_col = (
        "return_percent"
        if "return_percent" in movers.columns
        else "per_change"
    )

    if change_col not in movers.columns:
        st.warning("Market movement data is unavailable.")
    else:
        movers[change_col] = safe_numeric(movers[change_col])

        for sector_name in sorted(movers["sector"].dropna().unique()):
            sector_df = movers[movers["sector"] == sector_name].copy()

            st.markdown(f"### {sector_name}")

            gainers = (
                sector_df[sector_df[change_col] > 0]
                .sort_values(change_col, ascending=False)
                .head(3)
            )
            losers = (
                sector_df[sector_df[change_col] < 0]
                .sort_values(change_col, ascending=True)
                .head(3)
            )
            most_active = (
                sector_df.sort_values(
                    "traded_quantity",
                    ascending=False,
                ).head(3)
                if "traded_quantity" in sector_df.columns
                else sector_df.head(3)
            )

            c1, c2, c3 = st.columns(3)

            with c1:
                st.markdown("**🟢 Top 3 Gainers**")
                if gainers.empty:
                    st.info("No gainers")
                else:
                    display = gainers[["symbol", change_col]].copy()
                    display.columns = ["Stock", "Change %"]
                    display["Change %"] = display["Change %"].map(
                        lambda x: f"+{x:.2f}%"
                    )
                    st.dataframe(display, use_container_width=True, hide_index=True)

            with c2:
                st.markdown("**🔴 Top 3 Losers**")
                if losers.empty:
                    st.info("No losers")
                else:
                    display = losers[["symbol", change_col]].copy()
                    display.columns = ["Stock", "Change %"]
                    display["Change %"] = display["Change %"].map(
                        lambda x: f"{x:.2f}%"
                    )
                    st.dataframe(display, use_container_width=True, hide_index=True)

            with c3:
                st.markdown("**🔵 Top 3 Most Active**")
                if most_active.empty:
                    st.info("No active stocks")
                else:
                    active_cols = ["symbol"]
                    if "traded_quantity" in most_active.columns:
                        active_cols.append("traded_quantity")
                    if "traded_amount" in most_active.columns:
                        active_cols.append("traded_amount")
                    display = most_active[active_cols].copy()
                    display.columns = [
                        "Stock",
                        *(["Volume"] if "traded_quantity" in most_active.columns else []),
                        *(["Turnover"] if "traded_amount" in most_active.columns else []),
                    ]
                    st.dataframe(display, use_container_width=True, hide_index=True)

            st.divider()


# ============================================================
# TAB: COMPANY ANALYSIS
# ============================================================

if active_nav == "company":

    st.subheader(
        "Company / Symbol Analysis"
    )

    symbols = sorted(
        all_data[
            "symbol"
        ]
        .dropna()
        .unique()
        .tolist()
    )

    selected_symbol = st.selectbox(

        "Select symbol",

        options=symbols,

        index=0,

        key="company_symbol",
    )


    company = all_data[
        all_data["symbol"]
        == selected_symbol
    ].copy()


    company = (
        company
        .sort_values("published_date")
        .reset_index(drop=True)
    )


    if company.empty:

        st.warning(
            "No observations found."
        )

    else:

        # ====================================================
        # PRICE DATE RANGE
        # ====================================================

        min_date = (
            company[
                "published_date"
            ].min()
        )

        max_date = (
            company[
                "published_date"
            ].max()
        )


        selected_dates = st.date_input(

            "Select date range",

            value=(
                min_date.date(),
                max_date.date(),
            ),

            min_value=min_date.date(),

            max_value=max_date.date(),

            key="company_dates",
        )


        filtered_company = (
            company.copy()
        )


        if (
            isinstance(
                selected_dates,
                (tuple, list),
            )
            and
            len(selected_dates) == 2
        ):

            start_date = pd.Timestamp(
                selected_dates[0]
            )

            end_date = pd.Timestamp(
                selected_dates[1]
            )


            filtered_company = company[

                (
                    company[
                        "published_date"
                    ]
                    >= start_date
                )

                &

                (
                    company[
                        "published_date"
                    ]
                    <= end_date
                )

            ].copy()


        latest_row = (
            filtered_company
            .sort_values(
                "published_date"
            )
            .tail(1)
        )


        if not latest_row.empty:

            latest_close = (

                latest_row[
                    "close"
                ].iloc[0]

                if "close"
                in latest_row.columns

                else None
            )


            latest_return = (

                latest_row[
                    "return_percent"
                ].iloc[0]

                if "return_percent"
                in latest_row.columns

                else None
            )


            total_volume = (

                filtered_company[
                    "traded_quantity"
                ].sum()

                if "traded_quantity"
                in filtered_company.columns

                else None
            )


            total_turnover = (

                filtered_company[
                    "traded_amount"
                ].sum()

                if "traded_amount"
                in filtered_company.columns

                else None
            )


            k1, k2, k3, k4 = (
                st.columns(4)
            )


            k1.metric(
                "Latest Close",
                format_number(
                    latest_close,
                    2,
                ),
            )


            k2.metric(
                "Latest Return %",
                format_number(
                    latest_return,
                    2,
                ),
            )


            k3.metric(
                "Period Volume",
                format_integer(
                    total_volume
                ),
            )


            k4.metric(
                "Period Turnover",
                format_number(
                    total_turnover,
                    2,
                ),
            )


            st.divider()


        # ====================================================
        # FINANCIAL FUNDAMENTALS
        # ====================================================

        st.markdown(
            "## ▶ Financial Fundamentals"
        )


        # ----------------------------------------------------
        # Find company online
        # ----------------------------------------------------

        selected_financial = (
            get_company_financials(
                online_financial_data,
                selected_symbol,
            )
        )


        if selected_financial is None:

            st.info(
                f"No financial data available "
                f"for {selected_symbol} "
                f"from the online financial API."
            )

        else:

            # ------------------------------------------------
            # Get latest report
            # ------------------------------------------------

            latest_report = (
                get_latest_financial_report(
                    selected_financial
                )
            )


            if latest_report is None:

                st.info(
                    f"No financial reports "
                    f"available for "
                    f"{selected_symbol}."
                )

            else:

                # --------------------------------------------
                # Report details
                # --------------------------------------------

                report_type = (
                    latest_report.get(
                        "type",
                        "N/A",
                    )
                )

                fiscal_year = (
                    latest_report.get(
                        "fy",
                        "N/A",
                    )
                )

                quarter = (
                    latest_report.get(
                        "quarter",
                        "N/A",
                    )
                )


                st.caption(

                    f"Latest Report: "
                    f"{report_type} | "
                    f"{quarter} | "
                    f"FY {fiscal_year}"

                )


                # --------------------------------------------
                # Extract values
                # --------------------------------------------

                eps = financial_value(
                    latest_report,
                    "eps",
                )

                pe = financial_value(
                    latest_report,
                    "pe",
                )

                bvps = financial_value(
                    latest_report,
                    "net_worth_per_share",
                )

                profit = financial_value(
                    latest_report,
                    "profit",
                )

                paid_up_capital = (
                    financial_value(
                        latest_report,
                        "paid_up_capital",
                    )
                )

                roe = get_ratio_value(
                    latest_report,
                    financial_data,
                    selected_symbol,
                    ("roe", "roe_ttm", "return_on_equity", "ROE TTM"),
                )
                roa = get_ratio_value(
                    latest_report,
                    financial_data,
                    selected_symbol,
                    ("roa", "roa_ttm", "return_on_assets", "ROA TTM"),
                )
                net_margin = get_ratio_value(
                    latest_report,
                    financial_data,
                    selected_symbol,
                    (
                        "net_margin",
                        "net_margin_ttm",
                        "net profit margin",
                        "Net Margin TTM",
                    ),
                )


                # --------------------------------------------
                # Current market price
                # --------------------------------------------

                current_price = None


                if not company.empty:

                    latest_price_row = (
                        company
                        .sort_values(
                            "published_date"
                        )
                        .tail(1)
                    )

                    if (
                        not latest_price_row.empty
                        and
                        "close"
                        in latest_price_row.columns
                    ):

                        current_price = (
                            latest_price_row[
                                "close"
                            ].iloc[0]
                        )


                # --------------------------------------------
                # Calculate P/B
                # --------------------------------------------

                pb = None


                if (
                    current_price is not None
                    and bvps is not None
                    and bvps > 0
                ):

                    pb = (
                        current_price
                        / bvps
                    )


                # =================================================
                # VALUATION
                # =================================================

                st.markdown(
                    "### Valuation"
                )


                v1, v2, v3, v4 = (
                    st.columns(4)
                )


                v1.metric(
                    "P/E Ratio",
                    format_number(
                        pe,
                        2,
                    ),
                )


                v2.metric(
                    "P/B Ratio",
                    format_number(
                        pb,
                        2,
                    ),
                )


                v3.metric(
                    "Market Price",
                    format_number(
                        current_price,
                        2,
                    ),
                )


                v4.metric(
                    "BVPS",
                    format_number(
                        bvps,
                        2,
                    ),
                )


                # =================================================
                # PER SHARE
                # =================================================

                st.markdown(
                    "### Per Share"
                )


                p1, p2 = st.columns(2)


                p1.metric(
                    "EPS",
                    format_number(
                        eps,
                        2,
                    ),
                )


                p2.metric(
                    "Book Value Per Share",
                    format_number(
                        bvps,
                        2,
                    ),
                )


                # =================================================
                # COMPANY FINANCIALS
                # =================================================

                st.markdown(
                    "### Company Financials"
                )


                f1, f2 = st.columns(2)


                f1.metric(
                    "Profit",
                    format_number(
                        profit,
                        2,
                    ),
                )


                f2.metric(
                    "Paid-up Capital",
                    format_number(
                        paid_up_capital,
                        2,
                    ),
                )


                # =================================================
                # ADDITIONAL RATIOS
                # =================================================

                st.markdown(
                    "### Additional Ratios"
                )


                r1, r2, r3 = (
                    st.columns(3)
                )


                r1.metric(
                    "ROE",
                    f"{roe:.2f}%" if roe is not None else "N/A",
                )


                r2.metric(
                    "ROA",
                    f"{roa:.2f}%" if roa is not None else "N/A",
                )


                r3.metric(
                    "Net Margin",
                    f"{net_margin:.2f}%" if net_margin is not None else "N/A",
                )


                # =================================================
                # AI RECOMMENDATION
                # =================================================
                # Placed here rather than in the stock list/table or as
                # its own nav tab: it needs P/E, P/B, EPS, ROE and net
                # margin, all of which only exist once this fundamentals
                # section has been loaded for a specific symbol. Putting
                # it in a table column would mean recomputing this per
                # row with no room to show the "why"; putting it in its
                # own tab would separate the verdict from the numbers
                # that justify it.

                st.markdown(
                    "### 🤖 AI Recommendation"
                )

                ai_verdict, ai_summary, ai_reasons = (
                    generate_ai_recommendation(
                        eps=eps,
                        pe=pe,
                        pb=pb,
                        roe=roe,
                        roa=roa,
                        net_margin=net_margin,
                        symbol=selected_symbol,
                    )
                )

                st.markdown(
                    get_ai_recommendation_card_html(
                        ai_verdict,
                        ai_summary,
                        ai_reasons,
                        active_theme,
                    ),
                    unsafe_allow_html=True,
                )


                # =================================================
                # FULL FINANCIAL REPORT (human-readable)
                # =================================================
                # FIX #3: Replaced raw st.json(latest_report) dump
                # with a clean, formatted table. A collapsed,
                # clearly labeled "raw data" expander is kept for
                # advanced users who explicitly want it.

                with st.expander(
                    f"📋 View Complete "
                    f"{selected_symbol} "
                    f"Financial Report"
                ):

                    render_financial_report_readable(
                        latest_report,
                        title=f"{selected_symbol} — Latest Report Summary",
                    )


                # =================================================
                # ALL AVAILABLE REPORTS (human-readable)
                # =================================================

                all_reports = (
                    selected_financial.get(
                        "reports",
                        [],
                    )
                )


                if len(all_reports) > 1:

                    with st.expander(
                        "📚 View Previous "
                        "Financial Reports"
                    ):

                        for i, report in enumerate(
                            all_reports
                        ):

                            report_fy = (
                                report.get(
                                    "fy",
                                    "N/A",
                                )
                            )

                            report_quarter = (
                                report.get(
                                    "quarter",
                                    "N/A",
                                )
                            )

                            st.markdown(
                                f"**Report "
                                f"{i + 1}:** "
                                f"{report_quarter} "
                                f"| FY {report_fy}"
                            )

                            render_financial_report_readable(
                                report,
                                title=f"Report {i + 1} Summary",
                            )

                            st.divider()


# ============================================================
# TAB: LATEST TRADING DAY
# ============================================================

if active_nav == "latest":

    st.subheader(
        "Latest Trading Day"
    )

    latest_date = (
        all_data[
            "published_date"
        ].max()
    )

    latest = all_data[
        all_data[
            "published_date"
        ]
        == latest_date
    ].copy()


    st.write(
        "**Latest date:**",
        latest_date.strftime(
            "%Y-%m-%d"
        ),
    )


    l1, l2, l3 = (
        st.columns(3)
    )


    l1.metric(
        "Symbols",
        latest[
            "symbol"
        ].nunique(),
    )


    if (
        "traded_quantity"
        in latest.columns
    ):

        l2.metric(
            "Total Quantity",
            format_integer(
                latest[
                    "traded_quantity"
                ].sum()
            ),
        )


    if (
        "traded_amount"
        in latest.columns
    ):

        l3.metric(
            "Total Turnover",
            format_number(
                latest[
                    "traded_amount"
                ].sum()
            ),
        )


    sort_option = st.selectbox(

        "Sort by",

        options=[
            "symbol",
            "close",
            "return_percent",
            "traded_quantity",
            "traded_amount",
        ],

        index=0,

        key="latest_sort",
    )


    ascending = st.checkbox(

        "Ascending order",

        value=(
            sort_option
            == "symbol"
        ),

        key="latest_ascending",
    )


    if sort_option in latest.columns:

        latest = latest.sort_values(
            sort_option,
            ascending=ascending,
        )


    latest_columns = [

        c

        for c in [

            "symbol",
            "open",
            "high",
            "low",
            "close",
            "per_change",
            "return_percent",
            "traded_quantity",
            "traded_amount",

        ]

        if c
        in latest.columns
    ]


    st.dataframe(

        latest[
            latest_columns
        ],

        use_container_width=True,

        hide_index=True,
    )


    st.download_button(

        "Download Latest Day",

        data=csv_bytes(
            latest
        ),

        file_name=(
            "NEPSE_LATEST_DAY.csv"
        ),

        mime="text/csv",
    )


# ============================================================
# TAB: RAW DATA
# ============================================================

if active_nav == "data":

    st.subheader(
        "Complete Dataset"
    )


    d1, d2 = (
        st.columns(2)
    )


    with d1:

        symbol_filter = (
            st.multiselect(

                "Filter symbols",

                options=sorted(
                    all_data[
                        "symbol"
                    ]
                    .dropna()
                    .unique()
                    .tolist()
                ),

                default=[],

                key="raw_symbols",
            )
        )


    with d2:

        rows_to_show = (
            st.selectbox(

                "Rows to preview",

                options=[
                    100,
                    500,
                    1000,
                    5000,
                ],

                index=1,

                key="raw_rows",
            )
        )


    raw_filtered = (
        all_data.copy()
    )


    if symbol_filter:

        raw_filtered = (
            raw_filtered[
                raw_filtered[
                    "symbol"
                ].isin(
                    symbol_filter
                )
            ].copy()
        )


    st.write(
        f"Rows selected: "
        f"**{len(raw_filtered):,}**"
    )


    st.dataframe(

        raw_filtered.tail(
            rows_to_show
        ),

        use_container_width=True,

        hide_index=True,
    )


    st.download_button(

        "Download Selected Data",

        data=csv_bytes(
            raw_filtered
        ),

        file_name=(
            "NEPSE_SELECTED_DATA.csv"
        ),

        mime="text/csv",

        type="primary",
    )


# ============================================================
# FOOTER
# ============================================================

# st.markdown(
#     '<div class="ninja-footer">'
#     '🥷 <strong>NEPSE Ninja</strong> '
#     '— Nepal Stock Analysis Dashboard<br>'
#     'Data sourced from locally processed '
#     'NEPSE datasets and online financial data.'
#     '</div>',
#     unsafe_allow_html=True,
# )