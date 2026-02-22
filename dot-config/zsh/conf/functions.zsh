nixtemp() {
  nix shell "nixpkgs#$1"
}

zplug-update() {
  local target_dir="${1:-$ZDOTDIR/conf/plugins}"
  for dir in "$target_dir"/*/; do
    (cd "$dir" && git pull)
  done
}

function y() {
	local tmp="$(mktemp -t "yazi-cwd.XXXXXX")" cwd
	yazi "$@" --cwd-file="$tmp"
	IFS= read -r -d '' cwd < "$tmp"
	[ -n "$cwd" ] && [ "$cwd" != "$PWD" ] && builtin cd -- "$cwd"
	rm -f -- "$tmp"
}

function restart() {
	echo -n "Are you sure you want to restart? [y/n]: "
	read selection
	if [[ $selection == y ]]; then
		echo "Restarting..."
		sudo shutdown -r now
	else
		echo "Abandoining"
	fi
}

function shutdown() {
	echo -n "Are you sure you want to shutdown? [y/n]: "
	read selection
	if [[ $selection == y ]]; then
		echo "Shutting down..."
		sudo shutdown -h now
	else
		echo "Abandoining"
	fi
}


# Function to pipe a command's help output to bat
function rd() {
    "$@" | bat --paging=always -l help
}

function jqp() {	
cd ~/codex/
  git add .
  git commit -m "$(date +'%Y-%m-%d %H:%M:%S')"
  git push
}

# Path completion for task-note starting from ~/codex/
_task-note() {
  if [[ $CURRENT -eq 3 ]]; then
    local actions=(add open show)
    _describe 'command actions' actions
  elif [[ $CURRENT -eq 4 ]]; then
    _path_files -W ~/codex/
  else
    _default
  fi
}
compdef _task-note task-note

function tunnel-status() {
  if launchctl list 2>/dev/null | grep -q "reverse-ssh-tunnel"; then
    local pid=$(launchctl list | grep "reverse-ssh-tunnel" | awk '{print $1}')
    echo "Reverse SSH tunnel is running (PID: $pid)"
  else
    echo "Reverse SSH tunnel is not running"
  fi
}

function tunnel-restart() {
  echo -n "Restart reverse SSH tunnel? [y/n]: "
  read selection
  if [[ $selection == y ]]; then
    launchctl unload ~/Library/LaunchAgents/org.nixos.reverse-ssh-tunnel.plist 2>/dev/null
    launchctl load ~/Library/LaunchAgents/org.nixos.reverse-ssh-tunnel.plist
    echo "Tunnel restarted"
  else
    echo "Aborted"
  fi
}

# Create a new Python project with modular environment setup
pyproj() {
  if [[ -z "$1" ]]; then
    echo "Usage: pyproj <project-name>"
    return 1
  fi
  
  local script_path="$ZDOTDIR/conf/scripts/pyproj"
  if [[ -f "$script_path" ]]; then
    "$script_path" "$1"
  else
    echo "Error: pyproj script not found at $script_path"
    return 1
  fi
}

# Tab completion for pyproj
_pyproj() {
  _description 'create new python project'
  _message 'project name'
}
compdef _pyproj pyproj

# ==================== Git Worktree Functions ====================

# gwt: Create a new worktree from main branch
# Usage: gwt <branch-name>
# Creates branch from main, creates worktree in ./<branch-name>/, pushes, and cd's into it
gwt() {
  if [[ -z "$1" ]]; then
    echo "Usage: gwt <branch-name>"
    return 1
  fi

  local branch_name="$1"
  local worktree_dir="./$branch_name"

  # Check if we're in a git repository
  if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    echo "Error: Not in a git repository"
    return 1
  fi

  # Check if we're in the main worktree (not a worktree itself)
  if [[ -f "$(git rev-parse --git-dir)/commondir" ]]; then
    echo "Error: gwt must be run from the main git repository, not from a worktree"
    return 1
  fi

  # Check if branch already exists locally
  if git branch --list "$branch_name" | grep -q "^[*[:space:]]*$branch_name$"; then
    echo "Error: Branch '$branch_name' already exists locally"
    return 1
  fi

  # Check if branch is already checked out in another worktree
  if git worktree list | grep -q "$branch_name"; then
    echo "Error: Branch '$branch_name' is already checked out in another worktree"
    echo "Use 'git worktree list' to see active worktrees"
    return 1
  fi

  # Check if worktree directory already exists
  if [[ -d "$worktree_dir" ]]; then
    echo "Error: Worktree directory '$worktree_dir' already exists"
    return 1
  fi

  # Fetch latest from remote
  echo "Fetching from remote..."
  git fetch origin || return 1

  # Check if main branch exists
  if ! git show-ref --verify --quiet refs/remotes/origin/main && \
     ! git show-ref --verify --quiet refs/heads/main; then
    echo "Error: 'main' branch not found"
    return 1
  fi

  # Determine the best reference for main (local or remote)
  local main_ref="main"
  if git show-ref --verify --quiet refs/remotes/origin/main; then
    main_ref="origin/main"
  fi

  echo "Creating branch '$branch_name' from '$main_ref' and worktree at '$worktree_dir'..."
  # Use git worktree add -b to create branch and worktree in one step (does not switch current branch)
  git worktree add -b "$branch_name" "$worktree_dir" "$main_ref" || return 1

  echo "Pushing branch to remote..."
  (cd "$worktree_dir" && git push -u origin "$branch_name") || return 1

  echo "Switching to worktree..."
  cd "$worktree_dir" || return 1
}

# gwm: Merge current worktree branch back into main
# Usage: Run from inside a worktree created with gwt
gwm() {
  # Check if we're in a git repository
  if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    echo "Error: Not in a git repository"
    return 1
  fi

  # Check if we're in a worktree (not the main repo)
  if [[ ! -f "$(git rev-parse --git-dir)/commondir" ]]; then
    echo "Error: gwm must be run from inside a worktree (created with gwt)"
    return 1
  fi

  # Get current branch name
  local feature_branch
  feature_branch=$(git branch --show-current)
  if [[ -z "$feature_branch" ]]; then
    echo "Error: Could not determine current branch"
    return 1
  fi

  echo "Current branch: $feature_branch"

  # Find the main git directory
  local git_common_dir
  git_common_dir=$(git rev-parse --git-dir)/..
  if [[ -f "$(git rev-parse --git-dir)/commondir" ]]; then
    git_common_dir=$(cat "$(git rev-parse --git-dir)/commondir")
  fi

  echo "Moving to main repository at: $git_common_dir"
  cd "$git_common_dir" || return 1

  # Make sure we're on main branch
  echo "Switching to main branch..."
  git checkout main || return 1

  # Pull latest from remote
  echo "Pulling latest main from remote..."
  git pull origin main || return 1

  # Merge the feature branch
  echo "Merging '$feature_branch' into main..."
  git merge "$feature_branch" || return 1

  echo "Merge complete! You are now on main branch in the main repository."
  echo "Run 'gwc' from the worktree directory to clean up once you're ready."
}

# gwc: Clean up a merged worktree
# Usage: Run from inside the worktree directory (just merged with gwm)
# Deletes worktree and local branch (keeps remote branch)
gwc() {
  # Check if we're in a git repository
  if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    echo "Error: Not in a git repository"
    return 1
  fi

  # Check if we're in a worktree (not the main repo)
  if [[ ! -f "$(git rev-parse --git-dir)/commondir" ]]; then
    echo "Error: gwc must be run from inside a worktree (created with gwt)"
    return 1
  fi

  # Get current branch name
  local feature_branch
  feature_branch=$(git branch --show-current)
  if [[ -z "$feature_branch" ]]; then
    echo "Error: Could not determine current branch"
    return 1
  fi

  # Get the worktree path
  local worktree_path
  worktree_path=$(git rev-parse --show-toplevel)
  if [[ -z "$worktree_path" ]]; then
    echo "Error: Could not determine worktree path"
    return 1
  fi

  echo "Cleaning up worktree for branch: $feature_branch"
  echo "Worktree path: $worktree_path"

  # Find the main git directory
  local git_common_dir
  git_common_dir=$(git rev-parse --git-dir)/..
  if [[ -f "$(git rev-parse --git-dir)/commondir" ]]; then
    git_common_dir=$(cat "$(git rev-parse --git-dir)/commondir")
  fi

  echo "Moving to main repository..."
  cd "$git_common_dir" || return 1

  # Check if the worktree directory still exists
  if [[ ! -d "$worktree_path" ]]; then
    echo "Warning: Worktree directory '$worktree_path' does not exist (already removed?)"
  fi

  # Verify branch is fully merged into main
  echo "Checking if branch '$feature_branch' is fully merged into main..."
  if ! git branch --merged main | grep -q "^[*[:space:]]*$feature_branch$"; then
    echo "Error: Branch '$feature_branch' is NOT fully merged into main."
    echo "Aborting cleanup. Please merge first using 'gwm' from the worktree."
    return 1
  fi

  # Check if worktree is clean (no uncommitted changes)
  echo "Checking if worktree is clean..."
  if [[ -n "$(git -C "$worktree_path" status --porcelain 2>/dev/null)" ]]; then
    echo "Error: Worktree at '$worktree_path' has uncommitted changes."
    echo "Aborting cleanup. Please commit or stash your changes."
    return 1
  fi

  # Remove worktree using git worktree remove (safe)
  if [[ -d "$worktree_path" ]]; then
    echo "Removing worktree with git worktree remove..."
    git worktree remove "$worktree_path" || return 1
  fi

  # Delete local branch
  echo "Deleting local branch '$feature_branch'..."
  git branch -D "$feature_branch" || return 1

  # Prune worktree references
  echo "Pruning worktree references..."
  git worktree prune || return 1

  # Double-check directory removal
  if [[ -d "$worktree_path" ]]; then
    echo "Force removing leftover directory..."
    rm -rf "$worktree_path"
  fi

  echo "Cleanup complete! Branch and worktree removed."
  echo "Remote branch is still available."
}
