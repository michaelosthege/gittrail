"""
Utility functions independent of ``gittrail`` components.
"""

import hashlib
import os
import pathlib
from typing import Dict, Union


def hash_file(fp: Union[str, pathlib.Path]) -> str:
    """Computes the MD5 hash of a file."""
    file_hash = hashlib.md5()
    with open(fp, "rb") as file:
        while True:
            chunk = file.read(65536)
            if not chunk:
                break
            file_hash.update(chunk)
    return file_hash.hexdigest()


def hash_all_files(dp: str) -> Dict[str, str]:
    """Hashes all files in [dp], returning a dict keyed by the hashes."""
    files = tuple(pathlib.Path(dp).glob("**/*"))
    hashes = {}
    for fp in files:
        if fp.is_file():
            hashes[hash_file(fp)] = str(fp.relative_to(dp)).replace(os.sep, "/")
    return hashes
