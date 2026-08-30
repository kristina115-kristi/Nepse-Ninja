"""Scrape NEPSEAlpha financial tables for the full NEPSE symbol universe. Install: pip install selenium pandas lxml Google Colab install: %pip install selenium pandas lxml google-colab-selenium Examples: python nepsealpha_all_financials.py python nepsealpha_all_financials.py --symbols NABIL SCB NTC GBIME python nepsealpha_all_financials.py --symbols-file symbols.csv python nepsealpha_all_financials.py --max-symbols 5 The default run downloads a maintained NEPSE symbol list, opens each company's ``financials-menu`` page, saves the source table per symbol, and creates both a wide and a research-friendly long CSV. Successful symbols are skipped when the script is rerun, so an interrupted full-market scrape can be resumed. """

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import random
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable
from urllib.parse import parse_qs, quote, urlparse
from urllib.request import Request, urlopen

import pandas as pd
from selenium import webdriver
from selenium.common.exceptions import TimeoutException, WebDriverException
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait


BASE_URL = (
    "https://www.nepsealpha.com/search?q={symbol}&tab=financials-menu"
)

# Public, actively maintained list used only to obtain the NEPSE symbol universe.
# Securities with no company financial table (debentures, some mutual funds,
# promoter shares, etc.) are recorded as ``no_financial_table`` and skipped.
DEFAULT_SYMBOLS_URL = (
    "https://cdn.jsdelivr.net/gh/SamirWagle/Nepse-All-Scraper@main/"
    "data/company_list.json"
)

FINANCIAL_METRICS = (
    "paid up capital",
    "total equity",
    "total assets",
    "net profit",
    "gross profit",
    "operating profit",
    "revenue",
    "earning per share",
    "earnings per share",
    "book value",
    "net worth",
    "deposit",
    "loan and advance",
)

SECURITY_PAGE_MARKERS = (
    "performing security verification",
    "verify you are human",
    "checking your browser",
    "attention required",
)

METADATA_COLUMNS = {
    "symbol",
    "table_type",
    "table_index",
    "source_url",
    "scraped_at_utc",
}


class NoFinancialTableError(RuntimeError):
    """Raised when the requested symbol has no qualifying financial table."""


class SecurityVerificationError(RuntimeError):
    """Raised when NEPSEAlpha's security verification blocks the browser."""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Scrape NEPSEAlpha financials for all or selected symbols."
    )
    source = parser.add_mutually_exclusive_group()
    source.add_argument(
        "--symbols",
        nargs="+",
        help="Specific NEPSE symbols, e.g. --symbols NABIL SCB NTC.",
    )
    source.add_argument(
        "--symbols-file",
        type=Path,
        help="CSV (preferably with a 'symbol' column) or one-symbol-per-line file.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("nepsealpha_output"),
        help="Output directory (default: nepsealpha_output).",
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        help="Run Chrome headlessly. Visible Chrome is more reliable for site verification.",
    )
    parser.add_argument(
        "--profile-dir",
        type=Path,
        default=Path(".nepsealpha_chrome_profile"),
        help="Persistent Chrome profile for cookies/site verification.",
    )
    parser.add_argument(
        "--page-wait",
        type=float,
        default=25.0,
        help="Seconds to wait for each company's financial table (default: 25).",
    )
    parser.add_argument(
        "--verification-wait",
        type=float,
        default=180.0,
        help="Seconds to wait for a visible-browser verification (default: 180).",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=3.0,
        help="Minimum delay between companies in seconds (default: 3).",
    )
    parser.add_argument(
        "--delay-jitter",
        type=float,
        default=2.0,
        help="Random seconds added to --delay (default: 2).",
    )
    parser.add_argument(
        "--retries",
        type=int,
        default=2,
        help="Attempts per symbol (default: 2).",
    )
    parser.add_argument(
        "--max-symbols",
        type=int,
        help="Limit the run for testing, e.g. --max-symbols 5.",
    )
    parser.add_argument(
        "--no-resume",
        action="store_true",
        help="Reprocess symbols even if their prior status is successful.",
    )
    # Jupyter/Colab launches the kernel with private arguments such as
    # ``-f /root/.../kernel.json``. Ignore those inside a notebook, while still
    # rejecting misspelled options during normal command-line execution.
    args, unknown = parser.parse_known_args()
    running_in_notebook = "ipykernel" in sys.modules
    if unknown and not running_in_notebook:
        parser.error(f"unrecognized arguments: {' '.join(unknown)}")
    return args


