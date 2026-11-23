#!/usr/bin/env python3
"""
Script to scrape hotels from top N destinations.
Downloads top destinations from S3, scrapes hotels, and uploads results back to S3.

Usage: python -m src.apps.scraping.run_top5
"""

import logging
import os
import tempfile
from pathlib import Path

import pandas as pd
from scrapy.crawler import CrawlerProcess

from src.apps.scraping.booking import BookingPlaywrightSpider
from src.apps.storage.s3 import S3Storage
from src.settings import settings

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def main():
    """Main function to orchestrate hotel scraping for top N destinations."""

    logger.info("Initializing S3 client...")
    s3 = S3Storage(
        bucket_name=settings.bucket,
        aws_access_key_id=settings.aws_access_key_id,
        aws_secret_access_key=settings.aws_secret_access_key,
        region=settings.s3_region,
    )

    logger.info(
        f"Downloading Top-{settings.top_n_destinations} destinations from S3: {settings.s3_top5_destinations_path}"
    )

    if not s3.file_exists(settings.s3_top5_destinations_path):
        logger.error(
            f"Top destinations file not found: {settings.s3_top5_destinations_path}\n"
            "Please run 'make weather' first to generate the file."
        )
        return

    df_top5 = s3.download_dataframe(settings.s3_top5_destinations_path)
    cities_to_scrape = df_top5["city_name"].tolist()

    logger.info(f"Cities to scrape: {', '.join(cities_to_scrape)}")

    with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as tmp_file:
        temp_csv_path = tmp_file.name

    try:
        logger.info("Configuring Scrapy crawler...")
        Path("logs").mkdir(exist_ok=True)
        process = CrawlerProcess(
            {
                "USER_AGENT": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
                "ROBOTSTXT_OBEY": False,
                "FEEDS": {
                    temp_csv_path: {
                        "format": "csv",
                        "encoding": "utf8",
                        "overwrite": True,
                    }
                },
                "LOG_LEVEL": "INFO",
                "LOG_FILE": "logs/scrapy.log",
            }
        )

        BookingPlaywrightSpider.cities = cities_to_scrape
        BookingPlaywrightSpider.max_hotels = settings.hotels_per_destination

        logger.info(f"Starting scraper for {len(cities_to_scrape)} cities...")
        logger.info(f"Max hotels per city: {settings.hotels_per_destination}")
        logger.info(
            f"Expected total: {len(cities_to_scrape) * settings.hotels_per_destination} hotels"
        )

        crawler = process.create_crawler(BookingPlaywrightSpider)
        process.crawl(crawler)
        process.start()

        stats = crawler.stats.get_stats()
        logger.info(
            "scrapy stats: items=%s exceptions=%s",
            stats.get("item_scraped_count", 0),
            stats.get("downloader/exception_count", 0),
        )
        if "playwright/page_method/timeout_count" in stats:
            logger.info(
                "playwright timeouts: %s", stats["playwright/page_method/timeout_count"]
            )

        if not os.path.exists(temp_csv_path) or os.path.getsize(temp_csv_path) == 0:
            raise RuntimeError(
                "scraping produced no items. check logs/scrapy.log for details."
            )

        logger.info(f"Loading scraped data from {temp_csv_path}...")
        df_hotels = pd.read_csv(temp_csv_path)

        logger.info(f"Total hotels scraped: {len(df_hotels)}")

        hotels_per_city = df_hotels.groupby("city_name").size()
        logger.info("Hotels per city:")
        for city, count in hotels_per_city.items():
            logger.info(f"  - {city}: {count} hotels")

        logger.info(f"Uploading results to S3: {settings.s3_hotels_path}")
        s3.upload_dataframe(df_hotels, settings.s3_hotels_path)

        logger.info("OK Hotel scraping completed successfully!")
        logger.info(
            f"Results available at: s3://{settings.bucket}/{settings.s3_hotels_path}"
        )

    except Exception as e:
        logger.error(f"Error during scraping: {str(e)}")
        raise

    finally:
        if os.path.exists(temp_csv_path):
            os.remove(temp_csv_path)
            logger.info(f"Cleaned up temporary file: {temp_csv_path}")


if __name__ == "__main__":
    main()
