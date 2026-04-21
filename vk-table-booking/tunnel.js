/**
 * Tunnel для VK Mini App через standalone ngrok.exe
 * Не использует npm-пакет @ngrok/ngrok (его нативный .node файл блокируется WDAC).
 * Запускает ngrok.exe напрямую через child_process.
 */

import { spawn } from 'child_process';
import { existsSync } from 'fs';
import { join, dirname } from 'path';
import { fileURLToPath } from 'url';
import dotenv from 'dotenv';

dotenv.config();

const __dirname = dirname(fileURLToPath(import.meta.url));
const PORT = 5173;
const AUTHTOKEN = process.env.NGROK_AUTHTOKEN;

function findNgrok() {
    const candidates = [
        join(__dirname, 'ngrok.exe'),
        join(__dirname, 'ngrok'),
    ];
    for (const p of candidates) {
        if (existsSync(p)) return p;
    }
    return 'ngrok'; // попробовать из PATH
}

async function getNgrokUrl(retries = 15) {
    for (let i = 0; i < retries; i++) {
        await new Promise(r => setTimeout(r, 1000));
        try {
            const res = await fetch('http://localhost:4040/api/tunnels');
            const data = await res.json();
            const tunnel = data.tunnels?.find(t => t.proto === 'https');
            if (tunnel) return tunnel.public_url;
        } catch {}
    }
    return null;
}

async function startTunnel() {
    const ngrokBin = findNgrok();

    if (!AUTHTOKEN && ngrokBin !== 'ngrok') {
        console.warn('⚠️  NGROK_AUTHTOKEN не задан в .env — работаем без авторизации (ограниченный режим)\n');
    }

    const args = ['http', String(PORT)];
    if (AUTHTOKEN) {
        args.push('--authtoken', AUTHTOKEN);
    }

    console.log('🚀 Запуск ngrok туннеля...\n');

    const proc = spawn(ngrokBin, args, {
        stdio: ['ignore', 'ignore', 'pipe'],
        shell: false,
        detached: false,
    });

    proc.stderr.on('data', (d) => {
        const text = d.toString();
        if (!text.includes('INF') && !text.includes('DBG')) {
            process.stderr.write(text);
        }
    });

    proc.on('error', (err) => {
        if (err.code === 'ENOENT') {
            console.error('❌ ngrok.exe не найден!\n');
            console.log('📥 Скачайте ngrok.exe (Windows AMD64):');
            console.log('   https://ngrok.com/download\n');
            console.log('   Распакуйте и положите ngrok.exe в папку:');
            console.log(`   ${__dirname}\n`);
            console.log('💡 Или добавьте ngrok в PATH и запустите снова.\n');
        } else {
            console.error(`❌ Ошибка запуска ngrok: ${err.message}`);
        }
        process.exit(1);
    });

    proc.on('close', (code) => {
        if (code !== 0 && code !== null) {
            console.error(`\n❌ ngrok завершился с кодом ${code}`);
        }
        process.exit(0);
    });

    console.log('⏳ Ожидание подключения...');
    const url = await getNgrokUrl();

    if (url) {
        console.log('\n' + '='.repeat(55));
        console.log('✅ ТУННЕЛЬ ЗАПУЩЕН!');
        console.log(`🌐 URL: ${url}`);
        console.log('='.repeat(55));
        console.log('\n📋 Вставьте этот URL в настройки VK Mini App:');
        console.log('   vk.com → Управление → Приложение → URL приложения\n');
        console.log('⏸️  Ctrl+C для остановки\n');
    } else {
        console.warn('⚠️  URL не получен за 15 сек. Проверьте http://localhost:4040\n');
    }

    process.on('SIGINT', () => {
        console.log('\n🛑 Остановка туннеля...');
        proc.kill();
        process.exit(0);
    });
}

startTunnel();
