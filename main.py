"""Messaging server entry point.

The app itself lives in oracle/messaging/app.py. This shim keeps the
documented commands working: `python main.py` and `uvicorn main:app`.
"""
from oracle.messaging.app import app  # noqa: F401

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8050, reload=True, proxy_headers=True)
