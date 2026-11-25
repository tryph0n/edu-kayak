"""Streamlit dashboard for Weather Travel Recommender.

This dashboard provides an interactive read-only interface to visualize
travel recommendations from PostgreSQL database.
"""

import streamlit as st
import pandas as pd
from sqlalchemy.orm import joinedload
from sqlalchemy.sql import func

from src.apps.database.client import DatabaseClient
from src.apps.database.models import Destination, Hotel
from src.apps.visualization.maps import create_top5_map, create_hotels_map
from src.settings import settings


st.set_page_config(
    page_title="Weather Travel Recommender",
    layout="wide",
)

st.title("Weather Travel Recommender Dashboard")
st.markdown("Discover the best destinations and hotels in France based on weather data")


@st.cache_data(ttl=3600)
def load_data():
    """Load data from PostgreSQL database.

    Returns:
        tuple: (df_destinations, df_hotels, collected_at) DataFrames and collection timestamp

    Raises:
        Exception: If database query fails
    """
    db = DatabaseClient()
    session = db.get_session()

    try:
        collected_at = session.query(func.max(Destination.created_at)).scalar()
        destinations = session.query(Destination).all()
        df_destinations = pd.DataFrame(
            [
                {
                    "city_name": d.city_name,
                    "weather_score": d.weather_score,
                    "temperature": d.avg_temperature_7d,
                    "rain_prob": d.avg_rain_probability,
                    "cloud_coverage": d.avg_cloud_coverage,
                    "latitude": d.latitude,
                    "longitude": d.longitude,
                }
                for d in destinations
            ]
        )

        hotels = session.query(Hotel).options(joinedload(Hotel.destination)).all()
        df_hotels = pd.DataFrame(
            [
                {
                    "hotel_name": h.hotel_name,
                    "city_name": h.destination.city_name
                    if h.destination
                    else "Unknown",
                    "score": h.score,
                    "address": h.address,
                    "description": h.description,
                    "url": h.url,
                    "weather_score": h.destination.weather_score
                    if h.destination
                    else None,
                }
                for h in hotels
            ]
        )

        return df_destinations, df_hotels, collected_at

    finally:
        session.close()
        db.close()


try:
    df_destinations, df_hotels, collected_at = load_data()
except Exception as e:
    st.error(f"Error loading data from database: {e}")
    st.stop()

if collected_at:
    tz_label = collected_at.strftime("%Z") or collected_at.strftime("%z")
    st.caption(
        f"Recommendations last updated on {collected_at.strftime('%d/%m/%Y at %H:%M')} {tz_label}"
    )

col1, col2, col3, col4 = st.columns(4)

with col1:
    st.metric("Total Destinations", len(df_destinations))

with col2:
    st.metric("Total Hotels", len(df_hotels))

with col3:
    best_weather = (
        f"{df_destinations['weather_score'].max():.1f}"
        if not df_destinations.empty
        else "N/A"
    )
    st.metric("Best Weather Score", best_weather)

with col4:
    best_hotel = f"{df_hotels['score'].max():.1f}/10" if not df_hotels.empty else "N/A"
    st.metric("Best Hotel Score", best_hotel)

st.header("Top Destinations")

if not df_destinations.empty:
    display_df_destinations = (
        df_destinations[
            ["city_name", "weather_score", "temperature", "rain_prob", "cloud_coverage"]
        ]
        .sort_values("weather_score", ascending=False)
        .head(settings.top_n_destinations)
        .rename(
            columns={
                "city_name": "City",
                "weather_score": "Weather Score",
                "temperature": "Temperature (C)",
                "rain_prob": "Rain Probability (%)",
                "cloud_coverage": "Cloud Coverage (%)",
            }
        )
    )
    st.dataframe(display_df_destinations, hide_index=True)
else:
    st.info("No destinations data available")

try:
    fig_destinations = create_top5_map()
    st.plotly_chart(fig_destinations, width="stretch")
except Exception as e:
    st.error(f"Error generating destinations map: {e}")

st.header("Top Hotels")

try:
    fig_hotels_map = create_hotels_map()
    st.plotly_chart(fig_hotels_map, width="stretch")
except Exception as e:
    st.error(f"Error generating hotels map: {e}")

if not df_hotels.empty:
    expected_hotels = settings.top_n_destinations * settings.hotels_per_destination

    # Build column list: include description only if it exists and has non-null values
    base_cols = ["hotel_name", "city_name", "score", "weather_score", "address"]
    if "description" in df_hotels.columns and df_hotels["description"].notna().any():
        base_cols.append("description")

    rename_map = {
        "hotel_name": "Hotel",
        "city_name": "City",
        "score": "Hotel Score",
        "weather_score": "Weather Score",
        "address": "Address",
        "description": "Description",
    }

    display_df_hotels = (
        df_hotels[base_cols]
        .sort_values("score", ascending=False)
        .head(expected_hotels)
        .rename(columns=rename_map)
    )
    st.dataframe(display_df_hotels, hide_index=True)
else:
    st.info("No hotels data available")

st.markdown("---")
st.markdown(
    "Data sources: Nominatim (geocoding) + OpenWeatherMap (forecasts) + Booking.com via Scrapy/Playwright (hotels) | Pipeline: Data Lake (S3) -> Data Warehouse (PostgreSQL) | Built with Streamlit"
)
