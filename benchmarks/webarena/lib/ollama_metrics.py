#!/usr/bin/env python3
"""
benchmarks/webarena/lib/ollama_metrics.py

Lightweight Ollama inference-metrics collecting HTTP proxy.

Intercepts /v1/chat/completions requests intended for Ollama and
translates them to Ollama's native /api/chat endpoint, which returns
detailed per-request timing statistics:

    eval_count           — tokens generated
    eval_duration        — generation time (nanoseconds)
    prompt_eval_count    — prompt tokens processed
    prompt_eval_duration — prompt processing time (nanoseconds)
    total_duration       — end-to-end request time (nanoseconds)
    load_duration        — model-load overhead (nanoseconds)

From these the proxy computes:
    prompt_eval_rate_tok_s  — prompt throughput (tokens/sec)
    generation_rate_tok_s   — generation throughput (tokens/sec)
    time_to_first_token_ms  — TTFT = load_duration + prompt_eval_duration

All other paths (/v1/models, /api/tags, etc.) are forwarded transparently.

Usage:
    proxy = OllamaMetricsProxy(ollama_port=11434, proxy_port=11435)
    started = proxy.start()
    if started:
        # Point WebArena at proxy_port instead of ollama_port
        ...
        metrics = proxy.get_aggregate_metrics()
        per_req = proxy.get_per_request_metrics()
    proxy.stop()
"""

import json
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Dict, List, Optional

# CPU-only inference of large models (e.g. llama3.1:70b on 576 cores) can easily
# take 30+ minutes per request; 2 hours gives ample headroom without hanging forever.
INFERENCE_TIMEOUT_S = 7200

# CRITICAL: this proxy always talks to localhost (Ollama on ollama_port), but
# urllib.request.urlopen() honors HTTP_PROXY/HTTPS_PROXY from THIS process's
# own os.environ by default (unlike the child WebArena subprocess, whose env
# dict is explicitly sanitized in run.py). If the shell that launched run.py
# had a corporate proxy exported (e.g. left over from `ollama pull` proxy
# troubleshooting), every forwarded request here would get routed through it
# and rejected with an HTTP 403 "incorrect proxy service was requested" from
# the corporate proxy — even though the destination is 127.0.0.1. Use an
# explicit no-proxy opener for all internal localhost forwarding.
_NO_PROXY_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


