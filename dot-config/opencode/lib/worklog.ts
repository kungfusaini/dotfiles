import { createHash } from "node:crypto"
import { appendFileSync, existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs"
import { homedir } from "node:os"
import path from "node:path"

export const WORKLOG_VERSION = 1
export const ALLOWED_TYPES = new Set(["start", "progress", "decision", "mistake", "stuck", "finish", "next", "note"])

export type WorklogState = {
  disabled: Record<string, boolean>
  updatedAt?: string
}

export type WorklogEntry = {
  v?: number
  time: string
  type: string
  summary: string
  task?: string
  next?: string
  reason?: string
  lesson?: string
  blocker?: string
  result?: string
  files?: string[]
  session?: string
  project?: string
  root?: string
}

export type WorklogInfo = {
  cwd: string
  root: string
  id: string
  dir: string
  log: string
}

function slugify(input: string) {
  return input
    .replace(/[^a-z0-9._-]+/gi, "-")
    .replace(/-+/g, "-")
    .replace(/^-|-$/g, "")
    .toLowerCase()
    .slice(0, 80)
}

export function projectInfo(workdir: string): WorklogInfo {
  const cwd = path.resolve(workdir)
  const root = cwd
  const hash = createHash("sha256").update(root).digest("hex").slice(0, 12)
  const parent = path.basename(path.dirname(root))
  const leaf = path.basename(root) || "project"
  const base = slugify(parent && parent !== path.sep ? `${parent}-${leaf}` : leaf)
  const id = `${base || "project"}--${hash}`
  const dataHome = process.env.XDG_DATA_HOME || path.join(homedir(), ".local", "share")
  const dir = path.join(dataHome, "opencode", "project-logs", id)
  return { cwd, root, id, dir, log: path.join(dir, "worklog.jsonl") }
}

function stateFile() {
  const stateRoot = process.env.XDG_STATE_HOME || path.join(homedir(), ".local", "state")
  const dir = path.join(stateRoot, "opencode", "worklog")
  return { dir, file: path.join(dir, "state.json") }
}

function readState(): WorklogState {
  const { file } = stateFile()
  if (!existsSync(file)) return { disabled: {} }
  try {
    const raw = readFileSync(file, "utf8")
    const parsed = JSON.parse(raw)
    const disabled = parsed?.disabled && typeof parsed.disabled === "object" ? parsed.disabled : {}
    return { ...parsed, disabled } as WorklogState
  } catch {
    return { disabled: {} }
  }
}

function writeState(state: WorklogState) {
  const { dir, file } = stateFile()
  mkdirSync(dir, { recursive: true })
  writeFileSync(file, `${JSON.stringify({ ...state, updatedAt: new Date().toISOString() }, null, 2)}\n`, "utf8")
}

export function isDisabled(projectID: string): boolean {
  return Boolean(readState().disabled[projectID])
}

export function setDisabled(projectID: string, disabled: boolean) {
  const state = readState()
  writeState({
    ...state,
    disabled: {
      ...state.disabled,
      [projectID]: disabled,
    },
    updatedAt: new Date().toISOString(),
  })
}

export function ensureStore(info: WorklogInfo) {
  mkdirSync(info.dir, { recursive: true })
  if (!existsSync(info.log)) {
    const first: WorklogEntry = {
      v: WORKLOG_VERSION,
      time: new Date().toISOString(),
      type: "note",
      summary: "Created worklog file for this project.",
      next: "Append the first start/progress/decision entry when work begins.",
      project: info.id,
      root: info.root,
    }
    writeFileSync(info.log, `${JSON.stringify(first)}\n`, "utf8")
  }
  return info
}

export function parseEntries(text: string) {
  return text
    .split(/\r?\n/)
    .filter(Boolean)
    .map((line) => {
      try {
        return JSON.parse(line) as WorklogEntry
      } catch {
        return null
      }
    })
    .filter(Boolean) as WorklogEntry[]
}

export function readAllEntries(file: string): WorklogEntry[] {
  if (!existsSync(file)) return []
  return parseEntries(readFileSync(file, "utf8"))
}

export function appendWorklogEntry(info: WorklogInfo, entry: WorklogEntry) {
  ensureStore(info)
  appendFileSync(info.log, `${JSON.stringify(entry)}\n`, "utf8")
}

export function projectLabel(info: WorklogInfo) {
  return info.id.replace(/--[a-f0-9]+$/i, "") || path.basename(info.root) || info.id
}

export function latestSummary(info: WorklogInfo) {
  const latest = readAllEntries(info.log).at(-1)
  if (!latest) return "No recent worklog summary"
  if (latest.summary) return latest.summary
  if (latest.next) return latest.next
  if (latest.result) return latest.result
  return `${latest.type} update recorded`
}
