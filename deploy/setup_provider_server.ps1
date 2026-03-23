#Requires -Version 5.1
<#
.SYNOPSIS
    AI Scribe - Provider-Facing Server Setup (Windows)

.DESCRIPTION
    Installs CPU-only dependencies, configures the server for provider-facing role,
    and optionally sets up nginx-for-Windows reverse proxy and NSSM Windows Services.

    This is the Windows equivalent of deploy/setup_provider_server.sh.

.PARAMETER PipelineUrl
    Pipeline server URL (default: http://localhost:8100)

.PARAMETER PublicUrl
    This server's public URL (e.g. https://provider.example.com)

.PARAMETER Secret
    Pre-existing inter-server secret. If omitted, a cryptographically random secret is generated.

.PARAMETER WithNginx
    Install and configure nginx-for-Windows as HTTPS reverse proxy.

.PARAMETER TlsCert
    Path to TLS certificate file (used with -WithNginx).

.PARAMETER TlsKey
    Path to TLS private key file (used with -WithNginx).

.PARAMETER WithService
    Register NSSM Windows Services for the API and Web UI.

.EXAMPLE
    .\deploy\setup_provider_server.ps1 -PipelineUrl "http://pipeline:8100" -WithNginx -WithService

.EXAMPLE
    .\deploy\setup_provider_server.ps1 -Secret "my-shared-secret" -PublicUrl "https://provider.local"
#>

[CmdletBinding()]
param(
    [string]$PipelineUrl = "http://localhost:8100",
    [string]$PublicUrl   = "",
    [string]$Secret      = "",
    [switch]$WithNginx,
    [string]$TlsCert     = "",
    [string]$TlsKey      = "",
    [switch]$WithService
)

# ---------------------------------------------------------------------------
# Strict mode -- mirror bash set -euo pipefail
# ---------------------------------------------------------------------------
Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

# ---------------------------------------------------------------------------
# Path resolution
# ---------------------------------------------------------------------------
$ScriptDir   = Split-Path -Parent $MyInvocation.MyCommand.Definition
$ProjectRoot = Split-Path -Parent $ScriptDir

Write-Host "========================================"
Write-Host "AI Scribe - Provider-Facing Server Setup"
Write-Host "========================================"
Write-Host "Project root: $ProjectRoot"
Write-Host ""

# ===========================================================================
# Utility Functions
# ===========================================================================

function Compare-Version {
    <#
    .SYNOPSIS
        Numeric semantic version comparison.
    .DESCRIPTION
        Compares two version strings numerically (not lexicographically).
        Returns  1 if Actual > Required,
                 0 if Actual == Required,
                -1 if Actual < Required.
        Supports versions with different segment counts (e.g. "3.11" vs "3.11.4").
    .PARAMETER Actual
        The installed / actual version string (e.g. "3.11.4").
    .PARAMETER Required
        The minimum required version string (e.g. "3.11").
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)][string]$Actual,
        [Parameter(Mandatory)][string]$Required
    )

    $actualParts   = $Actual.Split('.')   | ForEach-Object { [int]$_ }
    $requiredParts = $Required.Split('.') | ForEach-Object { [int]$_ }

    $maxLen = [Math]::Max($actualParts.Count, $requiredParts.Count)

    for ($i = 0; $i -lt $maxLen; $i++) {
        $a = if ($i -lt $actualParts.Count)   { $actualParts[$i] }   else { 0 }
        $r = if ($i -lt $requiredParts.Count)  { $requiredParts[$i] } else { 0 }

        if ($a -gt $r) { return  1 }
        if ($a -lt $r) { return -1 }
    }
    return 0
}

