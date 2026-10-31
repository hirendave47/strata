#!/bin/bash
# setup-coder-mac.sh - set up the Qwen3.8-Flash-Next Coder (IQ1_M) for the Strata app on an Apple Silicon Mac.
#
# It builds the patched Metal engine of this fork, downloads the model (59 GB), packs it, writes the run config and
# start script (with the fast expert-cache setting), and makes the Strata app list the Coder. Every step is skipped when
# it is already done, so it is safe to run again. See README.md for what each step does.
#
#   ./setup-coder-mac.sh [--data-dir DIR] [--arena GB|off] [--context N] [--skip-download] [--skip-build] [--yes]
#
# Needs: Apple Silicon, macOS 15+, Xcode or the Command Line Tools, Homebrew, ~70 GB free, and Strata.app in /Applications.
# Everything is downloaded over HTTPS. The servers it configures listen on 127.0.0.1 only. No credentials are used.
set -euo pipefail

REPO="$(cd "$(dirname "$0")" && pwd)"
APP="/Applications/Strata.app"
APP_CONTROL="$APP/Contents/Resources/control"
APP_PY="$APP_CONTROL/python/bin/python3.12"
COMPONENTS="${STRATA_COMPONENTS_DIR:-$HOME/.local/share/strata/components}"
INSTALL_DIR="${STRATA_INSTALL_DIR:-$HOME/.local/share/strata/install}"

HF_REPO="ISTA-DASLab/Qwen3.8-Flash-Next-GSQ-RCO-Coder-GGUF"
SHARD1="Qwen3.8-Flash-Next-GSQ-RCO-IQ1_M-00001-of-00002.gguf"
SHARD2="Qwen3.8-Flash-Next-GSQ-RCO-IQ1_M-00002-of-00002.gguf"
MMPROJ="mmproj-Qwen3.8-Flash-Next-BF16.gguf"
SHARD1_BYTES=29608446496
SHARD2_BYTES=28800138432
MMPROJ_BYTES=907543008

METAL_CPP_URL="https://developer.apple.com/metal/cpp/files/metal-cpp_26.zip"
METAL_CPP_SHA256="4df3c078b9aadcb516212e9cb03004cbc5ce9a3e9c068fa3144d021db585a3a4"
LLAMA_COMMIT="3cf03257f219afbe7334045ff7c6a06ac68c627d"
LLAMA_URL="https://github.com/ggml-org/llama.cpp/archive/$LLAMA_COMMIT.zip"

DATA_DIR="$REPO"
ARENA=""
CONTEXT=""
SKIP_DOWNLOAD=0
SKIP_BUILD=0
ASSUME_YES=0

usage() {
  sed -n '2,11p' "$0" | sed 's/^# \{0,1\}//'
  cat <<'EOF'

Options:
  --data-dir DIR     where models/ and packs/ go (default: this repository folder; both are git-ignored)
  --arena GB|off     expert cache in GB (default: chosen from your RAM; 'off' = the engine's own, slower, choice)
  --context N        context window in tokens (default 131072)
  --skip-download    do not download the model (use what is in DATA_DIR/models)
  --skip-build       do not build the engine (use an existing build-metal/strata)
  --yes              do not ask before the 59 GB download
  -h, --help         this text
EOF
}

say()  { printf '\n==> %s\n' "$*"; }
note() { printf '    %s\n' "$*"; }
die()  { printf '\nERROR: %s\n' "$*" >&2; exit 1; }
have() { command -v "$1" >/dev/null 2>&1; }
need_arg() { [ "$#" -ge 2 ] || die "$1 needs a value"; }

while [ "$#" -gt 0 ]; do
  case "$1" in
    --data-dir)      need_arg "$@"; DATA_DIR="$2"; shift 2 ;;
    --arena)         need_arg "$@"; ARENA="$2"; shift 2 ;;
    --context)       need_arg "$@"; CONTEXT="$2"; shift 2 ;;
    --skip-download) SKIP_DOWNLOAD=1; shift ;;
    --skip-build)    SKIP_BUILD=1; shift ;;
    --yes|-y)        ASSUME_YES=1; shift ;;
    -h|--help)       usage; exit 0 ;;
    *)               usage >&2; die "unknown option: $1" ;;
  esac
done

file_size() { wc -c < "$1" | tr -d ' '; }
download() {  # download URL DEST - HTTPS only, TLS 1.2+, with a timeout on connect
  curl --proto '=https' --tlsv1.2 --fail --location --connect-timeout 30 --retry 3 --output "$2" "$1"
}

