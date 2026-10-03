import unittest
import os
import glob

class TestGithubWorkflows(unittest.TestCase):
    def test_no_raw_git_push(self):
        workflows_dir = os.path.join(os.path.dirname(__file__), "..", "..", ".github", "workflows")
        workflow_files = glob.glob(os.path.join(workflows_dir, "*.yml"))

        self.assertTrue(len(workflow_files) > 0, "No workflow files found to test.")

        for filepath in workflow_files:
            with open(filepath, "r") as f:
                content = f.read()

            # Exclude known intentional non-writeback usages if they ever exist
            # For now, we want to ensure no 'git push' exists for writing back generated files.
            # We enforce that all our workflows use github_writeback.py instead.

            lines = content.split('\n')
            for i, line in enumerate(lines):
                if 'git push' in line:
                    self.fail(f"Found raw 'git push' in {os.path.basename(filepath)} on line {i+1}:\n{line}\n\nUse scripts/common/github_writeback.py instead to avoid race conditions.")

if __name__ == "__main__":
    unittest.main()
