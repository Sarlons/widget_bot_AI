[CmdletBinding()]
param(
    [switch]$SkipTests,
    [switch]$SkipPortable,
    [switch]$SkipInstaller,
    [string]$SignToolPath,
    [string]$CertificateThumbprint,
    [string]$CertificatePath,
    [string]$TimestampServer = "http://timestamp.digicert.com",
    [switch]$SkipSignatureVerification
)

$ErrorActionPreference = "Stop"

function Remove-WithRetry {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [int]$Attempts = 20
    )
    for ($attempt = 0; $attempt -lt $Attempts; $attempt++) {
        if (-not (Test-Path $Path)) {
            return
        }
        try {
            Remove-Item -Recurse -Force $Path -ErrorAction Stop
            return
        }
        catch {
            if ($attempt -eq $Attempts - 1) {
                throw
            }
            # Antivirus scanners can briefly hold newly built files.
            Start-Sleep -Milliseconds 500
        }
    }
}

function Resolve-SignTool {
    param([string]$ExplicitPath)

    if ($ExplicitPath) {
        if (-not (Test-Path $ExplicitPath)) {
            throw "signtool.exe not found at $ExplicitPath"
        }
        return (Resolve-Path $ExplicitPath).Path
    }

    $roots = @()
    if (${env:ProgramFiles(x86)}) {
        $roots += Join-Path ${env:ProgramFiles(x86)} "Windows Kits\10\bin"
    }
    if ($env:ProgramFiles) {
        $roots += Join-Path $env:ProgramFiles "Windows Kits\10\bin"
    }
    foreach ($root in $roots) {
        if (-not (Test-Path $root)) {
            continue
        }
        $found = Get-ChildItem $root -Recurse -Filter signtool.exe -ErrorAction SilentlyContinue |
            Where-Object { $_.FullName -match '\\x64\\signtool\.exe$' } |
            Sort-Object FullName -Descending |
            Select-Object -First 1
        if ($found) {
            return $found.FullName
        }
    }

    $command = Get-Command signtool.exe -ErrorAction SilentlyContinue
    if ($command) {
        return $command.Source
    }
    return $null
}

function Invoke-SignFile {
    param(
        [Parameter(Mandatory = $true)][string]$SignTool,
        [Parameter(Mandatory = $true)][string]$File,
        [string]$Thumbprint,
        [string]$PfxPath,
        [string]$TimestampUrl
    )

    if (-not (Test-Path $File)) {
        throw "Cannot sign missing file: $File"
    }

    $arguments = @("sign", "/fd", "SHA256")
    if ($Thumbprint) {
        $arguments += @("/sha1", $Thumbprint)
    }
    else {
        $arguments += @("/f", $PfxPath)
        if ($env:AITW_CERT_PASSWORD) {
            $arguments += @("/p", $env:AITW_CERT_PASSWORD)
        }
    }
    if ($TimestampUrl) {
        $arguments += @("/tr", $TimestampUrl, "/td", "SHA256")
    }
    $arguments += $File

    & $SignTool @arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Signing failed for $File (exit code $LASTEXITCODE)"
    }

    if (-not $SkipSignatureVerification) {
        & $SignTool verify /pa /v $File | Out-Host
        if ($LASTEXITCODE -ne 0) {
            throw "Signature verification failed for $File (exit code $LASTEXITCODE)"
        }
    }
    Write-Host "Signed: $File"
}

$packaging = $PSScriptRoot
$project = Split-Path -Parent $packaging
$repo = Split-Path -Parent $project
$python = Join-Path $project ".venv\Scripts\python.exe"

if (-not (Test-Path $python)) {
    throw "Virtual environment not found at $python. Create it and install requirements-build.txt first."
}

if ($CertificateThumbprint -and $CertificatePath) {
    throw "Specify either -CertificateThumbprint or -CertificatePath, not both."
}
if ($CertificatePath -and -not (Test-Path $CertificatePath)) {
    throw "Certificate file not found: $CertificatePath"
}

$signingRequested = [bool]($CertificateThumbprint -or $CertificatePath)
$signTool = $null
if ($signingRequested) {
    $signTool = Resolve-SignTool -ExplicitPath $SignToolPath
    if (-not $signTool) {
        throw "Code signing was requested but signtool.exe was not found. Install the Windows SDK or pass -SignToolPath."
    }
    Write-Host "Code signing enabled: $signTool"
}
elseif ($SignToolPath) {
    Write-Warning "-SignToolPath was provided without a certificate; signing will be skipped."
}

