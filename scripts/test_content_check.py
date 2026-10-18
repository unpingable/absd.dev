"""Exercise local-rule fixture isolation through the actual content checker."""
import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent


class LocalRulesFixture(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="absd-content-rules-")
        self.addCleanup(self.temp.cleanup)
        self.checkout = pathlib.Path(self.temp.name) / "checkout"
        shutil.copytree(ROOT, self.checkout, ignore=shutil.ignore_patterns(
            ".git", "site", "__pycache__", "private-patterns.local"))
        (self.checkout / "scripts/private-patterns.local").write_text(
            "content-check-local-only-pattern\tsynthetic local rule\n")

    def run_checker(self):
        return subprocess.run([sys.executable, "-B", "scripts/content-check.py"],
                              cwd=self.checkout, capture_output=True, text=True)

    def test_checkout_with_local_rules_passes_without_inheriting_them(self):
        result = self.run_checker()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("fixtures removed", result.stdout)

    def test_fixture_guard_still_rejects_actual_rule_inheritance(self):
        script = self.checkout / "scripts/content-check.py"
        text = script.read_text()
        guard = "    assert not local_rules.exists(), 'fixture unexpectedly inherited local rules'"
        self.assertEqual(text.count(guard), 1)
        # Copy the source checkout's real fixture rule into the otherwise
        # isolated generated fixture. The product's existing guard must fail.
        text = text.replace(guard,
                            "    shutil.copyfile(ROOT/'scripts/private-patterns.local', local_rules)\n" + guard)
        script.write_text(text)
        result = self.run_checker()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("fixture unexpectedly inherited local rules", result.stderr)


if __name__ == "__main__":
    unittest.main()
