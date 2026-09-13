import unittest

from evaluation import evaluate_golden
from integrations.github_actions import GitHubActionsClient, GitHubActionsError


class FakeGitHubActionsClient(GitHubActionsClient):
    def __init__(self):
        super().__init__(token="server-only-token")

    def _get_json(self, path):
        if path.endswith("/jobs?per_page=100"):
            return {"jobs": [{"id": 77, "name": "unit-tests", "conclusion": "failure"}]}
        return {
            "name": "CI",
            "head_branch": "main",
            "conclusion": "failure",
            "repository": {"name": "demo"},
            "created_at": "2026-09-13T12:00:00Z",
            "html_url": "https://github.com/acme/demo/actions/runs/42",
        }

    def _get_job_logs(self, owner, repository, job_id):
        return "There are test failures\npassword=should-not-leak"


class Step3Tests(unittest.TestCase):
    def test_github_adapter_normalizes_read_only_run(self):
        incident = FakeGitHubActionsClient().fetch_incident("acme", "demo", 42)
        self.assertEqual(incident["source"], "github_actions")
        self.assertEqual(incident["metadata"]["run_id"], "42")
        self.assertIn("[REDACTED]", incident["logs"])
        self.assertNotIn("should-not-leak", incident["logs"])

    def test_github_adapter_rejects_invalid_repository(self):
        with self.assertRaises(GitHubActionsError):
            FakeGitHubActionsClient().fetch_incident("acme/evil", "demo", 42)

    def test_golden_evaluation_reports_small_dataset_warning(self):
        result = evaluate_golden(repetitions=1)
        self.assertEqual(result["cases"], 3)
        self.assertEqual(result["summary"]["total_runs"], 3)
        self.assertIsNotNone(result["summary"]["dataset_warning"])
        self.assertEqual(result["summary"]["routing_pass"], 3)


if __name__ == "__main__":
    unittest.main()
