#!/bin/bash
set -euo pipefail
export DISPLAY=:1

# Start Xvfb (virtual framebuffer) at 1280x720
Xvfb :1 -screen 0 1280x720x24 -ac &
sleep 1

# Start dbus session (needed by Xfce)
eval $(dbus-launch --sh-syntax)

# Start Xfce desktop
startxfce4 &
sleep 2

# VNC server on port 5900 (no password, shared mode)
x11vnc -display :1 -forever -nopw -listen 0.0.0.0 -rfbport 5900 -shared -bg

# websockify on port 6080 -> VNC 5900 (serves noVNC web client too)
websockify --web /usr/share/novnc 0.0.0.0:6080 localhost:5900 &

echo "Desktop ready on :1, VNC on 5900, WebSocket on 6080"
wait