function Get-CpuOnlyPackages {
    <#
    .SYNOPSIS
        Filters a list of package specifiers, removing GPU-specific packages.
    .DESCRIPTION
        Excludes packages matching: cuda*, torch-gpu, whisperx, nvidia-*, triton.
        Returns only CPU-compatible packages.
    .PARAMETER Packages
        Array of package name strings (may include version specifiers like "torch>=2.0").
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)][string[]]$Packages
    )

    $gpuPatterns = @(
        '^cuda',
        '^torch-gpu',
        '^whisperx$',
        '^nvidia-',
        '^triton$'
    )

    $filtered = @()
    foreach ($pkg in $Packages) {
        # Extract bare package name (strip version specifiers like >=, ==, [extras])
        $bareName = $pkg -replace '[>=<!\[\];,].*$', ''
        $bareName = $bareName.Trim().ToLower()
        $isGpu = $false
        foreach ($pattern in $gpuPatterns) {
            if ($bareName -match $pattern) {
                $isGpu = $true
                break
            }
        }
        if (-not $isGpu) {
            $filtered += $pkg
        }
    }
    return $filtered
}

function Write-DependencyError {
    <#
    .SYNOPSIS
        Structured error logging for dependency failures.
    .DESCRIPTION
        Logs a structured error message that includes the dependency name and
        version requirement, then exits with code 1.
    .PARAMETER DependencyName
        Name of the dependency that failed (e.g. "Python", "Node.js").
    .PARAMETER VersionRequired
        The minimum version requirement string (e.g. "3.11+").
    .PARAMETER ErrorDetail
        Optional additional detail about the failure.
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)][string]$DependencyName,
        [Parameter(Mandatory)][string]$VersionRequired,
        [string]$ErrorDetail = ""
    )

    $timestamp = Get-Date -Format "yyyy-MM-ddTHH:mm:ssK"
    $msg = "[$timestamp] ERROR: Dependency installation failed"
    $msg += " | dependency=$DependencyName"
    $msg += " | required_version=$VersionRequired"
    if ($ErrorDetail) {
        $msg += " | detail=$ErrorDetail"
    }
    Write-Error $msg
}

# ===========================================================================
# Step 1/7: Verify and install dependencies
# ===========================================================================
Write-Host "[1/7] Verifying dependencies..."

# --- Python 3.11+ ---
$pythonCmd = $null
foreach ($candidate in @("python", "python3", "py")) {
    try {
        $ver = & $candidate --version 2>&1
        if ($ver -match '(\d+\.\d+\.\d+)') {
            $pythonVersion = $Matches[1]
            if ((Compare-Version -Actual $pythonVersion -Required "3.11") -ge 0) {
                $pythonCmd = $candidate
                break
            }
        }
    } catch {
        # candidate not found, try next
    }
}

if (-not $pythonCmd) {
    Write-DependencyError -DependencyName "Python" -VersionRequired "3.11+" `
        -ErrorDetail "Python 3.11+ not found in PATH. Install from https://www.python.org/downloads/"
    exit 1
}
Write-Host "  [OK] Python $pythonVersion ($pythonCmd)"

# --- Node.js 18+ ---
$nodeVersion = $null
try {
    $nodeOut = & node --version 2>&1
    if ($nodeOut -match 'v?(\d+\.\d+\.\d+)') {
        $nodeVersion = $Matches[1]
    }
} catch {
    # node not found
}

if (-not $nodeVersion -or (Compare-Version -Actual $nodeVersion -Required "18.0.0") -lt 0) {
    Write-DependencyError -DependencyName "Node.js" -VersionRequired "18+" `
        -ErrorDetail "Node.js 18+ not found in PATH. Install from https://nodejs.org/"
    exit 1
}
Write-Host "  [OK] Node.js v$nodeVersion"

# --- nginx-for-Windows (only if -WithNginx) ---
if ($WithNginx) {
    $nginxCmd = Get-Command nginx -ErrorAction SilentlyContinue
    if (-not $nginxCmd) {
        Write-Host "  [..] nginx not found -- will be configured in step 5"
    } else {
        Write-Host "  [OK] nginx found at $($nginxCmd.Source)"
    }
}

