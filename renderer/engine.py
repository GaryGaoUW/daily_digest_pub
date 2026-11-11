import re
from pathlib import Path
from typing import Any, Dict, Tuple

from jinja2 import Environment, FileSystemLoader, select_autoescape

_TEMPLATE_DIR = Path(__file__).parent
# Mail clients auto-link "XEQT.TO" as a .to domain, so TSX suffixes are dropped for display
_TSX_RE = re.compile(r"\b([A-Z0-9]{1,6})\.TO\b")


def strip_tsx(value: Any) -> str:
    return _TSX_RE.sub(r"\1", str(value))


class Renderer:
    def __init__(self, template_dir: Path = _TEMPLATE_DIR) -> None:
        self.env = Environment(
            loader=FileSystemLoader(str(template_dir)),
            autoescape=select_autoescape(enabled_extensions=("html",), default=False),
            trim_blocks=True,
            lstrip_blocks=True,
        )
        self.env.filters["ticker"] = strip_tsx

    def render(self, context: Dict[str, Any]) -> Tuple[str, str]:
        html = self.env.get_template("template.html").render(**context)
        text = self.env.get_template("template.txt").render(**context)
        return html, text
