# Makefile for AI Context Scraper Actor

.PHONY: help install install-dev test test-cov lint format type-check security-scan clean run docker-build docker-run deploy

PYTHON := python
PIP := pip
PYTEST := pytest
BLACK := black
RUFF := ruff
PYLINT := pylint
MYPY := mypy
BANDIT := bandit

help: ## Show this help message
	@echo "Available commands:"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'

install: ## Install production dependencies
	$(PIP) install -r requirements.txt

install-dev: ## Install all dependencies including dev tools
	$(PIP) install -r requirements.txt
	$(PIP) install black ruff pylint mypy bandit safety pytest-cov

test: ## Run tests
	$(PYTEST) tests/ -v

test-cov: ## Run tests with coverage report
	$(PYTEST) tests/ -v --cov=src --cov-report=term-missing --cov-report=html

test-watch: ## Run tests in watch mode
	$(PYTEST) tests/ -v --watch

lint: ## Run all linters
	$(RUFF) check src tests
	$(PYLINT) src --fail-under=8.0

format: ## Format code with Black
	$(BLACK) src tests

format-check: ## Check code formatting
	$(BLACK) --check --diff src tests

type-check: ## Run type checking with MyPy
	$(MYPY) src

security-scan: ## Run security scans
	$(BANDIT) -r src -f screen
	safety check

quality: format-check lint type-check ## Run all quality checks

clean: ## Clean up generated files
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".mypy_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".ruff_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
	rm -rf htmlcov/ .coverage coverage.xml 2>/dev/null || true

run: ## Run the actor locally
	$(PYTHON) -m src

docker-build: ## Build Docker image
	docker build -t ai-context-scraper:latest .

docker-run: ## Run Docker container
	docker run --rm -e APIFY_TOKEN -e GITHUB_TOKEN ai-context-scraper:latest

docker-test: ## Test Docker image
	docker build -t ai-context-scraper:test .
	docker run --rm ai-context-scraper:test $(PYTHON) -m pytest tests/

deploy: ## Deploy to Apify
	apify push

deploy-beta: ## Deploy to Apify as beta version
	apify push --build-tag beta

validate: clean format lint type-check test ## Full validation pipeline
	@echo "✅ All validation checks passed!"

ci: quality test security-scan ## Run CI pipeline locally
	@echo "✅ CI pipeline completed!"
