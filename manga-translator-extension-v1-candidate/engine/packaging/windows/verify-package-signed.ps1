param(
  [Parameter(Mandatory=$true)][string]$RootPath,
  [Parameter(Mandatory=$true)][string]$OutputZip
)
$ErrorActionPreference = 'Stop'
if (-not (Test-Path $RootPath -PathType Container)) { throw "Signed payload root not found: $RootPath" }
$Files = Get-ChildItem -Path $RootPath -Recurse -File | Where-Object { $_.Extension -in @('.exe','.dll','.pyd') }
if ($Files.Count -eq 0) { throw 'No Windows PE files found to verify.' }
foreach ($File in $Files) {
  $Signature = Get-AuthenticodeSignature -FilePath $File.FullName
  if ($Signature.Status -ne 'Valid') {
    throw "Authenticode verification failed for $($File.FullName): $($Signature.Status)"
  }
}
if (Test-Path $OutputZip) { Remove-Item $OutputZip -Force }
$Parent = Split-Path -Parent $OutputZip
if ($Parent) { New-Item -ItemType Directory -Force -Path $Parent | Out-Null }
Compress-Archive -Path (Join-Path $RootPath '*') -DestinationPath $OutputZip -CompressionLevel Optimal
if (-not (Test-Path $OutputZip -PathType Leaf)) { throw 'Signed Windows archive was not created.' }
Write-Output $OutputZip
