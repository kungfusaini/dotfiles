#!/usr/bin/env node

import fs from "node:fs"
import os from "node:os"
import path from "node:path"

const DEFAULT_ENV_PATH = path.join(os.homedir(), ".config/opencode/.env")
const DEFAULT_BASE_URL = "https://nano-gpt.com/api/v1"
const SUBSCRIPTION_MODELS_URL = "https://nano-gpt.com/api/subscription/v1/models?detailed=true"
const DETAILS_URL = "https://nano-gpt.com/api/explore/text-model-details"
const DEFAULT_SORT = "intelligence"
const DEFAULT_LIMIT = 50
const BATCH_SIZE = 50

const args = parseArgs(process.argv.slice(2))

function parseArgs(argv) {
  const options = {
    envPath: DEFAULT_ENV_PATH,
    format: "table",
    sort: DEFAULT_SORT,
    limit: DEFAULT_LIMIT,
    output: null,
  }

  for (let index = 0; index < argv.length; index++) {
    const arg = argv[index]
    const next = () => {
      const value = argv[++index]
      if (!value) fail(`missing value for ${arg}`)
      return value
    }

    if (arg === "--help" || arg === "-h") options.help = true
    else if (arg === "--json") options.format = "json"
    else if (arg === "--csv") options.format = "csv"
    else if (arg === "--table") options.format = "table"
    else if (arg === "--sort") options.sort = next()
    else if (arg.startsWith("--sort=")) options.sort = arg.slice("--sort=".length)
    else if (arg === "--limit") options.limit = parseLimit(next())
    else if (arg.startsWith("--limit=")) options.limit = parseLimit(arg.slice("--limit=".length))
    else if (arg === "--all") options.limit = null
    else if (arg === "--output") options.output = next()
    else if (arg.startsWith("--output=")) options.output = arg.slice("--output=".length)
    else if (arg === "--env") options.envPath = expandHome(next())
    else if (arg.startsWith("--env=")) options.envPath = expandHome(arg.slice("--env=".length))
    else fail(`unknown argument: ${arg}`)
  }

  return options
}

function parseLimit(value) {
  const limit = Number.parseInt(value, 10)
  if (!Number.isFinite(limit) || limit < 1) fail(`invalid limit: ${value}`)
  return limit
}

function expandHome(value) {
  if (value === "~") return os.homedir()
  if (value.startsWith("~/")) return path.join(os.homedir(), value.slice(2))
  return value
}

function usage() {
  return `Usage: scripts/nanogpt-subscription-models.mjs [options]

Generate joined NanoGPT subscription model data from:
  - /api/subscription/v1/models?detailed=true
  - /api/explore/text-model-details?model_ids=...

Options:
  --table                 Print a compact table (default)
  --json                  Print full joined JSON
  --csv                   Print CSV
  --sort <key>            Sort by intelligence, coding, speed, avg-tps, latency,
                          context, output, multiplier, price, or name
                          (default: intelligence)
  --limit <n>             Limit rows for table/csv output (default: 50)
  --all                   Include all rows in table/csv output
  --output <path>         Write output to a file instead of stdout
  --env <path>            Dotenv file with NANOGPT_API_KEY
  -h, --help              Show this help

Secrets are read from ~/.config/opencode/.env by default and are never printed.
`
}

function fail(message, detail) {
  console.error(`NanoGPT model join failed: ${message}`)
  if (detail) console.error(sanitize(detail))
  process.exit(1)
}

function sanitize(text) {
  return String(text || "")
    .replace(/Bearer\s+\S+/gi, "Bearer [redacted]")
    .replace(/\bsk-[A-Za-z0-9][A-Za-z0-9._:-]{19,}\b/gi, "[redacted-token]")
    .slice(0, 1000)
}

