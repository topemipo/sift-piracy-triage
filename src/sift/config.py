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


def load_settings() -> Settings:
    """Load and merge config.yaml + .env into a Settings object.

    TODO (PRD FR-1.2): implement.
      - load_dotenv()
      - read CONFIG_PATH yaml
      - resolve USE_S3, S3_BUCKET, LOCAL_DATA_DIR, RANDOM_SEED from env with sane defaults
    """
    raise NotImplementedError
