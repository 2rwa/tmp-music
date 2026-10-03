import glob
import os
import unittest


class TestGithubWorkflows(unittest.TestCase):
    def _workflow_files(self):
        workflows_dir = os.path.join(
            os.path.dirname(__file__), "..", "..", ".github", "workflows"
        )
        return sorted(
            glob.glob(os.path.join(workflows_dir, "*.yml"))
            + glob.glob(os.path.join(workflows_dir, "*.yaml"))
        )

    def test_no_raw_git_push(self):
        workflow_files = self._workflow_files()
        self.assertTrue(workflow_files, "No workflow files found to test.")

        for filepath in workflow_files:
            with open(filepath, "r", encoding="utf-8") as f:
                content = f.read()

            for i, line in enumerate(content.splitlines(), start=1):
                if "git push" in line:
                    self.fail(
                        f"Found raw 'git push' in {os.path.basename(filepath)} "
                        f"on line {i}:\n{line}\n\n"
                        "Use scripts/common/github_writeback.py instead to avoid race conditions."
                    )

    def test_recovery_workflows_are_manual_only(self):
        workflows_dir = os.path.join(
            os.path.dirname(__file__), "..", "..", ".github", "workflows"
        )
        recovery_workflows = [
            "recover-jugemu-artifacts.yml",
            "recover-whisper-ao-artifacts.yml",
        ]
        for filename in recovery_workflows:
            path = os.path.join(workflows_dir, filename)
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()
            self.assertIn("workflow_dispatch:", content)
            self.assertNotIn(
                "\n  push:",
                content,
                f"{filename} must not auto-run on pushes; it can overwrite current analysis with historical artifacts.",
            )


if __name__ == "__main__":
    unittest.main()
