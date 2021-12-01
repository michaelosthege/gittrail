import pathlib
import subprocess


def create_repo(root, n_commits=1):
    repo = pathlib.Path(root) / "repo"
    repo.mkdir()
    rps = str(repo)
    subprocess.check_call(["git", "-C", rps, "init"])
    subprocess.check_call(["git", "-C", rps, "config", "user.name", "ci"])
    subprocess.check_call(["git", "-C", rps, "config", "user.email", "ci@testing.com"])
    for n in range(n_commits):
        subprocess.check_call(["git", "-C", rps, "commit", "--allow-empty", "-m", f"'Commit {n}'"])
    return repo
