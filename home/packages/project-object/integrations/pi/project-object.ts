import { execFileSync } from "node:child_process";
import { closeSync, constants, fchmodSync, fstatSync, fsyncSync, lstatSync, mkdirSync, openSync, readFileSync, readSync, realpathSync, renameSync, statSync, unlinkSync, writeSync } from "node:fs";
import { homedir } from "node:os";
import { isAbsolute, join, relative, resolve } from "node:path";
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";

const MAX_REGISTRY_BYTES = 1024 * 1024;
const MAX_STREAM_REGISTRY_BYTES = 1024 * 1024;
const MAX_AGENTS_BYTES = 64 * 1024;
const MAX_WORKLOG_BYTES = 32 * 1024 * 1024;
const MAX_WORKLOG_ENTRY_BYTES = 16 * 1024;
const MAX_RECENT_WORKLOG_EVENTS = 10;
const MAX_RECENT_WORKLOG_BYTES = 8 * 1024;
const MAX_WORKLOG_TAIL_BYTES = 12 * MAX_WORKLOG_ENTRY_BYTES;
const UUID_PATTERN = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;
const WORKLOG_TYPES = ["start", "progress", "decision", "mistake", "stuck", "finish", "next", "note"] as const;
const WORKLOG_TYPE_SET = new Set<string>(WORKLOG_TYPES);

const StreamCreateParameters = {
  type: "object",
  additionalProperties: false,
  required: ["name", "scope", "initialTasks"],
  properties: {
    name: { type: "string", minLength: 1, maxLength: 200 },
    scope: { type: "string", minLength: 1, maxLength: 4000, description: "Concise durable purpose, responsibilities, and boundaries for the stream's AGENTS.md." },
    initialTasks: {
      type: "array",
      minItems: 1,
      maxItems: 10,
      description: "Concrete initial work for the stream's TODO.md. Use plain single-line task text.",
      items: { type: "string", minLength: 1, maxLength: 1000 },
    },
  },
} as const;

const WorklogParameters = {
  type: "object",
  additionalProperties: false,
  required: ["type", "summary"],
  properties: {
    type: { type: "string", enum: WORKLOG_TYPES },
    summary: { type: "string", minLength: 1, maxLength: 2000 },
    task: { type: "string", minLength: 1, maxLength: 2000 },
    next: { type: "string", minLength: 1, maxLength: 4000 },
    reason: { type: "string", minLength: 1, maxLength: 4000 },
    lesson: { type: "string", minLength: 1, maxLength: 4000 },
    blocker: { type: "string", minLength: 1, maxLength: 4000 },
    result: { type: "string", minLength: 1, maxLength: 4000 },
    files: { type: "array", maxItems: 32, items: { type: "string", minLength: 1, maxLength: 4096 } },
    projectAttention: { type: "boolean", description: "Request parent-project review without copying or promoting this stream event." },
  },
} as const;

type WorklogParametersValue = {
  type: string;
  summary: string;
  task?: string;
  next?: string;
  reason?: string;
  lesson?: string;
  blocker?: string;
  result?: string;
  files?: string[];
  projectAttention?: boolean;
};

type ProjectRecord = {
  id: string;
  name: string;
  mainDirectory: string;
  archivedAt?: string | null;
};

type StreamRecord = {
  id: string;
  name: string;
  mainDirectory?: string | null;
  archivedAt?: string | null;
};

type ProjectContext = ProjectRecord & {
  projectHome: string;
  agentsFile: string;
};

type StreamContext = StreamRecord & {
  projectId: string;
  streamHome: string;
  agentsFile: string;
  mainDirectory: string;
};

type Resolution = { project?: ProjectContext; stream?: StreamContext; error?: string };

export function dataRoot(): string {
  return resolve(process.env.PROJECT_OBJECT_DATA_DIR || join(process.env.XDG_DATA_HOME || join(homedir(), ".local", "share"), "project-object"));
}

function runtimeRoot(): string {
  return resolve(process.env.PROJECT_OBJECT_RUNTIME_DIR || join(process.env.XDG_RUNTIME_DIR || `/tmp/project-object-${process.getuid()}`, "project-object"));
}

function activityFile(): string {
  return join(runtimeRoot(), "pi-activity", `${process.pid}.json`);
}

function writeActivity(resolution: Resolution, state: "working" | "idle"): void {
  const project = resolution.project;
  if (!project) return;
  const directory = join(runtimeRoot(), "pi-activity");
  mkdirSync(directory, { recursive: true, mode: 0o700 });
  const directoryMetadata = lstatSync(directory);
  if (directoryMetadata.isSymbolicLink() || !directoryMetadata.isDirectory()) throw new Error("Pi activity directory must be a regular non-symlink directory");
  const target = activityFile();
  const temporary = join(directory, `.${process.pid}.${Date.now()}.${Math.random().toString(16).slice(2)}.tmp`);
  const payload = `${JSON.stringify({
    version: 1,
    pid: process.pid,
    projectId: project.id,
    streamId: resolution.stream?.id || null,
    state,
    updatedAt: new Date().toISOString(),
  })}\n`;
  let descriptor: number | undefined;
  try {
    descriptor = openSync(temporary, constants.O_WRONLY | constants.O_CREAT | constants.O_EXCL | constants.O_NOFOLLOW, 0o600);
    fchmodSync(descriptor, 0o600);
    writeSync(descriptor, payload);
    fsyncSync(descriptor);
    closeSync(descriptor);
    descriptor = undefined;
    renameSync(temporary, target);
  } finally {
    if (descriptor !== undefined) closeSync(descriptor);
    try { unlinkSync(temporary); } catch (error) {
      if ((error as NodeJS.ErrnoException).code !== "ENOENT") throw error;
    }
  }
}

