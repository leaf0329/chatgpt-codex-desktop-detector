#requires -Version 5.1
[CmdletBinding()]
param([switch]$SkipDependencies)
$ErrorActionPreference = 'Stop'
$python = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not $SkipDependencies) {
    if (-not (Test-Path -LiteralPath $python)) {
        & python -m venv (Join-Path $PSScriptRoot '.venv')
        if ($LASTEXITCODE -ne 0) { throw 'Python 3.11+ is required.' }
    }
    & $python -m pip install -r (Join-Path $PSScriptRoot 'requirements-monitor.txt')
    if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed.' }
}
$pythonWindow = Join-Path $PSScriptRoot '.venv\Scripts\pythonw.exe'
if (-not (Test-Path -LiteralPath $pythonWindow)) { throw 'Monitor runtime missing.' }
$shell = New-Object -ComObject WScript.Shell
$locations = @([Environment]::GetFolderPath('Desktop'),
    (Join-Path ([Environment]::GetFolderPath('StartMenu')) 'Programs'))
foreach ($directory in $locations) {
    $link = $shell.CreateShortcut((Join-Path $directory 'Codex Desktop - Model Monitor.lnk'))
    $link.TargetPath = $pythonWindow
    $link.Arguments = '"' + (Join-Path $PSScriptRoot 'monitor.py') + '" --launch'
    $link.WorkingDirectory = $PSScriptRoot
    $link.Description = 'Launch Codex Desktop with a resident request/response model monitor.'
    $package = Get-AppxPackage -Name OpenAI.Codex | Select-Object -First 1
    if ($package) {
        $icon = Join-Path $package.InstallLocation 'app\ChatGPT.exe'
        if (Test-Path -LiteralPath $icon) { $link.IconLocation = $icon + ',0' }
    }
    $link.Save()
    Write-Host (Join-Path $directory 'Codex Desktop - Model Monitor.lnk')
}
Write-Host 'Installed. Fully exit Codex once, then use the Model Monitor shortcut. No system proxy or certificate store was changed.'
