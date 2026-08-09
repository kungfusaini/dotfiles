---
name: using-exe-dev
description: Guidance for using exe.dev VMs from Pi. Use when the user mentions exe.dev, exe VMs, *.exe.xyz, remote Linux sandboxes, temporary web app VMs, or creating/managing exe.dev infrastructure.
license: MIT
---

# Using exe.dev

exe.dev provides persistent Linux VMs managed through SSH. Use it when the user wants a small remote Linux box, sandbox, disposable web app host, or VM-backed experiment.

## Core model

- `ssh exe.dev <command>` is the exe.dev control plane/lobby for VM lifecycle, sharing, billing, defaults, and metadata.
- `ssh <vm>.exe.xyz` is the actual VM shell. Use this destination for normal shell work, `scp`, `sftp`, port forwarding, and file transfer.
- Prefer `--json` for scripting exe.dev lifecycle commands.
- Treat VMs as persistent resources: name them clearly, comment why they exist, keep them private by default, and clean them up when done.

## Default VM policy

Unless the user explicitly asks for exeuntu, Shelley, or preinstalled agent CLIs inside the VM, default to the smallest practical Ubuntu VM:

```sh
ssh exe.dev new --json \
  --name=<purposeful-name> \
  --comment="<short clear reason for this VM>" \
  --image=ubuntu:22.04 \
  --cpu=1 \
  --memory=2GB \
  --disk=10GB \
  --no-email
```

Empirical minimums observed on exe.dev:

- Memory: `2GB` minimum.
- Disk: `10GB` minimum nominal disk capacity.
- CPU: `--cpu=1` is the smallest observed real CPU allocation. `--cpu=0` may be accepted but means default, observed as 2 CPUs.

Use `ubuntu:22.04` as the default because it is much smaller than exeuntu for simple apps and probes. A tiny Ubuntu VM used about 100-150 MB of actual filesystem space in experiments even though nominal disk capacity is 10GB. exe.dev pooled disk is measured as filesystem usage, not nominal capacity, but billing usage can update asynchronously.

## Naming and comments

Always give VMs proper names and comments.

Names should be:

- Purposeful and human-readable.
- Short enough to type.
- Unique when creating throwaways, usually with a date/time or random suffix.
- Prefixed by purpose when useful, e.g. `pi-web-probe-...`, `sandbox-...`, `demo-...`, `agent-...`.

Comments should say why the VM exists and whether it is temporary. Example:

```sh
--comment="Temporary private VM for testing a minimal Flask app; delete after review"
```

## Privacy and sharing

- Keep everything private by default.
- Do not run `share set-public`, create public links, or expose unauthenticated URLs unless the user explicitly asks for a public/shareable URL.
- If public access is needed, state that it is public, list the URL, and remind the user to make it private or delete it afterward.
- Configure proxy ports explicitly for web apps when needed:

```sh
ssh exe.dev share port <vm> <port>
```

Only make public with explicit user intent:

```sh
ssh exe.dev share set-public <vm>
```

Return to private:

```sh
ssh exe.dev share set-private <vm>
```

## exeuntu policy

Use exeuntu only when its batteries-included environment is worth the extra disk usage, such as running Pi, Codex, Claude, Shelley, or an agent inside the VM.

Empirical comparison with identical `1 CPU / 2GB RAM / 10GB disk` VMs:

- `ubuntu:22.04`: about 106 MB used on `/`, about 47 MiB idle memory, no Pi/Codex/Claude/Python detected by default.
- default exeuntu: about 4.54 GB used on `/`, about 102 MiB idle memory, included Pi, Codex, Claude, Python 3.12, Go, and exe.dev helper bits.

So prefer Ubuntu for tiny web apps, probes, demos, and sandboxes. Prefer exeuntu when preinstalled agent tooling matters.

## Setup scripts and future custom images

For repeated setup without a custom image, use exe.dev setup scripts:

```sh
cat setup.sh | ssh exe.dev new --setup-script /dev/stdin ...
```

A setup script can inject VM-local agent context such as:

```sh
mkdir -p ~/.config/pi/agent
cat > ~/.config/pi/agent/AGENTS.md <<'EOF'
# VM-specific agent instructions
...
EOF
```

Longer-term, prefer a custom slim image when the desired baseline stabilizes. A custom image can include selected packages, bootstrap scripts, and VM-local `AGENTS.md` while staying much smaller than exeuntu.

## Safety checklist before creating a VM

Before creating an exe.dev VM, ensure:

- The user has asked to create or run something remotely, or has approved the VM creation.
- The image choice is justified: default `ubuntu:22.04`, exeuntu only if agent tooling is needed.
- The name is meaningful.
- The comment explains purpose and cleanup expectation.
- The VM will remain private unless public sharing was explicitly requested.
- There is a cleanup plan for throwaway experiments.

## Useful commands

```sh
ssh exe.dev help
ssh exe.dev ls --json
ssh exe.dev ls -l --json <vm>
ssh exe.dev stat --json <vm>
ssh exe.dev rm --json <vm>
ssh <vm>.exe.xyz
scp file.txt <vm>.exe.xyz:~/
```
