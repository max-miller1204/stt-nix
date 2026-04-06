import argparse
import json
import os
import socket
import sys


def get_socket_path() -> str:
    runtime = os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}")
    return os.path.join(runtime, "stt-nix.sock")


def send_command(cmd: dict) -> dict | None:
    path = get_socket_path()
    try:
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.connect(path)
        sock.sendall(json.dumps(cmd).encode() + b"\n")
        data = sock.recv(4096)
        sock.close()
        return json.loads(data.decode())
    except ConnectionRefusedError:
        print("Error: stt-nix daemon is not running", file=sys.stderr)
        sys.exit(1)
    except FileNotFoundError:
        print("Error: stt-nix daemon is not running", file=sys.stderr)
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(prog="stt", description="Speech-to-text CLI")
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("toggle", help="Toggle recording on/off")
    sub.add_parser("start", help="Start recording")
    sub.add_parser("stop", help="Stop recording and transcribe")
    sub.add_parser("status", help="Show daemon status")

    dl = sub.add_parser("download-model", help="Pre-download a whisper model")
    dl.add_argument("size", choices=["tiny", "base", "small", "medium"])

    args = parser.parse_args()

    if not args.command:
        # Default to toggle
        args.command = "toggle"

    if args.command == "download-model":
        from faster_whisper import WhisperModel
        print(f"Downloading model '{args.size}'...")
        WhisperModel(args.size)
        print("Done.")
        return

    resp = send_command({"cmd": args.command})
    if resp:
        if "error" in resp:
            print(f"Error: {resp['error']}", file=sys.stderr)
        elif "state" in resp:
            print(resp["state"])
        elif "ok" in resp:
            pass  # silent success


if __name__ == "__main__":
    main()
