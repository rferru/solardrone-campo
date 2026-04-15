#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Sistema de Captura Solar Drone v5.0 — Windows
Mejoras sobre v1:
- CSV se escribe a cada código (no al final) → nada se pierde si crashea
- GPS log continuo en gps_log.csv
- Reconexión automática de GPS y escáneres si se pierden
- Log de eventos (log.txt) con timestamps
- Guardado garantizado al cerrar ventana (WM_DELETE + atexit)
- Lectura HID robusta: captura teclas en toda la ventana, tolerante a foco perdido
- Config leída con ruta absoluta siempre
"""

import tkinter as tk
from tkinter import messagebox
import threading
import serial
import serial.tools.list_ports
import time
import os
import sys
import csv
import json
import atexit
import traceback
from datetime import datetime, timezone

try:
    import winsound
    BEEP_DISPONIBLE = True
except ImportError:
    BEEP_DISPONIBLE = False

# pyzbar opcional para decodificar Code128 en local
try:
    from pyzbar.pyzbar import decode as zbar_decode
    from PIL import Image as PIL_Image
    PYZBAR_DISPONIBLE = True
except ImportError:
    PYZBAR_DISPONIBLE = False

import io as _io
import queue as _queue

COLUMNAS_TOTAL = 14
BAUDRATE_ESCANER = 115200
BAUDRATE_GPS = 9600
RUTA_SCRIPT = os.path.dirname(os.path.abspath(__file__))
RUTA_CAPTURAS = os.path.join(RUTA_SCRIPT, "capturas")
RUTA_LOG = os.path.join(RUTA_SCRIPT, "log.txt")

# VID/PID de Honeywell (para redetectar si cambia de puerto COM)
HONEYWELL_VIDS = {0x0C2E, 0x05E0}  # Honeywell / Symbol


def beep(freq=1000, dur=150):
    if BEEP_DISPONIBLE:
        try:
            winsound.Beep(freq, dur)
        except Exception:
            pass


def log(msg):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
    linea = f"[{ts}] {msg}"
    print(linea)
    try:
        with open(RUTA_LOG, 'a', encoding='utf-8') as f:
            f.write(linea + "\n")
            f.flush()
    except Exception:
        pass


class EscanerFotos:
    # Registro compartido entre instancias: {serial_number_hw: puerto_actual}
    # Sirve para que si Windows cambia el COM, podamos redetectar por hardware_id
    _puertos_ocupados = set()

    def __init__(self, escaner_id, puerto, targetWhite=80, leds=True, serial_number_hw=None):
        self.escaner_id = escaner_id
        self.puerto = puerto  # COM "preferido" (del config.json), puede cambiar
        self.serial_number_hw = serial_number_hw  # nº serie USB — identifica el dispositivo físico
        self.targetWhite = targetWhite
        self.leds = leds
        self.serial = None
        self.capturando = False
        self.thread = None
        self.carpeta = None
        self.contador = 0
        self.errores_seguidos = 0

    def _identificar_serial_hw(self):
        """Lee el nº de serie USB del puerto actual"""
        for p in serial.tools.list_ports.comports():
            if p.device == self.puerto:
                if p.serial_number:
                    self.serial_number_hw = p.serial_number
                return True
        return False

    def _buscar_puerto_alternativo(self):
        """Busca el dispositivo físico (por nº serie USB) aunque haya cambiado de COM.
        Fallback: Honeywell libre por VID."""
        # 1º: match exacto por serial_number USB (dispositivo físico mismo, COM distinto)
        if self.serial_number_hw:
            for p in serial.tools.list_ports.comports():
                if p.serial_number == self.serial_number_hw:
                    return p.device
        # 2º: Honeywell libre por VID
        for p in serial.tools.list_ports.comports():
            if p.vid in HONEYWELL_VIDS and p.device not in EscanerFotos._puertos_ocupados:
                return p.device
        return None

    def conectar(self):
        # Si tenemos serial_number guardado y el COM del config no coincide, priorizar el COM que lo tenga
        if self.serial_number_hw:
            for p in serial.tools.list_ports.comports():
                if p.serial_number == self.serial_number_hw and p.device != self.puerto:
                    log(f"⟳ E{self.escaner_id} dispositivo (SN={self.serial_number_hw}) detectado en {p.device} (config decía {self.puerto})")
                    self.puerto = p.device
                    break
        try:
            self.serial = serial.Serial(self.puerto, BAUDRATE_ESCANER, timeout=0.1)
            time.sleep(0.3)
            self._identificar_serial_hw()
            EscanerFotos._puertos_ocupados.add(self.puerto)
            log(f"✓ E{self.escaner_id} conectado en {self.puerto} (SN={self.serial_number_hw}, tW={self.targetWhite})")
            return True
        except Exception as e:
            log(f"✗ Error conectando E{self.escaner_id} ({self.puerto}): {e}")
            return False

    def reconectar(self):
        """Cierra, busca nuevo COM si el dispositivo cambió, intenta reabrir"""
        EscanerFotos._puertos_ocupados.discard(self.puerto)
        try:
            if self.serial and self.serial.is_open:
                self.serial.close()
        except Exception:
            pass
        time.sleep(0.5)
        # Intentar primero el puerto original (lo más común: Windows le da el mismo COM)
        if self.conectar():
            return True
        # Si falló, buscar el MISMO dispositivo físico en otro COM
        nuevo = self._buscar_puerto_alternativo()
        if nuevo and nuevo != self.puerto:
            log(f"⟳ E{self.escaner_id} cambió de COM: {self.puerto} → {nuevo}")
            self.puerto = nuevo
            return self.conectar()
        return False

    def desconectar(self):
        self.detener()
        if self.serial and self.serial.is_open:
            try:
                self.serial.close()
            except Exception:
                pass

    def iniciar(self, carpeta):
        self.carpeta = carpeta
        os.makedirs(carpeta, exist_ok=True)
        self.capturando = True
        self.thread = threading.Thread(target=self._bucle, daemon=True)
        self.thread.start()

    def detener(self):
        self.capturando = False
        if self.thread:
            self.thread.join(timeout=2.0)

    def _solicitar_foto(self):
        """Captura con LEDs + q90 (óptimo validado 2026-04-15)"""
        luz = "1L" if self.leds else "0L"
        comando = f"\x16M\rIMGSNP1P{luz}{self.targetWhite}W;IMGSHP6F90J.\r".encode()
        self.serial.write(comando)

    def _bucle(self):
        while self.capturando:
            try:
                if not self.serial or not self.serial.is_open:
                    log(f"⚠ E{self.escaner_id} serial cerrado, reconectando…")
                    if not self.reconectar():
                        time.sleep(2)
                        continue

                self.serial.reset_input_buffer()
                self._solicitar_foto()

                data = bytearray()
                # 4s máx (q90 tarda más que q60)
                for _ in range(400):
                    if not self.capturando:
                        break
                    if self.serial.in_waiting > 0:
                        chunk = self.serial.read(self.serial.in_waiting)
                        data.extend(chunk)
                        if b'\xff\xd9' in data:
                            break
                    time.sleep(0.01)

                start = data.find(b'\xff\xd8')
                end = data.find(b'\xff\xd9', start)

                if start >= 0 and end > start:
                    jpeg = bytes(data[start:end+2])
                    # Notificar al app para miniatura móvil (callback opcional)
                    cb = getattr(self, 'on_foto_guardada', None)
                    if cb:
                        try: cb(jpeg)
                        except Exception: pass
                    ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
                    self.contador += 1
                    nombre = f"E{self.escaner_id}_{ts}_{self.contador:04d}.jpg"
                    ruta = os.path.join(self.carpeta, nombre)
                    with open(ruta, 'wb') as f:
                        f.write(jpeg)
                    self.errores_seguidos = 0
                else:
                    self.errores_seguidos += 1
                    if self.errores_seguidos % 3 == 1:
                        log(f"⚠ E{self.escaner_id} sin foto ({self.errores_seguidos} seguidas)")
                    # Reconectar tras 5 errores (~15s) — antes de perder la mesa entera
                    if self.errores_seguidos >= 5:
                        log(f"⚠ E{self.escaner_id} reconectando tras {self.errores_seguidos} errores")
                        self.reconectar()
                        self.errores_seguidos = 0

            except serial.SerialException as e:
                log(f"✗ E{self.escaner_id} SerialException: {e} → reconectar")
                self.reconectar()
                time.sleep(0.5)
            except Exception as e:
                log(f"✗ E{self.escaner_id} error: {e}")
                time.sleep(0.5)


class LectorGPS:
    def __init__(self, puerto):
        self.puerto = puerto
        self.serial_number_hw = None  # nº serie USB del dispositivo físico
        self.serial = None
        self.activo = False
        self.thread = None
        self.lat = None
        self.lon = None
        self.alt = None
        self.satelites = 0
        self.hdop = None
        self.conectado = False
        self.ultima_lectura = None
        self.callback_perdida = None
        self.gps_log_file = None
        self.gps_log_writer = None

    def conectar(self):
        try:
            self.serial = serial.Serial(self.puerto, BAUDRATE_GPS, timeout=1.0)
            time.sleep(0.3)
            log(f"✓ GPS conectado en {self.puerto}")
            return True
        except Exception as e:
            log(f"✗ Error conectando GPS ({self.puerto}): {e}")
            return False

    def reconectar(self):
        try:
            if self.serial and self.serial.is_open:
                self.serial.close()
        except Exception:
            pass
        time.sleep(0.5)
        return self.conectar()

    def abrir_log(self, ruta_csv):
        """Abre un CSV global para el log continuo de GPS"""
        nuevo = not os.path.exists(ruta_csv)
        self.gps_log_file = open(ruta_csv, 'a', newline='', encoding='utf-8')
        self.gps_log_writer = csv.writer(self.gps_log_file)
        if nuevo:
            self.gps_log_writer.writerow(['timestamp', 'lat', 'lon', 'alt', 'satelites', 'hdop'])
            self.gps_log_file.flush()

    def cerrar_log(self):
        if self.gps_log_file:
            try:
                self.gps_log_file.flush()
                self.gps_log_file.close()
            except Exception:
                pass
            self.gps_log_file = None
            self.gps_log_writer = None

    def iniciar(self):
        self.activo = True
        self.thread = threading.Thread(target=self._bucle, daemon=True)
        self.thread.start()

    def desconectar(self):
        self.activo = False
        if self.thread:
            self.thread.join(timeout=2.0)
        self.cerrar_log()
        if self.serial and self.serial.is_open:
            try:
                self.serial.close()
            except Exception:
                pass

    def _parse_gga(self, linea):
        """Parsea línea NMEA GGA, devuelve True si hay fix"""
        partes = linea.split(',')
        if len(partes) < 10:
            return False
        fix = partes[6]
        if fix == '' or fix == '0':
            return False
        try:
            if partes[2] and partes[3]:
                lat_raw = float(partes[2])
                lat_deg = int(lat_raw / 100)
                lat_min = lat_raw - (lat_deg * 100)
                lat = lat_deg + (lat_min / 60.0)
                if partes[3] == 'S':
                    lat = -lat
                self.lat = lat
            if partes[4] and partes[5]:
                lon_raw = float(partes[4])
                lon_deg = int(lon_raw / 100)
                lon_min = lon_raw - (lon_deg * 100)
                lon = lon_deg + (lon_min / 60.0)
                if partes[5] == 'W':
                    lon = -lon
                self.lon = lon
            if partes[7]:
                self.satelites = int(partes[7])
            if partes[8]:
                self.hdop = float(partes[8])
            if partes[9]:
                self.alt = float(partes[9])
            return True
        except Exception:
            return False

    def _bucle(self):
        ultimo_guardado = 0
        while self.activo:
            try:
                if not self.serial or not self.serial.is_open:
                    log("⚠ GPS serial cerrado, reconectando…")
                    if not self.reconectar():
                        time.sleep(2)
                        continue

                linea = self.serial.readline().decode('ascii', errors='ignore').strip()
                if linea.startswith(('$GPGGA', '$GNGGA')):
                    if self._parse_gga(linea):
                        self.conectado = True
                        self.ultima_lectura = time.time()
                        # Guardar al log cada ~1s
                        if self.gps_log_writer and (time.time() - ultimo_guardado) >= 1.0:
                            ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
                            self.gps_log_writer.writerow([ts, self.lat, self.lon, self.alt,
                                                         self.satelites, self.hdop])
                            self.gps_log_file.flush()
                            ultimo_guardado = time.time()

                if self.ultima_lectura and (time.time() - self.ultima_lectura) > 5:
                    if self.conectado:
                        self.conectado = False
                        log("⚠ GPS señal perdida (sin datos >5s)")
                        if self.callback_perdida:
                            self.callback_perdida()

            except serial.SerialException as e:
                log(f"✗ GPS SerialException: {e} → reconectar")
                self.conectado = False
                self.reconectar()
                time.sleep(1)
            except Exception as e:
                log(f"✗ GPS error: {e}")
                time.sleep(0.5)


class InterfazCaptura:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Solar Drone - Captura v5.0")
        self.root.geometry("850x650")
        self.root.configure(bg='#f0f0f0')

        self.config = self.cargar_config()
        self.capturando = False
        self.mesa_numero = 1
        self.mesa_nombre = ""
        self.carpeta_mesa = None
        self.columna_actual = 0
        self.codigos_unicos = set()

        # CSV incremental
        self.csv_file = None
        self.csv_writer = None
        self.csv_path = None

        # Hardware
        self.escaneres_fotos = []
        self.gps = None

        # HID buffer
        self.hid_buffer = ""
        self.hid_ultimo = time.time()

        # Semáforo pendiente (resultado al cerrar mesa, esperando aceptación del operario)
        self.semaforo_pendiente = None  # dict con {estado, motivo, ...} o None

        # Para miniatura móvil: guardar última foto bytes en memoria
        self._ultima_foto_bytes = None
        self._ultima_foto_lock = threading.Lock()

        # Detección pyzbar async (cola + worker)
        self.pyzbar_queue = _queue.Queue(maxsize=50)  # evitar memoria infinita
        self.pyzbar_contador = 0  # global rate limit
        self.detecciones_zbar = {1: 0, 2: 0, 3: 0}  # códigos detectados por escáner en mesa actual
        if PYZBAR_DISPONIBLE:
            threading.Thread(target=self._pyzbar_worker, daemon=True).start()
            log("✓ pyzbar disponible — detección local activa")
        else:
            log("⚠ pyzbar no instalado — sin detección local de códigos")

        os.makedirs(RUTA_CAPTURAS, exist_ok=True)

        self.crear_interfaz()

        # Arrancar GPS + log continuo antes de capturar
        self.root.after(300, self.conectar_gps)
        self.root.after(600, self.conectar_escaneres)

        # Arrancar servidor móvil (después de todo lo demás)
        self.root.after(1000, self._arrancar_servidor_movil)

        self.root.bind('<Button-1>', self.click_izquierdo)
        self.root.bind('<Button-2>', self.click_rueda)
        self.root.bind('<KeyPress>', self.tecla_presionada)
        self.root.protocol("WM_DELETE_WINDOW", self.cerrar_ventana)

        atexit.register(self.cleanup)
        self.actualizar_interfaz()

    def _arrancar_servidor_movil(self):
        try:
            from servidor_movil import ServidorMovil
            self.servidor_movil = ServidorMovil(self, puerto=8080)
            ips = self.servidor_movil.iniciar()
            log(f"✓ Servidor móvil activo en puerto 8080 — IPs: {ips}")
        except Exception as e:
            log(f"⚠ No se pudo arrancar servidor móvil: {e}")
            self.servidor_movil = None

    def cargar_config(self):
        ruta = os.path.join(RUTA_SCRIPT, "config.json")
        if os.path.exists(ruta):
            try:
                with open(ruta, 'r', encoding='utf-8') as f:
                    cfg = json.load(f)
                log(f"✓ Config leída: {ruta}")
                return cfg
            except Exception as e:
                log(f"✗ Error leyendo config: {e}")
        log(f"⚠ No existe {ruta}, usando defaults")
        return {
            "escaner_fotos_1": {"puerto": "COM3", "targetWhite": 80, "leds": True},
            "escaner_fotos_2": {"puerto": "COM4", "targetWhite": 80, "leds": True},
            "escaner_fotos_3": {"puerto": "COM5", "targetWhite": 80, "leds": True},
            "puerto_gps": "COM6"
        }

    def _get_escaner_cfg(self, i):
        """Compatible con config v4 (string) y v5 (dict con serial_number)"""
        v = self.config.get(f"escaner_fotos_{i}")
        if isinstance(v, dict):
            return (v.get("puerto", ""), v.get("targetWhite", 80),
                    v.get("leds", True), v.get("serial_number", "") or None)
        elif isinstance(v, str):
            return v, 80, False, None
        return "", 80, False, None

    def crear_interfaz(self):
        frame_titulo = tk.Frame(self.root, bg='#2c3e50', height=70)
        frame_titulo.pack(fill=tk.X)
        tk.Label(frame_titulo, text="SOLAR DRONE v5.0", font=('Arial', 22, 'bold'),
                fg='white', bg='#2c3e50').pack(pady=12)

        frame_main = tk.Frame(self.root, bg='#f0f0f0')
        frame_main.pack(fill=tk.BOTH, expand=True, padx=20, pady=15)

        self.label_mesa = tk.Label(frame_main, text="Mesa: ---", font=('Arial', 16), bg='#f0f0f0')
        self.label_mesa.pack(pady=5)

        frame_col = tk.Frame(frame_main, bg='#3498db', relief=tk.RAISED, bd=3)
        frame_col.pack(pady=15, padx=50, fill=tk.X)
        tk.Label(frame_col, text="COLUMNA", font=('Arial', 12),
                bg='#3498db', fg='white').pack(pady=3)
        self.label_columna = tk.Label(frame_col, text=f"0 / {COLUMNAS_TOTAL}",
                                      font=('Arial', 44, 'bold'), bg='#3498db', fg='white')
        self.label_columna.pack(pady=8)

        # GPS
        frame_gps = tk.Frame(frame_main, bg='#ecf0f1', relief=tk.GROOVE, bd=2)
        frame_gps.pack(pady=8, fill=tk.X)
        self.label_gps = tk.Label(frame_gps, text="GPS: Conectando…",
                                 font=('Arial', 11), bg='#ecf0f1', fg='#e74c3c')
        self.label_gps.pack(pady=5)

        # Escáneres
        frame_esc = tk.Frame(frame_main, bg='#ecf0f1', relief=tk.GROOVE, bd=2)
        frame_esc.pack(pady=5, fill=tk.X)
        self.label_escaneres = tk.Label(frame_esc, text="Escáneres: —",
                                        font=('Arial', 10), bg='#ecf0f1', fg='#7f8c8d')
        self.label_escaneres.pack(pady=5)

        # Contador fotos (por escáner)
        self.label_fotos = tk.Label(frame_main, text="Fotos: —",
                                    font=('Arial', 10), bg='#f0f0f0', fg='#7f8c8d')
        self.label_fotos.pack(pady=3)

        self.label_estado = tk.Label(frame_main,
                                     text="Click izquierdo o rueda = Iniciar/Detener captura",
                                     font=('Arial', 10), bg='#f0f0f0', fg='#7f8c8d')
        self.label_estado.pack(pady=10)

        frame_btn = tk.Frame(frame_main, bg='#f0f0f0')
        frame_btn.pack(pady=8)

        self.btn_siguiente = tk.Button(frame_btn, text="SIGUIENTE MESA",
                                       font=('Arial', 12, 'bold'),
                                       bg='#27ae60', fg='white',
                                       command=self.siguiente_mesa, state=tk.DISABLED)
        self.btn_siguiente.pack(side=tk.LEFT, padx=5)

        self.btn_brillo = tk.Button(frame_btn, text="⚙ AJUSTAR BRILLO",
                                    font=('Arial', 12, 'bold'),
                                    bg='#1565C0', fg='white',
                                    command=self.abrir_ajuste_brillo)
        self.btn_brillo.pack(side=tk.LEFT, padx=5)

    def abrir_ajuste_brillo(self):
        """Ventana modal con sliders de brillo (targetWhite) por escáner.
        Los cambios se aplican en la siguiente foto que tome cada escáner."""
        if not self.escaneres_fotos:
            messagebox.showinfo("Sin escáneres", "Aún no hay escáneres conectados.")
            return

        win = tk.Toplevel(self.root)
        win.title("Ajuste de brillo en vivo")
        win.geometry("520x420")
        win.configure(bg='white')
        win.transient(self.root)
        win.grab_set()

        tk.Label(win, text="AJUSTE DE BRILLO (en vivo)",
                font=('Arial', 16, 'bold'), bg='white', fg='black').pack(pady=12)
        tk.Label(win,
                text="Mueve el slider → se aplica en la siguiente foto del escáner",
                font=('Arial', 10), bg='white', fg='gray').pack()

        for e in self.escaneres_fotos:
            frame = tk.LabelFrame(win, text=f" Escáner {e.escaner_id}  (puerto {e.puerto}) ",
                                  font=('Arial', 11, 'bold'),
                                  bg='#FFF9C4', fg='black', relief=tk.RIDGE, bd=2)
            frame.pack(fill=tk.X, padx=15, pady=8)

            row = tk.Frame(frame, bg='#FFF9C4')
            row.pack(fill=tk.X, padx=10, pady=8)

            tk.Label(row, text="Brillo (targetWhite):", font=('Arial', 11, 'bold'),
                    bg='#FFF9C4', fg='black').pack(side=tk.LEFT)

            var_white = tk.IntVar(value=e.targetWhite)
            slider = tk.Scale(row, from_=20, to=200, orient=tk.HORIZONTAL,
                             length=240, bg='#FFF9C4', fg='black',
                             troughcolor='#FFE082', highlightthickness=0,
                             font=('Arial', 10, 'bold'),
                             variable=var_white,
                             command=lambda v, esc=e: self._cambiar_brillo(esc, int(float(v))))
            slider.pack(side=tk.LEFT, padx=10)

            var_leds = tk.BooleanVar(value=e.leds)
            tk.Checkbutton(frame, text="LEDs encendidos", variable=var_leds,
                          font=('Arial', 10, 'bold'), bg='#FFF9C4', fg='black',
                          command=lambda esc=e, v=var_leds: self._cambiar_leds(esc, v.get())
                          ).pack(anchor='w', padx=10, pady=(0, 6))

        tk.Button(win, text="CERRAR", font=('Arial', 12, 'bold'),
                 bg='#C62828', fg='white', padx=20, pady=6,
                 command=win.destroy).pack(pady=12)

    def _cambiar_brillo(self, escaner, valor):
        escaner.targetWhite = valor
        log(f"⚙ E{escaner.escaner_id} brillo → {valor}")

    def _cambiar_leds(self, escaner, encendidos):
        escaner.leds = encendidos
        log(f"⚙ E{escaner.escaner_id} LEDs → {'ON' if encendidos else 'OFF'}")

    def conectar_gps(self):
        puerto = self.config.get("puerto_gps")
        if not puerto:
            log("⚠ Sin puerto GPS configurado")
            return
        self.gps = LectorGPS(puerto)
        if self.gps.conectar():
            gps_log_path = os.path.join(RUTA_CAPTURAS, "gps_log.csv")
            self.gps.abrir_log(gps_log_path)
            self.gps.callback_perdida = lambda: log("⚠ Callback: GPS perdido")
            self.gps.iniciar()
            log(f"✓ GPS log continuo → {gps_log_path}")

    def conectar_escaneres(self):
        for i in range(1, 4):
            puerto, tw, leds, sn = self._get_escaner_cfg(i)
            if puerto or sn:
                e = EscanerFotos(i, puerto, targetWhite=tw, leds=leds, serial_number_hw=sn)
                e.on_foto_guardada = self._guardar_ultima_foto_miniatura
                if e.conectar():
                    self.escaneres_fotos.append(e)
        log(f"✓ {len(self.escaneres_fotos)}/3 escáneres conectados")

    def tecla_presionada(self, evento):
        """Captura teclas del escáner HID. Cierra el código cuando llega Enter
        O cuando pasan 120ms sin teclas nuevas (algunos Honeywell no envían CR)."""
        if not self.capturando:
            return
        if evento.char and evento.char.isprintable():
            self.hid_buffer += evento.char
            self.hid_ultimo = time.time()
            # Programar cierre por timeout
            if hasattr(self, '_hid_timer_id') and self._hid_timer_id:
                try:
                    self.root.after_cancel(self._hid_timer_id)
                except Exception:
                    pass
            self._hid_timer_id = self.root.after(120, self._cerrar_codigo_hid)
        elif evento.keysym in ('Return', 'KP_Enter'):
            self._cerrar_codigo_hid()

    def _cerrar_codigo_hid(self):
        self._hid_timer_id = None
        if not self.hid_buffer:
            return
        codigo = ''.join(c for c in self.hid_buffer if c.isalnum())
        self.hid_buffer = ""
        if len(codigo) >= 3:
            # AUTO-INICIO de mesa: si llega un código sin estar capturando,
            # arranca mesa nueva automáticamente
            if not self.capturando:
                log(f"▶ Auto-inicio de mesa por código HID")
                self.iniciar_captura()
            self.procesar_codigo(codigo)

    def procesar_codigo(self, codigo):
        if codigo in self.codigos_unicos:
            log(f"⚠ Código repetido ignorado: {codigo}")
            return

        self.codigos_unicos.add(codigo)
        self.columna_actual += 1
        ts = datetime.now()

        fila = {
            'timestamp': ts.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3],
            'codigo': codigo,
            'columna': self.columna_actual,
            'gps_lat': self.gps.lat if self.gps else '',
            'gps_lon': self.gps.lon if self.gps else '',
            'gps_alt': self.gps.alt if self.gps else '',
            'gps_sat': self.gps.satelites if self.gps else '',
            'gps_hdop': self.gps.hdop if self.gps else '',
            'gps_fix': 'OK' if (self.gps and self.gps.conectado) else 'NO_FIX',
        }

        # Escribir inmediatamente (protege ante crash)
        self._escribir_csv(fila)
        log(f"✓ Col {self.columna_actual}: {codigo} (fix={fila['gps_fix']}, sat={fila['gps_sat']})")

        # Beeps
        if self.columna_actual == 1:
            threading.Thread(target=lambda: beep(2000, 200), daemon=True).start()
        elif self.columna_actual == COLUMNAS_TOTAL:
            threading.Thread(target=self._beep_doble, daemon=True).start()
            # AUTO-CIERRE de mesa: detiene captura, calcula semáforo,
            # prepara siguiente mesa. Si llega otro código, se abre sola.
            self.root.after(500, self._auto_cerrar_mesa)
        else:
            threading.Thread(target=lambda: beep(1000, 150), daemon=True).start()

    def _auto_cerrar_mesa(self):
        """Cierra la mesa cuando se completa (14 códigos), evalúa semáforo,
        avanza el contador. La siguiente captura HID auto-iniciará la próxima mesa."""
        if not self.capturando:
            return
        log(f"✓ Mesa {self.mesa_numero} completa ({COLUMNAS_TOTAL} códigos) — auto-cierre")
        self.detener_captura()
        self._evaluar_semaforo()
        # Avanzar número de mesa para que el próximo HID arranque la siguiente
        self.mesa_numero += 1
        self.columna_actual = 0
        self.codigos_unicos = set()

    def _beep_doble(self):
        beep(1500, 200)
        time.sleep(0.1)
        beep(1500, 200)

    def _abrir_csv(self):
        """Abre CSV incremental para la mesa actual"""
        self.csv_path = os.path.join(self.carpeta_mesa, f"{self.mesa_nombre}.csv")
        nuevo = not os.path.exists(self.csv_path)
        self.csv_file = open(self.csv_path, 'a', newline='', encoding='utf-8')
        self.csv_writer = csv.DictWriter(self.csv_file, fieldnames=[
            'timestamp', 'codigo', 'columna',
            'gps_lat', 'gps_lon', 'gps_alt', 'gps_sat', 'gps_hdop', 'gps_fix'
        ])
        if nuevo:
            self.csv_writer.writeheader()
            self.csv_file.flush()
        log(f"✓ CSV abierto: {self.csv_path}")

    def _escribir_csv(self, fila):
        if not self.csv_writer:
            log("⚠ csv_writer no inicializado, abriendo de emergencia")
            try:
                self._abrir_csv()
            except Exception as e:
                log(f"✗ No se pudo abrir CSV: {e}")
                return
        try:
            self.csv_writer.writerow(fila)
            self.csv_file.flush()
            os.fsync(self.csv_file.fileno())
        except Exception as e:
            log(f"✗ Error escribiendo CSV: {e}")

    def _cerrar_csv(self):
        if self.csv_file:
            try:
                self.csv_file.flush()
                self.csv_file.close()
                log(f"✓ CSV cerrado: {self.csv_path}")
            except Exception as e:
                log(f"✗ Error cerrando CSV: {e}")
            self.csv_file = None
            self.csv_writer = None

    def click_izquierdo(self, event):
        if isinstance(event.widget, tk.Button):
            return
        if not self.capturando:
            self.iniciar_captura()
        else:
            self.detener_captura()

    def click_rueda(self, event):
        if isinstance(event.widget, tk.Button):
            return
        if not self.capturando:
            self.iniciar_captura()

    def iniciar_captura(self):
        self.mesa_nombre = self._generar_nombre_mesa()
        self.carpeta_mesa = os.path.join(RUTA_CAPTURAS, self.mesa_nombre)
        os.makedirs(self.carpeta_mesa, exist_ok=True)

        self.columna_actual = 0
        self.codigos_unicos = set()
        self.hid_buffer = ""
        self.detecciones_zbar = {1: 0, 2: 0, 3: 0}
        self.pyzbar_contador = 0

        # Abrir CSV ANTES de capturar nada
        self._abrir_csv()

        for e in self.escaneres_fotos:
            subcarpeta = os.path.join(self.carpeta_mesa, f"escaner_{e.escaner_id}")
            e.iniciar(subcarpeta)

        self.capturando = True
        threading.Thread(target=lambda: beep(1000, 200), daemon=True).start()
        log(f"🚀 CAPTURA INICIADA — {self.mesa_nombre}")

    def detener_captura(self):
        for e in self.escaneres_fotos:
            e.detener()
        self.capturando = False
        self._cerrar_csv()
        log(f"⏹ CAPTURA DETENIDA — mesa {self.mesa_nombre}")

    def siguiente_mesa(self):
        if self.capturando:
            self.detener_captura()
        self.mesa_numero += 1
        self.columna_actual = 0
        self.codigos_unicos = set()
        self.btn_siguiente.config(state=tk.DISABLED)
        log(f"➡ Preparada mesa {self.mesa_numero:03d}")

    def _generar_nombre_mesa(self):
        return f"{datetime.now().strftime('%d%m_%H%M%S')}_{self.mesa_numero:03d}"

    def actualizar_interfaz(self):
        try:
            if self.capturando:
                self.label_mesa.config(text=f"Mesa: {self.mesa_nombre} (capturando)")
            else:
                self.label_mesa.config(text=f"Mesa: {self.mesa_numero:03d} (preparada)")

            self.label_columna.config(text=f"{self.columna_actual} / {COLUMNAS_TOTAL}")

            if self.gps and self.gps.conectado and self.gps.lat is not None:
                txt = f"GPS: {self.gps.lat:.6f}, {self.gps.lon:.6f} ({self.gps.satelites} sat, HDOP={self.gps.hdop})"
                self.label_gps.config(text=txt, fg='#27ae60')
            elif self.gps:
                self.label_gps.config(text="GPS: Buscando satélites…", fg='#f39c12')
            else:
                self.label_gps.config(text="GPS: Desconectado", fg='#e74c3c')

            # Escáneres: mostrar estado serial
            estados = []
            for e in self.escaneres_fotos:
                ok = e.serial and e.serial.is_open
                estados.append(f"E{e.escaner_id}:{'✓' if ok else '✗'}")
            self.label_escaneres.config(text="Escáneres: " + "  ".join(estados) if estados else "Sin escáneres")

            # Fotos por escáner
            if self.escaneres_fotos:
                fotos = "  ".join(f"E{e.escaner_id}={e.contador}" for e in self.escaneres_fotos)
                self.label_fotos.config(text=f"Fotos: {fotos}")
        except Exception:
            pass
        self.root.after(200, self.actualizar_interfaz)

    def cerrar_ventana(self):
        log("Cerrando ventana…")
        self.cleanup()
        self.root.destroy()

    def cleanup(self):
        """Garantiza cierre ordenado — llamado por WM_DELETE y atexit"""
        try:
            if self.capturando:
                self.detener_captura()
            self._cerrar_csv()
            for e in self.escaneres_fotos:
                e.desconectar()
            if self.gps:
                self.gps.desconectar()
            if hasattr(self, 'servidor_movil') and self.servidor_movil:
                self.servidor_movil.parar()
            log("✓ Cleanup completo")
        except Exception as e:
            log(f"✗ Error en cleanup: {e}")

    # ============================================================
    # API para el servidor móvil (todos thread-safe: usan root.after)
    # ============================================================

    def estado_para_movil(self):
        """JSON con el estado actual — lo consume el móvil cada 2s"""
        total_fotos = {}
        escaneres_info = []
        for e in self.escaneres_fotos:
            total_fotos[e.escaner_id - 1] = e.contador
            escaneres_info.append({
                'id': e.escaner_id,
                'puerto': e.puerto,
                'targetWhite': e.targetWhite,
                'leds': e.leds,
                'fotos': e.contador,
                'conectado': bool(e.serial and e.serial.is_open),
            })

        gps_info = {}
        if self.gps:
            gps_info = {
                'gps_connected': True,
                'gps_ok': self.gps.conectado,
                'gps_lat': self.gps.lat,
                'gps_lon': self.gps.lon,
                'gps_sat': self.gps.satelites,
                'gps_hdop': self.gps.hdop,
            }
        else:
            gps_info = {'gps_connected': False, 'gps_ok': False}

        return {
            'capturando': self.capturando,
            'mesa_numero': self.mesa_numero,
            'mesa_nombre': self.mesa_nombre,
            'columna_actual': self.columna_actual,
            'columnas_total': COLUMNAS_TOTAL,
            'fotos': total_fotos,
            'detecciones_zbar': sum(self.detecciones_zbar.values()) if PYZBAR_DISPONIBLE else None,
            'escaneres': escaneres_info,
            'semaforo': self.semaforo_pendiente,
            **gps_info,
        }

    def ultima_foto_miniatura(self):
        """Devuelve bytes de la última foto capturada (para preview móvil)"""
        with self._ultima_foto_lock:
            return self._ultima_foto_bytes

    def _guardar_ultima_foto_miniatura(self, jpeg_bytes):
        """Llamado por EscanerFotos cada vez que guarda una foto.
        - Guarda última para preview móvil
        - Encola para pyzbar (rate-limited cada 3ª foto)"""
        with self._ultima_foto_lock:
            self._ultima_foto_bytes = jpeg_bytes
        # Rate limit pyzbar: 1 de cada 3 fotos para no saturar CPU
        if PYZBAR_DISPONIBLE and self.capturando:
            self.pyzbar_contador += 1
            if self.pyzbar_contador % 3 == 0:
                try:
                    self.pyzbar_queue.put_nowait(jpeg_bytes)
                except _queue.Full:
                    pass  # cola llena → descarta

    def _pyzbar_worker(self):
        """Procesa fotos en background y guarda detecciones a CSV"""
        while True:
            try:
                jpeg = self.pyzbar_queue.get(timeout=1)
            except _queue.Empty:
                continue
            try:
                img = PIL_Image.open(_io.BytesIO(jpeg)).convert('L')
                resultados = zbar_decode(img)
                if resultados:
                    for r in resultados:
                        codigo = r.data.decode('utf-8', errors='ignore')
                        # Identificar escáner por el último contador (aproximado)
                        log(f"🔍 pyzbar leyó: {codigo}")
                        # Guardar a CSV de detecciones
                        if self.carpeta_mesa:
                            ruta = os.path.join(self.carpeta_mesa, "detecciones_zbar.csv")
                            nuevo = not os.path.exists(ruta)
                            try:
                                with open(ruta, 'a', encoding='utf-8') as f:
                                    if nuevo:
                                        f.write("timestamp,codigo,tipo\n")
                                    ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]
                                    f.write(f"{ts},{codigo},{r.type}\n")
                            except Exception as ex:
                                log(f"  ⚠ No se pudo guardar deteccion: {ex}")
                        # Contador genérico (no podemos saber qué escáner sin más info)
                        self.detecciones_zbar[1] = self.detecciones_zbar.get(1, 0) + 1
            except Exception as e:
                log(f"⚠ pyzbar error: {e}")

    def iniciar_captura_desde_movil(self):
        self.root.after(0, self._iniciar_desde_movil)

    def _iniciar_desde_movil(self):
        if not self.capturando:
            self.iniciar_captura()

    def cerrar_captura_desde_movil(self):
        self.root.after(0, self._cerrar_desde_movil)

    def _cerrar_desde_movil(self):
        if self.capturando:
            self.detener_captura()
            self._evaluar_semaforo()

    def cerrar_semaforo_desde_movil(self, aceptar):
        self.root.after(0, lambda: self._cerrar_semaforo(aceptar))

    def _cerrar_semaforo(self, aceptar):
        """aceptar=True → siguiente mesa. aceptar=False → repetir mesa"""
        self.semaforo_pendiente = None
        if aceptar:
            self.siguiente_mesa()
        else:
            # Repetir: no avanza número de mesa
            self.columna_actual = 0
            self.codigos_unicos = set()
            log(f"↻ Mesa {self.mesa_numero} marcada para repetir")

    def set_brillo_desde_movil(self, esc_id, valor):
        for e in self.escaneres_fotos:
            if e.escaner_id == esc_id:
                e.targetWhite = max(20, min(200, int(valor)))
                log(f"⚙ E{esc_id} brillo → {e.targetWhite} (desde móvil)")
                return

    def auto_calibrar_desde_movil(self):
        """Auto-calibra LEDs y targetWhite por escáner.
        Estrategia: probar SIN LEDs primero. Si la foto sale clara → no hace falta LED.
        Si oscura → encender LED. Después ajustar targetWhite según media de brillo."""
        if self.capturando:
            log("⚠ No se puede auto-calibrar mientras se captura")
            return
        threading.Thread(target=self._auto_calibrar_thread, daemon=True).start()

    def _auto_calibrar_thread(self):
        log("🎯 Auto-calibrando todos los escáneres…")
        for e in self.escaneres_fotos:
            try:
                resultado = self._calibrar_escaner(e)
                log(f"  E{e.escaner_id}: LEDs={'ON' if resultado['leds'] else 'OFF'}, "
                    f"tW={resultado['targetWhite']} (brillo medido={resultado['brillo']})")
                e.leds = resultado['leds']
                e.targetWhite = resultado['targetWhite']
            except Exception as ex:
                log(f"  E{e.escaner_id}: error calibrando: {ex}")
        log("✓ Auto-calibrado completo")

    def _calibrar_escaner(self, escaner):
        """Toma 2 fotos (con y sin LED) y decide la mejor combinación.
        Devuelve {leds: bool, targetWhite: int, brillo: int}"""
        # Foto 1: SIN LED, targetWhite alto (para captar luz ambiental)
        b_sin = self._foto_y_brillo(escaner, leds=False, target=125)
        log(f"  E{escaner.escaner_id} sin LED: brillo={b_sin}")

        # Si la foto sin LED ya tiene buen brillo, no hace falta LED
        if 80 <= b_sin <= 180:
            return {'leds': False, 'targetWhite': 100, 'brillo': b_sin}

        # Si está MUY clara sin LED → mucho sol, sin LED y bajar targetWhite
        if b_sin > 180:
            tw = max(40, 80 - (b_sin - 180))  # menos exposición
            return {'leds': False, 'targetWhite': tw, 'brillo': b_sin}

        # Si está oscura sin LED → probar CON LED
        b_con = self._foto_y_brillo(escaner, leds=True, target=80)
        log(f"  E{escaner.escaner_id} con LED: brillo={b_con}")
        if b_con > 220:
            # Sobreexpuesto con LED → bajar targetWhite
            return {'leds': True, 'targetWhite': 50, 'brillo': b_con}
        return {'leds': True, 'targetWhite': 80, 'brillo': b_con}

    def _foto_y_brillo(self, escaner, leds, target):
        """Dispara foto con config dada, devuelve brillo medio (0-255).
        Usa muestreo simple sin PIL para no añadir dependencias."""
        # Comando directo al escáner (sin pasar por el bucle)
        luz = "1L" if leds else "0L"
        cmd = f"\x16M\rIMGSNP1P{luz}{target}W;IMGSHP6F90J.\r".encode()
        if not (escaner.serial and escaner.serial.is_open):
            escaner.reconectar()
        try:
            escaner.serial.reset_input_buffer()
            escaner.serial.write(cmd)
            data = bytearray()
            for _ in range(400):  # 4s máx
                if escaner.serial.in_waiting > 0:
                    chunk = escaner.serial.read(escaner.serial.in_waiting)
                    data.extend(chunk)
                    if b'\xff\xd9' in data:
                        break
                time.sleep(0.01)
            start = data.find(b'\xff\xd8')
            end = data.find(b'\xff\xd9', start)
            if start >= 0 and end > start:
                jpeg = bytes(data[start:end+2])
                return self._brillo_medio(jpeg)
        except Exception as e:
            log(f"  Error capturando para calibrar: {e}")
        return 128  # fallback

    def _brillo_medio(self, jpeg_bytes):
        """Brillo medio sin PIL. Usa PIL si está disponible (mejor), si no aproxima."""
        try:
            from PIL import Image
            import io
            img = Image.open(io.BytesIO(jpeg_bytes)).convert('L')
            # Muestreo: thumbnail 80x60 = 4800 píxeles
            img.thumbnail((80, 60))
            pixels = list(img.getdata())
            return int(sum(pixels) / len(pixels))
        except ImportError:
            # Sin PIL, aproximación: tamaño JPEG es proxy de brillo (más blanco = más datos)
            return 128 if 50_000 < len(jpeg_bytes) < 150_000 else 100

    def _evaluar_semaforo(self):
        """Calcula el semáforo tras cerrar mesa"""
        n_codigos = len(self.codigos_unicos)
        fotos_min = min([e.contador for e in self.escaneres_fotos], default=0)

        problemas = []
        estado = 'verde'

        if n_codigos < 10:
            estado = 'rojo'; problemas.append(f"solo {n_codigos} códigos")
        elif n_codigos < COLUMNAS_TOTAL:
            if estado == 'verde': estado = 'ambar'
            problemas.append(f"{n_codigos}/{COLUMNAS_TOTAL} códigos")

        if fotos_min < 10:
            estado = 'rojo'; problemas.append(f"escáner con solo {fotos_min} fotos")
        elif fotos_min < 30:
            if estado == 'verde': estado = 'ambar'
            problemas.append(f"escáner con {fotos_min} fotos (pocas)")

        # Solo evaluar GPS si está configurado (modo test sin GPS → se ignora)
        if self.gps is not None:
            gps_fix_pct = 100 if self.gps.conectado else 0
            if gps_fix_pct < 80:
                estado = 'rojo'; problemas.append("GPS sin fix")
            elif gps_fix_pct < 95:
                if estado == 'verde': estado = 'ambar'
                problemas.append(f"GPS {gps_fix_pct}%")

        self.semaforo_pendiente = {
            'estado': estado,
            'motivo': ', '.join(problemas) if problemas else 'todo OK',
            'n_codigos': n_codigos,
            'fotos_min': fotos_min,
        }
        log(f"🚦 Semáforo: {estado} — {self.semaforo_pendiente['motivo']}")

    def ejecutar(self):
        self.root.mainloop()


def main():
    log("=" * 60)
    log(f"INICIO captura_v5.py — {datetime.now().isoformat()}")
    try:
        app = InterfazCaptura()
        app.ejecutar()
    except Exception as e:
        log(f"✗ ERROR FATAL: {e}")
        log(traceback.format_exc())
        try:
            messagebox.showerror("Error fatal", f"{e}\n\nRevisa {RUTA_LOG}")
        except Exception:
            pass
        sys.exit(1)


if __name__ == "__main__":
    main()
