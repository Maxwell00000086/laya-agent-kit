param(
    [ValidateSet('codex', 'claude-code', 'cursor', 'generic')]
    [string[]]$Client = @('codex'),
    [string]$Python,
    [switch]$Offline,
    [switch]$DryRun,
    [switch]$Replace
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$pythonArguments = @()
if (-not $Python) {
    $localPython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
    if (Test-Path -LiteralPath $localPython) {
        $Python = $localPython
    } elseif (Get-Command py.exe -ErrorAction SilentlyContinue) {
        $Python = (Get-Command py.exe).Source
        $pythonArguments = @('-3')
    } else {
        $candidate = Get-Command python.exe -ErrorAction SilentlyContinue | Where-Object { $_.Source -notlike '*\WindowsApps\*' } | Select-Object -First 1
        if (-not $candidate) {
            throw 'Install 64-bit Python 3.12 first, or provide -Python with its executable path.'
        }
        $Python = $candidate.Source
    }
}
$installArguments = @('-X', 'utf8', (Join-Path $PSScriptRoot 'install.py'))
foreach ($clientName in $Client) {
    $installArguments += @('--client', $clientName)
}
if ($Offline) { $installArguments += '--offline' }
if ($DryRun) { $installArguments += '--dry-run' }
if ($Replace) { $installArguments += '--replace' }
& $Python @pythonArguments @installArguments
if ($LASTEXITCODE -ne 0) { throw "Laya installation failed with exit code $LASTEXITCODE" }
