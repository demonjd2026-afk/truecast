"""Proves the Azure AI Foundry HTTP path works, without a real Azure account.

A tiny mock server mimics the Azure OpenAI chat-completions response. We point
the FoundryNarrator at it and assert it calls the endpoint and returns the
model's line; we also assert it degrades to the offline narrator when the
endpoint is unreachable, which is the live-feed resilience guarantee.
"""

import json
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

# Never route localhost through an outbound proxy during the test.
os.environ["NO_PROXY"] = "*"
os.environ["no_proxy"] = "*"

from truecast.llm.foundry import FoundryNarrator
from truecast.llm.provider import NarrativeRequest, PersonaSpec
from truecast.models import Fact

MODEL_LINE = "Kai Enright buries it for Kingsmoor City — what a finish."


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):  # silence
        pass

    def do_POST(self):
        length = int(self.headers.get("content-length", 0))
        _ = self.rfile.read(length)
        body = {
            "choices": [{"message": {"role": "assistant", "content": MODEL_LINE}}]
        }
        payload = json.dumps(body).encode()
        self.send_response(200)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


@pytest.fixture()
def mock_server():
    srv = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    host, port = srv.server_address
    yield f"http://{host}:{port}"
    srv.shutdown()


def _request() -> NarrativeRequest:
    fact = Fact(
        fact_id="f1", kind="goal", subject_team="KGS", subject_player="KGS_7",
        clock_label="04:55", text="Kai Enright scored for Kingsmoor City at 04:55.",
        evidence=["e00147"],
        data={"scorer": "Kai Enright", "team": "Kingsmoor City",
              "score_home": 1, "score_away": 0, "xg": 0.49},
    )
    persona = PersonaSpec(key="analyst", label="Analyst", tone="precise")
    return NarrativeRequest(fact=fact, numbers={"xg": 0.49}, persona=persona,
                            score_line="KGS 1-0 STB")


def test_foundry_http_path(mock_server):
    nar = FoundryNarrator(endpoint=mock_server, api_key="k", deployment="d")
    out = nar.narrate(_request())
    assert out == MODEL_LINE


def test_foundry_health_ok(mock_server):
    nar = FoundryNarrator(endpoint=mock_server, api_key="k", deployment="d")
    h = nar.health()
    assert h["ok"] is True and h["mode"] == "foundry"


def test_foundry_falls_back_when_unreachable():
    # Nothing listening here -> must not raise, must return an offline line.
    nar = FoundryNarrator(endpoint="http://127.0.0.1:1", api_key="k",
                          deployment="d", timeout=0.3)
    out = nar.narrate(_request())
    assert out and out != MODEL_LINE
    assert "Kai Enright" in out  # the grounded offline line still names the scorer


def test_health_without_creds_is_offline():
    nar = FoundryNarrator(endpoint="", api_key="", deployment="d")
    h = nar.health()
    assert h["ok"] is False and h["mode"] == "offline"
