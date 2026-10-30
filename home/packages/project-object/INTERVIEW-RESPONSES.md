# System-wide Project Object — Interview Responses

## Question 1 — Ideal workflow

### Response

A global shortcut opens a project picker. Sumeet navigates the picker and chooses a project. Selecting it opens the relevant context for that project, which may include:

- the agent he has been working with;
- subagents in their own tmux windows;
- the ability for those tmux windows to be hidden or shown;
- relevant browser windows;
- notes associated with the project.

The initial interaction should therefore be project-first: choose the project once, then have its related working context made available together.

### Follow-up 1 — Restore behavior

The system should restore the project exactly as it was left. A predefined standard setup may be useful later, but it is not part of the initial behavior.

### Follow-up 2 — Meaning of exact state

“Exactly as it was left” includes all of the examples discussed:

- open applications and windows;
- their Hyprland positions;
- browser tabs;
- tmux windows and panes;
- running processes;
- agent conversations;
- unfinished prompts;
- project notes;
- other relevant working state.

### Follow-up 3 — Switching away

When Sumeet switches away from a project, its applications, processes, and agents should continue running in the background rather than being suspended or closed.

## Question 2 — Current pain

### Response

Several connected problems make the current workflow difficult:

#### Agent attention and progress

- It is hard to know when an agent has finished.
- There is no clear view of which agents need attention.
- There is no useful mental model of where each agent has got to in its work.

#### Scattered project context

- Returning to a project is difficult because its context is scattered.
- The browser, agent, and other relevant windows or tools may all be on different workspaces.
- Navigating between those pieces creates significant friction.

#### Tasks and notes

- Sumeet keeps a central to-do list or notes document and repeatedly jumps back and forth to it.
- The central list should remain high-level.
- Each project also needs its own more detailed to-do list so individual items can be explored without overloading the global list.

#### Worklogs and agent context

- The previous concept of worklogs has been lost.
- Worklogs were valuable as durable context for agents.

#### Projects and streams

- The earlier model of projects containing streams of work remains appealing.
- Some context or work should be shared at project level, while other context belongs to a particular stream.
- The exact boundary between project-level and stream-level information needs further discussion.

### Follow-up — Priority

These are not optional alternatives to prioritize away. Agent attention, project restoration, project-specific tasks, and worklogs/streams are all important parts of the intended system and should all be covered.

## Question 3 — What was valuable before?

### Response

#### Durable worklogs

The worklogs were especially valuable. They provided a durable record of what had been done, making it possible for both Sumeet and agents to pick the work back up with continuity.

#### Agent navigation

Keyboard shortcuts for moving between agents were useful. The stronger desired interaction is a single action with the mental model:

> Take me to the agent that needs me now.

The old implementation approached this but did not execute it as well as it could have.

## Question 4 — What should not return?

### Response

#### Herdr and rigid abstractions

Herdr felt like an additional, inflexible tool rather than a natural foundation. Its agent workspaces, sidebar, and related concepts imposed a rigid structure.

#### Unresolved terminal model

Tmux is viewed as the gold standard for terminal multiplexing because it remains fundamentally terminal-based. However, it is not yet clear that tmux should be the system’s organizing layer. The desired approach should stay as low-level as possible, and the right relationship between separate Kitty windows, tmux sessions, and project spaces remains an open question.

#### Hidden worklogs and weak schema

The worklog concept was good, but its data was hidden in difficult-to-reach directories. The old project/worklog schema also did not feel well designed.

#### Poor agent visibility

The relationship between the main agent and its subagents was difficult to see and understand. It was unclear what was happening across the agent hierarchy.

#### Too many competing surfaces

The old system exposed too many separate interaction surfaces, including Herdr plugins, Pi session pickers, and other controls. This increased complexity rather than producing one coherent project experience.

### Follow-up 1 — Meaning of low-level

The precise meaning of “low-level” is not settled. The stronger requirement is that the result should feel native to the operating system: one coherent experience, rather than a visibly messy collection of separate tools mixed together.

