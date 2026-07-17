Write-Host "=============================================" -ForegroundColor Cyan
Write-Host "        CycloneX System Compiler Setup       " -ForegroundColor Cyan
Write-Host "=============================================" -ForegroundColor Cyan

# Procurar compilador C++ / MSBuild / CMake
if (Get-Command cmake -ErrorAction SilentlyContinue) {
    Write-Host "[1/3] CMake detected." -ForegroundColor Green
} else {
    Write-Host "[!] CMake is not installed or not in PATH." -ForegroundColor Red
    return
}

# Criar pasta build
if (Test-Path build) {
    Remove-Item build -Recurse -Force | Out-Null
}
New-Item -ItemType Directory -Path build | Out-Null

# Gerar e Compilar
cd build
cmake ..
cmake --build . --config Release

if ($LASTEXITCODE -eq 0) {
    Write-Host "`n[Build] Project compiled successfully!" -ForegroundColor Green
    Copy-Item "Release\cyclone_agent.exe" "..\cyclone_agent.exe" -Force
    Copy-Item "Release\cyclone_launcher.exe" "..\cyclone_launcher.exe" -Force
    Write-Host "[Build] Executables moved to workspace root: cyclone_launcher.exe, cyclone_agent.exe" -ForegroundColor Green
    Write-Host "`nTo start, run: .\cyclone_launcher.exe" -ForegroundColor Cyan
} else {
    Write-Host "`n[Build] Project compilation failed." -ForegroundColor Red
}
