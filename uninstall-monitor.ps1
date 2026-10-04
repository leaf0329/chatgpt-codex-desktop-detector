#requires -Version 5.1
$ErrorActionPreference = 'Stop'
$shell = New-Object -ComObject WScript.Shell
$expected = Join-Path $PSScriptRoot '.venv\Scripts\pythonw.exe'
foreach ($directory in @([Environment]::GetFolderPath('Desktop'),
    (Join-Path ([Environment]::GetFolderPath('StartMenu')) 'Programs'))) {
    $path = Join-Path $directory 'Codex Desktop - Model Monitor.lnk'
    if (Test-Path -LiteralPath $path) {
        $link = $shell.CreateShortcut($path)
        if ($link.TargetPath -eq $expected -and $link.Arguments -like ('*' + $PSScriptRoot + '*')) {
            Remove-Item -LiteralPath $path
            Write-Host "Removed $path"
        }
    }
}
Write-Host 'Exit the monitor and restart Codex from its ordinary entry. Local metadata and CA files are preserved under .local.'
