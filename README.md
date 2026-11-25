> ## Educational project: please do not reproduce
>
> This repository is a learning exercise in data engineering (API ingestion, S3 data lake,
> PostgreSQL warehouse, Streamlit). The hotel-listing step uses a scraper against Booking.com.
> It is published to show how the pipeline is structured, not as a tool to collect Booking.com
> data, and it should not be run at scale or reused for that purpose. Booking.com's terms of use
> apply to anyone who runs it; this project does not claim any permission from Booking.com.
>
> What the scraping code does, as implemented:
> - Low volume: at most 25 pages per run with the defaults
>   (5 destinations x (1 results page + 4 hotel pages)).
> - Sequential and slowed down: one request at a time (`CONCURRENT_REQUESTS = 1`),
>   `DOWNLOAD_DELAY = 3` seconds (Scrapy randomizes it to 1.5-4.5 s), up to 4 retries per
>   failed page.
> - Listing fields only: hotel name, URL, score, address, description. No reviews, no guest or
>   reviewer data, no login, no account.
> - Hotel addresses are geocoded through Nominatim with an identifying User-Agent and a
>   1-second delay between requests.
> - Weather: one OpenWeatherMap call per city, 1 second apart.
> - Collected data is not committed to this repository.
>
> `ROBOTSTXT_OBEY` is disabled in this educational setup and the scraper sends a generic browser
> User-Agent; this is not a recommended practice.

![Python](https://img.shields.io/badge/python-3.12-blue)
[![CI](https://github.com/tryph0n/weather-travel-recommender/actions/workflows/ci.yml/badge.svg)](https://github.com/tryph0n/weather-travel-recommender/actions/workflows/ci.yml)

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
| Language | Python 3.12 |
| Package manager | uv |
| Scraping | Scrapy + Playwright (Booking.com) |
| Data processing | pandas, numpy |
| Storage | boto3 (AWS S3), SQLAlchemy + psycopg2 (PostgreSQL / NeonDB) |
| Visualization | Plotly |
| Dashboard | Streamlit |
| Testing and linting | pytest, ruff |
| APIs | OpenWeatherMap, Nominatim (geocoding) |

## Architecture

This project implements Data Lake and Data Warehouse patterns at training-course scale (~35 cities, CSV-based). The patterns are genuine; the scale is intentional. The architecture could evolve to production-grade tooling (Parquet/Delta Lake for the lake, Redshift/BigQuery for the warehouse) without changing the pipeline logic.

**Data Lake pattern (AWS S3)** -- S3 organizes data into 3 zones that enforce separation between raw ingestion, transformation, and consumption-ready outputs:

- `raw/` -- Geocoded city coordinates from Nominatim API (`coordinates.csv`)
- `processed/` -- Scored, cleaned, and filtered data (Gaussian-scored cities, deduplicated hotels)
- `final/` -- Enriched, merged datasets ready for consumption (Top-5 destinations with Top-20 hotels)

Each zone acts as an immutable checkpoint: if a downstream step fails, upstream data is preserved and the step can be re-run independently.

**Data Warehouse pattern (PostgreSQL / NeonDB)** -- NeonDB hosts 2 tables (`destinations`, `hotels`) that serve as the structured, queryable data store for end-user consumption. The relational model fits the one-to-many relationship naturally. This is not a star-schema OLAP warehouse -- it is a PostgreSQL database following the DW pattern of providing clean, structured data optimized for analytical queries via the Streamlit dashboard.

**ETL pipeline** -- The core value of the architecture. Data flows from external APIs and scraping through S3 zones (decoupling producers from consumers), then an ETL step loads the final datasets into PostgreSQL. The dashboard never reads from S3 directly; all user-facing queries go through the database.

**Flow:** Nominatim -> S3 `raw/` (coordinates) ; Weather scoring + Hotel scraping -> S3 `processed/` ; Merge -> S3 `final/` ; ETL -> PostgreSQL -> Dashboard

## Prerequisites

- Python 3.12
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
make scrape-hotels    # Scrape hotels from Top-5 destinations on Booking.com (asks for confirmation)
make merge-data       # Merge weather + hotels data, produce Top-20 recommendations
make etl              # Load final data from S3 into PostgreSQL (NeonDB)
make verify-db        # Verify database integrity after ETL
make visualize        # Generate interactive Plotly HTML maps
make dashboard        # Start Streamlit dashboard at http://localhost:8501
```

`make scrape-hotels` (and `make all`) asks for confirmation before the scraper starts. Set `CONFIRM=yes` to skip the prompt, for example `make all CONFIRM=yes`.

Run `make help` for the full list of available commands.

Reference documentation is in `docs/`: [configuration](docs/CONFIGURATION.md), [database schema](docs/database_schema.md) and [S3 structure](docs/s3_structure.md).

## Data

All pipeline data flows through AWS S3 (raw -> processed -> final), then into PostgreSQL. The maps are written to `outputs/` as HTML files (gitignored). Scraped data is not committed to the repository. `data/sample/` holds a small sample with the same columns as the final dataset. The pipeline is designed for local execution only -- there is no deployment target.

Sources:

- **Cities** -- the 35 French destinations listed in the Jedha training-course brief, which cites One Week In.com as its source (`src/core/constants.py`).
- **Coordinates** -- [Nominatim](https://nominatim.org/) (OpenStreetMap). Licence as each API response states in its `licence` field: data © OpenStreetMap contributors, ODbL 1.0 (https://osm.org/copyright). Use is subject to the [Nominatim Usage Policy](https://operations.osmfoundation.org/policies/nominatim/).
- **Weather** -- [OpenWeatherMap](https://openweathermap.org/) 5-day forecast API, free plan. Licence as OpenWeatherMap states for all self-service plans, the free plan included: ODbL, attribution required (https://openweathermap.org/full-price#licenses).
- **Hotels** -- Booking.com listings, fetched at run time by the scraper. They are not committed to this repository. The Booking.com terms of use apply.
- **Sample** -- `data/sample/travel_recommendations_sample.csv` is invented: fictional hotels, `example.org` URLs, weather values in realistic ranges.

These data are not covered by the code licence.

## Safeguards

Listing fields only; no guest or reviewer data. Rate limiting is enforced on all external sources: 3-second delay on Booking.com, 1-second delay on Nominatim and OpenWeatherMap. Only the Nominatim requests send an identifying User-Agent. `ROBOTSTXT_OBEY` is disabled in this educational setup and the scraper sends a generic browser User-Agent; this is not a recommended practice.

## License

This project was written for a data engineering training course (Bloc 1 -- Data Infrastructure) and is for educational purposes only.

Code released under the [MIT License](LICENSE).
