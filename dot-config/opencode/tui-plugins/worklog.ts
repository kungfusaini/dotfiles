import type { TuiPlugin, TuiPluginModule } from "@opencode-ai/plugin/tui"
import { ensureStore, isDisabled, latestSummary, projectInfo, projectLabel, setDisabled } from "../lib/worklog.js"

function enabledMessage(directory: string) {
  const info = ensureStore(projectInfo(directory))
  return `Worklog enabled · project: ${projectLabel(info)} · status: ${latestSummary(info)}`
}

function disabledMessage(directory: string) {
  const info = ensureStore(projectInfo(directory))
  return `Worklog disabled · project: ${projectLabel(info)}`
}

const tui: TuiPlugin = async (api) => {
  api.keymap.registerLayer({
    commands: [
      {
        name: "worklog.toggle",
        title: "Toggle worklog tracking",
        desc: "Toggle worklog tracking",
        category: "Session",
        namespace: "palette",
        slashName: "worklog",
        run() {
          const info = ensureStore(projectInfo(api.state.path.directory || process.cwd()))
          const enabled = !isDisabled(info.id)
          setDisabled(info.id, enabled)
          api.ui.toast({
            variant: enabled ? "info" : "success",
            message: enabled ? disabledMessage(info.root) : enabledMessage(info.root),
            duration: 5000,
          })
        },
      },
    ],
  })
}

const plugin: TuiPluginModule & { id: string } = {
  id: "sumeet.worklog",
  tui,
}

export default plugin
