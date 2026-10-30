"""Small adapter around the same Google Cloud CLI used by deployment workflows."""
import json
import os
from pathlib import Path
import re
import shutil
import subprocess


def prefix(value):
    if not isinstance(value, str) or not re.fullmatch(r'gs://[a-z0-9][a-z0-9._-]+[a-z0-9](?:/[a-zA-Z0-9][a-zA-Z0-9_-]*)+', value):
        raise ValueError('Supply an explicit gs://bucket/path/release-id without wildcards or trailing slash')
    return value


def generation(value):
    if not isinstance(value, str) or not re.fullmatch('[1-9][0-9]*', value):
        raise ValueError('Invalid GCS object generation')
    return value


def command():
    executable = shutil.which('gcloud')
    if not executable:
        raise RuntimeError('Install and authenticate the Google Cloud CLI first')
    if os.name == 'nt' and Path(executable).suffix.lower() in ('.cmd', '.bat'):
        # Call the SDK's bundled interpreter directly: no cmd.exe expansion of
        # local paths or object names. This matches the installed launcher.
        sdk = Path(executable).parent.parent
        python = sdk/'platform/bundledpython/python.exe'
        entry = sdk/'lib/gcloud.py'
        if not python.is_file() or not entry.is_file():
            raise RuntimeError('Use a Google Cloud SDK installation with bundled Python on Windows')
        return [str(python), '-S', str(entry)]
    return [executable]


class GCloudStore:
    def __init__(self):
        self.command = command()

    def _run(self, *args):
        env = dict(os.environ, CLOUDSDK_STORAGE_PARALLEL_COMPOSITE_UPLOAD_ENABLED='false')
        return subprocess.run([*self.command, '--quiet', 'storage', *args], env=env,
                              stdout=subprocess.PIPE, check=True).stdout

    def stat(self, uri, version=None):
        return json.loads(self._run('objects', 'describe', uri if version is None else uri+'#'+generation(version),
                                    '--raw', '--format=json'))

    def create(self, uri, path, md5):
        self._run('cp', str(path), uri, '--if-generation-match=0', '--content-md5='+md5,
                  '--cache-control=no-store')
        return self.stat(uri)

    def read(self, uri, version):
        return self._run('cat', uri+'#'+generation(version))