def running_in_colab() -> bool:
    return "google.colab" in sys.modules or bool(os.environ.get("COLAB_RELEASE_TAG"))


def normalize_symbols(values: Iterable[object]) -> list[str]:
    seen: set[str] = set()
    symbols: list[str] = []
    for value in values:
        symbol = str(value).strip().upper()
        if not symbol or symbol in {"NAN", "NONE", "SYMBOL"}:
            continue
        if symbol not in seen:
            seen.add(symbol)
            symbols.append(symbol)
    return symbols


def fetch_all_symbols(url: str = DEFAULT_SYMBOLS_URL) -> list[str]:
    request = Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urlopen(request, timeout=30) as response:
        payload = json.load(response)

    if isinstance(payload, list):
        if payload and isinstance(payload[0], dict):
            values = [
                row.get("symbol") or row.get("stock_symbol") or row.get("ticker")
                for row in payload
            ]
        else:
            values = payload
    elif isinstance(payload, dict):
        rows = payload.get("data") or payload.get("companies") or payload.get("symbols")
        if not isinstance(rows, list):
            raise ValueError("Symbol-list JSON has an unsupported structure.")
        values = [
            (row.get("symbol") if isinstance(row, dict) else row) for row in rows
        ]
    else:
        raise ValueError("Symbol-list JSON has an unsupported structure.")

    symbols = normalize_symbols(values)
    if len(symbols) < 100:
        raise ValueError(
            f"Only {len(symbols)} symbols were returned; refusing an incomplete all-market run."
        )
    return symbols


def load_symbols_file(path: Path) -> list[str]:
    if not path.exists():
        raise FileNotFoundError(f"Symbols file not found: {path}")

    if path.suffix.lower() == ".csv":
        frame = pd.read_csv(path, dtype=str)
        if frame.empty:
            return []
        column = next(
            (column for column in frame.columns if column.strip().lower() == "symbol"),
            frame.columns[0],
        )
        return normalize_symbols(frame[column])

    return normalize_symbols(path.read_text(encoding="utf-8").splitlines())


def make_driver(headless: bool, profile_dir: Path) -> webdriver.Chrome:
    if running_in_colab():
        # Selenium Manager and Colab's preinstalled/cached browser can drift out
        # of compatibility and fail before a session is created. This wrapper
        # installs and pairs Google Chrome Stable with its driver, then applies
        # Colab's required headless/container flags.
        try:
            import google_colab_selenium as gs
        except ModuleNotFoundError as exc:
            raise RuntimeError(
                "Google Colab requires its browser bootstrap package. Run this "
                "in a new cell, restart the session, and rerun the script:\n"
                "%pip install -q -U selenium pandas lxml google-colab-selenium"
            ) from exc

        colab_options = Options()
        colab_options.add_argument("--window-size=1920,1080")
        colab_options.add_argument("--disable-gpu")
        colab_options.page_load_strategy = "eager"
        return gs.Chrome(options=colab_options)

    options = Options()
    if headless:
        options.add_argument("--headless=new")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-setuid-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--remote-debugging-port=0")
    options.add_argument("--disable-extensions")
    options.add_argument("--disable-software-rasterizer")

    options.add_argument(f"--user-data-dir={profile_dir.resolve()}")
    options.page_load_strategy = "eager"
    return webdriver.Chrome(options=options)