# ---------------------------------------------------------------- 1. checks
say "1/8 Checking this Mac"
[ "$(uname -s)" = "Darwin" ] || die "this script is for macOS"
[ "$(uname -m)" = "arm64" ] || die "an Apple Silicon Mac (M1 or newer) is required"
MACOS_MAJOR="$(sw_vers -productVersion | cut -d. -f1)"
[ "$MACOS_MAJOR" -ge 15 ] || die "macOS 15 or newer is required (this is $(sw_vers -productVersion))"
[ -x "$APP_PY" ] || die "$APP is not installed (or is not the 0.1.x desktop app). Install Strata into /Applications first: https://github.com/Niko1221/Strata/releases"
if ! have xcrun || ! xcrun --find clang >/dev/null 2>&1; then
  die "Xcode or the Command Line Tools are missing. Install Xcode from the App Store, open it once, then run: xcode-select --install"
fi
mkdir -p "$DATA_DIR"
DATA_DIR="$(cd "$DATA_DIR" && pwd)"
FREE_KB="$(df -k "$DATA_DIR" | awk 'NR==2 {print $4}')"
NEED_GB=70
if [ "$SKIP_DOWNLOAD" -eq 0 ] && [ ! -f "$DATA_DIR/models/IQ1_M/$SHARD2" ]; then
  [ "$((FREE_KB / 1024 / 1024))" -ge "$NEED_GB" ] || die "need about $NEED_GB GB free in $DATA_DIR, have $((FREE_KB / 1024 / 1024)) GB"
fi
note "Apple Silicon, macOS $(sw_vers -productVersion), $(( $(sysctl -n hw.memsize) / 1073741824 )) GiB RAM"
note "app: $APP    repo: $REPO    data: $DATA_DIR"

# ---------------------------------------------------------------- 2. tools
say "2/8 Build tools (cmake, ninja, uv, hf)"
MISSING=""
for t in cmake ninja uv; do have "$t" || MISSING="$MISSING $t"; done
if [ -n "$MISSING" ]; then
  have brew || die "Homebrew is needed to install:$MISSING   (https://brew.sh) - or install them yourself and run this again"
  # shellcheck disable=SC2086
  brew install $MISSING
fi
export PATH="$HOME/.local/bin:$PATH"
if ! have hf; then
  uv tool install huggingface_hub
fi
have hf || die "'hf' (Hugging Face CLI) was not found after installing it; add \$HOME/.local/bin to PATH and run again"
note "cmake $(cmake --version | head -1 | awk '{print $3}'), ninja $(ninja --version), hf found"

