"""Weather scoring configuration."""

SEASONS = {
    "winter": {"start": (12, 1), "end": (2, 28), "midpoint": (1, 14)},
    "spring": {"start": (3, 1), "end": (5, 31), "midpoint": (4, 15)},
    "summer": {"start": (6, 1), "end": (8, 31), "midpoint": (7, 16)},
    "autumn": {"start": (9, 1), "end": (11, 30), "midpoint": (10, 16)},
}

# from HCI research
OPTIMAL_TEMPS = {
    "winter": 16.0,
    "spring": 20,
    "summer": 26,
    "autumn": 22,
}

SEASONAL_WEIGHTS = {
    "winter": {"temperature": 50, "rain": 40, "clouds": 10},
    "spring": {"temperature": 40, "rain": 20, "clouds": 40},
    "summer": {"temperature": 60, "rain": 30, "clouds": 10},
    "autumn": {"temperature": 50, "rain": 35, "clouds": 15},
}

for _season, _weights in SEASONAL_WEIGHTS.items():
    assert sum(_weights.values()) == 100, f"{_season} weights must sum to 100"

# gaussian bell width: at ±10°C from optimal, score = 0.5
# sigma = 10 / sqrt(2 * ln(2)) ~ 8.5°C
TEMP_SIGMA = 8.49

# season weight: 1.0 at midpoint, 0.5 at boundaries
# linear transition over TRANSITION_DAYS around each boundary
TRANSITION_DAYS = 30
BOUNDARY_WEIGHT = 0.5
PLATEAU_WEIGHT = 1.0
