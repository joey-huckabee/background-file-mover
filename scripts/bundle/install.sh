#!/bin/sh
# Install a new, versioned directory only. Never modify configuration/state/unit.
set -eu
test "$#" -eq 1 || { echo "Usage: $0 /absolute/new/install-directory" >&2; exit 2; }
prefix=$1
case "$prefix" in
    /*) ;;
    *) echo 'Installation path must be absolute' >&2; exit 2;;
esac
case "$prefix" in
    *[!A-Za-z0-9_./-]*|*/../*|*/./*|*//*|*/|*/..|*/.) echo 'Use a canonical path without spaces, dot components or shell characters' >&2; exit 2;;
esac
test ! -e "$prefix" && test ! -L "$prefix" || { echo 'Installation destination already exists; it will not be replaced' >&2; exit 1; }
parent=$(dirname -- "$prefix")
test "$parent" = "$(CDPATH= cd -- "$parent" && pwd -P)" || { echo 'Installation parent must exist without symlink aliases' >&2; exit 1; }
root=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd -P)
sh "$root/verify.sh"
umask 022
stage=$(mktemp -d "$parent/.file-mover-install.XXXXXX")
trap 'if test -n "$stage"; then rm -rf -- "$stage"; fi' EXIT
trap 'exit 1' HUP INT TERM
cp -R "$root/." "$stage/"
chmod 0755 "$stage"
sh "$stage/verify.sh"
mv -T --no-clobber -- "$stage" "$prefix"
test ! -d "$stage" || { echo 'Destination appeared during installation; nothing was replaced' >&2; exit 1; }
stage=
echo "Installed: $prefix"
echo 'No service was started/enabled; no configuration, enrollment or state was created/changed.'
