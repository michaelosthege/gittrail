import pathlib

from . import test_helpers, utils

_DP_REPOROOT = pathlib.Path(__file__).parent.parent


class TestHashing:
    def test_hash_file(self, tmpdir):
        tmpdir = pathlib.Path(tmpdir)
        fp = tmpdir / "test_hash_file.txt"
        # Create a file large enough to trigger the chunking mechanism
        with fp.open("wb") as file:
            file.write(("x\n" * 65_536).encode("ascii"))
        h = utils.hash_file(fp)
        assert isinstance(h, str)
        assert h == "3b3b66fa0374d39c905430f7c98606e4"
        pass

    def test_hash_depends_only_on_content(self, tmpdir):
        tmpdir = pathlib.Path(tmpdir)
        fp1 = tmpdir / "1.txt"
        fp2 = tmpdir / "2.txt"
        fp1.write_text("Hi there")
        fp2.write_text("Hi there")
        assert utils.hash_file(fp1) == utils.hash_file(fp2)
        pass

    def test_hash_all_files(self, tmpdir):
        tmpdir = pathlib.Path(tmpdir)
        d1 = tmpdir
        d2 = tmpdir / "subfolder"
        d2.mkdir(parents=True, exist_ok=True)
        (d1 / "one.txt").write_text("File one")
        (d2 / "two.txt").write_text("File two")
        result = utils.hash_all_files(d1)
        assert isinstance(result, dict)
        assert result["one.txt"] == "5d1c020d53f38ccf82ec532f35c9ca27"
        assert result["subfolder/two.txt"] == "51ae396c5595862e990e318c2176addb"
        pass


class TestGit:
    def test_git_log(self):
        commits = utils.git_log(_DP_REPOROOT)
        assert isinstance(commits, tuple)
        # New commits come first, because they're more relevant for the audittrail.
        assert commits[-1] == "3286fe415a4e1b7fcfdd596a88d8e06bbf6ffed8"
        assert commits[-2] == "ed3219e39b6aafb728fd34c9f2ec11c4978a166c"
        pass

    def test_git_status(self, tmpdir):
        repo = test_helpers.create_repo(tmpdir)

        result = utils.git_status(repo)
        assert "working tree clean" in result

        (repo / "hello.txt").touch()

        result = utils.git_status(repo)
        assert "working tree clean" not in result
        pass
