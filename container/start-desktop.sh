#!/bin/bash
set -euo pipefail
export DISPLAY=:1

# Start Xvfb (virtual framebuffer) at 1280x720
Xvfb :1 -screen 0 1280x720x24 -ac &
sleep 1

# Start dbus session (needed by Xfce and desktop integration)
eval $(dbus-launch --sh-syntax)
export DBUS_SESSION_BUS_ADDRESS

# Disable Xfce power management to prevent screen blanking/suspend
mkdir -p /home/computron/.config/xfce4/xfconf/xfce-perchannel-xml
# Set Xfce appearance: Greybird theme, elementary icons, DMZ cursor
cat > /home/computron/.config/xfce4/xfconf/xfce-perchannel-xml/xsettings.xml <<'XSETTINGS'
<?xml version="1.0" encoding="UTF-8"?>
<channel name="xsettings" version="1.0">
  <property name="Net" type="empty">
    <property name="ThemeName" type="string" value="Greybird"/>
    <property name="IconThemeName" type="string" value="elementary-xfce-dark"/>
    <property name="CursorThemeName" type="string" value="DMZ-White"/>
    <property name="CursorSize" type="int" value="24"/>
  </property>
</channel>
XSETTINGS

cat > /home/computron/.config/xfce4/xfconf/xfce-perchannel-xml/xfwm4.xml <<'XFWM4'
<?xml version="1.0" encoding="UTF-8"?>
<channel name="xfwm4" version="1.0">
  <property name="general" type="empty">
    <property name="theme" type="string" value="Greybird"/>
  </property>
</channel>
XFWM4

cat > /home/computron/.config/xfce4/xfconf/xfce-perchannel-xml/xfce4-power-manager.xml <<'XFCE_PM'
<?xml version="1.0" encoding="UTF-8"?>
<channel name="xfce4-power-manager" version="1.0">
  <property name="xfce4-power-manager" type="empty">
    <property name="dpms-enabled" type="bool" value="false"/>
    <property name="blank-on-ac" type="int" value="0"/>
    <property name="dpms-on-ac-sleep" type="uint" value="0"/>
    <property name="dpms-on-ac-off" type="uint" value="0"/>
  </property>
</channel>
XFCE_PM

# Start Xfce desktop
startxfce4 &
sleep 2

# Disable screen saver/blanking via xset (belt and suspenders)
xset s off -dpms 2>/dev/null || true

# VNC server on port 5900 (no password, shared mode)
x11vnc -display :1 -forever -nopw -listen 0.0.0.0 -rfbport 5900 -shared -cursor arrow -bg

# websockify on port 6080 -> VNC 5900 (serves noVNC web client too)
websockify --web /usr/share/novnc 0.0.0.0:6080 localhost:5900 &

echo "Desktop ready on :1, VNC on 5900, WebSocket on 6080"
wait
