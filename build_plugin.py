"""
Build an installable QGIS plugin ZIP for SCOPE.

Usage (any operating system, Python 3):

    python build_plugin.py

Creates SCOPE.zip next to this script, with a single top-level folder named
"SCOPE" regardless of what the checkout folder is called. Install it via
QGIS -> Plugins -> Manage and Install Plugins -> Install from ZIP.
"""
import fnmatch
import os
import sys
import zipfile

PLUGIN_NAME = "SCOPE"

# Development files and generated artifacts that do not ship with the plugin.
EXCLUDE_DIRS = {".git", ".vscode", ".idea", "__pycache__", "build", "dist", ".ruff_cache"}
EXCLUDE_FILES = [
    "*.py[cod]", "*.zip", "*.log", "*.grd", "*.xyz", "*.code-workspace",
    ".gitignore", ".gitattributes", "build_plugin.py", "build_plugin.sh", "launcher.py",
]


def main():
    src_dir = os.path.dirname(os.path.abspath(__file__))
    zip_path = os.path.join(src_dir, f"{PLUGIN_NAME}.zip")

    if not os.path.isfile(os.path.join(src_dir, "metadata.txt")):
        sys.exit("ERROR: metadata.txt not found next to build_plugin.py.")

    if os.path.exists(zip_path):
        os.remove(zip_path)

    count = 0
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, dirs, files in os.walk(src_dir):
            dirs[:] = sorted(d for d in dirs if d not in EXCLUDE_DIRS)
            for name in sorted(files):
                if any(fnmatch.fnmatch(name, pattern) for pattern in EXCLUDE_FILES):
                    continue
                path = os.path.join(root, name)
                rel = os.path.relpath(path, src_dir).replace(os.sep, "/")
                zf.write(path, f"{PLUGIN_NAME}/{rel}")
                count += 1

    print(f"Created {zip_path} ({count} files).")
    print("Install via QGIS -> Plugins -> Manage and Install Plugins -> Install from ZIP.")


if __name__ == "__main__":
    main()
