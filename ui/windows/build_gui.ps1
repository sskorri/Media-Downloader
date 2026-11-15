# Build the launcher beside the source. Optionally assemble a self-contained copy.
[CmdletBinding()]
param([switch] $BundleRuntime)

$ErrorActionPreference = 'Stop'
$project = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..\..')).Path
$output = Join-Path $project 'dist\Media Downloader'
$build = Join-Path $project 'build'
$runtime = Join-Path $output 'runtime'
$python = Join-Path $project '.venv\Scripts\python.exe'

function Ensure-Directory([string] $Path) {
    [System.IO.Directory]::CreateDirectory($Path) | Out-Null
}

function Copy-Tree([string] $Source, [string] $Destination, [string[]] $Exclude = @(), [string[]] $ExcludeFiles = @()) {
    # Copy only package files. Never mirror a user's existing portable folder.
    $options = @('/E', '/XJ', '/R:1', '/W:1', '/NFL', '/NDL', '/NJH', '/NJS', '/NP',
                 '/XF', '*.pyc', '*.pyo') + $ExcludeFiles + @('/XD', '__pycache__') + $Exclude
    $log = & robocopy.exe $Source $Destination @options
    if ($LASTEXITCODE -ge 8) { throw "Cannot copy $Source into $Destination. $log" }
}

$launcher = Join-Path $project 'Media Downloader.exe'
$compiler = Join-Path $env:WINDIR 'Microsoft.NET\Framework64\v4.0.30319\csc.exe'
if (!(Test-Path -LiteralPath $compiler)) {
    $compiler = Join-Path $env:WINDIR 'Microsoft.NET\Framework\v4.0.30319\csc.exe'
}
& $compiler /nologo /target:winexe /optimize+ /reference:System.Windows.Forms.dll "/out:$launcher" (Join-Path $PSScriptRoot 'Launcher.cs')
if ($LASTEXITCODE -ne 0) { throw 'Launcher compilation failed.' }
Write-Host "Built $launcher"
if (!$BundleRuntime) { exit 0 }

if (!(Test-Path -LiteralPath $python -PathType Leaf)) {
    throw 'Install ui/requirements.txt in the project .venv before building.'
}
$environmentInfo = & $python -B -c "import json,sys,sysconfig,webview,clr;print(json.dumps([sys.base_prefix, sysconfig.get_path('purelib'),'python%d%d' % sys.version_info[:2]]))"
if ($LASTEXITCODE -ne 0) { throw 'Install ui/requirements.txt in the project .venv before building.' }
$paths = ConvertFrom-Json -InputObject $environmentInfo
$basePython = $paths[0]
$packages = $paths[1]
$abi = $paths[2]

Ensure-Directory $output
Ensure-Directory $runtime
$tools = Join-Path $runtime 'bin'
$licenses = Join-Path $runtime 'licenses'
Ensure-Directory $tools
Ensure-Directory $licenses

Write-Host 'Copying the private Python runtime and GUI/download dependencies...'
foreach ($name in @('python.exe', 'pythonw.exe', 'python3.dll', "$abi.dll", 'LICENSE.txt')) {
    Copy-Item -LiteralPath (Join-Path $basePython $name) -Destination $runtime -Force
}
Get-ChildItem -LiteralPath $basePython -Filter 'vcruntime*.dll' -File |
    Copy-Item -Destination $runtime -Force
Copy-Tree (Join-Path $basePython 'DLLs') (Join-Path $runtime 'DLLs')
# The base interpreter's personal site-packages are never shipped.
Copy-Tree (Join-Path $basePython 'Lib') (Join-Path $runtime 'Lib') @(
    'site-packages', 'test', 'idlelib', 'turtledemo', 'ensurepip'
)
Copy-Tree $packages (Join-Path $runtime 'Lib\site-packages') @('pip', 'pip-*.dist-info')
# Resolve imports against this directory even if another Python is installed.
[System.IO.File]::WriteAllLines((Join-Path $runtime "$abi._pth"),
    [string[]]@('Lib', 'DLLs', 'Lib/site-packages', '..', 'import site'))

Write-Host 'Bundling the download tools...'
$ffmpeg = (Get-Command ffmpeg.exe -CommandType Application -ErrorAction Stop | Select-Object -First 1).Source
$ffBin = Split-Path -Parent $ffmpeg
foreach ($name in @('ffmpeg.exe', 'ffprobe.exe')) {
    Copy-Item -LiteralPath (Join-Path $ffBin $name) -Destination $tools -Force
}
# Shared FFmpeg distributions keep their companion DLLs beside ffmpeg.exe.
Get-ChildItem -LiteralPath $ffBin -Filter '*.dll' -File | Copy-Item -Destination $tools -Force
$ffRoot = Split-Path -Parent $ffBin
$ffNotices = @(Get-ChildItem -LiteralPath $ffBin,$ffRoot -File | Where-Object { $_.Name -match '^(LICENSE|COPYING)(\.|$)' })
if (!$ffNotices.Count) { throw 'Use an FFmpeg distribution that includes its LICENSE or COPYING file.' }
foreach ($notice in $ffNotices) {
    Copy-Item -LiteralPath $notice.FullName -Destination (Join-Path $licenses ('ffmpeg-' + $notice.Name)) -Force
}
if (Test-Path -LiteralPath (Join-Path $ffRoot 'README.txt')) {
    Copy-Item -LiteralPath (Join-Path $ffRoot 'README.txt') -Destination (Join-Path $licenses 'ffmpeg-README.txt') -Force
}

