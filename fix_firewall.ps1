# Run this as Administrator
$Port = 50000
$RuleName = "P2P File Sharing Discovery (UDP)"

Write-Host "Adding Firewall Rule for Inbound UDP Port $Port..."

# Remove existing rule if any
Remove-NetFirewallRule -DisplayName $RuleName -ErrorAction SilentlyContinue

# Add new rule
New-NetFirewallRule -DisplayName $RuleName `
                    -Direction Inbound `
                    -LocalPort $Port `
                    -Protocol UDP `
                    -Action Allow `
                    -Profile Any

Write-Host "Rule Added Successfully."
Write-Host "Please restart the application and try again."
pause
