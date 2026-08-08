#!/bin/sh
# Verifies the GPG signature on the Rocky CHECKSUM file.
#
# WHY THIS IS SEPARATE FROM THE DOWNLOAD. Get-RockyIso.ps1 verifies the ISO's
# SHA256 against the CHECKSUM published beside it. That proves the bytes are the
# bytes the CHECKSUM file describes -- it does NOT prove the CHECKSUM file came
# from Rocky. Anyone able to serve you both files can make them agree.
#
# The signature closes that, and it is checked here rather than on Windows
# because gpg already exists on the Linux side and installing a GPG stack on
# Windows to verify one file is a poor trade.
#
# WHAT THIS DOES NOT ESTABLISH BY ITSELF. The signing key is fetched over HTTPS
# from Rocky's own server. If that server is lying to you, it can lie about the
# key too -- so on its own this is trust-on-first-use, not verification. It
# becomes real verification once the fingerprint is checked ONCE against a
# source outside that channel (rockylinux.org publishes it; so do the release
# announcements) and pinned here.
#
# The pin lives in integration/provision/hyperv/rocky-gpg-fingerprint.txt. If
# that file is absent, this script prints the fingerprint and tells you to
# confirm it -- it does NOT invent one, because a wrong pinned fingerprint is
# worse than an unpinned check: it looks like verification and is not.
#
# Usage:  sh integration/scripts/verify-iso-signature.sh [iso-dir]
set -eu

ISO_DIR=${1:-/mnt/d/filemover-lab/iso}
PIN_FILE="$(dirname "$0")/../provision/hyperv/rocky-gpg-fingerprint.txt"
KEY_URL='https://dl.rockylinux.org/pub/rocky/RPM-GPG-KEY-Rocky-9'

if ! command -v gpg >/dev/null 2>&1; then
    echo "gpg is not installed. sudo apt-get install -y gnupg" >&2
    exit 2
fi

if [ ! -d "$ISO_DIR" ]; then
    echo "no such directory: $ISO_DIR" >&2
    echo "pass the ISO directory as the first argument if it is elsewhere" >&2
    exit 2
fi

CHECKSUM="$ISO_DIR/CHECKSUM"
SIGNATURE="$ISO_DIR/CHECKSUM.asc"

for f in "$CHECKSUM" "$SIGNATURE"; do
    if [ ! -f "$f" ]; then
        echo "missing $f -- run Get-RockyIso.ps1, which saves both" >&2
        exit 2
    fi
done

# A throwaway keyring. Importing into the user's own keyring would leave a
# distribution signing key trusted for everything else they ever verify.
GNUPGHOME=$(mktemp -d)
export GNUPGHOME
chmod 700 "$GNUPGHOME"
trap 'rm -rf "$GNUPGHOME"' EXIT INT TERM

echo "fetching the Rocky 9 signing key"
if ! curl -fsSL "$KEY_URL" -o "$GNUPGHOME/rocky.key"; then
    echo "could not fetch $KEY_URL" >&2
    exit 1
fi

gpg --quiet --import "$GNUPGHOME/rocky.key"

fingerprint=$(gpg --with-colons --fingerprint 2>/dev/null |
              awk -F: '/^fpr:/ { print $10; exit }')
if [ -z "$fingerprint" ]; then
    echo "could not read a fingerprint from the imported key" >&2
    exit 1
fi

echo "key fingerprint: $fingerprint"

if [ -f "$PIN_FILE" ]; then
    pinned=$(tr -d ' \n\r\t' < "$PIN_FILE" | tr 'a-f' 'A-F')
    got=$(printf '%s' "$fingerprint" | tr -d ' ' | tr 'a-f' 'A-F')
    if [ "$pinned" = "$got" ]; then
        echo "fingerprint matches the pin in $(basename "$PIN_FILE")"
    else
        echo "" >&2
        echo "FINGERPRINT MISMATCH" >&2
        echo "  pinned : $pinned" >&2
        echo "  fetched: $got" >&2
        echo "" >&2
        echo "Either the key rotated or you are being served a different key." >&2
        echo "Do not proceed until you know which." >&2
        exit 1
    fi
else
    echo ""
    echo "NOT PINNED. This is trust-on-first-use, not verification."
    echo ""
    echo "Confirm the fingerprint above against https://rockylinux.org/keys"
    echo "(and ideally a second source), then pin it:"
    echo ""
    echo "    echo '$fingerprint' > $PIN_FILE"
    echo ""
fi

echo "verifying the signature over CHECKSUM"
if gpg --quiet --verify "$SIGNATURE" "$CHECKSUM" 2>/tmp/gpgverify.err; then
    echo "SIGNATURE OK"
else
    # A clearsigned file is verified without a separate data argument; try that
    # before concluding the signature is bad.
    if gpg --quiet --verify "$SIGNATURE" 2>>/tmp/gpgverify.err; then
        echo "SIGNATURE OK (clearsigned)"
    else
        echo "SIGNATURE VERIFICATION FAILED" >&2
        sed 's/^/  /' /tmp/gpgverify.err >&2
        exit 1
    fi
fi

echo ""
echo "The CHECKSUM file is signed by the key above."
echo "Get-RockyIso.ps1 already checked the ISO's SHA256 against it."
