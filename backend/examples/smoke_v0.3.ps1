param([string]$BaseUrl = 'http://127.0.0.1:8000')
$ErrorActionPreference = 'Stop'
$smokeOrigin = ([uri]$BaseUrl).GetLeftPart([System.UriPartial]::Authority)
$smokeHeaders = @{ Origin = $smokeOrigin }
$null = Invoke-RestMethod "$BaseUrl/api/v1/session" -Method Post -Headers $smokeHeaders -ContentType 'application/json' -Body '{}' -SessionVariable smokeSession
$smokeHeaders['Idempotency-Key'] = [guid]::NewGuid().ToString()
$smokeBody = @{query='Rome for two days'; params=@{destination='Rome'; duration_days=2}} | ConvertTo-Json -Depth 5 -Compress
$smokeAccepted = Invoke-RestMethod "$BaseUrl/api/v1/searches" -Method Post -Headers $smokeHeaders -ContentType 'application/json' -Body $smokeBody -WebSession $smokeSession
$smokeSnapshot = $null
for ($attempt = 0; $attempt -lt 80; $attempt++) {
    $smokeSnapshot = Invoke-RestMethod "$BaseUrl/api/v1/searches/$($smokeAccepted.search_id)" -WebSession $smokeSession
    if ($smokeSnapshot.state -in @('completed', 'failed', 'cancelled')) { break }
    Start-Sleep -Milliseconds 250
}
if ($smokeSnapshot.state -ne 'completed') { throw 'Demo search did not complete' }
$smokeTripUrl = "$BaseUrl/api/v1/trips/$($smokeAccepted.trip_id)"
$smokeSaved = Invoke-RestMethod "$smokeTripUrl/saved" -Method Put -Headers $smokeHeaders -ContentType 'application/json' -Body '{}' -WebSession $smokeSession
$smokeTrips = Invoke-RestMethod "$BaseUrl/api/v1/trips?saved=true" -WebSession $smokeSession
if ($smokeAccepted.trip_id -notin $smokeTrips.items.trip_id) { throw 'Saved trip missing' }
$smokeSchedule = @{expected_revision=$smokeSaved.revision; start_date='2026-11-10'; end_date='2026-11-11'; timezone='Europe/Rome'} | ConvertTo-Json -Compress
$smokeTrip = Invoke-RestMethod "$smokeTripUrl/schedule" -Method Put -Headers $smokeHeaders -ContentType 'application/json' -Body $smokeSchedule -WebSession $smokeSession
if ($smokeTrip.schedule.start_date -ne '2026-11-10') { throw 'Schedule was not stored' }
$null = Invoke-RestMethod "$smokeTripUrl/saved" -Method Delete -Headers $smokeHeaders -WebSession $smokeSession
$null = Invoke-RestMethod "$BaseUrl/api/v1/session" -Method Delete -Headers $smokeHeaders -WebSession $smokeSession
Write-Output 'PASS: session -> search -> snapshot -> trip -> save -> list -> schedule -> unsave -> logout'
