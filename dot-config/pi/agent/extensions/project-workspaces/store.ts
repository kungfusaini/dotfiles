import { createHash } from "node:crypto";
import { existsSync, mkdirSync } from "node:fs";
import { homedir } from "node:os";
import path from "node:path";

function dataHome(): string {
	return process.env.XDG_DATA_HOME || path.join(homedir(), ".local", "share");
}

function slugify(input: string): string {
	return input.replace(/[^a-z0-9._-]+/gi, "-").replace(/-+/g, "-").replace(/^-|-$/g, "").toLowerCase().slice(0, 80);
}

export interface ProjectContextInfo {
	scope: "project" | "stream";
	id: string;
	root: string;
	dir: string;
	plans: string;
	project?: any;
	stream?: any;
}

export function projectInfo(workdir: string) {
	const root = path.resolve(workdir);
	const hash = createHash("sha256").update(root).digest("hex").slice(0, 12);
	const parent = path.basename(path.dirname(root));
	const leaf = path.basename(root) || "project";
	const base = slugify(parent && parent !== path.sep ? `${parent}-${leaf}` : leaf);
	const id = `${base || "project"}--${hash}`;
	const dir = path.join(dataHome(), "pi", "projects", id);
	return { root, id, dir };
}

export function ensureStore<T extends ProjectContextInfo>(info: T): T {
	mkdirSync(info.dir, { recursive: true });
	mkdirSync(info.plans, { recursive: true });
	mkdirSync(path.join(info.plans, "active"), { recursive: true });
	mkdirSync(path.join(info.plans, "archive"), { recursive: true });
	if (info.project?.dir) mkdirSync(info.project.dir, { recursive: true });
	return info;
}