function removeActivity(): void {
  try { unlinkSync(activityFile()); } catch (error) {
    if ((error as NodeJS.ErrnoException).code !== "ENOENT") throw error;
  }
}

function initSkillFile(): string {
  const configRoot = process.env.XDG_CONFIG_HOME || join(homedir(), ".config");
  return join(configRoot, "project-object", "init", "SKILL.md");
}

function canonicalProjectHome(id: string): string {
  return join(dataRoot(), "projects", id);
}

function canonicalStreamHome(projectId: string, streamId: string): string {
  return join(canonicalProjectHome(projectId), "streams", streamId);
}

function streamWorkspaceName(projectName: string, streamName: string): string {
  return `${projectName} · ${streamName}`;
}

function validateRegistry(parsed: unknown): ProjectRecord[] {
  if (!parsed || typeof parsed !== "object" || (parsed as { version?: unknown }).version !== 1 || !Array.isArray((parsed as { projects?: unknown }).projects)) {
    throw new Error("unsupported or malformed project registry");
  }
  const ids = new Set<string>();
  const names = new Set<string>();
  return (parsed as { projects: unknown[] }).projects.map((raw, index) => {
    if (!raw || typeof raw !== "object") throw new Error(`project record ${index} is not an object`);
    const record = raw as Record<string, unknown>;
    if (typeof record.id !== "string" || !UUID_PATTERN.test(record.id)) throw new Error(`project record ${index} has an invalid UUID`);
    if (typeof record.name !== "string" || record.name !== record.name.trim() || !record.name || /[\r\n\t]/.test(record.name)) throw new Error(`project ${record.id} has an invalid name`);
    if (typeof record.mainDirectory !== "string" || !isAbsolute(record.mainDirectory) || resolve(record.mainDirectory) !== record.mainDirectory) throw new Error(`project ${record.id} has an invalid mainDirectory`);
    if (record.archivedAt !== undefined && record.archivedAt !== null && typeof record.archivedAt !== "string") throw new Error(`project ${record.id} has an invalid archivedAt`);
    if (record.projectHome !== undefined && record.projectHome !== canonicalProjectHome(record.id)) throw new Error(`project ${record.id} has an unsafe projectHome`);
    const normalizedName = record.name.trim().normalize("NFKC").toLowerCase();
    if (ids.has(record.id)) throw new Error(`duplicate project ID: ${record.id}`);
    if (names.has(normalizedName)) throw new Error(`duplicate normalized project name: ${record.name}`);
    ids.add(record.id);
    names.add(normalizedName);
    return { id: record.id, name: record.name, mainDirectory: record.mainDirectory, archivedAt: record.archivedAt as string | null | undefined };
  });
}

function validateStreams(parsed: unknown, project: ProjectRecord): StreamRecord[] {
  if (!parsed || typeof parsed !== "object" || (parsed as { version?: unknown }).version !== 1 || !Array.isArray((parsed as { streams?: unknown }).streams)) {
    throw new Error(`unsupported or malformed stream registry for project ${project.id}`);
  }
  const ids = new Set<string>();
  const names = new Set<string>();
  return (parsed as { streams: unknown[] }).streams.map((raw, index) => {
    if (!raw || typeof raw !== "object") throw new Error(`stream record ${index} is not an object`);
    const record = raw as Record<string, unknown>;
    if (typeof record.id !== "string" || !UUID_PATTERN.test(record.id)) throw new Error(`stream record ${index} has an invalid UUID`);
    if (typeof record.name !== "string" || record.name !== record.name.trim() || !record.name || /[\r\n\t]/.test(record.name)) throw new Error(`stream ${record.id} has an invalid name`);
    if (record.mainDirectory !== undefined && record.mainDirectory !== null && (typeof record.mainDirectory !== "string" || !isAbsolute(record.mainDirectory) || resolve(record.mainDirectory) !== record.mainDirectory)) throw new Error(`stream ${record.id} has an invalid mainDirectory`);
    if (record.archivedAt !== undefined && record.archivedAt !== null && typeof record.archivedAt !== "string") throw new Error(`stream ${record.id} has an invalid archivedAt`);
    const normalizedName = record.name.trim().normalize("NFKC").toLowerCase();
    if (ids.has(record.id)) throw new Error(`duplicate stream ID: ${record.id}`);
    if (names.has(normalizedName)) throw new Error(`duplicate normalized stream name: ${record.name}`);
    ids.add(record.id);
    names.add(normalizedName);
    return { id: record.id, name: record.name, mainDirectory: record.mainDirectory as string | null | undefined, archivedAt: record.archivedAt as string | null | undefined };
  });
}

