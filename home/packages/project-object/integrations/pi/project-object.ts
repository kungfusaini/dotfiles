import { execFileSync } from "node:child_process";
import { closeSync, constants, fchmodSync, fstatSync, fsyncSync, mkdirSync, openSync, readFileSync, readSync, realpathSync, statSync, writeSync } from "node:fs";
import { homedir } from "node:os";
import { isAbsolute, join, relative, resolve } from "node:path";
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";

const MAX_REGISTRY_BYTES = 1024 * 1024;
const MAX_AGENTS_BYTES = 64 * 1024;
const MAX_WORKLOG_BYTES = 32 * 1024 * 1024;
const MAX_WORKLOG_ENTRY_BYTES = 16 * 1024;
const UUID_PATTERN = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;
const WORKLOG_TYPES = ["start", "progress", "decision", "mistake", "stuck", "finish", "next", "note"] as const;
const WORKLOG_TYPE_SET = new Set<string>(WORKLOG_TYPES);

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
};

type ProjectRecord = {
  id: string;
  name: string;
  mainDirectory: string;
  archivedAt?: string | null;
};

type ProjectContext = ProjectRecord & {
  projectHome: string;
  agentsFile: string;
};

type Resolution = { project?: ProjectContext; error?: string };

export function dataRoot(): string {
  return resolve(process.env.PROJECT_OBJECT_DATA_DIR || join(process.env.XDG_DATA_HOME || join(homedir(), ".local", "share"), "project-object"));
}