# --- NSSM (only if -WithService or -WithNginx) ---
if ($WithService -or $WithNginx) {
    $nssmCmd = Get-Command nssm -ErrorAction SilentlyContinue
    if (-not $nssmCmd) {
        Write-DependencyError -DependencyName "NSSM" -VersionRequired "2.24+" `
            -ErrorDetail "NSSM not found in PATH. Install from https://nssm.cc/download"
        exit 1
    }
    Write-Host "  [OK] NSSM found at $($nssmCmd.Source)"
}

Write-Host "  Dependencies verified."
Write-Host ""

# ===========================================================================
# Step 2/7: Python virtual environment and CPU-only dependencies
# ===========================================================================
Write-Host "[2/7] Setting up Python environment..."

$venvPath = Join-Path $ProjectRoot ".venv"

if (-not (Test-Path $venvPath)) {
    & $pythonCmd -m venv $venvPath
    if ($LASTEXITCODE -ne 0) {
        Write-DependencyError -DependencyName "Python venv" -VersionRequired "3.11+" `
            -ErrorDetail "Failed to create virtual environment at $venvPath"
        exit 1
    }
}

# Activate venv
$venvPython = Join-Path $venvPath "Scripts" "python.exe"
$venvPip    = Join-Path $venvPath "Scripts" "pip.exe"

# Upgrade pip
& $venvPip install --quiet --upgrade pip 2>&1 | Out-Null
if ($LASTEXITCODE -ne 0) {
    Write-Host "  [WARN] pip upgrade returned non-zero, continuing..."
}

# Install CPU-only API dependencies
# Try the [api] extra first, fall back to base install
$apiSpec = "${ProjectRoot}[api]"
& $venvPip install --quiet -e $apiSpec 2>&1 | Out-Null
if ($LASTEXITCODE -ne 0) {
    Write-Host "  [..] Falling back to base install..."
    & $venvPip install --quiet -e $ProjectRoot 2>&1 | Out-Null
    if ($LASTEXITCODE -ne 0) {
        Write-DependencyError -DependencyName "Python packages" -VersionRequired "see pyproject.toml" `
            -ErrorDetail "pip install failed for project dependencies"
        exit 1
    }
}

# Verify Python version inside venv
$venvPyVer = & $venvPython --version 2>&1
if ($venvPyVer -match '(\d+\.\d+\.\d+)') {
    $installedPyVer = $Matches[1]
    if ((Compare-Version -Actual $installedPyVer -Required "3.11") -lt 0) {
        Write-DependencyError -DependencyName "Python (venv)" -VersionRequired "3.11+" `
            -ErrorDetail "venv Python reports $installedPyVer"
        exit 1
    }
}

Write-Host "  [OK] Python environment ready ($venvPath)"
Write-Host ""

# ===========================================================================
# Step 3/7: Generate configuration
# ===========================================================================
Write-Host "[3/7] Configuring deployment..."

# --- Inter-server secret: use provided or generate cryptographically random ---
if ($Secret) {
    $interServerSecret = $Secret
    Write-Host "  [OK] Using provided inter-server secret"
} else {
    # Generate a cryptographically random URL-safe secret (minimum 32 chars)
    $secretBytes = New-Object byte[] 48
    $rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    $rng.GetBytes($secretBytes)
    $rng.Dispose()
    # Convert to URL-safe base64 (strip padding, replace +/ with -_)
    $interServerSecret = [Convert]::ToBase64String($secretBytes) -replace '\+','-' -replace '/','_' -replace '='
    Write-Host "  [OK] Generated cryptographic inter-server secret ($($interServerSecret.Length) chars)"
}

# --- Generate .env.provider ---
$envFilePath = Join-Path $ProjectRoot ".env.provider"
$dataDir     = Join-Path $ProjectRoot "ai-scribe-data"
$outputDir   = Join-Path $ProjectRoot "output"
$configDir   = Join-Path $ProjectRoot "config"

