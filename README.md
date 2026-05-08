![Python](https://img.shields.io/badge/python-3.11+-blue)

# Kayak Travel Recommender
> Data pipeline that recommends travel destinations in France based on weather forecasts, hotel scraping, and adaptive Gaussian scoring -- served through an interactive Streamlit dashboard.

## Key Results

- End-to-end pipeline from raw API data to interactive travel recommendations
- Geocoding of 35 French cities + 5-day weather forecasts via OpenWeatherMap
- Adaptive Gaussian weather scoring with seasonal optimization (temperature, rain, cloud weights vary by season)
- Top-5 best-weather destinations + top 4 hotels per destination (20 total, scraped from Booking.com)
- Interactive Plotly maps (destinations + hotels)
- All data persisted to AWS S3 and PostgreSQL (NeonDB)

## Tech Stack

| Category | Technology |
|----------|------------|
| Language | Python 3.11+ |
| Package manager | uv |
| Scraping | Scrapy + Playwright (Booking.com) |
| Data processing | pandas, numpy |
| Storage | boto3 (AWS S3), SQLAlchemy + psycopg2 (PostgreSQL / NeonDB) |
| Visualization | Plotly |
| Dashboard | Streamlit |
| Testing | pytest |
| APIs | OpenWeatherMap, Nominatim (geocoding) |

## Architecture

This project implements Data Lake and Data Warehouse patterns at certification scale (~35 cities, CSV-based). The patterns are genuine; the scale is intentional. The architecture could evolve to production-grade tooling (Parquet/Delta Lake for the lake, Redshift/BigQuery for the warehouse) without changing the pipeline logic.

**Data Lake pattern (AWS S3)** -- S3 organizes data into 3 zones that enforce separation between raw ingestion, transformation, and consumption-ready outputs:

- `raw/` -- Geocoded city coordinates from Nominatim API (`coordinates.csv`)
- `processed/` -- Scored, cleaned, and filtered data (Gaussian-scored cities, deduplicated hotels)
- `final/` -- Enriched, merged datasets ready for consumption (Top-5 destinations with Top-20 hotels)

Each zone acts as an immutable checkpoint: if a downstream step fails, upstream data is preserved and the step can be re-run independently.

**Data Warehouse pattern (PostgreSQL / NeonDB)** -- NeonDB hosts 2 tables (`destinations`, `hotels`) that serve as the structured, queryable data store for end-user consumption. The relational model fits the one-to-many relationship naturally. This is not a star-schema OLAP warehouse -- it is a PostgreSQL database following the DW pattern of providing clean, structured data optimized for analytical queries via the Streamlit dashboard.

**ETL pipeline** -- The core value of the architecture. Data flows from external APIs and scraping through S3 zones (decoupling producers from consumers), then an ETL step loads the final datasets into PostgreSQL. The dashboard never reads from S3 directly; all user-facing queries go through the database.

**Flow:** APIs/Scraping -> S3 `raw/` -> Processing -> S3 `processed/` -> Merging -> S3 `final/` -> ETL -> PostgreSQL -> Dashboard

## Prerequisites

- Python 3.11+
- [uv](https://docs.astral.sh/uv/) package manager
- API keys and services:
  - **OpenWeatherMap** -- API key ([register here](https://openweathermap.org/api))
  - **AWS** -- access key + secret key with S3 permissions
  - **PostgreSQL (NeonDB)** -- host, database, user, password ([free tier](https://neon.tech))
- Playwright browser install (Chromium, one-time setup)

## Installation

```bash
# Install dependencies
make setup

# Copy and fill in your API keys
cp .env.template .env
nano .env

# Install Playwright browsers (required for hotel scraping)
make setup-scraping

# Verify installation
make test
```

## Usage

Run the full pipeline (weather -> scrape -> merge -> etl -> visualize -> dashboard):

```bash
make all
```

Or run individual steps:

```bash
make weather          # Geocode cities, fetch forecasts, compute scores, generate Top-5
make scrape-hotels    # Scrape hotels from Top-5 destinations on Booking.com
make merge-data       # Merge weather + hotels data, produce Top-20 recommendations
make etl              # Load final data from S3 into PostgreSQL (NeonDB)
make verify-db        # Verify database integrity after ETL
make visualize        # Generate interactive Plotly HTML maps
make dashboard        # Start Streamlit dashboard at http://localhost:8501
```

Run `make help` for the full list of available commands.

## Data

All data flows through AWS S3 (raw -> processed -> final). Local output is written to `data/output/`. No data files are committed to the repository (gitignored). The pipeline is designed for local execution only -- there is no deployment target.

## Data Privacy

Only publicly available data is collected -- no personal data, no user tracking, no cookies. Rate limiting is enforced on all external sources: 3-second delay on Booking.com, 1-second delay on Nominatim. `ROBOTSTXT_OBEY = False` is set for Booking.com; this is justified by the academic context (certification project, no redistribution or commercial use) and compensated by strict rate limiting.

## License

This project is for educational purposes only (certification Bloc 1 -- Data Infrastructure).

Released under the [MIT License](LICENSE).
