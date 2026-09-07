import importlib.util
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


SRC_DIR = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC_DIR))

from collectors.tdx_env import DEFAULT_ENV_PATH, load_dotenv  # noqa: E402


class TestTdxEnv(unittest.TestCase):
    def test_collectors_env_loader_is_available(self):
        self.assertIsNotNone(importlib.util.find_spec("collectors.tdx_env"))

    def test_loads_env_file_and_preserves_existing_environment(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            env_path = Path(temp_dir) / ".env"
            env_path.write_text(
                "export TDX_CLIENT_ID=from-file\n"
                "TDX_CLIENT_SECRET='quoted-secret'\n",
                encoding="utf-8",
            )
            with patch.dict(
                os.environ,
                {"TDX_CLIENT_ID": "from-shell"},
                clear=False,
            ):
                os.environ.pop("TDX_CLIENT_SECRET", None)
                load_dotenv(env_path)

                self.assertEqual(os.environ["TDX_CLIENT_ID"], "from-shell")
                self.assertEqual(os.environ["TDX_CLIENT_SECRET"], "quoted-secret")

    def test_default_env_file_is_next_to_collectors(self):
        self.assertEqual(DEFAULT_ENV_PATH, SRC_DIR / "collectors" / ".env")


if __name__ == "__main__":
    unittest.main()
