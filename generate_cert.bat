@echo off
SETLOCAL

set IP_ADDR=%1
set OUT_DIR=%2
set CERT_PASS=%3

if "%OUT_DIR%"=="" set OUT_DIR=%CD%\certs
if "%CERT_PASS%"=="" set CERT_PASS=mypassword

powershell -ExecutionPolicy Bypass -File "%CD%\generate_cert.ps1" -IP_ADDR "%IP_ADDR%" -OUT_DIR "%OUT_DIR%" -CERT_PASS "%CERT_PASS%"

:: Extract certificate (.crt)
openssl pkcs12 -in "%OUT_DIR%\server.pfx" -clcerts -nokeys -out "%OUT_DIR%\server.crt" -passin pass:%CERT_PASS%

:: Extract private key (.key)
openssl pkcs12 -in "%OUT_DIR%\server.pfx" -nocerts -nodes -out "%OUT_DIR%\server.key" -passin pass:%CERT_PASS%


pause
