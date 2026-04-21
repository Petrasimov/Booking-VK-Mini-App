@echo off
echo Starting Cloudflare Tunnel...
echo.
echo После запуска скопируй URL вида https://xxx.trycloudflare.com
echo и вставь его в настройки VK Mini App.
echo.
set QUIC_GO_ENABLE_GSO=false
%~dp0cloudflared.exe tunnel --url http://localhost:5173 --protocol http2
