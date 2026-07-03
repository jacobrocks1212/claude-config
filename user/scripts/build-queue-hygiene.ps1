<#
.SYNOPSIS
  Build-queue process hygiene helpers — Windows Job-Object lifecycle.

.DESCRIPTION
  Dot-sourceable module that owns the Windows Job-Object lifecycle so a build
  runner can scope and reap exactly one build's descendant process tree.

  This is the shared home for build-queue hygiene helpers. Later work units
  add more functions here (result fidelity, etc.) — this revision adds the
  Job-Object surface, the VBCSCompiler recycle, and the poisoned-artifact
  sweep:

    New-BuildJobObject       - create a kill-on-close Job Object
    Add-ProcessToBuildJob    - assign a process to a Job Object
    Stop-BuildJobTree        - terminate the Job Object (and all members)
    Reset-CompilerServer     - force-recycle VBCSCompiler after a queued build
    Remove-PoisonedArtifacts - sweep bin/ + obj/ for 0-byte/truncated *.dll
    Test-BuildLogFailure     - pure scan of a captured build log for known
                               MSBuild failure signatures (bogus exit 0 guard)

.NOTES
  HARD REQUIREMENT — FAIL OPEN. None of these functions may throw in a way
  that aborts the caller's build. Any P/Invoke failure, missing API, or
  non-Windows host logs a Write-Warning and returns a benign sentinel
  ([IntPtr]::Zero / $false).

  HARD REQUIREMENT — NO GLOBAL PROCESS KILL. Reaping is scoped to Job-Object
  membership ONLY. This module must never contain a process-name-glob kill
  cmdlet pairing that targets processes by name rather than by Job-Object
  membership — doing so could tear down a sibling worktree's live build. See
  Locked Decision 2 in docs/bugs/build-queue-no-artifact-or-process-hygiene-on-crash.

  Dot-source this file; it defines functions only and performs no top-level
  side effects beyond the guarded Add-Type below.
#>

Set-StrictMode -Version Latest

# Fail-open helper idiom (copied verbatim from build-queue-runner.ps1:34-37).
function Get-SafeValue {
	param([scriptblock]$Block, $Fallback = $null)
	try { & $Block } catch { $Fallback }
}

function Read-WithRetry {
	<#
	.SYNOPSIS
	  Bounded parse-with-retry helper: invoke a parse scriptblock up to
	  -MaxAttempts times, returning the first non-$null result, or -Fallback
	  after all attempts are exhausted.

	.DESCRIPTION
	  Extracts the proven active.lock retry/settle pattern
	  (build-queue-runner.ps1 / build-queue.ps1: 3 attempts, 50ms apart, NO
	  sleep after the last attempt) into a reusable, Pester-testable helper. It
	  is the fix for build-queue-false-green-on-silent-build-failure Root Cause
	  C: a fidelity-bearing read (the runner's test-counts parse and build-log
	  read) races the wrapper-owned log flush/close and drops a trailing line,
	  reading as empty on the first shot. Routing those reads through this helper
	  gives a not-yet-flushed line time to settle instead of committing an empty
	  parse.

	  A $null return from the parse block means "not ready — retry"; any non-null
	  value (including '' if a caller chooses) means "done, use this". The sleep
	  happens ONLY between attempts (never after the final attempt), matching the
	  active.lock exemplar exactly.

	.PARAMETER Parse
	  Scriptblock that performs the read/parse and returns the parsed payload, or
	  $null when the expected content is not (yet) present.

	.PARAMETER MaxAttempts
	  Total number of parse attempts (default 3, as in the active.lock loop).

	.PARAMETER DelayMs
	  Milliseconds to sleep BETWEEN attempts (default 50, as in the active.lock
	  loop). No sleep occurs after the last attempt.

	.PARAMETER Fallback
	  Value returned when every attempt yields $null (default $null).

	.OUTPUTS
	  The first non-$null result of $Parse, or $Fallback.
	#>
	[CmdletBinding()]
	param(
		[Parameter(Mandatory = $true)]
		[scriptblock]$Parse,

		[int]$MaxAttempts = 3,

		[int]$DelayMs = 50,

		$Fallback = $null
	)

	for ($attempt = 1; $attempt -le $MaxAttempts; $attempt++) {
		$value = & $Parse
		if ($null -ne $value) {
			return $value
		}
		if ($attempt -lt $MaxAttempts) {
			Start-Sleep -Milliseconds $DelayMs
		}
	}

	return $Fallback
}

