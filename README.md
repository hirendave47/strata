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
> the config script in step 6 reproduces the working config (apart from two fields the app manages itself), but a full install
> from an empty machine has not been re-run.

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

### Quick start: one script

Install the [Strata app](https://github.com/Niko1221/Strata/releases/latest) into `/Applications` and [Homebrew](https://brew.sh), then:

```bash
git clone <URL-OF-THIS-REPOSITORY> Strata
cd Strata
./setup-coder-mac.sh
```

It does steps 1 to 7 below: checks the Mac, installs `cmake`, `ninja`, `uv` and `hf` if missing, builds the engine, downloads and
verifies the model (it asks before the 59 GB download), packs it, writes the run config with the expert-cache size for your RAM
(the speed setting), and makes the app list the Coder. Finished steps are skipped, so you can run it again after an interruption or
after an app update. Options: `--data-dir DIR` (models and packs; default is the repository folder, both git-ignored),
`--arena GB|off`, `--context N`, `--skip-download`, `--skip-build`, `--yes`; `--help` lists them.
Then quit and reopen Strata and choose Models, Coder, IQ1_M, Load.

The script was run here on a machine where everything but the Mac checks was already done (it skipped the finished steps, rebuilt
the engine and wrote the config and the app change); a run on an empty machine has not been tried.

### What is stored where

| Where | What |
| --- | --- |
| This repository | The patched engine sources, `setup-coder-mac.sh`, `tools/mac_*coder*.py`, `app-patch/` (reference copies), this README. Build output (`build-metal/`) and downloads (`third_party/`, and `models/` and `packs/` if you keep the default data folder) are git-ignored. |
| `--data-dir` (default: the repository folder; the manual steps below use its parent) | `models/IQ1_M/` (58 GB), `models/mmproj-...gguf`, `packs/iq1_m/`. |
| `~/.local/share/strata/install/` | `strata-coder-iq1_m.json` (the run config, including the arena setting), its `.bak` and log, and `run-coder-iq1_m.sh`. |
| `~/.local/share/strata/components/control/` | The patched copy of the app's Control component, and `active.json` that points the app at it. |
| `/Applications/Strata.app` | Not modified. |

The repository also keeps reference copies of the three items in the `~/.local/share/strata` rows (the run config of the tested setup and the four patched Control files) in [`app-patch/`](app-patch/README.md), so you can review exactly what the setup writes. The setup generates them for your machine; it does not copy them.

### Manual steps

The numbered steps below do the same by hand.

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

The Strata app lists every config named `strata-<model>.json` in `~/.local/share/strata/install/`. This script writes the
Coder's config (the same layout the app writes for IQ3_S, with the Coder's expert profile, the patched engine and the expert-cache
size for your RAM) and the start script `run-coder-iq1_m.sh`:

```bash
/Applications/Strata.app/Contents/Resources/control/python/bin/python3.12 \
  tools/mac_write_coder_config.py --data-dir ~/models/strata
# options: --arena GB|off   --context N   --port N   (run it with --help for all)
```

An existing config is kept as `strata-coder-iq1_m.json.bak`, and its `STRATA_METAL_ARENA_GB` is carried over unless you pass
`--arena`. The script checks that the engine, both shards, the pack, the vision projector and the expert profile exist and names
the first one that is missing. The start script listens on `127.0.0.1` only.

What the key settings do:

| Setting | Meaning |
| --- | --- |
| `exe` | The patched engine from step 4. Stock engines cannot load this model. |
| `--expert-profile .../expert-profile-coder.bin` | The Coder's 256-expert profile that ships in the Strata app (the 512-expert one is `expert-profile.bin`). |
| `--mmap-experts` | Read experts from the SSD through the page cache. Needed because the model is bigger than RAM on most Macs. |
| `--max-context 131072` | 128K context. |
| `--vision` | Image input, using the `mmproj` file from step 3. |
| `--spec 2`, `--suffix-draft 0` | Speculative decoding settings from the IQ3_S config; kept the same. |
| `env.STRATA_METAL_ARENA_GB` | How much RAM the engine may use as its expert cache. **This is the main speed setting**: see [Speed and memory](#speed-and-memory). `15` suits a 36 GB Mac; use `11` on 32 GB. |

### 7. Make the app list and load the Coder

The stock app cannot use the Coder on a Mac for two reasons, and one script fixes both:

1. **It is not in the model picker.** The picker is built from a catalog that the app's bundled "Control" component produces, and
   on a Mac that catalog only holds the regular Qwen sizes. A model with a run config is *installed*, but stays hidden unless the
   catalog lists it.
2. **Load can fail with "the app on a Mac runs the Qwen3.8-Flash-Next sizes (Q2_0, IQ3_XXS, IQ3_S); coder is not one of them".**
   Load only starts the model directly when every setting in the app (context size, pictures, low-RAM mode) equals the saved
   config. If one differs (the app suggests 64K context, the Coder config uses 128K), it runs the Mac *installer* first, and the
   stock installer refuses the Coder.

The script copies Control to `~/.local/share/strata/components/control/<version>.1`, adds the Coder (family `Coder`, size `IQ1_M`)
to the Mac catalog, and teaches that copy's installer to accept the Coder: it only checks that your hand-made config from step 6
exists and reports "All set". It downloads nothing and never rewrites your config, so the context, engine path and memory setting
you chose stay as they are. `/Applications/Strata.app` is not modified, so its signature stays valid.

```bash
/Applications/Strata.app/Contents/Resources/control/python/bin/python3.12 \
  ~/models/strata/Strata/tools/mac_add_coder_to_app.py
```

Quit and reopen Strata afterwards (`osascript -e 'quit app "Strata"'`, wait a few seconds, then `open -a Strata`).
**Run it again after every Strata app update or re-install**: the update brings a new bundled Control, and the script patches a
fresh copy of it. If the app's layout changed so much that the script cannot patch it, it stops without switching anything on,
and the app keeps working as before.

## Run it

Run **one** of the two ways below at a time. The model is 58 GB and does not fit in memory twice, and the script's default port
(8080) is used by whatever is loaded first.

### Option A: the Strata desktop app (GUI)

```bash
open -a Strata
```

or double-click `/Applications/Strata.app`. In the app, open **Models**, choose the **Coder** family, select **IQ1_M** and press **Load**.
If it is not listed, or Load shows the "coder is not one of them" error, run step 7 and restart the app.
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

## Speed and memory

The model is 58 GB. A Mac with less than about 64 GB cannot hold it, so the engine keeps the **dense weights and a cache of the
most-used experts in RAM** and reads every other expert from the SSD. Decode speed depends almost entirely on how many experts that
cache (the **expert arena**) can hold: a hit is a RAM read, a miss is an SSD read.

### Why it can be slow out of the box

The engine sizes the arena cautiously. On a 36 GB Mac it chose **3.8 GB** and left 10+ GB of RAM unused, so most experts came
from the SSD and decode ran at **10 to 13 tokens/s**. You can see the choice in the engine log
(`~/.local/share/strata/install/strata-coder-iq1_m.log`):

```
strata metal stream: expert arena 3.78 GB, 1728 slots ...
```

### Use more memory: set the arena yourself

Put `STRATA_METAL_ARENA_GB` in the `env` block of `~/.local/share/strata/install/strata-coder-iq1_m.json` (step 6 already writes it):

```json
"env": { "STRATA_METAL_STREAM": "1", "STRATA_METAL_ARENA_GB": "15" }
```

or change it with one command (any value you like):

```bash
python3 - <<'PY'
import json, os
p = os.path.expanduser("~/.local/share/strata/install/strata-coder-iq1_m.json")
c = json.load(open(p)); c["env"]["STRATA_METAL_ARENA_GB"] = "15"
json.dump(c, open(p, "w"), indent=2)
PY
```

Then **restart the model** (app: unload, then Load; script: stop it with Ctrl+C and start it again). The log should now say
`expert arena 15.00 GB, 6803 slots`.

Measured on an Apple M5 Max with 36 GB RAM, macOS 27, greedy decoding, 250 generated tokens, browsers and other big programs closed:

| `STRATA_METAL_ARENA_GB` | Decode | Free RAM while generating | Notes |
| --- | ---: | ---: | --- |
| unset (engine chose 3.8) | 10 to 13 tok/s | 75% | Safe, but most of the RAM is idle |
| 11 | 23 to 25 tok/s | about 22% | A good choice if you keep other apps open |
| **15** | **28 to 34 tok/s** | about 15% | No swapping while generating. The value this README uses |

![M5 Max 32GB MacBook inference speed of about 27 tok/s](https://github.com/user-attachments/assets/d93bd7d2-2dd9-462c-8b13-d4fee26c5751)

*A run on an M5 Max MacBook with 32 GB: about 27 tok/s.*

### How to choose the number for your Mac

The engine's total footprint is roughly **arena + 8 to 9 GB** (dense weights, buffers, prompt memory), and macOS needs about 7 GB
plus room for your other programs.

| Your RAM | Start with | Notes |
| --- | ---: | --- |
| 24 GB | 6 | Untested; expect it to be slower |
| 32 GB | 11 | The screenshot above is a 32 GB MacBook |
| 36 GB | 15 | Measured above |
| 48 GB | 24 | Untested starting point |
| 64 GB or more | leave unset | The engine already picks a much larger arena |

Then tune it:

1. **Close heavy programs first** (browsers with many tabs, other models). The arena only helps if macOS can give the memory
   without swapping.
2. **Raise it in steps of 2 GB** and run the same prompt each time. Keep the value while the speed still climbs.
3. **Stop when the Mac starts to swap.** While the model generates, check:
   ```bash
   memory_pressure | tail -1      # "System-wide memory free percentage": keep it above about 10%
   vm_stat | grep Swapouts        # run twice, 10 seconds apart: the number must not grow during generation
   ```
   If free memory falls under 10%, or `Swapouts` grows, lower the value by 2 to 4 GB. Swapping is slower than the default.
4. The engine has a ceiling of its own (about 30 GB total on a 36 GB Mac, the smaller of the GPU working set and the RAM less
   what it leaves to macOS). If your value goes over it, the engine says so in the log. `STRATA_METAL_KEEP_FREE_GB=N` sets how
   much RAM the engine leaves to macOS instead (default: the larger of 7 GB or 15% of the RAM); lowering it gives the arena more
   room but leaves macOS less.

Other switches (all go in the same `env` block; see also [docs/MAC.md](docs/MAC.md#switches)):

| Variable | Effect |
| --- | --- |
| `STRATA_METAL_ARENA_GB=N` | The expert arena in GB. The main lever |
| `STRATA_METAL_KEEP_FREE_GB=N` | RAM left to macOS (default: the larger of 7 GB or 15% of the RAM) |
| `STRATA_METAL_WIRE_ARENA=0` | Leave the filled arena pageable instead of wired (64 GB or more only) |
| `STRATA_METAL_PROMPT_CHUNK=N` | Prompt chunk size; 1024 by default on a smaller Mac |

### Other things that affect speed

- **The app's "resource preference" (Models → settings).** "Work" keeps some CPU and memory free for your other programs and passes
  `--pool-workers`; "Performance" drops that limit. The app rewrites `ui_resource_profile` and `--pool-workers` in the config when
  you switch, so the file can differ slightly from step 6's output. That is normal. `STRATA_METAL_ARENA_GB` is a separate setting
  and is not changed by it. I measured the speeds above with the script, not with each preference, so I cannot say how much
  "Performance" adds.
- **Quit the app's other work.** The vision reader keeps about 1 GB, and the engine itself about 8 GB, on top of the arena. If you
  never send images, turn pictures off in the model's settings in the app to free that memory.
- **Context size.** `--max-context 131072` reserves cache for 128K tokens. A smaller context uses less memory; lower it in the
  app's Context menu or in the config's `--max-context` if you want to give the arena more room.
- **The first request after loading is slower**, because the caches are cold.
- **Prompt reading** runs at about 400 tokens/s on a long prompt, and much slower on a very short one (tens of tokens/s). That is
  how the streaming path works; the arena setting does not change it much.
- **Long chats** re-read the conversation unless the start of the prompt is unchanged; keep the earlier messages as they are to
  reuse the cache.
- **Nothing else can fix the 58 GB vs. RAM gap.** A Mac with 64 GB or more keeps far more of the model resident and is much faster.

## Troubleshooting

| Symptom | Cause and fix |
| --- | --- |
| `port 8080 is already in use` | A model server is already running (maybe from an earlier run). Find it with `lsof -iTCP:8080 -sTCP:LISTEN`, stop it (`pkill -f "serve/server.py --engine strata"`), or use `--port`. |
| `metal window: the geometry differs from Qwen3.8-Flash-Next's` | The engine in `exe` is not the patched one. Rebuild it (step 4) and check `exe` in the config. |
| The app says `the app on a Mac runs the Qwen3.8-Flash-Next sizes ... coder is not one of them` (on Load, or in *Add from folder / Install*) | The app is using its stock, unpatched Control. Run step 7 and restart the app. Do not use *Add from folder / Install* for the Coder; steps 3 to 6 set it up. |
| The app does not list the Coder under Models (also right after you re-install or update the app) | Run step 7 again and restart the app. A new app version brings a fresh, unpatched catalog. Also check that the config is `~/.local/share/strata/install/strata-coder-iq1_m.json` and the pack is in `packs/iq1_m`. |
| After a re-install the config mentions `/Volumes/Strata 0.2.1/...` and the model fails to start | The app was opened from the `.dmg` instead of `/Applications`, and rewrote the configs' paths to the disk image. Drag `Strata.app` to `/Applications`, eject the image, and fix the paths: `sed -i '' 's#/Volumes/Strata [0-9.]*/Strata.app#/Applications/Strata.app#g' ~/.local/share/strata/install/strata-*.json` |
| Slow answers (10 to 13 tok/s) | The engine's default expert arena is small on a 36 GB Mac. See [Speed and memory](#speed-and-memory) and set `STRATA_METAL_ARENA_GB`. |
| Answers got slower after raising the arena, or the Mac feels sluggish | The value is too high and macOS is swapping. Lower `STRATA_METAL_ARENA_GB` by 2 to 4 GB (check `vm_stat | grep Swapouts` while generating). |
| Engine log | `~/.local/share/strata/install/strata-coder-iq1_m.log`; app logs are in `~/.local/share/strata/logs/`. |

## Rebuilding after a change

```bash
cd ~/models/strata/Strata
ninja -C build-metal strata
```

The tests that cover this change (built from the same tree): `ninja -C build-metal route_parity prompt_parity`, then run the
resulting binaries from `build-metal`.

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
