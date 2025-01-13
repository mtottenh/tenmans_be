#!/bin/bash
docker compose up -d 
# Run tests
# docker-compose --env-file .env.test -f docker-compose.yml -f docker-compose.override.yml up --build


# Creating alembic migrations
# Run the container, but use # tail -f /dev/null as the CMD so it doesn't actually launch the webserver
# Run, 
# alembic revision --autogenerate -m "Add new model or field"
# Check the new migration script that's generated then run
# alembic upgrade head