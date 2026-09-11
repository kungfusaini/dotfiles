#!/usr/bin/env node
import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { homedir } from "node:os";
import path from "node:path";
import { spawn, spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";

const SOURCE = "sumeet.exe-dev-usage";
const REFRESH_MS = 60_000;
const herdr = process.env.HERDR_BIN_PATH || "herdr";
const scriptPath = fileURLToPath(import.meta.url);
const pluginDir = path.dirname(scriptPath);

function dataHome() { return process.env.XDG_DATA_HOME || path.join(homedir(), ".local", "share"); }
function stateHome() { return process.env.XDG_STATE_HOME || path.join(homedir(), ".local", "state"); }
function vmRegistryPath() { return path.join(dataHome(), "pi", "exe-dev", "vms.json"); }
function stateDir() { return path.join(stateHome(), "herdr"); }
function pidPath() { return path.join(stateDir(), "exe-dev-usage.pid"); }
function logPath() { return path.join(stateDir(), "exe-dev-usage.log"); }
function cachePath() { return path.join(stateDir(), "exe-dev-usage-cache.json"); }
function readJson(file, fallback) { try { return JSON.parse(readFileSync(file, "utf8")); } catch { return fallback; } }
function writeJson(file, value) { mkdirSync(path.dirname(file), { recursive: true }); writeFileSync(file, `${JSON.stringify(value, null, 2)}\n`, "utf8"); }
function writeText(file, value) { mkdirSync(path.dirname(file), { recursive: true }); writeFileSync(file, value, "utf8"); }
function log(message) { try { mkdirSync(stateDir(), { recursive: true }); writeFileSync(logPath(), `${new Date().toISOString()} ${message}\n`, { flag: "a" }); } catch {} }

function run(command, args, timeout = 15_000) {
  return spawnSync(command, args, { encoding: "utf8", stdio: ["ignore", "pipe", "pipe"], timeout });
}
function runJson(command, args, fallback, timeout) {
  const result = run(command, args, timeout);
  if ((result.status ?? 1) !== 0 || !result.stdout) return fallback;
  try { return JSON.parse(result.stdout); } catch { return fallback; }
}
function runAsync(command, args, timeout = 20_000) {
  return new Promise((resolve) => {
    const child = spawn(command, args, { stdio: ["ignore", "pipe", "pipe"] });
    let stdout = "";
    let stderr = "";
    let done = false;
    const finish = (status, signal) => {
      if (done) return;
      done = true;
      clearTimeout(timer);
      resolve({ status, signal, stdout, stderr });
    };
    const timer = setTimeout(() => {
      try { child.kill("SIGTERM"); } catch {}
      finish(124, "timeout");
    }, timeout);
    child.stdout.setEncoding("utf8");
    child.stderr.setEncoding("utf8");
    child.stdout.on("data", (chunk) => { stdout += chunk; });
    child.stderr.on("data", (chunk) => { stderr += chunk; });
    child.on("error", () => finish(1));
    child.on("close", finish);
  });
}
async function runJsonAsync(command, args, fallback, timeout) {
  const result = await runAsync(command, args, timeout);
  if ((result.status ?? 1) !== 0 || !result.stdout) return fallback;
  try { return JSON.parse(result.stdout); } catch { return fallback; }
}

function snapshot() { return runJson(herdr, ["api", "snapshot"], undefined, 10_000)?.result?.snapshot; }
function exeList() { return runJson("ssh", ["exe.dev", "ls", "--json"], { vms: [] }, 20_000)?.vms || []; }
function exeStat(vmName) { return runJson("ssh", ["exe.dev", "stat", "--json", vmName], undefined, 20_000); }
function latestPoint(stat) { return Array.isArray(stat?.points) && stat.points.length ? stat.points[stat.points.length - 1] : undefined; }
function gb(value) { return Number.isFinite(Number(value)) ? Number(value) : undefined; }
function gibFromBytes(bytes) { return Number.isFinite(Number(bytes)) ? Number(bytes) / 1024 / 1024 / 1024 : undefined; }
function fmtGb(value) { if (value === undefined) return "?"; if (value >= 10) return `${value.toFixed(0)}G`; return `${value.toFixed(1)}G`; }
function fmtBytes(bytes) { return fmtGb(gibFromBytes(bytes)); }
function pct(used, total) { return used !== undefined && total ? Math.round((used / total) * 100) : undefined; }
function fmtPct(value) { return value === undefined ? "" : ` ${value}%`; }
function normName(value) { return String(value || "").replace(/\.exe\.xyz$/, ""); }
function vmHost(vmName) { return `${vmName}.exe.xyz`; }
function bar(used, total, width = 12) {
  const ratio = used !== undefined && total ? Math.max(0, Math.min(1, used / total)) : 0;
  const full = Math.round(ratio * width);
  return `${"█".repeat(full)}${"░".repeat(width - full)}`;
}
function add(a, b) { if (a === undefined) return b; if (b === undefined) return a; return a + b; }

function linkedVmByProject() {
  const registry = readJson(vmRegistryPath(), { links: {} });
  const out = new Map();
  for (const [projectID, link] of Object.entries(registry.links || {})) {
    const vmName = link?.defaultVm || Object.keys(link?.vms || {})[0];
    if (!vmName) continue;
    const vm = link?.vms?.[vmName] || { vmName, host: vmHost(vmName) };
    out.set(projectID, { ...vm, vmName: vm.vmName || vmName, host: vm.host || vmHost(vmName) });
  }
  return out;
}
function workspaceProjectKey(ws) { return ws?.tokens?.pi_project_id || ws?.tokens?.pi_project || ws?.label; }
function tokensFor(linkedVm, listVm, statPoint) {
  const vmName = normName(linkedVm?.vmName || linkedVm?.host || listVm?.vm_name || listVm?.ssh_host);
  if (!vmName) return undefined;
  const status = listVm?.status || linkedVm?.status || "linked";
  const cpuUsed = gb(statPoint?.cpu_cores);
  const cpuTotal = gb(statPoint?.cpu_nominal) ?? gb(listVm?.allocated_cpus);
  const memUsed = gibFromBytes(statPoint?.mem_used_bytes);
  const memTotal = gibFromBytes(statPoint?.mem_total_bytes) ?? gibFromBytes(listVm?.memory_capacity_bytes);
  const diskUsed = gb(statPoint?.fs_used_gb) ?? gb(statPoint?.disk_used_gb);
  const diskTotal = gb(statPoint?.fs_total_gb) ?? gb(statPoint?.disk_size_gb) ?? gibFromBytes(listVm?.disk_capacity_bytes);
  return [
    `exe_vm= ${vmName} ${status}`,
    `exe_cpu=CPU ${cpuUsed === undefined ? "?" : cpuUsed.toFixed(2)}/${cpuTotal === undefined ? "?" : cpuTotal.toFixed(0)} cores`,
    `exe_ram=RAM ${fmtGb(memUsed)}/${fmtGb(memTotal)}${fmtPct(pct(memUsed, memTotal))}`,
    `exe_disk=Disk ${fmtGb(diskUsed)}/${fmtGb(diskTotal)}${fmtPct(pct(diskUsed, diskTotal))}`,
  ];
}
function clearWorkspace(workspaceID) {
  run(herdr, ["workspace", "report-metadata", workspaceID, "--source", SOURCE, "--clear-token", "exe_vm", "--clear-token", "exe_cpu", "--clear-token", "exe_ram", "--clear-token", "exe_disk"], 10_000);
}
function reportWorkspace(workspaceID, tokens) {
  const args = ["workspace", "report-metadata", workspaceID, "--source", SOURCE, ...tokens.flatMap((token) => ["--token", token]), "--ttl-ms", String(REFRESH_MS * 3)];
  run(herdr, args, 10_000);
}
function refresh() {
  const snap = snapshot();
  if (!snap) throw new Error("Herdr snapshot unavailable");
  const links = linkedVmByProject();
  const vms = exeList();
  const vmByName = new Map(vms.map((vm) => [normName(vm.vm_name || vm.ssh_host || vm.ssh_dest), vm]));
  const statCache = new Map();
  let reported = 0;
  for (const ws of snap.workspaces || []) {
    const workspaceID = ws?.workspace_id;
    if (!workspaceID) continue;
    const projectKey = workspaceProjectKey(ws);
    const link = links.get(projectKey);
    if (!link) { clearWorkspace(workspaceID); continue; }
    const vmName = normName(link.vmName || link.host);
    const listVm = vmByName.get(vmName);
    if (!statCache.has(vmName)) statCache.set(vmName, latestPoint(exeStat(vmName)));
    const tokens = tokensFor(link, listVm, statCache.get(vmName));
    if (!tokens) { clearWorkspace(workspaceID); continue; }
    reportWorkspace(workspaceID, tokens);
    reported += 1;
  }
  log(`refresh ok workspaces=${reported} vms=${vms.length}`);
  return { ok: true, workspaces: reported, vms: vms.length };
}
function processAlive(pid) { if (!pid || pid === process.pid) return false; try { process.kill(pid, 0); return true; } catch { return false; } }
function ensureDaemon() {
  mkdirSync(stateDir(), { recursive: true });
  const existing = Number(String(existsSync(pidPath()) ? readFileSync(pidPath(), "utf8") : "").trim());
  if (processAlive(existing)) return false;
  const child = spawn(process.execPath, [scriptPath, "daemon"], { detached: true, stdio: "ignore", env: process.env });
  child.unref();
  return true;
}
async function daemon() {
  mkdirSync(stateDir(), { recursive: true });
  writeText(pidPath(), `${process.pid}\n`);
  process.on("exit", () => { try { if (String(readFileSync(pidPath(), "utf8")).trim() === String(process.pid)) writeText(pidPath(), ""); } catch {} });
  for (;;) {
    try { refresh(); } catch (error) { log(`refresh error ${error?.message || error}`); }
    await new Promise((resolve) => setTimeout(resolve, REFRESH_MS));
  }
}

async function fetchPanelData() {
  const [plan, usage, listResult] = await Promise.all([
    runJsonAsync("ssh", ["exe.dev", "billing", "plan", "--json"], undefined, 20_000),
    runJsonAsync("ssh", ["exe.dev", "billing", "usage", "--json"], undefined, 20_000),
    runJsonAsync("ssh", ["exe.dev", "ls", "--json"], { vms: [] }, 20_000),
  ]);
  const vms = (listResult?.vms || []).sort((a, b) => String(a.vm_name || "").localeCompare(String(b.vm_name || "")));
  const stats = await Promise.all(vms.map(async (vm) => {
    const name = normName(vm.vm_name || vm.ssh_host || vm.ssh_dest);
    return [name, latestPoint(await runJsonAsync("ssh", ["exe.dev", "stat", "--json", name], undefined, 20_000))];
  }));
  return { fetchedAt: new Date().toISOString(), plan, usage, vms, stats: Object.fromEntries(stats) };
}
function renderAccountSection(rows, plan, usage) {
  rows.push("Account limits");
  if (!plan && !usage) { rows.push("  billing usage unavailable"); rows.push(""); return; }
  if (plan?.plan || plan?.tier) rows.push(`  Plan ${[plan.plan, plan.tier].filter(Boolean).join(" / ")}`);
  rows.push(`  VMs  ${usage?.vm_count ?? "?"}/${plan?.max_vms ?? "?"}`);
  if (usage?.disk_used_bytes !== undefined || usage?.included_disk_bytes !== undefined) {
    const used = gibFromBytes(usage?.disk_used_bytes);
    const total = gibFromBytes(usage?.included_disk_bytes) ?? gb(plan?.pooled_disk_gb);
    rows.push(`  Disk ${bar(used, total)} ${fmtGb(used)}/${fmtGb(total)}${fmtPct(pct(used, total))}`);
  }
  if (usage?.included_bandwidth_bytes !== undefined) {
    const used = Number(usage?.rx_bytes || 0) + Number(usage?.tx_bytes || 0);
    const total = usage.included_bandwidth_bytes;
    rows.push(`  Net  ${bar(gibFromBytes(used), gibFromBytes(total))} ${fmtBytes(used)}/${fmtBytes(total)}${fmtPct(pct(used, total))}`);
  }
  if (usage?.avg_cpu_cores !== undefined) rows.push(`  Avg CPU this cycle ${Number(usage.avg_cpu_cores).toFixed(2)} cores`);
  if (plan?.max_cpus || plan?.max_memory_gb) rows.push(`  Per-VM max ${plan.max_cpus ?? "?"} CPU / ${plan.max_memory_gb ?? "?"}G RAM`);
  rows.push("");
}
function renderPanelRowsFromData(data, stale = false) {
  const rows = [];
  rows.push("exe.dev usage");
  const date = data?.fetchedAt ? new Date(data.fetchedAt) : new Date();
  rows.push(`${stale ? "cached " : "updated "}${date.toLocaleTimeString()}`);
  rows.push("");
  renderAccountSection(rows, data?.plan, data?.usage);
  const vms = data?.vms || [];
  if (!vms.length) { rows.push("No exe.dev VMs found."); return rows; }

  const entries = vms.map((vm) => {
    const name = normName(vm.vm_name || vm.ssh_host || vm.ssh_dest);
    const point = data?.stats?.[name];
    return {
      vm, name,
      cpuUsed: gb(point?.cpu_cores),
      cpuTotal: gb(point?.cpu_nominal) ?? gb(vm.allocated_cpus),
      memUsed: gibFromBytes(point?.mem_used_bytes),
      memTotal: gibFromBytes(point?.mem_total_bytes) ?? gibFromBytes(vm.memory_capacity_bytes),
      diskUsed: gb(point?.fs_used_gb) ?? gb(point?.disk_used_gb),
      diskTotal: gb(point?.fs_total_gb) ?? gb(point?.disk_size_gb) ?? gibFromBytes(vm.disk_capacity_bytes),
    };
  });
  const totals = entries.reduce((acc, entry) => ({
    cpuUsed: add(acc.cpuUsed, entry.cpuUsed), cpuTotal: add(acc.cpuTotal, entry.cpuTotal),
    memUsed: add(acc.memUsed, entry.memUsed), memTotal: add(acc.memTotal, entry.memTotal),
    diskUsed: add(acc.diskUsed, entry.diskUsed), diskTotal: add(acc.diskTotal, entry.diskTotal),
  }), { cpuUsed: undefined, cpuTotal: undefined, memUsed: undefined, memTotal: undefined, diskUsed: undefined, diskTotal: undefined });
  rows.push(`Live VM totals (${entries.length} VMs, not quota)`);
  rows.push(`  CPU  ${totals.cpuUsed === undefined ? "?" : totals.cpuUsed.toFixed(2)}/${totals.cpuTotal === undefined ? "?" : totals.cpuTotal.toFixed(0)} cores`);
  rows.push(`  RAM  ${bar(totals.memUsed, totals.memTotal)} ${fmtGb(totals.memUsed)}/${fmtGb(totals.memTotal)}${fmtPct(pct(totals.memUsed, totals.memTotal))}`);
  rows.push(`  FS   ${bar(totals.diskUsed, totals.diskTotal)} ${fmtGb(totals.diskUsed)}/${fmtGb(totals.diskTotal)}${fmtPct(pct(totals.diskUsed, totals.diskTotal))}`);
  rows.push("");
  for (const entry of entries) {
    const { vm, name, cpuUsed, cpuTotal, memUsed, memTotal, diskUsed, diskTotal } = entry;
    rows.push(`${name} (${vm.status || "unknown"})`);
    rows.push(`  CPU  ${cpuUsed === undefined ? "?" : cpuUsed.toFixed(2)}/${cpuTotal === undefined ? "?" : cpuTotal.toFixed(0)} cores`);
    rows.push(`  RAM  ${bar(memUsed, memTotal)} ${fmtGb(memUsed)}/${fmtGb(memTotal)}${fmtPct(pct(memUsed, memTotal))}`);
    rows.push(`  FS   ${bar(diskUsed, diskTotal)} ${fmtGb(diskUsed)}/${fmtGb(diskTotal)}${fmtPct(pct(diskUsed, diskTotal))}`);
    if (vm.comment) rows.push(`  ${String(vm.comment).slice(0, 38)}`);
    rows.push("");
  }
  rows.push("Ctrl-C closes panel");
  return rows;
}
function draw(lines) { process.stdout.write("\x1b[2J\x1b[H" + lines.join("\n") + "\n"); }
function exePanelPanes() {
  const snap = snapshot();
  return (snap?.panes || []).filter((pane) => pane?.label === "exe.dev Usage" || String(pane?.cwd || "") === pluginDir);
}
function togglePanel() {
  const panes = exePanelPanes();
  if (panes.length > 0) {
    for (const pane of panes) run(herdr, ["plugin", "pane", "close", pane.pane_id], 10_000);
    return { ok: true, action: "closed", panes: panes.map((pane) => pane.pane_id) };
  }
  const result = run(herdr, ["plugin", "pane", "open", "--plugin", SOURCE, "--entrypoint", "panel", "--placement", "split", "--direction", "right", "--no-focus"], 10_000);
  return { ok: (result.status ?? 1) === 0, action: "opened", stdout: result.stdout?.trim(), stderr: result.stderr?.trim() };
}
async function panel() {
  process.stdout.write("\x1b[?25l");
  const cleanup = () => process.stdout.write("\x1b[?25h\x1b[0m\n");
  process.on("SIGINT", () => { cleanup(); process.exit(0); });
  process.on("SIGTERM", () => { cleanup(); process.exit(0); });

  const cached = readJson(cachePath(), undefined);
  if (cached) draw(renderPanelRowsFromData(cached, true));
  else draw(["exe.dev usage", "", "Loading account and VM usage…", "", "Ctrl-C closes panel"]);

  for (;;) {
    try {
      const data = await fetchPanelData();
      writeJson(cachePath(), data);
      draw(renderPanelRowsFromData(data));
    } catch (error) {
      log(`panel error ${error?.message || error}`);
      draw(["exe.dev usage", "", `Error: ${error?.message || String(error)}`, "", "Will retry…"]);
    }
    await new Promise((resolve) => setTimeout(resolve, REFRESH_MS));
  }
}

const mode = process.argv[2] || "refresh";
if (mode === "daemon") await daemon();
else if (mode === "panel") await panel();
else if (mode === "toggle") {
  const result = togglePanel();
  console.log(JSON.stringify(result, null, 2));
  process.exit(result.ok ? 0 : 1);
} else {
  let result;
  try { result = refresh(); } catch (error) { result = { ok: false, error: error?.message || String(error) }; log(`refresh error ${result.error}`); }
  if (mode === "startup") result.daemon_started = ensureDaemon();
  console.log(JSON.stringify(result, null, 2));
  process.exit(result.ok ? 0 : 1);
}
