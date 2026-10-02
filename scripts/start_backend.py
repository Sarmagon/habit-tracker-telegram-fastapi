import json
import os
import subprocess
from pathlib import Path


def start_backend():
    secrets = json.loads(
        Path(os.environ.get("SECRET_FILE", "/secrets/runtime.json")).read_text()
    )
    os.environ["DATABASE_URL"] = secrets["database_url"]
    subprocess.run(["alembic", "upgrade", "head"], check=True)
    os.execvp(
        "uvicorn",
        ["uvicorn", "backend.main:application", "--host", "0.0.0.0", "--port", "8000"],
    )


if __name__ == "__main__":
    start_backend()
