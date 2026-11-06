"""Cookies opcionales y clientes de yt-dlp, sin red ni cookies reales."""

from __future__ import annotations

import logging
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.config import cookies_file, youtube_player_clients
from app.pipeline.download import _ytdlp_base_opts, _youtube_error
from app.pipeline.errors import PipelineError


class CookiesFileTests(unittest.TestCase):
    def test_unset_and_no_secret_file(self) -> None:
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("COOKIES_FILE", None)
            with patch.object(Path, "is_file", return_value=False):
                self.assertIsNone(cookies_file())

    def test_default_secret_path_when_it_exists(self) -> None:
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("COOKIES_FILE", None)

            def is_file(self: Path) -> bool:
                return self == Path("/etc/secrets/cookies.txt")

            with patch.object(Path, "is_file", is_file):
                self.assertEqual(cookies_file(), Path("/etc/secrets/cookies.txt"))

    def test_explicit_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "cookies.txt"
            path.write_text("# Netscape HTTP Cookie File\n", encoding="utf-8")
            with patch.dict(os.environ, {"COOKIES_FILE": str(path)}):
                self.assertEqual(cookies_file(), path)

    def test_explicit_missing_does_not_fall_back(self) -> None:
        missing = "/tmp/viral-clip-cookies-que-no-existen.txt"
        self.assertFalse(Path(missing).exists())
        with patch.dict(os.environ, {"COOKIES_FILE": missing}):
            with self.assertLogs("app.config", level="WARNING") as captured:
                self.assertIsNone(cookies_file())
        joined = "\n".join(captured.output)
        self.assertIn(missing, joined)
        self.assertNotIn("Netscape", joined)

    def test_blank_env_uses_default_rule(self) -> None:
        with patch.dict(os.environ, {"COOKIES_FILE": "   "}):
            with patch.object(Path, "is_file", return_value=False):
                self.assertIsNone(cookies_file())


class PlayerClientTests(unittest.TestCase):
    def test_unset(self) -> None:
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("YOUTUBE_PLAYER_CLIENTS", None)
            self.assertIsNone(youtube_player_clients())

    def test_comma_separated(self) -> None:
        with patch.dict(os.environ, {"YOUTUBE_PLAYER_CLIENTS": " web, android ,,"}):
            self.assertEqual(youtube_player_clients(), ["web", "android"])


class YoutubeDLOptsTests(unittest.TestCase):
    def test_cookiefile_and_no_forced_client(self) -> None:
        secret = "SESSION_SECRET_VALUE_DO_NOT_LEAK"
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "cookies.txt"
            path.write_text(
                "# Netscape HTTP Cookie File\n"
                f".youtube.com\tTRUE\t/\tTRUE\t0\tSID\t{secret}\n",
                encoding="utf-8",
            )
            env = {"COOKIES_FILE": str(path), "YOUTUBE_PLAYER_CLIENTS": ""}
            with patch.dict(os.environ, env):
                with self.assertLogs("app.pipeline.download", level="INFO") as captured:
                    opts = _ytdlp_base_opts()
        self.assertEqual(opts["cookiefile"], str(path))
        self.assertNotIn("extractor_args", opts)
        joined = "\n".join(captured.output)
        self.assertIn(f"cookiefile={path}", joined)
        self.assertNotIn(secret, joined)
        self.assertNotIn("android", joined)

    def test_optional_player_clients(self) -> None:
        with patch.dict(
            os.environ,
            {"YOUTUBE_PLAYER_CLIENTS": "tv_embedded,web", "COOKIES_FILE": ""},
        ):
            with patch.object(Path, "is_file", return_value=False):
                opts = _ytdlp_base_opts()
        self.assertNotIn("cookiefile", opts)
        self.assertEqual(
            opts["extractor_args"],
            {"youtube": {"player_client": ["tv_embedded", "web"]}},
        )

    def test_download_source_does_not_hardcode_android_web(self) -> None:
        source = Path(__file__).resolve().parents[1] / "app" / "pipeline" / "download.py"
        text = source.read_text(encoding="utf-8")
        self.assertNotIn('["android", "web"]', text)
        self.assertIn("cookiefile", text)
        self.assertIn("_FORMAT_TRIES", text)

    def test_bot_error_mentions_three_ways_out(self) -> None:
        err = _youtube_error(
            Exception("Sign in to confirm you’re not a bot"),
            "La descarga falló",
        )
        self.assertIsInstance(err, PipelineError)
        text = str(err)
        self.assertIn("Probar con video de muestra", text)
        self.assertIn("COOKIES_FILE", text)
        self.assertIn("cookies.txt", text)
        self.assertIn("PC de casa", text)

    def test_other_errors_keep_the_phase(self) -> None:
        err = _youtube_error(Exception("HTTP Error 403: Forbidden"), "La descarga falló")
        self.assertIn("La descarga falló", str(err))
        self.assertNotIn("COOKIES_FILE", str(err))


if __name__ == "__main__":
    logging.basicConfig(level="DEBUG")
    unittest.main()
