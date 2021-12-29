"""
Main implementation of the ``gittrail`` logic.
"""
import json
import logging
import os
import pathlib
from datetime import datetime
from typing import Dict, Optional, Set, Union

import filelock

from . import exceptions, utils

_log = logging.getLogger(__file__)


def _get_session_number(dp_trail: pathlib.Path) -> int:
    """Determins the current session number from the existing audittrail files."""
    sfiles = tuple(dp_trail.glob("*.json"))
    for s, sf in enumerate(sorted(sfiles, key=lambda fp: fp.name)):
        if not sf.name == f"{s:04d}.json":
            raise exceptions.IncompleteHistoryError(f"Missing audit trail of session number {s}.")
    return len(sfiles)


def _get_active_sessions(store: pathlib.Path) -> Set[int]:
    sfiles = tuple(store.glob("*.json"))
    active = {
        s
        for s, sf in enumerate(sorted(sfiles, key=lambda fp: fp.name))
        if _meta_read(sf)["end_utc"] is None
    }
    return active


def _drop_active(
    *, files: Dict[str, str], drop_meta: Set[int], drop_logs: Set[int], store: str
) -> Dict[str, str]:
    """Removes log and metadata files of specific sessions from the file hash dictionary."""
    ignore_jsons = {f"{store}/{s:04d}.json" for s in drop_meta}
    ignore_logs = {f"{store}/{s:04d}.log" for s in drop_logs}
    ignore_paths = {*ignore_logs, *ignore_jsons}
    return {fpr: h for fpr, h in files.items() if fpr not in ignore_paths}


def _meta_read(fp: pathlib.Path) -> dict:
    with fp.open(encoding="utf-8") as jfile:
        meta = json.load(jfile)
    return meta


def _meta_write(fp: pathlib.Path, meta: dict):
    with open(fp, "w", encoding="utf-8") as jfile:
        json.dump(meta, jfile, indent=4)
    return


def _commit_trail(
    fp: Union[str, pathlib.Path],
    commit_id: str,
    start_utc: datetime,
    end_utc: Optional[datetime],
    files: Dict[str, str],
):
    """Writes an audittrail entry."""
    meta = {
        "commit_id": commit_id,
        "start_utc": start_utc.strftime("%Y-%m-%dT%H:%M:%S.%f%z").replace("+0000", "Z"),
        "end_utc": end_utc.strftime("%Y-%m-%dT%H:%M:%S.%f%z").replace("+0000", "Z")
        if end_utc is not None
        else None,
        "files": files,
    }
    _meta_write(fp, meta)
    return


