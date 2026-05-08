"""Merge weather and hotels data to produce final travel recommendations."""

import logging

import pandas as pd

from src.apps.storage import S3Storage
from src.settings import settings

logger = logging.getLogger(__name__)


def merge_weather_hotels() -> pd.DataFrame:
    """Merge weather scores with hotel data to produce final travel recommendations."""
    s3 = S3Storage(
        bucket_name=settings.bucket,
        aws_access_key_id=settings.aws_access_key_id,
        aws_secret_access_key=settings.aws_secret_access_key,
        region=settings.s3_region,
    )

    logger.info("Downloading weather scored data from S3...")
    df_weather = s3.download_dataframe(settings.s3_weather_scored_path)
    logger.info(f"Weather data: {len(df_weather)} cities")

    logger.info("Downloading hotels data from S3...")
    df_hotels = s3.download_dataframe(settings.s3_hotels_path)
    if "score" in df_hotels.columns:
        df_hotels["score"] = pd.to_numeric(df_hotels["score"], errors="coerce")
    logger.info(f"Hotels data: {len(df_hotels)} hotels")

    logger.info("Merging datasets on city_name...")
    df_merged = pd.merge(
        df_hotels, df_weather, on="city_name", how="inner", suffixes=("_hotel", "_city")
    )
    logger.info(f"Merged data: {len(df_merged)} hotels")

    df_merged = df_merged.rename(
        columns={"latitude_city": "latitude", "longitude_city": "longitude"}
    )

    df_top = (
        df_merged.sort_values(["city_name", "score"], ascending=[True, False])
        .groupby("city_name", as_index=False)
        .head(settings.hotels_per_destination)
    )

    df_top = df_top.sort_values("score", ascending=False)

    total_hotels = len(df_top)
    n_destinations = df_top["city_name"].nunique()
    logger.info(
        f"Selected {total_hotels} hotels ({settings.hotels_per_destination} per destination x {n_destinations} destinations)"
    )
    logger.info(
        f"Score range: {df_top['score'].max():.1f} - {df_top['score'].min():.1f}"
    )

    logger.info("Uploading final recommendations to S3...")
    s3.upload_dataframe(df_top, settings.s3_final_recommendations_path)
    logger.info(
        f"Saved to: s3://{settings.bucket}/{settings.s3_final_recommendations_path}"
    )

    logger.info("Top-5 Hotels:")
    for idx, row in enumerate(df_top.head(5).itertuples(), 1):
        logger.info(
            f"  {idx}. {row.hotel_name} ({row.city_name}, score: {row.score:.1f})"
        )

    return df_top


if __name__ == "__main__":
    merge_weather_hotels()