Push-Location $repo
try {
    $pyinstallerVersion = @(& $python -c "import PyInstaller; print(PyInstaller.__version__)" 2>$null) -join "`n"
    if ($LASTEXITCODE -ne 0) {
        throw "PyInstaller is not installed. Run: `"$python`" -m pip install -r `"$project\requirements-build.txt`""
    }
    $pyinstallerVersion = $pyinstallerVersion.Trim()

    $version = @(& $python -c "import ai_token_widget; print(ai_token_widget.__version__)") -join "`n"
    if ($LASTEXITCODE -ne 0 -or -not $version) {
        throw "Could not read ai_token_widget.__version__"
    }
    $version = $version.Trim()

    $dist = Join-Path $project "dist"
    $work = Join-Path $project "build\pyinstaller"
    $assets = Join-Path $project "build\assets"

    if (Test-Path $assets) {
        Remove-WithRetry $assets
    }
    New-Item -ItemType Directory -Force -Path $assets | Out-Null
    & $python (Join-Path $packaging "make_assets.py") $assets
    if ($LASTEXITCODE -ne 0) {
        throw "Asset generation failed"
    }

    if (-not $SkipTests) {
        $previousQt = $env:QT_QPA_PLATFORM
        try {
            $env:QT_QPA_PLATFORM = "offscreen"
            & $python -m unittest discover -s "ai_token_widget\tests" -t "."
            if ($LASTEXITCODE -ne 0) {
                throw "Tests failed"
            }
        }
        finally {
            if ($null -eq $previousQt) {
                Remove-Item Env:QT_QPA_PLATFORM -ErrorAction SilentlyContinue
            }
            else {
                $env:QT_QPA_PLATFORM = $previousQt
            }
        }
    }

    & $python -m PyInstaller --noconfirm --clean --distpath $dist --workpath $work (Join-Path $packaging "AITokenWidget.spec")
    if ($LASTEXITCODE -ne 0) {
        throw "PyInstaller GUI build failed"
    }

    & $python -m PyInstaller --noconfirm --clean --distpath $dist --workpath $work (Join-Path $packaging "AITokenWidgetBridge.spec")
    if ($LASTEXITCODE -ne 0) {
        throw "PyInstaller bridge build failed"
    }

    $appDir = Join-Path $dist "AITokenWidget"
    $bridgeDir = Join-Path $dist "AITokenWidgetBridge"
    $appBridge = Join-Path $appDir "AITokenWidgetBridge"
    $mainExe = Join-Path $appDir "AITokenWidget.exe"
    $bridgeExe = Join-Path $bridgeDir "AITokenWidgetBridge.exe"
    foreach ($required in @($mainExe, $bridgeExe)) {
        if (-not (Test-Path $required)) {
            throw "Expected build output missing: $required"
        }
    }

    if ($signingRequested) {
        foreach ($file in @($mainExe, $bridgeExe)) {
            Invoke-SignFile -SignTool $signTool -File $file `
                -Thumbprint $CertificateThumbprint -PfxPath $CertificatePath `
                -TimestampUrl $TimestampServer
        }
    }

    if (Test-Path $appBridge) {
        Remove-WithRetry $appBridge
    }
    Copy-Item -Path $bridgeDir -Destination $appBridge -Recurse -Force
    Remove-WithRetry $bridgeDir

    Copy-Item (Join-Path $project "README.md") (Join-Path $appDir "README.md") -Force
    Copy-Item (Join-Path $packaging "INSTALL_NOTES.txt") (Join-Path $appDir "INSTALL_NOTES.txt") -Force

    $pythonVersion = (& $python -c "import platform; print(platform.python_version())").Trim()
    $buildInfo = @(
        "AI Token Widget $version",
        "Built: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss K')",
        "Python: $pythonVersion",
        "PyInstaller: $pyinstallerVersion"
    ) -join "`r`n"
    Set-Content -Path (Join-Path $appDir "BUILD_INFO.txt") -Value $buildInfo -Encoding UTF8

    if (-not $SkipPortable) {
        $zip = Join-Path $dist "AI-Token-Widget-$version-win64-portable.zip"
        if (Test-Path $zip) {
            Remove-Item $zip -Force
        }
        Compress-Archive -Path $appDir -DestinationPath $zip -CompressionLevel Optimal
        Write-Host "Portable ZIP: $zip"
    }

    if (-not $SkipInstaller) {
        $candidates = @()
        if ($env:LOCALAPPDATA) {
            $candidates += Join-Path $env:LOCALAPPDATA "Programs\Inno Setup 6\ISCC.exe"
            $candidates += Join-Path $env:LOCALAPPDATA "Inno Setup 6\ISCC.exe"
        }
        if ($env:ProgramFiles) {
            $candidates += Join-Path $env:ProgramFiles "Inno Setup 6\ISCC.exe"
        }
        if (${env:ProgramFiles(x86)}) {
            $candidates += Join-Path ${env:ProgramFiles(x86)} "Inno Setup 6\ISCC.exe"
        }

        $iscc = $null
        foreach ($candidate in $candidates) {
            if (Test-Path $candidate) {
                $iscc = $candidate
                break
            }
        }
        if (-not $iscc) {
            $command = Get-Command ISCC.exe -ErrorAction SilentlyContinue
            if ($command) {
                $iscc = $command.Source
            }
        }

        if ($iscc) {
            $installerDir = Join-Path $dist "installer"
            New-Item -ItemType Directory -Force -Path $installerDir | Out-Null
            & $iscc "/DAppVersion=$version" "/DSourceDir=$dist" "/DOutputDir=$installerDir" "/DIconFile=$assets\icon.ico" (Join-Path $packaging "installer.iss")
            if ($LASTEXITCODE -ne 0) {
                throw "Inno Setup build failed"
            }

            $setupExe = Join-Path $installerDir "AI-Token-Widget-$version-setup.exe"
            if (-not (Test-Path $setupExe)) {
                throw "Expected installer output missing: $setupExe"
            }
            if ($signingRequested) {
                Invoke-SignFile -SignTool $signTool -File $setupExe `
                    -Thumbprint $CertificateThumbprint -PfxPath $CertificatePath `
                    -TimestampUrl $TimestampServer
            }
            Write-Host "Installer: $installerDir"
        }
        else {
            Write-Warning "Inno Setup 6 (ISCC.exe) not found; portable ZIP was built without an installer."
        }
    }

    Write-Host "Application: $appDir"
    Write-Host "Build complete."
}
finally {
    Pop-Location
}
