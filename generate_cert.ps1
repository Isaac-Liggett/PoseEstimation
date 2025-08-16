param(
    [string]$IP_ADDR,
    [string]$OUT_DIR = "$PWD\certs",
    [string]$CERT_PASS = "mypassword"
)

if (-not (Test-Path $OUT_DIR)) { New-Item -ItemType Directory -Path $OUT_DIR }

# Generate self-signed cert in CurrentUser store
$cert = New-SelfSignedCertificate -DnsName $IP_ADDR -CertStoreLocation 'Cert:\CurrentUser\My' -NotAfter (Get-Date).AddYears(1)

# Save thumbprint
$cert.Thumbprint | Out-File -FilePath "$OUT_DIR\thumb.txt" -Encoding ascii

# Export .crt
Export-Certificate -Cert "Cert:\CurrentUser\My\$($cert.Thumbprint)" -FilePath "$OUT_DIR\server.crt"

# Export .pfx
$pwd = ConvertTo-SecureString -String $CERT_PASS -Force -AsPlainText
Export-PfxCertificate -Cert "Cert:\CurrentUser\My\$($cert.Thumbprint)" -FilePath "$OUT_DIR\server.pfx" -Password $pwd

# Extract private key using OpenSSL
& openssl pkcs12 -in "$OUT_DIR\server.pfx" -nocerts -nodes -out "$OUT_DIR\server.key" -passin pass:$CERT_PASS

Write-Output "Done!"
Write-Output "Certificate: $OUT_DIR\server.crt"
Write-Output "Private key: $OUT_DIR\server.key"
