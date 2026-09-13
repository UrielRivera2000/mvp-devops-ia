import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from app import Corpus, SecureLocalAgent, SOURCES_DIR
from provider import OpenRouterProvider, ProviderConfig


class FakeProviderHandler(BaseHTTPRequestHandler):
    calls = []

    def do_POST(self):  # noqa: N802
        length = int(self.headers.get("Content-Length", "0"))
        body = json.loads(self.rfile.read(length).decode("utf-8"))
        self.__class__.calls.append({
            "path": self.path,
            "body": body,
            "authorization": self.headers.get("Authorization"),
        })
        if self.path.endswith("/chat/completions") and len(self.__class__.calls) % 2 == 1:
            content = {"technical": True, "history": True}
        else:
            content = {
                "categoria": "Containers / Registry",
                "tecnologia": "Kubernetes",
                "error_detectado": "ImagePullBackOff",
                "confianza": 0.9,
                "evidencia": ["ImagePullBackOff aparece en el incidente."],
                "causas_probables": ["Credenciales del registry expiradas."],
                "validaciones_recomendadas": ["Confirmar imagen y tag."],
                "soluciones_sugeridas": ["Revisar con un especialista autorizado."],
                "informacion_faltante": [],
                "fuentes_utilizadas": ["KB-001", "DEVOPS-1001"],
                "incidentes_similares": ["DEVOPS-1001"],
                "fuera_de_alcance": False,
                "requiere_revision_humana": True,
                "mensaje_al_especialista": "Validar antes de actuar.",
            }
        response = json.dumps({"choices": [{"message": {"content": json.dumps(content)}}]}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(response)))
        self.end_headers()
        self.wfile.write(response)

    def log_message(self, *_args):
        return


class Step4Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        FakeProviderHandler.calls = []
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), FakeProviderHandler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=2)

    def test_provider_cycle_uses_allowlisted_sources_and_hides_token(self):
        port = self.server.server_address[1]
        provider = OpenRouterProvider(
            "unit-test-secret-token",
            ProviderConfig("local-mock", "mock-model", f"http://127.0.0.1:{port}"),
        )
        agent = SecureLocalAgent(Corpus(SOURCES_DIR), provider)
        result = agent.analyze(
            "Tecnología: Kubernetes\nLog: Failed to pull image: unauthorized: authentication required. ImagePullBackOff\nBusca antecedentes.",
            source="test",
        )
        self.assertEqual(result["trace"]["mode"], "llm")
        self.assertEqual(result["trace"]["selected_tools"], [
            "buscar_conocimiento_tecnico", "buscar_incidentes_historicos"
        ])
        self.assertEqual(result["behavior_ia"]["verdict"], "PASS")
        self.assertNotIn("unit-test-secret-token", json.dumps(result))
        self.assertEqual(len(FakeProviderHandler.calls), 2)
        self.assertEqual(FakeProviderHandler.calls[0]["authorization"], "Bearer unit-test-secret-token")
        self.assertNotIn("unit-test-secret-token", json.dumps(FakeProviderHandler.calls[0]["body"]))


if __name__ == "__main__":
    unittest.main()
