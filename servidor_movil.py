#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Servidor web → móvil del operario
- Sin dependencias externas (stdlib http.server)
- Se integra con InterfazCaptura vía un objeto "estado"
- HTML auto-refresca cada 2s, con sonidos HTML5 Audio
- Control total: iniciar/cerrar/repetir mesa, brillo, LEDs, auto-calibrar
"""
import http.server
import socketserver
import json
import threading
import socket


HTML_MOVIL = """<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, user-scalable=no">
<title>Solar Drone — Captura</title>
<style>
*{margin:0;padding:0;box-sizing:border-box;-webkit-tap-highlight-color:transparent}
body{font-family:-apple-system,BlinkMacSystemFont,sans-serif;background:#fff;color:#000;padding:10px;font-size:15px}
.header{background:#1565C0;color:#fff;padding:14px;border-radius:8px;margin-bottom:12px;text-align:center}
.header h1{font-size:18px;font-weight:700}
.mesa{background:#FFF9C4;padding:14px;border-radius:8px;margin-bottom:10px;text-align:center;border:3px solid #F57F17}
.mesa .num{font-size:28px;font-weight:900;color:#000}
.col-box{background:#1976D2;color:#fff;padding:18px;border-radius:8px;margin-bottom:10px;text-align:center}
.col-box .titulo{font-size:14px;opacity:0.9}
.col-box .numero{font-size:64px;font-weight:900;line-height:1.1}
.btn{display:block;width:100%;padding:18px;margin:6px 0;font-size:17px;font-weight:700;border:none;border-radius:8px;color:#fff;cursor:pointer}
.btn-start{background:#2E7D32}
.btn-stop{background:#C62828}
.btn-repeat{background:#E65100}
.btn-cal{background:#00695C}
.btn-next{background:#1565C0}
.btn:active{opacity:0.7}
.btn:disabled{background:#BDBDBD;color:#616161}
.grid{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin:10px 0}
.stat{background:#F5F5F5;padding:10px;border-radius:6px;border-left:4px solid #1565C0}
.stat .label{font-size:11px;color:#616161;text-transform:uppercase;font-weight:700}
.stat .val{font-size:20px;font-weight:700;color:#000}
.stat.err{border-left-color:#C62828;background:#FFEBEE}
.stat.ok{border-left-color:#2E7D32;background:#E8F5E9}
.stat.warn{border-left-color:#E65100;background:#FFF3E0}
.gps{padding:10px;border-radius:6px;margin-bottom:10px;text-align:center;font-size:13px;font-weight:700}
.gps.ok{background:#E8F5E9;color:#2E7D32}
.gps.err{background:#FFEBEE;color:#C62828}
.gps.warn{background:#FFF3E0;color:#E65100}
.sem{padding:30px;border-radius:10px;text-align:center;font-size:28px;font-weight:900;margin:12px 0;display:none}
.sem.show{display:block}
.sem.verde{background:#2E7D32;color:#fff}
.sem.rojo{background:#C62828;color:#fff;animation:blink 0.5s infinite}
.sem.ambar{background:#FF8F00;color:#fff}
@keyframes blink{50%{opacity:0.6}}
.sliders{background:#F5F5F5;padding:10px;border-radius:8px;margin-top:10px}
.sliders h3{font-size:13px;margin-bottom:6px;color:#000}
.slider-row{display:flex;align-items:center;gap:8px;margin:6px 0}
.slider-row label{font-size:12px;font-weight:700;min-width:35px}
.slider-row input[type=range]{flex:1;height:30px}
.slider-row .val{min-width:40px;font-weight:700;font-size:14px}
.foto-preview{width:100%;background:#000;border-radius:6px;margin-top:8px;min-height:100px;display:flex;align-items:center;justify-content:center;color:#888;font-size:12px}
.foto-preview img{max-width:100%;border-radius:6px;display:block}
.fotos-row{display:grid;grid-template-columns:1fr 1fr 1fr;gap:4px}
.fotos-row .stat{padding:6px}
.fotos-row .val{font-size:16px}
.codigo-pulse{animation:pulse 0.4s}
@keyframes pulse{0%{background:#2E7D32;color:#fff}100%{background:#FFF9C4;color:#000}}
</style>
</head>
<body>

<div class="mesa">
    <div style="font-size:12px;color:#424242">Sesión actual</div>
    <div class="num" id="mesaNum">—</div>
</div>

<div class="col-box">
    <div class="titulo">CÓDIGOS</div>
    <div class="numero" id="columna">0</div>
</div>

<div class="gps" id="gpsBox">GPS: —</div>

<div id="alarmaHW" style="display:none;background:#C62828;color:#fff;padding:14px;border-radius:8px;font-weight:700;text-align:center;margin:8px 0;animation:blink 0.5s infinite">
    ⚠ <span id="alarmaHWtxt"></span>
</div>

<div class="fotos-row">
    <div class="stat"><div class="label">E1 fotos</div><div class="val" id="e1f">0</div></div>
    <div class="stat"><div class="label">E2 fotos</div><div class="val" id="e2f">0</div></div>
    <div class="stat"><div class="label">E3 fotos</div><div class="val" id="e3f">0</div></div>
</div>

<div class="stat" id="zbarBox" style="display:none;margin-top:6px;border-left-color:#00695C">
    <div class="label">Códigos leídos por visión (pyzbar)</div>
    <div class="val" id="zbarVal">—</div>
</div>

<div class="sem" id="semaforo">—</div>

<button class="btn btn-start" id="btnStart" onclick="cmd('/api/iniciar_mesa')">▶ INICIAR CAPTURA</button>
<button class="btn btn-stop" id="btnStop" onclick="cmd('/api/cerrar_mesa')" style="display:none">■ PARAR CAPTURA</button>
<div id="toast" style="display:none;position:fixed;bottom:20px;left:50%;transform:translateX(-50%);background:#2E7D32;color:#fff;padding:10px 18px;border-radius:6px;font-weight:700;z-index:999;box-shadow:0 2px 8px rgba(0,0,0,0.3)"></div>

<details style="margin-top:14px">
<summary style="padding:10px;background:#F5F5F5;border-radius:8px;font-weight:700;cursor:pointer">⚙ Ajustes (cámaras)</summary>
<div class="sliders">
    <h3>Brillo por escáner (targetWhite)</h3>
    <div id="slidersBox"></div>
    <button class="btn btn-cal" onclick="cmd('/api/auto_calibrar')">🎯 AUTO-CALIBRAR TODOS</button>

    <h3 style="margin-top:16px">Detección códigos local (pyzbar)</h3>
    <div style="font-size:11px;color:#424242;margin-bottom:6px" id="pyzbarInfo">—</div>
    <select id="pyzbarModo" onchange="setPyzbarModo(this.value)" style="width:100%;padding:10px;font-size:14px;border-radius:6px;border:1px solid #999">
        <option value="off">OFF — sin análisis (máximo ahorro batería)</option>
        <option value="cada_3">Cada 3ª foto — bajo consumo (+3 Wh/día)</option>
        <option value="cada_2">Cada 2ª foto — consumo medio (+5 Wh/día)</option>
        <option value="todas">TODAS las fotos — alto consumo (+10 Wh/día)</option>
        <option value="solo_al_cerrar">Solo al cerrar mesa — bajo consumo (+1 Wh/día)</option>
    </select>
</div>
</details>

<div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:4px;margin-top:8px">
    <div style="position:relative"><div style="position:absolute;top:3px;left:6px;background:rgba(0,0,0,0.7);color:#fff;padding:2px 6px;border-radius:4px;font-size:11px;font-weight:700;z-index:1">E1</div><div class="foto-preview" id="fotoBox1">—</div></div>
    <div style="position:relative"><div style="position:absolute;top:3px;left:6px;background:rgba(0,0,0,0.7);color:#fff;padding:2px 6px;border-radius:4px;font-size:11px;font-weight:700;z-index:1">E2</div><div class="foto-preview" id="fotoBox2">—</div></div>
    <div style="position:relative"><div style="position:absolute;top:3px;left:6px;background:rgba(0,0,0,0.7);color:#fff;padding:2px 6px;border-radius:4px;font-size:11px;font-weight:700;z-index:1">E3</div><div class="foto-preview" id="fotoBox3">—</div></div>
</div>

<audio id="aBeep" preload="auto" src="/audio/beep"></audio>
<audio id="aDouble" preload="auto" src="/audio/double"></audio>
<audio id="aAlarm" preload="auto" src="/audio/alarm"></audio>
<audio id="aLost" preload="auto" src="/audio/lost"></audio>

<script>
let lastCol = 0;
let lastGpsOk = true;
let semaforoShowing = false;
let lastDescon = '';
let lastGpsRequerido = true;

async function cmd(url, body){
    const opts = {method:'POST'};
    if(body){opts.headers={'Content-Type':'application/json'};opts.body=JSON.stringify(body);}
    await fetch(url, opts);
    setTimeout(refrescar, 200);
}

function toast(msg, ms){
    const t = document.getElementById('toast');
    t.textContent = msg;
    t.style.display = 'block';
    setTimeout(() => t.style.display = 'none', ms || 1800);
}

async function aplicarBrillo(escId, valor){
    await fetch('/api/set_brillo/' + escId + '/' + valor, {method:'POST'});
    toast('Brillo E' + escId + ' → ' + valor);
}

function setPyzbarModo(modo){
    cmd('/api/set_pyzbar_modo', {modo});
}

function cerrarSemaforo(aceptar){
    fetch('/api/cerrar_semaforo', {method:'POST', headers:{'Content-Type':'application/json'},
          body: JSON.stringify({aceptar})});
    document.getElementById('semaforo').classList.remove('show');
    document.getElementById('btnNext').style.display='none';
    document.getElementById('btnRepeat').style.display='none';
    document.getElementById('btnStart').style.display='block';
    semaforoShowing = false;
    setTimeout(refrescar, 300);
}

async function refrescar(){
    try {
        const r = await fetch('/api/estado');
        const s = await r.json();

        document.getElementById('mesaNum').textContent = s.mesa_nombre || s.mesa_numero;
        document.getElementById('columna').textContent = s.columna_actual + ' / ' + s.columnas_total;
        document.getElementById('e1f').textContent = s.fotos[0] || 0;
        document.getElementById('e2f').textContent = s.fotos[1] || 0;
        document.getElementById('e3f').textContent = s.fotos[2] || 0;

        // pyzbar (si está disponible)
        if(s.detecciones_zbar !== null && s.detecciones_zbar !== undefined){
            document.getElementById('zbarBox').style.display = 'block';
            document.getElementById('zbarVal').textContent = s.detecciones_zbar;
        }

        // Selector de modo pyzbar
        const sel = document.getElementById('pyzbarModo');
        if(sel && s.pyzbar_modo && sel.value !== s.pyzbar_modo){
            sel.value = s.pyzbar_modo;
        }
        const info = document.getElementById('pyzbarInfo');
        if(info){
            if(!s.pyzbar_disponible){
                info.textContent = '⚠ pyzbar no instalado — instala con: pip install pyzbar pillow';
                if(sel) sel.disabled = true;
            } else {
                info.textContent = 'Modo actual: ' + (s.pyzbar_modo || '—');
            }
        }

        // GPS — solo alarma si está requerido
        const gpsEl = document.getElementById('gpsBox');
        const gpsReq = s.gps_requerido;
        lastGpsRequerido = gpsReq;
        if(s.gps_ok && s.gps_lat){
            gpsEl.className = 'gps ok';
            gpsEl.textContent = 'GPS ✓ ' + s.gps_lat.toFixed(5) + ', ' + s.gps_lon.toFixed(5) + ' (' + s.gps_sat + ' sat)';
            lastGpsOk = true;
        } else if(s.gps_connected){
            gpsEl.className = 'gps warn';
            gpsEl.textContent = 'GPS ⏳ buscando satélites…';
            if(lastGpsOk && gpsReq){document.getElementById('aLost').play().catch(()=>{});navigator.vibrate&&navigator.vibrate([200,100,200])}
            lastGpsOk = false;
        } else if(gpsReq){
            gpsEl.className = 'gps err';
            gpsEl.textContent = 'GPS ✗ SIN CONEXIÓN — REQUERIDO';
            if(lastGpsOk){document.getElementById('aLost').play().catch(()=>{});navigator.vibrate&&navigator.vibrate([200,100,200])}
            lastGpsOk = false;
        } else {
            gpsEl.className = 'gps warn';
            gpsEl.textContent = 'GPS no configurado (modo test)';
            lastGpsOk = true;
        }

        // Alarma de escáner desconectado (durante captura)
        const desconEl = document.getElementById('alarmaHW');
        const descon = (s.escaneres_desconectados || []).join(',');
        if(descon){
            desconEl.style.display = 'block';
            document.getElementById('alarmaHWtxt').textContent = 'ESCÁNER E' + descon + ' DESCONECTADO';
            if(descon !== lastDescon){
                document.getElementById('aAlarm').play().catch(()=>{});
                navigator.vibrate && navigator.vibrate([400,200,400,200,400]);
            }
        } else {
            desconEl.style.display = 'none';
        }
        lastDescon = descon;

        // Botones INICIAR/PARAR desde el móvil (manual, el HID también los dispara)
        document.getElementById('btnStart').style.display = s.capturando ? 'none' : 'block';
        document.getElementById('btnStop').style.display  = s.capturando ? 'block' : 'none';

        // Sonido al llegar código nuevo
        if(s.columna_actual > lastCol){
            if(s.columna_actual === s.columnas_total){
                document.getElementById('aDouble').play().catch(()=>{});
                navigator.vibrate && navigator.vibrate([150,80,150]);
            } else {
                document.getElementById('aBeep').play().catch(()=>{});
                navigator.vibrate && navigator.vibrate(80);
            }
        }
        lastCol = s.columna_actual;

        // Semáforo
        if(s.semaforo && s.semaforo.estado && !semaforoShowing){
            const sem = document.getElementById('semaforo');
            sem.className = 'sem show ' + s.semaforo.estado;
            sem.textContent = s.semaforo.estado === 'verde' ? '✓ MESA OK' :
                              s.semaforo.estado === 'ambar' ? '⚠ REVISAR: ' + s.semaforo.motivo :
                              '✗ REPETIR: ' + s.semaforo.motivo;
            document.getElementById('btnStop').style.display = 'none';
            if(s.semaforo.estado === 'verde' || s.semaforo.estado === 'ambar'){
                document.getElementById('btnNext').style.display = 'block';
                document.getElementById('btnRepeat').style.display = 'block';
            } else {
                document.getElementById('btnRepeat').style.display = 'block';
            }
            if(s.semaforo.estado === 'rojo'){
                document.getElementById('aAlarm').play().catch(()=>{});
                navigator.vibrate && navigator.vibrate([500,200,500,200,500]);
            } else if(s.semaforo.estado === 'ambar'){
                document.getElementById('aLost').play().catch(()=>{});
                navigator.vibrate && navigator.vibrate([300,100,300]);
            } else {
                document.getElementById('aDouble').play().catch(()=>{});
                navigator.vibrate && navigator.vibrate([150,80,150,80,150]);
            }
            semaforoShowing = true;
        }

        // Sliders
        const box = document.getElementById('slidersBox');
        if(box.children.length === 0 && s.escaneres){
            s.escaneres.forEach(e => {
                const div = document.createElement('div');
                div.className = 'slider-row';
                div.innerHTML = '<label>E'+e.id+':</label>' +
                    '<input type="range" min="20" max="200" value="'+e.targetWhite+'" id="sl_'+e.id+'" ' +
                    'oninput="document.getElementById(\\'val_\\' + '+e.id+').textContent=this.value" ' +
                    'onchange="aplicarBrillo('+e.id+', this.value)">' +
                    '<span class="val" id="val_'+e.id+'">'+e.targetWhite+'</span>';
                box.appendChild(div);
            });
        }

    } catch(e) {
        console.error(e);
    }
}

// Primera carga y refresh periódico cada 2s (batería)
refrescar();
setInterval(refrescar, 2000);

// Miniatura por escáner cada 5s
function cargarMini(id){
    const img = document.createElement('img');
    img.src = '/api/ultima_foto?e=' + id + '&t=' + Date.now();
    img.onload = () => {
        const box = document.getElementById('fotoBox' + id);
        box.innerHTML = '';
        box.appendChild(img);
    };
    img.onerror = () => {};
}
setInterval(() => { cargarMini(1); cargarMini(2); cargarMini(3); }, 5000);
</script>
</body>
</html>
"""


def generar_beep_wav(freq_hz, dur_ms, volumen=0.5):
    """Genera un WAV sinusoidal simple (PCM 16-bit mono 8kHz)"""
    import struct
    import math
    sample_rate = 8000
    n_samples = int(sample_rate * dur_ms / 1000)
    samples = []
    for i in range(n_samples):
        t = i / sample_rate
        # Envolvente exponencial para que no chasquee
        env = math.exp(-3 * t / (dur_ms / 1000))
        v = int(32767 * volumen * env * math.sin(2 * math.pi * freq_hz * t))
        samples.append(struct.pack('<h', v))
    data = b''.join(samples)
    # Cabecera WAV
    wav = (b'RIFF' + struct.pack('<I', 36 + len(data)) + b'WAVE' +
           b'fmt ' + struct.pack('<IHHIIHH', 16, 1, 1, sample_rate, sample_rate * 2, 2, 16) +
           b'data' + struct.pack('<I', len(data)) + data)
    return wav


def concatenar_beeps(beeps_params):
    """Genera WAV con varios beeps con silencio entre ellos
    beeps_params: [(freq, dur_ms, pausa_ms), ...]"""
    import struct
    import math
    sample_rate = 8000
    data = bytearray()
    for freq, dur, pausa in beeps_params:
        n = int(sample_rate * dur / 1000)
        for i in range(n):
            t = i / sample_rate
            env = math.exp(-3 * t / (dur / 1000))
            v = int(32767 * 0.5 * env * math.sin(2 * math.pi * freq * t))
            data.extend(struct.pack('<h', v))
        n_silencio = int(sample_rate * pausa / 1000)
        data.extend(b'\x00\x00' * n_silencio)
    wav = (b'RIFF' + struct.pack('<I', 36 + len(data)) + b'WAVE' +
           b'fmt ' + struct.pack('<IHHIIHH', 16, 1, 1, sample_rate, sample_rate * 2, 2, 16) +
           b'data' + struct.pack('<I', len(data)) + bytes(data))
    return wav


# Sonidos precomputados
_audio_cache = {}
def get_audio(nombre):
    if nombre in _audio_cache:
        return _audio_cache[nombre]
    if nombre == 'beep':
        w = generar_beep_wav(1000, 120)
    elif nombre == 'double':
        w = concatenar_beeps([(1500, 150, 80), (1500, 150, 0)])
    elif nombre == 'alarm':
        w = concatenar_beeps([(2000, 200, 100), (1500, 200, 100), (2000, 200, 100), (1500, 300, 0)])
    elif nombre == 'lost':
        w = generar_beep_wav(600, 500)
    else:
        w = generar_beep_wav(1000, 100)
    _audio_cache[nombre] = w
    return w


class ServidorMovil:
    """Servidor HTTP integrado con InterfazCaptura (se le pasa como 'app')"""
    def __init__(self, app, puerto=8080):
        self.app = app  # referencia a InterfazCaptura
        self.puerto = puerto
        self.thread = None
        self.server = None

    def iniciar(self):
        handler = _hacer_handler(self.app)
        self.server = socketserver.ThreadingTCPServer(("0.0.0.0", self.puerto), handler)
        self.server.daemon_threads = True
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        ips = _obtener_ips()
        print(f"\n{'='*60}")
        print(f"  SERVIDOR MÓVIL ESCUCHANDO")
        print(f"  Abre en el móvil (conectado al hotspot):")
        for ip in ips:
            print(f"     → http://{ip}:{self.puerto}")
        print(f"{'='*60}\n")
        return ips

    def parar(self):
        if self.server:
            self.server.shutdown()


def _obtener_ips():
    """Devuelve todas las IPs locales (excluye loopback)"""
    ips = set()
    try:
        hostname = socket.gethostname()
        for info in socket.getaddrinfo(hostname, None):
            ip = info[4][0]
            if ip and not ip.startswith('127.') and ':' not in ip:
                ips.add(ip)
    except Exception:
        pass
    try:
        # Fallback más fiable
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ips.add(s.getsockname()[0])
        s.close()
    except Exception:
        pass
    return sorted(ips) or ['<IP local>']


def _hacer_handler(app):
    class Handler(http.server.BaseHTTPRequestHandler):
        def log_message(self, *args): pass  # silencio

        def _json(self, data, code=200):
            body = json.dumps(data).encode('utf-8')
            self.send_response(code)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _ok(self):
            self._json({"ok": True})

        def do_GET(self):
            try:
                if self.path == '/' or self.path.startswith('/?'):
                    body = HTML_MOVIL.encode('utf-8')
                    self.send_response(200)
                    self.send_header('Content-Type', 'text/html; charset=utf-8')
                    self.send_header('Content-Length', str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                elif self.path == '/api/estado':
                    self._json(app.estado_para_movil())
                elif self.path.startswith('/api/ultima_foto'):
                    # Soporta ?e=N para seleccionar escáner específico
                    esc_id = None
                    if '?' in self.path:
                        qs = self.path.split('?', 1)[1]
                        from urllib.parse import parse_qs
                        params = parse_qs(qs)
                        if 'e' in params:
                            try: esc_id = int(params['e'][0])
                            except Exception: esc_id = None
                    data = app.ultima_foto_miniatura(esc_id)
                    if data:
                        self.send_response(200)
                        self.send_header('Content-Type', 'image/jpeg')
                        self.send_header('Cache-Control', 'no-cache')
                        self.send_header('Content-Length', str(len(data)))
                        self.end_headers()
                        self.wfile.write(data)
                    else:
                        self.send_response(404); self.end_headers()
                elif self.path.startswith('/audio/'):
                    nombre = self.path.split('/')[-1]
                    data = get_audio(nombre)
                    self.send_response(200)
                    self.send_header('Content-Type', 'audio/wav')
                    self.send_header('Content-Length', str(len(data)))
                    self.end_headers()
                    self.wfile.write(data)
                else:
                    self.send_response(404); self.end_headers()
            except (BrokenPipeError, ConnectionResetError):
                pass
            except Exception as e:
                try:
                    self._json({"error": str(e)}, 500)
                except Exception:
                    pass

        def do_POST(self):
            try:
                length = int(self.headers.get('Content-Length', 0))
                body = self.rfile.read(length).decode('utf-8') if length else ''
                data = json.loads(body) if body else {}

                if self.path == '/api/iniciar_mesa':
                    app.iniciar_captura_desde_movil()
                    self._ok()
                elif self.path == '/api/cerrar_mesa':
                    app.cerrar_captura_desde_movil()
                    self._ok()
                elif self.path == '/api/cerrar_semaforo':
                    aceptar = data.get('aceptar', False)
                    app.cerrar_semaforo_desde_movil(aceptar)
                    self._ok()
                elif self.path.startswith('/api/set_brillo/'):
                    partes = self.path.split('/')
                    esc_id = int(partes[3]); valor = int(partes[4])
                    app.set_brillo_desde_movil(esc_id, valor)
                    self._ok()
                elif self.path == '/api/auto_calibrar':
                    app.auto_calibrar_desde_movil()
                    self._ok()
                elif self.path == '/api/simular_codigo':
                    codigo = data.get('codigo', '')
                    app.simular_codigo_desde_movil(codigo)
                    self._ok()
                elif self.path == '/api/set_pyzbar_modo':
                    modo = data.get('modo', 'cada_3')
                    app.set_pyzbar_modo(modo)
                    self._ok()
                else:
                    self.send_response(404); self.end_headers()
            except (BrokenPipeError, ConnectionResetError):
                pass
            except Exception as e:
                try:
                    self._json({"error": str(e)}, 500)
                except Exception:
                    pass
    return Handler
