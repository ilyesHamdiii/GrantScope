param(
    [int]$LookbackDays = 30,
    [int]$MaxObjects = 100,
    [switch]$IncludeBetaServicePrincipalSignIns,
    [switch]$Check
)

$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $ProjectRoot

$ErrorActionPreference = "Stop"

$GraphArguments = @(
    "-m",
    "app.graph_export"
)

if ($Check) {
    $GraphArguments += "--check"
}
else {
    $GraphArguments += @(
        "--lookback-days",
        $LookbackDays,
        "--max-objects",
        $MaxObjects
    )

    if ($IncludeBetaServicePrincipalSignIns) {
        $GraphArguments += "--include-beta-service-principal-signins"
    }
}

docker compose exec -T api python @GraphArguments