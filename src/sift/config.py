"""Configuration loading for Sift.

Loads non-secret settings from config/config.yaml and secrets from .env.
Keep this the single source of truth for configuration so modules never read
environment variables directly.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = PROJECT_ROOT / "config" / "config.yaml"


@dataclass(frozen=True)
class Settings:
    """Resolved settings combining config.yaml and .env."""

    raw: dict[str, Any]
    use_s3: bool
    s3_bucket: str | None
    local_data_dir: Path
    random_seed: int

    def get(self, *keys: str, default: Any = None) -> Any:
        """Nested lookup into the yaml config, e.g. settings.get('model', 'baseline')."""
        node: Any = self.raw
        for key in keys:
            if not isinstance(node, dict) or key not in node:
                return default
            node = node[key]
        return node


def _as_bool(value: str | None, default: bool) -> bool:
    """Parse a truthy string from the environment."""
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def load_settings() -> Settings:
    """Load and merge config.yaml + .env into a Settings object.

    Non-secret defaults come from ``config/config.yaml``; secrets and
    environment-specific overrides come from ``.env`` (loaded into the process
    environment). This is the single place allowed to read environment
    variables, so the rest of the codebase depends only on the returned
    ``Settings`` object. (PRD FR-1.2)
    """
    load_dotenv(PROJECT_ROOT / ".env")

    with CONFIG_PATH.open("r", encoding="utf-8") as handle:
        raw: dict[str, Any] = yaml.safe_load(handle) or {}

    use_s3 = _as_bool(os.environ.get("USE_S3"), default=True)
    s3_bucket = os.environ.get("S3_BUCKET") or None

    local_data_dir_env = os.environ.get("LOCAL_DATA_DIR")
    local_data_dir = (
        Path(local_data_dir_env).expanduser()
        if local_data_dir_env
        else PROJECT_ROOT / "data"
    )

    seed_default = raw.get("project", {}).get("random_seed", 42)
    random_seed = int(os.environ.get("RANDOM_SEED", seed_default))

    return Settings(
        raw=raw,
        use_s3=use_s3,
        s3_bucket=s3_bucket,
        local_data_dir=local_data_dir,
        random_seed=random_seed,
    )
