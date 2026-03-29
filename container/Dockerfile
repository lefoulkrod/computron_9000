FROM docker.io/ubuntu:22.04

# ── Environment ───────────────────────────────────────────────────────────────
ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DISPLAY=:99

RUN ln -fs /usr/share/zoneinfo/Etc/UTC /etc/localtime && \
    echo "Etc/UTC" > /etc/timezone

# ── System packages (single apt block) ───────────────────────────────────────
# All apt installs are combined so we only pay for apt-get update once,
# and a single apt-get clean wipes the cache in the same layer.
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
      # Core build tools
      software-properties-common curl gnupg2 xz-utils ca-certificates jq \
      build-essential git sudo unzip wget \
      # Media / OCR
      ffmpeg imagemagick espeak-ng \
      # Search
      ripgrep \
      # Python 3.12 (via deadsnakes PPA)
      python3-pip && \
    add-apt-repository ppa:deadsnakes/ppa && \
    apt-get update && \
    apt-get install -y --no-install-recommends \
      python3.12 python3.12-venv python3.12-dev && \
    # Desktop environment + VNC stack
    apt-get install -y --no-install-recommends \
      xfce4 xfce4-terminal mousepad dbus-x11 \
      xvfb x11vnc websockify novnc \
      xdotool xclip scrot wmctrl tini \
      python3-pyatspi at-spi2-core libatk-adaptor \
      # Browsers
      firefox chromium-browser \
      # Theme + fonts
      elementary-xfce-icon-theme \
      greybird-gtk-theme \
      xcursor-themes dmz-cursor-theme \
      fonts-dejavu-core && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# ── GitHub CLI ────────────────────────────────────────────────────────────────
RUN mkdir -p /etc/apt/keyrings && \
    curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg \
      > /etc/apt/keyrings/githubcli-archive-keyring.gpg && \
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" \
      > /etc/apt/sources.list.d/github-cli.list && \
    apt-get update && \
    apt-get install -y --no-install-recommends gh && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

# ── Node.js LTS ───────────────────────────────────────────────────────────────
RUN set -eux; \
    LTS_VERSION=$(curl -fsSL https://nodejs.org/dist/index.json | \
      jq -r '[.[] | select(.lts != false)][0].version' | sed 's/^v//'); \
    curl -fsSLO "https://nodejs.org/dist/v${LTS_VERSION}/node-v${LTS_VERSION}-linux-x64.tar.xz"; \
    tar -xJf "node-v${LTS_VERSION}-linux-x64.tar.xz" -C /usr/local --strip-components=1 --no-same-owner; \
    rm "node-v${LTS_VERSION}-linux-x64.tar.xz"; \
    ln -sf /usr/local/bin/node /usr/local/bin/nodejs; \
    node -v && npm -v

# ── uv (fast Python package installer) ───────────────────────────────────────
RUN curl -LsSf https://astral.sh/uv/install.sh | sh && \
    cp /root/.local/bin/uv /usr/local/bin/uv && \
    cp /root/.local/bin/uvx /usr/local/bin/uvx

# ── Python setup ──────────────────────────────────────────────────────────────
RUN python3.12 -m ensurepip --upgrade && \
    # Remove PEP 668 guard — container sandbox, no guard needed
    rm -f /usr/lib/python3.12/EXTERNALLY-MANAGED && \
    # Consistent python/pip aliases all pointing at 3.12
    ln -sf /usr/bin/python3.12 /usr/local/bin/python && \
    ln -sf /usr/bin/python3.12 /usr/local/bin/python3 && \
    printf '#!/bin/bash\nexec python3.12 -m pip "$@"\n' > /usr/local/bin/pip && \
    chmod +x /usr/local/bin/pip && \
    ln -sf /usr/local/bin/pip /usr/local/bin/pip3 && \
    # Upgrade pip itself
    python3.12 -m pip install --no-cache-dir --upgrade pip

# ── Fix distutils-installed blinker before Flask pulls it in ─────────────────
# Ubuntu 22.04 ships blinker 1.4 via apt as a distutils package.
# pip cannot uninstall distutils packages, so we force-overwrite it first.
RUN python3.12 -m pip install --no-cache-dir --ignore-installed blinker

# ── Python packages (general) ─────────────────────────────────────────────────
# Kept as a separate layer from torch so a change here doesn't re-download 2.5 GB.
RUN python3.12 -m pip install --no-cache-dir \
      # HTTP / web scraping
      requests httpx \
      beautifulsoup4 lxml \
      # Images
      pillow \
      # Data
      pandas numpy scipy \
      # Visualisation
      matplotlib seaborn plotly \
      # Office docs
      openpyxl xlsxwriter \
      pypdf pymupdf python-docx python-pptx \
      tabulate \
      # Config / templating
      pyyaml toml jinja2 \
      # Math
      sympy \
      # ML (non-torch)
      scikit-learn \
      # Testing
      pytest \
      # TTS
      edge-tts kokoro-onnx soundfile \
      # Web servers
      flask flask-socketio

