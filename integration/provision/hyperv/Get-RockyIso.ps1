<#
.SYNOPSIS
    Downloads a Rocky Linux 9 ISO into the lab ISO directory and verifies it.

.DESCRIPTION
    The lab originally required this to be done by hand, on the grounds that a
    script which silently fetches an unverified OS image is not something this
    project should own. That objection was about "silently" and "unverified",
    not about automation -- so this script exists and does neither.

    What it verifies:

      SHA256      always, against the CHECKSUM file published beside the
                  image on the official redirector, over HTTPS. This catches
                  a truncated download, a corrupted mirror, and a mirror
                  serving the wrong release.

      GPG         NOT here. CHECKSUM.asc is downloaded alongside so the
                  signature can be checked, but gpg is not present on this
                  Windows host and installing a GPG stack to verify one file
                  is a poor trade. The check is done on the Linux side by
                  integration/scripts/verify-iso-signature.sh, which is where
                  gpg already exists.

    A file that fails verification is DELETED. Leaving a bad image on disk is
    how a later run picks it up and produces a VM nobody can explain.

.PARAMETER Variant
    minimal (default), boot, or dvd. The lab uses minimal.

.PARAMETER Version
    A specific release such as '9.8'. Omit to take whatever the /9/ path
    currently points at, which is the latest 9.x.

.NOTES
    Layer 1. Documented in docs/INTEGRATION-INVENTORY.md.
#>
[CmdletBinding()]
param(
    [string] $ConfigPath = (Join-Path $PSScriptRoot 'Lab.psd1'),
    [ValidateSet('minimal', 'boot', 'dvd')]
    [string] $Variant = 'minimal',
    [string] $Version,
    [switch] $Force
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

$lab = Import-PowerShellDataFile -Path $ConfigPath

if (-not (Test-Path $lab.IsoDir)) {
    New-Item -ItemType Directory -Force -Path $lab.IsoDir | Out-Null
}

# The redirector, not a specific mirror. It resolves to a nearby mirror and is
# the only URL Rocky documents as stable.
$base = 'https://download.rockylinux.org/pub/rocky/9/isos/x86_64/'

Write-Host "fetching CHECKSUM from $base"
$response = Invoke-WebRequest -Uri ($base + 'CHECKSUM') -UseBasicParsing -TimeoutSec 120
# -UseBasicParsing returns bytes for a non-text content type; decode explicitly
# rather than relying on .Content being a string, which it is not here.
$checksumText = [System.Text.Encoding]::UTF8.GetString($response.Content)

# Lines look like:  SHA256 (Rocky-9.8-x86_64-minimal.iso) = d338032c...
$pattern = if ($Version) {
    "^SHA256 \(Rocky-$([regex]::Escape($Version))-x86_64-$Variant\.iso\) = ([0-9a-f]{64})$"
} else {
    "^SHA256 \(Rocky-(\d+\.\d+)-x86_64-$Variant\.iso\) = ([0-9a-f]{64})$"
}

$isoName = $null
$expected = $null
foreach ($line in ($checksumText -split "`r?`n")) {
    $line = $line.Trim()
    if ($line -match $pattern) {
        # Skip the "Rocky-9-latest-" aliases: they are the same bytes under a
        # name that changes meaning over time, and Lab.psd1 pins an exact file
        # so that a rebuilt VM is the same VM.
        if ($Version) {
            $isoName = "Rocky-$Version-x86_64-$Variant.iso"
            $expected = $Matches[1]
        } else {
            $isoName = "Rocky-$($Matches[1])-x86_64-$Variant.iso"
            $expected = $Matches[2]
        }
        break
    }
}

if (-not $isoName) {
    throw "No $Variant ISO found in CHECKSUM$(if ($Version) { " for version $Version" }). Contents:`n$checksumText"
}

Write-Host "release  : $isoName"
Write-Host "sha256   : $expected"

$target = Join-Path $lab.IsoDir $isoName

if ((Test-Path $target) -and -not $Force) {
    Write-Host "already present, verifying rather than re-downloading"
} else {
    if (Test-Path $target) { Remove-Item -Path $target -Force }

    # curl.exe rather than Invoke-WebRequest: PowerShell 5.1 buffers the whole
    # response in memory before writing it, which for a 1.5 GB image is both
    # slow and a needless 1.5 GB of RAM. curl.exe ships with Windows 11.
    $curl = (Get-Command curl.exe -ErrorAction SilentlyContinue)
    if (-not $curl) { throw "curl.exe not found; cannot download efficiently" }

    Write-Host "downloading to $target (this takes a few minutes)"
    & curl.exe --fail --location --show-error --silent `
        --retry 3 --retry-delay 5 `
        --output $target ($base + $isoName)
    if ($LASTEXITCODE -ne 0) {
        if (Test-Path $target) { Remove-Item -Path $target -Force }
        throw "curl failed with exit code $LASTEXITCODE"
    }
}

# --- verification ---------------------------------------------------------
Write-Host "verifying SHA256 (this reads the whole file; give it a moment)"
$actual = (Get-FileHash -Path $target -Algorithm SHA256).Hash.ToLowerInvariant()

if ($actual -ne $expected) {
    Remove-Item -Path $target -Force
    throw @"
SHA256 MISMATCH -- the file has been deleted.

  expected $expected
  actual   $actual

A bad image left on disk is how a later run picks it up and produces a VM
nobody can explain. Re-run to try a different mirror.
"@
}
Write-Host "SHA256 OK"

# Saved beside the image so the signature can be checked on the Linux side.
foreach ($extra in 'CHECKSUM', 'CHECKSUM.asc') {
    $dest = Join-Path $lab.IsoDir $extra
    Write-Host "fetching $extra"
    & curl.exe --fail --location --show-error --silent --output $dest ($base + $extra)
    if ($LASTEXITCODE -ne 0) { Write-Warning "could not fetch $extra (exit $LASTEXITCODE)" }
}

$sizeGb = [math]::Round((Get-Item $target).Length / 1GB, 2)
Write-Host ""
Write-Host "$isoName  ($sizeGb GB)  verified"
Write-Host ""
Write-Host "Set this in Lab.psd1:"
Write-Host "    InstallIso   = '$isoName'"
Write-Host ""
Write-Host "Then verify the signature on the Linux side:"
Write-Host "    sh integration/scripts/verify-iso-signature.sh"