$node = Get-Command node.exe -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
if ($node) {
    $nodeVersion = (& $node.Source -p process.version).Trim()
    if ($nodeVersion -notmatch '^v\d+\.\d+\.\d+([-.][a-zA-Z0-9.-]+)?$') { throw 'Unrecognized Node.js version.' }
    $cache = Join-Path $build 'licenses'
    Ensure-Directory $cache
    $notice = Join-Path $cache "node-$nodeVersion-LICENSE.txt"
    if (!(Test-Path -LiteralPath $notice)) {
        $localNotice = Join-Path (Split-Path -Parent $node.Source) 'LICENSE'
        if (Test-Path -LiteralPath $localNotice) {
            Copy-Item -LiteralPath $localNotice -Destination $notice
        } else {
            Invoke-WebRequest -UseBasicParsing -Uri "https://raw.githubusercontent.com/nodejs/node/$nodeVersion/LICENSE" -OutFile $notice
        }
    }
    if ((Get-Item -LiteralPath $notice).Length -eq 0) { throw 'Missing Node.js license text.' }
    Copy-Item -LiteralPath $notice -Destination (Join-Path $licenses 'node-LICENSE.txt') -Force
    Copy-Item -LiteralPath $node.Source -Destination (Join-Path $tools 'node.exe') -Force
} else {
    Write-Warning 'Node.js was not found. Full YouTube support requires a supported JavaScript runtime on the destination computer.'
}

Write-Host 'Copying the application...'
foreach ($name in @('cli.py', 'LICENSE', 'README.md', 'requirements.txt')) {
    Copy-Item -LiteralPath (Join-Path $project $name) -Destination $output -Force
}
Copy-Tree (Join-Path $project 'src') (Join-Path $output 'src')
Copy-Tree (Join-Path $project 'ui') (Join-Path $output 'ui') @('windows')
Ensure-Directory (Join-Path $output 'ui\windows')
Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'setup.cmd') -Destination (Join-Path $output 'ui\windows') -Force
Copy-Item -LiteralPath $launcher -Destination $output -Force

$data = Join-Path $output 'data'
Ensure-Directory $data
Ensure-Directory (Join-Path $output 'media')
if (!(Test-Path -LiteralPath (Join-Path $data 'settings.json'))) {
    New-Item -ItemType File -Path (Join-Path $data 'settings.json') -Value '{"download_dir":"media"}' | Out-Null
}

$privatePython = Join-Path $runtime 'python.exe'
& $privatePython -I -B -c "import sys,pathlib,webview,clr,yt_dlp,importlib.util;assert importlib.util.find_spec('spotdl');assert pathlib.Path(webview.__file__).is_relative_to(sys.prefix);assert pathlib.Path(yt_dlp.__file__).is_relative_to(sys.prefix)"
if ($LASTEXITCODE -ne 0) { throw 'The private runtime failed its import check.' }
& $privatePython -I -B -m ui.gui --help | Out-Null
if ($LASTEXITCODE -ne 0) { throw 'The packaged GUI entry point failed its import check.' }

# On an upgrade, move the old UI files out of the distribution. Keeping them
# in build/ also preserves any edits made directly to an older portable copy.
$oldUiFiles = @('gui.py', 'Media Downloader GUI mockup.html', 'ui\Media Downloader GUI mockup.html',
                'src\gui_controller.py', 'src\gui_view.py', 'src\gui_assets\live.js')
$backup = Join-Path $build ('previous-ui-' + [Guid]::NewGuid().ToString('N'))
foreach ($relative in $oldUiFiles) {
    $old = Join-Path $output $relative
    if (Test-Path -LiteralPath $old -PathType Leaf) {
        $saved = Join-Path $backup $relative
        Ensure-Directory (Split-Path -Parent $saved)
        Move-Item -LiteralPath $old -Destination $saved
    }
}
if (Test-Path -LiteralPath $backup) { Write-Host "Retained files from the previous UI layout in $backup" }
$oldAssets = Join-Path $output 'src\gui_assets'
if ((Test-Path -LiteralPath $oldAssets -PathType Container) -and !(Get-ChildItem -LiteralPath $oldAssets -Force)) {
    [IO.Directory]::Delete($oldAssets)
}
Write-Host "Built $(Join-Path $output 'Media Downloader.exe')"
exit 0
