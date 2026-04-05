#!/bin/bash
# Container entrypoint: start desktop environment, then app server.
# Runs as root; drops privileges via gosu for each component.
export DISPLAY=:0
export COMPUTRON_CONTAINER=1

# ── Fix volume-mount ownership ───────────────────────────────────────────────
# When host directories are bind-mounted, they may arrive owned by the host
# user (e.g. UID 1000).  Ensure the container users own their directories.
chown computron:computron /home/computron
mkdir -p /home/computron/Desktop /home/computron/downloads

# Copy default Xfce config on first run (named volume starts empty)
if [ ! -d /home/computron/.config/xfce4/panel ]; then
    mkdir -p /home/computron/.config/xfce4
    cp -rn /etc/xdg/xfce4/* /home/computron/.config/xfce4/ 2>/dev/null
    chown -R computron:computron /home/computron/.config
fi
chown -R computron:computron /home/computron/Desktop
chown computron:computron_app /home/computron/downloads
chmod 775 /home/computron/downloads
chown computron_app:computron_app /var/lib/computron_9000

# ── Virtual framebuffer ──────────────────────────────────────────────────────
Xvfb :0 -screen 0 1280x720x24 -ac &
XVFB_PID=$!
sleep 1
if ! kill -0 $XVFB_PID 2>/dev/null; then
    echo "ERROR: Xvfb failed to start" >&2
    exit 1
fi

# ── D-Bus session (needed by Xfce and AT-SPI accessibility) ─────────────────
eval $(dbus-launch --sh-syntax)
export DBUS_SESSION_BUS_ADDRESS

# Enable accessibility for AT-SPI element detection
export GTK_MODULES=gail:atk-bridge
export ACCESSIBILITY_ENABLED=1

# ── Xfce desktop (as computron) ─────────────────────────────────────────────
# Pass D-Bus address explicitly so the child process inherits it.
gosu computron bash -c "export DBUS_SESSION_BUS_ADDRESS='$DBUS_SESSION_BUS_ADDRESS' GTK_MODULES=gail:atk-bridge ACCESSIBILITY_ENABLED=1; startxfce4" &
sleep 2

# Disable screen blanking, set default cursor
xset s off -dpms 2>/dev/null || true
xsetroot -cursor_name left_ptr 2>/dev/null || true

# Ensure window manager is running (startxfce4 sometimes fails to launch it)
if ! pgrep -x xfwm4 > /dev/null; then
    gosu computron bash -c 'DISPLAY=:0 xfwm4 &'
fi

# ── VNC server ───────────────────────────────────────────────────────────────
gosu computron x11vnc -display :0 -forever -nopw -noshm -listen 0.0.0.0 -rfbport 5900 -shared -cursor arrow -bg

# ── noVNC websocket bridge ───────────────────────────────────────────────────
websockify --web /usr/share/novnc 0.0.0.0:6080 localhost:5900 &

echo "Desktop ready on :0, VNC on 5900, noVNC on 6080"

# ── App server with auto-restart ─────────────────────────────────────────────
# The loop restarts the app on crash or when killed by container-restart-app.
# SIGTERM (from podman stop) breaks the loop for clean shutdown.
_shutdown=0
trap '_shutdown=1; echo "Received SIGTERM, shutting down..."' SIGTERM

cd /opt/computron_9000
while [ $_shutdown -eq 0 ]; do
    echo "Starting app server..."
    gosu computron_app python3.12 main.py &
    APP_PID=$!
    wait $APP_PID
    exit_code=$?
    [ $_shutdown -eq 1 ] && break
    echo "App server exited ($exit_code), restarting in 2s..."
    sleep 2
done
