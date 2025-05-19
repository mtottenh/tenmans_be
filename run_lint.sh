#!/bin/bash

# This script runs linting tools on the codebase

echo "Running Ruff linter..."

# Run ruff check with error details
docker exec tenmans-api-1 ruff check src/ test/ utils/ --fix

# Run ruff format (similar to Black)
echo -e "\nRunning Ruff formatter..."
docker exec tenmans-api-1 ruff format src/ test/ utils/

# Check if there are any remaining issues
echo -e "\nChecking for remaining issues..."
docker exec tenmans-api-1 ruff check src/ test/ utils/ --statistics

echo -e "\nLinting complete!"