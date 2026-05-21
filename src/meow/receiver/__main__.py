"""Entry point for ``python -m meow.receiver``.

Boots uvicorn programmatically. The Dockerfile (S8) invokes uvicorn
directly, but this module is convenient for local runs.
"""

from __future__ import annotations

import os

import uvicorn


def main() -> None:
    host = os.environ.get("MEOW_RECEIVER_HOST", "0.0.0.0")
    port = int(os.environ.get("MEOW_RECEIVER_PORT", "8000"))
    uvicorn.run("meow.receiver.app:app", host=host, port=port)


if __name__ == "__main__":
    main()
