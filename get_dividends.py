import pandas as pd

url = "https://www.sharesansar.com/proposed-dividend"

try:
    tables = pd.read_html(url)

    print("Tables found:", len(tables))

    for i, table in enumerate(tables):
        print("\nTABLE", i)
        print(table.head())

except Exception as e:
    print("ERROR:", e)