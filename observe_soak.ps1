param([Parameter(Mandatory=$true)][int]$ParentProcessId,
      [Parameter(Mandatory=$true)][string]$ReportPath)
$ErrorActionPreference = 'Stop'
$rows = [System.Collections.Generic.List[object]]::new()
$began = Get-Date
$gpuTool = Get-Command nvidia-smi.exe -ErrorAction SilentlyContinue
# Read only. Collect only child model processes owned by the supplied test PID.
# No process arguments, environment variables, keys or unrelated PID data saved.
while (Get-Process -Id $ParentProcessId -ErrorAction SilentlyContinue) {
    $children = @(Get-CimInstance Win32_Process -Filter "ParentProcessId = $ParentProcessId" |
                  Where-Object { $_.Name -eq 'llama-server.exe' })
    $gpuRows = @()
    if ($gpuTool) {
        $gpuRows = @(& $gpuTool.Source --query-compute-apps=pid,used_memory --format=csv,noheader,nounits 2>$null)
    }
    foreach ($child in $children) {
        $model = Get-Process -Id $child.ProcessId -ErrorAction SilentlyContinue
        if (-not $model) { continue }
        $model.Refresh()
        $gpuMemory = $null
        foreach ($gpuRow in $gpuRows) {
            $parts = $gpuRow -split ','
            if ($parts.Count -eq 2 -and $parts[0].Trim() -eq [string]$child.ProcessId) {
                $gpuMemory = $parts[1].Trim()
            }
        }
        $rows.Add([ordered]@{
            at = (Get-Date).ToString('o')
            observation_seconds = [math]::Round(((Get-Date)-$began).TotalSeconds,2)
            pid = [int]$child.ProcessId
            private_mb = [math]::Round($model.PrivateMemorySize64/1MB,2)
            working_set_mb = [math]::Round($model.WorkingSet64/1MB,2)
            handles = $model.HandleCount
            gpu_memory_mib_reported = $gpuMemory
        })
    }
    $report = [ordered]@{
        test_parent_pid = $ParentProcessId
        observation_started = $began.ToString('o')
        observation_seconds = [math]::Round(((Get-Date)-$began).TotalSeconds,2)
        scope = 'Read-only observation begun after soak startup. Only owned model child PID. Raw nvidia-smi field; null/N/A is unavailable, never zero.'
        samples = @($rows.ToArray())
        completed = $false
    }
    $report | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $ReportPath -Encoding utf8
    Start-Sleep -Seconds 30
}
$report.completed = $true
$report.observation_seconds = [math]::Round(((Get-Date)-$began).TotalSeconds,2)
$report | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $ReportPath -Encoding utf8