### Follow-up 2 — Meaning of operating-system native

The agent and project/workspace switcher should be led by the operating system and Hyprland. It must work globally without requiring Sumeet to already be inside a terminal. It should also be tool-independent rather than tied to one terminal, multiplexer, or agent implementation.

## Question 5 — New capability

### Response

The system should lower the overhead of switching between projects. AI makes it possible to produce and iterate very quickly, so the bottleneck becomes keeping many projects organized, understanding what is happening, and pointing the machine in the right direction.

The desired capability is to manage many projects well, switch context with very little effort, and lose as little awareness or working ability as possible during a switch.

There is also an unresolved tension around deep work. Switching away from a difficult project can destroy focus, but waiting for an agent to generate or complete work wastes time. The system should help use that waiting time without turning every agent completion into disruptive, uncontrolled context switching.

### Follow-up — Attention without interruption

The exact interaction is not yet clear, but the system should not forcibly interrupt focused work. It should provide a good notification or ambient indication when an agent needs help, allowing Sumeet to respond deliberately. Herdr’s agent-attention approach had value, but its implementation became too inflexible.

The useful parts of Herdr’s approach were:

- a persistent list of agents;
- visible agent status indicators;
- ordering by urgency;
- the ability to jump directly to the agent needing attention.

## Question 6 — Boundaries

### Response

The system’s boundaries are not yet clear. This should remain an open question rather than forcing an early division of responsibilities.

## Question 7 — Defining a project

### Response

Things belong to the same project because Sumeet defines them as belonging to that project. The system should not infer or automatically group unrelated existing things.

The intended workflow is contextual: enter a project, then things opened while inside that project remain associated with it. For example, a browser window opened while working in a project becomes part of that project because it was opened within that active project context.

### Follow-up — Global and home context

Some things should remain global, although the boundary between global and project-specific resources is not yet clear and may need to be redefined by the system.

There should also be a home workspace for quick, non-project activity such as checking email or briefly looking something up. A clear line is needed between home/global activity and project activity, but its exact position remains unresolved.

The current inclination is for the home workspace to behave like a project, potentially with its own remembered windows, notes, tasks, and state. This is tentative and needs deeper discussion before becoming a decision.

## Question 8 — Examples

### Response

A project could represent almost anything. The old worklogs under `~/matrix/pi-worklogs/` show examples across several categories:

- substantial software or business products: Elijah, Aether, Akhar, Reliq, Argus, and Arcane Codex;
- system and tooling work: Pi configuration, general system configuration, dotfiles, OpenCode migration, orchestration, Neovim, and worklog/plan plugins;
- experiments and focused technical efforts: Atomic Loop, forecasting benchmarks, stress testing, data annotation, and AI tooling;
- personal or general contexts: Home, CV/resume work, and syllabus planning;
- work in third-party repositories: AppFlowy, AFFiNE, and SiYuan;
- broad projects containing very different streams, including technical, operational, legal, creative, and business work.

The old registry also contains multiple distinct projects sharing the same filesystem root—for example Home and other user-level contexts—reinforcing that a project is intentionally defined and is not simply equivalent to a directory or Git repository.

## Question 9 — Non-projects

### Response

Something is a project only when Sumeet explicitly declares it to be one. The system should not automatically classify activity as a project. Undeclared activity remains outside the project model, regardless of what application, directory, or repository is involved.

## Question 10 — Project scale

### Response

The system should leave the meaning and scale of a project to the user. For Sumeet, projects would generally be high-level entities.

For example, Elijah could be one project containing its full body of context. It could contain streams for areas such as:

- the overall timeline and ongoing activity;
- legal work;
- software development.

A software stream could itself contain narrower streams, such as UI work, and those may potentially contain further substreams.

Creating a new stream of work and removing one should both be quick. Temporary or low-value streams should not leave rubbish and clutter behind indefinitely.

## Question 11 — Hierarchy

### Response

