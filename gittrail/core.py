"""
Main implementation of the ``gittrail`` logic.
"""
import json
import logging
import os
import pathlib
from datetime import datetime
from typing import Dict, Union

from . import exceptions, utils

_log = logging.getLogger(__file__)


def _commit_trail(
    fp: Union[str, pathlib.Path],
    commit_id: str,
    start_utc: datetime,
    end_utc: datetime,
    files: Dict[str, str],
):
    """Writes an audittrail entry."""
    meta = {
        "commit_id": commit_id,
        "start_utc": start_utc.strftime("%Y-%m-%dT%H:%M:%S.%f%z").replace("+0000", "Z"),
        "end_utc": end_utc.strftime("%Y-%m-%dT%H:%M:%S.%f%z").replace("+0000", "Z"),
        "files": files,
    }
    with open(fp, "w", encoding="utf-8") as jfile:
        json.dump(meta, jfile, indent=4)
    return


class GitTrail:
    """Context manager for linking data with git history."""

    def __init__(self, repo: str, data: str, *, log_level: int = None, store: str = ".gittrail"):
        """Instantiate a ``GitTrail`` configuration.

        Parameters
        ----------
        repo : path-like
            Path to the directory of a git repository.
        data : path-like
            Working directory for inputs/outputs of the data pipeline.
            This is where the audittrail will be kept.
        log_level : int
            Log level to capture within the session.
            Applies to the root logger, which will be reset to its original
            log level when the session ends.
        store : str
            Name of the sub-directory in ``data`` where the audit trail is stored.
        """
        self.repo = pathlib.Path(repo)
        self.data = pathlib.Path(data)
        if not self.repo.exists():
            raise FileNotFoundError(f"Repo path {self.repo} does not exist.")
        if not self.data.exists():
            raise FileNotFoundError(f"Data path {self.data} does not exist.")

        self._dp_trail = self.data / store
        self._git_history = None
        self._session_number = None
        self._session_start_utc = None
        self._session_end_utc = None
        self._log_file = None
        self._log_handler = None
        self._log_level = log_level
        self._log_level_before = None
        super().__init__()

    def __enter__(self):
        # Reset state attributes
        self._session_number = None
        self._session_start_utc = None
        self._session_end_utc = None
        self._log_file = None
        self._log_handler = None
        self._log_level_before = None

        # Validate that the git repo is clean
        status = utils.git_status(self.repo)
        if not "working tree clean" in status:
            raise exceptions.UncleanGitStatusError(
                f"The git status of {self.repo} indicates uncomitted changes:\n{status}"
            )
        self._git_history = utils.git_log(self.repo)

        # Check the audittrail
        self._dp_trail.mkdir(exist_ok=True)
        self._check_integrity()

        # All checks succceeded. The session can start.
        self._attach_log_handler()
        self._session_start_utc = utils.now()
        return self

    def __exit__(self, *args, **kwargs):
        self._session_end_utc = utils.now()
        self._detach_log_handler()
        _commit_trail(
            fp=self._dp_trail / f"{self._session_number:04d}.json",
            commit_id=self._git_history[0],
            start_utc=self._session_start_utc,
            end_utc=self._session_end_utc,
            files=utils.hash_all_files(self.data),
        )
        return

    def _get_session_number(self) -> int:
        """Determins the current session number from the existing audittrail files."""
        sfiles = tuple(self._dp_trail.glob("*.json"))
        for s, sf in enumerate(sorted(sfiles, key=lambda fp: fp.name)):
            if not sf.name == f"{s:04d}.json":
                raise exceptions.IncompleteHistoryError(
                    f"Missing audittrail of session number {s}."
                )
            with open(sf, encoding="utf-8") as jfile:
                meta = json.load(jfile)
                cid = meta["commit_id"]
                if not cid in self._git_history:
                    raise exceptions.UnknownCommitError(
                        f"Audit trail session {s} ran with "
                        f"commit {cid} that's not in the git history."
                    )
        return len(sfiles)

    def _check_integrity(self):
        """Checks that the current contents of the [data] match the audittrail."""
        _log.debug("Checking integrity of %s", self.data)
        sn = self._get_session_number()
        self._session_number = sn
        self._log_file = self._dp_trail / f"{self._session_number:04d}.log"

        # Get file hashes from the last session
        if self._session_number > 0:
            fp = self._dp_trail / f"{sn - 1:04d}.json"
            with fp.open("r", encoding="utf-8") as jfile:
                previous = json.load(jfile)["files"]
        else:
            previous = {}

        # And file hashes as they are now
        current = utils.hash_all_files(self.data)

        # Any files missing, compared to the previous session?
        missing = {h: fp for h, fp in previous.items() if not h in current}
        if missing:
            msg = "\n".join([f"{h}: {fp}" for h, fp in missing.items()])
            _log.warning(
                "Missing %i files compared to the previous session:\n%s", len(missing), msg
            )

        # Any new/changed files? (Except the last sessions audittrail file.)
        fpm = self._dp_trail / f"{sn - 1:04d}.json"
        fpm = str(fpm.relative_to(self.data)).replace(os.sep, "/")
        extra = {h: fp for h, fp in current.items() if not h in previous and fp != fpm}
        if extra:
            msg = "\n".join([f"{h}: {fp}" for h, fp in extra.items()])
            raise exceptions.IntegrityError(
                f"Found {len(extra)} files that were illegally added/changed:\n{msg}"
            )
        return

    def _attach_log_handler(self):
        _log.debug("Routing logs to %s", self._log_file)
        longFormatter = logging.Formatter(
            "%(levelname).1s\t%(asctime)s.%(msecs)03dZ\t%(pathname)s:%(lineno)d\t%(message)s",
            datefmt="%Y-%m-%dT%H:%M:%S",
        )
        longFormatter.converter = lambda x: datetime.utcnow().utctimetuple()
        fileHandler = logging.FileHandler(filename=self._log_file)
        fileHandler.setLevel(self._log_level or 0)
        fileHandler.setFormatter(longFormatter)
        self._log_handler = fileHandler
        rootLogger = logging.getLogger()
        rootLogger.addHandler(self._log_handler)
        if self._log_level is not None:
            self._log_level_before = rootLogger.level
            rootLogger.setLevel(self._log_level)
        return

    def _detach_log_handler(self):
        _log.debug("Detaching log handler")
        rootLogger = logging.getLogger()
        rootLogger.removeHandler(self._log_handler)
        if self._log_level is not None:
            rootLogger.setLevel(self._log_level_before)
        return
