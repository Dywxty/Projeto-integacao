const API_BASE = window.WEATHER_API_URL || (window.location.port === '5000' ? '' : 'http://localhost:5000');
const MQTT_CONFIG = { host: 'broker.hivemq.com', port: 8884, path: '/mqtt', topic: 'senai510/lttl/relogio' };

const state = {
    history: [], last: null, lastSource: null, lastUpdatedAt: 0,
    dht: { temperature: null, humidity: null }
};
const POLL_INTERVAL_MS = 15 * 60 * 1000;
const BOARD_CLIMATE_INTERVAL_MS = 10 * 60 * 1000;
let loadingLatest = false;
let mqttReconnectTimer = null;
const $ = (id) => document.getElementById(id);
const number = (value, fallback = null) => {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : fallback;
};
function updateRealtimeClock() {
    const now = new Date();
    const time = now.toLocaleTimeString('pt-BR', {
        timeZone: 'America/Sao_Paulo', hour: '2-digit', minute: '2-digit', second: '2-digit'
    });
    const date = now.toLocaleDateString('pt-BR', {
        timeZone: 'America/Sao_Paulo', day: '2-digit', month: '2-digit', year: 'numeric'
    });
    $('hero-clock').textContent = time;
    $('hero-date').textContent = date;
}
function setConnection(type, online, label) {
    const pill = $(type === 'api' ? 'api-pill' : 'mqtt-pill');
    if (type === 'api') {
        $('api-dot').className = online ? 'online' : '';
        $('api-status').textContent = label;
    }
    if (pill) {
        pill.textContent = online ? 'ONLINE' : label; pill.className = `connection-pill 
        ${online ? 'online' : type === 'mqtt' ? 'pending' : 'offline'}`;
    }
}
function conditionText(data) {
    return data.clima ||
        (data.temperatura >= 30 ? 'Quente' : data.temperatura <= 18 ? 'Frio' : data.umidade
            >= 80 ? 'Úmido' : 'Agradável');
}
function displayTime(data) {
    if (data.data_hora) {
        const parsed = new Date(data.data_hora);
        if (!Number.isNaN(parsed.getTime())) {
            return parsed.toLocaleTimeString('pt-BR', {
                timeZone: 'America/Sao_Paulo', hour: '2-digit', minute: '2-digit'
            });
        }
    }
    return data.hora || '--:--';
}
function updateDashboard(data, source = 'api') {
    if (source === 'mqtt') {
        const sensorTemperature = data.sensor_temperatura === null
            || data.sensor_temperatura === undefined ? null : number(data.sensor_temperatura);
        const sensorHumidity = data.sensor_umidade === null
            || data.sensor_umidade === undefined ? null : number(data.sensor_umidade);
        if (sensorTemperature !== null) state.dht.temperature = sensorTemperature;
        if (sensorHumidity !== null) state.dht.humidity = sensorHumidity;
    }
    const temperature = state.dht.temperature ?? number(data.temperatura, 0);
    const humidity = state.dht.humidity ?? number(data.umidade, 0);
    const condition = conditionText(data);
    const time = displayTime(data);
    $('temperature').textContent = state.dht.temperature === null ? '--' : temperature.toFixed(1);
    $('humidity').textContent = state.dht.humidity === null ? '--' : Math.round(humidity);
    $('condition').textContent = condition;
    $('detail-time').textContent = time;
    $('humidity-meter').style.width = `${Math.max(0, Math.min(100, humidity))}%`;
    $('condition-description').textContent = `${data.sensacao ? `Sensação de ${data.sensacao}°C` : 'Leitura atual do ambiente'} · 
            ${time}`;
    state.last = { ...data, temperatura: temperature, hora: time };
    $('last-sync').textContent = `ÚLTIMA LEITURA ${time}`;
    if (!state.history.some((item) => item.id === data.id && data.id)) state.history.push(state.last);
    state.history = state.history.slice(-12);
    $('detail-count').textContent = state.history.length; renderChart();
}
function renderChart() {
    const chart = $('temperature-chart');
    const points = state.history.filter((item) => Number.isFinite(item.temperatura));
    if (!points.length) return; const width = chart.clientWidth || 500; const height = chart.clientHeight ||
        213; const coordinates = points.map((item, index) => `${(index / Math.max(points.length - 1, 1)) * width},
    ${height - ((item.temperatura - 15) / 20) * height}`).join(' ');
    $('chart-labels').innerHTML = points.slice(-5).map((item) => `<span>${item.hora || '--:--'}</span>`).join('');
    chart.querySelector('.chart-empty')?.remove(); chart.querySelector('.chart-svg')?.remove();
    chart.insertAdjacentHTML('beforeend', `<svg class="chart-svg" viewBox="0 0 ${width} ${height}" 
        preserveAspectRatio="none"><polyline points="${coordinates}" fill="none" stroke="#cbef72" 
        stroke-width="2" vector-effect="non-scaling-stroke"/>${points.map((item, index) => `<circle cx="
            ${(index / Math.max(points.length - 1, 1)) * width}" cy="${height - ((item.temperatura - 15) / 20)
        * height}" r="3" fill="#cbef72"/>`).join('')}</svg>`);
}
async function loadLatest() {
    if (loadingLatest) return;
    loadingLatest = true;
    try {
        const statusResponse = await fetch(`${API_BASE}/status`, { cache: 'no-store' });
        if (statusResponse.ok) {
            const status = await statusResponse.json();
            setConnection('mqtt', status.mqtt, status.mqtt ? 'ONLINE' : 'INDISPONÍVEL');
        }
        const response = await fetch(`${API_BASE}/dados/ultimo`,
            { cache: 'no-store' }); if (!response.ok) throw new Error('API indisponível');
        const data = await response.json(); setConnection('api', true, 'API conectada');
        if (data.dados === null || data.temperatura === undefined) {
            setConnection('api', true, 'API online · sem leituras'); return;

        }
        updateDashboard(data);
        state.lastSource = 'api';
        state.lastUpdatedAt = data.data_hora ? Date.parse(data.data_hora) : Date.now();
        const historyResponse = await fetch(`${API_BASE}/dados`,
            { cache: 'no-store' }); if (historyResponse.ok) {
            const history = await historyResponse.json();
            const orderedHistory = history.slice().reverse().slice(-12);
            state.history = orderedHistory;
            $('detail-count').textContent = history.length;
            renderChart();
        }
    } catch (error) { setConnection('api', false, 'API desconectada'); }
    finally { loadingLatest = false; }
}
async function sendClimateToBoard() {
    try {
        const response = await fetch(`${API_BASE}/clima/publicar`, { method: 'POST' });
        const result = await response.json();
        if (!response.ok) throw new Error(result.erro || 'Falha ao enviar clima para a placa');
        console.info('Clima enviado para a placa:', result.dados);
    } catch (error) {
        console.error('Não foi possível enviar o clima para a placa:', error);
    }
}
function connectMqtt() {
    if (typeof Paho === 'undefined') {
        setConnection('mqtt', false, 'BIBLIOTECA INDISPONÍVEL');
        return;
    }
    try {
        const client = new Paho.MQTT.Client(MQTT_CONFIG.host,
            MQTT_CONFIG.port, MQTT_CONFIG.path, `weather-${Date.now()}`);
        const reconnect = () => {
            if (mqttReconnectTimer) return;
            mqttReconnectTimer = setTimeout(() => {
                mqttReconnectTimer = null;
                connectMqtt();
            }, 5000);
        };
        client.onConnectionLost = (response) => {
            console.error('Conexão MQTT via WebSocket perdida:', response);
            setConnection('mqtt', false, 'OFFLINE');
            reconnect();
        };
        client.onMessageArrived = (message) => {
            try {
                const payload = JSON.parse(message.payloadString.replace(/^\uFEFF/, '').trim());
                if (!payload || Array.isArray(payload) || typeof payload !== 'object') {
                    throw new Error('o payload precisa ser um objeto JSON');
                }
                updateDashboard(payload, 'mqtt');
                state.lastSource = 'mqtt';
                state.lastUpdatedAt = Date.now();
                setConnection('mqtt', true, 'ONLINE');
            } catch (error) {
                console.warn('Mensagem MQTT inválida:', message.payloadString, error);
            }
        };
        client.connect({
            useSSL: true, onSuccess: () => {
                client.subscribe(MQTT_CONFIG.topic); setConnection('mqtt', true, 'ONLINE');
            }, onFailure: (error) => {
                console.error('Falha ao conectar ao MQTT via WebSocket:', error);
                setConnection('mqtt', false, 'INDISPONÍVEL');
                reconnect();
            }
        });
    } catch (error) {
        console.error('Erro ao iniciar cliente MQTT via WebSocket:', error);
        setConnection('mqtt', false, 'INDISPONÍVEL');
    }
}
$('refresh-button').addEventListener('click', () => {
    loadLatest(); $('toast').textContent = 'Atualizando leituras...';
    $('toast').classList.add('show'); setTimeout(() => $('toast').classList.remove('show'), 1800);
});
$('history-button').addEventListener('click', () =>
    document.querySelector('.history-panel').scrollIntoView({ behavior: 'smooth' }));
window.addEventListener('resize', renderChart); updateRealtimeClock();
setInterval(updateRealtimeClock, 1000);
loadLatest(); connectMqtt(); sendClimateToBoard();
setInterval(loadLatest, POLL_INTERVAL_MS);
setInterval(sendClimateToBoard, BOARD_CLIMATE_INTERVAL_MS);
