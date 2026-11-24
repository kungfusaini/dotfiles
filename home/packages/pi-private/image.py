"""One-shot private image worker. JSON stdin/stdout; all inference stays in the sandbox."""
import base64
import io
import json
import os
from pathlib import Path
import secrets
import signal
import subprocess
import sys
import tempfile
import time
import urllib.request

from PIL import Image

MODEL = Path("/image-model.safetensors")
OUTPUT = Path("/images")
BASE_URL = "http://127.0.0.1:18081"
MAX_PROMPT = 4000
PRESETS = {
    "fast": {"size": 512, "steps": 20, "sampler": "euler", "scheduler": "discrete",
             "timeout": 240, "response_limit": 4 * 1024 * 1024},
    "quality": {"size": 1024, "steps": 35, "sampler": "dpm++2m", "scheduler": "karras",
                "timeout": 600, "response_limit": 16 * 1024 * 1024},
}


def preset_config(preset):
    if not isinstance(preset, str) or preset not in PRESETS:
        raise ValueError("Only fast and quality image presets are supported.")
    return PRESETS[preset]


def validate_prompt(value):
    if not isinstance(value, str) or not value.strip() or len(value) > MAX_PROMPT:
        raise ValueError("Use /image followed by a description of 1–4000 characters.")
    # sd-server interprets these tags as configuration, not natural-language text.
    if "<sd_cpp_extra_args" in value.lower():
        raise ValueError("Image descriptions cannot contain backend configuration tags.")
    if any(ord(c) < 32 and c not in "\n\t" for c in value):
        raise ValueError("Image descriptions cannot contain terminal control characters.")
    return value.strip()


def server_command(preset="quality"):
    config = preset_config(preset)
    command = ["@sdServer@", "-m", str(MODEL), "--backend", "vulkan0",
            "--listen-ip", "127.0.0.1", "--listen-port", "18081", "--threads", "4",
            "--steps", str(config["steps"]), "--cfg-scale", "5",
            "--sampling-method", config["sampler"], "--scheduler", config["scheduler"],
            "--disable-image-metadata"]
    if preset == "quality":
        # A full 1024px VAE graph exceeds this Intel driver's single-buffer
        # limit. Decode overlapping 512px tiles on the same GPU instead.
        command += ["--vae-tiling", "--vae-tile-size", "64x64", "--vae-tile-overlap", "0.5"]
    return command


def stop_server(server):
    # Repeated Escape/Ctrl-C must not interrupt termination/reaping.
    signal.signal(signal.SIGTERM, signal.SIG_IGN)
    signal.signal(signal.SIGINT, signal.SIG_IGN)
    server.terminate()
    try:
        server.wait(timeout=5)
    except subprocess.TimeoutExpired:
        server.kill()
        server.wait()


def generate(prompt, preset="quality"):
    prompt = validate_prompt(prompt)
    config = preset_config(preset)
    size = config["size"]
    if not MODEL.is_file():
        raise RuntimeError("The local Juggernaut XL weights are missing; no download or cloud fallback.")
    if not OUTPUT.is_dir() or OUTPUT.is_symlink():
        raise RuntimeError("Private image storage is unavailable.")
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    started = time.monotonic()
    # Never write server logs or request/response diagnostics to persistent storage.
    with tempfile.TemporaryFile() as log:
        server = subprocess.Popen(server_command(preset), stdout=log, stderr=log, close_fds=True)
        try:
            deadline = time.monotonic() + 120
            while True:
                if server.poll() is not None:
                    raise RuntimeError("The private image model failed to start; no fallback.")
                try:
                    with opener.open(BASE_URL + "/v1/models", timeout=1) as response:
                        if response.status == 200:
                            break
                except OSError:
                    if time.monotonic() > deadline:
                        raise RuntimeError("The private image model startup timed out.") from None
                    time.sleep(0.25)
            request = urllib.request.Request(BASE_URL + "/v1/images/generations",
                headers={"Content-Type": "application/json"},
                data=json.dumps({"prompt": prompt, "n": 1, "size": f"{size}x{size}",
                                 "output_format": "png"}).encode())
            with opener.open(request, timeout=config["timeout"]) as response:
                raw = response.read(config["response_limit"] + 1)
            if len(raw) > config["response_limit"]:
                raise RuntimeError("The private image response exceeded its size limit.")
            data = json.loads(raw)
            png = base64.b64decode(data["data"][0]["b64_json"], validate=True)
            with Image.open(io.BytesIO(png)) as source:
                if source.format != "PNG" or source.size != (size, size):
                    raise RuntimeError("The private image model returned an unexpected image.")
                # Re-encode pixels only: do not persist prompt metadata from the backend.
                pixels = source.convert("RGB")
                clean = Image.frombytes("RGB", pixels.size, pixels.tobytes())
            filename = secrets.token_hex(16) + ".png"
            # Publish a complete mode-0600 PNG without replacing any existing file.
            with tempfile.NamedTemporaryFile(dir=OUTPUT, prefix=".pending-") as target:
                clean.save(target, format="PNG")
                target.flush()
                os.link(target.name, OUTPUT / filename)
            preview = clean.resize((64, 64), Image.Resampling.LANCZOS)
            return {"filename": filename, "width": size, "height": size, "preset": preset,
                    "preview": base64.b64encode(preview.tobytes()).decode("ascii"),
                    "seconds": round(time.monotonic() - started, 1)}
        finally:
            stop_server(server)


def terminate(_signum, _frame):
    raise SystemExit(143)


def main():
    os.umask(0o077)
    signal.signal(signal.SIGTERM, terminate)
    signal.signal(signal.SIGINT, terminate)
    try:
        raw = sys.stdin.read(20000)
        request = json.loads(raw)
        if not isinstance(request, dict) or set(request) not in ({"prompt"}, {"prompt", "preset"}):
            raise ValueError("Only an image description and a named preset are accepted.")
        print(json.dumps(generate(request["prompt"], request.get("preset", "quality"))))
        return 0
    except ValueError as error:
        print(json.dumps({"error": str(error)}))
    except Exception:
        # Do not echo HTTP errors, backend diagnostics, prompt data or paths.
        print(json.dumps({"error": "Private image generation failed; nothing was sent to a cloud service."}))
    return 1


if __name__ == "__main__":
    sys.exit(main())
