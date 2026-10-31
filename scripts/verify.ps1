param([ValidateSet('G1','G2','G3','G4','G5')][string]$Stage = 'G1')
$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
& python (Join-Path $PSScriptRoot 'verify.py') --stage $Stage
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
