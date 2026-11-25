"""Weather data fetching using OpenWeatherMap API.

Note: This module uses the OpenWeatherMap 2.5 One Call API which is
available with free API keys. The 3.0 API requires a paid subscription.
"""

import logging
import math
import time
from datetime import datetime
import requests

from src.settings.weather_scoring import (
    SEASONS,
    OPTIMAL_TEMPS,
    SEASONAL_WEIGHTS,
    TEMP_SIGMA,
    TRANSITION_DAYS,
    BOUNDARY_WEIGHT,
    PLATEAU_WEIGHT,
)


logger = logging.getLogger(__name__)


class WeatherClient:
    """
    Client for OpenWeatherMap 2.5 One Call API (free tier).

    Attributes:
        api_key: OpenWeatherMap API key.
        base_url: Base URL for One Call API 2.5.
    """

    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base_url = "https://api.openweathermap.org/data/2.5/forecast"

    def get_score_for_row(self, row):
        try:
            weather_data = self.get_weather(row["latitude"], row["longitude"])
            return self.compute_weather_score(weather_data)
        except Exception as e:
            logger.warning("Failed to get weather score for row: %s", e, exc_info=True)
            return None

    def get_scores_batch(self, rows, delay: float = 1.0):
        """Get weather scores for multiple rows with rate limiting.

        Args:
            rows: List of rows with 'latitude' and 'longitude' keys.
            delay: Delay between requests in seconds (default: 1.0).

        Returns:
            list: One score dict per row, in the input order (None if it failed).
        """
        results = []

        for i, row in enumerate(rows):
            results.append(self.get_score_for_row(row))

            if i < len(rows) - 1:
                time.sleep(delay)

        return results

    def get_weather(self, latitude: float, longitude: float):
        """
        Fetch weather data for given coordinates.

        Args:
            latitude: GPS latitude.
            longitude: GPS longitude.

        Returns:
            dict: Weather data with daily forecasts.

        Raises:
            requests.RequestException: If API request fails.
        """
        params = {
            "lat": latitude,
            "lon": longitude,
            "appid": self.api_key,
            "units": "metric",
        }

        try:
            response = requests.get(
                self.base_url,
                params=params,
                timeout=10,
            )
            response.raise_for_status()
            return response.json()

        except requests.RequestException as e:
            raise requests.RequestException(
                f"Failed to fetch weather for {latitude}, {longitude}: {str(e)}"
            ) from e

    def _get_season_weight(self, target_date: datetime) -> dict[str, float]:
        """Calculate seasonal weights using plateau system with overlapping transitions.

        Transitions are defined around season END boundaries for simpler logic.
        During the 30-day transition period, both adjacent seasons have non-zero weights
        that sum to 1.0.

        Args:
            target_date: Date to calculate weights for.

        Returns:
            dict: Mapping of season name to weight (0.0-1.0), with most seasons at 0.0
                  and up to 2 seasons with non-zero weights during transitions.

        Example at Aug 31 (summer->autumn): day 229 w={summer:1.0}, day 244 w={0.5,0.5}, day 259 w={autumn:1.0}
        """
        target_ordinal = target_date.toordinal()
        half_transition = TRANSITION_DAYS / 2

        season_order = ["winter", "spring", "summer", "autumn"]
        weights = {"winter": 0.0, "spring": 0.0, "summer": 0.0, "autumn": 0.0}

        for i, season_name in enumerate(season_order):
            config = SEASONS[season_name]
            end_month, end_day = config["end"]

            end_date = datetime(target_date.year, end_month, end_day)

            if season_name == "winter":
                if target_date.month >= 12:
                    # December: winter ends next year
                    end_date = datetime(target_date.year + 1, end_month, end_day)
                elif target_date.month <= 3:
                    # Jan-Mar: winter ends this year (covers Feb 28 end + 15 days transition)
                    end_date = datetime(target_date.year, end_month, end_day)
                elif target_date.month >= 11:
                    # November: check transition to next year's winter end
                    end_date = datetime(target_date.year + 1, end_month, end_day)
                else:
                    # Apr-Oct: far from winter, skip
                    continue

            end_ordinal = end_date.toordinal()

            d = target_ordinal - end_ordinal

            if -half_transition <= d <= half_transition:
                # outgoing season: weight 1.0 at d=-15, 0.5 at d=0, 0.0 at d=+15
                outgoing_weight = BOUNDARY_WEIGHT - (d / TRANSITION_DAYS)
                weights[season_name] = max(0.0, min(1.0, outgoing_weight))

                next_season = season_order[(i + 1) % 4]
                incoming_weight = BOUNDARY_WEIGHT + (d / TRANSITION_DAYS)
                weights[next_season] = max(0.0, min(1.0, incoming_weight))

                return weights

        for season_name in season_order:
            config = SEASONS[season_name]
            start_month, start_day = config["start"]
            end_month, end_day = config["end"]

            start_date = datetime(target_date.year, start_month, start_day)
            end_date = datetime(target_date.year, end_month, end_day)

            # Handle winter year wrap
            if season_name == "winter":
                if target_date.month >= 12:
                    start_date = datetime(target_date.year, start_month, start_day)
                    end_date = datetime(target_date.year + 1, end_month, end_day)
                elif target_date.month <= 2:
                    start_date = datetime(target_date.year - 1, start_month, start_day)
                    end_date = datetime(target_date.year, end_month, end_day)
                elif target_date.month >= 11:
                    start_date = datetime(target_date.year, start_month, start_day)
                    end_date = datetime(target_date.year + 1, end_month, end_day)
                else:
                    continue

            start_ordinal = start_date.toordinal()
            end_ordinal = end_date.toordinal()

            # -1 for inclusive bounds, avoids leap-year off-by-one gap
            if (
                start_ordinal + half_transition - 1
                <= target_ordinal
                <= end_ordinal - half_transition
            ):
                weights[season_name] = PLATEAU_WEIGHT
                return weights

        # shouldn't happen, indicates season config bug
        raise RuntimeError(
            f"No season found for {target_date.strftime('%Y-%m-%d')} "
            f"(ordinal {target_ordinal}). This indicates a bug in season configuration."
        )

    def _compute_temp_score(self, temp: float, optimal_temp: float) -> float:
        """Calculate temperature score using Gaussian distribution.

        Args:
            temp: Actual temperature in °C.
            optimal_temp: Optimal temperature for season in °C.

        Returns:
            float: Score in [0, 1] range.
        """
        return math.exp(-((temp - optimal_temp) ** 2) / (2 * TEMP_SIGMA**2))

    def compute_weather_score(self, weather_data: dict, target_date: datetime = None):
        """Calculate weather score using plateau seasonal weighting.

        Score based on 3 metrics with season-dependent weights:
        - Temperature (Gaussian score centered on optimal for season)
        - Precipitation probability (0-1, inverted)
        - Cloud coverage (0-100%, inverted)

        Args:
            weather_data: Weather API response with forecast list.
            target_date: Date for seasonal weight calculation (default: now).

        Returns:
            dict: Weather metrics and computed score, or None if no data.
        """
        forecast_list = weather_data.get("list", [])

        if not forecast_list:
            return None

        temps = [item["main"]["temp"] for item in forecast_list]
        pop = [item.get("pop", 0) for item in forecast_list]
        clouds = [item["clouds"]["all"] for item in forecast_list]

        avg_temp = sum(temps) / len(temps)
        avg_pop = sum(pop) / len(pop)
        avg_clouds = sum(clouds) / len(clouds)

        if target_date is None:
            target_date = datetime.now()
        season_weights = self._get_season_weight(target_date)

        dominant_season = max(season_weights.items(), key=lambda x: x[1])[0]

        temp_score_total = 0.0
        rain_score = 1 - avg_pop
        cloud_score = 1 - (avg_clouds / 100)

        for season, season_weight in season_weights.items():
            if season_weight > 0:
                optimal_temp = OPTIMAL_TEMPS[season]
                temp_score = self._compute_temp_score(avg_temp, optimal_temp)
                temp_score_total += temp_score * season_weight

        weights = SEASONAL_WEIGHTS[dominant_season]

        final_score = (
            temp_score_total * weights["temperature"]
            + rain_score * weights["rain"]
            + cloud_score * weights["clouds"]
        )

        active_seasons = {s: w for s, w in season_weights.items() if w > 0}

        return {
            "avg_temperature": round(avg_temp, 1),
            "avg_rain_probability": round(avg_pop * 100, 1),  # in %
            "avg_cloud_coverage": round(avg_clouds, 1),  # in %
            "weather_score": round(final_score, 1),
            "forecast_count": len(forecast_list),
            "season": dominant_season,
            "season_weights": {s: round(w, 2) for s, w in active_seasons.items()},
        }
