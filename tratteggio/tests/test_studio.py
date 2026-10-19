import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

from tratteggio import archive, chunker
from tratteggio.ask import ARCHIVE, answer, studio
from tratteggio.brush import Ollama
from tratteggio.catalogue import Catalogue

Q = "What was the merchant holding in his right hand?"
MERCHANT = "disegno-14#description"


class Canned:
    def __init__(self, text): self.text, self.seen = text, None
    def chat(self, messages): self.seen = messages; return self.text


def source_no(result, chunk_id):
    return next(n for n, h in enumerate(result.sources, 1) if h.chunk.id == chunk_id)


def test_grounded_answer_passes():
    probe = answer(Q, studio(), Canned("NOT_IN_SOURCES"))
    n = source_no(probe, MERCHANT)
    r = answer(Q, studio(), Canned(f"He holds a balance raised in his right hand [S{n}]."))
    assert not r.refused


def test_invented_measurement_is_caught():
    r = answer("How big is the hole in the lower centre?", studio(),
               Canned("The loss is about 12 cm across [S1]."))
    assert r.refused and "12 is not in" in r.reason


def test_uncited_sentence_is_caught():
    r = answer(Q, studio(), Canned("He holds a balance [S3]. It was a common emblem of honest trade."))
    assert r.refused and "uncited" in r.reason


def test_model_refusal_is_respected():
    r = answer("How much did the 1953 treatment cost?", studio(), Canned("NOT_IN_SOURCES"))
    assert r.refused and "model found no answer" in r.reason


def test_gate_refuses_before_model():
    m = Canned("should never be called")
    r = answer("Is the fresco signed?", studio(), m)
    assert r.refused and m.seen is None


def test_wrong_chapel_and_old_report_are_filtered():
    cat = studio()
    assert cat.search(Q, k=1)[0].chunk.page.chapel == "pistoia"            # unfiltered: the purse
    assert all(h.chunk.page.chapel != "pistoia" for h in cat.search(Q, k=5, chapel="lanaioli"))
    q = "How big is the loss in the lower centre?"
    assert cat.search(q, k=1)[0].chunk.page.id == "report-1952"           # unfiltered: 12 cm
    assert cat.search(q, k=1, chapel="lanaioli", current=True)[0].chunk.page.id == "survey-2019"


def test_hybrid_fusion_promotes_vector_match():
    class Fake:
        def embed(self, texts):
            return [[1.0, 0.0] if ("balance held up" in t or "right hand?" in t) else [0.0, 1.0] for t in texts]
    cat = Catalogue(chunker.by_heading(archive.load(ARCHIVE)), embedder=Fake())
    assert cat.search(Q, k=3, chapel="lanaioli", current=True)[0].chunk.id == MERCHANT


def test_ollama_client_against_stand_in_server():
    class H(BaseHTTPRequestHandler):
        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            assert body["stream"] is False and body["options"]["temperature"] == 0
            out = json.dumps({"message": {"role": "assistant", "content": " ok [S1]. "}}).encode()
            self.send_response(200); self.end_headers(); self.wfile.write(out)
        def log_message(self, *a): pass
    srv = HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.handle_request, daemon=True).start()
    assert Ollama(url=f"http://127.0.0.1:{srv.server_port}").chat([{"role": "user", "content": "hi"}]) == "ok [S1]."