function loadStreams(project: ProjectRecord): StreamRecord[] {
  const registry = join(canonicalProjectHome(project.id), "streams.json");
  let metadata;
  try {
    metadata = lstatSync(registry);
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code === "ENOENT") return [];
    throw new Error(`cannot inspect stream registry: ${(error as Error).message}`);
  }
  if (metadata.isSymbolicLink() || !metadata.isFile()) throw new Error("stream registry must be a regular non-symlink file");
  if (metadata.size > MAX_STREAM_REGISTRY_BYTES) throw new Error(`stream registry exceeds ${MAX_STREAM_REGISTRY_BYTES} bytes`);
  try {
    return validateStreams(JSON.parse(readFileSync(registry, "utf8")), project);
  } catch (error) {
    throw new Error(`cannot load stream registry: ${(error as Error).message}`);
  }
}

export function loadProjects(): ProjectRecord[] {
  const registry = join(dataRoot(), "projects.json");
  let metadata;
  try {
    metadata = statSync(registry);
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code === "ENOENT") return [];
    throw new Error(`cannot inspect project registry: ${(error as Error).message}`);
  }
  if (metadata.size > MAX_REGISTRY_BYTES) throw new Error(`project registry exceeds ${MAX_REGISTRY_BYTES} bytes`);
  try {
    return validateRegistry(JSON.parse(readFileSync(registry, "utf8")));
  } catch (error) {
    throw new Error(`cannot load project registry: ${(error as Error).message}`);
  }
}

function activeWorkspace(): string | undefined {
  try {
    const output = execFileSync(process.env.PROJECT_PICKER_HYPRCTL || "hyprctl", ["activeworkspace", "-j"], {
      encoding: "utf8",
      stdio: ["ignore", "pipe", "ignore"],
      timeout: 1000,
    });
    return String(JSON.parse(output).name || "") || undefined;
  } catch {
    return undefined;
  }
}

export function resolveProject(): Resolution {
  try {
    const projects = loadProjects();
    const explicitId = process.env.PROJECT_OBJECT_ID;
    const explicitStreamId = process.env.PROJECT_OBJECT_STREAM_ID;
    if (explicitId && !UUID_PATTERN.test(explicitId)) throw new Error("PROJECT_OBJECT_ID is not a canonical UUID");
    if (explicitStreamId && !UUID_PATTERN.test(explicitStreamId)) throw new Error("PROJECT_OBJECT_STREAM_ID is not a canonical UUID");
    if (explicitStreamId && !explicitId) throw new Error("PROJECT_OBJECT_STREAM_ID requires PROJECT_OBJECT_ID");

    const workspace = explicitId ? undefined : activeWorkspace();
    let project = explicitId ? projects.find((candidate) => candidate.id === explicitId && !candidate.archivedAt) : undefined;
    let stream: StreamRecord | undefined;

    if (project && explicitStreamId) {
      stream = loadStreams(project).find((candidate) => candidate.id === explicitStreamId && !candidate.archivedAt);
      if (!stream) throw new Error(`attached stream not found: ${explicitStreamId}`);
    } else if (!explicitId && workspace) {
      const matches: Array<{ project: ProjectRecord; stream?: StreamRecord }> = [];
      for (const candidate of projects.filter((item) => !item.archivedAt)) {
        if (candidate.name === workspace) matches.push({ project: candidate });
        for (const candidateStream of loadStreams(candidate)) {
          if (!candidateStream.archivedAt && streamWorkspaceName(candidate.name, candidateStream.name) === workspace) {
            matches.push({ project: candidate, stream: candidateStream });
          }
        }
      }
      if (matches.length > 1) throw new Error(`ambiguous project or stream workspace name: ${JSON.stringify(workspace)}`);
      if (matches.length === 1) {
        project = matches[0].project;
        stream = matches[0].stream;
      }
    }
    if (!project) return {};

    const projectHome = canonicalProjectHome(project.id);
    const projectContext: ProjectContext = { ...project, projectHome, agentsFile: join(projectHome, "AGENTS.md") };
    if (!stream) return { project: projectContext };
    const streamHome = canonicalStreamHome(project.id, stream.id);
    return {
      project: projectContext,
      stream: {
        ...stream,
        projectId: project.id,
        streamHome,
        agentsFile: join(streamHome, "AGENTS.md"),
        mainDirectory: stream.mainDirectory || project.mainDirectory,
      },
    };
  } catch (error) {
    return { error: (error as Error).message };
  }
}

function trimmedField(value: string | undefined, name: string, maximum: number): string | undefined {
  if (value === undefined) return undefined;
  if (typeof value !== "string") throw new Error(`${name} must be a string`);
  const trimmed = value.trim();
  if (!trimmed) throw new Error(`${name} must not be empty`);
  if (trimmed.length > maximum) throw new Error(`${name} exceeds ${maximum} characters`);
  return trimmed;
}

