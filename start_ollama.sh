#!/usr/bin/env bash

# Exit immediately if a command exits with a non-zero status
# Treat unset variables as an error and exit immediately
# The return value of a pipeline is the status of the last command to exit with a non-zero status
set -euo pipefail

OLLAMA_DEBUG=1 ollama serve
