# Always-on VPS/dev box for terminal development and AI coding agents

Date: 2026-07-17

## Question

What community/prior-art exists around using an always-on VPS, home server, or cloud dev box as the primary terminal development environment, reachable from laptop/phone, instead of relying on a laptop that sleeps? Focus: recommendations and complaints around tmux/mosh/SSH, Tailscale, VS Code Remote SSH/Codespaces/devcontainers/cloud dev environments, Claude Code/opencode-like agents remotely, Git vs SSHFS/sync, security/secrets, latency, cost, and backups.

## Executive summary

Confirmed pattern: developers routinely treat laptops/phones as thin clients and keep code, terminals, long-running jobs, and now AI coding agents on a persistent Linux box. The boring stack is still strongest: SSH or Mosh into tmux/Zellij, private network via Tailscale/WireGuard, Git as source-of-truth, and optional VS Code Remote SSH/devcontainers for IDE ergonomics.

For AI agents, the pattern is even more attractive because Claude Code/opencode-style CLIs can keep running inside tmux while the laptop sleeps. Community complaints cluster around mobile input, image/paste support through SSH/tmux, terminal protocol mismatches, secrets exposed to a remote host/container, and agents having too much access to production credentials or remote databases.

Interpretation: use an always-on dev box if you value persistence and multi-device access. Avoid making SSHFS or a cloud IDE the core data layer; keep repositories on the dev box and sync via Git. Add snapshots/backups because the dev box becomes the single working-state machine.

## Sources

- Mosh official site and FAQ: https://mosh.org/
- Tailscale SSH docs: https://tailscale.com/kb/1193/tailscale-ssh
- VS Code Remote SSH docs: https://code.visualstudio.com/docs/remote/ssh
- VS Code Dev Containers docs: https://code.visualstudio.com/docs/devcontainers/containers
- GitHub Codespaces overview: https://docs.github.com/en/codespaces/overview
- GitHub Codespaces persistence docs: https://docs.github.com/en/codespaces/developing-in-a-codespace/persisting-environment-variables-and-temporary-files
- GitHub Codespaces billing: https://docs.github.com/en/billing/concepts/product-billing/github-codespaces
- Claude Code devcontainer docs: https://docs.anthropic.com/en/docs/claude-code/devcontainer
- Claude Code settings/security scopes: https://docs.anthropic.com/en/docs/claude-code/settings
- OpenCode docs: https://opencode.ai/docs/
- Coder workspace access docs: https://coder.com/docs/user-guides/workspace-access
- HN Algolia community examples:
  - Tailscale + VS Code Remote SSH as thin-client workflow: https://hn.algolia.com/api/v1/search?query=remote%20development%20vscode%20ssh%20tailscale&tags=comment
  - Claude Code + remote server + tmux/mobile comments: https://hn.algolia.com/api/v1/search?query=Claude%20Code%20remote%20server%20tmux&tags=comment

## Detailed notes

### 1. Terminal-first remote dev: SSH + tmux remains the baseline

Confirmed facts:

- Mosh is explicitly designed for roaming, intermittent connectivity, and laptop sleep/wake: “put your laptop to sleep and wake it up later, keeping your connection intact” and “more robust and responsive… over Wi‑Fi, cellular, and long-distance links” (https://mosh.org/).
- Mosh uses SSH for initial login and then UDP, which means firewalls must allow UDP ports, commonly 60000–61000; its FAQ says “Nothing received…” usually means UDP is blocked (https://mosh.org/).
- Mosh only syncs visible terminal state; its FAQ recommends screen/tmux for scrollback/session persistence (https://mosh.org/).

Community signal:

- HN commenters repeatedly describe central Linux workstations/home servers accessed from laptop/phone. One commenter says all development happens on a “beefy Linux workstation” via “Tailscale + VSCode SSH” and that remote SSH is the only thing keeping them on VS Code (HN Algolia result `objectID=46500881`, https://hn.algolia.com/api/v1/search?query=remote%20development%20vscode%20ssh%20tailscale&tags=comment).
- For AI coding agents, one HN commenter says multiple simultaneous Claude Code sessions on a remote server are a case where CLI + tmux makes sense because sessions are preconfigured when reconnecting (HN Algolia `objectID=47929776`, https://hn.algolia.com/api/v1/search?query=Claude%20Code%20remote%20server%20tmux&tags=comment).

Interpretation:

- If terminal development is primary, tmux is the durable state layer; Mosh is the better transport on bad/mobile networks; plain SSH is simplest and best supported everywhere.

### 2. Tailscale/WireGuard is the common “don’t expose SSH” answer

Confirmed facts:

- Tailscale SSH can authenticate and authorize SSH using Tailscale/WireGuard identities and ACLs, without modifying `sshd_config` or `authorized_keys` (https://tailscale.com/kb/1193/tailscale-ssh).
- It supports check mode for higher-risk connections, revocation through tailnet policy, MagicDNS names, and session recording in some plans/use cases (https://tailscale.com/kb/1193/tailscale-ssh).
- Limitations: Tailscale SSH assumes port 22, only works to devices running Tailscale, server component is Linux or open-source macOS tailscaled, restarting tailscaled stops existing Tailscale SSH sessions, and Tailscale warns it may be a poor fit for multi-user machines where local OS users have different SSH permissions (https://tailscale.com/kb/1193/tailscale-ssh).

Community signal:

- HN users recommend Tailscale + MagicDNS + SSH keys + VS Code Remote SSH; one specifically says it is “surprisingly fast” because you send keystrokes/commands rather than a rasterized desktop (HN Algolia `objectID=33108260`, https://hn.algolia.com/api/v1/search?query=remote%20development%20vscode%20ssh%20tailscale&tags=comment).
- For phone use, one commenter runs Claude Code on a remote server, connects via SSH over WireGuard, and uses code-server/port forwarding for dev servers (HN Algolia `objectID=46475595`, https://hn.algolia.com/api/v1/search?query=Claude%20Code%20remote%20server%20tmux&tags=comment).

Interpretation:

- Prefer private overlay networking over public SSH. Tailscale SSH is nice for identity/ACLs, but ordinary OpenSSH over Tailscale is more portable and avoids Tailscale SSH’s port-22/server limitations.

### 3. VS Code Remote SSH and devcontainers are mature, but not frictionless

Confirmed facts:

- VS Code Remote SSH runs commands and many extensions directly on the remote host; “No source code needs to be on your local machine” (https://code.visualstudio.com/docs/remote/ssh).
- Remote SSH gives remote terminals, port forwarding, debugging, host-specific settings, and remote extension installation (https://code.visualstudio.com/docs/remote/ssh).
- VS Code explicitly says it does not directly support syncing source code to local tools; suggested options are SSHFS or rsync. SSHFS is convenient but “significantly slower” and best for single-file edits; rsync is better when local tools bulk read/write many files (https://code.visualstudio.com/docs/remote/ssh).
- Dev Containers can run on a remote SSH host; you do not need Docker locally if Docker is installed on the remote host (https://code.visualstudio.com/docs/devcontainers/containers).

Community complaints:

- VS Code Remote SSH is valued, but users complain about local-vs-remote extension state and rebuild/bootstrap complexity when a VS Code install gets corrupted (HN Algolia `objectID=46500881`, https://hn.algolia.com/api/v1/search?query=remote%20development%20vscode%20ssh%20tailscale&tags=comment).
- Some users prefer containers/LXD on a home server to avoid doing everything “the Nix way” or fighting host tooling constraints (HN Algolia `objectID=30392432`, same query).

Interpretation:

- VS Code Remote SSH is the best “full IDE on remote code” path. It is heavier than terminal/tmux and can become stateful in two places, so keep the terminal workflow usable without it.

### 4. Codespaces/cloud dev environments solve onboarding, not always-on persistence cheaply

Confirmed facts:

- Codespaces are hosted in Docker containers on VMs, connectable from browser, VS Code, or GitHub CLI; VM choices range from 2 cores/8 GB/32 GB storage up to 32 cores/128 GB/128 GB storage (https://docs.github.com/en/codespaces/overview).
- `/workspaces` persists across stop/start and rebuild; files outside `/workspaces` persist across stop/start but not rebuild; `/tmp` is cleared when the codespace stops (https://docs.github.com/en/codespaces/developing-in-a-codespace/persisting-environment-variables-and-temporary-files).
- Billing is compute while active plus storage while the codespace/prebuild exists. Personal free quota is 120 hours + 15 GB-month for GitHub Free, 180 hours + 20 GB-month for Pro. Paid 2-core compute is $0.18/hour, 4-core $0.36/hour, 8-core $0.72/hour, storage $0.07/GB-month (https://docs.github.com/en/billing/concepts/product-billing/github-codespaces).
- GitHub’s marketing page emphasizes coding from any device, including iPad, and that Codespaces cannot be self-hosted (https://github.com/features/codespaces).
- Coder supports web terminals, SSH, VS Code, code-server, JetBrains Gateway, Cursor/Windsurf/Antigravity, port forwarding, and a desktop VPN-like app for workspace access (https://coder.com/docs/user-guides/workspace-access).

Interpretation:

- Codespaces is good for ephemeral/reproducible repo environments and onboarding. A VPS/home dev box is better when you want one persistent personal machine, long-running tmux sessions, predictable monthly cost, and full control.

### 5. AI coding agents make remote persistence more valuable and more dangerous

Confirmed facts:

- Claude Code’s devcontainer guidance explicitly supports running Claude inside a container on a local or cloud host such as Codespaces, with terminal, language servers, and tools running inside the container (https://docs.anthropic.com/en/docs/claude-code/devcontainer).
- Anthropic warns devcontainers are not complete protection; with `--dangerously-skip-permissions`, malicious projects can exfiltrate anything accessible in the container, including Claude credentials in `~/.claude`; they advise avoiding host secrets such as `~/.ssh` or cloud credential files and preferring repository-scoped or short-lived tokens (https://docs.anthropic.com/en/docs/claude-code/devcontainer).
- Claude Code stores auth tokens/settings/session history under `~/.claude`; docs recommend a named volume to persist it across rebuilds, or Codespaces secrets/API tokens for auth across codespaces (https://docs.anthropic.com/en/docs/claude-code/devcontainer).
- Claude settings have user/project/local/managed scopes; `~/.claude.json` contains OAuth session, MCP config, trust state, and caches (https://docs.anthropic.com/en/docs/claude-code/settings).
- OpenCode is a terminal-based, desktop, or IDE AI coding agent, requires a modern terminal and LLM provider API keys, and recommends committing project `AGENTS.md` after `/init` (https://opencode.ai/docs/).

Community signal:

- Remote Claude Code in tmux is already a live workflow. HN examples include tens of Claude Code sessions on a dev server switched via tmux, with complaints about image paste through terminal/SSH/tmux (HN Algolia `objectID=45125587`, https://hn.algolia.com/api/v1/search?query=Claude%20Code%20remote%20server%20tmux&tags=comment).
- Users complain about tmux/terminal mismatches with agents: washed-out colors, desktop notifications not passing through, scrollback weirdness, and image protocol mismatches (HN Algolia `objectID=48828400`, same query).
- Security complaints are concrete: an HN commenter warns Claude can wipe remote DBs via MCP/server access or run dangerous cleanup such as `rm -rf`; treat this as anecdotal but consistent with Anthropic’s own warnings about accessible secrets/resources (HN Algolia `objectID=46691744`, same query).

Interpretation:

- Remote agent boxes should be treated like semi-autonomous build machines. Give them less access than your laptop, not more. Use separate shell users, per-repo tokens, no prod DB credentials by default, and container/VM boundaries for untrusted repos.

### 6. Sync: Git beats SSHFS for primary workflow

Confirmed facts:

- VS Code’s official guidance: SSHFS is convenient but significantly slower and best for single-file edits; rsync is better for local tools that bulk read/write files (https://code.visualstudio.com/docs/remote/ssh).
- Codespaces persists repository work under `/workspaces` but not everything across rebuilds, reinforcing “commit/push/export branch” as durable state rather than relying on instance-local home directory (https://docs.github.com/en/codespaces/developing-in-a-codespace/persisting-environment-variables-and-temporary-files).

Interpretation:

- Keep the repo clone on the remote dev box. Use Git remotes for laptop/dev-box sync and disaster recovery. Use SSHFS only for occasional file browsing/editing from a local GUI; use rsync only for specific local tool workflows.

### 7. Backups and operational risk

Confirmed facts:

- None of the remote-dev docs make a VPS/home dev box automatically safe; Codespaces documents which paths persist and when they do not (https://docs.github.com/en/codespaces/developing-in-a-codespace/persisting-environment-variables-and-temporary-files).
- Codespaces can block resume when quota/budget is exhausted but lets users export changes to a branch (https://docs.github.com/en/billing/concepts/product-billing/github-codespaces).

Interpretation:

- For a personal always-on dev box, backups are not optional because tmux sessions, unpushed branches, local databases, agent logs, and `~/.claude`/opencode state will accumulate there. Minimum: provider snapshots plus nightly restic/borg of `$HOME`, `/etc`, project dirs, and local dev databases; Git push before risky agent runs.

## Tradeoffs

| Option | Good at | Complaints / limits |
|---|---|---|
| SSH + tmux | Lowest moving parts, durable sessions, phone/laptop access | Raw SSH dies on sleep/network changes; mobile input is painful |
| Mosh + tmux | Roaming/sleep/bad networks, responsive typing | Needs UDP; visible-state-only scrollback; UTF-8 assumptions |
| Tailscale + SSH | No public SSH exposure, MagicDNS, easy multi-device | Tailnet/account dependency; Tailscale SSH has port-22/server/multi-user caveats |
| VS Code Remote SSH | Local-quality IDE on remote filesystem | Extension split-brain, bootstrap state, proprietary Remote extensions |
| Devcontainers | Reproducible, safer per-project toolchains | Docker/storage/build complexity; secrets still leak if mounted |
| Codespaces | Fast onboarding, browser/iPad, GitHub integration | Metered cost, quota/budget stoppage, not self-hosted, not ideal as one persistent personal machine |
| Self-hosted Coder/code-server | Browser IDE plus SSH/ports under your control | You operate the platform; more moving parts than SSH/tmux |

## Recommendations

1. Use the boring baseline: `ssh`/`mosh` into a Linux dev box, run project sessions under tmux, and connect over Tailscale/WireGuard rather than public SSH.
2. Keep source of truth in Git. Do not make SSHFS the normal editing/storage path; use it only as a convenience.
3. If using VS Code, use Remote SSH directly to the dev box; add devcontainers only for projects that need isolation or reproducibility.
4. Run Claude Code/opencode agents remotely inside tmux, but fence them: non-root user, repo-scoped API keys, no default prod credentials, no broad MCP access, and preferably per-project containers/VMs for risky repos.
5. Add backups/snapshots before relying on this: dev-box `$HOME`, `/etc`, local databases, agent config/state, and unpushed work. Git push before long autonomous runs.
6. Use Codespaces/Coder when the problem is team onboarding or ephemeral review environments; use a VPS/home dev box when the problem is personal continuity, sleep-proof terminals, and predictable always-on state.

## Open questions

- How much mobile-first control is needed? SSH clients work, but good phone UX may require a web/voice/control layer beyond tmux.
- Whether to trust Tailscale SSH or prefer OpenSSH over Tailscale depends on machine sharing and desired key/ACL model.
- Exact VPS sizing/cost depends on workloads and model-agent parallelism; community examples range from cheap home PCs to per-dev EC2 instances.
- Backups should be tested with a restore drill; source docs do not cover personal VPS recovery details.