def page_is_security_verification(driver: webdriver.Chrome) -> bool:
    content = (driver.title + "\n" + driver.page_source[:200_000]).lower()
    return any(marker in content for marker in SECURITY_PAGE_MARKERS)


def wait_for_site_access( driver: webdriver.Chrome, *, headless: bool, verification_wait: float, ) -> None:
    if not page_is_security_verification(driver):
        return

    if headless:
        raise SecurityVerificationError(
            "NEPSEAlpha showed a browser-security verification page. "
            "Run again without --headless so the verification can complete in visible Chrome."
        )

    print(
        " Site verification is open in Chrome. Complete it there if prompted; "
        f"waiting up to {verification_wait:.0f} seconds ..."
    )
    try:
        WebDriverWait(driver, verification_wait, poll_frequency=1).until(
            lambda browser: not page_is_security_verification(browser)
        )
    except TimeoutException as exc:
        raise SecurityVerificationError(
            "NEPSEAlpha's browser-security verification did not clear in time. "
            "The saved progress is safe; rerun later to resume."
        ) from exc


def flatten_header(column: object) -> str:
    if isinstance(column, tuple):
        parts = [
            str(part).strip()
            for part in column
            if str(part).strip() and not str(part).lower().startswith("unnamed")
        ]
        text = " | ".join(dict.fromkeys(parts))
    else:
        text = str(column).strip()
    text = re.sub(r"\s+", " ", text)
    return text or "unnamed"


def make_unique_headers(columns: Iterable[object]) -> list[str]:
    counts: dict[str, int] = {}
    result: list[str] = []
    for column in columns:
        base = flatten_header(column)
        counts[base] = counts.get(base, 0) + 1
        result.append(base if counts[base] == 1 else f"{base}_{counts[base]}")
    return result


def clean_dataframe(frame: pd.DataFrame) -> pd.DataFrame:
    frame = frame.copy()
    frame.columns = make_unique_headers(frame.columns)
    frame = frame.dropna(axis=0, how="all").dropna(axis=1, how="all")
    frame = frame.fillna("")
    for column in frame.columns:
        frame[column] = frame[column].map(
            lambda value: re.sub(r"\s+", " ", str(value)).strip()
        )
    return frame.reset_index(drop=True)


def looks_like_period(text: str) -> bool:
    value = text.upper().replace(" ", "")
    return bool(
        re.search(r"Q[1-4]", value)
        or re.search(r"\d{2,4}[-/]\d{2,4}", value)
        or re.fullmatch(r"20\d{2}", value)
    )


def is_financial_table(frame: pd.DataFrame) -> bool:
    if frame.empty or frame.shape[1] < 2:
        return False
    headers = " ".join(map(str, frame.columns)).lower()
    sample = " ".join(frame.astype(str).head(30).to_numpy().ravel()).lower()
    metric_hits = sum(metric in sample for metric in FINANCIAL_METRICS)
    period_hits = sum(looks_like_period(str(column)) for column in frame.columns)
    has_particular = "particular" in headers
    return (has_particular and (period_hits > 0 or metric_hits > 0)) or metric_hits >= 3


def classify_table(frame: pd.DataFrame) -> str:
    headers = [str(column).upper().replace(" ", "") for column in frame.columns]
    if any(re.search(r"Q[1-4]", header) for header in headers):
        return "quarterly_financials"
    if any(looks_like_period(header) for header in headers):
        return "annual_financials"
    return "financial_table"


def visible_table_html(driver: webdriver.Chrome) -> list[str]:
    # #home is the company-detail area in the current site. The general fallback
    # keeps the scraper usable if NEPSEAlpha changes that container ID.
    elements = driver.find_elements(By.CSS_SELECTOR, "#home table")
    if not elements:
        elements = driver.find_elements(By.TAG_NAME, "table")

    html_tables: list[str] = []
    seen: set[str] = set()
    for element in elements:
        try:
            if not element.is_displayed():
                continue
            outer_html = element.get_attribute("outerHTML") or ""
        except WebDriverException:
            continue
        digest = hashlib.sha256(outer_html.encode("utf-8")).hexdigest()
        if outer_html and digest not in seen:
            seen.add(digest)
            html_tables.append(outer_html)
    return html_tables


