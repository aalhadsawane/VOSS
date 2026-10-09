"""SeBS 504.dna-visualisation: squiggle transform of a DNA sequence."""

from __future__ import annotations

import os

from squiggle import transform


def make_input(size_kb: int) -> str:
    return "".join("ACGT"[b & 3] for b in os.urandom(size_kb * 1024))


def handler(seq: str) -> int:
    x, _ = transform(seq)
    return len(x)
