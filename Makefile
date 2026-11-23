.PHONY: help setup check-settings test test-integration lint run weather scrape-hotels setup-scraping merge-data etl verify-db visualize dashboard clean all teardown

UV := uv

help:
	@echo "Kayak Travel Recommender - Available commands:"
	@echo ""
	@echo "  make all              Run complete pipeline: check-settings → weather → scrape → merge → etl → verify-db → visualize"
	@echo "  make setup            Setup project (installs all dependencies)"
	@echo "  make setup-scraping   Install Playwright browsers (required once before scraping)"
	@echo "  make test             Run unit tests"
	@echo "  make test-integration Run integration tests (real API calls)"
	@echo "  make lint             Run ruff lint and format checks"
	@echo "  make weather          Run weather pipeline and generate Top-5 destinations"
	@echo "  make scrape-hotels    Scrape hotels from Top-5 destinations (requires 'make weather' first; asks for confirmation, CONFIRM=yes skips it)"
	@echo "  make merge-data       Merge weather + hotels data and generate Top-20 final recommendations"
	@echo "  make etl              Run ETL pipeline: S3 → PostgreSQL NeonDB (requires 'make merge-data' first)"
	@echo "  make verify-db        Verify database integrity after ETL (requires 'make etl' first)"
	@echo "  make visualize        Generate Plotly visualizations (requires 'make etl' first)"
	@echo "  make dashboard        Start Streamlit dashboard (requires 'make etl' first)"
	@echo "  make check-settings   Validate pydantic-settings configuration"
	@echo "  make clean            Clean temporary files"
	@echo "  make teardown         Drop DB tables and delete S3 data (DESTRUCTIVE)"
	@echo ""
	@echo "For direct uv usage, see README.md"

setup:
	@echo "Syncing dependencies with uv..."
	$(UV) sync --extra scraping
	@if [ ! -f .env ]; then \
		echo "Creating .env from template..."; \
		cp .env.template .env; \
		echo "Please edit .env with your API keys"; \
	fi
	@mkdir -p data/output
	@echo "Setup complete! See README.md for uv usage."

setup-scraping:
	@echo "Installing playwright browsers..."
	$(UV) run playwright install chromium
	@echo "[OK] Scraping environment ready"

check-settings:
	@if [ ! -f .env ]; then \
		echo "Error: .env file not found"; \
		echo "Run 'make setup' first and configure your .env"; \
		exit 1; \
	fi
	@set -a && . ./.env && set +a && \
	PYTHONPATH=. \
	$(UV) run python -c "from src.settings import settings"

test:
	@echo "Running unit tests..."
	$(UV) run pytest tests/ -v --tb=short -m "not integration"

test-integration:
	@if [ ! -f .env ]; then \
		echo "Error: .env file not found"; \
		exit 1; \
	fi
	@echo "Running integration tests (real API calls)..."
	@set -a && . ./.env && set +a && \
	RUN_INTEGRATION_TESTS=1 \
	$(UV) run pytest tests/ -v -s -m "integration"

lint:
	@echo "Running ruff..."
	$(UV) run ruff check .
	$(UV) run ruff format --check .

weather:
	@if [ ! -f .env ]; then \
		echo "Error: .env file not found"; \
		echo "Run 'make setup' first and configure your .env"; \
		exit 1; \
	fi
	@echo "Running weather pipeline..."
	@set -a && . ./.env && set +a && \
	PYTHONPATH=. \
	$(UV) run python src/api/orchestration.py

scrape-hotels:
	@if [ ! -f .env ]; then \
		echo "Error: .env file not found"; \
		echo "Run 'make setup' first and configure your .env"; \
		exit 1; \
	fi
	@if [ "$(CONFIRM)" != "yes" ]; then \
		echo "This runs the Booking.com scraper (educational use only, see README.md)."; \
		read -p "Are you sure? Type 'yes' to confirm: " confirm && [ "$$confirm" = "yes" ] || (echo "Aborted."; exit 1); \
	fi
	@echo "Scraping hotels from Top-5 destinations..."
	@echo "Note: This requires 'make weather' to have been run first."
	@set -a && . ./.env && set +a && \
	PYTHONPATH=. \
	$(UV) run --extra scraping python -m src.apps.scraping.run_top5