function canonicalProjectHome(id: string): string {
  return join(dataRoot(), "projects", id);
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
    if (explicitId && !UUID_PATTERN.test(explicitId)) throw new Error("PROJECT_OBJECT_ID is not a canonical UUID");
    const workspace = explicitId ? undefined : activeWorkspace();
    const project = explicitId
      ? projects.find((candidate) => candidate.id === explicitId && !candidate.archivedAt)
      : projects.find((candidate) => !candidate.archivedAt && candidate.name === workspace);
    if (!project) return {};
    const projectHome = canonicalProjectHome(project.id);
    return { project: { ...project, projectHome, agentsFile: join(projectHome, "AGENTS.md") } };
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
  const validated: WorklogParametersValue = {
    type: parameters.type,
    summary: trimmedField(parameters.summary, "summary", 2000)!,
    task: trimmedField(parameters.task, "task", 2000),
    next: trimmedField(parameters.next, "next", 4000),
    reason: trimmedField(parameters.reason, "reason", 4000),
    lesson: trimmedField(parameters.lesson, "lesson", 4000),
    blocker: trimmedField(parameters.blocker, "blocker", 4000),
    result: trimmedField(parameters.result, "result", 4000),
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

export function appendProjectWorklogEntry(project: ProjectContext, parameters: WorklogParametersValue, sessionId: string): string {
  const validated = validateWorklogParameters(parameters);
  let projectDescriptor: number;
  try {
    projectDescriptor = openSync(project.projectHome, constants.O_RDONLY | constants.O_DIRECTORY | constants.O_NOFOLLOW);
  } catch (error) {
    throw new Error(`cannot open project home safely: ${(error as Error).message}`);
  }

  try {
    const expectedHome = join(realpathSync(dataRoot()), "projects", project.id);
    const openedHome = realpathSync(`/proc/self/fd/${projectDescriptor}`);
    if (openedHome !== expectedHome) throw new Error("opened project home does not match the canonical UUID path");

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
      return join(project.projectHome, "worklogs", "events.jsonl");
    } finally {
      closeSync(worklogsDescriptor);
    }
  } finally {
    closeSync(projectDescriptor);
  }
}

export function readAgentInstructions(project: ProjectContext, afterProjectDirectoryOpened?: () => void): string {
  let directoryDescriptor: number;
  try {
    directoryDescriptor = openSync(project.projectHome, constants.O_RDONLY | constants.O_DIRECTORY | constants.O_NOFOLLOW);
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code === "ENOENT") return `Project: ${project.name}\nProject home: ${project.projectHome}\nThe project AGENTS.md file is missing.`;
    throw new Error(`cannot open project home safely: ${(error as Error).message}`);
  }

  try {
    const expectedHome = join(realpathSync(dataRoot()), "projects", project.id);
    const openedHome = realpathSync(`/proc/self/fd/${directoryDescriptor}`);
    if (openedHome !== expectedHome) throw new Error("opened project home does not match the canonical UUID path");

    afterProjectDirectoryOpened?.();

    let descriptor: number;
    try {
      descriptor = openSync(`/proc/self/fd/${directoryDescriptor}/AGENTS.md`, constants.O_RDONLY | constants.O_NOFOLLOW);
    } catch (error) {
      if ((error as NodeJS.ErrnoException).code === "ENOENT") return `Project: ${project.name}\nProject home: ${project.projectHome}\nThe project AGENTS.md file is missing.`;
      throw new Error(`cannot open AGENTS.md safely: ${(error as Error).message}`);
    }

    try {
      const metadata = fstatSync(descriptor);
      if (!metadata.isFile()) throw new Error("AGENTS.md must be a regular file");
      if (metadata.size > MAX_AGENTS_BYTES) throw new Error(`AGENTS.md exceeds the ${MAX_AGENTS_BYTES}-byte limit`);

      const resolvedFile = realpathSync(`/proc/self/fd/${descriptor}`);
      const openedHome = realpathSync(`/proc/self/fd/${directoryDescriptor}`);
      if (relative(openedHome, resolvedFile) !== "AGENTS.md") throw new Error("AGENTS.md does not belong to the pinned project directory");

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

  pi.on("session_start", async (_event, ctx) => {
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
    ctx.ui.setStatus("project-object", ctx.ui.theme.fg("accent", `Project: ${project.name}`));
    if (ctx.mode === "tui") ctx.ui.notify(`Project context loaded: ${project.name}`, "info");
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
    const worklogGuidance = "For meaningful progress, decisions, mistakes, blockers, completed work, or a concrete next step, append one concise durable entry with project_worklog_append before wrapping up. Never put credentials, tokens, private keys, or other secrets in a worklog.";
    try {
      event.systemPromptOptions.sections.project_object = `${readAgentInstructions(project)}\n\n${worklogGuidance}`;
    } catch (error) {
      event.systemPromptOptions.sections.project_object = `Project: ${project.name}\nProject home: ${project.projectHome}\nProject AGENTS.md was not loaded: ${(error as Error).message}\n\n${worklogGuidance}`;
    }
  });

  pi.registerTool({
    name: "project_worklog_append",
    label: "Project worklog",
    description: "Append one concise durable event to the attached Project Object worklog. Use only for meaningful continuity: starts, progress, decisions, mistakes, blockers, finishes, next actions, or notes. Never include credentials, tokens, private keys, or other secrets.",
    parameters: WorklogParameters,
    async execute(_toolCallId, parameters, _signal, _onUpdate, ctx) {
      if (!resolution.project && !resolution.error) resolution = resolveProject();
      if (resolution.error) throw new Error(`Project context error: ${resolution.error}`);
      const project = resolution.project;
      if (!project) throw new Error("No project object is attached to this Pi session");
      const worklog = appendProjectWorklogEntry(project, parameters as WorklogParametersValue, ctx.sessionManager.getSessionId());
      return {
        content: [{ type: "text", text: `${parameters.type}: ${parameters.summary}` }],
        details: { projectId: project.id, worklog, type: parameters.type },
      };
    },
  });

  pi.registerCommand("catchup", {
    description: "Summarize where project work stopped and what to do next",
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
      pi.sendUserMessage([
        `Catch me up on where we left off in the ${project.name} project and what I should do next.`,
        "Do not introduce or explain the project to me. Assume I remember what the project is.",
        "Use tools to inspect the newest relevant worklog entries first, then TODO.md and NOTES.md in the project home, plus uncommitted Git changes and recent commits in the main directory when it is a Git repository.",
        `Worklog: ${join(project.projectHome, "worklogs", "events.jsonl")}`,
        `Project home: ${project.projectHome}`,
        `Main directory: ${project.mainDirectory}`,
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
      ctx.ui.notify([
        `Project: ${project.name}`,
        `Main directory: ${project.mainDirectory}`,
        `Project home: ${project.projectHome}`,
        `Agent instructions: ${project.agentsFile}`,
      ].join("\n"), "info");
    },
  });
}