The relationship between streams, substreams, and deeper levels needs an explicitly designed data model rather than an assumed folder-like hierarchy.

Context should be layered:

- child streams can inherit relevant shared context;
- detailed stream context should not automatically pollute the parent project context;
- useful information can be deliberately promoted upward;
- relevant project context may need to flow downward;
- a project should retain a high-level awareness of what is happening across its streams without absorbing all of their detail.

The rules for promotion, inheritance, summarization, and isolation in both directions remain to be defined.

### Follow-up — Project and stream object types

It is not yet clear whether projects and streams should be the same recursive object or distinct concepts. This should be decided deliberately when the data model is designed rather than assumed during the interview.

## Question 12 — Filesystem scope

### Response

A project must not be forced to correspond to one directory. Different streams within the same project may require entirely different filesystem locations.

For example, Elijah’s timeline material may live in a separate folder from the application code. Both still belong to the larger Elijah project, while each stream may have its own relevant working directory or set of resources.

## Question 13 — Shared resources

### Response

A resource should not normally belong to multiple projects. Projects have their own space, and their project-specific repositories, directories, notes, windows, and other resources should belong to that space rather than being shared across project identities.

Global resources remain a separate unresolved category rather than belonging to several projects at once.

## Scope and identity

### Response

A code repository is only one part of a project; it does not define the project itself. If the repository moves, the project remains the same and its reference to that repository should be updated. The project’s other context and resources remain intact.

## Project lifecycle

### Archive

Archiving a project should only remove it from the normal project picker. It should not delete the project’s files, context, worklogs, tasks, or other retained state.

A separate permanent-delete workflow is unnecessary for now. Archiving is sufficient, and the system should not take ownership of deleting underlying files or repositories.

### Creation

The tentative minimum for creating a project is a name and a main directory. This is not yet a firm requirement because some projects may need a different starting shape.

## Durable context

### Response

The desired return view is not yet clear. A dedicated project `catchup` command may be useful later. Sumeet requested research into how other tools solve project resumption and catch-up before defining this behavior.

Research findings are recorded in [`RESEARCH-CATCHUP.md`](RESEARCH-CATCHUP.md).

### Catch-up direction

A one-screen project briefing is a good starting direction. It should bring together:

- items needing attention;
- a current project summary;
- active streams and their status;
- important changes since the project was last visited;
- blockers and next actions;
- direct links to resume the relevant agent, window, note, or task.

The briefing should remain concise, with underlying evidence available when more detail is needed.

## Worklogs

### Existing event model

The previous worklogs contain 5,893 readable events across 112 worklog/event files. Their main event types were:

- `start`
- `progress`
- `decision`
- `mistake`
- `stuck`
- `finish`
- `note`
- `next`
- occasional `verification`, `handoff`, `milestone`, and `change` events

Entries commonly recorded a summary plus structured context such as task, result, reason, lesson, blocker, next action, affected files, session, project, stream, and scope.

The old model also included a `projectImpact` marker and generated project-level entries with `source.kind: stream-rollup`, allowing selected stream activity to appear in the parent project log while retaining a link to the original stream entry.

This existing event vocabulary is the baseline to evaluate rather than inventing a replacement from scratch.

### Stream-to-project roll-up

“Worklog wrap-up” refers to the stream-to-project roll-up behavior: deciding which stream activity should become visible at project level. The old rules were not good enough and need to be redesigned.

The old behavior suffered from all of the identified problems:

- too much stream-level noise reached the project;
- important developments could still be missed;
- entries were duplicated awkwardly;
- promotion depended too heavily on an agent correctly judging `projectImpact`;
- it was unclear why some entries appeared in the project log.

The preferred outcome is automatic roll-up, ideally initiated by the agent writing the stream log. However, that agent may not have enough parent-project perspective to judge what truly affects the project. The correct mechanism—stream-agent promotion, parent-level review, periodic summarization, or another approach—remains open.

## Tasks and plans

### Response

The relationship between global, project, and stream task lists should remain simple for now. A sophisticated synchronization, promotion, or summarization model is not required at this stage.