function validateWorklogParameters(parameters: WorklogParametersValue): WorklogParametersValue {
  if (!WORKLOG_TYPE_SET.has(parameters.type)) throw new Error(`invalid worklog type: ${parameters.type}`);
  if (parameters.projectAttention !== undefined && typeof parameters.projectAttention !== "boolean") throw new Error("projectAttention must be a boolean");
  const validated: WorklogParametersValue = {
    type: parameters.type,
    summary: trimmedField(parameters.summary, "summary", 2000)!,
    task: trimmedField(parameters.task, "task", 2000),
    next: trimmedField(parameters.next, "next", 4000),
    reason: trimmedField(parameters.reason, "reason", 4000),
    lesson: trimmedField(parameters.lesson, "lesson", 4000),
    blocker: trimmedField(parameters.blocker, "blocker", 4000),
    result: trimmedField(parameters.result, "result", 4000),
    projectAttention: parameters.projectAttention,
  };
  if (parameters.files !== undefined) {
    if (!Array.isArray(parameters.files) || parameters.files.length > 32) throw new Error("files must contain at most 32 paths");
    validated.files = parameters.files.map((file, index) => trimmedField(file, `files[${index}]`, 4096)!);
  }
  if (validated.type === "decision" && !validated.reason) throw new Error("decision entries require reason");
  if (validated.type === "mistake" && !validated.lesson) throw new Error("mistake entries require lesson");
  if (validated.type === "stuck" && !validated.blocker) throw new Error("stuck entries require blocker");
  return validated;
}

export function appendProjectWorklogEntry(project: ProjectContext, parameters: WorklogParametersValue, sessionId: string, stream?: StreamContext): string {
  const validated = validateWorklogParameters(parameters);
  if (validated.projectAttention && !stream) throw new Error("projectAttention is only valid for stream worklog entries");
  const scopeHome = stream?.streamHome || project.projectHome;
  const scopeLabel = stream ? "stream" : "project";
  let projectDescriptor: number;
  try {
    projectDescriptor = openSync(scopeHome, constants.O_RDONLY | constants.O_DIRECTORY | constants.O_NOFOLLOW);
  } catch (error) {
    throw new Error(`cannot open ${scopeLabel} home safely: ${(error as Error).message}`);
  }

  try {
    const expectedHome = stream
      ? join(realpathSync(dataRoot()), "projects", project.id, "streams", stream.id)
      : join(realpathSync(dataRoot()), "projects", project.id);
    const openedHome = realpathSync(`/proc/self/fd/${projectDescriptor}`);
    if (openedHome !== expectedHome) throw new Error(`opened ${scopeLabel} home does not match the canonical UUID path`);

    const worklogsPath = `/proc/self/fd/${projectDescriptor}/worklogs`;
    try {
      mkdirSync(worklogsPath, { mode: 0o700 });
    } catch (error) {
      if ((error as NodeJS.ErrnoException).code !== "EEXIST") throw error;
    }

    let worklogsDescriptor: number;
    try {
      worklogsDescriptor = openSync(worklogsPath, constants.O_RDONLY | constants.O_DIRECTORY | constants.O_NOFOLLOW);
    } catch (error) {
      throw new Error(`cannot open worklogs directory safely: ${(error as Error).message}`);
    }

    try {
      const worklogsMetadata = fstatSync(worklogsDescriptor);
      if (!worklogsMetadata.isDirectory()) throw new Error("worklogs must be a directory");
      if (realpathSync(`/proc/self/fd/${worklogsDescriptor}`) !== join(openedHome, "worklogs")) throw new Error("worklogs directory escapes project home");
      fchmodSync(worklogsDescriptor, 0o700);

      const entry = {
        v: 1,
        time: new Date().toISOString(),
        project: project.id,
        ...(stream ? { scope: "stream", stream: { id: stream.id, name: stream.name } } : { scope: "project" }),
        session: sessionId,
        ...validated,
      };
      const serialized = `${JSON.stringify(entry)}\n`;
      const entryBytes = Buffer.byteLength(serialized);
      if (entryBytes > MAX_WORKLOG_ENTRY_BYTES) throw new Error(`worklog entry exceeds ${MAX_WORKLOG_ENTRY_BYTES} bytes`);

      let worklogDescriptor: number;
      try {
        worklogDescriptor = openSync(
          `/proc/self/fd/${worklogsDescriptor}/events.jsonl`,
          constants.O_WRONLY | constants.O_APPEND | constants.O_CREAT | constants.O_NOFOLLOW,
          0o600,
        );
      } catch (error) {
        throw new Error(`cannot open worklog safely: ${(error as Error).message}`);
      }

      try {
        const metadata = fstatSync(worklogDescriptor);
        if (!metadata.isFile() || metadata.nlink !== 1) throw new Error("worklog must be a regular, singly linked file");
        if (metadata.size + entryBytes > MAX_WORKLOG_BYTES) throw new Error(`worklog exceeds ${MAX_WORKLOG_BYTES} bytes`);
        fchmodSync(worklogDescriptor, 0o600);
        const written = writeSync(worklogDescriptor, serialized);
        if (written !== entryBytes) throw new Error("short write while appending worklog entry");
        fsyncSync(worklogDescriptor);
        fsyncSync(worklogsDescriptor);
      } finally {
        closeSync(worklogDescriptor);
      }
      return join(scopeHome, "worklogs", "events.jsonl");
    } finally {
      closeSync(worklogsDescriptor);
    }
  } finally {
    closeSync(projectDescriptor);
  }
}

function compactWorklogText(value: unknown, name: string, maximum: number, required = false): string | undefined {
  if (value === undefined && !required) return undefined;
  if (typeof value !== "string") throw new Error(`worklog ${name} must be a string`);
  const compact = value.replace(/\s+/g, " ").trim();
  if (!compact) throw new Error(`worklog ${name} must not be empty`);
  return compact.length <= maximum ? compact : `${compact.slice(0, maximum - 1)}…`;
}

