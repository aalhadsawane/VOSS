"""SeBS 110.dynamic-html: render an HTML page with random numbers (Jinja2)."""

from __future__ import annotations

import datetime
import os
from typing import Any

from jinja2 import Template

PAGE = Template(
    "<html><body><h1>Hello {{ username }}</h1><p>{{ cur_time }}</p>"
    "<ul>{% for n in numbers %}<li>{{ n }}</li>{% endfor %}</ul></body></html>"
)


def make_input(size_kb: int) -> dict[str, Any]:
    return {"username": "voss", "n": 100 * size_kb}


def handler(inp: dict[str, Any]) -> str:
    return PAGE.render(username=inp["username"], cur_time=datetime.datetime.now(), numbers=list(os.urandom(inp["n"])))