$envContent = @"
AI_SCRIBE_SERVER_ROLE=provider-facing
AI_SCRIBE_DATA_DIR=$dataDir
AI_SCRIBE_OUTPUT_DIR=$outputDir
AI_SCRIBE_CONFIG_DIR=$configDir
PIPELINE_API_URL=$PipelineUrl
AI_SCRIBE_INTER_SERVER_SECRET=$interServerSecret
"@

Set-Content -Path $envFilePath -Value $envContent -Encoding UTF8
Write-Host "  [OK] Generated $envFilePath"

# --- Update config/deployment.yaml ---
$deploymentYamlPath = Join-Path $ProjectRoot "config" "deployment.yaml"

if (-not (Test-Path $deploymentYamlPath)) {
    Write-Error "  [ERROR] deployment.yaml not found at $deploymentYamlPath"
    exit 1
}

$yamlLines = Get-Content -Path $deploymentYamlPath -Encoding UTF8

# Section-aware YAML update using indentation-based parent tracking.
# Only keys whose value is a nested block (no inline value) are tracked as parents.
$updatedLines = @()
$parentAtIndent = @{}  # Maps indent level -> section name
foreach ($line in $yamlLines) {
    # Match any YAML key line
    if ($line -match '^(\s*)(\w[\w_]*):(.*)$') {
        $spaces = $Matches[1]
        $indent = $spaces.Length
        $key    = $Matches[2]
        $rest   = $Matches[3].Trim()

        # Clear deeper or equal levels from parent tracker
        foreach ($lvl in @($parentAtIndent.Keys | Where-Object { $_ -ge $indent })) {
            $parentAtIndent.Remove($lvl)
        }

        # Section header = no inline value (empty or comment-only after colon)
        $isSection = ($rest -eq "" -or $rest.StartsWith("#"))
        if ($isSection) {
            $parentAtIndent[$indent] = $key
        }

        # Build full dotted path: parents + current key
        $parentPath = ($parentAtIndent.GetEnumerator() | Sort-Object Name | ForEach-Object { $_.Value }) -join '.'
        if ($parentPath) {
            $fullPath = "$parentPath.$key"
        } else {
            $fullPath = $key
        }

        # Update network.provider_facing.public_url
        if ($fullPath -eq 'network.provider_facing.public_url' -and $PublicUrl) {
            $updatedLines += "${spaces}public_url: `"$PublicUrl`""
            continue
        }

        # Update network.processing_pipeline.internal_url
        if ($fullPath -eq 'network.processing_pipeline.internal_url') {
            $updatedLines += "${spaces}internal_url: `"$PipelineUrl`""
            continue
        }

        # Update security.inter_server_auth.enabled
        if ($fullPath -eq 'security.inter_server_auth.enabled') {
            $updatedLines += "${spaces}enabled: true"
            continue
        }
    }

    $updatedLines += $line
}

Set-Content -Path $deploymentYamlPath -Value $updatedLines -Encoding UTF8
Write-Host "  [OK] Updated $deploymentYamlPath"
Write-Host "       - network.processing_pipeline.internal_url = $PipelineUrl"
if ($PublicUrl) {
    Write-Host "       - network.provider_facing.public_url = $PublicUrl"
}
Write-Host "       - security.inter_server_auth.enabled = true"
Write-Host ""

# ===========================================================================
# Step 4/7: Create data directories and set NTFS ACLs
# ===========================================================================
Write-Host "[4/7] Creating data directories..."

$dataDirs = @(
    (Join-Path $dataDir   "dictation"),
    (Join-Path $dataDir   "conversation"),
    (Join-Path $outputDir "dictation"),
    (Join-Path $outputDir "conversation"),
    (Join-Path $configDir "providers"),
    (Join-Path $configDir "templates"),
    (Join-Path $configDir "dictionaries")
)

foreach ($dir in $dataDirs) {
    if (Test-Path $dir) {
        Write-Host "  [OK] Already exists: $dir"
    } else {
        New-Item -ItemType Directory -Path $dir -Force | Out-Null
        Write-Host "  [OK] Created: $dir"
    }
}