# ---------------------------------------------------------------- 3. engine component of the app
say "3/8 The app's engine component (its vision encoder is reused)"
find_vision() { ls -d "$COMPONENTS"/engine/*macos-arm64-metal/strata-vision 2>/dev/null | tail -1 || true; }
VISION="$(find_vision)"
if [ -z "$VISION" ]; then
  note "not unpacked yet: opening Strata once so that it unpacks its engine"
  open -a "$APP"
  i=0
  while [ -z "$VISION" ] && [ "$i" -lt 60 ]; do
    sleep 5; i=$((i + 1)); VISION="$(find_vision)"
  done
  [ -n "$VISION" ] || die "the app did not unpack its engine within 5 minutes. Open Strata, wait for its window, and run this again"
fi
note "found $VISION"

# ---------------------------------------------------------------- 4. third-party sources
say "4/8 Third-party sources (metal-cpp headers, llama.cpp ggml at the pinned commit)"
TP="$REPO/third_party"
mkdir -p "$TP"
if [ ! -f "$TP/metal-cpp/Metal/Metal.hpp" ]; then
  download "$METAL_CPP_URL" "$TP/metal-cpp_26.zip"
  GOT="$(shasum -a 256 "$TP/metal-cpp_26.zip" | awk '{print $1}')"
  [ "$GOT" = "$METAL_CPP_SHA256" ] || { rm -f "$TP/metal-cpp_26.zip"; die "metal-cpp download has the wrong checksum ($GOT)"; }
  rm -rf "$TP/metal-cpp"
  unzip -q "$TP/metal-cpp_26.zip" -d "$TP/metal-cpp-unzip"
  mv "$TP/metal-cpp-unzip/metal-cpp" "$TP/metal-cpp"
  rm -rf "$TP/metal-cpp-unzip"
  [ -f "$TP/metal-cpp/Metal/Metal.hpp" ] || die "metal-cpp did not unpack as expected"
else
  note "metal-cpp: already there"
fi
if [ ! -f "$TP/llama.cpp/ggml/CMakeLists.txt" ]; then
  download "$LLAMA_URL" "$TP/llama.cpp.zip"
  rm -rf "$TP/llama.cpp" "$TP/llama-unzip"
  unzip -q "$TP/llama.cpp.zip" -d "$TP/llama-unzip"
  mv "$TP/llama-unzip/llama.cpp-$LLAMA_COMMIT" "$TP/llama.cpp"
  rm -rf "$TP/llama-unzip" "$TP/llama.cpp.zip"
  [ -f "$TP/llama.cpp/ggml/CMakeLists.txt" ] || die "llama.cpp did not unpack as expected"
else
  note "llama.cpp: already there"
fi

# ---------------------------------------------------------------- 5. build
say "5/8 Building the Metal engine (first build takes a few minutes)"
if [ "$SKIP_BUILD" -eq 1 ]; then
  note "skipped (--skip-build)"
else
  cmake -S "$REPO/metal" -B "$REPO/build-metal" -G Ninja -DCMAKE_BUILD_TYPE=Release \
    -DMETAL_CPP_DIR="$TP/metal-cpp" -DSTRATA_GGML_DIR="$TP/llama.cpp" >/dev/null
  ninja -C "$REPO/build-metal" strata
fi
[ -x "$REPO/build-metal/strata" ] || die "build-metal/strata does not exist: the build did not finish"

# ---------------------------------------------------------------- 6. model
say "6/8 The model (59 GB from Hugging Face: $HF_REPO)"
MODELS="$DATA_DIR/models"
model_complete() {
  [ -f "$MODELS/IQ1_M/$SHARD1" ] && [ "$(file_size "$MODELS/IQ1_M/$SHARD1")" = "$SHARD1_BYTES" ] &&
  [ -f "$MODELS/IQ1_M/$SHARD2" ] && [ "$(file_size "$MODELS/IQ1_M/$SHARD2")" = "$SHARD2_BYTES" ] &&
  [ -f "$MODELS/$MMPROJ" ]       && [ "$(file_size "$MODELS/$MMPROJ")" = "$MMPROJ_BYTES" ]
}
if model_complete; then
  note "already complete"
elif [ "$SKIP_DOWNLOAD" -eq 1 ]; then
  die "--skip-download was given but the model is incomplete in $MODELS"
else
  if [ "$ASSUME_YES" -eq 0 ]; then
    [ -t 0 ] || die "this would download 59 GB; run it from a terminal or add --yes"
    printf '    Download 59 GB into %s ? [y/N] ' "$MODELS"
    read -r ANSWER
    case "$ANSWER" in y|Y|yes|YES) ;; *) die "stopped; nothing was downloaded" ;; esac
  fi
  hf download "$HF_REPO" --include "IQ1_M/*" --include "$MMPROJ" --local-dir "$MODELS"
  model_complete || die "the download is incomplete or the files have unexpected sizes; run this again to resume"
fi

# ---------------------------------------------------------------- 7. pack
say "7/8 Packing the model for the engine"
PACK="$DATA_DIR/packs/iq1_m"
if [ -f "$PACK/index.txt" ]; then
  note "already packed"
else
  mkdir -p "$DATA_DIR/packs"
  STRATA_GGUF_PY="$TP/llama.cpp/gguf-py" "$APP_PY" "$REPO/tools/iq_pack.py" --gguf "$MODELS/IQ1_M/$SHARD1" --out "$PACK"
  [ -f "$PACK/index.txt" ] || die "packing did not produce $PACK/index.txt"
fi

# ---------------------------------------------------------------- 8. config + app
say "8/8 Writing the run config and making the app list the Coder"
CFG_ARGS=(--data-dir "$DATA_DIR" --repo-dir "$REPO")
[ -z "$ARENA" ] || CFG_ARGS+=(--arena "$ARENA")
[ -z "$CONTEXT" ] || CFG_ARGS+=(--context "$CONTEXT")
"$APP_PY" "$REPO/tools/mac_write_coder_config.py" "${CFG_ARGS[@]}"
"$APP_PY" "$REPO/tools/mac_add_coder_to_app.py"

cat <<EOF

Done. To use the Coder:
  1. Quit Strata if it is open, then open it again.
  2. Models -> Coder -> IQ1_M -> Load.
Or without the app:   $INSTALL_DIR/run-coder-iq1_m.sh      (opens the chat at http://127.0.0.1:8080)

After you update the Strata app, run this script again (it skips the finished steps and re-applies the app change).
EOF
