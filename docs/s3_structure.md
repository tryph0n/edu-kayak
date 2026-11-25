# S3 Storage Structure

## Overview
This document describes the unified S3 storage structure for the Weather Travel Recommender project.

## Directory Structure

```
kayak/
├── raw/              # Raw unprocessed data from external APIs
├── processed/        # Calculated and cleaned data with scores
└── final/            # Enriched data ready for visualization
```

## File Paths and Purpose

### Raw Data (`kayak/raw/`)
Unprocessed data directly from external APIs.

| File | Path | Content | Source | Updated By |
|------|------|---------|--------|------------|
| Coordinates | `kayak/raw/coordinates.csv` | City coordinates (lat, lon) for 35 French cities | Nominatim API | `orchestration.py` |

Raw weather responses are not stored: the weather scoring step reads the API and writes the scores
directly to `kayak/processed/weather_scored.csv`.

---

### Processed Data (`kayak/processed/`)
Calculated and cleaned data with business logic applied.

| File | Path | Content | Input | Updated By |
|------|------|---------|-------|------------|
| Weather Scored | `kayak/processed/weather_scored.csv` | Cities with weather scores | Raw coordinates + weather API | `orchestration.py` |
| Top 5 Destinations | `kayak/processed/top5_destinations.csv` | Best 5 destinations by weather score | Weather scored data | `orchestration.py` |
| Hotels | `kayak/processed/hotels_top5.csv` | Hotel data for top 5 destinations | Booking.com scraping | `run_top5.py` |

**Format**: CSV with standardized columns and calculated fields.

**Key Columns in `weather_scored.csv`**:
- `city_name`: City name
- `latitude`, `longitude`: Coordinates
- `weather_score`: Calculated score (0-100)
- `avg_temperature_7d`: 7-day average temperature
- `avg_rain_probability`, `avg_cloud_coverage`, `forecast_count`, `season`, `season_weights`

**Columns in `hotels_top5.csv`**: `city_name`, `hotel_name`, `url`, `score`, `address`,
`description`.

---

### Final Data (`kayak/final/`)
Enriched data combining weather and hotel information, ready for visualization.

| File | Path | Content | Input | Updated By |
|------|------|---------|-------|------------|
| Travel Recommendations | `kayak/final/travel_recommendations.csv` | Complete travel recommendations with weather + hotels | Weather scored + hotels | `merger.py` |

**Format**: CSV, one row per hotel. The ETL loads it into PostgreSQL.

**Expected Columns**:
- Hotel fields: `hotel_name`, `url`, `score`, `address`, `description`
- City and weather fields: `city_name`, `latitude`, `longitude`, `avg_temperature_7d`,
  `avg_rain_probability`, `avg_cloud_coverage`, `weather_score`, `forecast_count`, `season`,
  `season_weights`

`latitude` and `longitude` are the city coordinates. The ETL geocodes each hotel address and
stores the hotel coordinates in PostgreSQL only.

---

## Configuration

All S3 paths are centralized in `src/settings/base.py`:

```python
class Settings(BaseSettings):
    s3_coordinates_path: str = "kayak/raw/coordinates.csv"
    s3_weather_scored_path: str = "kayak/processed/weather_scored.csv"
    s3_top5_destinations_path: str = "kayak/processed/top5_destinations.csv"
    s3_hotels_path: str = "kayak/processed/hotels_top5.csv"
    s3_final_recommendations_path: str = "kayak/final/travel_recommendations.csv"
```

Each path can be changed through an environment variable of the same name in upper case
(for example `S3_HOTELS_PATH`), as for every pydantic-settings field.

## Usage Example

```python
from src.settings import settings
from src.apps.storage import S3Storage

# Initialize S3 client
s3 = S3Storage(
    bucket_name=settings.bucket,
    aws_access_key_id=settings.aws_access_key_id,
    aws_secret_access_key=settings.aws_secret_access_key,
    region=settings.s3_region,
)

# Upload data using centralized paths
s3.upload_dataframe(df, settings.s3_weather_scored_path)

# Download data using centralized paths
df = s3.download_dataframe(settings.s3_top5_destinations_path)
```

## Data Flow

```
1. GEOCODING
   Nominatim API → coordinates.csv (raw)

2. WEATHER SCORING
   coordinates.csv + OpenWeatherMap API → weather_scored.csv (processed)
   weather_scored.csv → top5_destinations.csv (processed)

3. HOTEL SCRAPING
   top5_destinations.csv + Booking.com → hotels_top5.csv (processed)

4. FINAL ENRICHMENT
   weather_scored.csv + hotels_top5.csv → travel_recommendations.csv (final)

5. ETL
   travel_recommendations.csv + hotel geocoding (Nominatim) → PostgreSQL (destinations, hotels)

6. VISUALIZATION AND DASHBOARD
   PostgreSQL → Plotly maps in outputs/ (HTML files) and the Streamlit dashboard
```

## Benefits
- Single source of truth for all S3 paths
- Clear separation between raw, processed, and final data
- Easy to modify paths via Settings
- Consistent naming convention across the project
