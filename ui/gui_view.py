"""Bind the HTML interface to the desktop host."""

import base64
import gzip
import json
import re
from pathlib import Path


def _bundle_part(source: str, name: str):
    tag = re.search(fr'<script type="__bundler/{name}">\s*(.*?)\s*</script>', source, re.S)
    if tag is None:
        raise ValueError(f"ui/index.html is missing its {name} data.")
    return json.loads(tag[1])


def render_page(project_root: Path, preview: bool = False) -> str:
    """Return a self-contained page with the original React, CSS and fonts."""
    ui_dir = project_root / "ui"
    source = (ui_dir / "index.html").read_text(encoding="utf-8")
    template = _bundle_part(source, "template")

    # Its loader evaluates a DCLogic class named Component. Inherit its actual
    # renderVals(), including all the original presentation and animation rules.
    marker = "class Component extends DCLogic"
    if template.count(marker) != 1:
        raise ValueError("ui/index.html is missing its expected view component.")
    template = template.replace(marker, "class Mockup extends DCLogic")
    script_end = template.index("</script>", template.index("class Mockup extends DCLogic"))
    desktop = """
class DesktopWindow extends Mockup {
    renderVals() {
        return {...super.renderVals(),
            minimizeWindow: () => window.pywebview?.api?.minimize(),
            closeWindow: () => window.pywebview?.api?.close_window()
        };
    }
}
"""
    if preview:
        desktop += "class Component extends DesktopWindow {}"
    else:
        desktop += (ui_dir / "assets" / "live.js").read_text(encoding="utf-8")
    template = template[:script_end] + desktop + "\n" + template[script_end:]

    # Bind native controls to the existing header elements.
    for label, handler in (("Minimize", "minimizeWindow"), ("Close", "closeWindow")):
        attr = f'aria-label="{label}"'
        template = template.replace(attr, attr + ' sc-camel-on-click="{{ ' + handler + ' }}"')
    title_bar = """<style>
.hdr { -webkit-app-region: drag; app-region: drag; user-select: none; }
.hdr button, .hdr button * { -webkit-app-region: no-drag; app-region: no-drag; }
</style>"""

    # Resolve assets before navigation. The export's browser unpacker replaces
    # document.body after loading, after the desktop bridge has been attached.
    assets = {}
    for asset_id, entry in _bundle_part(source, "manifest").items():
        data = entry["data"]
        if entry.get("compressed"):
            data = base64.b64encode(gzip.decompress(base64.b64decode(data))).decode("ascii")
        assets[asset_id] = f'data:{entry["mime"]};base64,{data}'
        template = template.replace(asset_id, assets[asset_id])
    resources = {item["id"]: assets[item["uuid"]] for item in _bundle_part(source, "ext_resources")}
    resource_map = "<script>window.__resources = " + json.dumps(resources) + ";</script>"
    licenses = re.search(r"<!--.*?-->", source, re.S)
    if licenses is None:
        raise ValueError("ui/index.html is missing its bundled font licenses.")
    return template.replace("<head>", "<head>" + licenses[0] + resource_map + title_bar, 1)
