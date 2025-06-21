# bin Directory

This directory contains scripts designed to facilitate interaction with Computron 9000 from various modalities outside of a web interface.

## Purpose
Scripts in this directory provide command-line or programmatic access to Computron 9000, making it easier to integrate with other tools, automate workflows, or interact from environments where a web interface is not available or practical.

## Usage
- Use these scripts to interact with Computron 9000 from the terminal, shell scripts, or other automation tools.
- Each script is documented with usage instructions and options where applicable.

## Installation
To make these scripts available from your terminal, copy them to a directory included in your `PATH`. For most users, the recommended location is `~/.local/bin`, which is user-specific and does not require root permissions:

```bash
mkdir -p ~/.local/bin
cp * ~/.local/bin/
chmod +x ~/.local/bin/computron_9000  # Repeat for other scripts as needed
```

If you want the scripts to be available system-wide for all users, you can use `/usr/local/bin` instead (requires `sudo`):

```bash
sudo cp * /usr/local/bin/
sudo chmod +x /usr/local/bin/computron_9000  # Repeat for other scripts as needed
```

After this, you can run the scripts from any terminal session.
