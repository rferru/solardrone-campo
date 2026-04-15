#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Configurador Solar Drone v5.0
Auto-detecta GPS y escáneres. Configura brillo (targetWhite) por escáner.
Compatible Windows. Mantiene scripts originales intactos.
"""

import tkinter as tk
from tkinter import messagebox
import serial
import serial.tools.list_ports
import json
import time
import threading
import os

# Paleta alto contraste para sol directo
BG_PAGE = '#FFFFFF'       # fondo principal blanco
BG_PANEL = '#FFF9C4'      # amarillo muy claro para paneles (alto contraste con sol)
BG_PROMPT = '#FFEB3B'     # amarillo vivo para la instrucción activa
FG_TEXT = '#000000'       # texto negro
FG_SUBT = '#424242'       # texto secundario gris oscuro
COL_OK = '#2E7D32'        # verde oscuro saturado
COL_ERR = '#C62828'       # rojo saturado
COL_WARN = '#E65100'      # naranja oscuro
BTN_PRI = '#1565C0'       # azul fuerte
BTN_SEC = '#6A1B9A'       # morado fuerte
BTN_SAVE = '#C62828'      # rojo fuerte
BTN_HID = '#00695C'       # verde azulado para test HID


class ConfiguradorV5:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Configurador Solar Drone v5.0")
        self.root.geometry("820x780")
        self.root.configure(bg=BG_PAGE)

        self.config = {
            "escaner_fotos_1": {"puerto": "", "serial_number": "", "targetWhite": 80, "leds": True},
            "escaner_fotos_2": {"puerto": "", "serial_number": "", "targetWhite": 80, "leds": True},
            "escaner_fotos_3": {"puerto": "", "serial_number": "", "targetWhite": 80, "leds": True},
            "puerto_gps": "",
            "gps_serial_number": "",
            "gps_baudrate": 9600,
        }

        self.info_puertos = {}  # {puerto: serial_number} para guardar al asignar

        self.dispositivos = []  # Lista de {puerto, tipo, nombre}
        self.paso_actual = 0
        self.escuchando = False

        # Estado test HID
        self.hid_buffer = ""
        self.hid_ultimo = time.time()
        self.hid_test_activo = False
        self.hid_codigos = []

        self.pasos = [
            {"key": "gps", "nombre": "GPS", "tipo": "gps"},
            {"key": "escaner_fotos_1", "nombre": "Escáner Fotos 1 (arriba)", "tipo": "escaner"},
            {"key": "escaner_fotos_2", "nombre": "Escáner Fotos 2 (medio)", "tipo": "escaner"},
            {"key": "escaner_fotos_3", "nombre": "Escáner Fotos 3 (abajo-fotos)", "tipo": "escaner"},
        ]

        self.crear_interfaz()
        self.detectar_puertos()

    def crear_interfaz(self):
        # Título
        tk.Label(self.root, text="CONFIGURADOR SOLAR DRONE v5.0",
                font=('Arial', 20, 'bold'), fg=FG_TEXT, bg=BG_PAGE).pack(pady=(15, 5))

        tk.Label(self.root, text="Escáner de códigos (INFERIOR) = modo HID. Compruébalo abajo con TEST HID.",
                font=('Arial', 11, 'bold'), fg=FG_SUBT, bg=BG_PAGE).pack()

        # Instrucción actual (grande, alto contraste)
        self.frame_instruccion = tk.Frame(self.root, bg=BG_PROMPT, relief=tk.RAISED, bd=4)
        self.frame_instruccion.pack(pady=12, fill=tk.X, padx=20)
        self.label_paso = tk.Label(self.frame_instruccion, text="Detectando dispositivos...",
                                   font=('Arial', 16, 'bold'), bg=BG_PROMPT, fg=FG_TEXT)
        self.label_paso.pack(pady=14)

        # Dispositivos serie
        frame_disp = tk.LabelFrame(self.root, text=" Dispositivos serie (GPS + 3 escáneres arriba) ",
                                    font=('Arial', 12, 'bold'), bg=BG_PANEL, fg=FG_TEXT,
                                    relief=tk.RIDGE, bd=3)
        frame_disp.pack(fill=tk.X, padx=20, pady=6)

        self.labels_disp = []
        self.sliders_white = []
        for i, paso in enumerate(self.pasos):
            frame_row = tk.Frame(frame_disp, bg=BG_PANEL)
            frame_row.pack(fill=tk.X, padx=10, pady=5)

            tk.Label(frame_row, text=f"{paso['nombre']}:", font=('Arial', 11, 'bold'),
                    bg=BG_PANEL, fg=FG_TEXT, width=28, anchor='w').pack(side=tk.LEFT)

            label = tk.Label(frame_row, text="⏳ Pendiente", font=('Arial', 11, 'bold'),
                           bg=BG_PANEL, fg=COL_WARN)
            label.pack(side=tk.LEFT, padx=5)
            self.labels_disp.append(label)

            if paso['tipo'] == 'escaner':
                tk.Label(frame_row, text="Brillo:", font=('Arial', 10, 'bold'),
                        bg=BG_PANEL, fg=FG_TEXT).pack(side=tk.LEFT, padx=(15, 2))
                slider = tk.Scale(frame_row, from_=20, to=200, orient=tk.HORIZONTAL,
                                 length=140, bg=BG_PANEL, fg=FG_TEXT, highlightthickness=0,
                                 troughcolor='#FFE082', font=('Arial', 10, 'bold'))
                slider.set(80)
                slider.pack(side=tk.LEFT)
                self.sliders_white.append(slider)
            else:
                self.sliders_white.append(None)

        # ----- Test escáner HID (inferior) -----
        frame_hid = tk.LabelFrame(self.root,
                                  text=" Test escáner de códigos HID (INFERIOR) ",
                                  font=('Arial', 12, 'bold'),
                                  bg=BG_PANEL, fg=FG_TEXT, relief=tk.RIDGE, bd=3)
        frame_hid.pack(fill=tk.X, padx=20, pady=6)

        hid_row1 = tk.Frame(frame_hid, bg=BG_PANEL)
        hid_row1.pack(fill=tk.X, padx=10, pady=5)
        self.btn_hid = tk.Button(hid_row1, text="▶ INICIAR TEST HID",
                                 font=('Arial', 12, 'bold'), bg=BTN_HID, fg='white',
                                 activebackground='#004D40', activeforeground='white',
                                 command=self.toggle_test_hid, padx=15, pady=6)
        self.btn_hid.pack(side=tk.LEFT)
        self.label_hid_estado = tk.Label(hid_row1, text="Pulsa INICIAR y escanea algo con el HID (inferior)",
                                         font=('Arial', 11, 'bold'), bg=BG_PANEL, fg=FG_SUBT)
        self.label_hid_estado.pack(side=tk.LEFT, padx=15)

        self.label_hid_resultado = tk.Label(frame_hid, text="—",
                                            font=('Courier', 14, 'bold'),
                                            bg='white', fg=FG_TEXT, relief=tk.SUNKEN, bd=2,
                                            width=60, anchor='w', padx=8, pady=6)
        self.label_hid_resultado.pack(fill=tk.X, padx=10, pady=(0, 8))

        # Entry minúsculo que recibe las teclas del HID (el escáner escribe "como teclado").
        # IMPORTANTE: muchos HID Honeywell NO envían Enter al final → detectamos fin de
        # código por timeout (100ms sin teclas nuevas).
        self.entry_hid = tk.Entry(frame_hid, font=('Arial', 1), bg=BG_PANEL,
                                  fg=BG_PANEL, insertbackground=BG_PANEL,
                                  highlightthickness=0, bd=0, takefocus=1)
        self.entry_hid.pack(fill=tk.X, padx=10, pady=(0, 2))
        # Soporte ambos casos: con Enter y sin Enter (timeout)
        self.entry_hid.bind('<Return>', self._hid_entry_enter)
        self.entry_hid.bind('<KP_Enter>', self._hid_entry_enter)
        self.entry_hid.bind('<Key>', self._hid_entry_key)
        self._hid_timer_id = None

        # ----- Botones principales (grandes) -----
        frame_btn = tk.Frame(self.root, bg=BG_PAGE)
        frame_btn.pack(pady=15)

        self.btn_auto = tk.Button(frame_btn, text="AUTO-DETECTAR",
                                   font=('Arial', 13, 'bold'), bg=BTN_PRI, fg='white',
                                   activebackground='#0D47A1', activeforeground='white',
                                   command=self.auto_detectar, state=tk.DISABLED,
                                   padx=15, pady=8)
        self.btn_auto.pack(side=tk.LEFT, padx=5)

        self.btn_manual = tk.Button(frame_btn, text="PASO A PASO",
                                     font=('Arial', 13, 'bold'), bg=BTN_SEC, fg='white',
                                     activebackground='#4A148C', activeforeground='white',
                                     command=self.iniciar_manual, padx=15, pady=8)
        self.btn_manual.pack(side=tk.LEFT, padx=5)

        self.btn_guardar = tk.Button(frame_btn, text="GUARDAR",
                                      font=('Arial', 13, 'bold'), bg=BTN_SAVE, fg='white',
                                      activebackground='#8E0000', activeforeground='white',
                                      command=self.guardar, state=tk.DISABLED,
                                      padx=15, pady=8)
        self.btn_guardar.pack(side=tk.LEFT, padx=5)

        # Estado inferior
        self.label_estado = tk.Label(self.root, text="", font=('Arial', 11, 'bold'),
                                     bg=BG_PAGE, fg=FG_TEXT)
        self.label_estado.pack(pady=5)

    # ----- Test HID (captura por Entry con foco) -----
    def toggle_test_hid(self):
        self.hid_test_activo = not self.hid_test_activo
        if self.hid_test_activo:
            self.hid_codigos = []
            self.btn_hid.config(text="■ DETENER TEST HID", bg=COL_ERR)
            self.label_hid_estado.config(
                text="🟢 ESCUCHANDO… Dispara el HID contra un código", fg=COL_OK)
            self.label_hid_resultado.config(text="(esperando escaneo…)", fg=FG_SUBT)
            # Forzar foco en el entry oculto para que reciba las teclas del HID
            self.entry_hid.delete(0, tk.END)
            self.root.after(50, self._dar_foco_hid)
            # Mantener el foco en el entry cada 500ms (por si algo se lo quita)
            self._mantener_foco_id = self.root.after(500, self._mantener_foco_hid)
        else:
            self.btn_hid.config(text="▶ INICIAR TEST HID", bg=BTN_HID)
            # Cancelar mantenimiento de foco
            if hasattr(self, '_mantener_foco_id'):
                try:
                    self.root.after_cancel(self._mantener_foco_id)
                except Exception:
                    pass
            if self.hid_codigos:
                self.label_hid_estado.config(
                    text=f"✓ HID OK — {len(self.hid_codigos)} código(s) leídos", fg=COL_OK)
            else:
                self.label_hid_estado.config(
                    text="⚠ HID NO leyó nada. Revisa modo HID o cable", fg=COL_ERR)

    def _dar_foco_hid(self):
        self.root.focus_force()
        self.entry_hid.focus_set()

    def _mantener_foco_hid(self):
        if self.hid_test_activo:
            # Si el usuario pulsa otro botón, recuperar foco al entry
            try:
                if self.root.focus_get() is not self.entry_hid:
                    self.entry_hid.focus_set()
            except Exception:
                pass
            self._mantener_foco_id = self.root.after(500, self._mantener_foco_hid)

    def _hid_entry_enter(self, evento):
        """El escáner HID acaba cada código con Enter (si está configurado así)"""
        if not self.hid_test_activo:
            return "break"
        self._procesar_codigo_hid()
        return "break"

    def _hid_entry_key(self, evento):
        """Cada tecla del HID resetea un timer; si pasan 120ms sin teclas → fin de código"""
        if not self.hid_test_activo:
            return
        # Cancelar timer previo
        if self._hid_timer_id:
            try:
                self.root.after_cancel(self._hid_timer_id)
            except Exception:
                pass
        # Programar nuevo cierre de código
        self._hid_timer_id = self.root.after(120, self._procesar_codigo_hid)

    def _procesar_codigo_hid(self):
        self._hid_timer_id = None
        texto = self.entry_hid.get()
        self.entry_hid.delete(0, tk.END)
        codigo = ''.join(c for c in texto if c.isalnum())
        if len(codigo) >= 3:
            self.hid_codigos.append(codigo)
            self.label_hid_resultado.config(
                text=f"✓ {codigo}  ({len(self.hid_codigos)} total)", fg=COL_OK)
            self.label_hid_estado.config(
                text="✓ HID OK — escanea otro si quieres", fg=COL_OK)

    def detectar_puertos(self):
        threading.Thread(target=self._detectar, daemon=True).start()

    def _detectar(self):
        info = {}
        for p in serial.tools.list_ports.comports():
            info[p.device] = p.serial_number or ""
        self.info_puertos = info
        puertos = sorted(info.keys())
        self.root.after(0, lambda: self._puertos_detectados(puertos))

    def _puertos_detectados(self, puertos):
        n = len(puertos)
        self.label_estado.config(text=f"{n} puertos detectados: {', '.join(puertos)}")
        if n >= 4:
            self.btn_auto.config(state=tk.NORMAL)
            self.label_paso.config(text=f"{n} puertos. Click AUTO-DETECTAR o PASO A PASO")
        else:
            self.label_paso.config(text=f"⚠️ Solo {n} puertos. Conecta 3 escáneres + GPS")
        self.puertos = puertos

    def auto_detectar(self):
        """Detecta automáticamente GPS y escáneres"""
        self.btn_auto.config(state=tk.DISABLED)
        self.label_paso.config(text="🔍 Auto-detectando...")
        threading.Thread(target=self._auto_thread, daemon=True).start()

    def _auto_thread(self):
        gps_puerto = None
        escaner_puertos = []

        for puerto in self.puertos:
            # Probar GPS (9600 baud, buscar $GP/$GN)
            try:
                ser = serial.Serial(puerto, 9600, timeout=1.5)
                time.sleep(0.3)
                for _ in range(5):
                    linea = ser.readline().decode('ascii', errors='ignore').strip()
                    if linea.startswith('$GP') or linea.startswith('$GN'):
                        gps_puerto = puerto
                        ser.close()
                        self.root.after(0, lambda p=puerto: self._marcar(0, p, "GPS detectado"))
                        break
                else:
                    ser.close()
            except:
                pass

            if gps_puerto:
                break

        # El resto son escáneres — verificar enviando trigger
        for puerto in self.puertos:
            if puerto == gps_puerto:
                continue
            try:
                ser = serial.Serial(puerto, 115200, timeout=0.5)
                time.sleep(0.1)
                ser.write(b'\x16T\r')
                time.sleep(0.3)
                if ser.in_waiting > 0:
                    data = ser.read(ser.in_waiting)
                    escaner_puertos.append(puerto)
                    idx = len(escaner_puertos)
                    self.root.after(0, lambda p=puerto, i=idx: self._marcar(i, p, f"Escáner {i}"))
                ser.close()
            except:
                pass

            if len(escaner_puertos) >= 3:
                break

        # Resultado
        if gps_puerto and len(escaner_puertos) >= 3:
            self.config["puerto_gps"] = gps_puerto
            self.config["gps_serial_number"] = self.info_puertos.get(gps_puerto, "")
            for i, p in enumerate(escaner_puertos):
                self.config[f"escaner_fotos_{i+1}"]["puerto"] = p
                self.config[f"escaner_fotos_{i+1}"]["serial_number"] = self.info_puertos.get(p, "")
            self.root.after(0, self._auto_completo)
        else:
            msg = f"GPS: {'✓' if gps_puerto else '✗'}, Escáneres: {len(escaner_puertos)}/3"
            self.root.after(0, lambda: self.label_paso.config(text=f"⚠️ {msg}. Prueba PASO A PASO"))
            self.root.after(0, lambda: self.btn_auto.config(state=tk.NORMAL))

    def _marcar(self, paso_idx, puerto, texto):
        self.labels_disp[paso_idx].config(text=f"✓ {puerto} ({texto})", fg=COL_OK)

    def _auto_completo(self):
        self.label_paso.config(text="✓ AUTO-DETECCIÓN COMPLETA", bg=COL_OK, fg='white')
        self.btn_guardar.config(state=tk.NORMAL)

    def iniciar_manual(self):
        """Configuración paso a paso (como v4)"""
        self.escuchando = True
        self.paso_actual = 0
        self.btn_manual.config(state=tk.DISABLED)
        self._siguiente_paso()

        for puerto in self.puertos:
            threading.Thread(target=self._escuchar_puerto, args=(puerto,), daemon=True).start()

    def _siguiente_paso(self):
        if self.paso_actual >= len(self.pasos):
            self.label_paso.config(text="✓ CONFIGURACIÓN COMPLETA", bg=COL_OK, fg='white')
            self.btn_guardar.config(state=tk.NORMAL)
            self.escuchando = False
            return

        paso = self.pasos[self.paso_actual]
        if paso['tipo'] == 'gps':
            self.label_paso.config(text=f"Paso {self.paso_actual+1}/4: Esperando GPS...")
        else:
            self.label_paso.config(text=f"Paso {self.paso_actual+1}/4: Escanea un código con {paso['nombre']}")

    def _escuchar_puerto(self, puerto):
        """Escucha un puerto para detectar GPS o escaneo"""
        puertos_asignados = set()

        while self.escuchando:
            if puerto in puertos_asignados:
                break
            if self.paso_actual >= len(self.pasos):
                break

            paso = self.pasos[self.paso_actual]

            try:
                if paso['tipo'] == 'gps':
                    ser = serial.Serial(puerto, 9600, timeout=1)
                    linea = ser.readline().decode('ascii', errors='ignore').strip()
                    ser.close()
                    if linea.startswith('$GP') or linea.startswith('$GN'):
                        self.config["puerto_gps"] = puerto
                        self.config["gps_serial_number"] = self.info_puertos.get(puerto, "")
                        puertos_asignados.add(puerto)
                        self.root.after(0, lambda: self._paso_completado(puerto, "GPS"))
                        return

                elif paso['tipo'] == 'escaner':
                    ser = serial.Serial(puerto, 115200, timeout=0.3)
                    time.sleep(0.05)
                    if ser.in_waiting > 0:
                        ser.reset_input_buffer()
                    ser.write(b'\x16T\r')
                    time.sleep(0.3)
                    if ser.in_waiting > 0:
                        _ = ser.read(ser.in_waiting)  # drenar respuesta
                        data = _.decode('utf-8', errors='ignore').strip()
                        data = data.replace('\x06', '').replace('\x16T\r', '').strip()
                        if len(data) >= 3:
                            key = f"escaner_fotos_{self.paso_actual}"
                            self.config[key]["puerto"] = puerto
                            self.config[key]["serial_number"] = self.info_puertos.get(puerto, "")
                            puertos_asignados.add(puerto)
                            ser.close()
                            self.root.after(0, lambda p=puerto, c=data[:20]: self._paso_completado(p, c))
                            return
                    ser.close()
            except:
                pass

            time.sleep(0.2)

    def _paso_completado(self, puerto, info):
        self.labels_disp[self.paso_actual].config(text=f"✓ {puerto} ({info})", fg=COL_OK)
        self.paso_actual += 1
        self._siguiente_paso()

    def guardar(self):
        # Recoger valores de brillo de los sliders
        for i, slider in enumerate(self.sliders_white):
            if slider:
                key = f"escaner_fotos_{i}"  # 1, 2, 3
                if key in self.config:
                    self.config[key]["targetWhite"] = slider.get()

        ruta = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")
        with open(ruta, 'w') as f:
            json.dump(self.config, f, indent=4)

        resumen = f"GPS: {self.config['puerto_gps']}\n"
        for i in range(1, 4):
            c = self.config[f"escaner_fotos_{i}"]
            resumen += f"Escáner {i}: {c['puerto']} (brillo={c['targetWhite']})\n"

        messagebox.showinfo("Guardado", f"config.json guardado en:\n{ruta}\n\n{resumen}\n"
                           "RECUERDA: El escáner de códigos (inferior) debe estar en modo HID.")
        self.root.destroy()

    def ejecutar(self):
        self.root.mainloop()


if __name__ == "__main__":
    app = ConfiguradorV5()
    app.ejecutar()
