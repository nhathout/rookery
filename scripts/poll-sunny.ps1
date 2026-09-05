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

    This polls with `--no-probe`, which answers in 0.5s instead of 3.2s. The
    difference is two Ollama round trips for backend health and GPU state.
    `blockers` keeps its key and its shape either way -- sunny is deliberate
    about that, so a light selecting on it cannot have the field vanish --
    it just leaves out the entries that cost a round trip. Since `blockers`
    only ever reaches yellow here, that is not something this light acts on.
    Pass -Probe if you want a dead backend to show up.

    Sunny can also push at run transitions instead of waiting for the next
    poll -- see `beacon` in its config/config.yaml. It reports as a separate
    source (`sunny-run`), so the two run side by side and the most urgent
    wins. docs/integrations.md, recipe A'.

    Leave this running in its own terminal, or wrap it in a scheduled task.
    Ctrl-C clears the source so the light stops claiming to know.

.PARAMETER SunnyRoot
    Where Thousand Sunny lives.

.PARAMETER Every
    Seconds between polls. A --no-probe snapshot takes about 0.5s, so 60
    costs well under 1% of one core. Sunny's own UI refreshes every 20s.

.PARAMETER Probe
    Take the full snapshot, including backend health and GPU state. Costs
    about 3.2s per poll instead of 0.5s.

.EXAMPLE
    .\scripts\poll-sunny.ps1
    .\scripts\poll-sunny.ps1 -Every 30 -SunnyRoot D:\dev\sunny
    .\scripts\poll-sunny.ps1 -Probe -Every 300
#>
[CmdletBinding()]
param(
    [string]$SunnyRoot = "C:\dev\sunny",
    [int]$Every = 60,
    [switch]$Probe,
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
$flag = if ($Probe) { "" } else { " --no-probe" }
$command = "cd /d `"$SunnyRoot`" && `"$python`" -m jobs.status$flag"

$cost = if ($Probe) { "full snapshot" } else { "--no-probe" }
Write-Host "Watching $SunnyRoot every ${Every}s ($cost) -> $HttpHost`:$HttpPort" -ForegroundColor Cyan

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
