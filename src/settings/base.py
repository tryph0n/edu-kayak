"""Application settings and configuration."""

from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import URL


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    openweather_api_key: str

    aws_access_key_id: str
    aws_secret_access_key: str
    bucket: str
    s3_region: str = "eu-west-3"

    top_n_destinations: int = 5
    hotels_per_destination: int = 4

    s3_coordinates_path: str = "kayak/raw/coordinates.csv"
    s3_weather_scored_path: str = "kayak/processed/weather_scored.csv"
    s3_top5_destinations_path: str = "kayak/processed/top5_destinations.csv"
    s3_hotels_path: str = "kayak/processed/hotels_top5.csv"
    s3_final_recommendations_path: str = "kayak/final/travel_recommendations.csv"

    postgres_host: str
    postgres_port: str = "5432"
    postgres_database: str
    postgres_user: str
    postgres_password: str
    postgres_ssl_mode: str = "require"

    @property
    def postgres_url(self) -> URL:
        return URL.create(
            drivername="postgresql",
            username=self.postgres_user,
            password=self.postgres_password,
            host=self.postgres_host,
            port=int(self.postgres_port),
            database=self.postgres_database,
            query={"sslmode": self.postgres_ssl_mode} if self.postgres_ssl_mode else {},
        )


settings = Settings()