# ── PyTorch with CUDA ─────────────────────────────────────────────────────────
# Separate layer: ~2.5 GB download, rarely changes, expensive to re-pull.
RUN python3.12 -m pip install --no-cache-dir \
      torch torchaudio torchvision

# ── Pre-download Kokoro TTS model weights ─────────────────────────────────────
# ~88 MB int8 ONNX model — baked in so the agent never fetches at runtime.
RUN mkdir -p /opt/kokoro && \
    wget -q -O /opt/kokoro/kokoro-v1.0.int8.onnx \
      https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/kokoro-v1.0.int8.onnx && \
    wget -q -O /opt/kokoro/voices-v1.0.bin \
      https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/voices-v1.0.bin && \
    chmod -R 755 /opt/kokoro

# ── Non-root user ─────────────────────────────────────────────────────────────
RUN useradd --create-home --shell /bin/bash computron && \
    passwd -d computron && \
    usermod -aG sudo computron && \
    echo 'computron ALL=(ALL) NOPASSWD:ALL' >> /etc/sudoers && \
    chown -R computron:computron /home/computron && \
    chmod 700 /home/computron

# ── Xfce config (theme, icons, cursor, disable power management) ──────────────
RUN mkdir -p /home/computron/.config/xfce4/xfconf/xfce-perchannel-xml && \
    printf '<?xml version="1.0" encoding="UTF-8"?>\n\
<channel name="xsettings" version="1.0">\n\
  <property name="Net" type="empty">\n\
    <property name="ThemeName" type="string" value="Greybird"/>\n\
    <property name="IconThemeName" type="string" value="elementary-xfce-dark"/>\n\
    <property name="CursorThemeName" type="string" value="DMZ-White"/>\n\
    <property name="CursorSize" type="int" value="24"/>\n\
  </property>\n\
</channel>\n' \
      > /home/computron/.config/xfce4/xfconf/xfce-perchannel-xml/xsettings.xml && \
    printf '<?xml version="1.0" encoding="UTF-8"?>\n\
<channel name="xfwm4" version="1.0">\n\
  <property name="general" type="empty">\n\
    <property name="theme" type="string" value="Greybird"/>\n\
  </property>\n\
</channel>\n' \
      > /home/computron/.config/xfce4/xfconf/xfce-perchannel-xml/xfwm4.xml && \
    printf '<?xml version="1.0" encoding="UTF-8"?>\n\
<channel name="xfce4-power-manager" version="1.0">\n\
  <property name="xfce4-power-manager" type="empty">\n\
    <property name="dpms-enabled" type="bool" value="false"/>\n\
    <property name="blank-on-ac" type="int" value="0"/>\n\
    <property name="dpms-on-ac-sleep" type="uint" value="0"/>\n\
    <property name="dpms-on-ac-off" type="uint" value="0"/>\n\
  </property>\n\
</channel>\n' \
      > /home/computron/.config/xfce4/xfconf/xfce-perchannel-xml/xfce4-power-manager.xml && \
    chown -R computron:computron /home/computron/.config && \
    # Ensure DISPLAY=:99 in all interactive/login shells (belt-and-suspenders
    # on top of the container ENV, since --network=host exposes host display).
    printf 'export DISPLAY=:99\n' > /etc/profile.d/display.sh && \
    chmod 644 /etc/profile.d/display.sh

# ── Desktop scripts ───────────────────────────────────────────────────────────
COPY container/entrypoint.sh /opt/entrypoint.sh
COPY container/a11y_tree.py /opt/desktop/a11y_tree.py
RUN chmod +x /opt/entrypoint.sh && \
    chmod 755 /opt/desktop/a11y_tree.py && \
    mkdir -p /tmp/.X11-unix && chmod 1777 /tmp/.X11-unix

# ── Switch to non-root user ───────────────────────────────────────────────────
USER computron
WORKDIR /home/computron

# ── Git config ────────────────────────────────────────────────────────────────
RUN git config --global user.name "larry foulkrod" && \
    git config --global user.email "lefoulkrod@gmail.com" && \
    git config --global credential.helper \
      '!f() { test -n "$GITHUB_TOKEN" && echo "password=$GITHUB_TOKEN"; }; f'

SHELL ["/bin/bash", "-c"]

# tini reaps zombie processes; entrypoint starts desktop then idles
ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["/opt/entrypoint.sh"]