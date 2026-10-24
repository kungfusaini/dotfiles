import { execFileSync } from "node:child_process";
import { existsSync, readFileSync } from "node:fs";
import { homedir } from "node:os";
import { join } from "node:path";
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";

type ProjectRecord = {
  id: string;
  name: string;
  mainDirectory: string;
  projectHome?: string;
  archivedAt?: string | null;
};

type ProjectContext = ProjectRecord & {
  projectHome: string;
  agentsFile: string;
};

function dataRoot(): string {
  return process.env.PROJECT_OBJECT_DATA_DIR || join(process.env.XDG_DATA_HOME || join(homedir(), ".local", "share"), "project-object");
}

function loadProjects(): ProjectRecord[] {
  const registry = join(dataRoot(), "projects.json");
  if (!existsSync(registry)) return [];
  try {
    const parsed = JSON.parse(readFileSync(registry, "utf8"));
    return Array.isArray(parsed.projects) ? parsed.projects : [];
  } catch {
    return [];
  }
}

function activeWorkspace(): string | undefined {
  try {
    const output = execFileSync("hyprctl", ["activeworkspace", "-j"], {
      encoding: "utf8",
      stdio: ["ignore", "pipe", "ignore"],
      timeout: 1000,
    });
    return String(JSON.parse(output).name || "") || undefined;
  } catch {
    return undefined;
  }
}

function resolveProject(): ProjectContext | undefined {
  const projects = loadProjects();
  const explicitId = process.env.PROJECT_OBJECT_ID;
  const workspace = explicitId ? undefined : activeWorkspace();
  const project = explicitId
    ? projects.find((candidate) => candidate.id === explicitId)
    : projects.find((candidate) => !candidate.archivedAt && candidate.name === workspace);

  if (!project) return undefined;
  const projectHome = project.projectHome || join(dataRoot(), "projects", project.id);
  return {
    ...project,
    projectHome,
    agentsFile: join(projectHome, "AGENTS.md"),
  };
}

export default function projectObjectExtension(pi: ExtensionAPI) {
  let project: ProjectContext | undefined;

  pi.on("session_start", async (_event, ctx) => {
    project = resolveProject();
    if (!project) {
      ctx.ui.setStatus("project-object", undefined);
      return;
    }

    ctx.ui.setStatus(
      "project-object",
      ctx.ui.theme.fg("accent", `Project: ${project.name}`),
    );
    if (ctx.mode === "tui") {
      ctx.ui.notify(`Project context loaded: ${project.name}`, "info");
    }
  });

  pi.on("before_agent_start", (event) => {
    project ||= resolveProject();
    if (!project) {
      delete event.systemPromptOptions.sections.project_object;
      return;
    }

    if (!existsSync(project.agentsFile)) {
      event.systemPromptOptions.sections.project_object = `Project: ${project.name}\nProject home: ${project.projectHome}\nThe project AGENTS.md file is missing.`;
      return;
    }

    const instructions = readFileSync(project.agentsFile, "utf8").trim();
    event.systemPromptOptions.sections.project_object = instructions;
  });

  pi.registerCommand("project", {
    description: "Show the project object attached to this Pi session",
    handler: async (_args, ctx) => {
      project ||= resolveProject();
      if (!project) {
        ctx.ui.notify("No project object is attached to this Pi session", "warning");
        return;
      }
      ctx.ui.notify(
        [
          `Project: ${project.name}`,
          `Main directory: ${project.mainDirectory}`,
          `Project home: ${project.projectHome}`,
          `Agent instructions: ${project.agentsFile}`,
        ].join("\n"),
        "info",
      );
    },
  });
}
