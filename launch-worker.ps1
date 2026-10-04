#requires -Version 5.1
param([Parameter(Mandatory)][string]$Payload)
$ErrorActionPreference = 'Stop'
$request = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String($Payload)) | ConvertFrom-Json
try {
    if ([DateTime]::UtcNow -gt [DateTime]::Parse($request.deadline).ToUniversalTime()) { throw 'Launch request expired.' }
    $exe = Get-Item -LiteralPath $request.executable
    if ($exe.Name -notin @('ChatGPT.exe','Codex.exe') -or -not (Test-Path -LiteralPath (Join-Path $exe.DirectoryName 'icudtl.dat'))) { throw 'Not a Desktop executable.' }
    $info = New-Object Diagnostics.ProcessStartInfo
    $info.FileName = $exe.FullName
    $info.WorkingDirectory = $exe.DirectoryName
    $info.UseShellExecute = $false
    foreach ($key in @('HTTP_PROXY','HTTPS_PROXY','ALL_PROXY','http_proxy','https_proxy','all_proxy')) {
        $info.EnvironmentVariables[$key] = 'http://127.0.0.1:8901'
    }
    $info.EnvironmentVariables['NO_PROXY'] = 'localhost,127.0.0.1,::1'
    $info.EnvironmentVariables['CODEX_CA_CERTIFICATE'] = [string]$request.certificate
    if ($request.timezone) { $info.EnvironmentVariables['TZ'] = [string]$request.timezone }
    [void]$info.EnvironmentVariables.Remove('ELECTRON_RUN_AS_NODE')
    $child = [Diagnostics.Process]::Start($info)
    if ($child.WaitForExit(2000)) { throw 'Desktop exited before startup could be confirmed.' }
    $result = @{started=$true; pid=$child.Id; message='Desktop launched with process-only capture settings. Waiting for a real response to verify.'}
} catch {
    $result = @{started=$false; message=$_.Exception.Message}
}
$tempPath = [string]$request.result + '.tmp'
$result | ConvertTo-Json | Set-Content -LiteralPath $tempPath -Encoding UTF8
Move-Item -LiteralPath $tempPath -Destination $request.result -Force
