#!/usr/bin/env python3
"""Write the run config and the start script for the Qwen3.8-Flash-Next Coder (IQ1_M) on a Mac.

Run with the Python that ships in the Strata app (setup-coder-mac.sh does this):

    /Applications/Strata.app/Contents/Resources/control/python/bin/python3.12 tools/mac_write_coder_config.py

It writes, in the Strata install folder (default ~/.local/share/strata/install):
  strata-coder-iq1_m.json   the run config the Strata app lists and loads (mode 0600, like the app's own)
  run-coder-iq1_m.sh        starts the model without the app (OpenAI/Anthropic API + browser chat, 127.0.0.1 only)
An existing config is kept as strata-coder-iq1_m.json.bak first. Its STRATA_METAL_ARENA_GB is carried over unless --arena is given.

STRATA_METAL_ARENA_GB is the expert cache in GB (README, "Speed and memory"). Without it the engine picks a cautious size on a
32 to 48 GB Mac and decodes at about 10 to 13 tokens/s; with it 28 to 34 tokens/s were measured on a 36 GB M5 Max.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import stat
import subprocess
import sys
from pathlib import Path

TAG = "coder-iq1_m"
MODEL_NAME = "qwen3.8-flash-next-coder-iq1_m"
SHARD = "Qwen3.8-Flash-Next-GSQ-RCO-IQ1_M-0000{i}-of-00002.gguf"
MMPROJ = "mmproj-Qwen3.8-Flash-Next-BF16.gguf"

# (minimum RAM in GiB, arena in GB). Measured: 36 GiB -> 15 (28 to 34 tok/s), 11 on a 36 GiB Mac -> 23 to 25 tok/s.
# The 32, 24 and 48 GiB rows are starting points that follow the same rule (engine footprint = arena + 8 to 9 GB), not measurements.
# 60 GiB and up: no entry, the engine already picks a much larger arena.
ARENA_BY_RAM = ((60, None), (44, 24), (34, 15), (30, 11), (22, 6))


def ram_gib() -> float:
    out = subprocess.run(["sysctl", "-n", "hw.memsize"], capture_output=True, text=True, check=True).stdout.strip()
    return int(out) / 2**30


def auto_arena(ram: float):
    for floor, arena in ARENA_BY_RAM:
        if ram >= floor:
            return arena
    return 4                                           # under 22 GiB: untested, the smallest useful cache


def main() -> int:
    here = Path(__file__).resolve().parent.parent      # the repo
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data-dir", default=str(here.parent), help="folder with models/ and packs/ (default: the folder above this repo)")
    ap.add_argument("--repo-dir", default=str(here), help="this repository (its build-metal/strata is the engine)")
    ap.add_argument("--install-dir", default=os.environ.get("STRATA_INSTALL_DIR", str(Path.home() / ".local/share/strata/install")))
    ap.add_argument("--components-dir", default=os.environ.get("STRATA_COMPONENTS_DIR", str(Path.home() / ".local/share/strata/components")))
    ap.add_argument("--app-control", default=os.environ.get("STRATA_APP_CONTROL", "/Applications/Strata.app/Contents/Resources/control"))
    ap.add_argument("--arena", default=None, help="expert cache in GB, or 'off' for the engine's own choice (default: keep the existing value, else by RAM)")
    ap.add_argument("--context", type=int, default=131072)
    ap.add_argument("--port", type=int, default=8080)
    a = ap.parse_args()

    data, repo, inst = Path(a.data_dir).resolve(), Path(a.repo_dir).resolve(), Path(a.install_dir)
    ctrl, comps = Path(a.app_control), Path(a.components_dir)

    engines = sorted((comps / "engine").glob("*macos-arm64-metal"))
    if not engines or not (engines[-1] / "strata-vision").is_file():
        print(f"No Strata engine component under {comps / 'engine'}: open the Strata app once, wait a minute, and run this again.")
        return 1
    vision = str(engines[-1] / "strata-vision")
    engine = repo / "build-metal" / "strata"
    g1, g2 = (data / "models" / "IQ1_M" / SHARD.format(i=i) for i in (1, 2))
    pack = data / "packs" / "iq1_m"
    mmproj = data / "models" / MMPROJ
    profile = ctrl / "data" / "expert-profile-coder.bin"
    for what, p in (("engine", engine), ("model shard 1", g1), ("model shard 2", g2), ("pack index", pack / "index.txt"),
                    ("vision projector", mmproj), ("Coder expert profile", profile)):
        if not p.exists():
            print(f"Missing {what}: {p}")
            return 1

    cfg_path = inst / f"strata-{TAG}.json"
    previous = {}
    if cfg_path.is_file():
        try:
            previous = json.loads(cfg_path.read_text(encoding="utf-8"))
        except ValueError:
            previous = {}

    if a.arena is None:
        arena = (previous.get("env") or {}).get("STRATA_METAL_ARENA_GB") or auto_arena(ram_gib())
    elif a.arena.lower() in ("off", "none", "0"):
        arena = None
    else:
        arena = a.arena
        try:
            float(arena)                               # a typo stops here, not at engine start
        except ValueError:
            ap.error(f"--arena must be a number of GB or 'off', got {arena!r}")

    args = ["--pack", str(pack), "--native", str(g1), "--ple-gguf", str(g2),
            "--expert-profile", str(profile),
            "--expert-cache", "64", "--prefill", "auto", "--spec", "2", "--suffix-draft", "0",
            "--max-context", str(a.context), "--mmap-experts", "--vision", "--pool-workers", "14",
            "--vram-reserve-mib", "2048"]
    env = {"STRATA_METAL_STREAM": "1"}
    if arena is not None:
        env["STRATA_METAL_ARENA_GB"] = str(arena)
    cfg = {
        "exe": str(engine), "args": args, "cwd": str(ctrl), "tokenizer": str(pack / "tokenizer"),
        "model_name": MODEL_NAME, "log": str(inst / f"strata-{TAG}.log"), "lib_dirs": [], "port": a.port, "backend": "metal",
        "env": env,
        "vision": {"exe": vision, "mmproj": str(mmproj), "model": str(g1), "gpu": True, "max_tokens": 1024, "cpu_exe": vision},
        "args_written": args, "vram_reserve_mib": 2048, "ui_reserve_applied": 2048,
        "ui_resource_baseline": {"workers": 0, "reserve": 0, "ramBudget": False, "ramHeadroom": False},
        "ui_resource_profile": "work", "ui_vision_enabled": True, "ui_vision_device": "yes",
    }

    inst.mkdir(parents=True, exist_ok=True)
    if previous:
        shutil.copy2(cfg_path, cfg_path.with_suffix(".json.bak"))
    tmp = cfg_path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
    os.chmod(tmp, stat.S_IRUSR | stat.S_IWUSR)         # 0600: the app's own configs are private too
    os.replace(tmp, cfg_path)

    py = ctrl / "python" / "bin" / "python3.12"
    script = inst / f"run-{TAG}.sh"
    script.write_text(
        "#!/bin/sh\n"
        f'cd "{ctrl}"\n'
        f'exec "{py}" \\\n'
        f'  "{ctrl / "serve" / "server.py"}" \\\n'
        "  --engine strata \\\n"
        f'  --config "{cfg_path}" \\\n'
        f"  --host 127.0.0.1 --port {a.port} --open\n", encoding="utf-8")
    os.chmod(script, 0o755)

    print(f"config : {cfg_path}")
    print(f"script : {script}")
    print(f"engine : {engine}")
    print("arena  : " + (f"{arena} GB (STRATA_METAL_ARENA_GB)" if arena is not None else "the engine's own choice (off)"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
