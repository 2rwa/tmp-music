import glob
import os
import unittest


class TestGithubWorkflows(unittest.TestCase):
    def test_no_raw_git_push(self):
        workflows_dir = os.path.join(
            os.path.dirname(__file__), "..", "..", ".github", "workflows"
        )
        workflow_files = sorted(
            glob.glob(os.path.join(workflows_dir, "*.yml"))
            + glob.glob(os.path.join(workflows_dir, "*.yaml"))
        )

        self.assertTrue(workflow_files, "No workflow files found to test.")

        for filepath in workflow_files:
            with open(filepath, "r", encoding="utf-8") as f:
                content = f.read()

            # Write-back workflows must use scripts/common/github_writeback.py.
            # Fail if raw repository pushes are reintroduced in either YAML extension.
            for i, line in enumerate(content.splitlines(), start=1):
                if "git push" in line:
                    self.fail(
                        f"Found raw 'git push' in {os.path.basename(filepath)} "
                        f"on line {i}:\n{line}\n\n"
                        "Use scripts/common/github_writeback.py instead to avoid race conditions."
                    )


if __name__ == "__main__":
    unittest.main()
