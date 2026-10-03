#requires -Version 5.1
$ErrorActionPreference = 'Stop'
$resultPath = Join-Path $PSScriptRoot '.local\launch-result.json'
try {
    $package = Get-AppxPackage -Name OpenAI.Codex | Select-Object -First 1
    if (-not $package) { throw 'OpenAI.Codex package not found.' }
    [xml]$manifest = Get-Content -LiteralPath (Join-Path $package.InstallLocation 'AppxManifest.xml') -Raw
    $app = @($manifest.SelectNodes("//*[local-name()='Application']") | Where-Object { $_.GetAttribute('Executable') -match '(ChatGPT|Codex)\.exe$' })
    if ($app.Count -ne 1) { throw 'Desktop entry point is ambiguous.' }
    $executable = Join-Path $package.InstallLocation $app[0].GetAttribute('Executable')
    $running = @(Get-Process ChatGPT,Codex -ErrorAction SilentlyContinue | Where-Object { $_.Path -eq $executable })
    if ($running.Count) {
        @{started=$false; message='Codex is already running. Save work and fully exit it, then click Start Codex. The current process was not changed.'} | ConvertTo-Json | Set-Content -LiteralPath $resultPath -Encoding UTF8
        exit 0
    }
    $certificate = Join-Path $PSScriptRoot '.local\codex-ca-bundle.pem'
    if (-not (Test-Path -LiteralPath $certificate)) { throw 'Monitor certificate bundle is missing.' }
    $worker = Join-Path $PSScriptRoot 'launch-worker.ps1'
    $payload = @{executable=$executable; certificate=$certificate; result=$resultPath; deadline=[DateTime]::UtcNow.AddSeconds(30).ToString('o')}
    $settingsPath = Join-Path $PSScriptRoot '.local\launch-settings.json'
    if (Test-Path -LiteralPath $settingsPath) {
        $settings = Get-Content -LiteralPath $settingsPath -Raw | ConvertFrom-Json
        if ($settings.timezone) { $payload.timezone = [string]$settings.timezone }
    }
    $encoded = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes(($payload | ConvertTo-Json -Compress)))
    $workerArgs = '-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "' + $worker + '" -Payload ' + $encoded
    Invoke-CommandInDesktopPackage -PackageFamilyName $package.PackageFamilyName -AppId $app[0].GetAttribute('Id') -Command "$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe" -Args $workerArgs -PreventBreakaway | Out-Null
    $watch = [Diagnostics.Stopwatch]::StartNew()
    while (-not (Test-Path -LiteralPath $resultPath) -and $watch.Elapsed.TotalSeconds -lt 35) { Start-Sleep -Milliseconds 200 }
    if (-not (Test-Path -LiteralPath $resultPath)) { throw 'No package launch result; do not repeatedly launch.' }
} catch {
    @{started=$false; message=$_.Exception.Message} | ConvertTo-Json | Set-Content -LiteralPath $resultPath -Encoding UTF8
    exit 1
}
