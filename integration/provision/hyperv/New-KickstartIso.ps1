<#
.SYNOPSIS
    Builds the OEMDRV kickstart ISO, generating the lab SSH key if absent.

.DESCRIPTION
    Anaconda scans removable media for a volume labelled OEMDRV and loads
    ks.cfg from it automatically. That is what makes the install unattended
    without editing kernel boot parameters through a console.

    The ISO is built with IMAPI2FS, the COM filesystem-image writer built into
    Windows. Deliberately no genisoimage, xorriso, oscdimg or ADK: this is the
    only step that needs an ISO writer, and adding a toolchain dependency to
    the host for one 300 KB image is a poor trade -- particularly on a machine
    whose C: drive has no room for an SDK.

    Idempotent. Re-running regenerates the ISO from the current kickstart and
    the existing key; it does not replace a key that already exists, because
    doing so would silently lock you out of a VM built from the previous one.

.NOTES
    Layer 1. Documented per item in docs/INTEGRATION-INVENTORY.md.
#>
[CmdletBinding()]
param(
    [string] $ConfigPath = (Join-Path $PSScriptRoot 'Lab.psd1')
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$lab = Import-PowerShellDataFile -Path $ConfigPath

foreach ($dir in @($lab.LabRoot, $lab.IsoDir, $lab.KeyDir)) {
    if (-not (Test-Path $dir)) {
        Write-Host "creating $dir"
        New-Item -ItemType Directory -Force -Path $dir | Out-Null
    }
}

# --- the lab SSH key ------------------------------------------------------
$keyPath = Join-Path $lab.KeyDir $lab.SshKeyName
$pubPath = "$keyPath.pub"

if (-not (Test-Path $keyPath)) {
    Write-Host "generating lab SSH key at $keyPath"
    # ed25519: small, fast, and supported by every RHEL 9 sshd. -N '' because
    # this key exists to let an unattended playbook in; a passphrase it would
    # have to be given non-interactively is a passphrase that protects nothing.
    & ssh-keygen.exe -t ed25519 -f $keyPath -N '""' -C 'file-mover integration lab' | Out-Null
    if (-not (Test-Path $keyPath)) {
        throw "ssh-keygen did not produce $keyPath. Is OpenSSH client installed? (Add-WindowsCapability -Online -Name OpenSSH.Client~~~~0.0.1.0)"
    }
} else {
    Write-Host "reusing existing lab SSH key at $keyPath"
}

$publicKey = (Get-Content -Path $pubPath -Raw).Trim()
if ([string]::IsNullOrWhiteSpace($publicKey)) {
    throw "public key $pubPath is empty"
}

# --- render the kickstart -------------------------------------------------
$ksSource = Join-Path $PSScriptRoot 'kickstart\rocky9-lab.ks'
if (-not (Test-Path $ksSource)) { throw "kickstart not found: $ksSource" }

$ksText = Get-Content -Path $ksSource -Raw
if ($ksText -notmatch '@KEY@') {
    throw "kickstart has no @KEY@ placeholder; the VM would be built with no way in"
}
$ksText = $ksText.Replace('@KEY@', $publicKey)

$staging = Join-Path $env:TEMP ("fm-ks-" + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Force -Path $staging | Out-Null
try {
    # LF line endings. Anaconda tolerates CRLF in most places and not all of
    # them, and a kickstart that fails to parse leaves the installer sitting at
    # an interactive prompt on a VM with no console attached -- which presents
    # as "the install hung".
    $ksOut = Join-Path $staging 'ks.cfg'
    [System.IO.File]::WriteAllText($ksOut, ($ksText -replace "`r`n", "`n"), [System.Text.UTF8Encoding]::new($false))

    # --- burn the image ---------------------------------------------------
    $isoPath = Join-Path $lab.IsoDir $lab.KickstartIso
    if (Test-Path $isoPath) { Remove-Item -Path $isoPath -Force }

    $fsi = New-Object -ComObject IMAPI2FS.MsftFileSystemImage
    # Joliet + ISO9660. UDF is not used: Anaconda's OEMDRV scan reads the
    # volume label, and ISO9660 is the format every installer agrees on.
    $fsi.FileSystemsToCreate = 3
    $fsi.VolumeName = 'OEMDRV'
    $fsi.Root.AddTree($staging, $false)

    $result = $fsi.CreateResultImage()

    # Write the image to disk from C#, not from PowerShell.
    #
    # IFileSystemImageResult.ImageStream is an IStream. PowerShell wraps COM
    # objects in an adapter that does not carry the interface's type
    # information, so `[...ComTypes.IStream] $stream` fails with "Cannot convert
    # the System.__ComObject value ... to type IStream" -- the cast has nothing
    # to work from. Inside C# the same object is an ordinary RCW and `as
    # IStream` succeeds, which is why every working IMAPI2FS recipe goes through
    # Add-Type. No /unsafe here: the byte count IStream.Read wants as an IntPtr
    # is served just as well by AllocHGlobal as by a pointer to a local.
    if (-not ('FileMover.IsoWriter' -as [type])) {
        Add-Type -TypeDefinition @'
namespace FileMover {
    public static class IsoWriter {
        public static void Write(string path, object imageStream, int blockSize, int totalBlocks) {
            var stream = imageStream as System.Runtime.InteropServices.ComTypes.IStream;
            if (stream == null) {
                throw new System.ArgumentException("the object supplied is not an IStream");
            }
            System.IntPtr read = System.Runtime.InteropServices.Marshal.AllocHGlobal(4);
            try {
                byte[] buffer = new byte[blockSize];
                using (var file = System.IO.File.Create(path)) {
                    while (totalBlocks-- > 0) {
                        stream.Read(buffer, blockSize, read);
                        int count = System.Runtime.InteropServices.Marshal.ReadInt32(read);
                        if (count <= 0) { break; }
                        file.Write(buffer, 0, count);
                    }
                    file.Flush();
                }
            } finally {
                System.Runtime.InteropServices.Marshal.FreeHGlobal(read);
            }
        }
    }
}
'@
    }

    [FileMover.IsoWriter]::Write($isoPath, $result.ImageStream, $result.BlockSize, $result.TotalBlocks)

    $size = (Get-Item $isoPath).Length
    if ($size -lt 1KB) { throw "produced ISO is $size bytes; something went wrong" }
    Write-Host ("wrote {0} ({1:N0} bytes, volume label OEMDRV)" -f $isoPath, $size)
    Write-Host "the private key the playbook will use is $keyPath"
} finally {
    Remove-Item -Path $staging -Recurse -Force -ErrorAction SilentlyContinue
}
