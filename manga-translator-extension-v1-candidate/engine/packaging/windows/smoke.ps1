param([Parameter(Mandatory=$true)][string]$Executable)
$ErrorActionPreference = 'Stop'
python (Join-Path $PSScriptRoot '..\smoke_engine.py') $Executable