function Test-BuildProducedNoOutput {
	<#
	.SYNOPSIS
	  Positive build-output classifier: returns $true when a build op produced
	  no captured output (the exit-0 silently-broken-build residual case).

	.DESCRIPTION
	  Fix for build-queue-false-green-on-silent-build-failure Root Cause B: the
	  runner's negative log-signature scan (Test-BuildLogFailure) fails OPEN on a
	  0-byte / empty / whitespace-only build log, so a build that compiled nothing
	  is reported as a clean PASS. This is the POSITIVE complement — it asserts the
	  build actually emitted output rather than only scanning for known failure
	  signatures.

	  DEFAULT DETECTION (implemented here): the passed build-log text is classified
	  no-output ($true) when it is $null (a missing log path — the runner never
	  captured a log), empty, whitespace-only, or NEAR-EMPTY (trimmed length below
	  -MinChars). A real MSBuild / nx build log — even a trivial all-up-to-date one —
	  carries the tool banner, "Build succeeded.", warning/error counts, and an
	  elapsed-time line, i.e. hundreds of characters, so the near-empty threshold
	  cannot false-positive a genuine build.

	  FOLLOW-ON KNOB (documented, NOT implemented here): a stronger
	  expected-output-DLL check — the build's expected output DLL exists AND is
	  newer than its sources — would catch a build that logged plausibly but wrote
	  no artifact. It requires an expected-output path the runner does not track
	  today; it is a deliberate future extension (SPEC Open Question "Build-output
	  detection method"), left out of this default classifier.

	  Pure, side-effect-free; never throws.

	.PARAMETER LogText
	  The captured build-log text (read once, flush-safely, via Read-WithRetry).
	  $null when the runner never captured a log.

	.PARAMETER MinChars
	  Near-empty threshold: a trimmed log shorter than this many characters counts
	  as no-output. Default 40 — comfortably below any real build log, well above a
	  truncated/empty capture.

	.OUTPUTS
	  [bool] $true when the build produced no output; $false otherwise.
	#>
	[CmdletBinding()]
	[OutputType([bool])]
	param(
		[string]$LogText,
		[int]$MinChars = 40
	)

	if ([string]::IsNullOrWhiteSpace($LogText)) { return $true }
	if ($LogText.Trim().Length -lt $MinChars) { return $true }
	return $false
}

function Get-HygieneHighlight {
	<#
	.SYNOPSIS
	  Pure highlight selector for the per-build hygiene line in
	  build-queue-status.ps1: maps a build_fidelity / result_fidelity pair to the
	  status-line suffix + console color.

	.DESCRIPTION
	  Extracted so build-queue-status.ps1 and its Pester coverage exercise the SAME
	  branch selection (the status script itself reads state dirs and is not
	  dot-source-testable). Precedence (highest first):
	    1. build_fidelity 'log-failure-override' -> Red  '[BUILD LIED - copy-lock override fired]'
	    2. build_fidelity 'no-output'            -> Red  '[BUILD LIED - produced no output]'
	    3. result_fidelity 'no-output' (test op) -> Yellow '[UNVERIFIED - no test output captured]'
	    4. otherwise                             -> no highlight (empty suffix, $null color)

	  The two build-op arms (1,2) are distinct RED signals; the test-op arm (3) is a
	  softer YELLOW — a test op that captured no results is unverified, not a lie.
	  Pure, side-effect-free; never throws.

	.PARAMETER BuildFidelity
	  The recorded hygiene.build_fidelity ('verified' | 'log-failure-override' |
	  'no-output' | 'n/a').

	.PARAMETER ResultFidelity
	  The recorded hygiene.result_fidelity ('verified' | 'no-output' |
	  'no-tests-matched' | 'n/a').

	.OUTPUTS
	  [hashtable] @{ Suffix = <string>; Color = <ConsoleColor name or $null> }.
	#>
	[CmdletBinding()]
	[OutputType([hashtable])]
	param(
		[string]$BuildFidelity,
		[string]$ResultFidelity
	)

	if ($BuildFidelity -eq 'log-failure-override') {
		return @{ Suffix = '  [BUILD LIED - copy-lock override fired]'; Color = 'Red' }
	} elseif ($BuildFidelity -eq 'no-output') {
		return @{ Suffix = '  [BUILD LIED - produced no output]'; Color = 'Red' }
	} elseif ($ResultFidelity -eq 'no-output') {
		return @{ Suffix = '  [UNVERIFIED - no test output captured]'; Color = 'Yellow' }
	} else {
		return @{ Suffix = ''; Color = $null }
	}
}

# Guard Add-Type so re-dot-sourcing this file in the same PowerShell session
# (or re-importing in a test run) does not throw "type already exists".
if (-not ([System.Management.Automation.PSTypeName]'BuildQueueHygiene.NativeMethods').Type) {
	Get-SafeValue {
		Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;

namespace BuildQueueHygiene
{
    [StructLayout(LayoutKind.Sequential)]
    public struct JOBOBJECT_BASIC_LIMIT_INFORMATION
    {
        public long PerProcessUserTimeLimit;
        public long PerJobUserTimeLimit;
        public uint LimitFlags;
        public UIntPtr MinimumWorkingSetSize;
        public UIntPtr MaximumWorkingSetSize;
        public uint ActiveProcessLimit;
        public UIntPtr Affinity;
        public uint PriorityClass;
        public uint SchedulingClass;
    }

    [StructLayout(LayoutKind.Sequential)]
    public struct IO_COUNTERS
    {
        public ulong ReadOperationCount;
        public ulong WriteOperationCount;
        public ulong OtherOperationCount;
        public ulong ReadTransferCount;
        public ulong WriteTransferCount;
        public ulong OtherTransferCount;
    }

    [StructLayout(LayoutKind.Sequential)]
    public struct JOBOBJECT_EXTENDED_LIMIT_INFORMATION
    {
        public JOBOBJECT_BASIC_LIMIT_INFORMATION BasicLimitInformation;
        public IO_COUNTERS IoInfo;
        public UIntPtr ProcessMemoryLimit;
        public UIntPtr JobMemoryLimit;
        public UIntPtr PeakProcessMemoryUsed;
        public UIntPtr PeakJobMemoryUsed;
    }

    // --- Restart Manager (rstrtmgr.dll) surface: enumerate the processes that
    //     hold a handle on a worktree's bin/Debug/**/*.dll BEFORE the copy step,
    //     the root cause of intermittent MSB3027 copy-lock failures. ---

    public enum RM_APP_TYPE
    {
        RmUnknownApp = 0,
        RmMainWindow = 1,
        RmOtherWindow = 2,
        RmService = 3,
        RmExplorer = 4,
        RmConsole = 5,
        RmCritical = 1000
    }

    [StructLayout(LayoutKind.Sequential)]
    public struct RM_UNIQUE_PROCESS
    {
        public int dwProcessId;
        public System.Runtime.InteropServices.ComTypes.FILETIME ProcessStartTime;
    }

    [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Unicode)]
    public struct RM_PROCESS_INFO
    {
        public RM_UNIQUE_PROCESS Process;

        [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 256)]
        public string strAppName;

        [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 64)]
        public string strServiceShortName;

        public RM_APP_TYPE ApplicationType;
        public uint AppStatus;
        public uint TSSessionId;

        [MarshalAs(UnmanagedType.Bool)]
        public bool bRestartable;
    }

    public static class NativeMethods
    {
        public const uint JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x00002000;
        public const int JobObjectExtendedLimitInformation = 9;

        public const int RM_SESSION_KEY_LEN = 16;      // sizeof(GUID)
        public const int CCH_RM_SESSION_KEY = 32;      // RM_SESSION_KEY_LEN * 2
        public const int ERROR_MORE_DATA = 234;

        [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
        public static extern IntPtr CreateJobObjectW(IntPtr lpJobAttributes, string lpName);

        [DllImport("kernel32.dll", SetLastError = true)]
        public static extern bool SetInformationJobObject(
            IntPtr hJob,
            int JobObjectInfoClass,
            ref JOBOBJECT_EXTENDED_LIMIT_INFORMATION lpJobObjectInfo,
            uint cbJobObjectInfoLength);

        [DllImport("kernel32.dll", SetLastError = true)]
        public static extern bool AssignProcessToJobObject(IntPtr hJob, IntPtr hProcess);

        [DllImport("kernel32.dll", SetLastError = true)]
        public static extern bool TerminateJobObject(IntPtr hJob, uint uExitCode);

        [DllImport("kernel32.dll", SetLastError = true)]
        public static extern bool CloseHandle(IntPtr hObject);

        [DllImport("rstrtmgr.dll", CharSet = CharSet.Unicode)]
        public static extern int RmStartSession(
            out uint pSessionHandle,
            int dwSessionFlags,
            string strSessionKey);

        [DllImport("rstrtmgr.dll", CharSet = CharSet.Unicode)]
        public static extern int RmRegisterResources(
            uint pSessionHandle,
            uint nFiles,
            string[] rgsFilenames,
            uint nApplications,
            IntPtr rgApplications,
            uint nServices,
            string[] rgsServiceNames);

        [DllImport("rstrtmgr.dll")]
        public static extern int RmGetList(
            uint dwSessionHandle,
            out uint pnProcInfoNeeded,
            ref uint pnProcInfo,
            [In, Out] RM_PROCESS_INFO[] rgAffectedApps,
            ref uint lpdwRebootReasons);

        [DllImport("rstrtmgr.dll")]
        public static extern int RmEndSession(uint pSessionHandle);
    }
}
'@ -ErrorAction Stop
	}
}

