param([switch]$Release)
$ErrorActionPreference = 'Stop'
$Root = Resolve-Path (Join-Path $PSScriptRoot '..\..\..')
$Args = @((Join-Path $Root 'engine\packaging\build_engine.py'))
if ($Release) { $Args += '--release' }
python @Args
