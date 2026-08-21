# ============================================================
# SCRAPE FINANCIAL DATA TABLE FROM NEPSEALPHA.COM
# For one or more NEPSE stock symbols
#
# Requires: pip install selenium pandas
# Selenium 4.6+ auto-downloads the right ChromeDriver for you
# (via "Selenium Manager") — you do NOT need to install
# ChromeDriver manually. You DO need Google Chrome installed.
# ============================================================

import io
import time

import pandas as pd
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException


# ------------------------------------------------------------
# SETTINGS
# ------------------------------------------------------------

# The exact table XPath you found via inspecting the page
TABLE_XPATH = (
    '//*[@id="home"]/div/div[2]/div[2]/div/div/div[2]/'
    'div[1]/div/div/div/div[2]/table'
)

BASE_URL = "https://nepsealpha.com/search?q={symbol}"

OUT_FILE = "nepsealpha_financials.csv"

# Add as many NEPSE symbols as you want here
SYMBOLS = ["NABIL", "SCB", "NTC", "GBIME"]

HEADLESS = True          # set False if you want to watch it run
PAGE_LOAD_WAIT = 15       # seconds to wait for the table to appear
DELAY_BETWEEN_REQUESTS = 3  # be polite, avoid getting blocked


# ------------------------------------------------------------
# BROWSER SETUP
# ------------------------------------------------------------

def make_driver():
    options = Options()
    if HEADLESS:
        options.add_argument("--headless=new")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--disable-gpu")
    options.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0.0.0 Safari/537.36"
    )
    return webdriver.Chrome(options=options)


# ------------------------------------------------------------
# SCRAPE ONE SYMBOL
# ------------------------------------------------------------

def scrape_symbol(driver, symbol):
    url = BASE_URL.format(symbol=symbol)
    print(f"\nFetching {symbol} -> {url}")

    driver.get(url)

    try:
        WebDriverWait(driver, PAGE_LOAD_WAIT).until(
            EC.presence_of_element_located((By.XPATH, TABLE_XPATH))
        )
    except TimeoutException:
        print(f"  ⚠ Table did not load for {symbol} within {PAGE_LOAD_WAIT}s.")
        return None

    table_element = driver.find_element(By.XPATH, TABLE_XPATH)
    table_html = table_element.get_attribute("outerHTML")

    try:
        df = pd.read_html(io.StringIO(table_html))[0]
    except ValueError:
        print(f"  ⚠ pandas could not parse a table for {symbol}.")
        return None

    df.columns = [str(c).strip() for c in df.columns]
    df.insert(0, "symbol", symbol)

    print(f"  ✅ Got {len(df)} rows for {symbol}.")
    return df


# ------------------------------------------------------------
# MAIN
# ------------------------------------------------------------

def main():
    driver = make_driver()
    all_frames = []

    try:
        for symbol in SYMBOLS:
            df = scrape_symbol(driver, symbol)
            if df is not None:
                all_frames.append(df)
            time.sleep(DELAY_BETWEEN_REQUESTS)
    finally:
        driver.quit()

    if not all_frames:
        print("\n❌ No data scraped for any symbol.")
        return

    combined = pd.concat(all_frames, ignore_index=True)
    combined.to_csv(OUT_FILE, index=False)

    print(f"\n✅ SUCCESS! Saved {len(combined)} rows to '{OUT_FILE}'.")
    print(combined.head(10))


if __name__ == "__main__":
    main()