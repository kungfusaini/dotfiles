"""Compare synthetic chat timing in isolated CPU/GPU servers; never open real history."""
import argparse
import json
from pathlib import Path
import subprocess
import tempfile

from test_pi_private import load

# Runs inside the same sandbox as private inference. Only numeric timings and
# offload evidence leave it; model responses and server logs stay in tmpfs.
PROBE = r'''
import json, re, subprocess, sys, tempfile, time, urllib.request
argv = json.loads(sys.argv[1])
gpu = sys.argv[2] == "gpu"
argv.remove("--log-disable")
argv += ["--verbose"]
opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
with tempfile.TemporaryFile() as log:
    server = subprocess.Popen(argv, stdout=log, stderr=log)
    try:
        deadline = time.monotonic() + 180
        while True:
            if server.poll() is not None:
                raise RuntimeError("Synthetic model failed to start")
            try:
                with opener.open("http://127.0.0.1:18080/health", timeout=1) as response:
                    if response.status == 200:
                        break
            except OSError:
                if time.monotonic() >= deadline:
                    raise RuntimeError("Synthetic model startup timed out")
                time.sleep(0.25)
        rows = []
        for _ in range(2):
            payload = json.dumps({"messages": [
                {"role": "system", "content": "You are a private, local, chat-only assistant. You have no tools or file access. Answer the user's messages directly."},
                {"role": "user", "content": "Explain in simple terms why the sky looks blue during the day and red near sunset."}],
                "n_predict": 64, "temperature": 0, "seed": 42,
                "ignore_eos": True, "cache_prompt": False, "stream": False}).encode()
            request = urllib.request.Request("http://127.0.0.1:18080/v1/chat/completions",
                                              data=payload, headers={"Content-Type": "application/json"})
            started = time.monotonic()
            with opener.open(request, timeout=300) as response:
                result = json.load(response)
            assert result["choices"][0]["message"].get("content"), "No synthetic response"
            rows.append({"wall_seconds": round(time.monotonic() - started, 3),
                         "timings": result["timings"]})
        log.seek(0)
        diagnostics = log.read().decode(errors="replace")
        offload = re.findall(r"offloaded (\d+)/(\d+) layers to GPU", diagnostics)
        if gpu:
            evidence = "\n".join(line for line in diagnostics.splitlines() if any(
                word in line.lower() for word in ["offload", "vulkan", "buffer size"]))
            assert offload and any(int(a) > 0 and a == b for a, b in offload), "Full GPU offload not confirmed: " + evidence
        print(json.dumps({"backend": sys.argv[2], "offload": offload, "runs": rows}))
    finally:
        server.terminate()
        try:
            server.wait(timeout=10)
        except subprocess.TimeoutExpired:
            server.kill()
            server.wait()
'''


def run(package, label):
    launcher = load("performance_launcher_" + label, package / "bin/pi-private")
    with tempfile.TemporaryDirectory(prefix="pi-private-performance-") as tmp:
        argv = launcher.sandbox_command(Path(tmp), Path.home() / launcher.MODEL_RELATIVE)
        python, chat_path, _, _, _, server = argv[-6:]
        chat = load("performance_chat_" + label, Path(chat_path))
        if hasattr(chat, "model_command"):
            model = chat.model_command(server)
        else:
            # Exact pre-GPU private-server settings, for the original package.
            model = [server, "--model", "/model.gguf", "--alias", "private-qwen",
                     "--host", "127.0.0.1", "--port", "18080", "--ctx-size", "8192",
                     "--parallel", "1", "--threads", "4", "--threads-batch", "4",
                     "--n-gpu-layers", "0", "--jinja", "--reasoning", "off", "--log-disable"]
        argv[-6:] = [python, "-c", PROBE, json.dumps(model), label]
        result = subprocess.run(argv, capture_output=True, text=True, timeout=780)
        if result.returncode:
            raise RuntimeError(result.stderr)
        data = json.loads(result.stdout)
        print(json.dumps(data, indent=2), flush=True)
        return data


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--package", type=Path, required=True)
    parser.add_argument("--baseline-package", type=Path)
    args = parser.parse_args()
    baseline = run(args.baseline_package, "cpu") if args.baseline_package else None
    gpu = run(args.package, "gpu")
    if baseline:
        cpu_seconds = sum(r["wall_seconds"] for r in baseline["runs"])
        gpu_seconds = sum(r["wall_seconds"] for r in gpu["runs"])
        assert gpu_seconds < cpu_seconds, "GPU did not improve synthetic chat time"
        print(f"PASS: synthetic chat wall-time speedup {cpu_seconds / gpu_seconds:.2f}x")