# --- NTFS ACLs on ai-scribe-data (PHI directory) ---
# Grant FullControl to the current user (service account) and NT AUTHORITY\SYSTEM.
# Remove inherited permissions from other users.
# ACL failure is non-fatal — log warning and continue.
try {
    $serviceAccount = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
    $acl = New-Object System.Security.AccessControl.DirectorySecurity

    # Disable inheritance and remove inherited ACEs
    $acl.SetAccessRuleProtection($true, $false)

    # Grant FullControl to service account
    $serviceRule = New-Object System.Security.AccessControl.FileSystemAccessRule(
        $serviceAccount,
        [System.Security.AccessControl.FileSystemRights]::FullControl,
        ([System.Security.AccessControl.InheritanceFlags]::ContainerInherit -bor [System.Security.AccessControl.InheritanceFlags]::ObjectInherit),
        [System.Security.AccessControl.PropagationFlags]::None,
        [System.Security.AccessControl.AccessControlType]::Allow
    )
    $acl.AddAccessRule($serviceRule)

    # Grant FullControl to NT AUTHORITY\SYSTEM
    $systemRule = New-Object System.Security.AccessControl.FileSystemAccessRule(
        "NT AUTHORITY\SYSTEM",
        [System.Security.AccessControl.FileSystemRights]::FullControl,
        ([System.Security.AccessControl.InheritanceFlags]::ContainerInherit -bor [System.Security.AccessControl.InheritanceFlags]::ObjectInherit),
        [System.Security.AccessControl.PropagationFlags]::None,
        [System.Security.AccessControl.AccessControlType]::Allow
    )
    $acl.AddAccessRule($systemRule)

    Set-Acl -Path $dataDir -AclObject $acl
    Write-Host "  [OK] NTFS ACLs set on $dataDir (FullControl: $serviceAccount, NT AUTHORITY\SYSTEM)"
} catch {
    Write-Host "  [WARN] Failed to set NTFS ACLs on ${dataDir}: $_"
    Write-Host "         Directory is still usable but not hardened. Consider running as Administrator."
}

Write-Host ""

