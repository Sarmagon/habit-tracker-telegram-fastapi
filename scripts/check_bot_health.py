import time
from pathlib import Path

heartbeat = Path("/tmp/bot-heartbeat")
raise SystemExit(
    0 if heartbeat.exists() and time.time() - heartbeat.stat().st_mtime < 90 else 1
)
