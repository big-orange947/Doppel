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
    $name = & docker version --format "{{.Server.Platform.Name}}" 2>$null
    if ($LASTEXITCODE -ne 0) {
        return ""
    }
    return [string]$name
}

function Wait-DockerServer {
    param([int]$TimeoutSeconds)

    $deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
    do {
        $name = Get-DockerServerName
        if ($name) {
            return $name
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
    & docker desktop start | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw "Docker Desktop could not be started by its CLI."
    }
    $serverName = Wait-DockerServer -TimeoutSeconds $WaitSeconds
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
