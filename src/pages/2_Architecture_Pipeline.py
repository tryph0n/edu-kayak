"""Streamlit page presenting the project architecture and pipeline.

This page consolidates the three architecture diagrams (sources, architecture,
ETL flow) with the textual context mirrored from the README, intended for the
certification jury.
"""

from pathlib import Path

import streamlit as st

DIAGRAMS_DIR = Path(__file__).parent.parent / "assets" / "diagrams"


def load_dot(filename: str) -> str:
    path = DIAGRAMS_DIR / filename
    return path.read_text(encoding="utf-8")


st.set_page_config(
    page_title="Architecture & Pipeline",
    page_icon=None,
    layout="wide",
)

st.title("Architecture & Pipeline")
st.markdown(
    "Overview of the data sources, the Data Lake / Data Warehouse pattern, "
    "and the ETL pipeline flow."
)


st.header("1. Sources & Data Privacy")

st.markdown("Three external data sources feed the pipeline.")

st.graphviz_chart(load_dot("sources.dot"))

st.markdown("""
**RGPD / Privacy safeguards applied to the pipeline sources:**

| Safeguard | Applies to | Detail |
|---|---|---|
| Public data only | All sources | No personal data collected or stored |
| Rate limiting | GeocodingClient, WeatherClient, BookingSpider | Respectful API/site usage with enforced delays |
| Custom User-Agent | GeocodingClient, BookingSpider | Requests identify the application |
| robots.txt compliance | BookingSpider | Web scraping follows site directives |
""")

st.subheader("Sources")
st.markdown("""
- **Nominatim (OpenStreetMap)** -- Geocoding service used to resolve the 35 French
  city names into latitude/longitude coordinates.
- **OpenWeatherMap** -- 5-day weather forecasts (temperature, rain probability,
  cloud coverage) for each geocoded city, consumed via API key.
- **Booking.com** -- Hotel listings (name, address, score, description, URL)
  scraped from the Top-5 destinations using Scrapy + Playwright.
""")

st.subheader("Data Privacy")
st.markdown(
    "Only publicly available data is collected -- no personal data, no user "
    "tracking, no cookies. Rate limiting is enforced on all external sources: "
    "3-second delay on Booking.com, 1-second delay on Nominatim. "
    "`ROBOTSTXT_OBEY = False` is set for Booking.com; this is justified by the "
    "academic context (certification project, no redistribution or commercial "
    "use) and compensated by strict rate limiting."
)


st.header("2. Architecture (Data Lake + Data Warehouse)")

st.markdown("Pattern Data Lake (S3) + pattern Data Warehouse (PostgreSQL).")

st.graphviz_chart(load_dot("architecture.dot"))

st.markdown(
    "This project implements Data Lake and Data Warehouse patterns at "
    "certification scale (~35 cities, CSV-based). The patterns are genuine; "
    "the scale is intentional. The architecture could evolve to "
    "production-grade tooling (Parquet/Delta Lake for the lake, "
    "Redshift/BigQuery for the warehouse) without changing the pipeline logic."
)

st.subheader("Pattern Data Lake (AWS S3)")
st.markdown("""
S3 organizes data into 3 zones that enforce separation between raw ingestion,
transformation, and consumption-ready outputs:

- `raw/` -- Geocoded city coordinates from Nominatim API (`coordinates.csv`)
- `processed/` -- Scored, cleaned, and filtered data (Gaussian-scored cities,
  deduplicated hotels)
- `final/` -- Enriched, merged datasets ready for consumption (Top-5
  destinations with Top-20 hotels)

Each zone acts as an immutable checkpoint: if a downstream step fails, upstream
data is preserved and the step can be re-run independently.
""")

st.subheader("Pattern Data Warehouse (PostgreSQL / NeonDB)")
st.markdown(
    "NeonDB hosts 2 tables (`destinations`, `hotels`) that serve as the "
    "structured, queryable data store for end-user consumption. The relational "
    "model fits the one-to-many relationship naturally. This is not a "
    "star-schema OLAP warehouse -- it is a PostgreSQL database following the "
    "DW pattern of providing clean, structured data optimized for analytical "
    "queries via the Streamlit dashboard."
)

st.subheader("ETL pipeline")
st.markdown(
    "The core value of the architecture. Data flows from external APIs and "
    "scraping through S3 zones (decoupling producers from consumers), then an "
    "ETL step loads the final datasets into PostgreSQL. The dashboard never "
    "reads from S3 directly; all user-facing queries go through the database."
)

st.markdown(
    "**Flow:** APIs/Scraping -> S3 `raw/` -> Processing -> S3 `processed/` -> "
    "Merging -> S3 `final/` -> ETL -> PostgreSQL -> Dashboard"
)


st.header("3. ETL Pipeline Flow")

st.markdown("Orchestrated via Makefile targets.")

st.graphviz_chart(load_dot("etl_flow.dot"))

st.subheader("Makefile targets (execution order)")
st.markdown("""
- `make weather` -- Geocode cities, fetch forecasts, compute scores, generate Top-5
- `make scrape-hotels` -- Scrape hotels from Top-5 destinations on Booking.com
- `make merge-data` -- Merge weather + hotels data, produce Top-20 recommendations
- `make etl` -- Load final data from S3 into PostgreSQL (NeonDB)
- `make verify-db` -- Verify database integrity after ETL
- `make visualize` -- Generate interactive Plotly HTML maps
- `make dashboard` -- Start Streamlit dashboard at http://localhost:8501

The `make all` target runs the full pipeline (weather -> scrape -> merge -> etl
-> verify-db -> visualize) in sequence.
""")

st.markdown("---")
st.markdown("Architecture overview | Kayak Travel Recommender | Certification Bloc 1")
