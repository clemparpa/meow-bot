"""Entry point for ``python -m meow.worker``.

v0.0.x stub — the real durable worker (``workflows.run_worker``) lands in
v0.1.0 (spec §7). Until then this module exists so ``docker compose up``
can boot the ``worker`` service without crashlooping, and so S12's smoke
test can grep the structured ``worker.started`` log line.

We block on ``signal.pause()`` rather than a ``time.sleep`` loop so SIGTERM
(sent by ``docker stop`` / ``docker compose down``) returns immediately
instead of waiting for the next tick.
"""

from __future__ import annotations

import signal

from meow.common.logging import get_logger


def main() -> None:
    logger = get_logger("worker")
    logger.info("worker.started", extra={"mode": "stub"})
    signal.pause()


if __name__ == "__main__":
    main()
