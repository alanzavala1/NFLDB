"""Run a frozen R exporter and stop its process tree on interruption."""
import os
from pathlib import Path
import signal
import subprocess

from pipeline.snapshots import CandidateError


def run_r_export(command: list[str], *, cwd: Path, env: dict, logfile: Path) -> None:
    options = {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP} if os.name == "nt" else {"start_new_session": True}
    with logfile.open("xb") as log:
        process = subprocess.Popen(command, cwd=cwd, env=env, stdout=log, stderr=subprocess.STDOUT, **options)
        try:
            code = process.wait()
        except BaseException:
            if os.name == "nt":
                subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
            else:
                os.killpg(process.pid, signal.SIGKILL)
            process.wait()
            raise
    if code:
        raise CandidateError(f"R export failed ({code}); see {logfile}")
