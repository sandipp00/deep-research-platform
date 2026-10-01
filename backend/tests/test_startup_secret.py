import os
import subprocess
import sys

import pytest

from app.config import INSECURE_DEFAULT_JWT_SECRET, InsecureConfigError, Settings
from conftest import BACKEND_DIR


def _import_app(tmp_path, jwt_secret: str | None) -> subprocess.CompletedProcess:
    env = {k: v for k, v in os.environ.items() if k != "JWT_SECRET"}
    env["PYTHONPATH"] = str(BACKEND_DIR)
    if jwt_secret is not None:
        env["JWT_SECRET"] = jwt_secret
    return subprocess.run(
        [sys.executable, "-c", "import app.main"],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )


@pytest.mark.parametrize("secret", [None, "", "   ", INSECURE_DEFAULT_JWT_SECRET, "change-me"])
def test_app_refuses_to_start_with_missing_or_default_secret(tmp_path, secret):
    proc = _import_app(tmp_path, secret)
    assert proc.returncode != 0
    assert "InsecureConfigError" in proc.stderr
    assert "JWT_SECRET" in proc.stderr


def test_app_imports_with_real_secret(tmp_path):
    proc = _import_app(tmp_path, "a-real-secret-value-that-is-long-enough-1234567890")
    assert proc.returncode == 0, proc.stderr


def test_settings_ensure_secure_unit():
    with pytest.raises(InsecureConfigError):
        Settings(_env_file=None, jwt_secret=INSECURE_DEFAULT_JWT_SECRET).ensure_secure()
    with pytest.raises(InsecureConfigError):
        Settings(_env_file=None, jwt_secret="").ensure_secure()
    Settings(_env_file=None, jwt_secret="x" * 48).ensure_secure()
