# NEPSE Streamlit Dashboard

## Setup

### Project Structure
```
project_folder/
├── nepse_streamlit.py
├── README.md
└── nepse_data/
    └── processed/
        ├── NEPSE_ALL_DATA.csv
        ├── NEPSE_LATEST_DAY.csv
        ├── NEPSE_RECENT_30_DAYS.csv
        ├── NEPSE_SYMBOL_COVERAGE.csv (optional)
        └── NEPSE_DAILY_SUMMARY.csv (optional)
```

### Requirements
- Python 3.7+
- pandas
- streamlit

### Installation

Install required packages:
```bash
pip install streamlit pandas
```

### Running the Dashboard

From the project folder:
```bash
streamlit run nepse_streamlit.py
```

The app will open in your default browser at `http://localhost:8501`

## Features

The dashboard includes 6 interactive tabs:

1. **Overview** - Dataset statistics, missing values analysis, and observations by year
2. **Company Analysis** - Analyze individual symbols with price charts, returns, and trading volume
3. **Latest Trading Day** - View current day's trading data, sortable and filterable
4. **Market Activity** - Market-wide trends: total turnover, quantity, and traded symbols
5. **Symbol Coverage** - Coverage period for each symbol
6. **Raw Data** - Browse and export complete dataset with filtering options

## Data Settings

In the sidebar, you can:
- Specify a custom data folder path
- Reload data (clears cache and refreshes)
- View the expected path for the main dataset

## Export Options

All tabs provide CSV download buttons for:
- Company-specific data
- Latest trading day
- Coverage information
- Filtered selections

## Notes

- The app reads locally processed CSV files only
- To update data, run the data downloader script separately
- All charts and tables are interactive
- Dates are automatically parsed and formatted
- Numeric values are cleaned and standardized
