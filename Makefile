.PHONY: lint format test coverage install clean

# Variables
DOCKER_EXEC = docker exec tenmans-api-1

# Lint the code with Ruff
lint:
	$(DOCKER_EXEC) ruff check src/ test/ utils/

# Fix linting issues with Ruff
lint-fix:
	$(DOCKER_EXEC) ruff check src/ test/ utils/ --fix

# Format code with Ruff
format:
	$(DOCKER_EXEC) ruff format src/ test/ utils/

# Type check with mypy
typecheck:
	$(DOCKER_EXEC) mypy src/

# Run all quality checks
quality: lint format typecheck

# Run tests
test:
	python run_tests.py

# Run tests with coverage
coverage:
	$(DOCKER_EXEC) pytest test/ --cov=src --cov-report=term-missing

# Install dependencies
install:
	$(DOCKER_EXEC) pip install -e .[dev]

# Install pre-commit hooks
pre-commit-install:
	pre-commit install

# Run pre-commit on all files
pre-commit-all:
	pre-commit run --all-files

# Clean up cache files
clean:
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type d -name ".pytest_cache" -exec rm -rf {} +
	find . -type d -name ".mypy_cache" -exec rm -rf {} +
	find . -type d -name ".ruff_cache" -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
	find . -type f -name "*.pyo" -delete
	find . -type f -name "*~" -delete
	find . -type f -name ".coverage" -delete
	rm -rf htmlcov/ dist/ build/ *.egg-info/

# Build Docker image
build:
	docker compose build

# Start development environment
dev:
	docker compose up --build -d

# Stop development environment
down:
	docker compose down

# Show logs
logs:
	docker compose logs -f api

# Complete development setup
setup: build dev install pre-commit-install
	@echo "Development environment is ready!"

# Help
help:
	@echo "Available commands:"
	@echo "  make lint          - Check code with Ruff"
	@echo "  make lint-fix      - Fix linting issues with Ruff"
	@echo "  make format        - Format code with Ruff"
	@echo "  make typecheck     - Run mypy type checking"
	@echo "  make quality       - Run all code quality checks"
	@echo "  make test          - Run tests"
	@echo "  make coverage      - Run tests with coverage report"
	@echo "  make install       - Install dependencies"
	@echo "  make clean         - Clean up cache files"
	@echo "  make build         - Build Docker images"
	@echo "  make dev           - Start development environment"
	@echo "  make down          - Stop development environment"
	@echo "  make setup         - Complete development setup"