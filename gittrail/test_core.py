import json
import logging
import pathlib
from datetime import datetime, timezone

import pytest

import gittrail
from gittrail.exceptions import IncompleteHistoryError

_DP_REPOROOT = pathlib.Path(__file__).parent.parent
_LOG_LEVELS = [10, 20, 30, 40, 50]


from . import test_helpers, utils


class TestFunctions:
    def test_commit_trail(self, tmpdir):
        files = {
            "1234": "foo.bar",
            "5678": "sub/dir.txt",
        }
        fp = tmpdir / "0010.json"
        gittrail.core._commit_trail(
            fp=fp,
            commit_id="blabla",
            start_utc=datetime(2020, 1, 1, 13, 14, 15, tzinfo=timezone.utc),
            end_utc=datetime(2021, 10, 11, 7, 8, 9, microsecond=123, tzinfo=timezone.utc),
            files=files,
        )
        with fp.open("r", encoding="utf-8") as jfile:
            meta = json.load(jfile)
        assert meta["commit_id"] == "blabla"
        assert meta["start_utc"] == "2020-01-01T13:14:15.000000Z"
        assert meta["end_utc"] == "2021-10-11T07:08:09.000123Z"
        assert meta["files"] == files
        pass


class TestGittrail:
    def test_has_version(self):
        assert hasattr(gittrail, "__version__")
        pass

    def test_init(self, tmpdir):
        with pytest.raises(FileNotFoundError, match="Repo path"):
            gittrail.GitTrail(
                repo=_DP_REPOROOT / "notexists",
                data=tmpdir,
            )
        with pytest.raises(FileNotFoundError, match="Data path"):
            gittrail.GitTrail(
                repo=_DP_REPOROOT,
                data=tmpdir / "notexists",
            )

        gt = gittrail.GitTrail(
            repo=_DP_REPOROOT,
            data=tmpdir,
        )
        assert not gt._dp_trail.exists()
        pass

    def test_custom_subdir(self, tmpdir):
        gt = gittrail.GitTrail(
            repo=_DP_REPOROOT,
            data=tmpdir,
            store="audittrail",
        )
        assert gt._dp_trail.name == "audittrail"
        pass

    def test_enter_exit_noop_context(self, tmpdir):
        repo = test_helpers.create_repo(tmpdir)
        data = tmpdir / "data"
        data.mkdir()

        with gittrail.GitTrail(repo, data) as gt:
            assert len(gt._git_history) == 3
        assert (data / ".gittrail" / "0000.json").exists()
        assert (data / ".gittrail" / "0000.log").exists()
        with (data / ".gittrail" / "0000.json").open("r", encoding="utf-8") as jfile:
            meta = json.load(jfile)
        assert meta["commit_id"] == utils.git_log(repo)[0]
        assert "start_utc" in meta
        assert "end_utc" in meta
        assert len(meta["files"]) == 1
        assert tuple(meta["files"].values())[0] == ".gittrail/0000.log"
        pass

    @pytest.mark.parametrize("log_level", _LOG_LEVELS)
    def test_log_capture(self, tmpdir, log_level):
        repo = test_helpers.create_repo(tmpdir)
        data = tmpdir / "data"
        data.mkdir()
        rootLogger = logging.getLogger()
        rootLogger.setLevel(2)
        with gittrail.GitTrail(repo, data, log_level=log_level) as gt:
            assert rootLogger.level == log_level
            for l in _LOG_LEVELS:
                logging.log(level=l, msg=f"Level {l}.")
        assert rootLogger.level == 2
        assert gt._log_file.exists()
        captured = gt._log_file.read_text(encoding="utf-8")
        for l in reversed(_LOG_LEVELS):
            assert (f"Level {l}." in captured) == (l >= log_level), f"Level {l} is missing"
        pass

    def test_enter_exceptions(self, tmpdir):
        repo = test_helpers.create_repo(tmpdir)
        data = tmpdir / "data"
        data.mkdir()
        gt = gittrail.GitTrail(repo, data)

        fp_diff = repo / "new_code.py"
        fp_diff.touch()

        with pytest.raises(gittrail.UncleanGitStatusError, match="new_code.py"):
            gt.__enter__()

        pass

    def test_trail_gaps(self, tmpdir):
        repo = test_helpers.create_repo(tmpdir)
        data = tmpdir / "data"
        data.mkdir()
        gt = gittrail.GitTrail(repo, data)
        with gt:
            logging.info("Session 0")

        # In-between session metadata must be kept
        fp = gt._dp_trail / "0002.json"
        fp.touch()
        with pytest.raises(gittrail.IncompleteHistoryError, match="session number 1"):
            with gt:
                pass

        # Each historic session must link a commit ID from the git history
        gittrail.core._commit_trail(
            fp=gt._dp_trail / "0001.json",
            commit_id="notarealone",
            start_utc=utils.now(),
            end_utc=utils.now(),
            files=utils.hash_all_files(data),
        )
        with pytest.raises(gittrail.UnknownCommitError, match="session 1 ran with"):
            gt._get_session_number()
        pass

    def test_multiple_sessions(self, tmpdir, caplog):
        repo = test_helpers.create_repo(tmpdir)
        data = tmpdir / "data"
        data.mkdir()
        gt = gittrail.GitTrail(repo, data)
        with gt:
            logging.info("Session 0")
        with gt:
            logging.info("Session 1")
        # Remove the log file of session 0 to trigger the missing file warning
        (gt._dp_trail / "0000.log").unlink()
        with caplog.at_level(logging.WARNING):
            caplog.clear()
            with gt:
                logging.info("Session 2")
            assert "Missing 1 files" in caplog.records[0].message
            assert "0000.log" in caplog.records[0].message

        # Write a new log file of session 0 to trigger the file integrity error
        (gt._dp_trail / "0000.log").write_text("Not the real log")
        with pytest.raises(gittrail.IntegrityError, match="Found 1 files"):
            with gt:
                pass
        pass
