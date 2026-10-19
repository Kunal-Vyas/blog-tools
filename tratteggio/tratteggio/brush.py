"""The restorer's brush: a local model through Ollama's chat API."""
import json
import urllib.request

DEFAULT_URL = "http://localhost:11434"


class Ollama:
    def __init__(self, model: str = "llama3.2", url: str = DEFAULT_URL):
        self.model, self.url = model, url.rstrip("/")

    def _post(self, path: str, payload: dict) -> dict:
        req = urllib.request.Request(self.url + path, json.dumps(payload).encode(),
                                     {"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=120) as r:
            return json.loads(r.read())

    def chat(self, messages: list[dict]) -> str:
        out = self._post("/api/chat", {"model": self.model, "messages": messages,
                                       "stream": False, "options": {"temperature": 0}})
        return out["message"]["content"].strip()


class OllamaEmbedder:
    """Optional: pass to Catalogue(embedder=...) for hybrid search."""

    def __init__(self, model: str = "nomic-embed-text", url: str = DEFAULT_URL):
        self.client, self.model = Ollama(model, url), model

    def embed(self, texts: list[str]) -> list[list[float]]:
        out = self.client._post("/api/embed", {"model": self.model, "input": texts})
        vecs = out["embeddings"]
        return [[x / (sum(y * y for y in v) ** 0.5 or 1) for x in v] for v in vecs]
