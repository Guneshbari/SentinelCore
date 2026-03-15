# ============================================================
# SentinelCore Deployment Script
# Run this in PowerShell AS ADMINISTRATOR on each target machine
# ============================================================
#
# This script:
# 1. Installs Python dependencies
# 2. Resets checkpoint for fresh collection
# 3. Registers SentinelCore as a Windows Scheduled Task
#    that runs at system startup with SYSTEM privileges
#
# Usage:
#   Open PowerShell as Administrator, then:
#   cd C:\ProgramData\LogCollector
#   .\deploy_startup.ps1
#
# To uninstall:
#   Unregister-ScheduledTask -TaskName "SentinelCore" -Confirm:$false
# ============================================================

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$PythonExe = (Get-Command python -ErrorAction SilentlyContinue).Path
$CollectorScript = Join-Path $ScriptDir "src\collector.py"

Write-Host "============================================" -ForegroundColor Cyan
Write-Host "  SentinelCore Deployment Script" -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan

# --- Check Admin ---
$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
    Write-Host ""
    Write-Host "ERROR: This script must be run as Administrator!" -ForegroundColor Red
    Write-Host "  Right-click PowerShell -> Run as Administrator" -ForegroundColor Yellow
    exit 1
}

# --- Check Python ---
if (-not $PythonExe) {
    Write-Host "ERROR: Python not found in PATH!" -ForegroundColor Red
    Write-Host "  Install Python 3.9+ from https://python.org" -ForegroundColor Yellow
    exit 1
}

Write-Host ""
Write-Host "Python:   $PythonExe" -ForegroundColor Green
Write-Host "Script:   $CollectorScript" -ForegroundColor Green
Write-Host "WorkDir:  $ScriptDir" -ForegroundColor Green
Write-Host ""

# --- Step 1: Install Dependencies ---
Write-Host "[1/4] Installing Python dependencies..." -ForegroundColor Yellow
& $PythonExe -m pip install -r (Join-Path $ScriptDir "requirements.txt") --quiet 2>&1 | Out-Null
Write-Host "  Done." -ForegroundColor Green

# --- Step 2: Validate ---
Write-Host "[2/4] Running validation..." -ForegroundColor Yellow
& $PythonExe (Join-Path $ScriptDir "tests\validate_collector.py") 2>&1 | Out-Null
if ($LASTEXITCODE -eq 0) {
    Write-Host "  Validation PASSED." -ForegroundColor Green
} else {
    Write-Host "  Validation FAILED. Fix issues before deploying." -ForegroundColor Red
    exit 1
}

# --- Step 3: Reset Checkpoint (optional) ---
Write-Host "[3/4] Resetting checkpoint..." -ForegroundColor Yellow
$checkpointFile = Join-Path $ScriptDir "checkpoint.json"
if (Test-Path $checkpointFile) {
    Remove-Item $checkpointFile -Force
    Write-Host "  Checkpoint reset for fresh collection." -ForegroundColor Green
} else {
    Write-Host "  No existing checkpoint." -ForegroundColor Green
}

# --- Step 4: Register Scheduled Task ---
Write-Host "[4/4] Registering Scheduled Task..." -ForegroundColor Yellow

$TaskName = "SentinelCore"

# Remove existing task if present
$existingTask = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if ($existingTask) {
    Write-Host "  Removing existing task..." -ForegroundColor Yellow
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
}

# Create the task action
$Action = New-ScheduledTaskAction `
    -Execute $PythonExe `
    -Argument "`"$CollectorScript`"" `
    -WorkingDirectory $ScriptDir

# Trigger: At system startup
$Trigger = New-ScheduledTaskTrigger -AtStartup

# Settings
$Settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -RestartCount 3 `
    -RestartInterval (New-TimeSpan -Minutes 1) `
    -ExecutionTimeLimit (New-TimeSpan -Days 365)

# Register with SYSTEM account (highest privileges)
Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $Action `
    -Trigger $Trigger `
    -Settings $Settings `
    -User "SYSTEM" `
    -RunLevel Highest `
    -Description "SentinelCore Windows Telemetry Agent - Collects system events for fault diagnosis and ML training" | Out-Null

Write-Host "  Scheduled Task registered: $TaskName" -ForegroundColor Green

# --- Summary ---
Write-Host ""
Write-Host "============================================" -ForegroundColor Cyan
Write-Host "  DEPLOYMENT COMPLETE" -ForegroundColor Green
Write-Host "============================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "SentinelCore will start automatically on boot." -ForegroundColor White
Write-Host ""
Write-Host "Useful commands:" -ForegroundColor Yellow
Write-Host "  Start now:     Start-ScheduledTask -TaskName 'SentinelCore'"
Write-Host "  Stop:          Stop-ScheduledTask -TaskName 'SentinelCore'"
Write-Host "  Status:        Get-ScheduledTask -TaskName 'SentinelCore' | Select State"
Write-Host "  View logs:     Get-Content '$ScriptDir\sentinel.log' -Tail 50"
Write-Host "  Uninstall:     Unregister-ScheduledTask -TaskName 'SentinelCore' -Confirm:`$false"
Write-Host ""