def parse_financial_tables(html_tables: Iterable[str]) -> list[pd.DataFrame]:
    results: list[pd.DataFrame] = []
    fingerprints: set[str] = set()
    for table_html in html_tables:
        try:
            candidates = pd.read_html(io.StringIO(table_html), displayed_only=False)
        except (ValueError, ImportError):
            continue
        for candidate in candidates:
            frame = clean_dataframe(candidate)
            if not is_financial_table(frame):
                continue
            digest = hashlib.sha256(
                frame.to_csv(index=False).encode("utf-8")
            ).hexdigest()
            if digest not in fingerprints:
                fingerprints.add(digest)
                results.append(frame)
    return results


def exact_symbol_visible(driver: webdriver.Chrome, symbol: str) -> bool:
    selectors = "h1, h2, h3, h4, h5, h6, [class*='symbol'], [data-symbol]"
    parts = [driver.title]
    for element in driver.find_elements(By.CSS_SELECTOR, selectors):
        try:
            if element.is_displayed():
                parts.append(element.text)
                data_symbol = element.get_attribute("data-symbol")
                if data_symbol:
                    parts.append(data_symbol)
        except WebDriverException:
            continue

    text = "\n".join(parts).upper()
    pattern = rf"(?<![A-Z0-9]){re.escape(symbol.upper())}(?![A-Z0-9])"
    return re.search(pattern, text) is not None