export function readRecentWorklog(project: ProjectContext, stream?: StreamContext): string {
  const scopeHome = stream?.streamHome || project.projectHome;
  const scopeLabel = stream ? "stream" : "project";
  let scopeDescriptor: number;
  try {
    scopeDescriptor = openSync(scopeHome, constants.O_RDONLY | constants.O_DIRECTORY | constants.O_NOFOLLOW);
  } catch (error) {
    throw new Error(`cannot open ${scopeLabel} home safely: ${(error as Error).message}`);
  }

  try {
    const expectedHome = stream
      ? join(realpathSync(dataRoot()), "projects", project.id, "streams", stream.id)
      : join(realpathSync(dataRoot()), "projects", project.id);
    const openedHome = realpathSync(`/proc/self/fd/${scopeDescriptor}`);
    if (openedHome !== expectedHome) throw new Error(`opened ${scopeLabel} home does not match the canonical UUID path`);

    let worklogsDescriptor: number;
    try {
      worklogsDescriptor = openSync(`/proc/self/fd/${scopeDescriptor}/worklogs`, constants.O_RDONLY | constants.O_DIRECTORY | constants.O_NOFOLLOW);
    } catch (error) {
      if ((error as NodeJS.ErrnoException).code === "ENOENT") return "";
      throw new Error(`cannot open worklogs directory safely: ${(error as Error).message}`);
    }

    try {
      if (realpathSync(`/proc/self/fd/${worklogsDescriptor}`) !== join(openedHome, "worklogs")) throw new Error("worklogs directory escapes scope home");
      let descriptor: number;
      try {
        descriptor = openSync(`/proc/self/fd/${worklogsDescriptor}/events.jsonl`, constants.O_RDONLY | constants.O_NOFOLLOW);
      } catch (error) {
        if ((error as NodeJS.ErrnoException).code === "ENOENT") return "";
        throw new Error(`cannot open worklog safely: ${(error as Error).message}`);
      }

      try {
        const metadata = fstatSync(descriptor);
        if (!metadata.isFile() || metadata.nlink !== 1) throw new Error("worklog must be a regular, singly linked file");
        if (metadata.size > MAX_WORKLOG_BYTES) throw new Error(`worklog exceeds ${MAX_WORKLOG_BYTES} bytes`);
        if (metadata.size === 0) return "";

        const readBytes = Math.min(metadata.size, MAX_WORKLOG_TAIL_BYTES);
        const buffer = Buffer.alloc(readBytes);
        const count = readSync(descriptor, buffer, 0, readBytes, metadata.size - readBytes);
        let text = buffer.subarray(0, count).toString("utf8");
        if (metadata.size > readBytes) {
          const firstNewline = text.indexOf("\n");
          text = firstNewline >= 0 ? text.slice(firstNewline + 1) : "";
        }
        const lines = text.split("\n").filter((line) => line.trim()).slice(-MAX_RECENT_WORKLOG_EVENTS);
        const rendered: string[] = [];
        for (const line of lines) {
          let raw: Record<string, unknown>;
          try {
            raw = JSON.parse(line) as Record<string, unknown>;
          } catch (error) {
            throw new Error(`worklog contains malformed JSON: ${(error as Error).message}`);
          }
          if (raw.v !== 1 || raw.project !== project.id || raw.scope !== (stream ? "stream" : "project")) throw new Error("worklog entry does not match the attached scope");
          if (stream) {
            const entryStream = raw.stream as Record<string, unknown> | undefined;
            if (!entryStream || entryStream.id !== stream.id) throw new Error("worklog entry does not match the attached stream");
          }
          if (typeof raw.type !== "string" || !WORKLOG_TYPE_SET.has(raw.type)) throw new Error("worklog entry has an invalid type");
          const time = compactWorklogText(raw.time, "time", 40, true)!;
          const summary = compactWorklogText(raw.summary, "summary", 1000, true)!;
          const details = [
            ["Result", compactWorklogText(raw.result, "result", 800)],
            ["Reason", compactWorklogText(raw.reason, "reason", 500)],
            ["Lesson", compactWorklogText(raw.lesson, "lesson", 500)],
            ["Next", compactWorklogText(raw.next, "next", 800)],
            ["Blocker", compactWorklogText(raw.blocker, "blocker", 800)],
          ].filter((item): item is [string, string] => Boolean(item[1]));
          rendered.push([`[${time} · ${raw.type}] ${summary}`, ...details.map(([label, value]) => `  ${label}: ${value}`)].join("\n"));
        }

        const selected: string[] = [];
        let bytes = 0;
        for (const event of rendered.reverse()) {
          const eventBytes = Buffer.byteLength(event) + (selected.length ? 2 : 0);
          if (bytes + eventBytes > MAX_RECENT_WORKLOG_BYTES) break;
          selected.unshift(event);
          bytes += eventBytes;
        }
        return selected.join("\n\n");
      } finally {
        closeSync(descriptor);
      }
    } finally {
      closeSync(worklogsDescriptor);
    }
  } finally {
    closeSync(scopeDescriptor);
  }
}

