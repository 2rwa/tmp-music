#!/usr/bin/env python3
import os
import subprocess
import sys
import time

def run(cmd, **kwargs):
    kwargs.setdefault("check", True)
    kwargs.setdefault("text", True)
    print(f"+ {' '.join(cmd)}")
    return subprocess.run(cmd, **kwargs)

def main():
    if len(sys.argv) < 3:
        print("Usage: github_writeback.py <commit_message> <path1> [path2...]")
        sys.exit(1)

    msg = sys.argv[1]
    paths = sys.argv[2:]

    run(["git", "config", "user.name", "github-actions[bot]"])
    run(["git", "config", "user.email", "41898282+github-actions[bot]@users.noreply.github.com"])

    for path in paths:
        run(["git", "add", path])

    res = run(["git", "diff", "--cached", "--quiet"], check=False)
    if res.returncode == 0:
        print("No changes to commit")
        return

    run(["git", "commit", "-m", msg])

    max_retries = 3
    for attempt in range(max_retries):
        print(f"Push attempt {attempt + 1} of {max_retries}")

        # Try pushing
        # Use origin HEAD:main equivalent as github workflows often do
        res = run(["git", "push", "origin", "HEAD:main"], check=False)
        if res.returncode == 0:
            print("Successfully pushed changes.")
            return

        print("Push failed, likely due to a concurrent update.")
        if attempt < max_retries - 1:
            print("Reconciling with origin/main...")
            run(["git", "fetch", "origin", "main"])
            # Rebase our changes on top of the new main
            rebase_res = run(["git", "rebase", "origin/main"], check=False)
            if rebase_res.returncode != 0:
                print("Rebase conflict. A concurrent change conflicts with ours.")
                run(["git", "rebase", "--abort"])
                print("Aborting to avoid silent overwrite. Failing workflow.")
                sys.exit(1)

            time.sleep(2)
        else:
            print("Max retries reached. Failing workflow.")
            sys.exit(1)

if __name__ == "__main__":
    main()