# ===========================================================================
# Step 5/7: nginx-for-Windows configuration
# ===========================================================================
if ($WithNginx) {
    Write-Host "[5/7] Setting up nginx-for-Windows..."

    # --- TLS certificate handling ---
    $nginxDir = Join-Path $ProjectRoot "deploy" "nginx"
    $sslDir   = Join-Path $nginxDir "ssl"

    if (-not (Test-Path $nginxDir)) {
        New-Item -ItemType Directory -Path $nginxDir -Force | Out-Null
    }
    if (-not (Test-Path $sslDir)) {
        New-Item -ItemType Directory -Path $sslDir -Force | Out-Null
    }

    if ($TlsCert -and $TlsKey) {
        # Use provided TLS certificate and key
        $tlsCertPath = $TlsCert
        $tlsKeyPath  = $TlsKey
        Write-Host "  [OK] Using provided TLS certificate: $TlsCert"
        Write-Host "  [OK] Using provided TLS key: $TlsKey"
    } else {
        # Generate self-signed certificate via New-SelfSignedCertificate
        Write-Host "  [..] Generating self-signed TLS certificate..."
        $certSubject = "CN=ai-scribe-provider"
        $pfxPath     = Join-Path $sslDir "ai-scribe.pfx"
        $tlsCertPath = Join-Path $sslDir "ai-scribe.crt"
        $tlsKeyPath  = Join-Path $sslDir "ai-scribe.key"

        try {
            $cert = New-SelfSignedCertificate `
                -DnsName "localhost","ai-scribe-provider" `
                -CertStoreLocation "Cert:\CurrentUser\My" `
                -NotAfter (Get-Date).AddYears(2) `
                -KeyAlgorithm RSA `
                -KeyLength 2048 `
                -Subject $certSubject

            # Export to PFX (with empty password)
            $emptyPassword = New-Object System.Security.SecureString
            Export-PfxCertificate -Cert $cert -FilePath $pfxPath -Password $emptyPassword | Out-Null

            # Convert PFX to PEM files using .NET classes
            $pfxCollection = New-Object System.Security.Cryptography.X509Certificates.X509Certificate2Collection
            $pfxCollection.Import($pfxPath, "", [System.Security.Cryptography.X509Certificates.X509KeyStorageFlags]::Exportable)

            # Export certificate (public key) as PEM
            $certPem = "-----BEGIN CERTIFICATE-----`n"
            $certPem += [Convert]::ToBase64String($pfxCollection[0].RawData, [Base64FormattingOptions]::InsertLineBreaks)
            $certPem += "`n-----END CERTIFICATE-----"
            Set-Content -Path $tlsCertPath -Value $certPem -Encoding ASCII

            # Export private key as PEM
            $rsaKey = $pfxCollection[0].PrivateKey
            $keyBytes = $rsaKey.ExportRSAPrivateKey()
            $keyPem = "-----BEGIN RSA PRIVATE KEY-----`n"
            $keyPem += [Convert]::ToBase64String($keyBytes, [Base64FormattingOptions]::InsertLineBreaks)
            $keyPem += "`n-----END RSA PRIVATE KEY-----"
            Set-Content -Path $tlsKeyPath -Value $keyPem -Encoding ASCII

            # Clean up cert from store
            Remove-Item "Cert:\CurrentUser\My\$($cert.Thumbprint)" -ErrorAction SilentlyContinue

            Write-Host "  [OK] Self-signed certificate generated"
            Write-Host "  [WARN] Replace with a production certificate for live deployments"
        } catch {
            Write-Error "  [ERROR] Failed to generate self-signed certificate: $_"
            Write-Host "  Suggestion: Provide -TlsCert and -TlsKey with existing certificate files"
            exit 1
        }
    }

    # --- Generate nginx.conf ---
    $nginxConfPath = Join-Path $nginxDir "nginx.conf"

    # Normalize paths for nginx (forward slashes)
    $nginxTlsCert = $tlsCertPath -replace '\\','/'
    $nginxTlsKey  = $tlsKeyPath  -replace '\\','/'

    $nginxConf = @"
# AI Scribe Provider Server - nginx configuration
# Generated by deploy/setup_provider_server.ps1

worker_processes auto;

events {
    worker_connections 1024;
}

http {
    include       mime.types;
    default_type  application/octet-stream;
    sendfile      on;
    keepalive_timeout 65;

    # Rate limiting: 100 requests/second per client IP
    limit_req_zone `$binary_remote_addr zone=api_limit:10m rate=100r/s;

    # Upstream backends
    upstream api_backend {
        server 127.0.0.1:8000;
    }

    upstream web_backend {
        server 127.0.0.1:3000;
    }

    # Redirect HTTP to HTTPS
    server {
        listen 80;
        server_name _;
        return 301 https://`$host`$request_uri;
    }

    # HTTPS server
    server {
        listen 443 ssl;
        server_name _;

        # TLS configuration
        ssl_certificate     $nginxTlsCert;
        ssl_certificate_key $nginxTlsKey;
        ssl_protocols       TLSv1.2 TLSv1.3;
        ssl_ciphers         HIGH:!aNULL:!MD5;
        ssl_prefer_server_ciphers on;

        # WebSocket upgrade for /ws/ paths
        location /ws/ {
            proxy_pass http://api_backend;
            proxy_http_version 1.1;
            proxy_set_header Upgrade `$http_upgrade;
            proxy_set_header Connection "upgrade";
            proxy_set_header Host `$host;
            proxy_set_header X-Real-IP `$remote_addr;
            proxy_set_header X-Forwarded-For `$proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto https;
            proxy_read_timeout 86400;
        }

        # API reverse proxy
        location /api/ {
            limit_req zone=api_limit burst=50 nodelay;
            proxy_pass http://api_backend;
            proxy_set_header Host `$host;
            proxy_set_header X-Real-IP `$remote_addr;
            proxy_set_header X-Forwarded-For `$proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto https;
        }

        # Web UI reverse proxy (default)
        location / {
            proxy_pass http://web_backend;
            proxy_set_header Host `$host;
            proxy_set_header X-Real-IP `$remote_addr;
            proxy_set_header X-Forwarded-For `$proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto https;
        }
    }
}
"@

    Set-Content -Path $nginxConfPath -Value $nginxConf -Encoding UTF8
    Write-Host "  [OK] Generated $nginxConfPath"
    Write-Host "       - HTTPS on port 443"
    Write-Host "       - API proxy -> 127.0.0.1:8000"
    Write-Host "       - Web UI proxy -> 127.0.0.1:3000"
    Write-Host "       - WebSocket upgrade for /ws/"
    Write-Host "       - Rate limiting: 100 req/s per client IP"

    # --- Register nginx as Windows Service via NSSM ---
    $nginxExe = (Get-Command nginx -ErrorAction SilentlyContinue).Source
    if ($nginxExe) {
        $nginxConfAbsolute = (Resolve-Path $nginxConfPath).Path
        Write-Host "  [..] Registering nginx as Windows Service via NSSM..."
        & nssm install ai-scribe-nginx "$nginxExe"
        & nssm set ai-scribe-nginx AppParameters "-c `"$nginxConfAbsolute`""
        & nssm set ai-scribe-nginx Start SERVICE_AUTO_START
        & nssm set ai-scribe-nginx AppRestartDelay 5000
        Write-Host "  [OK] Registered ai-scribe-nginx service"
    } else {
        Write-Host "  [WARN] nginx executable not found in PATH -- skipping service registration"
        Write-Host "         Install nginx-for-Windows and re-run, or register the service manually"
    }
} else {
    Write-Host "[5/7] nginx setup skipped (use -WithNginx to enable)"
}
Write-Host ""

