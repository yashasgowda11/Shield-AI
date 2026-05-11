"""Dev orchestrator — runs Shield AI backend with Lobster Trap as a sidecar.

Behavior:
  1. Looks for the lobstertrap binary in (in order):
       - $LOBSTERTRAP_BIN
       - ./lobstertrap
       - ../lobstertrap/lobstertrap
       - ~/Documents/lobstertrap/lobstertrap
       - whatever `which lobstertrap` returns
  2. If port 8080 is already serving (i.e. Lobster Trap already running),
     leaves it alone.
  3. Otherwise spawns `lobstertrap serve` with stdout/stderr → logs/lobstertrap.log
  4. Spawns uvicorn in the foreground.
  5. On Ctrl+C, sends SIGINT to both processes and waits for them to exit.

Use:
    python scripts/dev.py            # full stack (this is what `make backend` calls)
    make backend-only                # just uvicorn, no Lobster Trap orchestration
"""
import os
import shutil
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
LOG_DIR = REPO_ROOT / "logs"
LOG_DIR.mkdir(exist_ok=True)
LT_LOG = LOG_DIR / "lobstertrap.log"

LT_PORT = int(os.getenv("LOBSTERTRAP_PORT", "8080"))
BACKEND_PORT = int(os.getenv("SHIELD_BACKEND_PORT", "8000"))


def _port_in_use(port: int) -> bool:
    """Return True if something is already listening on the given port."""
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.5):
            return True
    except (socket.timeout, ConnectionRefusedError, OSError):
        return False


def find_lobstertrap_bin() -> str | None:
    """Resolve the lobstertrap binary path. Returns None if not findable."""
    explicit = os.getenv("LOBSTERTRAP_BIN")
    if explicit and Path(explicit).is_file() and os.access(explicit, os.X_OK):
        return str(Path(explicit).resolve())

    candidates = [
        REPO_ROOT / "lobstertrap",
        REPO_ROOT.parent / "lobstertrap" / "lobstertrap",
        Path.home() / "Documents" / "lobstertrap" / "lobstertrap",
    ]
    on_path = shutil.which("lobstertrap")
    if on_path:
        candidates.append(Path(on_path))

    for c in candidates:
        if c.is_file() and os.access(c, os.X_OK):
            return str(c.resolve())
    return None


def start_lobstertrap() -> subprocess.Popen | None:
    """Start Lobster Trap if needed. Returns the Popen handle, or None if we
    didn't start one (either already running or binary not found)."""
    if _port_in_use(LT_PORT):
        print(f"[dev] Lobster Trap already running on port {LT_PORT} — leaving it alone.")
        return None

    bin_path = find_lobstertrap_bin()
    if not bin_path:
        print(
            "[dev] Lobster Trap binary not found.\n"
            "      Backend will run with the offline pattern detector only.\n"
            "      To enable Lobster Trap:\n"
            "        - Install from https://github.com/veeainc/lobstertrap\n"
            "        - Either place the binary at ./lobstertrap or in ~/Documents/lobstertrap/\n"
            "        - Or set LOBSTERTRAP_BIN=/full/path/to/lobstertrap"
        )
        return None

    print(f"[dev] Starting Lobster Trap: {bin_path} serve (logs → {LT_LOG.relative_to(REPO_ROOT)})")
    log_fh = LT_LOG.open("w")
    proc = subprocess.Popen(
        [bin_path, "serve"],
        stdout=log_fh,
        stderr=subprocess.STDOUT,
        cwd=str(Path(bin_path).parent),
    )
    # Give it a beat to bind the port
    for _ in range(20):  # up to ~4 seconds
        if _port_in_use(LT_PORT):
            print(f"[dev] Lobster Trap ready on http://127.0.0.1:{LT_PORT}/_lobstertrap/")
            return proc
        if proc.poll() is not None:
            print(f"[dev] Lobster Trap exited prematurely. See {LT_LOG}.")
            return None
        time.sleep(0.2)
    print(f"[dev] Lobster Trap didn't bind to port {LT_PORT} in time — continuing anyway.")
    return proc


def start_uvicorn() -> subprocess.Popen:
    print(f"[dev] Starting Shield AI backend (uvicorn) on port {BACKEND_PORT}")
    return subprocess.Popen([
        sys.executable, "-m", "uvicorn",
        "backend.main:app",
        "--reload",
        "--port", str(BACKEND_PORT),
    ])


def main() -> int:
    if _port_in_use(BACKEND_PORT):
        print(
            f"[dev] Port {BACKEND_PORT} already in use. "
            "Stop the existing backend first:  pkill -f 'uvicorn backend.main'"
        )
        return 1

    lt_proc = start_lobstertrap()
    uv_proc = start_uvicorn()

    procs = [(name, p) for name, p in [("lobstertrap", lt_proc), ("uvicorn", uv_proc)] if p is not None]

    def shutdown(signum=None, frame=None):
        print("\n[dev] Shutting down...")
        # Stop in reverse start order — backend first, then sidecar
        for name, p in reversed(procs):
            if p.poll() is None:
                print(f"[dev]   sending SIGINT to {name} (PID {p.pid})")
                try:
                    p.send_signal(signal.SIGINT)
                except Exception as e:
                    print(f"[dev]   couldn't signal {name}: {e}")
        # Wait briefly for graceful exit
        deadline = time.time() + 5
        for name, p in procs:
            remaining = max(0.1, deadline - time.time())
            try:
                p.wait(timeout=remaining)
            except subprocess.TimeoutExpired:
                print(f"[dev]   {name} didn't exit in time — killing")
                p.kill()
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    try:
        uv_proc.wait()
    except KeyboardInterrupt:
        pass
    finally:
        shutdown()
    return 0


if __name__ == "__main__":
    sys.exit(main())
