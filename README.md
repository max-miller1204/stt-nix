# stt-nix

Simple speech-to-text for NixOS. Runs locally on your GPU or uses the Groq API.

## Features

- **Local GPU transcription** via [faster-whisper](https://github.com/SYSTRAN/faster-whisper) (CUDA)
- **Groq API** as a cloud alternative
- **System tray icon** showing idle/recording/transcribing state
- **Hold-to-talk** or **toggle** hotkey with modifier support (e.g. `ctrl+space`)
- **Clipboard-paste output** via `dotool` — configurable paste keystroke
- Auto-detects CUDA availability, falls back to CPU

## Install

### Home Manager module (recommended)

```nix
# flake.nix
{
  inputs.stt-nix.url = "github:max-miller1204/stt-nix";
}

# In your Home Manager config:
{
  imports = [ inputs.stt-nix.homeManagerModules.default ];

  services.stt-nix = {
    enable = true;
    groqApiKeyFile = "/path/to/env-file"; # file containing GROQ_API_KEY=gsk_...
    settings = {
      transcription = {
        backend = "groq";
        language = "en";
      };
      output.paste_key = "ctrl+shift+v";
      hotkey = {
        enabled = true;
        key = "ctrl+space";
        mode = "hold";
      };
    };
  };
}
```

This creates a systemd user service that starts with your graphical session.

### With overlay

```nix
{
  inputs.stt-nix.url = "github:max-miller1204/stt-nix";

  # Add overlay
  nixpkgs.overlays = [ inputs.stt-nix.overlays.default ];

  # Provides: pkgs.stt-nix (CPU) and pkgs.stt-nix-cuda
  environment.systemPackages = [ pkgs.stt-nix ];
}
```

### Run directly

```bash
# CPU-only (fast build)
nix run github:max-miller1204/stt-nix#cpu

# With CUDA
nix run github:max-miller1204/stt-nix
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
paste_key = "ctrl+v"    # "ctrl+shift+v" for terminals

[hotkey]
enabled = false
key = "ctrl+space"      # supports modifiers: ctrl, shift, alt, super
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

## Requirements

- NixOS with PipeWire
- Wayland compositor (uses `wl-clipboard` and `dotool`)
- NVIDIA GPU for local CUDA transcription (optional, CPU works too)
