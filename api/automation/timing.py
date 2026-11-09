"""Diagnostic stage timings, separate from release data and validation policy."""
from contextlib import contextmanager
from datetime import datetime, timezone
import json
from time import perf_counter


PREFIX = '[refresh-timing] '


@contextmanager
def stage_timer(stage, *, log=print):
    """Measure elapsed time without changing a stage's return or failure behavior."""
    started = perf_counter()

    def emit(status):
        record = dict(stage=stage, status=status,
                      recorded_at=datetime.now(timezone.utc).isoformat())
        if status != 'started':
            record['elapsed_seconds'] = round(perf_counter() - started, 3)
        log(PREFIX + json.dumps(record, sort_keys=True))

    emit('started')
    try:
        yield
    except BaseException:
        emit('failed')
        raise
    else:
        emit('completed')