function New-BuildJobObject {
	<#
	.SYNOPSIS
	  Creates a Windows Job Object with JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE set,
	  so closing/terminating the job kills every process assigned to it.

	.OUTPUTS
	  [IntPtr] job handle on success, or [IntPtr]::Zero on any failure
	  (fail-open — never throws).
	#>
	[CmdletBinding()]
	[OutputType([IntPtr])]
	param()

	$result = Get-SafeValue {
		if (-not ([System.Management.Automation.PSTypeName]'BuildQueueHygiene.NativeMethods').Type) {
			throw 'BuildQueueHygiene.NativeMethods type unavailable (non-Windows host or Add-Type failure).'
		}

		$jobHandle = [BuildQueueHygiene.NativeMethods]::CreateJobObjectW([IntPtr]::Zero, $null)
		if ($jobHandle -eq [IntPtr]::Zero) {
			throw "CreateJobObjectW failed (Win32 error $([System.Runtime.InteropServices.Marshal]::GetLastWin32Error()))."
		}

		$limitInfo = New-Object BuildQueueHygiene.JOBOBJECT_EXTENDED_LIMIT_INFORMATION
		$limitInfo.BasicLimitInformation.LimitFlags = [BuildQueueHygiene.NativeMethods]::JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE

		$infoSize = [System.Runtime.InteropServices.Marshal]::SizeOf([type][BuildQueueHygiene.JOBOBJECT_EXTENDED_LIMIT_INFORMATION])
		$ok = [BuildQueueHygiene.NativeMethods]::SetInformationJobObject(
			$jobHandle,
			[BuildQueueHygiene.NativeMethods]::JobObjectExtendedLimitInformation,
			[ref]$limitInfo,
			[uint32]$infoSize)

		if (-not $ok) {
			$err = [System.Runtime.InteropServices.Marshal]::GetLastWin32Error()
			[void][BuildQueueHygiene.NativeMethods]::CloseHandle($jobHandle)
			throw "SetInformationJobObject failed (Win32 error $err)."
		}

		$jobHandle
	} $null

	if ($null -eq $result) {
		Write-Warning 'New-BuildJobObject: failed to create/configure Job Object; returning benign sentinel ([IntPtr]::Zero).'
		return [IntPtr]::Zero
	}

	return $result
}

