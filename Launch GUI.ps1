$ErrorActionPreference = 'Stop'
$taskRoot = $PSScriptRoot
$localPython = Join-Path $taskRoot '.venv\Scripts\python.exe'
if (Test-Path -LiteralPath $localPython) {
    $taskPython = $localPython
} else {
    $taskPython = (Get-Command python -ErrorAction Stop).Source
}
$taskScript = Join-Path $taskRoot 'rolamgas.py'
$taskArguments = '"' + $taskScript + '"'
Start-Process -FilePath $taskPython -ArgumentList $taskArguments -WorkingDirectory $taskRoot -WindowStyle Hidden
