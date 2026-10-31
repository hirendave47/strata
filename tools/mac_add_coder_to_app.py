#!/usr/bin/env python3
"""Make the Strata desktop app (Mac) list the Qwen3.8-Flash-Next Coder (IQ1_M) in its model picker.

The app builds its model list from a catalog that the bundled "Control" component produces, and on a Mac that catalog only
contains the Qwen family. A model whose run config exists is installed, but it stays out of the picker unless the catalog
lists it. This script copies the app's Control component to the per-user component folder as version <bundled>.1, adds the
Coder (family "coder", size IQ1_M) to the Mac catalog there, and points the app at it. /Applications/Strata.app is not
modified (its signature stays valid). Run with the Python that ships in the app:

    /Applications/Strata.app/Contents/Resources/control/python/bin/python3.12 tools/mac_add_coder_to_app.py

It also lets the app's Mac installer accept the Coder: when the app's Load button finds that its settings (for example the
context size) differ from the saved config, it runs "install" first, and the stock installer refuses the Coder. The patched one
only checks that the hand-made config exists and reports "All set" - it downloads nothing and never overwrites the config.

Then quit and reopen Strata. Run it again after you update the app (the new bundle needs the same change).
"""
from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path

APP_CONTROL = Path(os.environ.get("STRATA_APP_CONTROL", "/Applications/Strata.app/Contents/Resources/control"))
COMPONENTS = Path(os.environ.get("STRATA_COMPONENTS_DIR", Path.home() / ".local/share/strata/components"))

MAC_FIT_ANCHOR = '    "IQ3_S": {"shard1_gb": 54.8, "tested": True},\n'
MAC_FIT_ADD = ('    # the Coder (family "coder"): 256 experts per layer, shard 1 is 29.6 GB (needs the patched Metal engine of this fork)\n'
               '    "IQ1_M": {"shard1_gb": 29.6, "tested": True, "family": "coder", "shards": 2},\n')

MODEL_TABLE = '''    def _mac_model_table(self, hw: dict) -> list:
        models, families, _ctx, _src = self.tables()
        ram = float(hw.get("ram_gb") or 0)
        have = {c.stem[len("strata-"):] for c in self.configs()}
        out = []
        for family in ("qwen", "coder"):                # the Coder after the regular sizes: never the default
            fd = families.get(family)
            if fd is None:
                continue
            sizes = []
            for m in self._mac_sizes(models, family):
                d = models[m]
                tag = (fd.get("tag", "") + m).lower()
                sizes.append({"model": m, "about": d["about"], "download_gb": d["download_gb"], "experimental": False,
                              "images": d.get("vision", fd.get("vision", True)) is not False,
                              "ram_needed_gb": d["ram_gb"], "experts_gb": d.get("arena_gb"), "mem_total": False,
                              "memory_gb": round(float(d.get("arena_gb") or d["ram_gb"]) + 1.0, 1),
                              "on_this_pc": self._mac_verdict(m, ram) if ram else None, "installed": tag in have, "id": tag})
            if sizes:
                out.append({"family": family, "title": fd["title"], "about": fd.get("about"), "experimental": False,
                            "images": any(x["images"] for x in sizes), "sizes": sizes})
        return out

'''

SETUP_ANCHOR = '    app_sizes = [m for m, d in MF.MAC_MODELS.items() if d.get("family", "qwen") == "qwen"]\n'
SETUP_ADD = '''    if a.family == "coder":                            # this fork: the Coder is set up by hand (README); nothing is downloaded or rewritten
        coder_cfg = home() / "strata-coder-iq1_m.json"
        if not coder_cfg.is_file():
            fail(f"the Coder's run config {coder_cfg} does not exist",
                 "set it up by hand first (README, steps 3 to 6 of the Coder fork)")
        ok(f"Coder IQ1_M: run config {coder_cfg} is in place (kept as it is)")
        say()
        say("All set.")
        return 0
'''


def main() -> int:
    if not (APP_CONTROL / "BUNDLE.json").is_file():
        print(f"Strata's Control component was not found at {APP_CONTROL}. Install the Strata app first.")
        return 1
    bundle = json.loads((APP_CONTROL / "BUNDLE.json").read_text(encoding="utf-8-sig"))
    base = bundle["version"]
    version = f"{base}.1"
    dest = COMPONENTS / "control" / version
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(APP_CONTROL, dest, symlinks=True)
    for cache in dest.rglob("__pycache__"):
        shutil.rmtree(cache, ignore_errors=True)

    fit = dest / "strata_control" / "mac_fit.py"
    text = fit.read_text(encoding="utf-8")
    if MAC_FIT_ANCHOR not in text:
        print("strata_control/mac_fit.py is not the layout this script expects (app version changed?). Nothing was switched on.")
        shutil.rmtree(dest)
        return 1
    fit.write_text(text.replace(MAC_FIT_ANCHOR, MAC_FIT_ANCHOR + MAC_FIT_ADD, 1), encoding="utf-8")

    mcp = dest / "tools" / "strata_mcp.py"
    text = mcp.read_text(encoding="utf-8")
    sig_old = "    def _mac_sizes(self, models: dict) -> list:"
    row_old = 'return [m for m, d in mf.MAC_MODELS.items() if d.get("family", "qwen") == "qwen" and m in models] if mf else []'
    start, end = text.find("    def _mac_model_table"), text.find("    def recommend", text.find("    def _mac_model_table"))
    if sig_old not in text or row_old not in text or start < 0 or end < 0:
        print("tools/strata_mcp.py is not the layout this script expects (app version changed?). Nothing was switched on.")
        shutil.rmtree(dest)
        return 1
    text = text.replace(sig_old, '    def _mac_sizes(self, models: dict, family: str = "qwen") -> list:', 1)
    text = text.replace(row_old, row_old.replace('== "qwen"', "== family"), 1)
    start, end = text.find("    def _mac_model_table"), text.find("    def recommend", text.find("    def _mac_model_table"))
    mcp.write_text(text[:start] + MODEL_TABLE + text[end:], encoding="utf-8")

    setup = dest / "setup.py"
    text = setup.read_text(encoding="utf-8")
    if text.count(SETUP_ANCHOR) != 1:
        print("setup.py is not the layout this script expects (app version changed?). Nothing was switched on.")
        shutil.rmtree(dest)
        return 1
    setup.write_text(text.replace(SETUP_ANCHOR, SETUP_ADD + SETUP_ANCHOR, 1), encoding="utf-8")

    for rel in ("strata_control/mac_fit.py", "tools/strata_mcp.py", "setup.py"):
        compile((dest / rel).read_text(encoding="utf-8"), rel, "exec")        # a syntax error stops here, before the switch

    bundle["version"] = version
    (dest / "BUNDLE.json").write_text(json.dumps(bundle, indent=1), encoding="utf-8")
    (COMPONENTS / "control" / "active.json").write_text(json.dumps({"version": version, "folder": version}), encoding="utf-8")
    print(f"Done: the app will use {dest}. Quit and reopen Strata.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
