"""Voice server entry point.

The app itself lives in oracle/voice/app.py. This shim keeps
`python voice.py [--staging]` (used by start_staging.py) and `voice:app`
working. oracle/voice/app.py reads `--staging` from sys.argv at import time,
so it must stay the first import here.
"""
from oracle.voice.app import app  # noqa: F401

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("voice:app", host="0.0.0.0", port=8002, reload=True, proxy_headers=True, ws_ping_interval=None, ws_ping_timeout=None)
