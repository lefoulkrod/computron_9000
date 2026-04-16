FROM docker.io/ubuntu:22.04

# ── Environment ───────────────────────────────────────────────────────────────
ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    LANG=C.UTF-8 \
    DISPLAY=:99

RUN ln -fs /usr/share/zoneinfo/Etc/UTC /etc/localtime && \
    echo "Etc/UTC" > /etc/timezone

# ── System packages ──────────────────────────────────────────────────────────
# Single apt layer — one update, one clean.
# NOTE: python3-pip is deliberately omitted.  We bootstrap pip via ensurepip
# for Python 3.12.  The system python3-pip drags in 3.10-era packages (PIL,
# blinker, …) into /usr/lib/python3/dist-packages/ which 3.12 then picks up,
# causing C-extension ABI mismatches.
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
      # Build tools & CLI
      software-properties-common curl gnupg2 xz-utils ca-certificates jq \
      build-essential git sudo unzip wget gosu file \
      # Media
      ffmpeg imagemagick espeak-ng \
      # Search
      ripgrep && \
    # Python 3.12 via deadsnakes PPA
    add-apt-repository ppa:deadsnakes/ppa && \
    apt-get update && \
    apt-get install -y --no-install-recommends \
      python3.12 python3.12-venv python3.12-dev && \
    # Desktop environment + VNC
    apt-get install -y --no-install-recommends \
      xfce4 xfce4-terminal mousepad dbus-x11 \
      xvfb x11vnc websockify novnc \
      xdotool xclip scrot wmctrl tini \
      # Accessibility (used by a11y_tree.py under system Python 3.10)
      python3-pyatspi at-spi2-core libatk-adaptor \
      # Theme + fonts
      elementary-xfce-icon-theme \
      greybird-gtk-theme \
      xcursor-themes dmz-cursor-theme \
      fonts-dejavu-core && \
    # Clean up system Python packages that leak into 3.12's import path.
    # These are 3.10-compiled C extensions — they segfault or ImportError
    # when loaded by 3.12.  We install proper versions via pip below.
    rm -rf /usr/lib/python3/dist-packages/PIL \
           /usr/lib/python3/dist-packages/Pillow* \
           /usr/lib/python3/dist-packages/blinker* && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# ── Google Chrome (browser automation) ───────────────────────────────────────
RUN curl -fsSL https://dl.google.com/linux/linux_signing_key.pub \
      | gpg --dearmor -o /etc/apt/keyrings/google-chrome.gpg && \
    echo "deb [arch=amd64 signed-by=/etc/apt/keyrings/google-chrome.gpg] \
      https://dl.google.com/linux/chrome/deb/ stable main" \
      > /etc/apt/sources.list.d/google-chrome.list && \
    apt-get update && \
    apt-get install -y --no-install-recommends google-chrome-stable && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

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

# ── Python 3.12 setup ────────────────────────────────────────────────────────
RUN python3.12 -m ensurepip --upgrade && \
    rm -f /usr/lib/python3.12/EXTERNALLY-MANAGED && \
    # Consistent python/pip aliases
    ln -sf /usr/bin/python3.12 /usr/local/bin/python && \
    ln -sf /usr/bin/python3.12 /usr/local/bin/python3 && \
    printf '#!/bin/bash\nexec python3.12 -m pip "$@"\n' > /usr/local/bin/pip && \
    chmod +x /usr/local/bin/pip && \
    ln -sf /usr/local/bin/pip /usr/local/bin/pip3 && \
    python3.12 -m pip install --no-cache-dir --upgrade pip

# ── PyTorch + CUDA ────────────────────────────────────────────────────────────
# ~2.5 GB — separate layer, rarely changes. Placed before agent packages so
# additions to the package list below don't bust this expensive cache layer.
RUN python3.12 -m pip install --no-cache-dir \
      torch torchaudio torchvision

# ── Agent packages (general) ─────────────────────────────────────────────────
# Pre-installed so the agent can import them immediately without pip install.
RUN python3.12 -m pip install --no-cache-dir \
      # HTTP / scraping
      requests httpx beautifulsoup4 lxml \
      # Images / vision
      pillow opencv-python-headless \
      # Data / math
      pandas numpy scipy sympy scikit-learn \
      # Visualisation
      matplotlib seaborn plotly \
      # Office documents
      openpyxl xlsxwriter tabulate \
      pypdf pymupdf python-docx python-pptx \
      # Config / templating
      pyyaml toml jinja2 \
      # Audio
      soundfile \
      # TTS
      edge-tts kokoro-onnx \
      # Testing
      pytest \
      # Web servers (agent can build quick prototypes)
      flask flask-socketio blinker

