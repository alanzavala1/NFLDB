"""Timing diagnostics preserve success, failure and interruption behavior."""
import json

import pytest

from automation import timing


def test_stage_duration_uses_monotonic_clock_and_does_not_change_result(monkeypatch):
    clock = iter([100.0, 112.3456])
    monkeypatch.setattr(timing, 'perf_counter', lambda: next(clock))
    messages = []
    with timing.stage_timer('Capture fresh native season', log=messages.append):
        result = 'original result'
    records = [json.loads(message.removeprefix(timing.PREFIX)) for message in messages]
    assert result == 'original result'
    assert [record['status'] for record in records] == ['started', 'completed']
    assert records[1]['elapsed_seconds'] == 12.346
    assert all(record['stage'] == 'Capture fresh native season' for record in records)


@pytest.mark.parametrize('error', [RuntimeError('failed calculation'), KeyboardInterrupt()])
def test_stage_failure_is_recorded_and_same_exception_propagates(monkeypatch, error):
    clock = iter([100.0, 105.0])
    monkeypatch.setattr(timing, 'perf_counter', lambda: next(clock))
    messages = []
    with pytest.raises(type(error)) as caught:
        with timing.stage_timer('Calculate fresh passing views', log=messages.append):
            raise error
    assert caught.value is error
    records = [json.loads(message.removeprefix(timing.PREFIX)) for message in messages]
    assert [record['status'] for record in records] == ['started', 'failed']
    assert records[1]['elapsed_seconds'] == 5.0
