"""Run manifest (doc 01 §8): what a run was, so ``voss repro`` can redo it and check the result hash."""

from __future__ import annotations

import json
import platform
import subprocess
from dataclasses import asdict, dataclass, field
from importlib import metadata
from pathlib import Path
from typing import Any

from voss.core.config import RunConfig
from voss.core.hashing import hash_dir

_PKGS = ("numpy", "scipy", "pandas", "pyarrow", "pydantic")


@dataclass
class Manifest:
    git_sha: str
    git_dirty: bool
    config: dict[str, Any]
    config_hash: str
    scenario_hash: str | None
    calibration_hash: str | None
    seed: int
    clock_mode: str
    result_hash: str
    versions: dict[str, str] = field(default_factory=dict)

    def write(self, path: Path) -> None:
        path.write_text(json.dumps(asdict(self), indent=2, sort_keys=True))

    @staticmethod
    def read(path: Path) -> Manifest:
        return Manifest(**json.loads(path.read_text()))


def git_state(repo: Path) -> tuple[str, bool]:
    """``(sha, dirty)``; ``("unknown", True)`` outside a git checkout."""
    try:
        sha = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True, text=True, check=True
        ).stdout.strip()
        status = subprocess.run(
            ["git", "status", "--porcelain"], cwd=repo, capture_output=True, text=True, check=True
        ).stdout
    except (OSError, subprocess.CalledProcessError):
        return "unknown", True
    return sha, bool(status.strip())


def versions() -> dict[str, str]:
    out = {"python": platform.python_version()}
    for pkg in _PKGS:
        try:
            out[pkg] = metadata.version(pkg)
        except metadata.PackageNotFoundError:
            out[pkg] = "missing"
    return out


def calibration_hash(cfg: RunConfig) -> str | None:
    if cfg.calibration is None:
        return None
    path = Path(cfg.calibration)
    return hash_dir(path) if path.is_dir() else None


def build_manifest(cfg: RunConfig, scenario_hash: str | None, result_hash: str, repo: Path) -> Manifest:
    sha, dirty = git_state(repo)
    return Manifest(
        git_sha=sha,
        git_dirty=dirty,
        config=cfg.model_dump(mode="json"),
        config_hash=cfg.config_hash(),
        scenario_hash=scenario_hash,
        calibration_hash=calibration_hash(cfg),
        seed=cfg.seed,
        clock_mode=cfg.decision_clock.mode,
        result_hash=result_hash,
        versions=versions(),
    )