# ── Image generation (Flux via diffusers) ─────────────────────────────────────
RUN python3.12 -m pip install --no-cache-dir \
      git+https://github.com/huggingface/diffusers.git \
      "transformers>=4.51.0,<4.58.0" accelerate safetensors sentencepiece protobuf \
      "huggingface_hub[cli]" bitsandbytes ftfy

# ── Music generation (ACE-Step 1.5) ──────────────────────────────────────────
RUN git clone --depth 1 https://github.com/ace-step/ACE-Step-1.5.git /tmp/ace-step-1.5 && \
    python3.12 -m pip install --no-cache-dir /tmp/ace-step-1.5/acestep/third_parts/nano-vllm && \
    python3.12 -m pip install --no-cache-dir --no-deps /tmp/ace-step-1.5 && \
    python3.12 -m pip install --no-cache-dir \
      einops "vector-quantize-pytorch>=1.27.15" "torchcodec>=0.9.1" \
      "torchao>=0.16.0,<0.17.0" numba loguru diskcache modelscope \
      "peft>=0.18.0" lycoris-lora && \
    rm -rf /tmp/ace-step-1.5

# ── Pre-downloaded models ────────────────────────────────────────────────────
# Baked in so the agent never fetches at runtime.

# TAESD — fast image preview decoding (~10 MB)
RUN python3.12 -c "from diffusers import AutoencoderTiny; AutoencoderTiny.from_pretrained('madebyollin/taef1')"

# Kokoro TTS — int8 ONNX voice model (~88 MB)
RUN mkdir -p /opt/kokoro && \
    wget -q -O /opt/kokoro/kokoro-v1.0.int8.onnx \
      https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/kokoro-v1.0.int8.onnx && \
    wget -q -O /opt/kokoro/voices-v1.0.bin \
      https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/voices-v1.0.bin && \
    chmod -R 755 /opt/kokoro

# ── User & permissions ───────────────────────────────────────────────────────
# Single user: computron runs the app server, agent tools, and desktop.
# App code is root-owned (read-only). State and home are both owned by computron.
RUN useradd --create-home --shell /bin/bash --uid 1000 computron && \
    passwd -d computron && \
    mkdir -p /var/lib/computron && \
    chown computron:computron /var/lib/computron && \
    chmod 755 /var/lib/computron && \
    chown -R computron:computron /home/computron && \
    mkdir -p /home/computron/Desktop && \
    mkdir -p /home/computron/downloads && \
    # Sudoers: computron can install packages as root
    echo "computron ALL=(root) NOPASSWD: /usr/bin/apt-get, /usr/local/bin/pip, /usr/local/bin/npm" \
      > /etc/sudoers.d/computron && \
    chmod 440 /etc/sudoers.d/computron

# ── Xfce config ──────────────────────────────────────────────────────────────
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
    printf 'export DISPLAY=:99\n' > /etc/profile.d/display.sh && \
    chmod 644 /etc/profile.d/display.sh

# ── Desktop scripts ───────────────────────────────────────────────────────────
COPY container/a11y_tree.py /opt/desktop/a11y_tree.py
RUN chmod 755 /opt/desktop/a11y_tree.py && \
    mkdir -p /tmp/.X11-unix && chmod 1777 /tmp/.X11-unix

# ── App dependencies (cached unless manifests change) ────────────────────────
WORKDIR /opt/computron
COPY pyproject.toml uv.lock ./
RUN uv pip install --system --no-cache -e . 2>/dev/null || true

COPY server/ui/package.json server/ui/package-lock.json server/ui/
RUN cd server/ui && npm ci

# ── App source ───────────────────────────────────────────────────────────────
COPY --chmod=755 . /opt/computron/
RUN uv pip install --system --no-cache -e .
RUN cd server/ui && npm run build

# ── Entrypoint (late COPY so edits don't bust app/UI cache) ─────────────────
COPY container/entrypoint.sh /opt/entrypoint.sh
RUN chmod +x /opt/entrypoint.sh

SHELL ["/bin/bash", "-c"]

EXPOSE 8080 5900 6080

# tini reaps zombie processes; entrypoint starts desktop then app server
ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["/opt/entrypoint.sh"]
