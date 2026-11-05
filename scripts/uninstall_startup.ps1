# Remove automatic startup for Desktop Agent. Does not delete project files or memory.
$ErrorActionPreference = "Stop"
$TaskName = "DesktopAgent-Alexa"
$Task = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if ($Task) {
    Stop-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
    Write-Host "Desktop Agent automatic startup has been removed."
} else {
    Write-Host "Desktop Agent startup task was not installed."
}
