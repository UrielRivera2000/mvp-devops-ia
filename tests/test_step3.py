import unittest
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from evaluation import evaluate_golden
from integrations.github_actions import GitHubActionsClient, GitHubActionsError


class RedirectTargetHandler(BaseHTTPRequestHandler):
    authorization = None

    def do_GET(self):  # noqa: N802
        self.__class__.authorization = self.headers.get("Authorization")
        body = b"redirected-log"
        self.send_response(200)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_args):
        return


class RedirectSourceHandler(BaseHTTPRequestHandler):
    target_url = ""

    def do_GET(self):  # noqa: N802
        self.send_response(302)
        self.send_header("Location", self.__class__.target_url)
        self.end_headers()

    def log_message(self, *_args):
        return


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
    def test_github_redirect_does_not_forward_authorization(self):
        target_server = ThreadingHTTPServer(("127.0.0.1", 0), RedirectTargetHandler)
        target_thread = threading.Thread(target=target_server.serve_forever, daemon=True)
        target_thread.start()
        target_url = f"http://127.0.0.1:{target_server.server_address[1]}/logs"

        RedirectSourceHandler.target_url = target_url
        source_server = ThreadingHTTPServer(("127.0.0.1", 0), RedirectSourceHandler)
        source_thread = threading.Thread(target=source_server.serve_forever, daemon=True)
        source_thread.start()
        try:
            client = GitHubActionsClient(
                token="unit-test-token",
                base_url=f"http://127.0.0.1:{source_server.server_address[1]}",
            )
            self.assertEqual(client._request_bytes("/logs", "text/plain"), b"redirected-log")
            self.assertIsNone(RedirectTargetHandler.authorization)
        finally:
            source_server.shutdown()
            source_server.server_close()
            source_thread.join(timeout=2)
            target_server.shutdown()
            target_server.server_close()
            target_thread.join(timeout=2)

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
