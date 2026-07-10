#!/usr/bin/env node

import fs from "node:fs"
import os from "node:os"
import path from "node:path"

const AUTH_PATH = path.join(os.homedir(), ".local/share/opencode/auth.json")
const TOKEN_URL = "https://auth.openai.com/oauth/token"
const USAGE_URL = "https://chatgpt.com/backend-api/wham/usage"
const CLIENT_ID = "app_EMoamEEZ73f0CkXaXp7hrann"

const jsonMode = process.argv.includes("--json")

function fail(message, detail) {
  if (jsonMode) {
    console.log(JSON.stringify({ ok: false, error: message, detail }, null, 2))
  } else {
    console.error(`Codex limits unavailable: ${message}`)
    if (detail) console.error(detail)
  }
  process.exit(1)
}

function readAuthFile() {
  if (!fs.existsSync(AUTH_PATH)) fail(`auth file not found at ${AUTH_PATH}`)

  try {
    return JSON.parse(fs.readFileSync(AUTH_PATH, "utf8"))
  } catch (error) {
    fail(`could not parse ${AUTH_PATH}`, error.message)
  }
}

function writeAuthFile(authFile) {
  const tmp = `${AUTH_PATH}.${process.pid}.tmp`
  fs.writeFileSync(tmp, `${JSON.stringify(authFile, null, 2)}\n`, { mode: 0o600 })
  fs.renameSync(tmp, AUTH_PATH)
}

function decodeJwt(token) {
  try {
    const [, payload] = token.split(".")
    if (!payload) return null
    return JSON.parse(Buffer.from(payload, "base64url").toString("utf8"))
  } catch {
    return null
  }
}

async function refreshAccessToken(authFile, auth) {
  if (!auth.refresh) fail("OpenAI OAuth refresh token is missing")

  const response = await fetch(TOKEN_URL, {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: new URLSearchParams({
      grant_type: "refresh_token",
      refresh_token: auth.refresh,
      client_id: CLIENT_ID,
    }),
  })

  if (!response.ok) {
    const body = await safeBody(response)
    fail(`token refresh failed with HTTP ${response.status}`, sanitize(body))
  }

  const payload = await response.json()
  if (!payload.access_token || !payload.refresh_token || typeof payload.expires_in !== "number") {
    fail("token refresh response did not include expected OAuth fields")
  }

  auth.access = payload.access_token
  auth.refresh = payload.refresh_token
  auth.expires = Date.now() + payload.expires_in * 1000
  if (payload.id_token) auth.idToken = payload.id_token

  writeAuthFile(authFile)
  return auth
}

async function safeBody(response) {
  try {
    return await response.text()
  } catch {
    return ""
  }
}

function sanitize(text) {
  return String(text || "")
    .replace(/Bearer\s+\S+/gi, "Bearer [redacted]")
    .replace(/eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+/g, "[redacted-token]")
    .replace(/\bsk-[A-Za-z0-9][A-Za-z0-9._:-]{19,}\b/gi, "[redacted-token]")
    .slice(0, 500)
}

function accountIdFrom(auth) {
  return (
    auth.accountIdOverride ||
    decodeJwt(auth.access)?.["https://api.openai.com/auth"]?.chatgpt_account_id ||
    decodeJwt(auth.idToken || "")?.["https://api.openai.com/auth"]?.chatgpt_account_id
  )
}

async function fetchUsage(auth) {
  const accountId = accountIdFrom(auth)
  if (!accountId) fail("could not determine ChatGPT account id from OpenAI OAuth token")

  const headers = {
    Authorization: `Bearer ${auth.access}`,
    "ChatGPT-Account-Id": accountId,
    originator: "codex_cli_rs",
    accept: "application/json",
    "User-Agent": "codex-cli",
  }

  if (auth.organizationIdOverride) {
    headers["OpenAI-Organization"] = auth.organizationIdOverride
  }

  const response = await fetch(USAGE_URL, { headers })
  if (!response.ok) {
    const body = await safeBody(response)
    fail(`usage request failed with HTTP ${response.status}`, sanitize(body))
  }

  return await response.json()
}

function mapWindow(window) {
  if (!window) return null
  const usedPercent = numberOrNull(window.used_percent)
  const leftPercent = usedPercent === null ? null : Math.max(0, Math.round(100 - usedPercent))
  const windowSeconds = numberOrNull(window.limit_window_seconds)
  const resetAtSeconds = numberOrNull(window.reset_at)
  const resetAfterSeconds = numberOrNull(window.reset_after_seconds)
  const resetAtMs = resetAtSeconds
    ? resetAtSeconds * 1000
    : resetAfterSeconds
      ? Date.now() + resetAfterSeconds * 1000
      : null

  return {
    usedPercent,
    leftPercent,
    windowSeconds,
    windowMinutes: windowSeconds ? Math.ceil(windowSeconds / 60) : null,
    resetAtMs,
  }
}

