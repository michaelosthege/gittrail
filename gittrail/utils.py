"""
Utility functions independent of ``gittrail`` components.
"""

import datetime
import hashlib
import os
import pathlib
import subprocess
from typing import Dict, Optional, Set, Tuple, Union

PathLike = Union[str, pathlib.Path]


def hash_file(fp: PathLike) -> str:
    """Computes the MD5 hash of a file."""
    file_hash = hashlib.md5()
    with open(fp, "rb") as file:
        while True:
            chunk = file.read(65536)
            if not chunk:
                break
            file_hash.update(chunk)
    return file_hash.hexdigest()


def hash_all_files(
    dp: str, exclude: Optional[Set[Union[str, pathlib.Path]]] = None
) -> Dict[str, str]:
    """Hashes all files in [dp], returning a dict keyed by the relative filepaths.

    Parameters
    ----------
    dp : path-like
        Target directory.
    exclude : set of str
        File paths to ``dp`` to exclude from the hashing.
    """
    exclude = {
        str(pathlib.Path(fp).relative_to(dp)).replace(os.sep, "/") for fp in exclude or set()
    }
    files = tuple(pathlib.Path(dp).glob("**/*"))
    hashes = {}
    for fp in files:
        if fp.is_file():
            fpr = str(fp.relative_to(dp)).replace(os.sep, "/")
            if fpr not in exclude:
                hashes[fpr] = hash_file(fp)
    return hashes


def git_log(dp: PathLike) -> Tuple[str]:
    """Returns a tuple of all commit hashes in the git history (newest first)."""
    output = subprocess.check_output(["git", "-C", str(dp), "log", '--format=format:"%H"'])
    output = output.strip().decode("ascii")
    output = output.replace('"', "")
    return tuple(output.split("\n"))


def git_status(dp: PathLike) -> str:
    """Returns the git status message."""
    output = subprocess.check_output(["git", "-C", str(dp), "status"])
    output = output.strip().decode("ascii")
    return output


def now() -> datetime.datetime:
    """Timezone aware UTC now."""
    return datetime.datetime.now().astimezone(datetime.timezone.utc)
