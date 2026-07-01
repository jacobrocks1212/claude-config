<#
.SYNOPSIS
  Self-releasing detached build runner for the machine-global Cognito build queue.

.DESCRIPTION
  Invoked as a detached child by build-queue.ps1.  Runs the filtered build/test
  script as a nested powershell.exe grandchild, then writes results/<seq>.json
  and releases active.lock (seq-scoped, idempotent) before exiting with the
  build exit code.  The result survives the foreground wrapper being killed.

  Parameters
    -Exec       Absolute path to the filtered script to run.
    -Seq        Queue sequence number allocated by the wrapper.
    -StateRoot  State directory (defaults to the same root as build-queue.ps1).
    Remaining   Verbatim args forwarded to the filtered script.

  results/<seq>.json schema
    {
      seq: <int>, exit_code: <int>, ended_at: "<ISO-8601>",
      hygiene: {
        vbcscompiler_recycled: <bool>,   # whether VBCSCompiler was recycled after the build
        quarantined_artifacts: [<path>], # absolute paths of 0-byte/truncated-PE *.dll swept from bin/+obj/ (empty on a clean build)
        result_fidelity: "verified" | "no-output" | "n/a"  # "no-output" = test op produced zero results; "verified" = test op had real output; "n/a" = build op
        build_fidelity: "log-failure-override" | "verified" | "n/a"  # "log-failure-override" = a build op exited 0 but its captured log matched a known MSBuild failure signature (Test-BuildLogFailure), so the exit code/buildFailed were overridden to failure BEFORE the quarantine gate; "verified" = build op needed no override; "n/a" = non-build op (e.g. test)
      }
    }
    Job-Object reap of build descendants happens unconditionally but records no PID list
    (fire-and-forget) — there is no reaped-PID field.

    Build-op stdout/stderr are redirected to logs/<seq>.build.log / <seq>.build.err.log
    (sibling of results/) so Test-BuildLogFailure has a log to scan for a bogus-exit-0
    failure signature (e.g. copy-lock retries that MSBuild reports as errors but the
    outer process still exits success).