def table_fingerprint(tables: Iterable[pd.DataFrame]) -> str:
    payload = "\n---TABLE---\n".join(
        table.to_csv(index=False) for table in tables
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def load_existing_fingerprints(per_symbol_dir: Path) -> dict[str, str]:
    """Load saved table hashes so stale-table detection also works after resume."""
    grouped: dict[str, list[tuple[int, pd.DataFrame]]] = {}
    for path in sorted(per_symbol_dir.glob("*_table_*.csv")):
        try:
            frame = pd.read_csv(path, dtype=str, keep_default_na=False)
        except (OSError, pd.errors.ParserError):
            continue
        if frame.empty or "symbol" not in frame.columns:
            continue
        symbol = str(frame.iloc[0]["symbol"]).strip().upper()
        try:
            table_index = int(str(frame.iloc[0].get("table_index", "1")))
        except ValueError:
            table_index = 1
        financial_columns = [
            column for column in frame.columns if str(column) not in METADATA_COLUMNS
        ]
        grouped.setdefault(symbol, []).append(
            (table_index, clean_dataframe(frame[financial_columns]))
        )

    fingerprints: dict[str, str] = {}
    for symbol, indexed_tables in grouped.items():
        tables = [table for _, table in sorted(indexed_tables, key=lambda item: item[0])]
        fingerprints[table_fingerprint(tables)] = symbol
    return fingerprints


def scrape_symbol_once( driver: webdriver.Chrome, symbol: str, *, page_wait: float, verification_wait: float, headless: bool, cache_bust: bool, ) -> tuple[list[pd.DataFrame], str]:
    encoded = quote(symbol, safe="")
    url = BASE_URL.format(symbol=encoded)
    if cache_bust:
        url += f"&_={time.time_ns()}"

    print(f"\nFetching {symbol} -> {url}")
    driver.get(url)
    wait_for_site_access(
        driver,
        headless=headless,
        verification_wait=verification_wait,
    )

    current_query = parse_qs(urlparse(driver.current_url).query)
    loaded_symbol = (current_query.get("q") or [""])[0].upper()
    if loaded_symbol != symbol.upper():
        raise RuntimeError(
            f"Requested {symbol}, but the loaded URL reports {loaded_symbol or 'no symbol'}."
        )

    deadline = time.monotonic() + page_wait
    tables: list[pd.DataFrame] = []
    while time.monotonic() < deadline:
        wait_for_site_access(
            driver,
            headless=headless,
            verification_wait=verification_wait,
        )
        tables = parse_financial_tables(visible_table_html(driver))
        if tables:
            break
        time.sleep(0.75)

    if not tables:
        raise NoFinancialTableError(
            f"No qualifying financial table appeared within {page_wait:.0f}s."
        )

    if not exact_symbol_visible(driver, symbol):
        raise RuntimeError(
            f"A table loaded, but {symbol} was not visible in the company heading/title. "
            "This prevents a stale/default NABIL table from being saved under the wrong symbol."
        )

    return tables, driver.current_url


def scrape_symbol( driver: webdriver.Chrome, symbol: str, *, page_wait: float, verification_wait: float, headless: bool, retries: int, ) -> tuple[list[pd.DataFrame], str]:
    last_error: Exception | None = None
    for attempt in range(1, max(retries, 1) + 1):
        try:
            return scrape_symbol_once(
                driver,
                symbol,
                page_wait=page_wait,
                verification_wait=verification_wait,
                headless=headless,
                cache_bust=attempt > 1,
            )
        except SecurityVerificationError:
            raise
        except NoFinancialTableError as exc:
            # A second attempt distinguishes a genuinely unavailable statement
            # from a slow first render.
            last_error = exc
        except (TimeoutException, WebDriverException, RuntimeError, ValueError) as exc:
            last_error = exc

        if attempt < max(retries, 1):
            print(f" Attempt {attempt} failed: {last_error}. Retrying ...")
            time.sleep(2)

    assert last_error is not None
    raise last_error


def safe_symbol_filename(symbol: str) -> str:
    return re.sub(r"[^A-Z0-9._-]+", "_", symbol.upper())


def save_symbol_tables( tables: list[pd.DataFrame], symbol: str, source_url: str, per_symbol_dir: Path, ) -> list[Path]:
    per_symbol_dir.mkdir(parents=True, exist_ok=True)
    scraped_at = datetime.now(timezone.utc).isoformat()
    paths: list[Path] = []
    safe_symbol = safe_symbol_filename(symbol)

    for table_index, table in enumerate(tables, start=1):
        output = table.copy()
        output.insert(0, "scraped_at_utc", scraped_at)
        output.insert(0, "source_url", source_url)
        output.insert(0, "table_index", table_index)
        output.insert(0, "table_type", classify_table(table))
        output.insert(0, "symbol", symbol)
        path = per_symbol_dir / f"{safe_symbol}_table_{table_index:02d}.csv"
        output.to_csv(path, index=False, encoding="utf-8-sig")
        paths.append(path)
    return paths


def find_particular_column(frame: pd.DataFrame) -> str | None:
    for column in frame.columns:
        if "particular" in str(column).lower():
            return str(column)
    candidates = [str(column) for column in frame.columns if column not in METADATA_COLUMNS]
    return candidates[0] if candidates else None


def parse_numeric(raw_value: object) -> float | None:
    text = str(raw_value).strip()
    if not text or text.lower() in {"nan", "-", "--", "n/a", "na"}:
        return None
    negative = text.startswith("(") and text.endswith(")")
    cleaned = re.sub(r"[^0-9.\-]", "", text.replace(",", ""))
    if cleaned in {"", "-", ".", "-."}:
        return None
    try:
        value = float(cleaned)
    except ValueError:
        return None
    return -abs(value) if negative else value


def unit_for_value(raw_value: object, particular_header: str) -> str:
    text = str(raw_value)
    header = particular_header.lower()
    if "%" in text:
        return "percent"
    if "000" in header and ("rs" in header or "npr" in header):
        return "NPR_thousands"
    return "as_reported"


def wide_to_long(frame: pd.DataFrame) -> pd.DataFrame:
    particular = find_particular_column(frame)
    if particular is None:
        return pd.DataFrame()

    yoy_column = next(
        (str(column) for column in frame.columns if "yoy" in str(column).lower()),
        None,
    )
    period_columns = [
        str(column)
        for column in frame.columns
        if str(column) not in METADATA_COLUMNS
        and str(column) != particular
        and str(column) != yoy_column
        and "chart" not in str(column).lower()
        and looks_like_period(str(column))
    ]

    records: list[dict[str, object]] = []
    for _, row in frame.iterrows():
        metric = str(row.get(particular, "")).strip()
        if not metric or metric.lower() == "nan":
            continue
        yoy_growth = str(row.get(yoy_column, "")).strip() if yoy_column else ""
        for period in period_columns:
            raw_value = str(row.get(period, "")).strip()
            records.append(
                {
                    "symbol": row.get("symbol", ""),
                    "table_type": row.get("table_type", ""),
                    "table_index": row.get("table_index", ""),
                    "particular": metric,
                    "period": period,
                    "raw_value": raw_value,
                    "value_numeric": parse_numeric(raw_value),
                    "unit": unit_for_value(raw_value, particular),
                    "yoy_growth": yoy_growth,
                    "source_url": row.get("source_url", ""),
                    "scraped_at_utc": row.get("scraped_at_utc", ""),
                }
            )
    return pd.DataFrame.from_records(records)


def build_combined_outputs(per_symbol_dir: Path, output_dir: Path) -> tuple[int, int]:
    files = sorted(per_symbol_dir.glob("*_table_*.csv"))
    if not files:
        return 0, 0

    wide_frames = [pd.read_csv(path, dtype=str, keep_default_na=False) for path in files]
    combined_wide = pd.concat(wide_frames, ignore_index=True, sort=False)
    wide_path = output_dir / "nepsealpha_financials_wide.csv"
    combined_wide.to_csv(wide_path, index=False, encoding="utf-8-sig")

    long_frames = [frame for frame in map(wide_to_long, wide_frames) if not frame.empty]
    if long_frames:
        combined_long = pd.concat(long_frames, ignore_index=True, sort=False)
    else:
        combined_long = pd.DataFrame()
    long_path = output_dir / "nepsealpha_financials_long.csv"
    combined_long.to_csv(long_path, index=False, encoding="utf-8-sig")
    return len(combined_wide), len(combined_long)


def load_status(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame(columns=["symbol", "status", "tables", "rows", "message", "updated_at_utc"])
    return pd.read_csv(path, dtype=str, keep_default_na=False)


def update_status(path: Path, record: dict[str, object]) -> None:
    status = load_status(path)
    if "symbol" in status.columns:
        status = status[status["symbol"] != str(record["symbol"])]
    status = pd.concat([status, pd.DataFrame([record])], ignore_index=True)
    status = status.sort_values("symbol", kind="stable")
    status.to_csv(path, index=False, encoding="utf-8-sig")


def status_record( symbol: str, status: str, *, tables: int = 0, rows: int = 0, message: str = "", ) -> dict[str, object]:
    return {
        "symbol": symbol,
        "status": status,
        "tables": tables,
        "rows": rows,
        "message": message,
        "updated_at_utc": datetime.now(timezone.utc).isoformat(),
    }


def main() -> None:
    args = parse_args()
    if running_in_colab() and not args.headless:
        # Colab has no desktop window in which to display ordinary Chrome.
        args.headless = True
        print("Google Colab detected: using headless Chrome.")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    per_symbol_dir = args.output_dir / "per_symbol"
    status_path = args.output_dir / "nepsealpha_scrape_status.csv"

    if args.symbols:
        symbols = normalize_symbols(args.symbols)
        symbol_source = "command line"
    elif args.symbols_file:
        symbols = load_symbols_file(args.symbols_file)
        symbol_source = str(args.symbols_file)
    else:
        print(f"Downloading current NEPSE symbol list from:\n {DEFAULT_SYMBOLS_URL}")
        symbols = fetch_all_symbols()
        symbol_source = "all-market symbol list"

    if args.max_symbols is not None:
        symbols = symbols[: max(args.max_symbols, 0)]
    if not symbols:
        raise SystemExit("No symbols to process.")

    prior_status = load_status(status_path)
    completed = set()
    if not args.no_resume and not prior_status.empty:
        completed = set(
            prior_status.loc[
                prior_status["status"].isin(["ok", "no_financial_table"]), "symbol"
            ]
        )

    pending = [symbol for symbol in symbols if symbol not in completed]
    print(
        f"Loaded {len(symbols)} symbols from {symbol_source}; "
        f"{len(pending)} pending and {len(symbols) - len(pending)} already complete."
    )

    if not pending:
        wide_rows, long_rows = build_combined_outputs(per_symbol_dir, args.output_dir)
        print(f"Nothing to scrape. Combined outputs contain {wide_rows} wide and {long_rows} long rows.")
        return

    driver = make_driver(args.headless, args.profile_dir)
    known_fingerprints = load_existing_fingerprints(per_symbol_dir)
    security_blocked = False

    try:
        for position, symbol in enumerate(pending, start=1):
            print(f"\n[{position}/{len(pending)}] {symbol}")
            try:
                tables, source_url = scrape_symbol(
                    driver,
                    symbol,
                    page_wait=args.page_wait,
                    verification_wait=args.verification_wait,
                    headless=args.headless,
                    retries=args.retries,
                )

                fingerprint = table_fingerprint(tables)
                duplicate_of = known_fingerprints.get(fingerprint)
                if duplicate_of and duplicate_of != symbol:
                    print(
                        f" Table exactly matches {duplicate_of}; forcing one fresh reload "
                        "to guard against stale/default NABIL data."
                    )
                    tables, source_url = scrape_symbol_once(
                        driver,
                        symbol,
                        page_wait=args.page_wait,
                        verification_wait=args.verification_wait,
                        headless=args.headless,
                        cache_bust=True,
                    )
                    fingerprint = table_fingerprint(tables)
                    duplicate_of = known_fingerprints.get(fingerprint)
                    if duplicate_of and duplicate_of != symbol:
                        raise RuntimeError(
                            f"Financial table is still identical to {duplicate_of}; "
                            "not saving potentially stale data."
                        )

                known_fingerprints[fingerprint] = symbol
                paths = save_symbol_tables(tables, symbol, source_url, per_symbol_dir)
                row_count = sum(len(table) for table in tables)
                update_status(
                    status_path,
                    status_record(
                        symbol,
                        "ok",
                        tables=len(tables),
                        rows=row_count,
                        message="; ".join(path.name for path in paths),
                    ),
                )
                print(f" Saved {row_count} rows across {len(tables)} table(s).")

            except NoFinancialTableError as exc:
                update_status(
                    status_path,
                    status_record(symbol, "no_financial_table", message=str(exc)),
                )
                print(f" No company financial table: {exc}")
            except SecurityVerificationError as exc:
                update_status(
                    status_path,
                    status_record(symbol, "blocked", message=str(exc)),
                )
                print(f" STOPPED: {exc}")
                security_blocked = True
                break
            except Exception as exc:  # Continue the market-wide batch and log the symbol.
                update_status(
                    status_path,
                    status_record(symbol, "failed", message=f"{type(exc).__name__}: {exc}"),
                )
                print(f" Failed: {type(exc).__name__}: {exc}")

            if position < len(pending):
                time.sleep(max(args.delay, 0) + random.uniform(0, max(args.delay_jitter, 0)))
    finally:
        driver.quit()

    wide_rows, long_rows = build_combined_outputs(per_symbol_dir, args.output_dir)
    print("\nFinished building outputs:")
    print(f" {args.output_dir / 'nepsealpha_financials_wide.csv'} ({wide_rows} rows)")
    print(f" {args.output_dir / 'nepsealpha_financials_long.csv'} ({long_rows} rows)")
    print(f" {status_path}")
    if security_blocked:
        print("Rerun without --headless; completed symbols will be skipped automatically.")


if __name__ == "__main__":
    main()