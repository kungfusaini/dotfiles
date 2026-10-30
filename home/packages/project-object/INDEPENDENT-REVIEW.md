## Findings

### Blocker

None identified.

### High

1. **The system wiring is not reproducible or rollback-safe under Nix.**
   Hyprland invokes executables directly from a mutable development checkout rather than installing them through Home Manager/Nix:

   - `/home/sumeet/.config/nixos/home/modules/hypr.nix:65`
   - `/home/sumeet/.config/nixos/home/modules/hypr.nix:224`

   Both `bin/project-picker` and `bin/project-terminal` are currently untracked. The Pi extension is also untracked, despite being referenced by:

   - `/home/sumeet/.config/nixos/home/modules/pi.nix:4`

   In a Git-backed flake, an untracked extension source may be absent from the flake source, while the hard-coded checkout paths bypass Nix generation rollback entirely. The live extension symlink currently points back into the mutable Nix checkout rather than an immutable store path.

   **Required:** install/package both scripts declaratively, reference store/profile paths from Hyprland, and ensure the extension is tracked and deployed immutably.

2. **Registry-controlled IDs and `projectHome` paths can escape the intended XDG trees and trigger writes or privileged prompt injection.**
   Registry validation checks only that three fields are strings:

   - `bin/project-picker:99-107`

   It does not validate UUID format, path containment, duplicate IDs, duplicate normalized names, or safe `projectHome` placement. The picker subsequently creates directories and files at the supplied path:

   - `bin/project-picker:52-60`
   - `bin/project-picker:86-90`

   The terminal similarly creates both project-home and Pi-session paths derived from unvalidated records:

   - `bin/project-terminal:57-62`

   The extension then reads `AGENTS.md` from that path and injects it into the system prompt:

   - `/home/sumeet/.config/nixos/home/config/pi/extensions/project-object.ts:48-62`
   - `/home/sumeet/.config/nixos/home/config/pi/extensions/project-object.ts:84-97`

   A malformed or tampered registry can therefore write outside the application tree and select arbitrary local instructions for system-prompt injection.

   **Required:** strictly validate IDs, records and uniqueness; derive project homes and session directories from validated IDs; reject or explicitly constrain legacy `projectHome` paths before writing or reading.

3. **Human project names are being used as workspace identity without collision protection.**
   Workspace identity is exactly `project["name"]`:

   - `bin/project-picker:173-174`
   - `bin/project-picker:228-235`
   - `bin/project-picker:287-297`

   Name validation only prevents collisions with other projects:

   - `bin/project-picker:181-189`

   It does not reserve global workspaces already configured as `browser`, `comms`, and `music`:

   - `/home/sumeet/.config/nixos/home/modules/hypr.nix:68-70`

   A project named `browser`, for example, would treat the global browser workspace as that project, export project credentials/context to terminals launched there, and make the Pi fallback resolve it as current.

   **Required:** use a stable, namespaced workspace identifier containing the project UUID, or at minimum reject all global/reserved names and unsupported workspace syntax.

### Medium

4. **Creation and opening are not transactional, despite the documented atomicity claim.**
   Project-home files are created before the registry is updated:

   - `bin/project-picker:537-557`

   A registry-write failure leaves an orphan project home. Opening changes the active workspace before writing runtime state:

   - `bin/project-picker:228-235`

   A session-write failure therefore changes the desktop while reporting a failed action. Terminal launch happens last and can also fail after the project is marked open.

   This conflicts with `PICKER-DESIGN.md:181-188` and the failure-coherence requirement.

5. **Pi session isolation is only guaranteed for terminals originally launched with project environment.**
   The project-specific session directory is selected exclusively in the terminal wrapper:

   - `bin/project-terminal:57-72`

   The extension’s active-workspace fallback can attach project prompt context without setting `PI_CODING_AGENT_SESSION_DIR`:

   - `/home/sumeet/.config/nixos/home/config/pi/extensions/project-object.ts:48-54`

   Thus Pi launched from an old/moved terminal, application launcher, or any process not descended from `project-terminal` can receive project context while using the normal shared session lookup. This is acknowledged in `PROJECT-CONTEXT-INTEGRATION.md:132-136`, but means the claimed isolation is conditional.

6. **Pi extension failures are either silently hidden or can break prompt preparation.**
   Malformed/unreadable registry data is treated as “no project” without surfacing an error:

   - `/home/sumeet/.config/nixos/home/config/pi/extensions/project-object.ts:24-32`

   `AGENTS.md` is read synchronously without error handling or a size limit:

   - `/home/sumeet/.config/nixos/home/config/pi/extensions/project-object.ts:91-97`

   Permission errors, races, or very large files can fail a handler or inflate every model request. Explicit IDs also resolve archived projects because only workspace fallback checks `archivedAt` at lines 52-54.

