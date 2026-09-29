<#
Run the copied FOFEM 6.9.4 batch executable without relying on an installed FOFEM directory.

On a clean Windows machine, copy the repository and the fofem_694 directory, then run:
  powershell -ExecutionPolicy Bypass -File tests/manual/fofem694_no_install_smoke.ps1

If the executable cannot start because the Visual C++ runtime is absent, rerun with
-IncludeRuntimeDlls. Use -AllowInstalledHost only to validate this harness on a
machine where FOFEM 6.9.4 is already installed. If only user data remains after uninstall, use -AllowResidualUserData.
#>
param(
    [string]$BundleDir,
    [switch]$AllowInstalledHost,
    [switch]$AllowResidualUserData,
    [switch]$IncludeRuntimeDlls,
    [switch]$IncludeMortality
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$repoRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..\..')).Path
if (-not $BundleDir) {
    $BundleDir = Join-Path $repoRoot 'src\fuel_analyst\supporting_data\fofem_694'
}
$BundleDir = (Resolve-Path -LiteralPath $BundleDir).Path

if (-not $AllowInstalledHost) {
    $installed = @((Join-Path $env:ProgramFiles 'FOFEM 6.9.4'))
    $programFilesX86 = [Environment]::GetEnvironmentVariable('ProgramFiles(x86)')
    if ($programFilesX86) {
        $installed += Join-Path $programFilesX86 'FOFEM 6.9.4'
    }
    $found = @($installed | Where-Object { Test-Path -LiteralPath $_ })
    if ($found.Count) {
        throw "This host still has a FOFEM 6.9.4 program directory: $($found -join ', ')."
    }
    $residualData = Join-Path $env:LOCALAPPDATA 'FOFEM 6.9.4'
    if (Test-Path -LiteralPath $residualData) {
        if (-not $AllowResidualUserData) {
            throw "FOFEM 6.9.4 user data remains at $residualData. Use -AllowResidualUserData to test the uninstalled program while isolating this folder."
        }
        Write-Warning "Residual FOFEM 6.9.4 user data exists but will not be used: $residualData"
    }
}

$fixture = Join-Path $repoRoot 'tests\test_data\fofem694\burnup_parameters_694.brn'
$required = @('runfofem.exe', 'Emission_Factors.csv')
if ($IncludeRuntimeDlls) {
    $required += @('msvcp140.dll', 'vcruntime140.dll', 'vcruntime140_1.dll')
}
if ($IncludeMortality) {
    $required += 'FOF_SPP.CSV'
}
foreach ($name in $required) {
    if (-not (Test-Path -LiteralPath (Join-Path $BundleDir $name))) {
        throw "Missing required bundle file: $name"
    }
}
if (-not (Test-Path -LiteralPath $fixture)) {
    throw "Missing Burnup parameter fixture: $fixture"
}
$mortalityFixture = Join-Path $repoRoot 'tests\test_data\fofem694\FFI_FOFEM_Sample.tre'
if ($IncludeMortality -and -not (Test-Path -LiteralPath $mortalityFixture)) {
    throw "Missing mortality fixture: $mortalityFixture"
}

$probeRoot = Join-Path $env:TEMP ('FuelAnalyst_fofem694_no_install_' + [guid]::NewGuid().ToString('N'))
$appDir = Join-Path $probeRoot 'app'
$workDir = Join-Path $probeRoot 'work'
$localAppDataDir = Join-Path $probeRoot 'local_app_data'
New-Item -ItemType Directory -Path $appDir, $workDir, $localAppDataDir | Out-Null

foreach ($name in $required) {
    Copy-Item -LiteralPath (Join-Path $BundleDir $name) -Destination (Join-Path $appDir $name)
}
Copy-Item -LiteralPath $fixture -Destination (Join-Path $workDir 'Burnup-Params.brn')
if ($IncludeMortality) {
    Copy-Item -LiteralPath $mortalityFixture -Destination (Join-Path $workDir 'FFI_FOFEM_Sample.tre')
}

$originalPath = $env:PATH
$originalData = $env:FOFEM_DATA
$originalLocalAppData = $env:LOCALAPPDATA
try {
    $env:PATH = $appDir + ';' + ((@($originalPath -split ';') | Where-Object { $_ -and ($_ -notmatch 'FOFEM') }) -join ';')
    $env:FOFEM_DATA = $appDir
    $env:LOCALAPPDATA = $localAppDataDir

    $baseRow = 'PlotSmoke,1,1,1,10,1,0.25,0.25,0.25,0.25,0,0,0,0,10,1,40,0.5,0,0,0,0,1,InteriorWest,PN,Summer,Natural'
    $equations = ',-1,-1,-1,-1,-1,-1'
    $cases = @(
        @{ Name = 'consumption'; Mode = '0'; Row = $baseRow + $equations; HeaderCount = 80; UnitsCount = 74 },
        @{ Name = 'soil'; Mode = '1'; Row = $baseRow + ',Loamy-Skeletal,10,20' + $equations; HeaderCount = 86; UnitsCount = 80 }
    )

    foreach ($case in $cases) {
        $inputPath = Join-Path $workDir ($case.Name + '-in.txt')
        $outputPath = Join-Path $workDir ($case.Name + '-out.csv')
        $errorPath = Join-Path $workDir ($case.Name + '-err.txt')
        Set-Content -LiteralPath $inputPath -Encoding Ascii -Value @(
            '#1k-SizeClass',
            '#ConsumptionEquation',
            '#BurnUpFile Burnup-Params.brn',
            '#PlotId,Litter',
            $case.Row
        )

        & (Join-Path $appDir 'runfofem.exe') $case.Mode $inputPath $outputPath $errorPath | Out-Null
        if ($LASTEXITCODE -ne 0) {
            throw "$($case.Name) runfofem.exe exited with code $LASTEXITCODE. Output directory: $workDir"
        }
        if (-not (Test-Path -LiteralPath $outputPath) -or -not (Test-Path -LiteralPath $errorPath)) {
            throw "$($case.Name) did not produce output and error files. Output directory: $workDir"
        }
        $lines = @(Get-Content -LiteralPath $outputPath)
        if ($lines.Count -ne 3) {
            throw "$($case.Name) produced $($lines.Count) output lines; expected two headers and one plot. Output directory: $workDir"
        }
        $counts = @($lines | ForEach-Object { ($_ -split ',').Count })
        if ($counts[0] -ne $case.HeaderCount -or $counts[1] -ne $case.UnitsCount -or $counts[2] -ne $case.HeaderCount) {
            throw "$($case.Name) output column counts $($counts -join '/') differ from expected $($case.HeaderCount)/$($case.UnitsCount)/$($case.HeaderCount). Output directory: $workDir"
        }
        if ($lines[2] -notmatch '^"PlotSmoke",') {
            throw "$($case.Name) output does not contain PlotSmoke. Output directory: $workDir"
        }
        $errors = @(Get-Content -LiteralPath $errorPath | Select-Object -Skip 4 | Where-Object { $_.Trim() })
        if ($errors.Count) {
            throw "$($case.Name) reported batch errors: $($errors -join ' | '). Output directory: $workDir"
        }
        Write-Output "$($case.Name): PASS ($($counts -join '/') columns)"
    }

    if ($IncludeMortality) {
        $inputPath = Join-Path $workDir 'FFI_FOFEM_Sample.tre'
        $outputPath = Join-Path $workDir 'mortality-out.csv'
        $errorPath = Join-Path $workDir 'mortality-err.txt'
        & (Join-Path $appDir 'runfofem.exe') '2' $inputPath $outputPath $errorPath 'S' '10' | Out-Null
        if ($LASTEXITCODE -ne 0) {
            throw "Mortality runfofem.exe exited with code $LASTEXITCODE. Output directory: $workDir"
        }
        $lines = @(Get-Content -LiteralPath $outputPath)
        $errors = @(Get-Content -LiteralPath $errorPath | Select-Object -Skip 4 | Where-Object { $_.Trim() })
        if ($lines.Count -le 2 -or $errors.Count) {
            throw "Mortality output or error file is invalid. Output directory: $workDir"
        }
        Write-Output "mortality: PASS ($($lines.Count - 2) plot rows)"
    }

    Write-Output "Smoke output: $workDir"
    Write-Output "FOFEM_DATA: $appDir"
    Write-Output "Files copied: $($required -join ', ')"
} finally {
    $env:PATH = $originalPath
    $env:FOFEM_DATA = $originalData
    $env:LOCALAPPDATA = $originalLocalAppData
}
