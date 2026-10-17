#!/usr/bin/env bash
# Build the ReXGlue Xenos GPU plugin (librexgpu-xenos.so) and the codegen tool
# (rexglue) from source with the fixes in patches/rexglue-sdk/, and install them
# into an overlay of the nightly SDK so the forza build (its codegen step and the
# plugin it ships) and tools/run_forza.sh pick them up. Adapted from
# RecompiledHaloReach; the patch set started as Reach's.
#
# Usage: tools/build_rexglue_sdk.sh [--source-only]
#   --source-only  only check out and patch the SDK source (all tools/build_windows.sh needs)
#
# Why: the SDK's Xenos emulation lacks many Xenia fixes; the first one found
# (in Halo: Reach) was the SPIR-V translator reading the texture-fetch exponent
# bias from fetch-constant word 4 instead of word 3, which darkens textures 256x.
# Upstream closed the report (rexglue/rexglue-sdk#456) without taking GPU
# changes, so we carry the patches (docs/sdk_patches.md).
#
# Environment:
#   REXSDK_NIGHTLY  installed nightly SDK the overlay is based on
#                   (default ~/rexglue-sdk-nightly/0.10.0.24/linux-amd64)
#   REXSDK_SRC      source checkout (default ~/rexglue-sdk-src-forza/sdk)
#   REXSDK_JOBS     parallel compile jobs (default 4; the build runs at nice 15)
#   REXSDK_PATCHED  overlay prefix to create
#                   (default ~/rexglue-sdk-patched-forza/0.10.0.24/linux-amd64)
#
# The defaults are this project's own clone and overlay: RecompiledHaloReach uses
# ~/rexglue-sdk-src and ~/rexglue-sdk-patched, and the two patch sets may differ.
#
# Only the plugin and bin/rexglue are taken from this build; every other SDK file
# in the overlay is a symlink into the nightly, so both must be built from the
# nightly's exact commit to stay ABI-compatible with its librexruntime.so.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SDK_COMMIT=bd833a2ab69d305f99ddf57418fc38ffec8af93d  # nightly 0.10.0.24 (nightly-20261002-bd833a2a)
NIGHTLY="${REXSDK_NIGHTLY:-$HOME/rexglue-sdk-nightly/0.10.0.24/linux-amd64}"
SRC="${REXSDK_SRC:-$HOME/rexglue-sdk-src-forza/sdk}"
OVERLAY="${REXSDK_PATCHED:-$HOME/rexglue-sdk-patched-forza/0.10.0.24/linux-amd64}"
BREW=/home/linuxbrew/.linuxbrew

SOURCE_ONLY=0
[ "${1:-}" = --source-only ] && SOURCE_ONLY=1
[ "$SOURCE_ONLY" = 1 ] || [ -d "$NIGHTLY/lib" ] || { echo "nightly SDK not found at $NIGHTLY" >&2; exit 1; }

if [ ! -d "$SRC/.git" ]; then
    git clone https://github.com/rexglue/rexglue-sdk "$SRC"
fi
git -C "$SRC" fetch --quiet origin "$SDK_COMMIT" 2>/dev/null || true
git -C "$SRC" checkout --quiet "$SDK_COMMIT"
git -C "$SRC" submodule update --init --recursive --depth 1 --quiet

