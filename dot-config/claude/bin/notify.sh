#!/usr/bin/env bash
set -u

NOTIFIER="$HOME/.config/claude/bin/terminal-notifier.app/Contents/MacOS/terminal-notifier"

input=$(cat)
cwd=$(printf '%s' "$input"   | jq -r '.cwd // empty')
msg=$(printf '%s' "$input"   | jq -r '.message // empty')
event=$(printf '%s' "$input" | jq -r '.hook_event_name // empty')
session=$(printf '%s' "$input" | jq -r '.session_id // "claude"')

project=$(basename "${cwd:-Claude}")
title="Claude: ${project}"
[ -z "$msg" ] && msg="Done"
[ "$event" = "Stop" ] && msg="Done"

# Per-session group so a new notif replaces the previous one for the same session.
"$NOTIFIER" -title "$title" -message "$msg" -sound Glass -group "claude-${session}"
