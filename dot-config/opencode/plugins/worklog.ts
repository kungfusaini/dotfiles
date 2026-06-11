import { tool, type Plugin } from "@opencode-ai/plugin"
import {
  ALLOWED_TYPES,
  WORKLOG_VERSION,
  appendWorklogEntry,
  ensureStore,
  isDisabled,
  projectInfo,
  type WorklogEntry,
} from "../lib/worklog.js"

const worklogAppendTool = tool({
  description: "Append a worklog event to the current project worklog",
  args: {
    type: tool.schema.string().describe("Event type: start, progress, decision, mistake, stuck, finish, next, note"),
    summary: tool.schema.string().describe("Short summary text"),
    task: tool.schema.string().optional().describe("Optional task context"),
    next: tool.schema.string().optional().describe("Next action/context"),
    reason: tool.schema.string().optional().describe("Reason for decision/mistake"),
    lesson: tool.schema.string().optional().describe("Lesson for mistake"),
    blocker: tool.schema.string().optional().describe("What is blocking progress"),
    result: tool.schema.string().optional().describe("Result summary"),
    file: tool.schema.array(tool.schema.string()).optional().describe("Files related to this entry"),
    session: tool.schema.string().optional().describe("Session id"),
  },
  async execute(args, context) {
    const info = ensureStore(projectInfo(context.directory))
    if (isDisabled(info.id)) {
      return "Worklog tracking is disabled for this project."
    }

    const type = args.type.trim().toLowerCase()
    if (!ALLOWED_TYPES.has(type)) {
      return `❌ Invalid type: ${args.type}`
    }

    context.metadata({ title: "Writing to worklog" })

    const entry: WorklogEntry = {
      v: WORKLOG_VERSION,
      time: new Date().toISOString(),
      session: args.session || context.messageID || context.sessionID || "unknown",
      project: info.id,
      root: info.root,
      type,
      summary: args.summary,
      task: args.task,
      next: args.next,
      reason: args.reason,
      lesson: args.lesson,
      blocker: args.blocker,
      result: args.result,
      files: args.file,
    }

    appendWorklogEntry(info, entry)
    return {
      title: `Wrote to worklog: ${entry.summary}`,
      output: `${entry.type}: ${entry.summary}`,
    }
  },
})

export const WorklogPlugin: Plugin = async () => {
  return {
    tool: {
      worklog_append: worklogAppendTool,
    },
  }
}

export default WorklogPlugin
