"""Generate all Plotly visualizations.

This script generates both interactive maps:
- Top N destinations by weather score (configurable)
- Top hotels by score (configurable)

Usage:
    python -m src.apps.visualization.generate
    make visualize
"""

import logging
import os
import sys

from src.apps.visualization.maps import create_top5_map, create_top20_hotels_map
from src.settings import settings

logger = logging.getLogger(__name__)


def generate_all_maps():
    """Generate all visualization maps.

    Creates the outputs/ directory if it doesn't exist, then generates
    both the top destinations and top hotels maps.

    Returns:
        bool: True if all maps generated successfully, False otherwise
    """
    try:
        os.makedirs("outputs", exist_ok=True)
        logger.info("Generating visualizations...")

        logger.info(f"[1/2] Generating Top-{settings.top_n_destinations} Destinations map...")
        fig_dest = create_top5_map()
        fig_dest.write_html("outputs/top5_destinations.html")
        logger.info("Saved: outputs/top5_destinations.html")

        expected_hotels = settings.top_n_destinations * settings.hotels_per_destination
        logger.info(f"[2/2] Generating Top-{expected_hotels} Hotels map...")
        fig_hotels = create_top20_hotels_map()
        fig_hotels.write_html("outputs/top20_hotels.html")
        logger.info("Saved: outputs/top20_hotels.html")

        logger.info("All visualizations generated successfully. Files saved in: outputs/")

        return True

    except Exception as e:
        logger.error(f"Error generating visualizations: {e}")
        return False


if __name__ == "__main__":
    success = generate_all_maps()
    sys.exit(0 if success else 1)