class OllamaMetricsProxy:
    """HTTP proxy that captures per-request Ollama inference timing.

    Intercepts POST /v1/chat/completions, re-issues the request to
    Ollama's native /api/chat (which includes full timing fields in the
    response), records per-request metrics, and returns a standard
    OpenAI-compatible response to the caller.

    All other endpoints are forwarded transparently to Ollama.
    """

    def __init__(self, ollama_port: int = 11434, proxy_port: int = 11435) -> None:
        self.ollama_port = ollama_port
        self.proxy_port = proxy_port
        self._metrics: List[Dict] = []
        self._lock = threading.Lock()
        self._current_task_idx: Optional[int] = None
        self._server: Optional[HTTPServer] = None
        self._thread: Optional[threading.Thread] = None

    # ── Public API ────────────────────────────────────────────────────────────

    def start(self) -> bool:
        """Start the proxy server in a daemon thread.

        Returns True if the server bound successfully, False otherwise.
        A False return means the caller should fall back to using Ollama directly.
        """
        proxy = self  # captured by inner class

        class _Handler(BaseHTTPRequestHandler):
            def log_message(self, fmt, *args):  # suppress per-request access logs
                pass

            # ── POST handler ─────────────────────────────────────────────────
            def do_POST(self):
                content_len = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(content_len)

                if self.path.rstrip("/") in ("/v1/chat/completions",
                                             "/v1/chat/completions/"):
                    self._handle_chat(body)
                else:
                    self._forward(body)

            # ── GET handler ──────────────────────────────────────────────────
            def do_GET(self):
                if self.path == "/metrics":
                    data = proxy.get_aggregate_metrics()
                    resp = json.dumps(data).encode()
                    self._send_json(200, resp)
                else:
                    self._forward(b"")

            # ── /v1/chat/completions → /api/chat ─────────────────────────────
            def _handle_chat(self, body: bytes) -> None:
                """Translate OpenAI-compat request → Ollama native, capture timing."""
                try:
                    req_data = json.loads(body)
                except Exception:
                    req_data = {}

                # Build Ollama native /api/chat request
                native_req: Dict = {
                    "model": req_data.get("model", ""),
                    "messages": req_data.get("messages", []),
                    "stream": False,
                    "options": {},
                }
                if "temperature" in req_data:
                    native_req["options"]["temperature"] = req_data["temperature"]
                if "max_tokens" in req_data:
                    native_req["options"]["num_predict"] = req_data["max_tokens"]
                # Pass through any additional options
                for k in ("top_p", "top_k", "seed"):
                    if k in req_data:
                        native_req["options"][k] = req_data[k]
                if not native_req["options"]:
                    del native_req["options"]

                t0 = time.time()
                try:
                    native_url = f"http://localhost:{proxy.ollama_port}/api/chat"
                    req_obj = urllib.request.Request(
                        native_url,
                        data=json.dumps(native_req).encode(),
                        headers={"Content-Type": "application/json"},
                        method="POST",
                    )
                    with _NO_PROXY_OPENER.open(req_obj, timeout=INFERENCE_TIMEOUT_S) as r:
                        resp_body = r.read()
                    wall_time_s = time.time() - t0
                    native_resp = json.loads(resp_body)
                except Exception:
                    # If native translation fails, forward the original request
                    # transparently (graceful degradation — no metrics captured).
                    self._forward(body)
                    return

                # ── Record per-request metrics ────────────────────────────────
                eval_count        = int(native_resp.get("eval_count",        0) or 0)
                eval_dur_ns       = int(native_resp.get("eval_duration",      0) or 0)
                prompt_eval_count = int(native_resp.get("prompt_eval_count",  0) or 0)
                prompt_eval_dur_ns = int(native_resp.get("prompt_eval_duration", 0) or 0)
                total_dur_ns      = int(native_resp.get("total_duration",     0) or 0)
                load_dur_ns       = int(native_resp.get("load_duration",      0) or 0)

                gen_tok_s    = (eval_count / (eval_dur_ns / 1e9)
                                if eval_dur_ns > 0 else 0.0)
                prompt_tok_s = (prompt_eval_count / (prompt_eval_dur_ns / 1e9)
                                if prompt_eval_dur_ns > 0 else 0.0)
                # TTFT = time from sending prompt to receiving the first generated token
                # = load_duration + prompt_eval_duration
                ttft_ms = (load_dur_ns + prompt_eval_dur_ns) / 1e6

                infer_s = (total_dur_ns / 1e9
                           if total_dur_ns > 0 else round(wall_time_s, 2))

                proxy._record({
                    "prompt_tokens":           prompt_eval_count,
                    "completion_tokens":       eval_count,
                    "prompt_eval_rate_tok_s":  round(prompt_tok_s, 2),
                    "generation_rate_tok_s":   round(gen_tok_s, 2),
                    "time_to_first_token_ms":  round(ttft_ms, 1),
                    "inference_time_s":        round(infer_s, 2),
                    "wall_time_s":             round(wall_time_s, 2),
                })

                # ── Build OpenAI-compatible response ─────────────────────────
                msg_content = (native_resp.get("message") or {}).get("content", "")
                openai_resp = {
                    "id":      f"chatcmpl-proxy-{int(time.time())}",
                    "object":  "chat.completion",
                    "created": int(time.time()),
                    "model":   native_resp.get("model", native_req["model"]),
                    "choices": [
                        {
                            "index":         0,
                            "message":       {"role": "assistant", "content": msg_content},
                            "finish_reason": native_resp.get("done_reason", "stop"),
                        }
                    ],
                    "usage": {
                        "prompt_tokens":     prompt_eval_count,
                        "completion_tokens": eval_count,
                        "total_tokens":      prompt_eval_count + eval_count,
                    },
                }
                self._send_json(200, json.dumps(openai_resp).encode())

            # ── Transparent forward ───────────────────────────────────────────
            def _forward(self, body: bytes) -> None:
                """Forward the request unchanged to Ollama and relay the response."""
                try:
                    fwd_url = f"http://localhost:{proxy.ollama_port}{self.path}"
                    # Preserve relevant headers; drop hop-by-hop headers
                    fwd_headers = {
                        k: v for k, v in self.headers.items()
                        if k.lower() not in ("host", "content-length",
                                             "transfer-encoding", "connection")
                    }
                    req_obj = urllib.request.Request(
                        fwd_url,
                        data=body if body else None,
                        headers=fwd_headers,
                        method=self.command,
                    )
                    if body:
                        req_obj.add_header("Content-Length", str(len(body)))
                    with _NO_PROXY_OPENER.open(req_obj, timeout=INFERENCE_TIMEOUT_S) as r:
                        resp_body = r.read()
                        status = r.status
                    self._send_json(status, resp_body)
                except urllib.error.HTTPError as e:
                    resp_body = e.read()
                    self._send_json(e.code, resp_body)
                except Exception as e:
                    msg = json.dumps({"error": str(e)}).encode()
                    self._send_json(502, msg)

            # ── Helpers ───────────────────────────────────────────────────────
            def _send_json(self, status: int, body: bytes) -> None:
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        try:
            self._server = HTTPServer(("127.0.0.1", self.proxy_port), _Handler)
            self._thread = threading.Thread(
                target=self._server.serve_forever, daemon=True, name="ollama-metrics-proxy"
            )
            self._thread.start()
            return True
        except OSError as e:
            print(f"[ollama-proxy] Failed to bind port {self.proxy_port}: {e} — metrics disabled")
            return False

    def stop(self) -> None:
        """Shut down the proxy server."""
        if self._server is not None:
            self._server.shutdown()
            self._server = None

    def set_current_task(self, task_idx: int) -> None:
        """Tag subsequent inference requests with task_idx."""
        with self._lock:
            self._current_task_idx = task_idx

    def clear_current_task(self) -> None:
        """Clear the current task tag (called between tasks)."""
        with self._lock:
            self._current_task_idx = None

    def get_per_task_metrics(self) -> Dict[int, List[Dict]]:
        """Return per-request metrics grouped by task_idx.

        Requests recorded outside a task boundary (task_idx is None) are
        stored under key -1.
        """
        with self._lock:
            records = list(self._metrics)

        grouped: Dict[int, List[Dict]] = {}
        for r in records:
            idx = r.get("task_idx")
            if idx is None:
                idx = -1
            grouped.setdefault(idx, []).append(r)
        return grouped

    def get_aggregate_metrics(self) -> Dict:
        """Return aggregate inference metrics across all recorded requests.

        All rate fields are "N/A" if no requests were recorded (graceful
        degradation when the proxy was not used or Ollama is unreachable).
        """
        with self._lock:
            records = list(self._metrics)

        if not records:
            return {
                "avg_prompt_eval_tok_s":   "N/A",
                "avg_generation_tok_s":    "N/A",
                "avg_ttft_ms":             "N/A",
                "total_prompt_tokens":     0,
                "total_completion_tokens": 0,
                "total_inference_time_s":  0.0,
                "num_llm_requests":        0,
            }

        total_prompt     = sum(r["prompt_tokens"]      for r in records)
        total_completion = sum(r["completion_tokens"]  for r in records)
        total_infer      = sum(r["inference_time_s"]   for r in records)

        prompt_rates = [r["prompt_eval_rate_tok_s"]  for r in records
                        if r["prompt_eval_rate_tok_s"] > 0]
        gen_rates    = [r["generation_rate_tok_s"]   for r in records
                        if r["generation_rate_tok_s"] > 0]
        ttfts        = [r["time_to_first_token_ms"]  for r in records
                        if r["time_to_first_token_ms"] > 0]

        def _avg(lst):
            return round(sum(lst) / len(lst), 1) if lst else "N/A"

        return {
            "avg_prompt_eval_tok_s":   _avg(prompt_rates),
            "avg_generation_tok_s":    _avg(gen_rates),
            "avg_ttft_ms":             _avg(ttfts),
            "total_prompt_tokens":     total_prompt,
            "total_completion_tokens": total_completion,
            "total_inference_time_s":  round(total_infer, 1),
            "num_llm_requests":        len(records),
        }

    def get_per_request_metrics(self) -> List[Dict]:
        """Return a copy of the per-request metrics list."""
        with self._lock:
            return list(self._metrics)

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _record(self, m: Dict) -> None:
        with self._lock:
            m["task_idx"] = self._current_task_idx
            self._metrics.append(m)
