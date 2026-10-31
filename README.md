# Strata, patched for the Qwen3.8-Flash-Next **Coder** (IQ1_M) on Apple Silicon

This repository is a **custom fork of [Strata](https://github.com/Niko1221/Strata)** (original project by
[Niko1221](https://github.com/Niko1221) and the Strata contributors, MIT license). All credit for the engine, the desktop app and
the tooling goes to them. If you want Strata itself, use the original repository and its releases.

It exists for one purpose: **to run the ISTA-DASLab Coder model on a Mac with the Strata Metal engine and the Strata desktop app.**

| | |
| --- | --- |
| Model | [ISTA-DASLab/Qwen3.8-Flash-Next-GSQ-RCO-Coder-GGUF](https://huggingface.co/ISTA-DASLab/Qwen3.8-Flash-Next-GSQ-RCO-Coder-GGUF) (file set `IQ1_M`, 58.4 GB, Apache-2.0 per the model card) |
| Original Strata | <https://github.com/Niko1221/Strata> |
| Model authors | [ISTA-DASLab](https://huggingface.co/ISTA-DASLab) (GSQ + RCO expert pruning) |

## Why this fork exists

The Coder is Qwen3.8-Flash-Next with **half of its experts removed: 256 experts per layer instead of 512** (48 layers, 10 active
per token). Everything else is the same as the regular Qwen3.8-Flash-Next models (such as IQ3_S) that Strata supports.

Stock Strata on a Mac fails with this model in two places:

1. **The desktop app's "Install" flow refuses it.** On a Mac it only accepts the Qwen family. The Coder shows up as "not
   supported". The upstream docs say the same: *Coder is not set up on Mac yet*.
2. **The Metal engine assumes 512 experts.** Even with a hand-made config, the stock engine stops at load time with
   `metal window: the geometry differs from Qwen3.8-Flash-Next's`.

What this fork changes (only the Metal engine; the Windows/Linux engines and everything else are untouched):

| File | Change |
| --- | --- |
| `metal/src/engine/window.cpp`, `metal/src/engine/prompt_chain.inc` | Accept 256 or 512 experts (`nexp_`) instead of a fixed 512; decode and prompt paths use it |
| `metal/src/engine/stream.h`, `metal/src/engine/stream.cpp` | Expert streaming reads the expert count from the model (`blk.0.ffn_gate_exps.weight`) |
| `metal/kernels/moe.metal`, `metal/kernels/prompt.metal` | Router kernels mask the unused columns when there are fewer than 512 experts |
| `metal/tests/prompt_chain.cpp`, `metal/tests/prompt_parity.cpp` | Updated for the new `route_topk` argument |

The 512-expert models keep working. IQ3_S was re-checked on the patched engine, and the `route_parity` and `prompt_parity` tests
pass.

The app's "Install" flow is **not** patched. Instead you build the model's pack with Strata's own tool and write one run config by
hand (steps 5 and 6 below). The Strata desktop app then lists the model as installed and can load it.

> **Status.** Verified on an Apple M5 Max, 36 GB RAM, macOS 27, Strata app 0.1.46. The model produced correct code, and
> recalled a hidden word from a 3,348-token prompt. Other Macs are untested. The steps below were written from that working setup;
> the config generator in step 6 was checked to reproduce the working config exactly, but a full install from an empty machine
> has not been re-run.

## Requirements

- An **Apple Silicon Mac** (M1 or newer) with **macOS 15 or newer**. Intel Macs cannot run it.
- **About 70 GB of free disk**: 58.4 GB for the model, plus the vision projector (0.9 GB) and the pack (small).
- **RAM.** The model is 58 GB, so on a 32 to 48 GB Mac the experts stream from the SSD. On the 36 GB test machine decode ran
  at about 15 tokens/s and prompts at about 250 tokens/s. More RAM keeps more experts resident and is faster.
- **[Strata desktop app](https://github.com/Niko1221/Strata/releases/latest), version 0.1.46**, installed in `/Applications`. It provides
  the Python runtime, the expert profile and the vision reader that this setup reuses.
- **Xcode** (full app, with the Command Line Tools) to build the engine. The engine compiles its Metal kernels at run time, so the
  separate "Metal Toolchain" download is not needed.

## Install

Every path below assumes everything lives under `~/models/strata`:

```
~/models/strata/
├── Strata/            <- this repository
├── models/
│   ├── IQ1_M/         <- the two Coder GGUF shards
│   └── mmproj-Qwen3.8-Flash-Next-BF16.gguf
└── packs/iq1_m/       <- built in step 5
```

### 1. Install the packages (macOS)

Install [Homebrew](https://brew.sh) if you do not have it, then:

```bash
xcode-select --install          # Command Line Tools (skip if already installed)
brew install cmake ninja git uv
uv tool install huggingface_hub # provides the `hf` download command
```

Also install the **Strata app** from the [original releases page](https://github.com/Niko1221/Strata/releases/latest) (drag
`Strata.app` to `/Applications`, open it once). If macOS calls it "damaged", see the upstream
[troubleshooting](docs/TROUBLESHOOTING.md#the-desktop-app-and-the-terminal).

Tested versions: cmake 4.4.3, ninja 1.13.2, Xcode 27.2.

### 2. Get the code

```bash
mkdir -p ~/models/strata && cd ~/models/strata
git clone <URL-OF-THIS-REPOSITORY> Strata
cd Strata
```

### 3. Download the model

The model is the **IQ1_M** set from
<https://huggingface.co/ISTA-DASLab/Qwen3.8-Flash-Next-GSQ-RCO-Coder-GGUF> (two shards, both required, plus the BF16 vision
projector that sits next to them):

```bash
hf download ISTA-DASLab/Qwen3.8-Flash-Next-GSQ-RCO-Coder-GGUF \
  --include "IQ1_M/*" --include "mmproj-Qwen3.8-Flash-Next-BF16.gguf" \
  --local-dir ~/models/strata/models
```

Check that you have:

```
~/models/strata/models/IQ1_M/Qwen3.8-Flash-Next-GSQ-RCO-IQ1_M-00001-of-00002.gguf   (29.6 GB)
~/models/strata/models/IQ1_M/Qwen3.8-Flash-Next-GSQ-RCO-IQ1_M-00002-of-00002.gguf   (28.8 GB, the n-gram table)
~/models/strata/models/mmproj-Qwen3.8-Flash-Next-BF16.gguf                            (0.9 GB)
```

The model card notes that the first shard was updated on October 17, 2026 (less looping, better coding scores). If you downloaded
it before that date, download it again.

### 4. Build the patched Metal engine

The build needs Apple's `metal-cpp` headers and the `llama.cpp` source at the commit Strata pins (only its `ggml` part is used):

```bash
cd ~/models/strata/Strata

# Apple's metal-cpp headers (pinned by SHA-256)
curl -L -o third_party/metal-cpp_26.zip https://developer.apple.com/metal/cpp/files/metal-cpp_26.zip
echo "4df3c078b9aadcb516212e9cb03004cbc5ce9a3e9c068fa3144d021db585a3a4  third_party/metal-cpp_26.zip" | shasum -a 256 -c -
unzip -q third_party/metal-cpp_26.zip -d third_party

# llama.cpp at Strata's pinned commit
curl -L -o /tmp/llama.cpp.zip https://github.com/ggml-org/llama.cpp/archive/3cf03257f219afbe7334045ff7c6a06ac68c627d.zip
unzip -q /tmp/llama.cpp.zip -d /tmp
mv /tmp/llama.cpp-3cf03257f219afbe7334045ff7c6a06ac68c627d third_party/llama.cpp

# configure and build
cmake -S metal -B build-metal -G Ninja -DCMAKE_BUILD_TYPE=Release \
  -DMETAL_CPP_DIR="$PWD/third_party/metal-cpp" \
  -DSTRATA_GGML_DIR="$PWD/third_party/llama.cpp"
ninja -C build-metal strata
```

The result is `~/models/strata/Strata/build-metal/strata`. **Keep this folder**: the run config in step 6 points at it, and the
engine loads its Metal kernels from the source tree.

### 5. Build the model pack

The pack is an index of the GGUF that the engine uses. It reads the GGUF in place, takes seconds and does not change the
downloaded files. Use the Python that ships inside the Strata app (it already has `numpy`):

```bash
CTRL=/Applications/Strata.app/Contents/Resources/control
"$CTRL/python/bin/python3.12" ~/models/strata/Strata/tools/iq_pack.py \
  --gguf ~/models/strata/models/IQ1_M/Qwen3.8-Flash-Next-GSQ-RCO-IQ1_M-00001-of-00002.gguf \
  --out  ~/models/strata/packs/iq1_m
```

The folder name `iq1_m` matters: the app finds a pack by lower-casing the GGUF's folder name (`IQ1_M` becomes `iq1_m`).

### 6. Write the run config and the start script

The Strata app lists every config named `strata-<model>.json` in `~/.local/share/strata/install/`. The block below writes the
Coder's config (the same layout the app writes for IQ3_S, with the Coder's expert profile and the patched engine):

```bash
STRATA_HOME="$HOME/models/strata"
CTRL="/Applications/Strata.app/Contents/Resources/control"
export STRATA_HOME CTRL
"$CTRL/python/bin/python3.12" - <<'PY'
import json, os
home, ctrl = os.environ["STRATA_HOME"], os.environ["CTRL"]
inst = os.path.expanduser("~/.local/share/strata/install")
eng = os.path.expanduser("~/.local/share/strata/components/engine")
engdir = sorted(d for d in os.listdir(eng) if d.endswith("macos-arm64-metal"))[-1]
vision = f"{eng}/{engdir}/strata-vision"
g1 = f"{home}/models/IQ1_M/Qwen3.8-Flash-Next-GSQ-RCO-IQ1_M-00001-of-00002.gguf"
g2 = f"{home}/models/IQ1_M/Qwen3.8-Flash-Next-GSQ-RCO-IQ1_M-00002-of-00002.gguf"
args = ["--pack", f"{home}/packs/iq1_m", "--native", g1, "--ple-gguf", g2,
        "--expert-profile", f"{ctrl}/data/expert-profile-coder.bin",
        "--expert-cache", "64", "--prefill", "auto", "--spec", "2", "--suffix-draft", "0",
        "--max-context", "131072", "--mmap-experts", "--vision", "--pool-workers", "14",
        "--vram-reserve-mib", "2048"]
cfg = {
  "exe": f"{home}/Strata/build-metal/strata", "args": args, "cwd": ctrl,
  "tokenizer": f"{home}/packs/iq1_m/tokenizer",
  "model_name": "qwen3.8-flash-next-coder-iq1_m",
  "log": f"{inst}/strata-coder-iq1_m.log", "lib_dirs": [], "port": 8080, "backend": "metal",
  "env": {"STRATA_METAL_STREAM": "1"},
  "vision": {"exe": vision, "mmproj": f"{home}/models/mmproj-Qwen3.8-Flash-Next-BF16.gguf",
             "model": g1, "gpu": True, "max_tokens": 1024, "cpu_exe": vision},
  "args_written": args, "vram_reserve_mib": 2048, "ui_reserve_applied": 2048,
  "ui_resource_baseline": {"workers": 0, "reserve": 0, "ramBudget": False, "ramHeadroom": False},
  "ui_resource_profile": "work", "ui_vision_enabled": True, "ui_vision_device": "yes"}
os.makedirs(inst, exist_ok=True)
json.dump(cfg, open(f"{inst}/strata-coder-iq1_m.json", "w"), indent=2)
PY

cat > ~/.local/share/strata/install/run-coder-iq1_m.sh <<'EOF'
#!/bin/sh
cd "/Applications/Strata.app/Contents/Resources/control"
exec "/Applications/Strata.app/Contents/Resources/control/python/bin/python3.12" \
  "/Applications/Strata.app/Contents/Resources/control/serve/server.py" \
  --engine strata \
  --config "$HOME/.local/share/strata/install/strata-coder-iq1_m.json" \
  --port 8080 --open
EOF
chmod +x ~/.local/share/strata/install/run-coder-iq1_m.sh
```

What the key settings do:

| Setting | Meaning |
| --- | --- |
| `exe` | The patched engine from step 4. Stock engines cannot load this model. |
| `--expert-profile .../expert-profile-coder.bin` | The Coder's 256-expert profile that ships in the Strata app (the 512-expert one is `expert-profile.bin`). |
| `--mmap-experts` | Read experts from the SSD through the page cache. Needed because the model is bigger than RAM on most Macs. |
| `--max-context 131072` | 128K context. |
| `--vision` | Image input, using the `mmproj` file from step 3. |
| `--spec 2`, `--suffix-draft 0` | Speculative decoding settings from the IQ3_S config; kept the same. |

## Run it

Run **one** of the two ways below at a time. The model is 58 GB and does not fit in memory twice, and the script's default port
(8080) is used by whatever is loaded first.

### Option A: the Strata desktop app (GUI)

```bash
open -a Strata
```

or double-click `/Applications/Strata.app`. In the app, pick **`coder-iq1_m`** from the installed models and press **Load**.
The first load takes a minute or two. When it reports ready, chat in the app.

The app starts the engine itself, on a port of its own with a generated API key, and uses the `exe` from your config, so it runs
the patched engine. The app will not load a model while a script-started server is running; quit that server first.

### Option B: the start script (browser chat and API)

```bash
~/.local/share/strata/install/run-coder-iq1_m.sh
```

Wait for `ready: http://127.0.0.1:8080/v1 ...`. `--open` then opens the browser chat at <http://127.0.0.1:8080/>. The server
speaks the OpenAI API (`/v1/chat/completions`) and the Anthropic API (`/v1/messages`). The model id is
`qwen3.8-flash-next-coder-iq1_m`. Closing the terminal stops the model.

```bash
curl http://127.0.0.1:8080/v1/chat/completions -H 'Content-Type: application/json' -d '{
  "model": "qwen3.8-flash-next-coder-iq1_m",
  "messages": [{"role": "user", "content": "Write a Python function that reverses a string."}],
  "max_tokens": 150
}'
```

To run the script while the app is open, give it another port and drop `--open`:

```bash
/Applications/Strata.app/Contents/Resources/control/python/bin/python3.12 \
  /Applications/Strata.app/Contents/Resources/control/serve/server.py \
  --engine strata --config ~/.local/share/strata/install/strata-coder-iq1_m.json \
  --port 8090 --host 127.0.0.1
```

The server listens on `127.0.0.1` (this Mac only) by default. If you ever expose it on your network with `--host 0.0.0.0`, also
set `--api-key`.

Useful `server.py` options: `--port`, `--host`, `--api-key`, `--lazy` (load on first request), `--idle-unload SECONDS`,
`--parallel N`. `server.py --help` lists the rest.

## Troubleshooting

| Symptom | Cause and fix |
| --- | --- |
| `port 8080 is already in use` | A model server is already running (maybe from an earlier run). Find it with `lsof -iTCP:8080 -sTCP:LISTEN`, stop it (`pkill -f "serve/server.py --engine strata"`), or use `--port`. |
| The app says the model is **not supported** / install fails with "coder is not one of them" | You used the app's *Add from folder / Install* flow. Do not use it for the Coder. Follow steps 5 and 6 instead; the app lists the config you wrote as already installed. |
| `metal window: the geometry differs from Qwen3.8-Flash-Next's` | The engine in `exe` is not the patched one. Rebuild it (step 4) and check `exe` in the config. |
| The app does not show `coder-iq1_m` | The config must be `~/.local/share/strata/install/strata-coder-iq1_m.json`, and the pack must be in `packs/iq1_m` beside the `models` folder. |
| Slow answers | Expected on a Mac with less than 64 GB: experts stream from the SSD. Close other large apps to free RAM. |
| Engine log | `~/.local/share/strata/install/strata-coder-iq1_m.log`; app logs are in `~/.local/share/strata/logs/`. |

## Rebuilding after a change

```bash
cd ~/models/strata/Strata
ninja -C build-metal strata
```

The tests that cover this change (built from the same tree): `ninja -C build-metal route_parity prompt_parity`, then run the
resulting binaries from `build-metal`.

## M5 Max 32GB Macbook inference speed of 27 tok/s
<img width="2864" height="1822" alt="sceenshot 2026-10-31 at 5 02 06 PM@2x" src="https://github.com/user-attachments/assets/d93bd7d2-2dd9-462c-8b13-d4fee26c5751" />


## Credits and licenses

- **Strata**, the engine, desktop app and tooling this fork is based on: <https://github.com/Niko1221/Strata>
  (Niko1221 and the Strata contributors). This fork keeps the upstream [MIT license](LICENSE) and copyright notice. Report general
  Strata problems upstream; this fork only adds Coder support on Mac.
- **Qwen3.8-Flash-Next-GSQ-RCO-Coder-GGUF**: [ISTA-DASLab](https://huggingface.co/ISTA-DASLab) at the Institute of Science and
  Technology Austria. Method papers: [GSQ](https://arxiv.org/abs/2604.18556) and [RCO](https://arxiv.org/abs/2605.00649). The weights
  inherit the license of the base model, Qwen3.8-Flash-Next; read the
  [model card](https://huggingface.co/ISTA-DASLab/Qwen3.8-Flash-Next-GSQ-RCO-Coder-GGUF) before use. The Coder keeps half of the
  experts, tuned for code, agentic tool use and vision, and is weaker outside those areas. For general use, ISTA-DASLab recommends their
  [unpruned GSQ-RCO releases](https://huggingface.co/ISTA-DASLab/Qwen3.8-Flash-Next-GSQ-RCO-GGUF).
- Apple [metal-cpp](https://developer.apple.com/metal/cpp/) and [llama.cpp / ggml](https://github.com/ggml-org/llama.cpp) are
  used to build the Metal engine.
