# Install Desktop Agent to start automatically at the current user's Windows logon.
$ErrorActionPreference = "Stop"
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$TaskName = "DesktopAgent-Alexa"
$Pythonw = Join-Path $ProjectRoot ".venv\Scripts\pythonw.exe"
if (-not (Test-Path $Pythonw)) {
    $Python = (Get-Command python.exe -ErrorAction SilentlyContinue).Source
    if (-not $Python) {
        throw "Python was not found. Activate your environment and install the project first."
    }
    $Pythonw = Join-Path (Split-Path $Python -Parent) "pythonw.exe"
}
if (-not (Test-Path $Pythonw)) {
    throw "pythonw.exe was not found. Create .venv and install Desktop Agent before enabling startup."
}
$Action = New-ScheduledTaskAction -Execute $Pythonw -Argument "-m desktop_agent.startup" -WorkingDirectory $ProjectRoot
$Trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$Settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1) -ExecutionTimeLimit ([TimeSpan]::Zero) -MultipleInstances IgnoreNew
$Principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited
Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Trigger -Settings $Settings -Principal $Principal -Description "Starts the local Desktop Agent and Alexa wake-word listener at user logon." -Force | Out-Null
Start-ScheduledTask -TaskName $TaskName
Write-Host "Desktop Agent startup task installed and started."
Write-Host "Dashboard: http://127.0.0.1:8765"
Write-Host "Voice status: http://127.0.0.1:8765/api/voice/status"
Write-Host "Logs: $env:LOCALAPPDATA\DesktopAgent\logs\agent.log"
