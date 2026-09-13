#!/usr/bin/env python3
"""Tests des V16-Transports: Direktpfade ohne den lokalen YesMem-Proxy.

Bewusst als Guard-Tests formuliert:

- Default-Target ist ``proxy`` (rueckwaerts-kompatibel zu V11-V15; der lokale
  Proxy bleibt die Vorgabe, Direkt-Transporte sind explizit).
- ``BEMYSELF_TARGET=deepseek|cluster`` loest Endpoint, Modell und
  Key-Eintrag der Ziel-Tabelle auf; ``BEMYSELF_PROXY_URL`` gilt weiter fuer
  Target ``proxy``.
- Ein unbekanntes Target bricht mit SystemExit ab (ein Tippfehler darf nicht
  still als Proxy laufen).
- ``BEMYSELF_MAX_TOKENS``/``BEMYSELF_REASONING_EFFORT`` steuern den
  Request-Body; ``call_model`` sendet Modell und URL des gewaehlten Targets.
- Kein Key-Wert erscheint in Fehlermeldungen oder im Lauf-Manifest.
"""

from __future__ import annotations

import importlib.util
import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
TOOLING = ROOT / "yesdocs" / "deepseek-math-notation" / "tooling"

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(TOOLING) not in sys.path:
    sys.path.insert(0, str(TOOLING))


