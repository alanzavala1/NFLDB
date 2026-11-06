"""Observe a selected native release and upstream changes without large downloads."""
import json
import os
from pathlib import Path

from pipeline import releases as native
from publication.releases import _bytes_record, verify
from publication.selection import read_selection


def write_record(path, value):
    with Path(path).open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(value, stream, sort_keys=True, indent=2, allow_nan=False)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())


def plan_refresh(pointer, store, *, season=None, force=False, observe=None):
    from jobs.refresh import native_remote_watermarks, upstream_latest_season

    year = upstream_latest_season() if season is None else season
    if type(year) is not int or year < 1999:
        raise ValueError('Provide an integer season from 1999 onward')
    selected = read_selection(pointer, store)
    choice = selected['selection']
    publication = verify(choice['destination'], store, marker_generation=choice['manifest_generation'],
                         marker_sha256=choice['manifest_sha256'])
    record = publication['publication']['files']['watermarks.json']
    raw = store.read(choice['destination']+'/watermarks.json', record['generation'])
    if any(_bytes_record(raw)[key] != record[key] for key in ('bytes', 'sha256', 'md5')):
        raise ValueError('Previous watermarks differ from the selected publication')
    marks = json.loads(raw)
    native._marks(marks)
    remote = (observe or native_remote_watermarks)(year)
    moved = sorted(key for key, stamp in remote.items()
                   if stamp is not None and marks.get(f'{key}:{year}') != stamp)
    return dict(format_version=1, kind='native_refresh_plan', season=year,
                changed=bool(moved) or force, forced=force, moved=moved,
                observed_versions=remote, selection=selected, publication=publication,
                validation_code_sha256=native.validation_revision())


def read_plan(path):
    value = json.loads(Path(path).read_bytes())
    if (type(value.get('format_version')) is not int or value['format_version'] != 1
            or value.get('kind') != 'native_refresh_plan' or type(value.get('season')) is not int
            or value['season'] < 1999 or type(value.get('changed')) is not bool
            or value.get('validation_code_sha256') != native.validation_revision()):
        raise ValueError('Invalid or incompatible native refresh plan')
    return value
