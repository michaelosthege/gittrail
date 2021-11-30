import pytest

import gittrail


class TestGittrail:
    def test_has_version(self):
        assert hasattr(gittrail, "__version__")
        pass
