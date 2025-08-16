UQCS Hackathon Projet For 2025

Project Members:
- Isaac Liggett
- Prabhjot Singh

This project was built on Python 3.10

Run the below script to generate a crt and key. Replace the ip address with your devices ipv4 address and the folder address with your project folder \certs

generate_cert.bat 10.89.152.112 C:\Users\isaac\OneDrive\Documents\CodeProjects\UQCSHackathon\PoseEstimation\certs mypassword

If you wish to use this application over LAN you must use localtunnel which can be installed via npm. A localtunnel server needs to be created for port 8080 and 5000. The domains returned should be placed into tunnels.config.json. 

static - 5000
webrtc - 8080


