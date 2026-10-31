.PHONY: help install setup run dry-run check-sources render-sample clean

help:
	@echo "AI News Bot - Available Commands"
	@echo "================================="
	@echo "  make install       - Install Python dependencies"
	@echo "  make setup         - Initial setup (copy .env.example, install deps)"
	@echo "  make run           - Run the news bot"
	@echo "  make dry-run       - Generate digest only (no notifications)"
	@echo "  make check-sources - Verify RSS feeds in config.yaml (no Gemini)"
	@echo "  make render-sample - Print sample full/short digest (no Gemini)"
	@echo "  make clean         - Clean up cache files"
	@echo ""

install:
	@echo "Installing dependencies..."
	pip install -r requirements.txt
	@echo "Done!"

setup: install
	@echo "Setting up AI News Bot..."
	@if [ ! -f .env ]; then \
		echo "Creating .env from .env.example..."; \
		cp .env.example .env; \
		echo "Please edit .env with your actual credentials"; \
	else \
		echo ".env already exists, skipping..."; \
	fi
	@echo ""
	@echo "Setup complete! Next steps:"
	@echo "  1. Edit .env with your API keys"
	@echo "  2. Run 'make dry-run' to generate a digest locally (needs API key)"
	@echo "  3. Or use GitHub Actions with dry_run checked"

run:
	@echo "Running AI News Bot..."
	python main.py

dry-run:
	@echo "Running AI News Bot (dry run)..."
	python main.py --dry-run

check-sources:
	@python3 scripts/check_sources.py

render-sample:
	@python3 scripts/render_sample.py

clean:
	@echo "Cleaning up..."
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete
	find . -type f -name "*.pyo" -delete
	find . -type f -name "*.log" -delete
	@echo "Done!"