function readEnv(filePath) {
  if (!fs.existsSync(filePath)) fail(`env file not found at ${filePath}`)

  const env = {}
  for (const line of fs.readFileSync(filePath, "utf8").split(/\r?\n/)) {
    const trimmed = line.trim()
    if (!trimmed || trimmed.startsWith("#") || !trimmed.includes("=")) continue
    const [rawKey, ...rest] = trimmed.split("=")
    const key = rawKey.replace(/^export\s+/, "").trim()
    const value = rest.join("=").trim().replace(/^['"]|['"]$/g, "")
    env[key] = value
  }
  return env
}

async function fetchJson(url, apiKey) {
  const response = await fetch(url, {
    headers: {
      Authorization: `Bearer ${apiKey}`,
      Accept: "application/json",
      "User-Agent": "opencode-nanogpt-models",
    },
  })

  if (!response.ok) {
    const body = await response.text().catch(() => "")
    fail(`request failed with HTTP ${response.status}: ${url}`, body)
  }

  return await response.json()
}

function chunks(items, size) {
  const result = []
  for (let index = 0; index < items.length; index += size) {
    result.push(items.slice(index, index + size))
  }
  return result
}

async function fetchDetails(modelIds, apiKey) {
  const joined = {}
  for (const batch of chunks(modelIds, BATCH_SIZE)) {
    const params = new URLSearchParams({ model_ids: batch.join(",") })
    const payload = await fetchJson(`${DETAILS_URL}?${params}`, apiKey)
    Object.assign(joined, payload.models || {})
  }
  return joined
}

function numberOrNull(value) {
  return typeof value === "number" && Number.isFinite(value) ? value : null
}

function priceTotal(model) {
  const pricing = model.pricing || {}
  return (numberOrNull(pricing.prompt) ?? 0) + (numberOrNull(pricing.completion) ?? 0)
}

function joinModel(model, details) {
  const capabilities = model.capabilities || {}
  const benchmarkData = details?.benchmarkData || null
  const subscription = model.subscription || null

  return {
    id: model.id,
    name: model.name || model.id,
    provider: model.owned_by || null,
    category: model.category || null,
    description: model.description || null,
    contextLength: numberOrNull(model.context_length),
    maxOutputTokens: numberOrNull(model.max_output_tokens),
    pricing: model.pricing || null,
    capabilities: {
      reasoning: Boolean(capabilities.reasoning),
      structuredOutput: Boolean(capabilities.structured_output),
      toolCalling: Boolean(capabilities.tool_calling || capabilities.parallel_tool_calls),
      vision: Boolean(capabilities.vision),
      audioInput: Boolean(capabilities.audio_input),
      videoInput: Boolean(capabilities.video_input),
      pdfUpload: Boolean(capabilities.pdf_upload),
    },
    subscription: subscription
      ? {
          included: Boolean(subscription.included),
          inputTokenMultiplier: numberOrNull(subscription.inputTokenMultiplier) ?? 1,
          note: subscription.note || null,
        }
      : null,
    metrics: {
      avgTps: numberOrNull(details?.avgTps),
      avgTtftMs: numberOrNull(details?.avgTtftMs),
      intelligence: numberOrNull(benchmarkData?.intelligence),
      coding: numberOrNull(benchmarkData?.coding),
      math: numberOrNull(benchmarkData?.math),
      lmarena: numberOrNull(benchmarkData?.lmarena),
      speedTokensPerSecond: numberOrNull(benchmarkData?.speedTokensPerSecond),
      gpqa: numberOrNull(benchmarkData?.gpqa),
      hle: numberOrNull(benchmarkData?.hle),
      ifbench: numberOrNull(benchmarkData?.ifbench),
      lcr: numberOrNull(benchmarkData?.lcr),
      scicode: numberOrNull(benchmarkData?.scicode),
      tau2: numberOrNull(benchmarkData?.tau2),
      terminalbenchHard: numberOrNull(benchmarkData?.terminalbenchHard),
      lastUpdated: benchmarkData?.lastUpdated || null,
    },
  }
}

function sortValue(row, sort) {
  switch (sort) {
    case "intelligence":
      return row.metrics.intelligence
    case "coding":
      return row.metrics.coding
    case "math":
      return row.metrics.math
    case "speed":
      return row.metrics.speedTokensPerSecond
    case "avg-tps":
      return row.metrics.avgTps
    case "latency":
      return row.metrics.avgTtftMs === null ? null : -row.metrics.avgTtftMs
    case "context":
      return row.contextLength
    case "output":
      return row.maxOutputTokens
    case "multiplier":
      return row.subscription?.inputTokenMultiplier === null ? null : -row.subscription?.inputTokenMultiplier
    case "price":
      return -priceTotal(row)
    case "name":
      return row.name.toLowerCase()
    default:
      fail(`unsupported sort: ${sort}`)
  }
}

function sortRows(rows, sort) {
  return [...rows].sort((left, right) => {
    const a = sortValue(left, sort)
    const b = sortValue(right, sort)
    if (typeof a === "string" || typeof b === "string") return String(a || "").localeCompare(String(b || ""))
    if (a === null && b === null) return left.name.localeCompare(right.name)
    if (a === null) return 1
    if (b === null) return -1
    if (a !== b) return b - a
    return left.name.localeCompare(right.name)
  })
}

function fmt(value, digits = 1) {
  if (typeof value !== "number" || !Number.isFinite(value)) return "-"
  return value.toFixed(digits).replace(/\.0$/, "")
}

function compactNumber(value) {
  if (typeof value !== "number" || !Number.isFinite(value)) return "-"
  if (value >= 1_000_000) return `${fmt(value / 1_000_000)}M`
  if (value >= 1_000) return `${fmt(value / 1_000)}K`
  return String(value)
}

function boolFlag(value, label) {
  return value ? label : ""
}

function table(rows) {
  const headers = ["model", "intel", "coding", "speed", "avg tps", "ttft", "ctx", "out", "mult", "caps"]
  const body = rows.map((row) => [
    row.id,
    fmt(row.metrics.intelligence),
    fmt(row.metrics.coding),
    fmt(row.metrics.speedTokensPerSecond),
    fmt(row.metrics.avgTps),
    row.metrics.avgTtftMs === null ? "-" : `${fmt(row.metrics.avgTtftMs / 1000)}s`,
    compactNumber(row.contextLength),
    compactNumber(row.maxOutputTokens),
    `${row.subscription?.inputTokenMultiplier ?? 1}x`,
    [
      boolFlag(row.capabilities.reasoning, "reason"),
      boolFlag(row.capabilities.toolCalling, "tools"),
      boolFlag(row.capabilities.structuredOutput, "struct"),
      boolFlag(row.capabilities.vision, "vision"),
    ].filter(Boolean).join(","),
  ])

  const widths = headers.map((header, index) => Math.max(header.length, ...body.map((row) => String(row[index]).length)))
  const line = (columns) => columns.map((column, index) => String(column).padEnd(widths[index])).join("  ")
  return [line(headers), line(headers.map((header) => "-".repeat(header.length))), ...body.map(line)].join("\n")
}

function csvEscape(value) {
  const text = String(value ?? "")
  return /[",\n]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text
}

function csv(rows) {
  const fields = [
    "id",
    "name",
    "provider",
    "intelligence",
    "coding",
    "speedTokensPerSecond",
    "avgTps",
    "avgTtftMs",
    "contextLength",
    "maxOutputTokens",
    "inputTokenMultiplier",
    "reasoning",
    "toolCalling",
    "structuredOutput",
    "vision",
  ]
  const values = (row) => [
    row.id,
    row.name,
    row.provider,
    row.metrics.intelligence,
    row.metrics.coding,
    row.metrics.speedTokensPerSecond,
    row.metrics.avgTps,
    row.metrics.avgTtftMs,
    row.contextLength,
    row.maxOutputTokens,
    row.subscription?.inputTokenMultiplier ?? 1,
    row.capabilities.reasoning,
    row.capabilities.toolCalling,
    row.capabilities.structuredOutput,
    row.capabilities.vision,
  ]

  return [fields.join(","), ...rows.map((row) => values(row).map(csvEscape).join(","))].join("\n")
}

function output(text) {
  if (!args.output) {
    console.log(text)
    return
  }

  const outputPath = expandHome(args.output)
  fs.mkdirSync(path.dirname(outputPath), { recursive: true })
  fs.writeFileSync(outputPath, `${text}\n`)
  console.error(`Wrote ${outputPath}`)
}

async function main() {
  if (args.help) {
    console.log(usage())
    return
  }

  const env = readEnv(args.envPath)
  const apiKey = env.NANOGPT_API_KEY
  const baseUrl = (env.NANOGPT_BASE_URL || DEFAULT_BASE_URL).replace(/\/+$/, "")
  if (!apiKey) fail(`NANOGPT_API_KEY not found in ${args.envPath}`)

  const modelPayload = await fetchJson(SUBSCRIPTION_MODELS_URL, apiKey)
  const subscriptionModels = (Array.isArray(modelPayload.data) ? modelPayload.data : [])
    .filter((model) => model?.id && model.subscription?.included !== false)

  if (subscriptionModels.length === 0) fail("no subscription models returned")

  const details = await fetchDetails(subscriptionModels.map((model) => model.id), apiKey)
  const rows = sortRows(subscriptionModels.map((model) => joinModel(model, details[model.id])), args.sort)
  const selectedRows = args.limit === null ? rows : rows.slice(0, args.limit)
  const generatedAt = new Date().toISOString()

  if (args.format === "json") {
    output(JSON.stringify({
      generatedAt,
      source: {
        subscriptionModelsUrl: SUBSCRIPTION_MODELS_URL,
        detailsUrl: DETAILS_URL,
        baseUrl,
      },
      count: rows.length,
      sort: args.sort,
      models: rows,
    }, null, 2))
  } else if (args.format === "csv") {
    output(csv(selectedRows))
  } else {
    output(`# NanoGPT subscription models (${rows.length}), sorted by ${args.sort}\n# Generated ${generatedAt}\n\n${table(selectedRows)}`)
  }
}

main().catch((error) => fail(error.message, error.stack))