export function readAgentInstructions(project: ProjectContext, afterProjectDirectoryOpened?: () => void, stream?: StreamContext): string {
  const scopeHome = stream?.streamHome || project.projectHome;
  const scopeLabel = stream ? "Stream" : "Project";
  const scopeName = stream?.name || project.name;
  let directoryDescriptor: number;
  try {
    directoryDescriptor = openSync(scopeHome, constants.O_RDONLY | constants.O_DIRECTORY | constants.O_NOFOLLOW);
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code === "ENOENT") return `${scopeLabel}: ${scopeName}\n${scopeLabel} home: ${scopeHome}\nThe ${scopeLabel.toLowerCase()} AGENTS.md file is missing.`;
    throw new Error(`cannot open ${scopeLabel.toLowerCase()} home safely: ${(error as Error).message}`);
  }

  try {
    const expectedHome = stream
      ? join(realpathSync(dataRoot()), "projects", project.id, "streams", stream.id)
      : join(realpathSync(dataRoot()), "projects", project.id);
    const openedHome = realpathSync(`/proc/self/fd/${directoryDescriptor}`);
    if (openedHome !== expectedHome) throw new Error(`opened ${scopeLabel.toLowerCase()} home does not match the canonical UUID path`);

    afterProjectDirectoryOpened?.();

    let descriptor: number;
    try {
      descriptor = openSync(`/proc/self/fd/${directoryDescriptor}/AGENTS.md`, constants.O_RDONLY | constants.O_NOFOLLOW);
    } catch (error) {
      if ((error as NodeJS.ErrnoException).code === "ENOENT") return `${scopeLabel}: ${scopeName}\n${scopeLabel} home: ${scopeHome}\nThe ${scopeLabel.toLowerCase()} AGENTS.md file is missing.`;
      throw new Error(`cannot open AGENTS.md safely: ${(error as Error).message}`);
    }

    try {
      const metadata = fstatSync(descriptor);
      if (!metadata.isFile()) throw new Error("AGENTS.md must be a regular file");
      if (metadata.size > MAX_AGENTS_BYTES) throw new Error(`AGENTS.md exceeds the ${MAX_AGENTS_BYTES}-byte limit`);

      const resolvedFile = realpathSync(`/proc/self/fd/${descriptor}`);
      const openedHome = realpathSync(`/proc/self/fd/${directoryDescriptor}`);
      if (relative(openedHome, resolvedFile) !== "AGENTS.md") throw new Error(`AGENTS.md does not belong to the pinned ${scopeLabel.toLowerCase()} directory`);

      const chunks: Buffer[] = [];
      let total = 0;
      while (total <= MAX_AGENTS_BYTES) {
        const chunk = Buffer.alloc(Math.min(8192, MAX_AGENTS_BYTES + 1 - total));
        const count = readSync(descriptor, chunk, 0, chunk.length, null);
        if (count === 0) break;
        chunks.push(chunk.subarray(0, count));
        total += count;
      }
      if (total > MAX_AGENTS_BYTES) throw new Error(`AGENTS.md exceeds the ${MAX_AGENTS_BYTES}-byte limit`);
      return Buffer.concat(chunks).toString("utf8").trim();
    } catch (error) {
      throw new Error(`cannot read AGENTS.md: ${(error as Error).message}`);
    } finally {
      closeSync(descriptor);
    }
  } finally {
    closeSync(directoryDescriptor);
  }
}

