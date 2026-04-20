import logging
import signal
import time

from sqlalchemy import create_engine, text

from app.config import settings

logging.basicConfig(level=settings.log_level.upper(), format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("chronos.worker")

engine = create_engine(settings.database_url, pool_pre_ping=True, future=True)

_shutdown = False


def _handle_signal(signum: int, _frame: object) -> None:
    global _shutdown
    log.info("received signal %s, shutting down", signum)
    _shutdown = True


def poll_once() -> int:
    """Poll the jobs table for pending work. Returns number of jobs processed.

    Placeholder: the jobs table does not exist yet. The worker currently proves DB
    reachability and exits the poll loop; real job pickup lands with the scheduling engine.
    """
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    return 0


def main() -> None:
    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)
    log.info("worker started, poll_interval=%ss", settings.job_poll_interval_seconds)
    while not _shutdown:
        try:
            processed = poll_once()
            if processed:
                log.info("processed %d job(s)", processed)
        except Exception:
            log.exception("poll cycle failed")
        time.sleep(settings.job_poll_interval_seconds)
    log.info("worker stopped")


if __name__ == "__main__":
    main()
