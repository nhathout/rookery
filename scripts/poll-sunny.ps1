<#
.SYNOPSIS
    Point the rookery light at a Thousand Sunny crew.

.DESCRIPTION
    Sunny already answers the question -- `python -m jobs.status` prints one
    JSON snapshot with the queue, every crewmate's state, open briefs and
    blockers -- so this only has to ask it on a timer and say which fields
    mean which colour. Nothing needs to change on sunny's side.

      red     a crewmate failed, the last run had failures, the budget cap is
              hit, or a brief is open waiting for you to run it
      green   a task is running right now
      yellow  something to read: a crewmate has news, work is queued, or a
              blocker is listed
      clear   nothing to say

    Two of those are judgement calls rather than obvious mappings, and they
    are the difference between a light you believe and one you learn to
    ignore:

      * `blockers` is yellow, not red. It is non-empty on a healthy system --
        "ANTHROPIC_API_KEY not set" is a deliberate choice, not a fault.
      * `has_news` is yellow, not red. Red is for broken or blocking. If red
        means "sometime this week", you will stop looking at it.

    Leave this running in its own terminal, or wrap it in a scheduled task.
    Ctrl-C clears the source so the light stops claiming to know.

.PARAMETER SunnyRoot
    Where Thousand Sunny lives.

.PARAMETER Every
    Seconds between polls. A snapshot takes about 3s to answer, so 60 costs
    roughly 5% of one core. Sunny's own UI refreshes every 20s.

.EXAMPLE
    .\scripts\poll-sunny.ps1
    .\scripts\poll-sunny.ps1 -Every 30 -SunnyRoot D:\dev\sunny
#>
[CmdletBinding()]
param(
    [string]$SunnyRoot = "C:\dev\sunny",
    [int]$Every = 60,
    [string]$Source = "sunny",
    [string]$HttpHost = "127.0.0.1",
    [int]$HttpPort = 8787
)

$ErrorActionPreference = "Stop"

$python = Join-Path $SunnyRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    Write-Error "No venv at $python. Point -SunnyRoot at your sunny checkout."
}

# `cd /d` so the poll works whatever directory you started it from: sunny
# resolves config and logs relative to its own root.
$command = "cd /d `"$SunnyRoot`" && `"$python`" -m jobs.status"

Write-Host "Watching $SunnyRoot every ${Every}s -> $HttpHost`:$HttpPort" -ForegroundColor Cyan

rookery poll `
    --source $Source --every $Every --json `
    --http-host $HttpHost --http-port $HttpPort `
    --command $command `
    --needs-you-if 'crew[*].state==failed' `
    --needs-you-if 'last_run.failed>0' `
    --needs-you-if 'budget.cap_reached' `
    --needs-you-if 'briefs.open>0' `
    --working-if   'queue.running>0' `
    --idle-if      'crew[*].state==has_news' `
    --idle-if      'queue.queued>0' `
    --idle-if      'blockers'
