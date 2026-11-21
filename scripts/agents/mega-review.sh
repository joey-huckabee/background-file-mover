#!/bin/bash
# Start the Repository Mega Review Agent (Claude Fable) as a cloud child of the
# current Cloudroom thread. Run ONLY when the user explicitly asks for a mega
# review. The routine per-PR reviewer is thr_xnjapdndei and is resumed instead.
#
# Usage: scripts/agents/mega-review.sh <pushed-branch> [focus text...]
#   MEGA_REVIEW_MODEL   default claude-fable-5-2
#   MEGA_REVIEW_EFFORT  default max (low|medium|high|xhigh|max)
set -euo pipefail
cd "$(dirname "$0")/../.."
branch=${1:?usage: mega-review.sh <pushed-branch> [focus text...]}
shift
focus=${*:-"Whole repository; no specific focus."}
: "${ROOM_PROJECT_ID:?ROOM_PROJECT_ID is not set (run from a Cloudroom thread)}"
git fetch -q origin "$branch"
commit=$(git rev-parse "origin/$branch")
prompt=$(mktemp "${TMPDIR:-/tmp}/mega-review-XXXXXX.md")
trap 'rm -f "$prompt"' EXIT
{
  cat docs/agents/MEGA-REVIEW-BRIEF.md
  printf '\n## This request\n\n'
  printf -- '- Branch: `%s`, commit `%s` (review exactly this commit).\n' "$branch" "$commit"
  printf -- '- Focus: %s\n' "$focus"
  printf -- '- Requested by the user on %s.\n' "$(date -u +%Y-%m-%d)"
} > "$prompt"
room-cli thread spawn --parent-self --project "$ROOM_PROJECT_ID" \
  --machine cloud --base-branch "$branch" \
  --provider claude-code --model "${MEGA_REVIEW_MODEL:-claude-fable-5-2}" \
  --reasoning-level "${MEGA_REVIEW_EFFORT:-max}" \
  --title "Repository Mega Review ($branch @ ${commit:0:7})" \
  --prompt-file "$prompt"
