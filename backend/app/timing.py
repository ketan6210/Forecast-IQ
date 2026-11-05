import logging
from contextlib import contextmanager
from time import perf_counter
from typing import Iterator

logger = logging.getLogger("forecastiq.timings")


@contextmanager
def timed(name: str, timings: dict[str, float]) -> Iterator[None]:
    start = perf_counter()
    try:
        yield
    finally:
        elapsed = perf_counter() - start
        timings[name] = round(elapsed, 6)
        logger.info("%s duration_seconds=%.6f", name, elapsed)
