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

    def test_get_session_number(self, tmpdir):
        tmpdir = pathlib.Path(tmpdir)
        (tmpdir / "0001.json").touch()
        (tmpdir / "0000.json").touch()
        (tmpdir / "0002.json").touch()
        assert gittrail.core._get_session_number(tmpdir) == 3

        (tmpdir / "0004.json").touch()
        with pytest.raises(gittrail.IncompleteHistoryError, match="session number 3"):
            gittrail.core._get_session_number(tmpdir)
        pass

    def test_get_active_sessions(self, tmpdir):
        data = pathlib.Path(tmpdir)
        store = data / "gittrail"
        store.mkdir()
        gittrail.core._meta_write(store / "0000.json", dict(end_utc="2021-10-11T07:08:09.000123Z"))
        gittrail.core._meta_write(store / "0001.json", dict(end_utc=None))
        assert gittrail.core._get_active_sessions(store) == {1}
        pass

    def test_drop_active(self):
        assert gittrail.core._drop_active(
            files={
                "store/0000.log": 1,
                "store/0000.json": 2,
                "store/0001.log": 3,
                "store/0001.json": 4,
                "store/0002.log": 5,
                "store/0002.json": 6,
            },
            drop_logs={0, 2},
            drop_meta={1},
            store="store",
        ) == {
            "store/0000.json": 2,
            "store/0001.log": 3,
            "store/0002.json": 6,
        }
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
        assert gt._session_number is None
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
        repo = test_helpers.create_repo(tmpdir, n_commits=3)
        data = tmpdir / "data"
        data.mkdir()

        with gittrail.GitTrail(repo, data) as gt:
            assert len(gt._git_history) == 3
            assert gt._session_number == 0
            assert gt._session_fp is not None
            assert gt._session_start_utc is not None
            assert gt._session_end_utc is None
            assert gt._files == {}
            assert gt._log_file is not None
            assert gt._log_handler is not None
            assert gt._log_file is not None
            assert (data / "gittrail" / "0000.json").exists()
            assert (data / "gittrail" / "0000.log").exists()
            meta = gittrail.core._meta_read(data / "gittrail" / "0000.json")
            assert meta["commit_id"] == utils.git_log(repo)[0]
            assert len(meta["start_utc"]) == 27
            assert meta["end_utc"] is None
            assert meta["files"] == {}
        assert set(gt._files) == {"gittrail/0000.log"}
        meta = gittrail.core._meta_read(data / "gittrail" / "0000.json")
        assert meta["end_utc"] is not None
        assert set(meta["files"]) == {"gittrail/0000.log"}
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

    def test_check_integrity(self, tmpdir):
        repo = test_helpers.create_repo(tmpdir)
        data = tmpdir / "data"
        data.mkdir()
        gt = gittrail.GitTrail(repo, data)
        with gt:
            logging.info("Session 0")

        # Each historic session must link a commit ID from the git history
        gittrail.core._commit_trail(
            fp=gt._dp_trail / "0001.json",
            commit_id="notarealone",
            start_utc=utils.now(),
            end_utc=utils.now(),
            files=utils.hash_all_files(data),
        )
        with pytest.raises(gittrail.UnknownCommitError, match="session 1 ran with"):
            with gt:
                pass
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

    def test_nested_sessions(self, tmpdir):
        repo = test_helpers.create_repo(tmpdir)
        data = tmpdir / "data"
        data.mkdir()

        with gittrail.GitTrail(repo, data) as outer:
            logging.info("Outer session")
            assert len(outer._files) == 0

            # Start a parallel session
            with gittrail.GitTrail(repo, data) as inner:
                logging.info("Inner session")
                # The JSON & LOG of the outer session are expected diffs
                assert len(outer._files) == 0
            # Log of the inner session
            assert len(inner._files) == 1
        # Log & json of the inner + log of the outer session
        assert len(outer._files) == 3
        pass

    def test_interleaved_sessions(self, tmpdir):
        repo = test_helpers.create_repo(tmpdir)
        data = tmpdir / "data"
        data.mkdir()

        sessA = gittrail.GitTrail(repo, data)
        sessB = gittrail.GitTrail(repo, data)

        sessA.__enter__()
        assert len(sessA._files) == 0

        sessB.__enter__()
        assert len(sessA._files) == 0

        sessA.__exit__()
        assert len(sessA._files) == 1

        sessB.__exit__()
        assert len(sessB._files) == 3
        pass
