$port=8015
$stdout='tmp_phase4_live_stdout.log'
$stderr='tmp_phase4_live_stderr.log'
if(Test-Path $stdout){Remove-Item $stdout -Force}
if(Test-Path $stderr){Remove-Item $stderr -Force}
$cmd = "set ENVIRONMENT=development&& set DEV_UNSAFE_AUTH_BYPASS=true&& set GOOGLE_APPLICATION_CREDENTIALS=__missing__.json&& python -m uvicorn app:app --app-dir apps/backend --host 127.0.0.1 --port $port --lifespan off"
$p = Start-Process -FilePath cmd.exe -ArgumentList '/c', $cmd -PassThru -RedirectStandardOutput $stdout -RedirectStandardError $stderr
try {
  $ready=$false
  for($i=0; $i -lt 60; $i++){
    Start-Sleep -Milliseconds 500
    try {
      $r = Invoke-WebRequest -Uri ("http://127.0.0.1:{0}/docs" -f $port) -UseBasicParsing -TimeoutSec 2
      if($r.StatusCode -ge 200){ $ready=$true; break }
    } catch {}
  }
  if(-not $ready){ throw 'Server not ready' }

  $bodyObj = @{
    question='bilhassa'
    firebase_uid='vpq1p0UzcCSLAh1d18WgZZWPBE63'
    include_private_notes=$false
    visibility_scope='default'
  }
  $body = $bodyObj | ConvertTo-Json

  try {
    $resp = Invoke-RestMethod -Uri ("http://127.0.0.1:{0}/api/search" -f $port) -Method Post -ContentType 'application/json' -Body $body -TimeoutSec 120
    Write-Output ("API_SEARCH_OK answer_len={0}" -f (($resp.answer | Out-String).Trim().Length))
    if($resp.metadata){
      Write-Output ("META_HAS_graph={0}" -f [bool]($resp.metadata.PSObject.Properties.Name -contains 'graph_bridge_used'))
      Write-Output ("META_vis={0}" -f $resp.metadata.visibility_scope)
    }
  } catch {
    Write-Output ("API_SEARCH_ERR {0}" -f $_.Exception.Message)
  }
}
finally {
  if($p -and -not $p.HasExited){ Stop-Process -Id $p.Id -Force }
  Start-Sleep -Milliseconds 500
  if(Test-Path $stderr){
    Write-Output '--- STDERR TAIL ---'
    Get-Content $stderr -Tail 120
  }
}
