# stt-nix

Simple speech-to-text for NixOS. Runs locally on your GPU or uses the Groq API.

## Features

- **Local GPU transcription** via [faster-whisper](https://github.com/SYSTRAN/faster-whisper) (CUDA)
- **Groq API** as a cloud alternative
- **System tray icon** showing idle/recording/transcribing state
- **Push-to-talk**: toggle mode (press to start/stop) or hold-to-talk (via evdev)
- **Clipboard-paste output**: text is pasted into the focused window, no spacing issues
- Auto-detects CUDA availability, falls back to CPU

## Install

### With Cachix (pre-built, no compilation)

```bash
# Add the binary cache (skip the long CUDA build)
nix run nixpkgs#cachix -- use stt-nix

# Run directly
nix run github:max-miller1204/stt-nix

# Or install to your profile
nix profile install github:max-miller1204/stt-nix
```

### In a flake

```nix
{
  inputs.stt-nix.url = "github:max-miller1204/stt-nix";

  # Add to your packages
  environment.systemPackages = [ inputs.stt-nix.packages.x86_64-linux.default ];
}
```

### CPU-only (no CUDA needed, fast build)

```bash
nix run github:max-miller1204/stt-nix#cpu
```

## Usage

### Start the daemon

```bash
stt-nix
```

This starts the background daemon with a system tray icon.

### Control via CLI

```bash
stt toggle          # Toggle recording on/off (default if no subcommand)
stt start           # Start recording
stt stop            # Stop recording and transcribe
stt status          # Show current state (idle/recording/transcribing)
stt download-model base  # Pre-download a model (tiny/base/small/medium)
```

### Keybinding (niri example)

```kdl
binds {
    Ctrl+Space { spawn "stt" "toggle"; }
}
```

## Configuration

Create `~/.config/stt-nix/config.toml`:

```toml
[transcription]
backend = "local"       # "local" or "groq"
model = "base"          # tiny, base, small, medium
language = "en"         # or "auto" for detection
device = "auto"         # "auto", "cuda", or "cpu"
compute_type = "auto"   # "auto", "float16", "int8", etc.

[groq]
api_key = ""            # or set GROQ_API_KEY env var

[output]
paste_delay_ms = 100

[hotkey]
enabled = false
key = "KEY_RIGHTALT"    # evdev key name
mode = "hold"           # "hold" or "toggle"
```

All settings are optional. Defaults work out of the box.

### Using Groq API

```toml
[transcription]
backend = "groq"

[groq]
api_key = "gsk_..."
```

Or just set `GROQ_API_KEY` in your environment.

## Model sizes

| Model  | VRAM   | Speed   | Accuracy |
|--------|--------|---------|----------|
| tiny   | ~75MB  | Fastest | Lower    |
| base   | ~150MB | Fast    | Good     |
| small  | ~500MB | Medium  | Better   |
| medium | ~1.5GB | Slower  | Best     |

Models download automatically on first use. Pre-download with `stt download-model <size>`.

## Hold-to-talk

Hold-to-talk uses evdev to monitor key events directly. Your user must be in the `input` group:

```bash
sudo usermod -aG input $USER
```

Or in NixOS configuration:

```nix
users.users.yourname.extraGroups = [ "input" ];
```

Then enable in config:

```toml
[hotkey]
enabled = true
key = "KEY_RIGHTALT"
mode = "hold"
```

## Requirements

- NixOS with PipeWire
- Wayland compositor (uses `wtype` and `wl-clipboard`)
- NVIDIA GPU for local CUDA transcription (optional, CPU works too)