def _load(name):
    spec = importlib.util.spec_from_file_location(name, TOOLING / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


harness = _load("harness")

_PROXY_URL = "http://localhost:9099/v1/chat/completions"
_DEEPSEEK_URL = "https://api.deepseek.com/v1/chat/completions"
_CLUSTER_URL = "https://llm.ccm19.app/v1/chat/completions"
_TEST_DEEPSEEK_KEY = "test-deepseek-key-value"
_TEST_GATEWAY_KEY = "test-gateway-key-value"


class _TransportEnvTest(unittest.TestCase):
    """Gemeinsame Klammer: ENV und AUTH_PATH sind je Test isoliert."""

    ENV_KEYS = (
        "BEMYSELF_TARGET",
        "BEMYSELF_PROXY_URL",
        "BEMYSELF_MAX_TOKENS",
        "BEMYSELF_REASONING_EFFORT",
    )

    def setUp(self):
        self._saved_env = dict(os.environ)
        for key in self.ENV_KEYS:
            os.environ.pop(key, None)
        self._auth_dir = Path(tempfile.mkdtemp(dir=self._tmp_root()))
        self.addCleanup(shutil.rmtree, self._auth_dir, ignore_errors=True)
        self.auth_path = self._auth_dir / "auth.json"
        self.write_auth({"deepseek": {"key": _TEST_DEEPSEEK_KEY}, "gateway": {"key": _TEST_GATEWAY_KEY}})
        self._saved_auth_path = harness.AUTH_PATH
        harness.AUTH_PATH = str(self.auth_path)

    def tearDown(self):
        harness.AUTH_PATH = self._saved_auth_path
        os.environ.clear()
        os.environ.update(self._saved_env)

    def _tmp_root(self):
        tmp_root = ROOT / ".yesmem" / "tmp"
        tmp_root.mkdir(parents=True, exist_ok=True)
        return tmp_root

    def write_auth(self, payload):
        self.auth_path.write_text(json.dumps(payload), encoding="utf-8")


class TargetResolutionTest(_TransportEnvTest):
    def test_default_target_is_the_local_proxy(self):
        self.assertEqual(harness.target_name(), "proxy")
        cfg = harness.target_config()
        self.assertEqual(cfg["url"], _PROXY_URL)
        self.assertEqual(cfg["model"], "deepseek-flash")

    def test_proxy_url_env_still_routes_the_proxy_target(self):
        os.environ["BEMYSELF_PROXY_URL"] = "http://127.0.0.1:9999/v1/chat/completions"
        self.assertEqual(harness.target_config()["url"], "http://127.0.0.1:9999/v1/chat/completions")

    def test_proxy_url_env_does_not_leak_into_other_targets(self):
        os.environ["BEMYSELF_PROXY_URL"] = "http://127.0.0.1:9999/v1/chat/completions"
        os.environ["BEMYSELF_TARGET"] = "deepseek"
        self.assertEqual(harness.target_config()["url"], _DEEPSEEK_URL)

    def test_deepseek_target_endpoint_and_model(self):
        os.environ["BEMYSELF_TARGET"] = "deepseek"
        cfg = harness.target_config()
        self.assertEqual(cfg["url"], _DEEPSEEK_URL)
        self.assertEqual(cfg["model"], "deepseek-flash")

    def test_cluster_target_endpoint_and_model(self):
        os.environ["BEMYSELF_TARGET"] = "cluster"
        cfg = harness.target_config()
        self.assertEqual(cfg["url"], _CLUSTER_URL)
        self.assertEqual(cfg["model"], "privateTomMax")

    def test_target_name_is_case_insensitive(self):
        os.environ["BEMYSELF_TARGET"] = " DeepSeek "
        self.assertEqual(harness.target_name(), "deepseek")

    def test_unknown_target_aborts(self):
        os.environ["BEMYSELF_TARGET"] = "bogus"
        with self.assertRaises(SystemExit):
            harness.target_config()


class ApiKeyTest(_TransportEnvTest):
    def test_key_entry_follows_the_target(self):
        self.assertEqual(harness._api_key(), _TEST_DEEPSEEK_KEY)
        os.environ["BEMYSELF_TARGET"] = "deepseek"
        self.assertEqual(harness._api_key(), _TEST_DEEPSEEK_KEY)
        os.environ["BEMYSELF_TARGET"] = "cluster"
        self.assertEqual(harness._api_key(), _TEST_GATEWAY_KEY)

    def test_missing_key_error_leaks_no_secret(self):
        self.write_auth({"deepseek": {"key": _TEST_DEEPSEEK_KEY}})
        os.environ["BEMYSELF_TARGET"] = "cluster"
        with self.assertRaises(SystemExit) as caught:
            harness._api_key()
        self.assertNotIn(_TEST_DEEPSEEK_KEY, str(caught.exception))
        self.assertNotIn("sk-", str(caught.exception))

    def test_unreadable_auth_error_leaks_no_secret(self):
        harness.AUTH_PATH = str(self.auth_path) + ".missing"
        with self.assertRaises(SystemExit) as caught:
            harness._api_key()
        self.assertNotIn(_TEST_DEEPSEEK_KEY, str(caught.exception))


class _FakeUrlopen:
    """Records the outgoing request; returns a minimal well-formed response."""

    def __init__(self):
        self.requests = []

    def __call__(self, request, timeout=None):
        self.requests.append(request)
        payload = {
            "choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}],
            "usage": {},
        }

        class _Resp:
            def __enter__(self_):
                return self_

            def __exit__(self_, *args):
                return False

            def read(self_):
                return json.dumps(payload).encode("utf-8")

        return _Resp()


class CallModelBodyTest(_TransportEnvTest):
    def _call(self, messages=None):
        fake = _FakeUrlopen()
        with mock.patch("urllib.request.urlopen", fake):
            payload, _raw, _duration, error = harness.call_model(
                messages or [{"role": "user", "content": "hallo"}], 5.0
            )
        self.assertIsNone(error)
        self.assertEqual(payload["content"], "ok")
        return fake.requests[-1]

    def test_default_body_keeps_the_v15_shape(self):
        request = self._call()
        self.assertEqual(request.full_url, _PROXY_URL)
        body = json.loads(request.data.decode("utf-8"))
        self.assertEqual(body["model"], "deepseek-flash")
        self.assertEqual(body["max_tokens"], 8192)
        self.assertNotIn("reasoning_effort", body)

    def test_cluster_body_carries_model_and_overrides(self):
        os.environ["BEMYSELF_TARGET"] = "cluster"
        os.environ["BEMYSELF_MAX_TOKENS"] = "65536"
        os.environ["BEMYSELF_REASONING_EFFORT"] = "max"
        request = self._call()
        self.assertEqual(request.full_url, _CLUSTER_URL)
        body = json.loads(request.data.decode("utf-8"))
        self.assertEqual(body["model"], "privateTomMax")
        self.assertEqual(body["max_tokens"], 65536)
        self.assertEqual(body["reasoning_effort"], "max")
        self.assertEqual(request.headers["Authorization"], f"Bearer {_TEST_GATEWAY_KEY}")

    def test_deepseek_body_uses_the_deepseek_key(self):
        os.environ["BEMYSELF_TARGET"] = "deepseek"
        request = self._call()
        self.assertEqual(request.full_url, _DEEPSEEK_URL)
        self.assertEqual(request.headers["Authorization"], f"Bearer {_TEST_DEEPSEEK_KEY}")

    def test_invalid_max_tokens_aborts(self):
        os.environ["BEMYSELF_MAX_TOKENS"] = "viele"
        with self.assertRaises(SystemExit):
            harness.max_tokens()

    def test_blank_overrides_count_as_unset(self):
        os.environ["BEMYSELF_MAX_TOKENS"] = "  "
        os.environ["BEMYSELF_REASONING_EFFORT"] = ""
        self.assertEqual(harness.max_tokens(), 8192)
        self.assertEqual(harness.reasoning_effort(), "")


class ManifestTest(_TransportEnvTest):
    """Das Manifest belegt den Transport — ohne jemals den Key zu tragen."""

    def _root(self):
        tmp_root = ROOT / ".yesmem" / "tmp"
        tmp_root.mkdir(parents=True, exist_ok=True)
        root = Path(tempfile.mkdtemp(dir=tmp_root))
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        return root

    def _run_manifest(self, env):
        os.environ.update(env)
        original_select = harness._select_tasks
        original_runs = harness.RUNS_DIR
        runs_root_target = self._root()

        def fake_select(tier_a, tier_b, args):
            return []

        harness._select_tasks = fake_select
        harness.RUNS_DIR = runs_root_target
        try:
            code = harness.main(["batch", "--skip-warmup", "--task-ids", "A3-0001"])
        finally:
            harness._select_tasks = original_select
            harness.RUNS_DIR = original_runs
        self.assertEqual(code, 0)
        manifests = sorted(runs_root_target.glob("*/manifest.json"))
        self.assertTrue(manifests, "kein Manifest geschrieben")
        return manifests[-1]

    def test_manifest_records_target_without_key(self):
        manifest_path = self._run_manifest({"BEMYSELF_TARGET": "deepseek"})
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        self.assertEqual(manifest["transport"]["target"], "deepseek")
        self.assertEqual(manifest["transport"]["url"], _DEEPSEEK_URL)
        self.assertEqual(manifest["transport"]["model"], "deepseek-flash")
        self.assertEqual(manifest["model"], "deepseek-flash")
        text = json.dumps(manifest)
        self.assertNotIn(_TEST_DEEPSEEK_KEY, text)
        self.assertNotIn(_TEST_GATEWAY_KEY, text)
        self.assertNotIn("sk-", text)


if __name__ == "__main__":
    unittest.main()
