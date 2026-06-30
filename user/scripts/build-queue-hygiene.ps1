<#
.SYNOPSIS
  Build-queue process hygiene helpers — Windows Job-Object lifecycle.

.DESCRIPTION
  Dot-sourceable module that owns the Windows Job-Object lifecycle so a build
  runner can scope and reap exactly one build's descendant process tree.

  This is the shared home for build-queue hygiene helpers. Later work units
  add more functions here (artifact sweep, result fidelity, etc.) — this
  revision adds the Job-Object surface plus the VBCSCompiler recycle:

    New-BuildJobObject     - create a kill-on-close Job Object
    Add-ProcessToBuildJob  - assign a process to a Job Object
    Stop-BuildJobTree      - terminate the Job Object (and all members)
    Reset-CompilerServer   - force-recycle VBCSCompiler after a queued build

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

    public static class NativeMethods
    {
        public const uint JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x00002000;
        public const int JobObjectExtendedLimitInformation = 9;

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
	  docs/bugs/build-queue-no-artifact-or-process-hygiene-on-crash). It is
	  safe ONLY because the build queue serializes builds machine-wide — by
	  the time a build finishes, no other queued build's compiler server can
	  be mid-use, so recycling it never tears down a concurrent build. This
	  is a narrow, deliberate exception to Locked Decision 2's no-global-
	  process-kill rule (see New-BuildJobObject/Stop-BuildJobTree above),
	  and it must stay scoped to this one compiler-server process. It must
	  NEVER be widened to the build-tree process family (the SDK CLI host,
	  the test host, or the MSBuild host process) — those remain reaped
	  exclusively via Job-Object membership per Locked Decision 2, never by
	  matching their process name.

	.OUTPUTS
	  [bool] $true if a recycle action was taken/succeeded, $false otherwise
	  (fail-open — never throws).
	#>
	[CmdletBinding()]
	[OutputType([bool])]
	param()

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
