param(
    [Parameter(Mandatory=$true)][string]$InputDocx,
    [Parameter(Mandatory=$true)][string]$OutputPdf
)

$resolvedInput = (Resolve-Path -LiteralPath $InputDocx).Path
$resolvedOutput = [System.IO.Path]::GetFullPath($OutputPdf)
$outputDir = [System.IO.Path]::GetDirectoryName($resolvedOutput)
if (-not (Test-Path -LiteralPath $outputDir)) {
    New-Item -ItemType Directory -Path $outputDir | Out-Null
}

$word = $null
$document = $null
try {
    $word = New-Object -ComObject Word.Application
    $word.Visible = $false
    $word.DisplayAlerts = 0
    $document = $word.Documents.Open($resolvedInput, $false, $true)
    $document.Fields.Update() | Out-Null
    foreach ($section in $document.Sections) {
        foreach ($footer in $section.Footers) {
            $footer.Range.Fields.Update() | Out-Null
        }
    }
    $document.ExportAsFixedFormat($resolvedOutput, 17)
}
finally {
    if ($document -ne $null) {
        $document.Close($false)
        [System.Runtime.InteropServices.Marshal]::ReleaseComObject($document) | Out-Null
    }
    if ($word -ne $null) {
        $word.Quit()
        [System.Runtime.InteropServices.Marshal]::ReleaseComObject($word) | Out-Null
    }
    [GC]::Collect()
    [GC]::WaitForPendingFinalizers()
}

Write-Output $resolvedOutput
