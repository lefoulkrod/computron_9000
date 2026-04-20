#!/bin/bash
# Container entrypoint: start desktop environment, then app server.
# Runs as root; drops privileges via gosu for each component.
#
# Env knobs (default in parens):
#   DISPLAY         — X11 display number (":99"). Parallel containers
#                     sharing a network namespace need distinct values.
#   ENABLE_DESKTOP  — "true" to run xfce + x11vnc + noVNC so a user can view
#                     the container's desktop. Default "false" — Xvfb still
#                     runs (Playwright needs it) but xfce and VNC are skipped.
export DISPLAY="${DISPLAY:-:99}"
# Strip the leading colon to get just the number for Xvfb
_DISPLAY_NUM="${DISPLAY#:}"
_DESKTOP="${ENABLE_DESKTOP:-false}"

# Re-export container env vars so gosu children inherit them.
# Podman/Docker -e vars are in the process env but not always exported
# in the bash sense when tini execs the entrypoint.
[ -n "${HF_TOKEN:-}" ] && export HF_TOKEN
[ -n "${GITHUB_TOKEN:-}" ] && export GITHUB_TOKEN
[ -n "${GITHUB_USER:-}" ] && export GITHUB_USER
# Default LLM_HOST to host Ollama if not explicitly set
export LLM_HOST="${LLM_HOST:-http://localhost:11434}"

# ── Set up /home/computron ───────────────────────────────────────────────────
# Bind-mounted host dirs may arrive owned by the host UID, so we chown to
# computron AFTER creating any subdirectories below. Chowning first leaves
# anything mkdir'd later (e.g. .config) root-owned, which silently breaks
# Chrome: its crashpad handler can't write to ~/.config/google-chrome and the
# launcher pipe closes with "recvmsg: Connection reset by peer".
mkdir -p /home/computron/Desktop /home/computron/downloads

# Copy default Xfce config on first run (named volume starts empty)
if [ ! -d /home/computron/.config/xfce4/panel ]; then
    mkdir -p /home/computron/.config/xfce4
    cp -rn /etc/xdg/xfce4/* /home/computron/.config/xfce4/ 2>/dev/null
fi

chown -R computron:computron /home/computron /var/lib/computron
chmod 755 /home/computron

# ── Virtual framebuffer ──────────────────────────────────────────────────────
Xvfb ":${_DISPLAY_NUM}" -screen 0 1280x720x24 -ac &
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

# ── Desktop (optional, gated by ENABLE_DESKTOP) ─────────────────────────────
# Xfce + x11vnc + noVNC only run when the desktop feature is enabled. Xvfb
# above always runs because Playwright browsers need an X display regardless.
if [ "${_DESKTOP}" = "true" ]; then
    # Xfce desktop (as computron). Pass D-Bus address so child inherits it.
    gosu computron bash -c "export DBUS_SESSION_BUS_ADDRESS='$DBUS_SESSION_BUS_ADDRESS' GTK_MODULES=gail:atk-bridge ACCESSIBILITY_ENABLED=1; startxfce4" &
    # Give startxfce4 a moment to spawn xfwm4 before the pgrep check below; without this
    # the check races and we launch a duplicate window manager.
    sleep 2

    # Disable screen blanking, set default cursor
    xset s off -dpms 2>/dev/null || true
    xsetroot -cursor_name left_ptr 2>/dev/null || true

    # Ensure window manager is running (startxfce4 sometimes fails to launch it)
    if ! pgrep -x xfwm4 > /dev/null; then
        gosu computron bash -c "DISPLAY=${DISPLAY} xfwm4 &"
    fi

    # VNC + noVNC bridge so the user can view the desktop in a browser
    gosu computron x11vnc -display "${DISPLAY}" -forever -nopw -noshm -listen 0.0.0.0 -rfbport 5900 -shared -cursor arrow -bg
    websockify --web /usr/share/novnc 0.0.0.0:6080 localhost:5900 &
    echo "Desktop ready on ${DISPLAY}, VNC on 5900, noVNC on 6080"
else
    echo "Desktop disabled (ENABLE_DESKTOP=${_DESKTOP}); Xvfb only on ${DISPLAY}"
fi

# ── App server with auto-restart ─────────────────────────────────────────────
# The loop restarts the app on crash or when killed by container-restart-app.
# SIGTERM (from podman stop) breaks the loop for clean shutdown.
_shutdown=0
trap '_shutdown=1; echo "Received SIGTERM, shutting down..."' SIGTERM

cd /opt/computron
while [ $_shutdown -eq 0 ]; do
    echo "Starting app server..."
    gosu computron python3.12 main.py &
    APP_PID=$!
    wait $APP_PID
    exit_code=$?
    [ $_shutdown -eq 1 ] && break
    echo "App server exited ($exit_code), restarting in 2s..."
    sleep 2
done