merge-data:
	@if [ ! -f .env ]; then \
		echo "Error: .env file not found"; \
		echo "Run 'make setup' first and configure your .env"; \
		exit 1; \
	fi
	@echo "Merging weather and hotels data..."
	@echo "Note: This requires 'make weather' and 'make scrape-hotels' to have been run first."
	@set -a && . ./.env && set +a && \
	PYTHONPATH=. \
	$(UV) run python -m src.apps.data.merger

etl:
	@if [ ! -f .env ]; then \
		echo "Error: .env file not found"; \
		echo "Run 'make setup' first and configure your .env"; \
		exit 1; \
	fi
	@echo "Running ETL pipeline: S3 → PostgreSQL NeonDB..."
	@echo "Note: This requires 'make merge-data' to have been run first."
	@set -a && . ./.env && set +a && \
	PYTHONPATH=. \
	$(UV) run python -m src.apps.database.etl

verify-db:
	@if [ ! -f .env ]; then \
		echo "Error: .env file not found"; \
		echo "Run 'make setup' first and configure your .env"; \
		exit 1; \
	fi
	@echo "Verifying database integrity..."
	@echo "Note: This requires 'make etl' to have been run first."
	@set -a && . ./.env && set +a && \
	PYTHONPATH=. \
	$(UV) run python -m src.apps.database.verify

visualize:
	@if [ ! -f .env ]; then \
		echo "Error: .env file not found"; \
		echo "Run 'make setup' first and configure your .env"; \
		exit 1; \
	fi
	@echo "Generating Plotly visualizations..."
	@echo "Note: This requires 'make etl' to have been run first."
	@set -a && . ./.env && set +a && \
	PYTHONPATH=. \
	$(UV) run python -m src.apps.visualization.generate

dashboard:
	@if [ ! -f .env ]; then \
		echo "Error: .env file not found"; \
		echo "Run 'make setup' first and configure your .env"; \
		exit 1; \
	fi
	@echo "Starting Streamlit dashboard..."
	@echo "Note: This requires 'make etl' to have been run first."
	@set -a && . ./.env && set +a && \
	PYTHONPATH=. \
	$(UV) run streamlit run src/dashboard.py

all:
	@echo "Running complete pipeline..."
	@echo ""
	@$(MAKE) check-settings
	@echo ""
	@$(MAKE) weather
	@echo ""
	@$(MAKE) scrape-hotels
	@echo ""
	@$(MAKE) merge-data
	@echo ""
	@$(MAKE) etl
	@echo ""
	@$(MAKE) verify-db
	@echo ""
	@$(MAKE) visualize
	@echo ""
	@echo "Pipeline complete. Run 'make dashboard' to start the dashboard."

teardown:
	@if [ ! -f .env ]; then \
		echo "Error: .env file not found"; \
		echo "Run 'make setup' first and configure your .env"; \
		exit 1; \
	fi
	@echo "WARNING: This will drop all database tables and delete all S3 data under kayak/."
	@read -p "Are you sure? Type 'yes' to confirm: " confirm && [ "$$confirm" = "yes" ] || (echo "Aborted."; exit 1)
	@echo "Running teardown..."
	@set -a && . ./.env && set +a && \
	PYTHONPATH=. \
	$(UV) run python -c " \
import sys; \
import logging; \
logging.basicConfig(level=logging.INFO); \
logger = logging.getLogger('teardown'); \
from src.apps.database.client import DatabaseClient; \
from src.apps.storage.s3 import S3Storage; \
from src.settings import settings; \
logger.info('Dropping and recreating database tables...'); \
db = DatabaseClient(); \
db.recreate_tables(); \
db.close(); \
logger.info('Database tables reset.'); \
logger.info('Deleting S3 objects under kayak/...'); \
s3 = S3Storage( \
    bucket_name=settings.bucket, \
    aws_access_key_id=settings.aws_access_key_id, \
    aws_secret_access_key=settings.aws_secret_access_key, \
    region=settings.s3_region, \
); \
deleted = s3.bucket.objects.filter(Prefix='kayak/').delete(); \
logger.info('S3 teardown complete.'); \
"
	@echo "Teardown complete."

clean:
	@echo "Cleaning temporary files..."
	@rm -rf __pycache__ .pytest_cache .coverage htmlcov
	@find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	@find . -type f -name "*.pyc" -delete
	@find . -type f -name "*.pyo" -delete
	@find . -type f -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
	@echo "Cleanup complete"
