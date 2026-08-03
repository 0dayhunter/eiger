"""Deploy the Gandalf (Lakera) warm-up lab as a public Modal web app.

Wraps the existing threaded proxy (labs/m0-gandalf/gandalf_lakera_proxy.py) so
participants SELF-SERVE at a public HTTPS URL instead of only watching it on screen.
Stdlib-only; the proxy talks to the real Lakera Gandalf API (keyless).

Deploy (colleague, with Modal creds):
    modal deploy deploy/modal_gandalf.py
Modal prints a URL like  https://<workspace>--eiger-gandalf-serve.modal.run
Share that single URL with the room.

Accepted risk (KK's call): one shared container => one egress IP to Lakera's public,
anonymous API. If Lakera throttles/blocks the room, fall back to running the proxy on
screen. One warm container is enough — the proxy is threaded (ThreadingTCPServer) and
only proxies network I/O, so 32 participants share it comfortably.
"""
import os
import subprocess
import sys
from pathlib import Path

import modal

PORT = 8787
REMOTE_PROXY = "/app/gandalf_lakera_proxy.py"
LOCAL_PROXY = Path(__file__).parent.parent / "labs" / "m0-gandalf" / "gandalf_lakera_proxy.py"

# stdlib-only proxy — no pip deps. Bake the script into the image.
image = modal.Image.debian_slim(python_version="3.12").add_local_file(
    LOCAL_PROXY, REMOTE_PROXY
)

app = modal.App("eiger-gandalf")


@app.function(
    image=image,
    min_containers=1,   # keep one container warm through the session (older Modal: keep_warm=1)
    timeout=60 * 60,    # long-lived web server
)
@modal.concurrent(max_inputs=60)  # 32 participants share one container (older Modal: put allow_concurrent_inputs=60 on @app.function instead)
@modal.web_server(PORT, startup_timeout=60)
def serve():
    env = {
        **os.environ,
        "GANDALF_HOST": "0.0.0.0",   # bind all interfaces so Modal's proxy can reach it
        "GANDALF_PORT": str(PORT),
        "GANDALF_NO_BROWSER": "1",   # headless — never try to open a browser
    }
    # Launch the threaded proxy; Modal keeps the container alive and fronts it with HTTPS.
    subprocess.Popen([sys.executable, REMOTE_PROXY], env=env)