7. **Persisting an absolute derived `projectHome` undermines XDG relocation and migration.**
   The canonical location can be derived from data root plus project ID, yet migration stores the absolute current path:

   - `bin/project-picker:52-53`
   - `bin/project-picker:92-109`
   - live `projects.json:11`

   Changing `XDG_DATA_HOME`, restoring on another machine, or moving the data tree leaves the old absolute path authoritative. The extension and terminal both honor it. Store a relative path or derive the canonical home instead.

8. **Pi session-state directories are created with permissive default modes.**
   `project-terminal` uses plain `mkdir`:

   - `bin/project-terminal:60-62`

   The live state hierarchy is mode `0755`, including `pi-sessions`. Pi transcripts can contain prompts, tool output, paths and other sensitive material. Project state directories should be `0700`, with files restricted accordingly.

9. **The headless demo does not prove the complete system-wide integration.**
   The documentation explicitly says it uses Openbox and fake compositor control:

   - `PROJECT-CONTEXT-INTEGRATION.md:97-106`
   - `PROJECT-CONTEXT-INTEGRATION.md:132-135`

   The contact sheet does show picker selection, exported environment, extension status, `/project`, and a model response. It does **not** prove:
   - the actual Hyprland binding or dispatch;
   - real workspace naming/collision behavior;
   - duplicate-picker handling;
   - restart/session reset;
   - project creation or migration;
   - isolation between two projects sharing a directory.

   No reproducible demo harness or fixtures are present in the repositories.

### Low

10. **Terminal-wrapper registry handling is inconsistent with the picker’s safer failure policy.**
    `project-terminal` performs unchecked JSON loading and schema access:

    - `bin/project-terminal:17-21`
    - `bin/project-terminal:57-72`

    A malformed registry can make the normal terminal shortcuts fail with a traceback rather than notifying the user or safely launching a generic terminal.

11. **Atomic replacement is not durable against sudden power loss.**
    `write_json_atomic` uses a unique temporary and `replace`, which protects against torn readers, but does not flush the file or parent directory:

    - `bin/project-picker:44-49`

    It also writes before setting mode `0600`, briefly relying on the process umask.

12. **The live schema’s intermediate directories have inconsistent permissions.**
    The application root and project directory are `0700`, but the live `projects/` directory is `0755`. The protected parent currently prevents traversal, so this is not an immediate disclosure, but directory creation should consistently enforce intended modes.

---

## Missing tests

There is no checked-in automated test suite. At minimum, add tests for:

- schema validation: duplicate IDs/names, invalid UUIDs, missing fields, malformed JSON;
- path traversal and absolute-ID behavior;
- constrained migration of legacy `projectHome`;
- migration preserving existing files and handling partial failures;
- atomic creation failure and workspace/session-write failure;
- concurrent picker starts and stale locks;
- compositor-instance change resetting runtime state;
- workspace collisions with global, numeric, special and unusual names;
- archived-project behavior through explicit IDs;
- environment propagation with spaces and unusual paths;
- two projects sharing one `mainDirectory` but receiving separate Pi session directories;
- moved/old terminals and direct Pi launches;
- extension lifecycle across start, reload, session switch and shutdown;
- missing, unreadable, changing and oversized `AGENTS.md`;
- malformed registry behavior in both the terminal wrapper and extension;
- Nix/flake evaluation proving all referenced sources are tracked and installed;
- a reproducible headless integration test, plus a real-Hyprland smoke test where safe.

---

## Positive observations

- Durable data, operational state and compositor-session state are conceptually separated into appropriate XDG data, state and runtime locations.
- Runtime state includes `HYPRLAND_INSTANCE_SIGNATURE`, preventing ordinary cross-login open-state reuse.
- Registry and session JSON replacement uses unique temporary files and atomic rename.
- The picker avoids overwriting existing project artifact files during normal migration.
- UUIDs are generated for new project identity; display names are not used as registry identity.
- Environment propagation uses argument arrays and `execvpe`, avoiding shell interpolation.
- `PI_CODING_AGENT_SESSION_DIR` is a supported Pi mechanism.
- The extension uses the structured system-prompt section rather than replacing the complete system prompt.
- TUI-only notification behavior is correctly guarded.
- Live project data is internally consistent: the registered main directory exists, the project home exists, and its core files are mode `0600`.
- The Python files pass static AST parsing, the live registry parses as JSON, and diff whitespace checks passed.

---

## Verdict

**DO NOT SHIP**

Minimum fixes required:

1. Package and deploy the picker and terminal through Nix/Home Manager; track all referenced files and remove mutable checkout paths.
2. Validate project records and IDs strictly, enforce uniqueness, and prevent project/session paths from escaping their XDG roots.
3. Replace human-name workspace identity with a stable namespaced identifier, or comprehensively reserve conflicting names.
4. Make creation/migration/opening failure behavior coherent and recoverable.
5. Define and enforce the Pi session-isolation boundary, including fallback launches.
6. Add extension error handling, prompt-size limits, archived checks, and private state-directory permissions.
7. Add automated schema, migration, isolation, concurrency and Nix evaluation tests.
