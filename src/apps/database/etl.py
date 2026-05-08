"""ETL pipeline for loading travel recommendations from S3 to PostgreSQL.

This module implements the Extract-Transform-Load pipeline:
- Extract: Download travel_recommendations.csv from S3
- Transform: Clean data, validate types, handle nulls
- Load: Insert destinations and hotels into PostgreSQL NeonDB
"""

import logging
import sys
from io import StringIO

import boto3
import pandas as pd
from sqlalchemy.exc import SQLAlchemyError

from src.apps.database.client import DatabaseClient
from src.apps.database.models import Destination, Hotel
from src.apps.geocoding.client import GeocodingClient
from src.settings import settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)


class ETLPipeline:
    """ETL pipeline for S3 to PostgreSQL data loading.

    Attributes:
        db_client: Database client for PostgreSQL operations
        s3_client: Boto3 S3 client for data extraction
    """

    def __init__(self):
        """Initialize ETL pipeline with database and S3 clients."""
        self.db_client = DatabaseClient()
        self.s3_client = boto3.client(
            "s3",
            aws_access_key_id=settings.aws_access_key_id,
            aws_secret_access_key=settings.aws_secret_access_key,
            region_name=settings.s3_region,
        )
        self.geocoder = GeocodingClient()

    def extract(self) -> pd.DataFrame:
        """Extract travel recommendations CSV from S3.

        Returns:
            DataFrame with raw data from S3.

        Raises:
            Exception: If S3 download fails.
        """
        logger.info("Extracting data from S3...")
        logger.info(f"Bucket: {settings.bucket}")
        logger.info(f"Path: {settings.s3_final_recommendations_path}")

        try:
            response = self.s3_client.get_object(
                Bucket=settings.bucket, Key=settings.s3_final_recommendations_path
            )
            csv_content = response["Body"].read().decode("utf-8")
            df = pd.read_csv(StringIO(csv_content))
            logger.info(f"Extracted {len(df)} rows from S3")
            logger.info(f"Columns: {list(df.columns)}")
            return df

        except Exception as e:
            logger.error(f"Failed to extract data from S3: {e}")
            raise

    def geocode_hotels(self, df: pd.DataFrame) -> pd.DataFrame:
        """Geocode hotel addresses to get GPS coordinates.

        Args:
            df: DataFrame with hotel addresses.

        Returns:
            DataFrame with added latitude and longitude columns for hotels.
        """
        logger.info("Geocoding hotel addresses...")

        if "address" not in df.columns:
            logger.warning("No 'address' column found, skipping hotel geocoding")
            df["hotel_latitude"] = None
            df["hotel_longitude"] = None
            return df

        hotels_data = df[["address", "city_name", "hotel_name"]].to_dict("records")

        logger.info(f"Geocoding {len(hotels_data)} hotels...")
        geocoded = self.geocoder.geocode_hotels_batch(hotels_data, delay=1.0)

        df["hotel_latitude"] = [h.get("latitude") for h in geocoded]
        df["hotel_longitude"] = [h.get("longitude") for h in geocoded]

        success_count = sum(
            1
            for lat, lon in zip(df["hotel_latitude"], df["hotel_longitude"])
            if lat is not None and lon is not None
        )
        logger.info(
            f"Successfully geocoded {success_count}/{len(df)} hotels "
            f"({success_count / len(df) * 100:.1f}%)"
        )

        return df

    def transform(self, df: pd.DataFrame) -> pd.DataFrame:
        """Transform and clean data.

        Args:
            df: Raw dataframe from S3.

        Returns:
            Cleaned dataframe ready for loading.
        """
        logger.info("Transforming data...")

        initial_count = len(df)
        df = df.drop_duplicates()
        if len(df) < initial_count:
            logger.info(f"Removed {initial_count - len(df)} duplicate rows")

        df = self.geocode_hotels(df)

        required_destination_cols = [
            "city_name",
            "latitude",
            "longitude",
            "weather_score",
        ]
        required_hotel_cols = ["hotel_name", "url"]

        all_required_cols = required_destination_cols + required_hotel_cols
        missing_cols = [col for col in all_required_cols if col not in df.columns]
        if missing_cols:
            raise ValueError(f"Missing required columns: {missing_cols}")

        df = df.dropna(subset=required_destination_cols)
        logger.info(f"After dropping nulls in destination columns: {len(df)} rows")

        df = df.dropna(subset=required_hotel_cols)
        logger.info(f"After dropping nulls in hotel columns: {len(df)} rows")

        df["latitude"] = pd.to_numeric(df["latitude"], errors="coerce")
        df["longitude"] = pd.to_numeric(df["longitude"], errors="coerce")
        df["weather_score"] = pd.to_numeric(df["weather_score"], errors="coerce")

        if "avg_temperature_7d" in df.columns:
            df["avg_temperature_7d"] = pd.to_numeric(
                df["avg_temperature_7d"], errors="coerce"
            )
        if "avg_rain_probability" in df.columns:
            df["avg_rain_probability"] = pd.to_numeric(
                df["avg_rain_probability"], errors="coerce"
            )
        if "avg_cloud_coverage" in df.columns:
            df["avg_cloud_coverage"] = pd.to_numeric(
                df["avg_cloud_coverage"], errors="coerce"
            )
        if "forecast_count" in df.columns:
            df["forecast_count"] = pd.to_numeric(
                df["forecast_count"], errors="coerce"
            ).astype("Int64")
        if "score" in df.columns:
            df["score"] = pd.to_numeric(df["score"], errors="coerce")

        df = df.dropna(subset=["latitude", "longitude", "weather_score"])
        logger.info(f"After type validation: {len(df)} rows")

        logger.info("Data transformation complete")
        return df

    def load(self, df: pd.DataFrame) -> dict:
        """Load data into PostgreSQL database.

        Strategy:
        1. Truncate hotels and destinations tables (idempotency)
        2. Insert unique destinations first
        3. Flush to get city_ids
        4. Map city_name to city_id
        5. Insert hotels with city_id foreign key

        Args:
            df: Transformed dataframe.

        Returns:
            Dictionary with load statistics.

        Raises:
            SQLAlchemyError: If database operations fail.
        """
        logger.info("Loading data into PostgreSQL...")

        session = self.db_client.get_session()
        stats = {
            "destinations_inserted": 0,
            "hotels_inserted": 0,
        }

        try:
            destination_cols = [
                "city_name",
                "latitude",
                "longitude",
                "weather_score",
                "avg_temperature_7d",
                "avg_rain_probability",
                "avg_cloud_coverage",
                "forecast_count",
            ]
            existing_cols = [col for col in destination_cols if col in df.columns]
            destinations_df = df[existing_cols].drop_duplicates(subset=["city_name"])

            logger.info(f"Inserting {len(destinations_df)} unique destinations...")

            for _, row in destinations_df.iterrows():
                forecast_val = row.get("forecast_count")
                dest = Destination(
                    city_name=row["city_name"],
                    latitude=row["latitude"],
                    longitude=row["longitude"],
                    weather_score=row["weather_score"],
                    avg_temperature_7d=row.get("avg_temperature_7d"),
                    avg_rain_probability=row.get("avg_rain_probability"),
                    avg_cloud_coverage=row.get("avg_cloud_coverage"),
                    forecast_count=(
                        int(forecast_val) if pd.notna(forecast_val) else None
                    ),
                )
                session.add(dest)
                stats["destinations_inserted"] += 1

            session.flush()
            logger.info("Destinations flushed, retrieving city_ids...")

            city_id_map = {}
            for dest in session.query(Destination).all():
                city_id_map[dest.city_name] = dest.city_id

            logger.info(f"Mapped {len(city_id_map)} city names to city_ids")

            logger.info(f"Inserting {len(df)} hotels...")

            for _, row in df.iterrows():
                city_id = city_id_map.get(row["city_name"])
                if not city_id:
                    logger.warning(
                        f"City {row['city_name']} not found in mapping, skipping hotel"
                    )
                    continue

                score_val = row.get("score")
                addr_val = row.get("address")
                desc_val = row.get("description")
                lat_val = row.get("hotel_latitude")
                lon_val = row.get("hotel_longitude")
                hotel = Hotel(
                    city_id=city_id,
                    hotel_name=row["hotel_name"],
                    url=row["url"],
                    score=score_val if pd.notna(score_val) else None,
                    address=addr_val if pd.notna(addr_val) else None,
                    description=desc_val if pd.notna(desc_val) else None,
                    latitude=lat_val if pd.notna(lat_val) else None,
                    longitude=lon_val if pd.notna(lon_val) else None,
                )
                session.add(hotel)
                stats["hotels_inserted"] += 1

            session.commit()
            logger.info("Transaction committed successfully")

            return stats

        except SQLAlchemyError as e:
            logger.error(f"Database error during load: {e}")
            session.rollback()
            logger.info("Transaction rolled back")
            raise

        finally:
            session.close()

    def run(self):
        """Execute complete ETL pipeline.

        Returns:
            Dictionary with execution statistics.
        """
        logger.info("Starting ETL Pipeline: S3 -> PostgreSQL NeonDB")

        try:
            self.db_client.recreate_tables()
            logger.info("Database tables ready")

            df = self.extract()
            df = self.transform(df)
            stats = self.load(df)

            logger.info("ETL Pipeline Completed Successfully")
            logger.info(f"OK Destinations: {stats['destinations_inserted']} inserted")
            logger.info(f"OK Hotels: {stats['hotels_inserted']} inserted")

            return stats

        except Exception as e:
            logger.error("ETL Pipeline Failed")
            logger.error(f"Error: {e}")
            raise


if __name__ == "__main__":
    pipeline = ETLPipeline()
    try:
        pipeline.run()
        sys.exit(0)
    except Exception:
        sys.exit(1)
