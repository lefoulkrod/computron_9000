#!/bin/bash
# Container entrypoint: start desktop environment, then idle.
export DISPLAY=:1

# Virtual framebuffer
Xvfb :1 -screen 0 1280x720x24 -ac &
sleep 1

# D-Bus session (needed by Xfce and AT-SPI accessibility)
eval $(dbus-launch --sh-syntax)
export DBUS_SESSION_BUS_ADDRESS

# Enable accessibility for AT-SPI element detection
export GTK_MODULES=gail:atk-bridge
export ACCESSIBILITY_ENABLED=1

# Xfce desktop
startxfce4 &
sleep 2

# Disable screen blanking, set default cursor
xset s off -dpms 2>/dev/null || true
xsetroot -cursor_name left_ptr 2>/dev/null || true

# VNC server
x11vnc -display :1 -forever -nopw -listen 0.0.0.0 -rfbport 5900 -shared -cursor arrow -bg

# noVNC websocket bridge
websockify --web /usr/share/novnc 0.0.0.0:6080 localhost:5900 &

echo "Desktop ready on :1, VNC on 5900, WebSocket on 6080"

# Keep container alive
exec sleep infinity