## Desktop model

### Response

A project should normally correspond to one Hyprland workspace. That workspace may contain multiple windows, tabs, or switchable “screens” within the project.

A project screen means a full-workspace view of one part of the project. For example, a browser may occupy the whole working area, while a terminal occupies another full-area view, with a quick way to move between them without leaving the logical project.

Hyprland does not provide nested workspaces directly. Potential native primitives to evaluate later include full-width columns in the scrolling layout, tabbed window groups, or several real named workspaces grouped as one logical project by this system. No approach has been selected yet.

A promising interaction is **project-local semantic shortcuts**. For example, `Super+B` always means “go to the browser,” but resolves to the browser belonging to the currently active project. The shortcut remains stable while its target changes with project context. The same principle could potentially apply to other roles such as terminal, notes, or agents.

The existing Nix configuration confirms the current mental model: `Super+B` switches to the global named Hyprland workspace `browser`, then a helper ensures a Vivaldi window exists there. The desired evolution is a two-dimensional workspace model:

```text
active project -> role workspace
Elijah        -> browser
Elijah        -> terminal
Elijah        -> notes
Aether        -> browser
Aether        -> terminal
```

Thus `Super+B` should move to the browser workspace *inside the active project*, not merely launch or focus a browser window. Hyprland does not need native nested workspaces if the project system can group or resolve ordinary named workspaces as project-local role workspaces.

Selecting a project from the picker should return to the last role workspace used inside that project.

## Global interface

### Project picker

Each project row should remain concise. At a glance it should show:

- agents needing attention;
- the project’s current stream.

Additional task lists, history, and detailed status do not need to appear directly in the picker row.

## Terminals and processes

### Response

The terminal model is intentionally unresolved. It is not yet clear whether a project should use separate Kitty windows, a tmux session with windows and panes, a mixture, or simply preserve whatever arrangement the user creates.

## Agents

### Scope rather than hierarchy

A project does not require one persistent main agent, and a project-level agent does not need to control stream agents.

Each stream is an independent piece of work that inherits relevant project context and has its own understanding of which agent or agents are running within it. Agents are associated with project or stream scopes; they do not need to form a parent-agent/subagent command hierarchy that mirrors those scopes.

A stream may contain multiple agents working concurrently.

### Worktrees

Git worktrees may be needed when multiple streams operate concurrently against the same repository within one project.

When isolation is needed, one worktree per stream is the preferred model, with all agents in that stream sharing it. A worktree is optional rather than intrinsic to every stream. For example, an Elijah timeline stream operating in a separate non-code directory would not need one, while concurrent software streams changing the same repository may each need their own worktree.

Creating a worktree should be an explicit choice when the stream is created or configured, not an automatic decision made by the system.

## Persistence and portability

### Response

The system only needs to support one machine for now. Cross-machine synchronization and portability are out of scope. Local restart and recovery remain relevant, but there is no need to design shared project state across computers.

After reboot, projects should not all reopen automatically. A project is restored only when Sumeet chooses to open it.

Closing a project should remove its live workspace while preserving enough state to restore it later. This is distinct from merely switching away: switching leaves the project open and running in the background, whereas closing removes the workspace but retains its saved state.

Closing a project should also stop its agents and development processes. Reopening the project should reconstruct the saved environment rather than relying on those processes having remained alive.

## Ownership and tool independence

### Response

The project model must remain independent of specific tools. Replacing Kitty, Pi, Vivaldi, tmux, or another surface should require replacing that integration, not changing the identity or conceptual structure of the project.

## First useful version

### Response

The first iteration should be much smaller than the complete vision. Agent monitoring is not needed yet. The initial milestone should focus on delivering the system-wide project picker well; agent attention, worklog catch-up, streams, and richer integrations can follow in later iterations.

The project-picker iteration should support:

- listing active projects;
- creating a project;
- opening or switching to a project;
- closing a project while saving its state;
- archiving and restoring projects.
