from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from wellpass_sync.app_paths import ensure_default_env_file
from wellpass_sync.config import MICROSOFT_GRAPH_COMMAND_LINE_TOOLS_CLIENT_ID, load_config


class ConfigTests(unittest.TestCase):
    def test_runtime_paths_default_to_env_directory(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            env_path = Path(temp_dir) / ".env"
            env_path.write_text("", encoding="utf-8")
            base_dir = Path(temp_dir).resolve()

            config = load_config(env_path)

            self.assertEqual(config.database_path, base_dir / "data" / "wellpass-sync.sqlite")
            self.assertEqual(config.graph_token_cache, base_dir / "data" / "graph-token-cache.json")
            self.assertEqual(config.google_client_secrets_path, base_dir / "google-oauth-client.json")
            self.assertEqual(config.google_token_cache, base_dir / "data" / "google-token-cache.json")
            self.assertEqual(config.ics_export_dir, base_dir / "exports")

    def test_relative_runtime_paths_resolve_against_env_directory(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            env_path = Path(temp_dir) / ".env"
            env_path.write_text(
                "\n".join(
                    [
                        "DATABASE_PATH=state\\sync.sqlite",
                        "GRAPH_TOKEN_CACHE=state\\graph.json",
                        "GOOGLE_CLIENT_SECRETS_PATH=oauth\\client.json",
                        "GOOGLE_TOKEN_CACHE=state\\google.json",
                        "ICS_EXPORT_DIR=calendar-export",
                    ]
                ),
                encoding="utf-8",
            )
            base_dir = Path(temp_dir).resolve()

            config = load_config(env_path)

            self.assertEqual(config.database_path, base_dir / "state" / "sync.sqlite")
            self.assertEqual(config.graph_token_cache, base_dir / "state" / "graph.json")
            self.assertEqual(config.google_client_secrets_path, base_dir / "oauth" / "client.json")
            self.assertEqual(config.google_token_cache, base_dir / "state" / "google.json")
            self.assertEqual(config.ics_export_dir, base_dir / "calendar-export")

    def test_imap_host_can_be_inferred_from_common_domains(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            env_path = Path(temp_dir) / ".env"
            env_path.write_text("EMAIL_PROVIDER=imap\nIMAP_USERNAME=person@gmail.com\n", encoding="utf-8")

            config = load_config(env_path)

            self.assertEqual(config.imap_host, "imap.gmail.com")

    def test_imap_preset_overrides_domain_inference(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            env_path = Path(temp_dir) / ".env"
            env_path.write_text(
                "EMAIL_PROVIDER=imap\nIMAP_PROVIDER=icloud\nIMAP_USERNAME=person@example.com\n",
                encoding="utf-8",
            )

            config = load_config(env_path)

            self.assertEqual(config.imap_host, "imap.mail.me.com")

    def test_blank_graph_client_id_uses_builtin_default(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            env_path = Path(temp_dir) / ".env"
            env_path.write_text("GRAPH_CLIENT_ID=\n", encoding="utf-8")

            config = load_config(env_path)

            self.assertEqual(config.graph_client_id, MICROSOFT_GRAPH_COMMAND_LINE_TOOLS_CLIENT_ID)

    def test_first_run_env_file_is_created_for_gui(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            env_path = Path(temp_dir) / "app" / ".env"
            base_dir = env_path.parent.resolve()

            created = ensure_default_env_file(env_path)

            self.assertEqual(created, env_path)
            self.assertTrue(env_path.exists())
            config = load_config(env_path)
            self.assertEqual(config.email_provider, "graph")
            self.assertEqual(config.database_path, base_dir / "data" / "wellpass-sync.sqlite")


if __name__ == "__main__":
    unittest.main()
