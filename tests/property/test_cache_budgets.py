"""Property: the cache never exceeds its tier budgets (doc 05 §7)."""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st
from voss.world.cache import WorkerCache

OPS = st.lists(
    st.tuples(
        st.sampled_from(["insert", "promote", "pin", "unpin", "remove", "warm", "take"]),
        st.integers(0, 12),
        st.floats(1, 120),
    ),
    max_size=60,
)


@settings(max_examples=200, deadline=None)
@given(ssd=st.floats(50, 300), hdd=st.floats(0, 400), mem=st.floats(100, 1000), ops=OPS)
def test_budgets_hold(ssd: float, hdd: float, mem: float, ops: list[tuple[str, int, float]]) -> None:
    c = WorkerCache(ssd, hdd, mem, hdd_tier=hdd > 0)
    for t, (op, key, size) in enumerate(ops):
        d = f"d{key}"
        if op == "insert":
            c.insert(d, "bundle", size, float(t))
        elif op == "promote":
            c.promote(d, float(t))
        elif op in ("pin", "unpin"):
            c.pin(d, op == "pin")
        elif op == "remove":
            c.remove(d)
        elif op == "warm":
            c.park_warm(f"f{key % 3}", size, float(t))
        else:
            c.take_warm(f"f{key % 3}")
        assert c.used("ssd") <= ssd + 1e-9
        assert c.used("hdd") <= c.budget["hdd"] + 1e-9
        assert c.warm_mb() <= mem + 1e-9
        assert abs(c.used("ssd") - sum(e.size_mb for e in c.disk.values() if e.tier == "ssd")) < 1e-6
