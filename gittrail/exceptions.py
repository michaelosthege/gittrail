"""
Types of errors that can appear with ``gittrail``.
"""


class GittrailError(Exception):
    """Common base class of all gittrail exceptions."""


class UncleanGitStatusError(GittrailError):
    """Error about a git repository with uncommitted changes."""


class IncompleteHistoryError(GittrailError):
    """Error about gaps in an audit trail."""


class UnknownCommitError(GittrailError):
    """Error about an audit trail session not linking to a historic commit."""


class IntegrityError(GittrailError):
    """Error about new/changed file hashes."""
