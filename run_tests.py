import subprocess
import sys
import time
from pathlib import Path

def run_command(command: list[str], check: bool = True) -> subprocess.CompletedProcess:
    """Run a command and return the result"""
    try:
        result = subprocess.run(
            command,
            check=check,
            text=True,
            capture_output=True
        )
        print(f"Command output:\n{result.stdout}")
        if result.stderr:
            print(f"Command errors:\n{result.stderr}", file=sys.stderr)
        return result
    except subprocess.CalledProcessError as e:
        print(f"Command failed with exit code {e.returncode}")
        print(f"Error output:\n{e.stderr}", file=sys.stderr)
        raise

def main():
    # Ensure we're in the project root directory
    project_root = Path(__file__).parent

    print("Stopping any existing containers...")
    run_command(["docker", "compose", "down"], check=False)

    print("\nStarting test environment...")
    run_command([
        "docker", "compose",
        "-f", "docker-compose.yml",
        "-f", "docker-compose.override.yml",
        "up", "--build", "-d"
    ])

    print("\nWaiting for services to be ready..")
    for i in range(5):
        time.sleep(1)  # Give services time to start
        print('.')
    
    # Start a uvicorn server for tests that need a running API
    print("\nStarting test API server...")
    run_command([
        "docker", "exec", "-d", "tenmans-api-1", 
        "python", "-m", "uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"
    ])
    
    # Wait for API to be ready
    print("\nWaiting for API to start...")
    for i in range(3):
        time.sleep(1)
        print('.')

    try:
        # Check if specific tests were passed as arguments
        test_args = sys.argv[1:] if len(sys.argv) > 1 else ["../test"]

        # Build the pytest command with event loop policy for asyncio
        pytest_command = [
            "docker", "exec", "tenmans-api-1", 
            "python", "-m", "pytest", "-v", 
        ] + test_args

        print(f"\nRunning tests: {' '.join(test_args)}")
        run_command(pytest_command)

    except Exception as e:
        print(f"Error running tests: {e}")
        sys.exit(1)
    finally:
        print("\nTest run complete. Containers will remain running.")
        print("Run 'docker compose down' to stop containers when finished.")

if __name__ == "__main__":
    main()