# ===========================================================================
# Step 6/7: NSSM Windows Services
# ===========================================================================
if ($WithService) {
    Write-Host "[6/7] Setting up Windows Services via NSSM..."

    $envFileAbsolute = (Resolve-Path $envFilePath -ErrorAction SilentlyContinue)
    if (-not $envFileAbsolute) {
        $envFileAbsolute = $envFilePath
    } else {
        $envFileAbsolute = $envFileAbsolute.Path
    }

    # Load environment variables from .env.provider for NSSM AppEnvironmentExtra
    $envExtra = @()
    if (Test-Path $envFilePath) {
        foreach ($line in (Get-Content $envFilePath -Encoding UTF8)) {
            $line = $line.Trim()
            if ($line -and -not $line.StartsWith("#")) {
                $envExtra += $line
            }
        }
    }
    $envExtraString = $envExtra -join "`n"

    # --- Register ai-scribe-api service ---
    $uvicornExe = Join-Path $ProjectRoot ".venv" "Scripts" "uvicorn.exe"
    $apiAppArgs = "api.main:app --host 0.0.0.0 --port 8000"

    Write-Host "  [..] Registering ai-scribe-api service..."
    & nssm install ai-scribe-api "$uvicornExe"
    & nssm set ai-scribe-api AppParameters "$apiAppArgs"
    & nssm set ai-scribe-api AppDirectory "$ProjectRoot"
    & nssm set ai-scribe-api Start SERVICE_AUTO_START
    & nssm set ai-scribe-api AppRestartDelay 5000
    if ($envExtraString) {
        & nssm set ai-scribe-api AppEnvironmentExtra $envExtraString
    }
    Write-Host "  [OK] Registered ai-scribe-api service"
    Write-Host "       - Executable: $uvicornExe"
    Write-Host "       - Arguments: $apiAppArgs"
    Write-Host "       - Startup: Automatic"
    Write-Host "       - Restart delay: 5 seconds"

    # --- Register ai-scribe-web service ---
    $nodeExe = (Get-Command node -ErrorAction SilentlyContinue).Source
    if (-not $nodeExe) {
        $nodeExe = "node"
    }
    $webAppDir  = Join-Path $ProjectRoot "client" "web"
    $webAppArgs = "node_modules/.bin/next start -p 3000"

    Write-Host "  [..] Registering ai-scribe-web service..."
    & nssm install ai-scribe-web "$nodeExe"
    & nssm set ai-scribe-web AppParameters "$webAppArgs"
    & nssm set ai-scribe-web AppDirectory "$webAppDir"
    & nssm set ai-scribe-web Start SERVICE_AUTO_START
    & nssm set ai-scribe-web AppRestartDelay 5000
    & nssm set ai-scribe-web DependOnService ai-scribe-api
    if ($envExtraString) {
        & nssm set ai-scribe-web AppEnvironmentExtra $envExtraString
    }
    Write-Host "  [OK] Registered ai-scribe-web service"
    Write-Host "       - Executable: $nodeExe"
    Write-Host "       - Arguments: $webAppArgs"
    Write-Host "       - Depends on: ai-scribe-api"
    Write-Host "       - Startup: Automatic"
    Write-Host "       - Restart delay: 5 seconds"
} else {
    Write-Host "[6/7] Windows Service setup skipped (use -WithService to enable)"
}
Write-Host ""

