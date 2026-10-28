#!/bin/sh
# Usage: save-state.sh REMOTE DIR
# Publishes the contents of DIR as the single commit on the `state` branch, only when something changed.
set -eu
remote="$1"
dir="$2"

cd "$dir"
git add -A
if [ -z "$(git status --porcelain)" ]; then
  echo "state unchanged"
  exit 0
fi

git checkout --quiet --orphan snapshot
git add -A
git -c user.name="github-actions[bot]" \
    -c user.email="41898282+github-actions[bot]@users.noreply.github.com" \
    commit --quiet -m "chore: update state"
git push --quiet --force "$remote" snapshot:state
