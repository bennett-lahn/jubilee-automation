FROM python:3.12-slim

# Install system dependencies for Kivy and general build tools
RUN apt-get update && apt-get install -y \
    build-essential \
    python3-dev \
    libsdl2-dev \
    libsdl2-image-dev \
    libsdl2-mixer-dev \
    libsdl2-ttf-dev \
    libportmidi-dev \
    libswscale-dev \
    libavformat-dev \
    libavcodec-dev \
    zlib1g-dev \
    libgstreamer1.0-0 \
    gstreamer1.0-plugins-base \
    gstreamer1.0-plugins-good \
    libasound2-dev \
    libpulse-dev \
    libaudio-dev \
    libjack-dev \
    libsndio-dev \
    libsamplerate0-dev \
    libx11-dev \
    libxext-dev \
    libxrandr-dev \
    libxcursor-dev \
    libxfixes-dev \
    libxi-dev \
    libxss-dev \
    libwayland-dev \
    libxkbcommon-dev \
    libdrm-dev \
    libgbm-dev \
    libgl1-mesa-dev \
    libgles2-mesa-dev \
    libegl1-mesa-dev \
    libdbus-1-dev \
    libibus-1.0-dev \
    libudev-dev \
    fcitx-libs-dev \
    git \
    tesseract-ocr \
    libtesseract-dev \
    libleptonica-dev \
    pkg-config \
    && rm -rf /var/lib/apt/lists/*

# Set environment variables for Kivy
ENV KIVY_GL_BACKEND=sdl2 \
    KIVY_WINDOW=sdl2

# Set workdir
WORKDIR /app

# Copy requirements and install Python dependencies
COPY requirements.txt ./
RUN pip install --upgrade pip && pip install -r requirements.txt

# Copy the rest of the code
COPY . .

# Default command (can be overridden)
CMD ["python", "jubilee_gui.py"] 