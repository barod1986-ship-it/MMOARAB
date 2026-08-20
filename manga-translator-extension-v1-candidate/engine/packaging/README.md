# Local Engine packaging

Phase 7 packages the Python Local Engine into a native PyInstaller **onedir** artifact. Onedir is intentional for a large ML/native-dependency companion: it avoids onefile self-extraction semantics and keeps model files outside the executable bundle.

`build_engine.py --release` fails closed unless the exact release Python/uv/PyInstaller versions and `uv.lock` are present. OS-specific signing/notarization lives under `windows/`, `macos/`, and `linux/`. The machine-readable support claims remain false until signed/notarized clean-machine gates actually pass.
