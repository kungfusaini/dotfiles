"""Inspect every pixel of every recorded private-compositor transition frame."""
import json
from pathlib import Path
import subprocess
import sys
from PIL import Image, ImageChops, ImageOps

video, destination = sys.argv[1:]
metadata = json.loads(subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-count_frames", "-show_entries", "stream=width,height,nb_read_frames", "-of", "json", video],
                                     capture_output=True, text=True, check=True).stdout)
width, height = [metadata["streams"][0][key] for key in ("width", "height")]
total = int(metadata["streams"][0]["nb_read_frames"])
sample_frames = {round((total - 1) * index / 5) for index in range(6)}
reader = subprocess.Popen(["ffmpeg", "-v", "error", "-i", video, "-an", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], stdout=subprocess.PIPE)
size = width * height * 3
frames = 0
samples = []
while True:
    data = reader.stdout.read(size)
    if not data: break
    assert len(data) == size, "Truncated recorded frame"
    image = Image.frombytes("RGB", (width, height), data)
    red, green, blue = image.split()
    mask = ImageChops.multiply(red.point(lambda p: 255 if p >= 250 else 0),
        ImageChops.multiply(green.point(lambda p: 255 if p <= 5 else 0), blue.point(lambda p: 255 if p >= 250 else 0)))
    if mask.getbbox():
        image.save("desktop-leak.png")
        raise AssertionError(f"Work desktop visible in transition frame {frames}: {mask.getbbox()}")
    if frames in sample_frames: samples.append(ImageOps.contain(image, (320, 200)))
    frames += 1
assert reader.wait(timeout=10) == 0
assert frames == total, f"Decode changed the recorded frame count: {frames} != {total}"
assert frames >= 80, f"Insufficient transition coverage: {frames} frames"
output = Path(destination)
output.mkdir(exist_ok=True)
summary = {"frames": frames, "width": width, "height": height, "pixelsCheckedPerFrame": width * height, "desktopLeakFrames": 0}
(output / "transition-frames.json").write_text(json.dumps(summary) + "\n")
sheet = Image.new("RGB", (960, 400), "#172b3c")
for index, image in enumerate(samples): sheet.paste(image, ((index % 3) * 320, (index // 3) * 200))
sheet.save(output / "transition-contact-sheet.png")
print(json.dumps(summary))
