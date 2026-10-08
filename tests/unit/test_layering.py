"""import-linter must reject a policy → world import (doc 05 §2, D-05)."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def _lint(root: Path) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "PYTHONPATH": str(root)}
    lint = Path(sys.executable).with_name("lint-imports")
    return subprocess.run([str(lint)], cwd=root, env=env, capture_output=True, text=True, check=False)


def _copy(tmp: Path) -> Path:
    shutil.copytree(REPO / "voss", tmp / "voss", ignore=shutil.ignore_patterns("__pycache__"))
    shutil.copy(REPO / ".importlinter", tmp / ".importlinter")
    return tmp


def test_clean_tree_passes(tmp_path: Path) -> None:
    res = _lint(_copy(tmp_path))
    assert res.returncode == 0, res.stdout + res.stderr


def test_policy_importing_world_fails(tmp_path: Path) -> None:
    root = _copy(tmp_path)
    (root / "voss/policy/leak.py").write_text("import voss.world\n")
    res = _lint(root)
    assert res.returncode != 0
    assert "information boundary" in res.stdout and "BROKEN" in res.stdout


def test_actor_importing_actor_fails(tmp_path: Path) -> None:
    root = _copy(tmp_path)
    with (root / "voss/runtime/router.py").open("a") as f:
        f.write("import voss.runtime.worker_agent\n")
    res = _lint(root)
    assert res.returncode != 0
