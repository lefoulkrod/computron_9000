FROM docker.io/nvidia/cuda:12.4.1-runtime-ubuntu22.04

# Non-interactive + UTC timezone
ENV DEBIAN_FRONTEND=noninteractive
ENV NVIDIA_VISIBLE_DEVICES=all
ENV NVIDIA_DRIVER_CAPABILITIES=compute,utility
RUN ln -fs /usr/share/zoneinfo/Etc/UTC /etc/localtime && \
    echo "Etc/UTC" > /etc/timezone

# System deps for Python, Node, compiling packages, etc.
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
      software-properties-common curl gnupg2 xz-utils ca-certificates jq \
      build-essential git sudo unzip wget \
      ffmpeg imagemagick espeak-ng \
      ripgrep && \
    add-apt-repository ppa:deadsnakes/ppa && \
    apt-get update && \
    apt-get install -y --no-install-recommends \
      python3.12 python3.12-venv python3-pip && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

RUN curl -LsSf https://astral.sh/uv/install.sh | sh && \
    cp /root/.local/bin/uv /usr/local/bin/uv && \
    cp /root/.local/bin/uvx /usr/local/bin/uvx

# Install latest Node.js LTS
RUN set -eux; \
    LTS_VERSION=$(curl -fsSL https://nodejs.org/dist/index.json | jq -r '[.[] | select(.lts != false)][0].version' | sed 's/^v//'); \
    curl -fsSLO "https://nodejs.org/dist/v${LTS_VERSION}/node-v${LTS_VERSION}-linux-x64.tar.xz"; \
    tar -xJf "node-v${LTS_VERSION}-linux-x64.tar.xz" -C /usr/local --strip-components=1 --no-same-owner; \
    rm "node-v${LTS_VERSION}-linux-x64.tar.xz"; \
    ln -sf /usr/local/bin/node /usr/local/bin/nodejs; \
    node -v && npm -v

# Create non-root user 'computron' with sudo (no password)
RUN useradd --create-home --shell /bin/bash computron && \
    passwd -d computron && \
    usermod -aG sudo computron && \
    echo 'computron ALL=(ALL) NOPASSWD:ALL' >> /etc/sudoers && \
    chown -R computron:computron /home/computron && \
    chmod 700 /home/computron

# python, python3, pip, pip3 all target Python 3.12
RUN python3.12 -m ensurepip --upgrade && \
    # Remove PEP 668 guard — running as root in a sandbox, no guard needed
    rm -f /usr/lib/python3.12/EXTERNALLY-MANAGED && \
    # Consistent python aliases
    ln -sf /usr/bin/python3.12 /usr/local/bin/python && \
    ln -sf /usr/bin/python3.12 /usr/local/bin/python3 && \
    # pip wrapper scripts — always invoke python3.12's pip regardless of PATH quirks
    printf '#!/bin/bash\nexec python3.12 -m pip "$@"\n' > /usr/local/bin/pip && \
    chmod +x /usr/local/bin/pip && \
    ln -sf /usr/local/bin/pip /usr/local/bin/pip3

# Pre-install commonly needed Python packages so the agent avoids repeated pip calls
RUN python3.12 -m pip install --no-cache-dir \
      requests httpx \
      beautifulsoup4 lxml \
      pillow \
      pandas numpy scipy \
      matplotlib seaborn plotly \
      openpyxl xlsxwriter \
      pypdf pymupdf python-docx python-pptx \
      tabulate \
      pyyaml toml \
      jinja2 \
      sympy \
      scikit-learn \
      pytest \
      edge-tts \
      kokoro-onnx soundfile

# PyTorch with CUDA 12.4 support for GPU-accelerated workloads (e.g. Stable Diffusion).
# Pin exact versions — torch/torchvision/torchaudio must stay in lockstep.
# Unpinned installs (e.g. agent running `pip install torch`) will silently
# pull a mismatched version and break torchvision op registration.
RUN python3.12 -m pip install --no-cache-dir \
      torch==2.6.0 torchvision==0.21.0 torchaudio==2.6.0 \
      --index-url https://download.pytorch.org/whl/cu124

# Image generation stack (Flux + FLUX.2 klein via HuggingFace diffusers)
# Install diffusers from git main for Flux2KleinPipeline support.
# --no-deps on torch-dependent packages to prevent pip from upgrading torch.
RUN python3.12 -m pip install --no-cache-dir \
      git+https://github.com/huggingface/diffusers.git \
      transformers accelerate safetensors sentencepiece protobuf \
      "huggingface_hub[cli]" bitsandbytes ftfy opencv-python-headless

# Pre-download TAESD (AutoencoderTiny) for cheap image preview decoding (~50 MB).
# Used by the inference server to stream denoising previews during generation.
RUN python3.12 -c "from diffusers import AutoencoderTiny; AutoencoderTiny.from_pretrained('madebyollin/taef1')"

# Pre-download Kokoro-82M model files (int8 quantized, ~88 MB) so the agent
# can use TTS without fetching weights at runtime.
RUN mkdir -p /opt/kokoro && \
    wget -q -O /opt/kokoro/kokoro-v1.0.int8.onnx \
      https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/kokoro-v1.0.int8.onnx && \
    wget -q -O /opt/kokoro/voices-v1.0.bin \
      https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/voices-v1.0.bin && \
    chmod -R 755 /opt/kokoro

# Desktop environment for computer use (on-demand, started via start-desktop.sh)
RUN apt-get update && apt-get install -y --no-install-recommends \
    xfce4 xfce4-terminal dbus-x11 \
    xvfb x11vnc websockify novnc \
    xdotool xclip scrot wmctrl tini \
    # Cursor + theme packages for usable desktop appearance
    elementary-xfce-icon-theme \
    greybird-gtk-theme \
    xcursor-themes dmz-cursor-theme \
    fonts-dejavu-core \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# Inference server scripts — baked into the image so the container is self-contained.
# Placed outside the agent's home directory so agents can't read or modify them.
COPY container/inference_server.py container/inference_client.py /opt/inference/
COPY container/grounding_server.py container/grounding_client.py /opt/inference/
RUN chmod -R 755 /opt/inference

# Xfce desktop config (theme, icons, cursor, disable power management)
RUN mkdir -p /home/computron/.config/xfce4/xfconf/xfce-perchannel-xml && \
    printf '<?xml version="1.0" encoding="UTF-8"?>\n<channel name="xsettings" version="1.0">\n  <property name="Net" type="empty">\n    <property name="ThemeName" type="string" value="Greybird"/>\n    <property name="IconThemeName" type="string" value="elementary-xfce-dark"/>\n    <property name="CursorThemeName" type="string" value="DMZ-White"/>\n    <property name="CursorSize" type="int" value="24"/>\n  </property>\n</channel>\n' \
      > /home/computron/.config/xfce4/xfconf/xfce-perchannel-xml/xsettings.xml && \
    printf '<?xml version="1.0" encoding="UTF-8"?>\n<channel name="xfwm4" version="1.0">\n  <property name="general" type="empty">\n    <property name="theme" type="string" value="Greybird"/>\n  </property>\n</channel>\n' \
      > /home/computron/.config/xfce4/xfconf/xfce-perchannel-xml/xfwm4.xml && \
    printf '<?xml version="1.0" encoding="UTF-8"?>\n<channel name="xfce4-power-manager" version="1.0">\n  <property name="xfce4-power-manager" type="empty">\n    <property name="dpms-enabled" type="bool" value="false"/>\n    <property name="blank-on-ac" type="int" value="0"/>\n    <property name="dpms-on-ac-sleep" type="uint" value="0"/>\n    <property name="dpms-on-ac-off" type="uint" value="0"/>\n  </property>\n</channel>\n' \
      > /home/computron/.config/xfce4/xfconf/xfce-perchannel-xml/xfce4-power-manager.xml && \
    chown -R computron:computron /home/computron/.config

# Container entrypoint — starts desktop environment on boot
COPY container/entrypoint.sh /opt/entrypoint.sh
RUN chmod +x /opt/entrypoint.sh && \
    mkdir -p /tmp/.X11-unix && chmod 1777 /tmp/.X11-unix

# Switch to non-root user (safer sandbox)
USER computron
WORKDIR /home/computron

SHELL ["/bin/bash", "-c"]

# tini reaps zombie processes; entrypoint starts desktop then idles
ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["/opt/entrypoint.sh"]
