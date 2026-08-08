<#
.SYNOPSIS
    Parses every layer-1 PowerShell file and reports syntax errors.

.DESCRIPTION
    Uses the parser built into PowerShell itself, so this needs nothing
    installed -- notably not PSScriptAnalyzer, which is a module download on a
    machine whose C: drive has no room for one.

    This is a SYNTAX check and nothing more. It proves the scripts parse; it
    says nothing about whether they create a working VM. The only thing that
    answers that is running them, which needs Hyper-V access this account did
    not have when they were written.

.NOTES
    Layer 1. Run from anywhere: paths are resolved relative to this file.
#>
[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$root = Split-Path -Parent $PSScriptRoot
$files = @(Get-ChildItem -Path $root -Recurse -Include '*.ps1','*.psd1' -File)

if ($files.Count -eq 0) {
    Write-Error "no PowerShell files found under $root"
    exit 1
}

$failed = 0
foreach ($file in $files) {
    $errors = $null
    $null = [System.Management.Automation.Language.Parser]::ParseFile(
        $file.FullName, [ref] $null, [ref] $errors)

    $rel = $file.FullName.Substring($root.Length + 1)
    if ($errors -and $errors.Count -gt 0) {
        Write-Host ("  FAIL  {0}" -f $rel)
        foreach ($e in $errors) {
            Write-Host ("        line {0}: {1}" -f $e.Extent.StartLineNumber, $e.Message)
        }
        $failed++
    } else {
        Write-Host ("  ok    {0}" -f $rel)
    }
}

# The data file must also LOAD, not merely parse -- Import-PowerShellDataFile
# refuses anything with executable content, which is the property that makes it
# safe to read, and a psd1 that parses but will not import fails at the worst
# moment: inside New-TestLab.ps1, after the ISO checks have already passed.
$labConfig = Join-Path $root 'provision\hyperv\Lab.psd1'
if (Test-Path $labConfig) {
    try {
        $lab = Import-PowerShellDataFile -Path $labConfig
        $required = @('LabRoot','IsoDir','VhdDir','VmDir','KeyDir','InstallIso',
                      'KickstartIso','VmName','CpuCount','MemoryMB','DiskGB',
                      'SwitchName','AdminUser','SshKeyName')
        $missing = @($required | Where-Object { -not $lab.ContainsKey($_) })
        if ($missing.Count -gt 0) {
            Write-Host ("  FAIL  Lab.psd1 is missing keys: {0}" -f ($missing -join ', '))
            $failed++
        } else {
            Write-Host "  ok    Lab.psd1 imports and has every required key"
        }
    } catch {
        Write-Host ("  FAIL  Lab.psd1 does not import: {0}" -f $_.Exception.Message)
        $failed++
    }
}

Write-Host ""
if ($failed -gt 0) {
    Write-Host "PowerShell syntax: $failed file(s) failed"
    exit 1
}
Write-Host "PowerShell syntax: all files parse"
