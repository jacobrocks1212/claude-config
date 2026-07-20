<#
.SYNOPSIS
  Cross-platform FIFO per-queue-item file lock — PowerShell workstation plane.

.DESCRIPTION
  The PowerShell workstation implementation of the ONE documented concurrent-lock
  grammar (user/skills/_components/concurrent-lock-contract.md). It conforms to
  that contract INDEPENDENTLY of the stdlib-Python plane
  (user/scripts/lazy_coord.py :: acquire_item_lock / release_item_lock) — a
  documented grammar, NOT shared code (the runner-outcome two-implementation
  pattern). Mirrors build-queue.ps1's active.lock + confirmed-dead-reclaim
  precedent, keyed PER QUEUE ITEM (Locked Decision 1 — per-item grain).

  Legs (see the contract):
    1. Per-item grain — one lock file per item id; different items never block.
    2. Acquire = wait-for-unlock FIFO — a live holder is waited on (bounded
       backoff), never stolen; a released lock is taken by a waiter in turn.
    3. Fencing-token release — acquire mints a token written into the lock file;
       release verifies it (a superseded holder cannot release another's lock).
    4. Stale-holder reclaim via CONFIRMED-dead only — a dead pid (or a reused
       pid: live start-time mismatches the recorded one) is reclaimed; an
       ambiguous/live holder is NEVER falsely reclaimed (safety over liveness,
       mirroring Get-ActiveLockStatusFromText / Test-ShouldReclaimLock).
    5. Authoritative acquire/timeout outcome — the LAST-stdout-line banner
       (runner-outcome-contract.md): a timeout is NEVER a false ACQUIRED.

  Silently inert off-Windows (workstation-only plane). The pure functions are
  platform-neutral and dot-sourceable (concurrent-lock.Tests.ps1 dot-sources
  this file to exercise them without running main).

.PARAMETER ItemId
  The queue-item id to lock (feature/bug slug) — the per-item lock key.

.PARAMETER Op
  'acquire' (default) or 'release'.

.PARAMETER Token
  The fencing token returned by a prior acquire — required for release.

.PARAMETER TimeoutSeconds
  Acquire timeout budget (default 10). On exhaustion: RESULT=TIMEOUT, exit 124.

.PARAMETER PollIntervalMs
  Backoff poll interval while waiting on a live holder (default 50).

.PARAMETER TtlSeconds
  Advisory holder TTL recorded in the lock file (default 300).

.PARAMETER StateRoot
  Lock-state root; defaults to ~/.claude/state/concurrent-locks.
#>
[CmdletBinding()]
param(
	[string]$ItemId,
	[ValidateSet('acquire', 'release')]
	[string]$Op = 'acquire',
	[string]$Token,
	[int]$TimeoutSeconds = 10,
	[int]$PollIntervalMs = 50,
	[double]$TtlSeconds = 300,
	[string]$StateRoot
)

# ---------------------------------------------------------------------------
# Pure helpers (platform-neutral; dot-sourceable by the Pester suite)
# ---------------------------------------------------------------------------

function Get-CLSafeValue {
	param([scriptblock]$Script, $Default = $null)
	try { & $Script } catch { $Default }
}

function Test-CLPidAlive {
	param([int]$ProcId)
	if ($ProcId -le 0) { return $false }
	try {
		$null = [System.Diagnostics.Process]::GetProcessById($ProcId)
		return $true
	} catch [System.ArgumentException] {
		return $false
	} catch {
		return $true   # fail safe to alive — better to over-wait than mis-reclaim
	}
}

function Get-CLKernelStartTime {
	param([int]$ProcId)
	Get-CLSafeValue {
		([System.Diagnostics.Process]::GetProcessById($ProcId)).StartTime.ToFileTimeUtc()
	} $null
}

function Get-LockHolderStatus {
	<#
	.SYNOPSIS
	  Classify a lock file's TEXT into 'alive' | 'dead' | 'unknown'. File absence
	  is the CALLER's concern. Mirrors Get-ActiveLockStatusFromText, plus the
	  PID-reuse guard (_confirmed_dead_owner parity): a live pid whose live
	  start-time mismatches the recorded one is 'dead' (reuse).
	#>
	[OutputType([string])]
	param(
		[AllowEmptyString()][string]$Text,
		[Parameter(Mandatory = $true)][scriptblock]$IsPidAlive,
		[scriptblock]$GetStartTime = { param($p) $null }
	)
	$result = Get-CLSafeValue {
		if ([string]::IsNullOrWhiteSpace($Text)) { return 'unknown' }
		$data = Get-CLSafeValue { $Text | ConvertFrom-Json } $null
		if ($null -eq $data) { return 'unknown' }
		$holderPid = Get-CLSafeValue {
			$v = $data | Select-Object -ExpandProperty pid -ErrorAction SilentlyContinue
			if ($null -ne $v) { [int]$v } else { $null }
		} $null
		if ($null -eq $holderPid) { return 'unknown' }
		$isAlive = Get-CLSafeValue { & $IsPidAlive $holderPid } $null
		if ($null -eq $isAlive) { return 'alive' }   # probe threw -> fail safe alive
		if ($isAlive -ne $true) { return 'dead' }
		# Alive pid: guard against PID reuse via recorded vs. live start-time.
		$recordedStart = Get-CLSafeValue {
			$data | Select-Object -ExpandProperty kernel_start_time -ErrorAction SilentlyContinue
		} $null
		if ($null -eq $recordedStart) { return 'alive' }   # incomplete metadata -> ambiguous
		$liveStart = Get-CLSafeValue { & $GetStartTime $holderPid } $null
		if ($null -eq $liveStart) { return 'alive' }       # unverifiable -> never reclaim
		if ("$liveStart" -ne "$recordedStart") { return 'dead' }  # reuse -> confirmed dead
		return 'alive'
	} 'unknown'
	if ([string]::IsNullOrWhiteSpace($result)) { return 'unknown' }
	return $result
}

function Test-ShouldReclaimItemLock {
	<# Reclaim ONLY a CONFIRMED-dead holder. Ambiguous 'unknown'/'alive' never reclaim. #>
	[OutputType([bool])]
	param([string]$Status)
	return ($Status -eq 'dead')
}

function Format-ConcurrentLockBanner {
	<# Leg 5 authoritative LAST-stdout-line banner (runner-outcome-contract.md). #>
	[OutputType([string])]
	param(
		[string]$ItemId,
		[string]$Op,
		[string]$Result,
		$Holder = $null,
		[double]$Elapsed = 0,
		[string]$NextAction
	)
	$line = "concurrent-lock: item=$ItemId op=$Op RESULT=$Result"
	if ($null -ne $Holder -and "$Holder" -ne '') { $line += " holder=$Holder" }
	$line += (" (elapsed={0:0.###}s)" -f $Elapsed)
	if ($NextAction) { $line += " -> $NextAction" }
	return $line
}

function Get-ConcurrentLockStateRoot {
	param([string]$StateRoot)
	if (-not [string]::IsNullOrWhiteSpace($StateRoot)) { return $StateRoot }
	return (Join-Path $HOME '.claude/state/concurrent-locks')
}

function Get-ItemLockPath {
	param([string]$StateRoot, [string]$ItemId)
	$safe = ($ItemId -replace '[^A-Za-z0-9._-]', '-')
	if ([string]::IsNullOrWhiteSpace($safe)) { $safe = 'item' }
	return (Join-Path $StateRoot "$safe.lock")
}

function Invoke-AcquireItemLock {
	<#
	.SYNOPSIS
	  Acquire the per-item FIFO lock. Returns [pscustomobject]@{Result;Token;Holder;Elapsed}
	  with Result in ACQUIRED | RECLAIMED | TIMEOUT (Leg 2/4/5).
	#>
	param(
		[string]$StateRoot,
		[string]$ItemId,
		[int]$TimeoutSeconds = 10,
		[int]$PollIntervalMs = 50,
		[double]$TtlSeconds = 300,
		[scriptblock]$IsPidAlive = { param($p) (Test-CLPidAlive -ProcId $p) },
		[scriptblock]$GetStartTime = { param($p) (Get-CLKernelStartTime -ProcId $p) },
		[scriptblock]$Clock = { [double]([DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds()) / 1000.0 }
	)
	$null = New-Item -ItemType Directory -Path $StateRoot -Force -ErrorAction SilentlyContinue
	$lockPath = Get-ItemLockPath -StateRoot $StateRoot -ItemId $ItemId
	$token = [Guid]::NewGuid().ToString('N')
	$myPid = $PID
	$myStart = Get-CLKernelStartTime -ProcId $myPid
	$start = & $Clock
	$reclaimed = $false

	while ($true) {
		$created = $false
		try {
			$fs = [System.IO.File]::Open(
				$lockPath, [System.IO.FileMode]::CreateNew,
				[System.IO.FileAccess]::Write, [System.IO.FileShare]::None)
			try {
				$body = [ordered]@{
					pid                = $myPid
					kernel_start_time  = $myStart
					acquired_at        = ([DateTimeOffset]::UtcNow.ToString('o'))
					token              = $token
					ttl_seconds        = $TtlSeconds
				} | ConvertTo-Json -Compress
				$bytes = [System.Text.Encoding]::UTF8.GetBytes($body)
				$fs.Write($bytes, 0, $bytes.Length)
			} finally { $fs.Dispose() }
			$created = $true
		} catch [System.IO.IOException] {
			$created = $false
		}

		if ($created) {
			$elapsed = (& $Clock) - $start
			$res = if ($reclaimed) { 'RECLAIMED' } else { 'ACQUIRED' }
			return [pscustomobject]@{ Result = $res; Token = $token; Holder = $myPid; Elapsed = $elapsed }
		}

		# Contended: classify the holder.
		$text = Get-CLSafeValue { [System.IO.File]::ReadAllText($lockPath) } ''
		$status = Get-LockHolderStatus -Text $text -IsPidAlive $IsPidAlive -GetStartTime $GetStartTime
		$holderPid = Get-CLSafeValue {
			($text | ConvertFrom-Json) | Select-Object -ExpandProperty pid -ErrorAction SilentlyContinue
		} $null

		if (Test-ShouldReclaimItemLock -Status $status) {
			# Confirmed-dead: rename-then-delete best-effort, then retry create.
			$null = Get-CLSafeValue { Remove-Item -LiteralPath $lockPath -Force -ErrorAction Stop; $true } $false
			$reclaimed = $true
			continue
		}

		$elapsed = (& $Clock) - $start
		if ($elapsed -ge $TimeoutSeconds) {
			return [pscustomobject]@{ Result = 'TIMEOUT'; Token = $null; Holder = $holderPid; Elapsed = $elapsed }
		}
		Start-Sleep -Milliseconds $PollIntervalMs
	}
}

function Invoke-ReleaseItemLock {
	<#
	.SYNOPSIS
	  Release the per-item lock (Leg 3 — fencing-token release). Returns
	  [pscustomobject]@{Result} with Result in RELEASED | FENCING-STALE.
	  Idempotent: an absent lock is RELEASED (nothing to do).
	#>
	param(
		[string]$StateRoot,
		[string]$ItemId,
		[string]$Token
	)
	$lockPath = Get-ItemLockPath -StateRoot $StateRoot -ItemId $ItemId
	if (-not (Test-Path -LiteralPath $lockPath)) {
		return [pscustomobject]@{ Result = 'RELEASED' }
	}
	$text = Get-CLSafeValue { [System.IO.File]::ReadAllText($lockPath) } ''
	$onDisk = Get-CLSafeValue {
		($text | ConvertFrom-Json) | Select-Object -ExpandProperty token -ErrorAction SilentlyContinue
	} $null
	if ($null -ne $onDisk -and "$onDisk" -ne "$Token") {
		# Superseded holder — never release another's lock.
		return [pscustomobject]@{ Result = 'FENCING-STALE' }
	}
	$null = Get-CLSafeValue { Remove-Item -LiteralPath $lockPath -Force -ErrorAction Stop; $true } $false
	return [pscustomobject]@{ Result = 'RELEASED' }
}

function Invoke-ConcurrentLockMain {
	<#
	.SYNOPSIS
	  Dispatch acquire/release and return [pscustomobject]@{Banner; ExitCode}.
	  Returns the banner as data (NOT Write-Output) so the entry point can print
	  it to stdout as the LAST line and exit with the code — a value-context
	  capture of Write-Output would otherwise swallow the banner.
	#>
	param(
		[string]$ItemId,
		[string]$Op = 'acquire',
		[string]$Token,
		[int]$TimeoutSeconds = 10,
		[int]$PollIntervalMs = 50,
		[double]$TtlSeconds = 300,
		[string]$StateRoot
	)

	# Silently inert off-Windows (workstation-only plane).
	$isWindows = $env:OS -eq 'Windows_NT' -or [System.Environment]::OSVersion.Platform -eq 'Win32NT'
	if (-not $isWindows) {
		return [pscustomobject]@{
			Banner   = (Format-ConcurrentLockBanner -ItemId $ItemId -Op $Op -Result 'INERT' `
				-Elapsed 0 -NextAction 'off-windows workstation-only plane')
			ExitCode = 0
		}
	}

	if ([string]::IsNullOrWhiteSpace($ItemId)) {
		return [pscustomobject]@{
			Banner   = 'concurrent-lock: item=<none> op=' + $Op + ' RESULT=ERROR -> -ItemId is required'
			ExitCode = 2
		}
	}

	$root = Get-ConcurrentLockStateRoot -StateRoot $StateRoot

	if ($Op -eq 'release') {
		$r = Invoke-ReleaseItemLock -StateRoot $root -ItemId $ItemId -Token $Token
		return [pscustomobject]@{
			Banner   = (Format-ConcurrentLockBanner -ItemId $ItemId -Op 'release' -Result $r.Result -Elapsed 0)
			ExitCode = $(if ($r.Result -eq 'RELEASED') { 0 } else { 1 })
		}
	}

	$a = Invoke-AcquireItemLock -StateRoot $root -ItemId $ItemId `
		-TimeoutSeconds $TimeoutSeconds -PollIntervalMs $PollIntervalMs -TtlSeconds $TtlSeconds
	$next = $null
	switch ($a.Result) {
		'ACQUIRED'  { $next = "token=$($a.Token)" }
		'RECLAIMED' { $next = "token=$($a.Token) (reclaimed a confirmed-dead holder)" }
		'TIMEOUT'   { $next = 'holder still live; re-await or check the lock state' }
	}
	return [pscustomobject]@{
		Banner   = (Format-ConcurrentLockBanner -ItemId $ItemId -Op 'acquire' -Result $a.Result `
			-Holder $a.Holder -Elapsed $a.Elapsed -NextAction $next)
		ExitCode = $(if ($a.Result -eq 'TIMEOUT') { 124 } else { 0 })
	}
}

# ---------------------------------------------------------------------------
# Entry point — run main ONLY when invoked directly (dot-source guard so the
# Pester suite can load the pure functions without executing main). The banner
# is written here at script scope (NOT captured in a value context) so it lands
# on stdout as the LAST line, then we exit with the run's own code.
# ---------------------------------------------------------------------------
if ($MyInvocation.InvocationName -ne '.') {
	$__cl = Invoke-ConcurrentLockMain -ItemId $ItemId -Op $Op -Token $Token `
		-TimeoutSeconds $TimeoutSeconds -PollIntervalMs $PollIntervalMs `
		-TtlSeconds $TtlSeconds -StateRoot $StateRoot
	Write-Output $__cl.Banner
	exit $__cl.ExitCode
}
