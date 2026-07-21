import { realpathSync } from "node:fs";
import { pathToFileURL } from "node:url";
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { matchesKey } from "@earendil-works/pi-tui";

const PATCH_STATE = Symbol.for("sumeet.pi.tree-tab-toggle");

type TreeListInternals = {
  filteredNodes: Array<{ node: { entry: { id: string } } }>;
  selectedIndex: number;
  foldedNodes: Set<string>;
  isFoldable(entryId: string): boolean;
  applyFilter(): void;
};

type TreeSelectorInternals = {
  labelInput: unknown;
  getTreeList(): TreeListInternals;
};

type PatchState = {
  original: (this: TreeSelectorInternals, keyData: string) => void;
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

  const state = prototype[PATCH_STATE] ?? { original: prototype.handleInput };
  prototype[PATCH_STATE] = state;

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

    state.original.call(this, keyData);
  };
}
