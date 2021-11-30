import pathlib
import subprocess


def create_repo(root):
    repo = pathlib.Path(root) / "repo"
    repo.mkdir()
    rps = str(repo)
    subprocess.check_call(["git", "-C", rps, "init"])
    subprocess.check_call(["git", "-C", rps, "config", "user.name", "ci"])
    subprocess.check_call(["git", "-C", rps, "config", "user.email", "ci@testing.com"])
    subprocess.check_call(["git", "-C", rps, "commit", "--allow-empty", "-m", "'1st commit'"])
    subprocess.check_call(["git", "-C", rps, "commit", "--allow-empty", "-m", "'2nd commit'"])
    subprocess.check_call(["git", "-C", rps, "commit", "--allow-empty", "-m", "'3rd commit'"])
    return repo
