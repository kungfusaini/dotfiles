#!/usr/bin/env python3
"""Make a separate, consistently padded PNG without changing the generated original."""

import argparse
import hashlib
import io
import json
import os
from pathlib import Path

from PIL import Image, ImageOps

ALPHA_THRESHOLD = 16
FILL = 0.90


def visible_bounds(image):
    """Ignore almost-invisible alpha noise when measuring the actual silhouette."""
    return image.getchannel("A").point(lambda alpha: 255 if alpha >= ALPHA_THRESHOLD else 0).getbbox()


def normalize(input_path, output_path, size=1024):
    input_path, output_path = Path(input_path), Path(output_path)
    if not 32 <= size <= 4096:
        raise ValueError("Canvas size must be between 32 and 4096 pixels.")
    if input_path.resolve() == output_path.resolve():
        raise ValueError("Use a separate output file; originals must not be overwritten.")
    if output_path.suffix.lower() != ".png":
        raise ValueError("Normalized output must be a PNG.")
    source = input_path.read_bytes()
    with Image.open(io.BytesIO(source)) as original:
        if getattr(original, "n_frames", 1) != 1:
            raise ValueError("Animated images need a separate workflow.")
        image = ImageOps.exif_transpose(original).convert("RGBA")
    if image.getchannel("A").getextrema()[0] == 255:
        raise ValueError("Opaque input: establish real transparency before normalizing; do not colour-trim.")
    bounds = visible_bounds(image)
    if bounds is None:
        raise ValueError("No visible subject at alpha >= 16; inspect the original rather than invent a crop.")
    left, top, right, bottom = bounds
    scale = round(size * FILL) / max(right - left, bottom - top)
    # Keep nearby antialiasing without allowing distant alpha=1 specks to set the crop.
    # Bound the feather for tiny/upscaled sources so the complete crop still fits.
    feather = min(2, int((size - round(size * FILL)) / (2 * scale)))
    crop = image.crop((max(0, left - feather), max(0, top - feather),
                       min(image.width, right + feather), min(image.height, bottom + feather)))
    scaled = crop.resize((max(1, round(crop.width * scale)), max(1, round(crop.height * scale))),
                         Image.Resampling.LANCZOS)
    scaled_bounds = visible_bounds(scaled)
    if scaled_bounds is None:
        raise ValueError("Subject disappeared during resizing.")
    # Upsampling can expand the measured soft edge. Correct that measured size,
    # proportionally, instead of assuming requested dimensions equal visible bounds.
    longest = max(scaled_bounds[2] - scaled_bounds[0], scaled_bounds[3] - scaled_bounds[1])
    correction = round(size * FILL) / longest
    if abs(longest - round(size * FILL)) > 1:
        scaled = scaled.resize((max(1, round(scaled.width * correction)),
                                max(1, round(scaled.height * correction))), Image.Resampling.LANCZOS)
        scaled_bounds = visible_bounds(scaled)
        if scaled_bounds is None:
            raise ValueError("Subject disappeared during edge correction.")
    x = round((size - scaled_bounds[0] - scaled_bounds[2]) / 2)
    y = round((size - scaled_bounds[1] - scaled_bounds[3]) / 2)
    if (x + scaled_bounds[0] < 0 or y + scaled_bounds[1] < 0 or
            x + scaled_bounds[2] > size or y + scaled_bounds[3] > size):
        raise ValueError("Visible subject does not fit the canvas; inspect this input manually.")
    canvas = Image.new("RGBA", (size, size))
    canvas.alpha_composite(scaled, (x, y))
    encoded = io.BytesIO()
    canvas.save(encoded, format="PNG", optimize=True)
    output_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    # Exclusive creation also rejects symlink destinations. No --force/in-place mode.
    with os.fdopen(os.open(output_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "wb") as output:
        output.write(encoded.getvalue())
    return {
        "algorithm": "visible-alpha-v1", "input": str(input_path), "output": str(output_path),
        "sourceSha256": hashlib.sha256(source).hexdigest(),
        "outputSha256": hashlib.sha256(encoded.getvalue()).hexdigest(),
        "sourceSize": list(image.size), "canvasSize": [size, size],
        "alphaThreshold": ALPHA_THRESHOLD, "targetLongestSideFraction": FILL,
        "sourceVisibleBounds": list(bounds), "outputVisibleBounds": list(visible_bounds(canvas)),
        "initialScale": scale, "resizedSize": list(scaled.size), "sourceFeatherPixels": feather,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--size", type=int, default=1024)
    args = parser.parse_args()
    try:
        result = normalize(args.input, args.output, args.size)
    except (OSError, ValueError) as error:
        parser.exit(1, f"pi-normalize-emoji: {error}\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
