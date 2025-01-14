# Tenmans Backend API server



Welcome to CS2 10 Mans! We're a friendly community dedicated to enjoying Counter-Strike 2 in a fun, laid-back environment. Whether you're joining our frequent 10-man games, diving into tournaments, or just looking to escape the frustration of Premier mode, we've got you covered. With a focus on good vibes and playing the forgotten classics like Cache, Train, and Biome, we're here to bring the fun back to CS2. Come join us and let's enjoy the game together!

# Use the override file to run pytest directly
docker compose -f docker-compose.yml -f docker-compose.override.yml up --build -d
# Run tests in the container
docker exec tenmans-api-1 python -m pytest test/test/competitions/tournament/ -v


# Start the normal environment (without override)
docker compose up --build -d
# Wait a moment for services to start, then run tests
docker exec tenmans-api-1 python -m pytest test/test/authentication -v

# Running a specific test
docker exec tenmans-api-1 python -m pytest test/test/competitions/tournament/test_progression.py::TestTournamentProgression::test_start_tournament -v