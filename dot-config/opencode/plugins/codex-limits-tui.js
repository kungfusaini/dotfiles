import { execFile } from "node:child_process"
import { promisify } from "node:util"

const execFileAsync = promisify(execFile)
const SCRIPT = "/Users/sumeet/.config/opencode/scripts/codex-limits.mjs"

async function getLimitsSummary() {
  const { stdout, stderr } = await execFileAsync("node", [SCRIPT, "--json"], {
    timeout: 30_000,
    maxBuffer: 128 * 1024,
  })

  const output = stdout.trim()
  if (!output) throw new Error(stderr.trim() || "Codex limits returned no output.")

  return JSON.parse(output)
}

function bar(leftPercent) {
  const width = 20
  const left = Number.isFinite(leftPercent) ? Math.max(0, Math.min(100, leftPercent)) : 0
  const filled = Math.round((left / 100) * width)
  return `${"█".repeat(filled)}${"░".repeat(width - filled)}`
}

function formatReset(resetAtMs) {
  if (!resetAtMs) return "reset unknown"
  const when = new Date(resetAtMs).toLocaleString(undefined, {
    weekday: "short",
    month: "short",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  })
  const deltaMs = resetAtMs - Date.now()
  if (deltaMs <= 0) return `resets now\n${when}`

  const minutes = Math.round(deltaMs / 60000)
  if (minutes < 60) return `resets in ${minutes}m\n${when}`

  const hours = Math.floor(minutes / 60)
  const rest = minutes % 60
  if (hours < 24) return `resets in ${hours}h ${rest}m\n${when}`

  const days = Math.floor(hours / 24)
  const dayHours = hours % 24
  return `resets in ${days}d ${dayHours}h\n${when}`
}

function lineFor(limit) {
  const left = Number.isFinite(limit?.leftPercent) ? limit.leftPercent : 0
  const used = Number.isFinite(limit?.usedPercent) ? limit.usedPercent : 100 - left
  return [
    `${limit?.name ?? "Limit"}`,
    `[${bar(left)}]`,
    `${left}% left · ${used}% used`,
    formatReset(limit?.resetAtMs),
  ].join("\n")
}

function formatLimits(summary) {
  const fiveHour = summary.limits?.find((limit) => limit?.windowMinutes === 300)
  const weekly = summary.limits?.find((limit) => limit?.windowMinutes === 10080)

  return [lineFor(fiveHour), "", lineFor(weekly)].join("\n")
}

function sanitizeError(error) {
  const text = [error?.message, error?.stdout, error?.stderr]
    .filter(Boolean)
    .join("\n")
    .replace(/Bearer\s+\S+/gi, "Bearer [redacted]")
    .replace(/eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+/g, "[redacted-token]")
    .replace(/\bsk-[A-Za-z0-9][A-Za-z0-9._:-]{19,}\b/gi, "[redacted-token]")
    .trim()

  return text || "Unknown error."
}

function showAlert(api, title, message) {
  api.ui.dialog.replace(() =>
    api.ui.DialogAlert({
      title,
      message,
      onConfirm: () => api.ui.dialog.clear(),
    }),
  )
}

async function showCodexLimits(api) {
  showAlert(api, "Codex limits", "Loading Codex limits…")

  try {
    const summary = await getLimitsSummary()
    showAlert(api, "Codex limits", formatLimits(summary))
  } catch (error) {
    showAlert(api, "Codex limits unavailable", sanitizeError(error))
  }
}

export default {
  id: "codex-limits-tui",
  async tui(api) {
    const dispose = api.command?.register(() => [
      {
        title: "Codex limits",
        value: "codex-limits.show",
        description: "Show current Codex 5h and weekly usage in a dialog.",
        category: "Codex",
        slash: {
          name: "limits",
          aliases: ["codex-limits"],
        },
        onSelect: () => showCodexLimits(api),
      },
    ])

    if (dispose) api.lifecycle.onDispose(dispose)
  },
}
