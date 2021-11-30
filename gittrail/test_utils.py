import pathlib

from gittrail import utils

_DP_TESTDATA = pathlib.Path(__file__).parent / "testdata"
_DP_TESTDATA.mkdir(parents=True, exist_ok=True)
_DP_REPOROOT = pathlib.Path(__file__).parent.parent


class TestHashing:
    def test_hash_file(self):
        fp = _DP_TESTDATA / "test_hash_file.txt"
        # Create a file large enough to trigger the chunking mechanism
        with fp.open("wb") as file:
            file.write(("x\n" * 65_536).encode("ascii"))
        h = utils.hash_file(fp)
        assert isinstance(h, str)
        assert h == "3b3b66fa0374d39c905430f7c98606e4"
        pass

    def test_hash_all_files(self):
        d1 = _DP_TESTDATA / "test_hash_all_files"
        d2 = _DP_TESTDATA / "test_hash_all_files" / "subfolder"
        d1.mkdir(parents=True, exist_ok=True)
        d2.mkdir(parents=True, exist_ok=True)
        (d1 / "one.txt").write_text("File one")
        (d2 / "two.txt").write_text("File two")
        result = utils.hash_all_files(d1)
        assert isinstance(result, dict)
        assert result["5d1c020d53f38ccf82ec532f35c9ca27"] == "one.txt"
        assert result["51ae396c5595862e990e318c2176addb"] == "subfolder/two.txt"
        pass


class TestGit:
    def test_git_log(self):
        commits = utils.git_log(_DP_REPOROOT)
        assert isinstance(commits, tuple)
        # New commits come first, because they're more relevant for the audittrail.
        assert commits[-1] == "3286fe415a4e1b7fcfdd596a88d8e06bbf6ffed8"
        assert commits[-2] == "ed3219e39b6aafb728fd34c9f2ec11c4978a166c"
        pass
