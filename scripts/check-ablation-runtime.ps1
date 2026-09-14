[CmdletBinding()]
param(
    [switch]$Start,
    [ValidateRange(5, 300)]
    [int]$WaitSeconds = 120,
    [string[]]$Containers = @(
        "doppel-ablation-pgvector",
        "memo-echo-neo4j"
    )
)

$ErrorActionPreference = "Stop"

function Get-DockerServerName {
    # A broken Desktop pipe can make `docker version` hang instead of returning an
    # error. Use a private, no-window process so every read-only probe has its own
    # hard deadline and Windows PowerShell 5 cannot promote native stderr to a
    # terminating ErrorRecord.
    $dockerCommand = Get-Command docker -ErrorAction Stop
    $probe = New-Object System.Diagnostics.Process
    $probe.StartInfo = New-Object System.Diagnostics.ProcessStartInfo
    $probe.StartInfo.FileName = $dockerCommand.Source
    $probe.StartInfo.Arguments = 'version --format "{{.Server.Platform.Name}}"'
    $probe.StartInfo.UseShellExecute = $false
    $probe.StartInfo.CreateNoWindow = $true
    $probe.StartInfo.RedirectStandardOutput = $true
    $probe.StartInfo.RedirectStandardError = $true
    try {
        if (-not $probe.Start()) {
            return ""
        }
        if (-not $probe.WaitForExit(2000)) {
            $probe.Kill()
            $probe.WaitForExit()
            return ""
        }
        $name = $probe.StandardOutput.ReadToEnd().Trim()
        if ($probe.ExitCode -ne 0) {
            return ""
        }
        return [string]$name
    }
    finally {
        $probe.Dispose()
    }
}

function Wait-DockerServer {
    param(
        [int]$TimeoutSeconds,
        [System.Diagnostics.Process]$StartProcess = $null
    )

    $deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
    do {
        $name = Get-DockerServerName
        if ($name) {
            return $name
        }
        if (
            $null -ne $StartProcess -and
            $StartProcess.HasExited -and
            $StartProcess.ExitCode -ne 0
        ) {
            throw "Docker Desktop start command failed with exit code $($StartProcess.ExitCode)."
        }
        Start-Sleep -Seconds 2
    } while ([DateTime]::UtcNow -lt $deadline)
    throw "Docker Desktop did not become ready within $TimeoutSeconds seconds."
}

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    throw "Docker CLI was not found on PATH."
}

$serverName = Get-DockerServerName
if (-not $serverName) {
    if (-not $Start) {
        throw "Docker Desktop is not ready. Re-run with -Start to start it safely."
    }
    $dockerCommand = Get-Command docker -ErrorAction Stop
    $startProcess = Start-Process `
        -FilePath $dockerCommand.Source `
        -ArgumentList @("desktop", "start") `
        -PassThru `
        -WindowStyle Hidden
    try {
        $serverName = Wait-DockerServer `
            -TimeoutSeconds $WaitSeconds `
            -StartProcess $startProcess
    }
    finally {
        if ($null -ne $startProcess -and -not $startProcess.HasExited) {
            Stop-Process -Id $startProcess.Id -Force -ErrorAction SilentlyContinue
        }
    }
}

$rows = foreach ($container in $Containers) {
    & docker container inspect $container *> $null
    if ($LASTEXITCODE -ne 0) {
        [PSCustomObject]@{
            Container = $container
            Status = "missing"
            Health = "unknown"
            RestartPolicy = "unknown"
        }
        continue
    }

    $state = & docker inspect --format `
        "{{.State.Status}}|{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}|{{.HostConfig.RestartPolicy.Name}}" `
        $container
    if ($LASTEXITCODE -ne 0) {
        throw "Could not inspect container $container."
    }
    $parts = $state -split "\|", 3
    if ($Start -and $parts[0] -ne "running") {
        & docker start $container | Out-Null
        if ($LASTEXITCODE -ne 0) {
            throw "Could not start container $container."
        }
        $state = & docker inspect --format `
            "{{.State.Status}}|{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}|{{.HostConfig.RestartPolicy.Name}}" `
            $container
        $parts = $state -split "\|", 3
    }
    if (
        $Start -and
        ($parts[0] -ne "running" -or $parts[1] -notin @("healthy", "none"))
    ) {
        $deadline = [DateTime]::UtcNow.AddSeconds($WaitSeconds)
        do {
            $state = & docker inspect --format `
                "{{.State.Status}}|{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}|{{.HostConfig.RestartPolicy.Name}}" `
                $container
            $parts = $state -split "\|", 3
            if ($parts[0] -eq "running" -and $parts[1] -in @("healthy", "none")) {
                break
            }
            Start-Sleep -Seconds 2
        } while ([DateTime]::UtcNow -lt $deadline)
    }

    [PSCustomObject]@{
        Container = $container
        Status = $parts[0]
        Health = $parts[1]
        RestartPolicy = $parts[2]
    }
}

$dataDisk = Join-Path $env:LOCALAPPDATA "Docker\wsl\disk\docker_data.vhdx"
Write-Output "Docker server: $serverName"
Write-Output "Docker data disk present: $(Test-Path -LiteralPath $dataDisk)"
Write-Output "Docker data disk: $dataDisk"
$rows | Format-Table -AutoSize

if ($rows | Where-Object { $_.Status -ne "running" -or $_.Health -notin @("healthy", "none") }) {
    throw "One or more benchmark containers are not ready. No Docker data was changed."
}
