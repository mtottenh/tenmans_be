-- Create test database and grant privileges
CREATE DATABASE test_db;

-- Grant privileges to the application user
GRANT ALL PRIVILEGES ON DATABASE test_db TO cs210mans_postgres_user;
ALTER DATABASE test_db OWNER TO cs210mans_postgres_user;