function numberOrNull(value) {
  return typeof value === "number" && Number.isFinite(value) ? value : null
}

function limitName(window, fallback) {
  if (window?.windowMinutes === 300) return "5h limit"
  if (window?.windowMinutes === 10080) return "Weekly limit"
  return fallback
}

function formatReset(ms) {
  if (!ms) return "unknown"
  const date = new Date(ms)
  if (!Number.isFinite(date.getTime())) return "unknown"
  const absolute = date.toLocaleString(undefined, {
    weekday: "short",
    month: "short",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  })
  const deltaMs = ms - Date.now()
  if (deltaMs <= 0) return `${absolute} (now)`
  const minutes = Math.round(deltaMs / 60000)
  if (minutes < 60) return `${absolute} (in ${minutes}m)`
  const hours = Math.floor(minutes / 60)
  const rest = minutes % 60
  return `${absolute} (in ${hours}h ${rest}m)`
}

function formatLimit(label, window) {
  if (!window) return `${label}: unavailable`
  const used = window.usedPercent === null ? "unknown" : `${window.usedPercent}% used`
  const left = window.leftPercent === null ? "unknown left" : `${window.leftPercent}% left`
  return `${label}: ${left} (${used}); resets ${formatReset(window.resetAtMs)}`
}

function creditsSummary(credits) {
  if (!credits) return null
  if (credits.unlimited) return "unlimited"
  if (typeof credits.balance === "string" && credits.balance.trim()) return credits.balance.trim()
  if (credits.has_credits) return "available"
  return null
}

function summarize(payload) {
  const primary = mapWindow(payload.rate_limit?.primary_window)
  const secondary = mapWindow(payload.rate_limit?.secondary_window)
  const limits = [
    primary ? { name: limitName(primary, "Primary limit"), ...primary } : null,
    secondary ? { name: limitName(secondary, "Secondary limit"), ...secondary } : null,
  ]
  const additionalLimits = (Array.isArray(payload.additional_rate_limits) ? payload.additional_rate_limits : [])
    .map((limit) => summarizeAdditionalLimit(limit))
    .filter(Boolean)
  const credits = creditsSummary(payload.credits)

  return {
    ok: true,
    planType: payload.plan_type ?? null,
    allowed: payload.rate_limit?.allowed ?? null,
    limitReached: payload.rate_limit?.limit_reached ?? null,
    limits,
    additionalLimits,
    credits,
  }
}

function summarizeAdditionalLimit(limit) {
  const rateLimit = limit?.rate_limit
  if (!rateLimit) return null

  const primary = mapWindow(rateLimit.primary_window)
  const secondary = mapWindow(rateLimit.secondary_window)
  const limits = [
    primary ? { name: limitName(primary, "5h limit"), ...primary } : null,
    secondary ? { name: limitName(secondary, "Weekly limit"), ...secondary } : null,
  ]

  return {
    name: limit.limit_name ?? limit.metered_feature ?? "Additional limit",
    meteredFeature: limit.metered_feature ?? null,
    allowed: rateLimit.allowed ?? null,
    limitReached: rateLimit.limit_reached ?? null,
    limits,
  }
}

function printHuman(summary) {
  console.log("Codex limits")
  if (summary.planType) console.log(`Plan: ${summary.planType}`)
  if (typeof summary.allowed === "boolean") {
    console.log(`Allowed: ${summary.allowed ? "yes" : "no"}`)
  }
  if (typeof summary.limitReached === "boolean") {
    console.log(`Limit reached: ${summary.limitReached ? "yes" : "no"}`)
  }
  for (const limit of summary.limits) {
    console.log(formatLimit(limit?.name ?? "Limit", limit))
  }
  for (const additionalLimit of summary.additionalLimits) {
    console.log("")
    console.log(additionalLimit.name)
    if (typeof additionalLimit.allowed === "boolean") {
      console.log(`Allowed: ${additionalLimit.allowed ? "yes" : "no"}`)
    }
    if (typeof additionalLimit.limitReached === "boolean") {
      console.log(`Limit reached: ${additionalLimit.limitReached ? "yes" : "no"}`)
    }
    for (const limit of additionalLimit.limits) {
      console.log(formatLimit(limit?.name ?? "Limit", limit))
    }
  }
  if (summary.credits) console.log(`Credits: ${summary.credits}`)
  console.log(`Source: ${USAGE_URL}`)
}

const authFile = readAuthFile()
let auth = authFile.openai
if (!auth || auth.type !== "oauth") fail("OpenAI OAuth credentials are not configured; run `opencode auth login` for OpenAI")

if (!auth.access || !auth.expires || auth.expires <= Date.now() + 60_000) {
  auth = await refreshAccessToken(authFile, auth)
}

const usage = await fetchUsage(auth)
const summary = summarize(usage)

if (jsonMode) {
  console.log(JSON.stringify(summary, null, 2))
} else {
  printHuman(summary)
}