# ===========================================================================
# Step 7/7: Health checks
# ===========================================================================
Write-Host "[7/7] Running health checks..."

function Test-HealthEndpoint {
    <#
    .SYNOPSIS
        Sends GET /health to the given URL and returns $true iff the JSON
        response contains a top-level "status" field with value "ok".
    #>
    param(
        [Parameter(Mandatory)][string]$Url
    )
    try {
        $response = Invoke-RestMethod -Uri $Url -Method Get -TimeoutSec 10
        if ($response.status -eq "ok") {
            return $true
        }
        return $false
    } catch {
        return $false
    }
}

# --- Local Provider Server health check ---
$localHealthUrl = "http://localhost:8000/health"
Write-Host "  [..] Checking local Provider Server at $localHealthUrl ..."
if (-not (Test-HealthEndpoint -Url $localHealthUrl)) {
    Write-Error "  [ERROR] Local Provider Server health check failed at $localHealthUrl"
    Write-Host "         Ensure the API server is running on port 8000."
    exit 1
}
Write-Host "  [OK] Local Provider Server is healthy"

# --- Pipeline Server health check ---
$pipelineHealthUrl = "$PipelineUrl/health"
$pipelineHealthy = $true
Write-Host "  [..] Checking Pipeline Server at $pipelineHealthUrl ..."
if (-not (Test-HealthEndpoint -Url $pipelineHealthUrl)) {
    Write-Host "  [WARN] Pipeline Server health check failed at $pipelineHealthUrl"
    Write-Host "         The Pipeline Server may not be running yet. Continuing..."
    $pipelineHealthy = $false
}

if ($pipelineHealthy) {
    $publicDisplay = if ($PublicUrl) { $PublicUrl } else { "http://localhost:8000" }
    Write-Host "  [OK] Both health checks passed"
    Write-Host "       Provider Server: $publicDisplay"
    Write-Host "       Pipeline Server: $PipelineUrl"
}
Write-Host ""

# ===========================================================================
# Done
# ===========================================================================
Write-Host "========================================"
Write-Host "Setup complete!"
Write-Host ""
Write-Host "To start the server manually:"
Write-Host "  cd $ProjectRoot"
Write-Host "  .\.venv\Scripts\Activate.ps1"
Write-Host "  uvicorn api.main:app --host 0.0.0.0 --port 8000"
Write-Host ""
Write-Host "Pipeline server URL: $PipelineUrl"
Write-Host "========================================"