#>
[CmdletBinding()]
param(
	[Parameter(Mandatory=$true)]
	[string]$Exec,

	[Parameter(Mandatory=$true)]
	[int]$Seq,

	[string]$StateRoot = (Join-Path $HOME '.claude\state\build-queue'),

	[string]$Worktree,

	[Parameter(ValueFromRemainingArguments=$true)]
	$ExecArgs
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

function Get-SafeValue {
	param([scriptblock]$Block, $Fallback = $null)
	try { & $Block } catch { $Fallback }
}

Get-SafeValue {
	. (Join-Path $PSScriptRoot 'build-queue-hygiene.ps1')
}

function Format-ProcArg {
	param([string]$Value)
	if ($Value -eq '' -or $Value -match '[\s"]') {
		return '"' + ($Value -replace '"', '\"') + '"'
	}
	return $Value
}

$job = [IntPtr]::Zero
$vbcscompilerRecycled = $false
$quarantinedArtifacts = @()
$execLeaf = Get-SafeValue { Split-Path -Leaf $Exec } ''
$isBuildOp = $execLeaf -match 'build-filtered\.ps1$'
$buildLogPath = $null
$buildFidelity = 'n/a'
trap {
	Get-SafeValue { Stop-BuildJobTree -JobHandle $job }
	continue
}

try {
	$procArgList = @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', (Format-ProcArg $Exec))
	foreach ($a in $ExecArgs) {
		$procArgList += (Format-ProcArg ([string]$a))
	}
	$procArgString = $procArgList -join ' '

	$startProcParams = @{
		FilePath     = 'powershell.exe'
		ArgumentList = $procArgString
		NoNewWindow  = $true
		PassThru     = $true
	}
	if ($isBuildOp) {
		Get-SafeValue {
			$logsDir = Join-Path $StateRoot 'logs'
			if (-not (Test-Path $logsDir)) {
				$null = New-Item -ItemType Directory -Path $logsDir -Force
			}
			$buildLogPath = Join-Path $logsDir "$Seq.build.log"
			$startProcParams['RedirectStandardOutput'] = $buildLogPath
			$startProcParams['RedirectStandardError']  = (Join-Path $logsDir "$Seq.build.err.log")
		}
	}

	$proc = Start-Process @startProcParams
	$null = $proc.Handle

	$job = New-BuildJobObject
	if ($job -ne [IntPtr]::Zero) {
		$null = Add-ProcessToBuildJob -JobHandle $job -ProcessHandle $proc.Handle
	}

	$proc.WaitForExit()
	$exitCode = $proc.ExitCode
	if ($null -eq $exitCode) { $exitCode = 0 }

	if ($isBuildOp) {
		$logFailure = Get-SafeValue {
			if ([string]::IsNullOrWhiteSpace($buildLogPath) -or -not (Test-Path $buildLogPath)) {
				return @{ failed = $false; signature = $null }
			}
			$logText = [System.IO.File]::ReadAllText($buildLogPath)
			Test-BuildLogFailure -Log $logText
		} @{ failed = $false; signature = $null }

		if ($logFailure.failed -and $exitCode -eq 0) {
			$exitCode = 1
			$buildFailed = $true
			$buildFidelity = 'log-failure-override'
		} else {
			$buildFidelity = 'verified'
		}
	}
} finally {
	Get-SafeValue { Stop-BuildJobTree -JobHandle $job }
	$vbcscompilerRecycled = Get-SafeValue { Reset-CompilerServer } $false

	$buildFailed = Get-SafeValue { ($null -eq $exitCode) -or ($exitCode -ne 0) } $true
	if ($buildFailed -and -not [string]::IsNullOrWhiteSpace($Worktree)) {
		$quarantinedArtifacts = Get-SafeValue { @(Remove-PoisonedArtifacts -WorktreeRoot $Worktree) } @()
	}
}

$resultFidelity = Get-SafeValue {
	$isTestOp = $execLeaf -match 'test-filtered\.ps1$'
	if (-not $isTestOp) { 'n/a' }
	elseif ($exitCode -eq 3) { 'no-output' }
	else { 'verified' }
} 'n/a'

$resultsDir = Join-Path $StateRoot 'results'
Get-SafeValue {
	if (-not (Test-Path $resultsDir)) {
		$null = New-Item -ItemType Directory -Path $resultsDir -Force
	}
}

$resultPath = Join-Path $resultsDir "$Seq.json"
$resultTmp  = Join-Path $resultsDir "$Seq.tmp"
$resultBody = [ordered]@{
	seq       = $Seq
	exit_code = $exitCode
	ended_at  = (Get-Date).ToString('o')
	hygiene   = [ordered]@{
		vbcscompiler_recycled = $vbcscompilerRecycled
		quarantined_artifacts = $quarantinedArtifacts
		result_fidelity       = $resultFidelity
		build_fidelity        = $buildFidelity
	}
} | ConvertTo-Json -Compress -Depth 5

[System.IO.File]::WriteAllText($resultTmp, $resultBody)
try {
	[System.IO.File]::Replace($resultTmp, $resultPath, [NullString]::Value)
} catch {
	Get-SafeValue { [System.IO.File]::WriteAllText($resultPath, $resultBody) }
	Get-SafeValue { Remove-Item $resultTmp -Force -ErrorAction SilentlyContinue }
}

$activeLock = Join-Path $StateRoot 'active.lock'
Get-SafeValue {
	if (Test-Path $activeLock) {
		$data    = [System.IO.File]::ReadAllText($activeLock) | ConvertFrom-Json
		$lockSeq = Get-SafeValue { [int]$data.seq } $null
		if ($lockSeq -eq $Seq) {
			Remove-Item $activeLock -Force
		}
	}
}

exit $exitCode
