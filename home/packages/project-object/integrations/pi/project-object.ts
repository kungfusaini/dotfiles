import { execFileSync } from "node:child_process";
import { closeSync, constants, fstatSync, openSync, readFileSync, readSync, realpathSync, statSync } from "node:fs";
import { homedir } from "node:os";
import { isAbsolute, join, relative, resolve } from "node:path";
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";

const MAX_REGISTRY_BYTES = 1024 * 1024;
const MAX_AGENTS_BYTES = 64 * 1024;
const UUID_PATTERN = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;

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
    try {
      event.systemPromptOptions.sections.project_object = readAgentInstructions(project);
    } catch (error) {
      event.systemPromptOptions.sections.project_object = `Project: ${project.name}\nProject home: ${project.projectHome}\nProject AGENTS.md was not loaded: ${(error as Error).message}`;
    }
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
        "Use tools to inspect the newest relevant worklogs first, then TODO.md and NOTES.md in the project home, plus uncommitted Git changes and recent commits in the main directory when it is a Git repository.",
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
