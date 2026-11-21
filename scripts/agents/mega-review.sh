#!/bin/bash
# Start the Repository Mega Review Agent (Claude Fable) as a cloud child of the
# current Cloudroom thread. Run ONLY when the user explicitly asks for a mega
# review. The routine per-PR reviewer is thr_xnjapdndei and is resumed instead.
#
# Run it from the LOCAL coordinator thread (the canonical checkout), whose
# room-cli supports --parent-self/--project/--machine/--base-branch. Cloud
# sandboxes ship a reduced CLI; the script refuses there.
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
help=$(room-cli thread spawn --help 2>&1 || true)
for flag in --parent-self --project --machine --base-branch --prompt-file --reasoning-level; do
  case "$help" in
    *"$flag"*) ;;
    *) echo "mega-review: this room-cli lacks $flag; run from the local coordinator thread" >&2; exit 2 ;;
  esac
done
git fetch -q origin "$branch"
commit=$(git rev-parse --verify "FETCH_HEAD^{commit}")
prompt=$(mktemp "${TMPDIR:-/tmp}/mega-review-XXXXXX.md")
trap 'rm -f "$prompt"' EXIT
{
  cat docs/agents/MEGA-REVIEW-BRIEF.md
  printf '\n## This request\n\n'
  printf -- '- Branch: `%s`, commit `%s`. Review exactly this commit; the branch\n' "$branch" "$commit"
  printf -- '  may have moved since. Run `git fetch origin %s` if needed, then\n' "$branch"
  printf -- '  `git checkout --detach %s` and confirm `git rev-parse HEAD` prints it.\n' "$commit"
  printf -- '  If that commit is unavailable, report that and stop without reviewing.\n'
  printf -- '- Focus: %s\n' "$focus"
  printf -- '- Requested by the user on %s.\n' "$(date -u +%Y-%m-%d)"
} > "$prompt"
room-cli thread spawn --parent-self --project "$ROOM_PROJECT_ID" \
  --machine cloud --base-branch "$branch" \
  --provider claude-code --model "${MEGA_REVIEW_MODEL:-claude-fable-5-2}" \
  --reasoning-level "${MEGA_REVIEW_EFFORT:-max}" \
  --title "Repository Mega Review ($branch @ ${commit:0:7})" \
  --prompt-file "$prompt"
