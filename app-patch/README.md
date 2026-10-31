# app-patch: reference copies of what the setup puts outside the repository

These are **reference copies**, kept so you can see (and review) exactly what `setup-coder-mac.sh` writes to
`~/.local/share/strata/`. The setup does not copy them; it generates the same content on your machine
(`tools/mac_write_coder_config.py` and `tools/mac_add_coder_to_app.py`), so the paths, your RAM and your app version are right.

| Here | Written to | By |
| --- | --- | --- |
| `install/strata-coder-iq1_m.json` | `~/.local/share/strata/install/strata-coder-iq1_m.json` | `tools/mac_write_coder_config.py` |
| `control-0.1.46.1/` | `~/.local/share/strata/components/control/0.1.46.1/` | `tools/mac_add_coder_to_app.py` |
| `active.json` | `~/.local/share/strata/components/control/active.json` | `tools/mac_add_coder_to_app.py` |
| `opencode/opencode.json` | `~/.config/opencode/opencode.json` (copy it yourself) | you; see "Use it with opencode" in the main README |

## The run config

`install/strata-coder-iq1_m.json` is the config of the tested setup (36 GB Mac, `STRATA_METAL_ARENA_GB` = 15).
Every path contains `/Users/YOU`: replace it with your home folder (and the model folders with yours) if you copy it by hand.
Prefer `tools/mac_write_coder_config.py`, which fills the paths in, picks the arena for your RAM and checks that the files exist.
The app edits two fields on its own (`ui_resource_profile`, and it adds or removes `--pool-workers`); that is normal.

## The patched Control component

The app's own Control component (`/Applications/Strata.app/Contents/Resources/control`, 145 MB with its Python runtime) is not
copied here: it is Strata's, and `mac_add_coder_to_app.py` copies it on your machine. Only the four files that differ from
Strata 0.1.46 are kept here:

| File | Change |
| --- | --- |
| `strata_control/mac_fit.py` | Adds the `IQ1_M` size with `family: coder` to the Mac catalog. |
| `tools/strata_mcp.py` | `_mac_sizes` takes a family; `_mac_model_table` lists the qwen and coder families (so the picker shows the Coder). |
| `setup.py` | The Mac installer accepts `family == "coder"`: it only checks that the run config exists and reports "All set". |
| `BUNDLE.json` | Version `0.1.46.1`, so the app loads this copy instead of the bundled one. |

To compare with your app: `diff -r /Applications/Strata.app/Contents/Resources/control/<file> app-patch/control-0.1.46.1/<file>`.
These copies match Strata 0.1.46. For another app version run `tools/mac_add_coder_to_app.py` instead of copying them; it patches
the new bundle, or stops without changing anything if the layout differs.
