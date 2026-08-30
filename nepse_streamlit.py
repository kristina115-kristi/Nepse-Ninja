from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st
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
    get_navbar_html,
    get_hero_html,
    get_market_status,
    get_popular_tags_html,
    get_sector_pills_html,
    get_company_list_modal_html,
    SECTOR_CLASS_MAP,
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
# THEME
# ============================================================

active_nav = st.query_params.get("nav", "home")
active_theme = get_theme(st.query_params)

st.markdown(
    get_ninja_css(active_theme),
    unsafe_allow_html=True,
)

st.markdown(
    get_navbar_html(active_nav, active_theme),
    unsafe_allow_html=True,
)


# ============================================================
# PATH SETTINGS
# ============================================================

BASE_DIR = Path.cwd()

DEFAULT_PROCESSED_DIR = (
    BASE_DIR / "nepse_data" / "processed"
)

ALL_DATA_FILE = "NEPSE_ALL_DATA.csv"
LATEST_DAY_FILE = "NEPSE_LATEST_DAY.csv"
RECENT_FILE = "NEPSE_RECENT_30_DAYS.csv"
COVERAGE_FILE = "NEPSE_SYMBOL_COVERAGE.csv"
DAILY_SUMMARY_FILE = "NEPSE_DAILY_SUMMARY.csv"

# These are now optional/legacy.
# Financial fundamentals come from the online API.
FINANCIAL_FILE = "nepsealpha_financials.csv"
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
            timeout=30,
        )

        response.raise_for_status()

        data = response.json()

        if not isinstance(data, list):

            st.error(
                "Financial API returned "
                "an unexpected format."
            )

            return []

        return data

    except Exception as e:

        st.error(
            f"Could not load online "
            f"financial data: {e}"
        )

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


# ============================================================
# CHECK MAIN FILE
# ============================================================

if not all_data_path.exists():

    st.error(
        "NEPSE_ALL_DATA.csv was not found."
    )

    st.write(
        "Run the downloader first:"
    )

    st.code(
        "python download_nepse_data.py"
    )

    st.write(
        "Then make sure this file exists:"
    )

    st.code(
        str(all_data_path)
    )

    st.stop()


# ============================================================
# LOAD MAIN DATA
# ============================================================

with st.spinner(
    "Loading NEPSE historical data..."
):

    all_data = load_csv(
        str(all_data_path)
    )

    all_data = prepare_all_data(
        all_data
    )


if all_data.empty:

    st.error(
        "The main NEPSE dataset is empty."
    )

    st.stop()


# ============================================================
# LOAD ONLINE FINANCIAL DATA
# ============================================================

with st.spinner(
    "Loading online financial data..."
):

    online_financial_data = (
        load_online_financials()
    )


# ============================================================
# LOAD OPTIONAL FILES
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


(
    latest_day,
    recent_data,
    coverage,
    daily_summary,
) = load_optional_files(
    str(processed_dir)
)


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

financial_data = load_csv(
    str(financial_path)
)

dividend_data = load_csv(
    str(dividend_path)
)


# ============================================================
# SECTOR MAPPING
# ============================================================

_sector_path = (
    BASE_DIR / "sector_mapping.csv"
)

sector_mapping = load_csv(
    str(_sector_path)
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

    st.markdown(
        get_hero_html(
            get_market_status()
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

        home_symbol = st.text_input(

            "Search",

            placeholder=(
                "Search NEPSE stocks "
                "by symbol, name or sector..."
            ),

            label_visibility="collapsed",

            key="home_search_input",
        ).strip().upper()


    st.markdown(
        get_popular_tags_html(
            POPULAR_STOCKS
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
            "## 📊 Financial Fundamentals"
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


                # The current API response does not
                # directly provide enough information
                # to calculate these safely.

                r1.metric(
                    "ROE",
                    "N/A",
                )


                r2.metric(
                    "ROA",
                    "N/A",
                )


                r3.metric(
                    "Net Margin",
                    "N/A",
                )


                st.caption(
                    "ROE, ROA and Net Margin are "
                    "shown as N/A until the API "
                    "provides the required "
                    "financial statement fields."
                )


                # =================================================
                # RAW FINANCIAL REPORT
                # =================================================

                with st.expander(
                    f"📋 View Complete "
                    f"{selected_symbol} "
                    f"Financial Report"
                ):

                    st.json(
                        latest_report
                    )


                # =================================================
                # ALL AVAILABLE REPORTS
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

                            st.json(
                                report
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