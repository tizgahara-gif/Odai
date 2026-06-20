param(
    [string]$Project = ".\\src\\SilhouetteLocalDaily\\SilhouetteLocalDaily.csproj",
    [string]$Runtime = "win-x64",
    [string]$Configuration = "Release"
)

$ErrorActionPreference = "Stop"

dotnet publish $Project `
  -c $Configuration `
  -r $Runtime `
  --self-contained true `
  /p:WindowsAppSDKSelfContained=true

Write-Host "Published successfully."