function Add-ProcessToBuildJob {
	<#
	.SYNOPSIS
	  Assigns a process to a Job Object so it (and any children it spawns)
	  is reaped when the job is terminated.

	.PARAMETER JobHandle
	  The Job Object handle returned by New-BuildJobObject.

	.PARAMETER ProcessHandle
	  The native process handle to assign (e.g. a System.Diagnostics.Process
	  object's .Handle).

	.OUTPUTS
	  [bool] $true on success, $false on any failure (fail-open — never throws).
	#>
	[CmdletBinding()]
	[OutputType([bool])]
	param(
		[Parameter(Mandatory = $true)]
		[IntPtr]$JobHandle,

		[Parameter(Mandatory = $true)]
		[IntPtr]$ProcessHandle
	)

	$result = Get-SafeValue {
		if (-not ([System.Management.Automation.PSTypeName]'BuildQueueHygiene.NativeMethods').Type) {
			throw 'BuildQueueHygiene.NativeMethods type unavailable (non-Windows host or Add-Type failure).'
		}
		if ($JobHandle -eq [IntPtr]::Zero -or $ProcessHandle -eq [IntPtr]::Zero) {
			throw 'Add-ProcessToBuildJob: JobHandle and ProcessHandle must both be non-zero.'
		}

		$ok = [BuildQueueHygiene.NativeMethods]::AssignProcessToJobObject($JobHandle, $ProcessHandle)
		if (-not $ok) {
			$err = [System.Runtime.InteropServices.Marshal]::GetLastWin32Error()
			throw "AssignProcessToJobObject failed (Win32 error $err)."
		}

		$true
	} $false

	if ($result -ne $true) {
		Write-Warning 'Add-ProcessToBuildJob: failed to assign process to Job Object; returning $false.'
		return $false
	}

	return $true
}

function Stop-BuildJobTree {
	<#
	.SYNOPSIS
	  Terminates a Job Object (killing every assigned process and their
	  descendants, scoped strictly to that job's membership) and closes the
	  handle.

	.PARAMETER JobHandle
	  The Job Object handle returned by New-BuildJobObject.

	.OUTPUTS
	  [bool] $true if the job was terminated, $false on failure/no-op
	  (fail-open — never throws).
	#>
	[CmdletBinding()]
	[OutputType([bool])]
	param(
		[Parameter(Mandatory = $true)]
		[IntPtr]$JobHandle
	)

	$result = Get-SafeValue {
		if (-not ([System.Management.Automation.PSTypeName]'BuildQueueHygiene.NativeMethods').Type) {
			throw 'BuildQueueHygiene.NativeMethods type unavailable (non-Windows host or Add-Type failure).'
		}
		if ($JobHandle -eq [IntPtr]::Zero) {
			throw 'Stop-BuildJobTree: JobHandle must be non-zero.'
		}

		$terminated = [BuildQueueHygiene.NativeMethods]::TerminateJobObject($JobHandle, 1)
		if (-not $terminated) {
			$err = [System.Runtime.InteropServices.Marshal]::GetLastWin32Error()
			Write-Warning "Stop-BuildJobTree: TerminateJobObject failed (Win32 error $err)."
		}

		Get-SafeValue { [void][BuildQueueHygiene.NativeMethods]::CloseHandle($JobHandle) }

		$terminated
	} $false

	if ($result -ne $true) {
		return $false
	}

	return $true
}

function Get-BuildQueueOccupancy {
	<#
	.SYNOPSIS
	  Counts the OTHER live (non-self) queue seqs currently occupying the
	  machine-global build queue, so a caller can gate a machine-wide action
	  (the VBCSCompiler recycle) on whether it would be safe.

	.DESCRIPTION
	  Self-contained — does NOT depend on build-queue.ps1 (no dot-sourcing,
	  no shared helper reuse) so this module stays independently loadable.

	  Reads every ticket under `<StateRoot>/tickets/*.json` (each expected
	  to carry `{seq, pid}`) and the single `<StateRoot>/active.lock` (if
	  present, expected to carry `{seq, build_pid}`). A seq is counted iff
	  it is a valid integer, it is NOT $SelfSeq, and its pid is ALIVE. The
	  same OTHER seq can legitimately appear in both a ticket AND
	  active.lock (a build holds its ticket while it also holds the active
	  lock) — such a seq is counted ONCE (union by seq, not by occurrence).

	  Pid liveness is checked inline via
	  [System.Diagnostics.Process]::GetProcessById — this module
	  deliberately does NOT depend on build-queue.ps1's Test-PidAlive. A pid
	  <= 0 is treated as dead. A GetProcessById call that throws
	  [System.ArgumentException] means no such process exists → dead. Any
	  OTHER exception (e.g. access denied) fails SAFE to alive — matching
	  the existing Test-PidAlive / Get-ActiveLockStatusFromText "fail safe
	  to alive" bias elsewhere in this module.

	  FAIL-OPEN TOWARD RECYCLE: the entire read is wrapped so that ANY
	  failure (absent/unreadable StateRoot, an unreadable/malformed
	  individual ticket, a malformed active.lock) yields a LOW count. An
	  unreadable individual ticket is skipped (not counted) rather than
	  aborting the whole scan. This bias is deliberate — a failed occupancy
	  read must fall back to the EXISTING (pre-gate) recycle behavior
	  (count 0 -> `Reset-CompilerServer -OtherBuildActive $false` -> normal
	  recycle), never silently keep a poisoned compiler server alive by
	  spuriously reporting a high occupancy.

	.PARAMETER StateRoot
	  Root directory of the build-queue state (contains `tickets/` and
	  `active.lock`).

	.PARAMETER SelfSeq
	  The calling build's own queue seq, excluded from the count.

	.OUTPUTS
	  [int] count of OTHER live seqs. Never throws; never negative.
	#>
	[CmdletBinding()]
	[OutputType([int])]
	param(
		[Parameter(Mandatory = $true)]
		[string]$StateRoot,

		[Parameter(Mandatory = $true)]
		[int]$SelfSeq
	)

	$isPidAlive = {
		param([long]$TargetPid)

		if ($TargetPid -le 0) {
			return $false
		}

		try {
			[void][System.Diagnostics.Process]::GetProcessById([int]$TargetPid)
			return $true
		} catch [System.ArgumentException] {
			return $false
		} catch {
			# Any other failure (e.g. access denied) fails SAFE to alive.
			return $true
		}
	}

	$count = Get-SafeValue {
		$liveOtherSeqs = New-Object 'System.Collections.Generic.HashSet[int]'

		$ticketsDir = Join-Path $StateRoot 'tickets'
		if (Test-Path -LiteralPath $ticketsDir) {
			$ticketFiles = Get-SafeValue { Get-ChildItem -LiteralPath $ticketsDir -Filter '*.json' -File -ErrorAction Stop } @()
			if ($null -eq $ticketFiles) { $ticketFiles = @() }

			foreach ($ticketFile in @($ticketFiles)) {
				$parsed = Get-SafeValue {
					$text = [System.IO.File]::ReadAllText($ticketFile.FullName)
					$text | ConvertFrom-Json
				} $null
				if ($null -eq $parsed) { continue }

				$seq = Get-SafeValue { [int]$parsed.seq } $null
				if ($null -eq $seq -or $seq -eq $SelfSeq) { continue }

				$ticketPid = Get-SafeValue { [long]$parsed.pid } $null
				if ($null -eq $ticketPid) { continue }

				$alive = Get-SafeValue { & $isPidAlive $ticketPid } $false
				if ($alive -eq $true) {
					[void]$liveOtherSeqs.Add($seq)
				}
			}
		}

		$lockPath = Join-Path $StateRoot 'active.lock'
		if (Test-Path -LiteralPath $lockPath) {
			$lockParsed = Get-SafeValue {
				$text = [System.IO.File]::ReadAllText($lockPath)
				$text | ConvertFrom-Json
			} $null

			if ($null -ne $lockParsed) {
				$lockSeq = Get-SafeValue { [int]$lockParsed.seq } $null
				if ($null -ne $lockSeq -and $lockSeq -ne $SelfSeq) {
					$lockPid = Get-SafeValue { [long]$lockParsed.build_pid } $null
					if ($null -ne $lockPid) {
						$lockAlive = Get-SafeValue { & $isPidAlive $lockPid } $false
						if ($lockAlive -eq $true) {
							[void]$liveOtherSeqs.Add($lockSeq)
						}
					}
				}
			}
		}

		$liveOtherSeqs.Count
	} 0

	if ($null -eq $count) {
		return 0
	}

	return [int]$count
}

function Reset-CompilerServer {
	<#
	.SYNOPSIS
	  Force-recycles the machine-global VBCSCompiler compiler-server process
	  after a queued build, so the NEXT build cold-starts a fresh server
	  instead of inheriting a half-dead one that poisons it with MSB4166
	  ("child node exited prematurely").

	.DESCRIPTION
	  Primary path: ask the .NET SDK to shut its build servers down
	  gracefully (`dotnet build-server shutdown`). If that does not succeed
	  (missing `dotnet`, non-zero exit, or a thrown error), falls back to a
	  direct process-name-targeted stop of VBCSCompiler.

	  This name-targeted fallback is the ONE sanctioned name-targeted kill in
	  this module (Locked Decision 1 in
	  docs/bugs/build-queue-no-artifact-or-process-hygiene-on-crash). It is a
	  narrow, deliberate exception to Locked Decision 2's no-global-process-
	  kill rule (see New-BuildJobObject/Stop-BuildJobTree above), and it must
	  stay scoped to this one compiler-server process. It must NEVER be
	  widened to the build-tree process family (the SDK CLI host, the test
	  host, or the MSBuild host process) — those remain reaped exclusively
	  via Job-Object membership per Locked Decision 2, never by matching
	  their process name.

	  OCCUPANCY-GATED (this is no longer safe by blanket machine-wide
	  serialization assumption). The recycle used to be justified by "the
	  build queue serializes builds machine-wide, so by the time a build
	  finishes no other queued build's compiler server can be mid-use" — but
	  that invariant is violable (a reclaim race on a stale lock, or an
	  off-queue `BUILD_QUEUE_BYPASS=1` build, can run concurrently with this
	  build), and a blind recycle in that window kills a CONCURRENT
	  worktree's live VBCSCompiler mid-compile (MSB4166). The caller now
	  computes queue occupancy (`Get-BuildQueueOccupancy`) and passes
	  `-OtherBuildActive`: when another build is active, the recycle is
	  SKIPPED entirely (shared compilation stays enabled; only the recycle
	  is gated) so it never tears down a concurrent build's compiler server.

	  Residuals (accepted, not closed):
	    (a) Occupancy is queue-visible only. An off-queue
	        `BUILD_QUEUE_BYPASS=1` build never writes a ticket/active.lock
	        entry, so it is invisible to `Get-BuildQueueOccupancy` and can
	        still be torn down by a recycle that sees occupancy 0. Mitigated
	        (the common case — a queue-obedient concurrent build — is now
	        safe), not closed.
	    (b) The fail-open bias is TOWARD recycling, not away from it. An
	        occupancy-read failure (unreadable state dir, malformed ticket
	        JSON, etc.) resolves to a count of 0 — i.e. the recycle
	        proceeds — because a failed occupancy read must never silently
	        leave a poisoned VBCSCompiler running machine-wide.

	.PARAMETER OtherBuildActive
	  Whether the caller has determined (via Get-BuildQueueOccupancy) that at
	  least one OTHER build is currently active in the queue. When $true,
	  the recycle is skipped and this function returns $false without
	  attempting either the graceful shutdown or the fallback kill.

	.OUTPUTS
	  [bool] $true if a recycle action was taken/succeeded, $false if it was
	  skipped (occupancy-gated) or otherwise failed (fail-open — never
	  throws).
	#>
	[CmdletBinding()]
	[OutputType([bool])]
	param(
		[bool]$OtherBuildActive = $false
	)

	if ($OtherBuildActive) {
		Write-Verbose 'Reset-CompilerServer: another build is active (occupancy>0) — SKIPPING the machine-wide VBCSCompiler recycle to avoid tearing down a concurrent build''s compiler server.'
		return $false
	}

	$result = Get-SafeValue {
		$gracefulOk = Get-SafeValue {
			$null = & dotnet build-server shutdown 2>&1
			$LASTEXITCODE -eq 0
		} $false

		if ($gracefulOk -eq $true) {
			return $true
		}

		$fallbackOk = Get-SafeValue {
			Get-Process -Name 'VBCSCompiler' -ErrorAction SilentlyContinue |
				Stop-Process -Force -ErrorAction SilentlyContinue
			$true
		} $false

		$fallbackOk
	} $false

	if ($result -ne $true) {
		return $false
	}

	return $true
}

function Get-ProjectDlls {
	<#
	.SYNOPSIS
	  Shared per-project *.dll enumerator: recursively finds every *.dll under
	  ANY bin/ or obj/ segment beneath the worktree root — across EVERY project
	  subdir (<root>/**/bin, <root>/**/obj), not just <root>/bin + <root>/obj.

	.DESCRIPTION
	  This is the single enumeration source both Remove-PoisonedArtifacts (poison
	  sweep, no filter) and Get-DllLockers (copy-lock enumeration, 'bin/Debug'
	  filter) call. Widening from the worktree-root-only walk to a per-project
	  walk is the fix for build-queue-false-green-on-silent-build-failure Root
	  Cause A: a poisoned per-project artifact (e.g. a 0-byte
	  Cognito/bin/Debug/netstandard2.0/Cognito.dll) survived the old
	  <root>/bin-only sweep and poisoned the next incremental build.

	  Enumeration is recursive from $WorktreeRoot for *.dll, then restricted to
	  files whose path contains a bin/ or obj/ segment (so non-build DLLs are
	  excluded). An optional -PathSegmentFilter (e.g. 'bin/Debug', either slash
	  style) further restricts to files whose path contains that consecutive
	  segment run — this is how Get-DllLockers keeps its bin/Debug scope while
	  sharing this one enumeration.

	  Fail-open: a nonexistent root or ANY enumeration error yields an empty
	  array (never throws) — a build must proceed even if enumeration is
	  impossible.

	.PARAMETER WorktreeRoot
	  Root directory of the worktree to enumerate.

	.PARAMETER PathSegmentFilter
	  Optional path-segment run (e.g. 'bin/Debug') that a DLL's full path must
	  contain to be returned. Omitted / empty ⇒ every bin|obj DLL is returned.

	.OUTPUTS
	  [System.IO.FileInfo[]] the matching DLL file objects (empty array on a
	  missing root, no matches, or any failure).
	#>
	[CmdletBinding()]
	[OutputType([System.IO.FileInfo[]])]
	param(
		[Parameter(Mandatory = $true)]
		[string]$WorktreeRoot,

		[string]$PathSegmentFilter
	)

	if (-not (Test-Path -LiteralPath $WorktreeRoot)) {
		return @()
	}

	# Recurse the WHOLE worktree for *.dll, then keep only those under a bin/ or
	# obj/ path segment — the per-project widening of the old <root>/{bin,obj}
	# roots loop. Fail-open to @() on any enumeration error.
	$dlls = Get-SafeValue {
		Get-ChildItem -LiteralPath $WorktreeRoot -Filter '*.dll' -Recurse -File -ErrorAction Stop |
			Where-Object { $_.FullName -match '[\\/](bin|obj)[\\/]' }
	} @()
	if ($null -eq $dlls) { $dlls = @() }
	$dlls = @($dlls)

	if (-not [string]::IsNullOrEmpty($PathSegmentFilter)) {
		# Turn e.g. 'bin/Debug' (either slash style) into a consecutive-segment
		# regex: [\\/]bin[\\/]Debug[\\/]. This mirrors the pre-existing
		# Get-DllLockers bin/Debug scoping.
		$segments = @($PathSegmentFilter -split '[\\/]+' | Where-Object { $_ -ne '' })
		$pattern = '[\\/]' + ($segments -join '[\\/]') + '[\\/]'
		$dlls = @($dlls | Where-Object { $_.FullName -match $pattern })
	}

	# Emit the FileInfo objects directly; every caller re-wraps with @(...), so a
	# single-element unwrap is harmless and an empty result yields nothing (NOT a
	# one-element array containing @(), which the ,$dlls comma-operator would).
	return $dlls
}

function Remove-PoisonedArtifacts {
	<#
	.SYNOPSIS
	  Targeted sweep that quarantines (deletes) 0-byte / truncated-PE *.dll
	  artifacts left behind by a crashed build, under BOTH bin/ and obj/.

	.DESCRIPTION
	  Locked Decision 3 (docs/bugs/build-queue-no-artifact-or-process-hygiene-on-crash):
	  a crashed build can leave a 0-byte or truncated *.dll in the worktree's
	  bin/ and obj/ trees. MSBuild's timestamp-based incremental up-to-date
	  check then treats the poisoned artifact as current, causing CS0009 /
	  CS0234 on the next build. This is a TARGETED sweep, not a blanket
	  force-clean — it only removes *.dll files that are provably poisoned.

	  A *.dll is classified poisoned when EITHER:
	    (a) it is 0 bytes, OR
	    (b) it is nonzero length but its first 2 bytes are not the 'MZ'
	        (0x4D 0x5A) DOS-header magic — i.e. not a valid PE image. This
	        cheap 2-byte probe (NOT a full PE/CLI-header parse) is the
	        agreed-upon check resolving SPEC Open Question 2.

	  Both bin/ and obj/ are swept recursively under $WorktreeRoot; a root
	  that does not exist (e.g. a fresh worktree with no obj/ yet) is
	  skipped rather than treated as an error.

	  Per-file fail-open: a delete failure (locked/read-only file) logs a
	  Write-Warning and the sweep continues — it never aborts or throws.

	.PARAMETER WorktreeRoot
	  Root directory of the worktree to sweep (bin/ and obj/ are resolved
	  underneath it).

	.OUTPUTS
	  [string[]] absolute paths of the *.dll files that were successfully
	  deleted (quarantined). Empty array when nothing was poisoned or
	  neither root exists.
	#>
	[CmdletBinding()]
	[OutputType([string[]])]
	param(
		[Parameter(Mandatory = $true)]
		[string]$WorktreeRoot
	)

	$quarantined = New-Object System.Collections.Generic.List[string]

	# Per-project sweep: enumerate *.dll across EVERY project subdir's bin/ and
	# obj/ via the shared Get-ProjectDlls enumerator (no path filter → both bin
	# and obj across all project subdirs and all build configs are swept). This
	# replaces the old <root>/bin + <root>/obj-only roots loop that was blind to
	# a poisoned per-project artifact (Root Cause A of
	# build-queue-false-green-on-silent-build-failure).
	$dlls = @(Get-ProjectDlls -WorktreeRoot $WorktreeRoot)

	foreach ($dll in $dlls) {
			$fullPath = $dll.FullName
			$isPoisoned = $false

			$length = Get-SafeValue { $dll.Length } $null
			if ($null -eq $length) {
				continue
			}

			if ($length -eq 0) {
				$isPoisoned = $true
			} else {
				$hasMzMagic = Get-SafeValue {
					$stream = [System.IO.File]::OpenRead($fullPath)
					try {
						$header = New-Object byte[] 2
						$bytesRead = $stream.Read($header, 0, 2)
						($bytesRead -eq 2 -and $header[0] -eq 0x4D -and $header[1] -eq 0x5A)
					} finally {
						$stream.Dispose()
					}
				} $false

				if ($hasMzMagic -ne $true) {
					$isPoisoned = $true
				}
			}

			if (-not $isPoisoned) {
				continue
			}

			$deleted = Get-SafeValue {
				Remove-Item -LiteralPath $fullPath -Force -ErrorAction Stop
				$true
			} $false

			if ($deleted -eq $true) {
				$quarantined.Add($fullPath)
			} else {
				Write-Warning "Remove-PoisonedArtifacts: failed to delete poisoned artifact '$fullPath'; continuing sweep (fail-open)."
			}
		}

	return [string[]]$quarantined.ToArray()
}

function Set-LockFileAtomic {
	<#
	.SYNOPSIS
	  Atomically writes a lock-file body to disk via a temp-then-move sequence,
	  mirroring the atomic final-write idiom at build-queue.ps1:310-317.

	.DESCRIPTION
	  Writes $Body to $TempPath, then moves it into place at $Path using
	  [System.IO.File]::Replace when $Path already exists (atomic swap-in) or
	  [System.IO.File]::Move when it does not (no destination to replace). On
	  ANY Replace/Move error, falls back to a direct
	  [System.IO.File]::WriteAllText($Path, $Body) and cleans up the temp file.

	.PARAMETER Path
	  Destination lock-file path.

	.PARAMETER Body
	  Lock-file text content to write.

	.PARAMETER TempPath
	  Temp file path to stage the write. Defaults to "$Path.tmp".

	.OUTPUTS
	  [bool] $true on success (by any path), $false fail-open on total failure.
	  Never throws.
	#>
	[CmdletBinding()]
	[OutputType([bool])]
	param(
		[Parameter(Mandatory = $true)]
		[string]$Path,

		[Parameter(Mandatory = $true)]
		[string]$Body,

		[string]$TempPath
	)

	if ([string]::IsNullOrWhiteSpace($TempPath)) {
		$TempPath = "$Path.tmp"
	}

	Get-SafeValue {
		[System.IO.File]::WriteAllText($TempPath, $Body)

		Get-SafeValue {
			if (Test-Path -LiteralPath $Path) {
				[System.IO.File]::Replace($TempPath, $Path, [NullString]::Value)
			} else {
				[System.IO.File]::Move($TempPath, $Path)
			}
		} $null
	} $null

	# Determine success: either the Replace/Move above succeeded (Path now has
	# the body and TempPath is gone), or we need the WriteAllText fallback.
	$movedOk = Get-SafeValue { (Test-Path -LiteralPath $Path) -and -not (Test-Path -LiteralPath $TempPath) } $false

	if ($movedOk -eq $true) {
		return $true
	}

	# Fallback: direct write to destination, then clean up any leftover temp file.
	$fallbackOk = Get-SafeValue {
		[System.IO.File]::WriteAllText($Path, $Body)
		$true
	} $false

	Get-SafeValue { if (Test-Path -LiteralPath $TempPath) { Remove-Item -LiteralPath $TempPath -Force -ErrorAction SilentlyContinue } }

	if ($fallbackOk -ne $true) {
		return $false
	}

	return $true
}

function Get-ActiveLockStatusFromText {
	<#
	.SYNOPSIS
	  Pure classification of build-queue active.lock TEXT into 'alive' | 'dead' |
	  'unknown'. File-absence ('absent') is the CALLER's responsibility, not this
	  function's — it only ever sees text that was already read from disk.

	.DESCRIPTION
	  Parses $Text as JSON. Unparseable / empty / whitespace-only / valid-JSON-
	  but-missing-build_pid all classify 'unknown'. A well-formed integer
	  build_pid is probed via $IsPidAlive: probe $true -> 'alive', probe $false
	  -> 'dead'. If invoking the probe itself throws, this fails safe to 'alive'
	  (matches Test-PidAlive's "fail safe to alive" bias in build-queue.ps1:51-62)
	  — better to over-wait than to wrongly reclaim a live holder's lock.

	.PARAMETER Text
	  Raw text read from active.lock (may be malformed/truncated).

	.PARAMETER IsPidAlive
	  Scriptblock taking one int param, returning $true/$false for pid liveness.

	.OUTPUTS
	  [string] one of 'alive' | 'dead' | 'unknown'. Never throws.
	#>
	[CmdletBinding()]
	[OutputType([string])]
	param(
		[AllowEmptyString()]
		[string]$Text,

		[Parameter(Mandatory = $true)]
		[scriptblock]$IsPidAlive
	)

	$result = Get-SafeValue {
		if ([string]::IsNullOrWhiteSpace($Text)) {
			return 'unknown'
		}

		$data = Get-SafeValue { $Text | ConvertFrom-Json } $null
		if ($null -eq $data) {
			return 'unknown'
		}

		$buildPid = Get-SafeValue {
			$v = $data | Select-Object -ExpandProperty build_pid -ErrorAction SilentlyContinue
			if ($null -ne $v) { [int]$v } else { $null }
		} $null

		if ($null -eq $buildPid) {
			return 'unknown'
		}

		$isAlive = Get-SafeValue { & $IsPidAlive $buildPid } $null
		if ($null -eq $isAlive) {
			# The probe threw (Get-SafeValue swallowed it) - fail safe to alive.
			return 'alive'
		}

		if ($isAlive -eq $true) { return 'alive' }
		return 'dead'
	} 'unknown'

	if ([string]::IsNullOrWhiteSpace($result)) {
		return 'unknown'
	}

	return $result
}

function Test-ShouldReclaimLock {
	<#
	.SYNOPSIS
	  Decides whether the build-queue should reclaim (delete) a stale active.lock,
	  based on a bounded observation history and lowest-seq gating.

	.DESCRIPTION
	  Returns $true iff $IsLowestSeq is $true AND $Observations contains at least
	  $StaleThreshold CONSECUTIVE 'dead' entries (checked at the trailing end of
	  the sequence — i.e. the most recent run of consecutive 'dead' observations
	  must meet or exceed the threshold). Any non-'dead' entry ('unknown',
	  'alive', 'absent') resets the consecutive-dead run to zero.

	.PARAMETER Observations
	  Ordered array of prior Get-ActiveLockStatus(FromText) results (oldest first).

	.PARAMETER StaleThreshold
	  Minimum consecutive 'dead' observations required to reclaim.

	.PARAMETER IsLowestSeq
	  Whether the calling waiter holds the lowest live seq (only the lowest-seq
	  waiter is allowed to reclaim).

	.OUTPUTS
	  [bool]. Fails open to $false on bad/malformed input. Never throws.
	#>
	[CmdletBinding()]
	[OutputType([bool])]
	param(
		[string[]]$Observations,

		[int]$StaleThreshold,

		[bool]$IsLowestSeq
	)

	$result = Get-SafeValue {
		if ($IsLowestSeq -ne $true) {
			return $false
		}
		if ($StaleThreshold -le 0) {
			return $false
		}
		if ($null -eq $Observations -or @($Observations).Count -eq 0) {
			return $false
		}

		$consecutiveDead = 0
		foreach ($obs in @($Observations)) {
			if ($obs -eq 'dead') {
				$consecutiveDead++
			} else {
				$consecutiveDead = 0
			}
		}

		return ($consecutiveDead -ge $StaleThreshold)
	} $false

	if ($result -ne $true) {
		return $false
	}

	return $true
}

function Get-DllLockers {
	<#
	.SYNOPSIS
	  Enumerate the processes holding an open handle on any of the worktree's
	  bin/Debug/**/*.dll artifacts, via the Windows Restart Manager API.

	.DESCRIPTION
	  The intermittent MSB3027 copy-lock failures at the START of a build are
	  caused by a leftover process (a hung testhost/dotnet from a prior run, an
	  editor, a file indexer) still holding a handle on an output DLL, so the
	  next build's copy-to-output step cannot overwrite it. This function names
	  those lockers so the caller (Stop-DllLockers) can reap the in-worktree ones
	  BEFORE the copy step runs.

	  It uses the Restart Manager (rstrtmgr.dll): RmStartSession →
	  RmRegisterResources(the dll paths) → RmGetList (called twice — once to size
	  pnProcInfoNeeded, then to fill the RM_PROCESS_INFO[] buffer) →
	  RmEndSession. Each affected RM_PROCESS_INFO is mapped to a locker record.

	  Only DLLs under <WorktreeRoot>/**/bin/Debug are considered — mirroring how
	  Remove-PoisonedArtifacts scopes its sweep under the worktree. A worktree
	  with no such DLLs (fresh checkout) yields an empty list.

	  The ENTIRE body is wrapped in Get-SafeValue so ANY Restart-Manager /
	  P/Invoke error fails OPEN to an empty list — a build must proceed even if
	  locker enumeration is impossible (non-Windows host, missing rstrtmgr.dll,
	  access denied). Enumeration failing OPEN can only miss a reap, never abort
	  a build.

	.PARAMETER WorktreeRoot
	  Root directory of the worktree; bin/Debug DLLs are resolved underneath it.

	.OUTPUTS
	  An array of locker records @( @{ pid = [int]; name = [string];
	  path = [string] } ). Empty array when there are no DLLs, no lockers, or on
	  any failure (fail-open).
	#>
	[CmdletBinding()]
	[OutputType([object[]])]
	param(
		[Parameter(Mandatory = $true)]
		[string]$WorktreeRoot
	)

	$result = Get-SafeValue {
		if (-not ([System.Management.Automation.PSTypeName]'BuildQueueHygiene.NativeMethods').Type) {
			throw 'BuildQueueHygiene.NativeMethods type unavailable (non-Windows host or Add-Type failure).'
		}

		if (-not (Test-Path -LiteralPath $WorktreeRoot)) {
			return @()
		}

		# Collect every bin/Debug/**/*.dll across ALL project subdirs beneath the
		# worktree (<root>/**/bin/Debug) via the shared per-project enumerator.
		# This is the per-project widening that makes this function's docstring
		# "mirroring how Remove-PoisonedArtifacts scopes its sweep" claim true —
		# both now share ONE enumeration (Root Cause A / DLL-locker-sweep parity).
		$dllPaths = @(Get-ProjectDlls -WorktreeRoot $WorktreeRoot -PathSegmentFilter 'bin/Debug' | ForEach-Object { $_.FullName })
		if ($dllPaths.Count -eq 0) {
			return @()
		}

		$sessionHandle = [uint32]0
		$sessionKey = ([guid]::NewGuid().ToString('N'))  # 32-char hex, CCH_RM_SESSION_KEY

		$startRc = [BuildQueueHygiene.NativeMethods]::RmStartSession([ref]$sessionHandle, 0, $sessionKey)
		if ($startRc -ne 0) {
			throw "RmStartSession failed (rc=$startRc)."
		}

		try {
			$regRc = [BuildQueueHygiene.NativeMethods]::RmRegisterResources(
				$sessionHandle,
				[uint32]$dllPaths.Count,
				[string[]]$dllPaths,
				[uint32]0, [IntPtr]::Zero,
				[uint32]0, $null)
			if ($regRc -ne 0) {
				throw "RmRegisterResources failed (rc=$regRc)."
			}

			$procInfoNeeded = [uint32]0
			$procInfo = [uint32]0
			$rebootReasons = [uint32]0

			# First call: size the buffer (pnProcInfo = 0 → RmGetList reports needed).
			$sizeRc = [BuildQueueHygiene.NativeMethods]::RmGetList(
				$sessionHandle,
				[ref]$procInfoNeeded,
				[ref]$procInfo,
				$null,
				[ref]$rebootReasons)

			# rc 0 with 0 needed → no lockers. ERROR_MORE_DATA → allocate & refill.
			if ($sizeRc -eq 0 -and $procInfoNeeded -eq 0) {
				return @()
			}
			if ($sizeRc -ne [BuildQueueHygiene.NativeMethods]::ERROR_MORE_DATA -and $sizeRc -ne 0) {
				throw "RmGetList (sizing) failed (rc=$sizeRc)."
			}
			if ($procInfoNeeded -eq 0) {
				return @()
			}

			$affected = New-Object BuildQueueHygiene.RM_PROCESS_INFO[] $procInfoNeeded
			$procInfo = [uint32]$procInfoNeeded

			$fillRc = [BuildQueueHygiene.NativeMethods]::RmGetList(
				$sessionHandle,
				[ref]$procInfoNeeded,
				[ref]$procInfo,
				$affected,
				[ref]$rebootReasons)
			if ($fillRc -ne 0) {
				throw "RmGetList (fill) failed (rc=$fillRc)."
			}

			$lockers = New-Object System.Collections.Generic.List[object]
			for ($i = 0; $i -lt $procInfo; $i++) {
				$info = $affected[$i]
				$lockers.Add([ordered]@{
					pid  = [int]$info.Process.dwProcessId
					name = [string]$info.strAppName
					path = [string]$WorktreeRoot
				})
			}
			return @($lockers.ToArray())
		} finally {
			[void](Get-SafeValue { [BuildQueueHygiene.NativeMethods]::RmEndSession($sessionHandle) })
		}
	} @()

	if ($null -eq $result) { $result = @() }
	return @($result)
}

function Stop-DllLockers {
	<#
	.SYNOPSIS
	  Terminate the in-worktree processes that Get-DllLockers reports as holding
	  a handle on the worktree's bin/Debug/**/*.dll, clearing the copy-lock BEFORE
	  the build's copy step. EXCLUDES the VBCSCompiler shared server by name.

	.DESCRIPTION
	  Kills ONLY the lockers Get-DllLockers returned for THIS worktree — it never
	  performs a global process-name kill and never touches an out-of-worktree
	  process (Locked Decision 2: build-tree processes are reaped by membership,
	  not by a name glob, so a sibling worktree's live build is never torn down).

	  VBCSCompiler (the Roslyn shared compiler server) is EXEMPT by name
	  (case-insensitive) — Locked Decision 1: it is recycled via the sanctioned
	  Reset-CompilerServer path, never reaped here.

	  Each Stop-Process is wrapped in Get-SafeValue so a per-process failure
	  (already exited, access denied) is swallowed and the reap continues.

	.PARAMETER WorktreeRoot
	  Root directory of the worktree whose lockers should be reaped.

	.OUTPUTS
	  An [int[]] of the PIDs that were reaped. Empty array when there were no
	  lockers, all lockers were VBCSCompiler, or on any failure (fail-open).
	#>
	[CmdletBinding()]
	[OutputType([int[]])]
	param(
		[Parameter(Mandatory = $true)]
		[string]$WorktreeRoot
	)

	$result = Get-SafeValue {
		$lockers = @(Get-DllLockers -WorktreeRoot $WorktreeRoot)
		if ($lockers.Count -eq 0) {
			return @()
		}

		$reaped = New-Object System.Collections.Generic.List[int]
		foreach ($locker in $lockers) {
			$lockerPid = [int]$locker.pid
			$lockerName = [string]$locker.name

			# Locked Decision 1: never reap the shared VBCSCompiler server here.
			if ($lockerName -and $lockerName -match '(?i)VBCSCompiler') {
				continue
			}

			$killed = Get-SafeValue {
				Stop-Process -Id $lockerPid -Force -ErrorAction Stop
				$true
			} $false

			if ($killed -eq $true) {
				$reaped.Add($lockerPid)
			}
		}

		return @($reaped.ToArray())
	} @()

	if ($null -eq $result) { $result = @() }
	return [int[]]@($result)
}

function Test-BuildLogFailure {
	<#
	.SYNOPSIS
	  Pure scan of a captured build log for known MSBuild failure signatures —
	  the testable half of overriding a bogus exit 0 from a queued build.

	.DESCRIPTION
	  A queued build can exit 0 while the captured console output actually
	  shows a failure (e.g. seq-346: VBCSCompiler-poisoned copy retries that
	  MSBuild reports as errors but the outer process still exits success).
	  This function scans the log text for that failure shape so a caller can
	  override a bogus success exit code with the real verdict.

	  Signature set (checked in this order; the FIRST match wins and is
	  reported as $result.signature):
	    - literal 'Build FAILED'
	    - literal 'error MSB3027'
	    - literal 'error MSB3021'
	    - a '<N> Error(s)' line where N > 0

	  Pure function: no file I/O, no process calls, no side effects. The
	  entire body is wrapped in Get-SafeValue so a malformed/unexpected input
	  fails OPEN to a non-failure result rather than throwing.

	.PARAMETER Log
	  The captured build log, either as a single [string] (may contain
	  embedded newlines) or a [string[]] of lines. $null / empty / a
	  non-string value are all tolerated and fail open to non-failure.

	.OUTPUTS
	  A hashtable @{ failed = [bool]; signature = [string] or $null }.
	#>
	[CmdletBinding()]
	[OutputType([hashtable])]
	param(
		$Log
	)

	$benignResult = [ordered]@{ failed = $false; signature = $null }

	return Get-SafeValue {
		if ($null -eq $Log) {
			return [ordered]@{ failed = $false; signature = $null }
		}

		if ($Log -is [string]) {
			$lines = $Log -split "`r`n|`n|`r"
		} elseif ($Log -is [array]) {
			$lines = @($Log) | ForEach-Object { [string]$_ }
		} else {
			# Non-string, non-array input (e.g. an int) — fail open.
			return [ordered]@{ failed = $false; signature = $null }
		}

		$errorCountPattern = '(\d+)\s+Error\(s\)'

		foreach ($line in $lines) {
			if ($null -eq $line) { continue }

			if ($line -match 'Build FAILED') {
				return [ordered]@{ failed = $true; signature = 'Build FAILED' }
			}
			if ($line -match 'error MSB3027') {
				return [ordered]@{ failed = $true; signature = 'error MSB3027' }
			}
			if ($line -match 'error MSB3021') {
				return [ordered]@{ failed = $true; signature = 'error MSB3021' }
			}
			if ($line -match $errorCountPattern) {
				$count = [int]$Matches[1]
				if ($count -gt 0) {
					return [ordered]@{ failed = $true; signature = $Matches[0] }
				}
			}
		}

		return [ordered]@{ failed = $false; signature = $null }
	} $benignResult
}

function Format-BuildQueueBanner {
	<#
	.SYNOPSIS
	  Composes a single-line build-queue outcome banner string — RESULT,
	  test counts, result-fidelity, and (on any non-PASS result) a stable
	  next-action hint.

	.DESCRIPTION
	  Pure, side-effect-free string formatting: no filesystem/process access,
	  never throws (even on $null counts or $null/empty fidelity strings).

	  RESULT precedence (checked in this order):
	    1. NO-TESTS-MATCHED  when $ResultFidelity -eq 'no-tests-matched'
	    2. FAIL              when $ExitCode -ne 0 OR $BuildFidelity -eq
	                          'log-failure-override'
	    3. PASS              otherwise

	  A non-PASS RESULT appends exactly one next-action suffix:
	    - NO-TESTS-MATCHED -> "widen the filter and retry"
	    - FAIL, build_fidelity no-output -> "build produced no output; delete obj/bin and rebuild"
	    - FAIL, exit code 4 -> "rebuild (stale DLL)"
	    - FAIL, otherwise    -> "read logs/<Seq>.build.err.log"

	.PARAMETER Seq
	  The build-queue sequence number for this build.

	.PARAMETER Op
	  The queued operation name (e.g. msbuild, mstest, nxbuild, nxtest).

	.PARAMETER ExitCode
	  The build/test process exit code.

	.PARAMETER ResultFidelity
	  The result-fidelity classification (e.g. verified, no-tests-matched).

	.PARAMETER BuildFidelity
	  The build-fidelity classification (e.g. verified, log-failure-override,
	  no-output).

	.PARAMETER Counts
	  Optional hashtable with keys 'passed'/'failed'/'total'. Any key (or the
	  whole hashtable) may be $null; a $null/missing 'total' omits the
	  tests=/failed= segment entirely.

	.OUTPUTS
	  [string] a single-line banner. Never throws.
	#>
	[CmdletBinding()]
	[OutputType([string])]
	param(
		[int]$Seq,
		[string]$Op,
		[int]$ExitCode,
		[string]$ResultFidelity,
		[string]$BuildFidelity,
		[hashtable]$Counts
	)

	$result = Get-SafeValue {
		$resultLabel = if ($ResultFidelity -eq 'no-tests-matched') {
			'NO-TESTS-MATCHED'
		} elseif ($ExitCode -ne 0 -or $BuildFidelity -eq 'log-failure-override') {
			'FAIL'
		} else {
			'PASS'
		}

		$banner = "build-queue: seq=$Seq op=$Op RESULT=$resultLabel"

		$total = $null
		if ($null -ne $Counts) {
			$total = Get-SafeValue { $Counts['total'] } $null
		}
		if ($null -ne $total) {
			$failed = Get-SafeValue { $Counts['failed'] } $null
			if ($null -eq $failed) {
				$failed = 0
			}
			$banner += " tests=$total failed=$failed"
		}

		$banner += " (result_fidelity=$ResultFidelity)"

		if ($resultLabel -ne 'PASS') {
			$nextAction = if ($resultLabel -eq 'NO-TESTS-MATCHED') {
				'widen the filter and retry'
			} elseif ($BuildFidelity -eq 'no-output') {
				'build produced no output; delete obj/bin and rebuild'
			} elseif ($ExitCode -eq 4) {
				'rebuild (stale DLL)'
			} else {
				"read logs/$Seq.build.err.log"
			}
			$banner += " -> $nextAction"
		}

		$banner
	} $null

	if ($null -eq $result) {
		Write-Warning 'Format-BuildQueueBanner: failed to compose banner; returning a benign fallback (fail-open).'
		return "build-queue: seq=$Seq op=$Op RESULT=UNKNOWN (result_fidelity=$ResultFidelity)"
	}

	return [string]$result
}
