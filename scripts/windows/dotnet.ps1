# CLI de .NET 10 en el contenedor del SDK. Uso: scripts\windows\dotnet.ps1 <carpeta> <argumentos de dotnet>
#   scripts\windows\dotnet.ps1 sistemas\polizas\app test
param([Parameter(Mandatory = $true)][string]$Carpeta, [Parameter(ValueFromRemainingArguments = $true)][string[]]$Argumentos)
. (Join-Path $PSScriptRoot 'comun.ps1')
Invocar-Dotnet $Carpeta $Argumentos
