#!/bin/sh
# Enforces L2-SEC-015: cryptographic hashing used for file verification is
# SHA-256 or stronger. Non-cryptographic checksums are permitted for
# torn-write framing only, never for file verification.
#
# Preventive rather than corrective. Integrity verification is deferred to v1.1
# with L1-SYS-003, so today there is no hashing here at all and this gate finds
# nothing -- exactly like `no-shell`, which guards a capability ADR-0011
# removed. The value is that the constraint is enforced from the moment the
# feature arrives rather than remembered afterwards, and v1.1 is precisely when
# someone reaches for the first hash function they recognise.
#
# MD5 and SHA-1 are both broken for collision resistance, which is the property
# that matters for "is this the file I moved". CRC32 is not a cryptographic
# hash at all and is listed because it is the one people reach for when they
# mean "checksum" and then quietly rely on for verification.
#
# Usage:  sh scripts/assert-strong-hash.sh
set -eu

cd "$(dirname "$0")/.."

# Word-boundary matched, so prose naming the hazard does not trip the gate --
# and comments are stripped first, because this rule is worth explaining.
banned='(^|[^_[:alnum:]])(MD5|md5|SHA1|sha1|SHA_1|CRC32|crc32|adler32)[_[:alnum:]]*[[:space:]]*\('

status=0
for f in $(find src include tests fuzz -name '*.cpp' -o -name '*.hpp' 2>/dev/null | sort); do
    hits=$(sed 's://.*::' "$f" | grep -nE "$banned" || true)
    if [ -n "$hits" ]; then
        echo "assert-strong-hash: $f uses a weak or non-cryptographic hash" >&2
        echo "$hits" | sed "s|^|  $f:|" >&2
        status=1
    fi
done

if [ "$status" -ne 0 ]; then
    echo "" >&2
    echo "L2-SEC-015: file verification requires SHA-256 or stronger. MD5 and" >&2
    echo "SHA-1 are broken for collision resistance, which is the property" >&2
    echo "'is this the file I moved' depends on. A non-cryptographic checksum" >&2
    echo "is acceptable for torn-write framing only -- if that is the use," >&2
    echo "allow-list it here deliberately and say which." >&2
    exit 1
fi

echo "strong-hash OK: no weak or non-cryptographic hash used for verification"
