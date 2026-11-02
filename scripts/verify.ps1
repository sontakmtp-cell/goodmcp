param(
  [ValidateSet('G1','G2','G3','G4','G5','G9')][string]$Stage = 'G1',
  [switch]$WorkingTree,
  [string]$G4Release
)
$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
$verifyArgs = @((Join-Path $PSScriptRoot 'verify.py'), '--stage', $Stage)
if ($WorkingTree) { $verifyArgs += '--working-tree' }
if ($G4Release) { $verifyArgs += @('--g4-release', $G4Release) }
& python @verifyArgs
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
