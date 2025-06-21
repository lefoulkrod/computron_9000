#!/usr/bin/env bash
# install_bin_scripts.sh — Install all scripts in this directory to ~/.local/bin
# Skips README files and itself.

set -euo pipefail

SCRIPT_NAME="$(basename "$0")"
INSTALL_DIR="$HOME/.local/bin"

mkdir -p "$INSTALL_DIR"

for file in "$(dirname "$0")"/*; do
  base="$(basename "$file")"
  # Skip README files and this script
  if [[ "$base" == "README"* ]] || [[ "$base" == "$SCRIPT_NAME" ]]; then
    continue
  fi
  if [[ -f "$file" ]]; then
    cp "$file" "$INSTALL_DIR/"
    chmod +x "$INSTALL_DIR/$base"
    echo "Installed $base to $INSTALL_DIR"
  fi

done

echo "All eligible scripts have been installed to $INSTALL_DIR."
