param(
  [string]$ConfigPath = (Join-Path $PSScriptRoot '..\config\local\relay.local.json'),
  [int]$Duration = 300
)
$ErrorActionPreference = 'Stop'
& python (Join-Path $PSScriptRoot 'relay_live.py') --config $ConfigPath --duration $Duration
exit $LASTEXITCODE
