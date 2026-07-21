import { realpathSync } from "node:fs";
import { pathToFileURL } from "node:url";
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { matchesKey } from "@earendil-works/pi-tui";

const PATCH_STATE = Symbol.for("sumeet.pi.tree-tab-toggle");
const COLLAPSE_INITIALIZED = Symbol.for("sumeet.pi.tree-default-collapse.initialized");

type TreeListInternals = {
  flatNodes: Array<{ node: { entry: { id: string } } }>;
  filteredNodes: Array<{ node: { entry: { id: string } } }>;
  selectedIndex: number;
  foldedNodes: Set<string>;
  isFoldable(entryId: string): boolean;
  applyFilter(): void;
};

type TreeSelectorInternals = {
  labelInput: unknown;
  [COLLAPSE_INITIALIZED]?: boolean;
  getTreeList(): TreeListInternals;
};

type PatchState = {
  original?: (this: TreeSelectorInternals, keyData: string) => void;
  originalHandleInput?: (this: TreeSelectorInternals, keyData: string) => void;
  originalRender?: (this: TreeSelectorInternals, width: number) => string[];
};

export default async function (_pi: ExtensionAPI) {
  // Pi does not currently expose a smart fold-toggle keybinding. Patch only the
  // built-in tree component; Tab keeps its normal completion behavior elsewhere.
  // Resolve from Pi's running CLI rather than this extension. Core packages are
  // available to extension imports, but are not in this file's Node resolution path.
  const agentCliUrl = pathToFileURL(realpathSync(process.argv[1]));
  const treeSelectorUrl = new URL(
    "./modes/interactive/components/tree-selector.js",
    agentCliUrl,
  );
  const { TreeSelectorComponent } = await import(treeSelectorUrl.href);
  const prototype = TreeSelectorComponent.prototype as typeof TreeSelectorComponent.prototype & {
    [PATCH_STATE]?: PatchState;
  };

  const existingState = prototype[PATCH_STATE];
  const state: Required<Pick<PatchState, "originalHandleInput" | "originalRender">> = {
    originalHandleInput: existingState?.originalHandleInput ?? existingState?.original ?? prototype.handleInput,
    originalRender: existingState?.originalRender ?? prototype.render,
  };
  prototype[PATCH_STATE] = state;

  prototype.render = function (this: TreeSelectorInternals, width: number): string[] {
    if (!this[COLLAPSE_INITIALIZED]) {
      this[COLLAPSE_INITIALIZED] = true;
      const tree = this.getTreeList();
      for (const node of tree.flatNodes) {
        const entryId = node.node.entry.id;
        if (tree.isFoldable(entryId)) tree.foldedNodes.add(entryId);
      }
      tree.applyFilter();
    }

    return state.originalRender.call(this, width);
  };

  prototype.handleInput = function (this: TreeSelectorInternals, keyData: string): void {
    if (!this.labelInput && matchesKey(keyData, "tab")) {
      const tree = this.getTreeList();
      const entryId = tree.filteredNodes[tree.selectedIndex]?.node.entry.id;
      if (!entryId) return;

      if (tree.foldedNodes.has(entryId)) {
        tree.foldedNodes.delete(entryId);
        tree.applyFilter();
      } else if (tree.isFoldable(entryId)) {
        tree.foldedNodes.add(entryId);
        tree.applyFilter();
      }
      return;
    }

    state.originalHandleInput.call(this, keyData);
  };
}