class GitTrail:
    """Context manager for linking data with git history."""

    def __init__(self, repo: str, data: str, *, log_level: int = None, store: str = "gittrail"):
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
        self._dp_trail_lock = filelock.FileLock(self._dp_trail / "lock")
        self._git_history = None
        self._session_number = None
        self._session_fp = None
        self._session_start_utc = None
        self._session_end_utc = None
        self._files = None
        self._log_file = None
        self._log_handler = None
        self._log_level = log_level
        self._log_level_before = None
        super().__init__()

    def __enter__(self):
        # Reset state attributes
        self._session_number = None
        self._session_fp = None
        self._session_start_utc = None
        self._session_end_utc = None
        self._files = None
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
        with self._dp_trail_lock.acquire():
            self._session_start_utc = utils.now()
            self._session_number = _get_session_number(self._dp_trail)
            self._session_fp = self._dp_trail / f"{self._session_number:04d}.json"
            self._log_file = self._dp_trail / f"{self._session_number:04d}.log"
            active_sessions = _get_active_sessions(self._dp_trail)
            self._files = _drop_active(
                files=utils.hash_all_files(self.data, exclude={self._dp_trail_lock.lock_file}),
                drop_logs=active_sessions,
                drop_meta=active_sessions,
                store=self._dp_trail.name,
            )
            self._check_integrity()

            # All checks succceeded. The session can start.
            self._attach_log_handler()
            _commit_trail(
                fp=self._session_fp,
                commit_id=self._git_history[0],
                start_utc=self._session_start_utc,
                end_utc=None,
                files=self._files,
            )
        return self

    def __exit__(self, *args, **kwargs):
        with self._dp_trail_lock.acquire():
            self._detach_log_handler()
            self._session_end_utc = utils.now()
            active_sessions = _get_active_sessions(self._dp_trail)
            self._files = _drop_active(
                files=utils.hash_all_files(self.data, exclude={self._dp_trail_lock.lock_file}),
                drop_logs=active_sessions - {self._session_number},
                drop_meta=active_sessions,
                store=self._dp_trail.name,
            )
            _commit_trail(
                fp=self._session_fp,
                commit_id=self._git_history[0],
                start_utc=self._session_start_utc,
                end_utc=self._session_end_utc,
                files=self._files,
            )
        return

    def _check_integrity(self):
        """Checks that the current contents of the [data] match the audittrail."""
        _log.debug("Checking integrity of %s", self.data)

        # First read all existing session metadata
        metas = [
            (s, _meta_read(self._dp_trail / f"{s:04d}.json")) for s in range(self._session_number)
        ]

        # Sort them by the time of the snapshot and collect active vs. completed separately
        metas = list(sorted(metas, key=lambda sm: sm[1]["end_utc"] or sm[1]["start_utc"]))
        metas_active = [(s, m) for s, m in metas if m["end_utc"] is None]
        metas_ended = [(s, m) for s, m in metas if m["end_utc"] is not None]

        # All commit IDs must be in the git history
        known_files = {}
        for s, meta in metas:
            cid = meta["commit_id"]
            if not cid in self._git_history:
                raise exceptions.UnknownCommitError(
                    f"Audit trail session {s} ran with "
                    f"commit {cid} that's not in the git history."
                )
            known_files.update(meta["files"])

        # Some files are expected to be missing from the history
        expected_extra = set()
        for s, meta in metas_active:
            # JSON and LOG files of active sessions are subject to change.
            expected_extra.add(self._dp_trail / f"{s:04d}.json")
            expected_extra.add(self._dp_trail / f"{s:04d}.log")
        if metas_ended and metas_ended[-1] == metas[-1]:
            # No session began after the last session ended.
            s, _ = metas_ended[-1]
            expected_extra.add(self._dp_trail / f"{s:04d}.json")
        expected_extra = {
            str(fp.relative_to(self.data)).replace(os.sep, "/") for fp in expected_extra
        }
        unexpectedly_known = expected_extra.intersection(known_files)
        if unexpectedly_known:
            msg = "\n".join(unexpectedly_known)
            msg += f"\nKnown: {known_files.keys()}"
            msg += f"\nExpected to be missing: {expected_extra}"
            raise exceptions.IntegrityError(
                f"Some files are, but should not be in the history:\n{msg}"
            )

        # Any files missing, compared to the historically known files?
        missing = {fpr: h for fpr, h in known_files.items() if not fpr in self._files}
        if missing:
            _log.warning(
                "Missing %i files compared to the previous session:\n%s",
                len(missing),
                "\n".join(missing),
            )

        # Any new files? (Not allowed unless other sessions are currently active.)
        new = set(self._files) - set(known_files) - expected_extra
        if new:
            msg = "\n".join(new)
            if metas_active:
                _log.warning(
                    "One of the %i currently active sessions added some files:\n%s",
                    len(metas_active),
                    msg,
                )
            else:
                raise exceptions.IntegrityError(
                    f"Found {len(new)} files that were illegally added:\n{msg}"
                )

        # Any changed files? (Not allowed unless other sessions are currently active.)
        changed = {
            fp: h
            for fp, h in self._files.items()
            if fp not in new and fp not in expected_extra and h != known_files.get(fp, h)
        }
        if changed:
            msg = "\n".join(changed)
            if metas_active:
                _log.warning(
                    "One of the %i currently active sessions changed some files:\n%s",
                    len(metas_active),
                    msg,
                )
            else:
                raise exceptions.IntegrityError(
                    f"Found {len(changed)} files that were illegally changed:\n{msg}"
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
