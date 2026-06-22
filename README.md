# Audio Reactive Video Maker v1.5

A Python/Tkinter GUI app that creates audio-reactive MP4 videos using FFmpeg, Pillow, and NumPy.

## Requirements

Install the Python packages:

```bash
python -m pip install pillow numpy
```

FFmpeg and FFprobe must be installed and available on PATH:

```bash
ffmpeg -version
ffprobe -version
```

Run:

```bash
python audio_reactive_video_maker_v5.py
```

## Fixes and Improvements in v5

- Single mode now disables the Random/Overlap effects section.
- Random and Overlap modes enable the effects section.
- Section length moved into **Effects Available for Random and Overlap Mode**.
- Added **Show command output window** checkbox.
- Added **Dark / Light** command output window theme.
- Added **Lightning Storm** effect.
- Added **Audio Reactive Fractal Zoom** effect.
- Fixed Audio Tunnel rectangle crash: `x1 must be greater than or equal to x0`.

## Main Settings

### Audio file
The audio track that drives the visuals. The final render keeps the original audio.

### Output file
The MP4 file to create.

### Background image
Optional fixed background image.

### Background folder
Optional folder of images. If provided, images may be used as backgrounds.

### Resolution
Final video size.

Recommended:
- `1280x720` for fast tests
- `1920x1080` for YouTube
- `2560x1440` for higher quality

### FPS
Frame rate.

Recommended:
- `24` cinematic
- `30` standard/default
- `60` smoother but slower

### Background fit
- `cover`: fills the screen and crops edges if needed
- `contain`: shows the full image with padding

## Visual Mode

### Single effect
Uses the selected single effect for the whole video. The Random/Overlap effects section is disabled in this mode.

### Random by section
Randomly selects effects from the checked effects list. The selection changes every section.

### Overlapping effects
Uses multiple checked effects together. The number of simultaneous effects is controlled by the overlap selector.

## Effects Available for Random and Overlap Mode

### Section length for random
Controls how often effects change in Random mode.

Suggested:
- `8` seconds = fast changing
- `12` seconds = balanced
- `20` seconds = slower and smoother

### Number of overlapping effects
Controls how many effects render at once.

Suggested:
- `1` = clean
- `2` = best default
- `3` = busy/high-energy

## Color Palette

Controls the colors used by generated visuals.

Good pairings:
- Tesla Ball: Electric Blue, Cyberpunk, Purple Neon, Emerald
- Lightning Storm: Electric Blue, Ice, Cyberpunk
- Fire/Solar: Energy Rings, Plasma Field
- Gold: Blooming Fractals, Nebula
- Monochrome: Equalizer Bars, Audio Tunnel

## Effects

### Pulsing Color Field
Full-screen pulsing rings and color clouds.

### Particle Emissions
Glowing particles that burst outward based on volume and bass.

### Tesla Ball
Center orb with colored lightning arcs.

### Lightning Storm
Vertical lightning strikes across the frame.

### Equalizer Bars
Classic bar-style visualizer.

### Energy Rings
Expanding rings from the center.

### Nebula
Soft clouds and glowing gas-like shapes.

### Kaleidoscope
Symmetric rotating geometry.

### Audio Tunnel
Tunnel-like rectangles pulsing with audio.

### Audio Reactive Fractal Zoom
Spiral/fractal zoom pattern that reacts to amplitude.

### Blooming Fractals
Flower-like radial patterns.

### Plasma Field
Animated plasma-like colored wave lines.

## Preview

Use Render Preview first. It creates a short preview using the Preview seconds value.

## Command Output Window

Checking **Show command output window** opens a separate internal output window.

Theme options:
- Dark
- Light

This window shows render progress and FFmpeg output.