# Apply the patch series idempotently: build the patched tree (the SDK commit plus every
# patch, in a temporary index), then rewrite only the files whose content differs from it.
# Patches are not checked one by one against the working tree: later patches change the
# context of earlier ones (0035 that of 0018), so on a clone with the whole series applied
# neither the forward nor the reverse check of 0018 passes. Files that already match keep
# their timestamps, so a re-run rebuilds nothing; a changed, added or dropped patch rewrites
# just the files it touches.
patched_index="$(mktemp)"
GIT_INDEX_FILE="$patched_index" git -C "$SRC" read-tree "$SDK_COMMIT"
for patch in "$ROOT"/patches/rexglue-sdk/*.patch; do
    if ! GIT_INDEX_FILE="$patched_index" git -C "$SRC" apply --cached "$patch"; then
        echo "patch does not apply to $SDK_COMMIT: $(basename "$patch")" >&2
        rm -f "$patched_index"; exit 1
    fi
done
GIT_INDEX_FILE="$patched_index" git -C "$SRC" update-index -q --refresh > /dev/null || true
changed="$(GIT_INDEX_FILE="$patched_index" git -C "$SRC" diff-files --ignore-submodules --name-only)"
if [ -z "$changed" ]; then
    echo "patches already applied ($(ls "$ROOT"/patches/rexglue-sdk/*.patch | wc -l) in patches/rexglue-sdk)"
else
    while IFS= read -r file; do
        GIT_INDEX_FILE="$patched_index" git -C "$SRC" checkout-index -f -- "$file"
        echo "patched: $file"
    done <<< "$changed"
fi
rm -f "$patched_index"
[ "$SOURCE_ONLY" = 0 ] || exit 0

# Building the SDK needs X11/XCB and Wayland headers (its UI module and SDL3
# require them). Hosts without them (immutable Fedora) can use Homebrew's:
#   brew install libx11 libxcb libxext libxfixes libxcursor libxi libxrandr \
#                libxscrnsaver libxrender libxtst xorgproto wayland systemd
#   (systemd supplies libudev.h: without it SDL is built without udev and sees no joystick)
cmake_args=()
if [ -d "$BREW/opt/xorgproto/include" ]; then
    xp="$BREW/opt/xorgproto"
    inc=""
    for pkg in xorgproto wayland libxcb libx11 libxau libxdmcp systemd; do
        inc+=" -I$BREW/opt/$pkg/include"
    done
    export PKG_CONFIG_PATH="$BREW/lib/pkgconfig:$BREW/share/pkgconfig:$xp/share/pkgconfig${PKG_CONFIG_PATH:+:$PKG_CONFIG_PATH}"
    # The -L only serves this build's own librexruntime.so, which the plugin
    # links against but which is never shipped (the nightly's is used).
    cmake_args+=(-DCMAKE_PREFIX_PATH="$BREW" -DX11_X11_INCLUDE_PATH="$BREW/include"
                 "-DCMAKE_C_FLAGS=-march=x86-64-v2 $inc"
                 "-DCMAKE_CXX_FLAGS=-march=x86-64-v2 $inc"
                 "-DCMAKE_SHARED_LINKER_FLAGS=-L$BREW/lib")
fi
( cd "$SRC" && cmake --preset linux-amd64 "${cmake_args[@]}" > /dev/null )
nice -n 15 cmake --build "$SRC/out/build/linux-amd64" --config Release --target rexgpu-xenos rexglue rexruntime \
    --parallel "${REXSDK_JOBS:-4}"

built="$SRC/out/linux-amd64/Release/librexgpu-xenos.so"
[ -n "$built" ] || { echo "librexgpu-xenos.so not found in the build tree" >&2; exit 1; }

# Overlay: symlink everything from the nightly, then replace the plugin.
mkdir -p "$OVERLAY/lib"
for entry in "$NIGHTLY"/*; do
    case "$(basename "$entry")" in
        lib|bin) ;;
        *) ln -sfn "$entry" "$OVERLAY/$(basename "$entry")" ;;
    esac
done
for entry in "$NIGHTLY"/lib/*; do
    # The plugin and runtime are installed below (atomically); never swap them for a symlink.
    case "$(basename "$entry")" in librexgpu-xenos.so|librexruntime.so) continue ;; esac
    ln -sfn "$entry" "$OVERLAY/lib/$(basename "$entry")"
done
# Install by rename: overwriting a mapped .so in place can crash a running game.
plugin_new="$OVERLAY/lib/.librexgpu-xenos.new"
cp "$built" "$plugin_new"
mv -f "$plugin_new" "$OVERLAY/lib/librexgpu-xenos.so"
echo "patched plugin: $OVERLAY/lib/librexgpu-xenos.so"
# Keep this outside the nightly's symlinked share tree.
if [ -f "$SRC/out/linux-amd64/Release/SMAA-LICENSE.txt" ]; then
    mkdir -p "$OVERLAY/fh1-licenses"
    cp "$SRC/out/linux-amd64/Release/SMAA-LICENSE.txt" "$OVERLAY/fh1-licenses/SMAA.txt"
fi

# The runtime (patch 0028: faster memory protection queries). Same commit as the nightly's,
# so it is a drop-in; give it the nightly's RUNPATH (its own is the build tree's).
runtime_new="$OVERLAY/lib/.librexruntime.new"
cp "$SRC/out/linux-amd64/Release/librexruntime.so" "$runtime_new"
rpath_script="$(mktemp)"
printf 'file(RPATH_SET FILE "%s" NEW_RPATH "$ORIGIN:$ORIGIN/../lib")\n' "$runtime_new" > "$rpath_script"
cmake -P "$rpath_script"
rm -f "$rpath_script"
mv -f "$runtime_new" "$OVERLAY/lib/librexruntime.so"
echo "patched runtime: $OVERLAY/lib/librexruntime.so"

# The codegen tool: patches change the generated code too (0025: Xenon's dot-product
# overflow). Older overlays linked bin/ to the nightly's; it is a directory now.
[ -L "$OVERLAY/bin" ] && rm "$OVERLAY/bin"
mkdir -p "$OVERLAY/bin"
for entry in "$NIGHTLY"/bin/*; do
    [ "$(basename "$entry")" = rexglue ] || ln -sfn "$entry" "$OVERLAY/bin/$(basename "$entry")"
done
# The build tree's rexglue has that tree's absolute RUNPATH; give it the nightly's
# ($ORIGIN/../lib is the overlay's lib/, which links into the nightly).
tool_new="$OVERLAY/bin/.rexglue.new"
cp "$SRC/out/linux-amd64/Release/rexglue" "$tool_new"
rpath_script="$(mktemp)"
printf 'file(RPATH_SET FILE "%s" NEW_RPATH "$ORIGIN:$ORIGIN/../lib")\n' "$tool_new" > "$rpath_script"
cmake -P "$rpath_script"
rm -f "$rpath_script"
if cmp -s "$tool_new" "$OVERLAY/bin/rexglue"; then
    rm -f "$tool_new"
else
    mv -f "$tool_new" "$OVERLAY/bin/rexglue"
    # Code generated by another tool is stale. The forza build reruns codegen when the
    # tool is newer than its output, but codegen skips modules whose stamp fingerprint
    # (its inputs, not the tool) matches: drop the stamps.
    rm -f "$ROOT"/forza-recomp/generated/*/codegen.stamp
fi
"$OVERLAY/bin/rexglue" --help > /dev/null
echo "patched codegen: $OVERLAY/bin/rexglue"

# Stage it next to existing builds of the same SDK right away (the forza
# POST_BUILD step only re-copies it when forza relinks). Builds against other
# SDK versions keep their own plugin: it must match their librexruntime.so.
for build in "$ROOT"/forza-recomp/out/build/*/; do
    # Some build dirs have the plugin but no CMakeCache.txt (copies made for tests);
    # under set -e the sed would end the script before it reached the others.
    [ -f "$build/librexgpu-xenos.so" ] && [ -f "$build/CMakeCache.txt" ] || continue
    sdk_dir="$(sed -n 's/^rexglue_DIR:PATH=//p' "$build/CMakeCache.txt")"
    case "$sdk_dir" in
        "$NIGHTLY"/*|"$OVERLAY"/*)
            # Rename over it: running instances may have the old file mapped.
            cp "$OVERLAY/lib/librexgpu-xenos.so" "$build/.librexgpu-xenos.new"
            mv -f "$build/.librexgpu-xenos.new" "$build/librexgpu-xenos.so"
            echo "staged into $build" ;;
    esac
done
