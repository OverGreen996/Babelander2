param([Parameter(Mandatory)][int]$ModelProcessId,
      [Parameter(Mandatory)][int]$ApplicationProcessId,
      [Parameter(Mandatory)][string]$Report,
      [int]$Samples=5,[int]$IntervalSeconds=20)
$ErrorActionPreference='Stop'
$records=[Collections.Generic.List[object]]::new()
for ($index=0;$index -lt $Samples;$index++) {
    $row=[ordered]@{utc=[DateTime]::UtcNow.ToString('o');model_pid=$ModelProcessId;app_pid=$ApplicationProcessId}
    try {
        $counters=(Get-Counter '\GPU Process Memory(*)\Dedicated Usage','\GPU Process Memory(*)\Shared Usage' -ErrorAction Stop).CounterSamples
        foreach ($entry in @(@('model',$ModelProcessId),@('app',$ApplicationProcessId))) {
            $selected=@($counters | Where-Object { $_.InstanceName -like "pid_$($entry[1])_*" })
            $dedicated=@($selected | Where-Object { $_.Path -like '*\dedicated usage' })
            $shared=@($selected | Where-Object { $_.Path -like '*\shared usage' })
            $row[$entry[0]]=[ordered]@{
                process_alive=([bool](Get-Process -Id $entry[1] -ErrorAction SilentlyContinue))
                counters_available=([bool]$selected)
                dedicated_bytes=$(if($dedicated){($dedicated | Measure-Object CookedValue -Sum).Sum}else{$null})
                shared_bytes=$(if($shared){($shared | Measure-Object CookedValue -Sum).Sum}else{$null})
                samples=@($selected | Select-Object InstanceName,Path,CookedValue)
            }
        }
    } catch {$row.error=$_.Exception.Message}
    $records.Add([pscustomobject]$row)
    [ordered]@{scope='Read-only Windows GPU Process Memory counters of the owned test processes. Reported per-process usage, no adapter totals or game performance; unavailable is null, not zero.';records=@($records.ToArray())} | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $Report -Encoding utf8
    if ($index -lt $Samples-1) {Start-Sleep -Seconds $IntervalSeconds}
}