export default function projectObjectExtension(pi: ExtensionAPI) {
  let resolution: Resolution = {};
  let startupWorklog = "";
  let startupWorklogError: string | undefined;

  pi.on("session_start", async (_event, ctx) => {
    startupWorklog = "";
    startupWorklogError = undefined;
    try { removeActivity(); } catch { /* advisory */ }
    resolution = resolveProject();
    if (resolution.error) {
      ctx.ui.setStatus("project-object", ctx.ui.theme.fg("error", "Project context error"));
      if (ctx.hasUI) ctx.ui.notify(`Project context disabled: ${resolution.error}`, "error");
      return;
    }
    const project = resolution.project;
    if (!project) {
      ctx.ui.setStatus("project-object", undefined);
      return;
    }
    const stream = resolution.stream;
    try {
      startupWorklog = readRecentWorklog(project, stream);
    } catch (error) {
      startupWorklogError = (error as Error).message;
    }
    const label = stream ? `Project: ${project.name} · Stream: ${stream.name}` : `Project: ${project.name}`;
    ctx.ui.setStatus("project-object", ctx.ui.theme.fg("accent", label));
    try { writeActivity(resolution, "idle"); } catch { /* Activity is advisory and must never block Pi. */ }
    if (ctx.mode === "tui") ctx.ui.notify(`${label} context loaded`, "info");
  });

  pi.on("agent_start", () => {
    try { writeActivity(resolution, "working"); } catch { /* advisory */ }
  });

  pi.on("agent_settled", () => {
    try { writeActivity(resolution, "idle"); } catch { /* advisory */ }
  });

  pi.on("session_shutdown", () => {
    try { removeActivity(); } catch { /* advisory */ }
  });

  pi.on("before_agent_start", (event) => {
    if (!resolution.project && !resolution.error) resolution = resolveProject();
    if (resolution.error) {
      event.systemPromptOptions.sections.project_object = `Project context was not loaded because validation failed: ${resolution.error}`;
      return;
    }
    const project = resolution.project;
    if (!project) {
      delete event.systemPromptOptions.sections.project_object;
      return;
    }
    const stream = resolution.stream;
    const worklogScope = stream ? `the ${stream.name} stream` : "the project";
    const worklogGuidance = `When a durable conversational fact, requirement, decision, mistake, blocker, completed result, or concrete next step becomes clear, append one concise entry with project_worklog_append then rather than waiting for shutdown. It writes to ${worklogScope}; do not log casual conversation or copy stream details into project artifacts automatically. Never put credentials, tokens, private keys, or other secrets in a worklog.`;
    const instructions: string[] = [];
    try {
      instructions.push(readAgentInstructions(project));
    } catch (error) {
      instructions.push(`Project: ${project.name}\nProject home: ${project.projectHome}\nProject AGENTS.md was not loaded: ${(error as Error).message}`);
    }
    if (stream) {
      try {
        instructions.push(readAgentInstructions(project, undefined, stream));
      } catch (error) {
        instructions.push(`Stream: ${stream.name}\nStream home: ${stream.streamHome}\nStream AGENTS.md was not loaded: ${(error as Error).message}`);
      }
    }
    if (startupWorklog) instructions.push(`Recent ${stream ? "stream" : "project"} worklog (up to 10 newest events):\n${startupWorklog}`);
    if (startupWorklogError) instructions.push(`Recent worklog was not loaded: ${startupWorklogError}`);
    if (!stream) instructions.push("When the user asks to create a stream under this project, a stream in the picker, or a project workspace, use project_stream_create. Do not use the workstream skill unless the user explicitly asks for an isolated Git worktree or worker session.");
    instructions.push(worklogGuidance);
    instructions.push("For configured external APIs, use `project-api list` to discover APIs enabled for this project, `project-api describe <id>` for docs and authentication metadata, and `project-api request <id> <GET|POST|PUT|PATCH|DELETE> </path>` for authenticated calls. Never put credentials in prompts or worklogs. Existing CLIs such as `gh` are separate.");
    event.systemPromptOptions.sections.project_object = instructions.join("\n\n");
  });

  pi.registerTool({
    name: "project_stream_create",
    label: "Create project stream",
    description: "Create and register a ready-to-use Project Object stream under the attached project so it appears in the project picker. Use this whenever the user asks for a stream under this project, a picker stream, or a project workspace. Never substitute the Git workstream skill. Derive a concise AGENTS.md scope and concrete initial TODO.md tasks from the user's request. NOTES.md remains blank. This does not open the stream workspace or launch an agent.",
    promptSnippet: "Create Project Object streams that appear under the attached project in the picker.",
    promptGuidelines: ["For a stream under the attached project or in the picker, use project_stream_create rather than the Git workstream skill."],
    parameters: StreamCreateParameters,
    async execute(_toolCallId, parameters) {
      if (!resolution.project && !resolution.error) resolution = resolveProject();
      if (resolution.error) throw new Error(`Project context error: ${resolution.error}`);
      const project = resolution.project;
      if (!project) throw new Error("No project object is attached to this Pi session");
      if (resolution.stream) throw new Error("Streams can only be created from a project-level Pi session");

      const executable = process.env.PROJECT_OBJECT_STREAM_CLI || "project-picker-tui";
      let output: string;
      try {
        output = execFileSync(executable, [
          "--create-stream", parameters.name,
          "--project-id", project.id,
          "--scope", parameters.scope,
          "--tasks-json", JSON.stringify(parameters.initialTasks),
        ], {
          encoding: "utf8",
          stdio: ["ignore", "pipe", "pipe"],
          timeout: 5000,
        });
      } catch (error) {
        const failure = error as Error & { stderr?: Buffer | string };
        const stderr = String(failure.stderr || "").trim();
        throw new Error(stderr || `Could not create stream: ${failure.message}`);
      }

      let created: { projectId: string; streamId: string; name: string; streamHome: string; workspaceName: string };
      try {
        created = JSON.parse(output) as typeof created;
      } catch (error) {
        throw new Error(`Stream creation returned invalid output: ${(error as Error).message}`);
      }
      return {
        content: [{ type: "text", text: `Created stream “${created.name}” in ${project.name}. It is now available in the project picker.` }],
        details: created,
      };
    },
  });

  pi.registerTool({
    name: "project_worklog_append",
    label: "Project/stream worklog",
    description: "Append one concise durable event to the attached scope worklog. Stream-scoped sessions write to the stream; project-scoped sessions write to the project. Set projectAttention only when parent-project review is genuinely needed; it requests review but does not copy or promote the event. Never include credentials or secrets.",
    parameters: WorklogParameters,
    async execute(_toolCallId, parameters, _signal, _onUpdate, ctx) {
      if (!resolution.project && !resolution.error) resolution = resolveProject();
      if (resolution.error) throw new Error(`Project context error: ${resolution.error}`);
      const project = resolution.project;
      if (!project) throw new Error("No project object is attached to this Pi session");
      const stream = resolution.stream;
      const worklog = appendProjectWorklogEntry(project, parameters as WorklogParametersValue, ctx.sessionManager.getSessionId(), stream);
      return {
        content: [{ type: "text", text: `${parameters.type}: ${parameters.summary}` }],
        details: { projectId: project.id, streamId: stream?.id, scope: stream ? "stream" : "project", worklog, type: parameters.type },
      };
    },
  });

  pi.registerCommand("init", {
    description: "Initialize pristine artifacts for the attached project or stream once",
    handler: async (args, ctx) => {
      if (!ctx.isIdle()) {
        ctx.ui.notify("Wait for the current response to finish before running /init", "warning");
        return;
      }
      if (!resolution.project && !resolution.error) resolution = resolveProject();
      if (resolution.error) {
        ctx.ui.notify(`Project context error: ${resolution.error}`, "error");
        return;
      }
      const project = resolution.project;
      const stream = resolution.stream;
      if (!project) {
        ctx.ui.notify("/init requires a project- or stream-attached Pi session", "warning");
        return;
      }
      const scopeHome = stream?.streamHome || project.projectHome;
      const scopeName = stream?.name || project.name;
      const scopeKind = stream ? "stream" : "project";
      const marker = join(scopeHome, ".project-object-initialized.json");
      try {
        const metadata = lstatSync(marker);
        if (metadata.isSymbolicLink() || !metadata.isFile()) {
          ctx.ui.notify(`${scopeKind === "stream" ? "Stream" : "Project"} initialization marker is unsafe; refusing /init`, "error");
        } else {
          ctx.ui.notify(`${scopeName} has already been initialized`, "warning");
        }
        return;
      } catch (error) {
        if ((error as NodeJS.ErrnoException).code !== "ENOENT") {
          ctx.ui.notify(`Cannot inspect ${scopeKind} initialization state: ${(error as Error).message}`, "error");
          return;
        }
      }

      const suppliedGoal = args.trim();
      pi.sendUserMessage([
        stream
          ? `Initialize the pristine ${stream.name} stream in the ${project.name} project.`
          : `Initialize the pristine ${project.name} project.`,
        `Before doing anything else, read and follow the complete one-time init skill at: ${initSkillFile()}`,
        "The skill guard is authoritative. If it refuses, make no changes.",
        "This is setup only: do not begin substantive investigation, SSH, implementation, deployment, or external actions.",
        suppliedGoal ? `User-supplied goal or context: ${suppliedGoal}` : "Use the active conversation to infer the goal; ask one concise question only if it is genuinely unclear.",
      ].join("\n"));
    },
  });

  pi.registerCommand("catchup", {
    description: "Summarize where the attached project or stream work stopped",
    handler: async (args, ctx) => {
      if (!ctx.isIdle()) {
        ctx.ui.notify("Wait for the current response to finish before running /catchup", "warning");
        return;
      }
      if (!resolution.project && !resolution.error) resolution = resolveProject();
      if (resolution.error) {
        ctx.ui.notify(`Project context error: ${resolution.error}`, "error");
        return;
      }
      const project = resolution.project;
      if (!project) {
        ctx.ui.notify("No project object is attached to this Pi session", "warning");
        return;
      }

      const optionalFocus = args.trim();
      const stream = resolution.stream;
      const scopeHome = stream?.streamHome || project.projectHome;
      const mainDirectory = stream?.mainDirectory || project.mainDirectory;
      const scopeDescription = stream ? `${stream.name} stream in the ${project.name} project` : `${project.name} project`;
      pi.sendUserMessage([
        `Catch me up on where we left off in the ${scopeDescription} and what I should do next.`,
        "Do not introduce or explain the project to me. Assume I remember what it is.",
        `Use tools to inspect the newest relevant worklog entries first, then TODO.md as the current task list and NOTES.md only when relevant, plus uncommitted Git changes and recent commits in the working directory when it is a Git repository. Treat repository or application data as authoritative for mutable operational facts. ${stream ? "Use inherited project instructions as stable background; keep detailed stream findings local." : "Include bounded stream activity and unresolved projectAttention worklog entries when relevant, without copying stream detail into project artifacts."}`,
        `Worklog: ${join(scopeHome, "worklogs", "events.jsonl")}`,
        `Scope home: ${scopeHome}`,
        `Project home: ${project.projectHome}`,
        `Main directory: ${mainDirectory}`,
        "Reply concisely under exactly these headings: What we were doing; Where we left off; What's next.",
        "Prefer concrete recent evidence. If the records are sparse, say what you inferred from Git rather than filling space with general project background.",
        optionalFocus ? `Pay particular attention to: ${optionalFocus}` : "",
      ].filter(Boolean).join("\n"));
    },
  });

  pi.registerCommand("project", {
    description: "Show the project object attached to this Pi session",
    handler: async (_args, ctx) => {
      if (!resolution.project && !resolution.error) resolution = resolveProject();
      if (resolution.error) {
        ctx.ui.notify(`Project context error: ${resolution.error}`, "error");
        return;
      }
      const project = resolution.project;
      if (!project) {
        ctx.ui.notify("No project object is attached to this Pi session", "warning");
        return;
      }
      const stream = resolution.stream;
      ctx.ui.notify([
        `Project: ${project.name}`,
        ...(stream ? [
          `Stream: ${stream.name}`,
          `Working directory: ${stream.mainDirectory}`,
          `Stream home: ${stream.streamHome}`,
          `Stream instructions: ${stream.agentsFile}`,
        ] : [`Main directory: ${project.mainDirectory}`]),
        `Project home: ${project.projectHome}`,
        `Project instructions: ${project.agentsFile}`,
      ].join("\n"), "info");
    },
  });
}
