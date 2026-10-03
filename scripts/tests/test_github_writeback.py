import subprocess
import tempfile
import os
import unittest
import shutil

class TestGithubWriteback(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.remote_dir = os.path.join(self.temp_dir, "remote.git")
        self.local_dir = os.path.join(self.temp_dir, "local")
        self.other_dir = os.path.join(self.temp_dir, "other")

        # Setup remote
        subprocess.run(["git", "init", "--bare", self.remote_dir], check=True, capture_output=True)

        # Setup local
        subprocess.run(["git", "clone", self.remote_dir, self.local_dir], check=True, capture_output=True)
        with open(os.path.join(self.local_dir, "test.txt"), "w") as f:
            f.write("initial\n")
        subprocess.run(["git", "add", "test.txt"], cwd=self.local_dir, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=self.local_dir, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=self.local_dir, check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "initial"], cwd=self.local_dir, check=True, capture_output=True)
        subprocess.run(["git", "push", "origin", "master:main"], cwd=self.local_dir, check=True, capture_output=True)

        # Setup other client to create race condition
        subprocess.run(["git", "clone", self.remote_dir, self.other_dir], check=True, capture_output=True)
        subprocess.run(["git", "checkout", "main"], cwd=self.other_dir, check=True, capture_output=True)

    def tearDown(self):
        shutil.rmtree(self.temp_dir)

    def test_race_condition_handled(self):
        # Local makes a change
        subprocess.run(["git", "checkout", "main"], cwd=self.local_dir, check=True, capture_output=True)

        # Other makes a change and pushes
        with open(os.path.join(self.other_dir, "other.txt"), "w") as f:
            f.write("other\n")
        subprocess.run(["git", "add", "other.txt"], cwd=self.other_dir, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=self.other_dir, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=self.other_dir, check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "other commit"], cwd=self.other_dir, check=True, capture_output=True)
        subprocess.run(["git", "push", "origin", "main"], cwd=self.other_dir, check=True, capture_output=True)

        # Local tries to writeback using the script
        with open(os.path.join(self.local_dir, "local.txt"), "w") as f:
            f.write("local\n")

        script_path = os.path.abspath("scripts/common/github_writeback.py")
        env = os.environ.copy()

        res = subprocess.run([
            "python3", script_path, "local commit", "local.txt"
        ], cwd=self.local_dir, env=env, capture_output=True, text=True)

        self.assertEqual(res.returncode, 0, f"Script failed: {res.stdout}\n{res.stderr}")
        self.assertIn("Push failed", res.stdout)
        self.assertIn("Successfully pushed changes", res.stdout)

        # Verify remote has both
        subprocess.run(["git", "pull"], cwd=self.local_dir, check=True, capture_output=True)
        self.assertTrue(os.path.exists(os.path.join(self.local_dir, "other.txt")))
        self.assertTrue(os.path.exists(os.path.join(self.local_dir, "local.txt")))

    def test_genuine_conflict(self):
        subprocess.run(["git", "checkout", "main"], cwd=self.local_dir, check=True, capture_output=True)

        # Other makes a conflicting change and pushes
        with open(os.path.join(self.other_dir, "test.txt"), "w") as f:
            f.write("other\n")
        subprocess.run(["git", "add", "test.txt"], cwd=self.other_dir, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=self.other_dir, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=self.other_dir, check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "other commit"], cwd=self.other_dir, check=True, capture_output=True)
        subprocess.run(["git", "push", "origin", "main"], cwd=self.other_dir, check=True, capture_output=True)

        # Local tries to writeback conflicting change
        with open(os.path.join(self.local_dir, "test.txt"), "w") as f:
            f.write("local conflict\n")

        script_path = os.path.abspath("scripts/common/github_writeback.py")
        env = os.environ.copy()

        res = subprocess.run([
            "python3", script_path, "local commit", "test.txt"
        ], cwd=self.local_dir, env=env, capture_output=True, text=True)

        self.assertNotEqual(res.returncode, 0)
        self.assertIn("Rebase conflict", res.stdout)

        # Local artifact should still be present in the filesystem
        with open(os.path.join(self.local_dir, "test.txt"), "r") as f:
            self.assertEqual(f.read(), "local conflict\n")

if __name__ == "__main__":
    unittest.main()
