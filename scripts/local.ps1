param([ValidateSet('Start','Download','Probe','Evaluate')][string]$Action = 'Probe')
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectRoot
$env:INTERRA_PROFILE = 'local'
$env:INTERRA_MODEL = 'qwen3-vl:2b'
$env:INTERRA_MODEL_ROOT = Join-Path $projectRoot '.models'
$env:INTERRA_MEDIA_ROOT = Join-Path $projectRoot 'vendor/samsung_theme05'
$env:INTERRA_TRACE_DIR = Join-Path $projectRoot 'artifacts/local-traces'
$env:OLLAMA_MODELS = Join-Path $projectRoot '.models/ollama'
$env:OLLAMA_NUM_PARALLEL = '1'
$env:OLLAMA_MAX_LOADED_MODELS = '1'
$env:OLLAMA_CONTEXT_LENGTH = '4096'
$python = Join-Path $projectRoot '.venv/Scripts/python.exe'
switch ($Action) {
    'Start' {
        $ollama = Join-Path $projectRoot '.tools/ollama/ollama.exe'
        if (-not (Test-Path -LiteralPath $ollama)) { $ollama = (Get-Command ollama -ErrorAction Stop).Source }
        New-Item -ItemType Directory -Force artifacts | Out-Null
        Start-Process -FilePath $ollama -ArgumentList 'serve' -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $projectRoot 'artifacts/ollama.out.log') -RedirectStandardError (Join-Path $projectRoot 'artifacts/ollama.err.log')
    }
    'Download' { & $python -m agent.local_setup download }
    'Probe' { & $python -m agent.local_setup probe --audio audio/pub_05_turn1.mp3 --image frames/pub_07_f017.png }
    'Evaluate' { & $python vendor/samsung_theme05/eval_submission.py . --reps 3 --time-scale 1 --out artifacts/samsung-local-evaluation.json }
}
if ($Action -ne 'Start' -and $LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
