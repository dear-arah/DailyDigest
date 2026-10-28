#!/bin/sh
# Usage: load-state.sh REMOTE DIR
# Clones the `state` branch into DIR. A branch that does not exist yet starts a fresh state.
# Any other failure (network, auth) aborts, so a hiccup is never mistaken for a first run.
set -u
remote="$1"
dir="$2"

git ls-remote --exit-code --heads "$remote" state >/dev/null 2>&1
code=$?

case "$code" in
  0) git clone --quiet --depth 1 --branch state "$remote" "$dir" ;;
  2) git init --quiet -b state "$dir" ;;
  *)
    echo "cannot read state branch from the remote (git exit $code); aborting" >&2
    exit 1
    ;;
esac
