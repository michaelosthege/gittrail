import logging
import pathlib
import subprocess
import time
import traceback
from datetime import datetime

import gittrail


def create_repo(root, n_commits=1):
    repo = pathlib.Path(root) / "repo"
    repo.mkdir()
    rps = str(repo)
    subprocess.check_call(["git", "-C", rps, "init"])
    subprocess.check_call(["git", "-C", rps, "config", "user.name", "ci"])
    subprocess.check_call(["git", "-C", rps, "config", "user.email", "ci@testing.com"])
    for n in range(n_commits):
        subprocess.check_call(["git", "-C", rps, "commit", "--allow-empty", "-m", f"'Commit {n}'"])
    return repo


def session_worker(kwargs):
    """For testing with multiprocessing/multithreading."""
    repo = kwargs.get("repo")
    data = kwargs.get("data")
    num = kwargs.get("worker_number")
    outfile = kwargs.get("outfile", "end")
    assert outfile in {"none", "start", "end", "start+end"}
    delay = kwargs.get("delay", 0)
    duration = kwargs.get("duration", 0)
    success = False
    message = ""
    try:
        if delay:
            logging.info("Worker number %i delaying.", num)
            time.sleep(delay)
        logging.info("Worker number %i starting.", num)
        with gittrail.GitTrail(repo, data, log_level=logging.DEBUG) as gt:
            fp_outfile = gt.data / f"worker_{num}.data"
            logging.info("Worker number %i started.", num)
            if "start" in outfile:
                fp_outfile.open("a").write(f"Made by worker {num} ({datetime.now()}).\n")
            time.sleep(duration)
            if "end" in outfile:
                fp_outfile.open("a").write(f"Made by worker {num} ({datetime.now()}).\n")
            logging.info("Worker number %i exiting.", num)
        logging.info("Worker number %i exited.", num)
        success = True
    except Exception as ex:
        success = False
        message = f"Worker {num} failed.\n"
        logging.error(message, exc_info=ex)
        message += "".join(traceback.format_exception(None, ex, ex.__traceback__))
    return success, message
