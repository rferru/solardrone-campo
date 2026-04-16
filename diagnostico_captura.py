#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Diagnóstico rápido en campo — por qué captura_v5 no coge fotos.
Lee config.json, intenta capturar una foto con cada escáner usando:
  1) El comando ACTUAL (q90 + LEDs ON)
  2) El comando VIEJO (q60 + LEDs OFF)
  3) Trigger simple (detección genérica)
Reporta qué funciona.
"""
import serial
import json
import time
import os
import sys


def intentar(puerto, comando, etiqueta, timeout_s=6):
    """Envía comando y espera respuesta JPEG. Devuelve (ok, tamaño_bytes, tiempo)"""
    t0 = time.time()
    try:
        ser = serial.Serial(puerto, 115200, timeout=0.1)
        time.sleep(0.3)
        ser.reset_input_buffer()
        ser.write(comando.encode() if isinstance(comando, str) else comando)

        data = bytearray()
        fin = time.time() + timeout_s
        while time.time() < fin:
            if ser.in_waiting > 0:
                data.extend(ser.read(ser.in_waiting))
                if b'\xff\xd9' in data:
                    break
            time.sleep(0.02)
        ser.close()

        dt = time.time() - t0
        start = data.find(b'\xff\xd8')
        end = data.find(b'\xff\xd9', start)
        if start >= 0 and end > start:
            return True, end - start, dt, None
        else:
            # No salió JPEG, mirar qué devolvió
            hex_ini = data[:60].hex() if data else '(vacío)'
            return False, len(data), dt, f"Sin JPEG. {len(data)}B recibidos. Ini={hex_ini}"
    except Exception as e:
        return False, 0, time.time() - t0, str(e)


def main():
    ruta_cfg = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")
    if not os.path.exists(ruta_cfg):
        print(f"❌ No encuentro config.json en {ruta_cfg}")
        input("Enter…")
        return

    with open(ruta_cfg, encoding='utf-8') as f:
        cfg = json.load(f)

    escaneres = []
    for i in range(1, 4):
        v = cfg.get(f"escaner_fotos_{i}")
        if isinstance(v, dict):
            p = v.get("puerto", "")
            sn = v.get("serial_number", "")
        else:
            p = v or ""
            sn = ""
        if p:
            escaneres.append((i, p, sn))

    print("\n" + "=" * 70)
    print("  DIAGNÓSTICO CAPTURA — ejecuta con TODOS los escáneres conectados")
    print("=" * 70)
    print(f"Escáneres en config.json: {len(escaneres)}\n")

    if not escaneres:
        print("❌ No hay escáneres en config.json")
        input("Enter…")
        return

    COMANDOS = [
        ("ACTUAL (q90 + LEDs ON)", "\x16M\rIMGSNP1P1L80W;IMGSHP6F90J.\r"),
        ("VIEJO (q60 + LEDs OFF)", "\x16M\rIMGSNP1P0L80W;IMGSHP6F60J60K0P.\r"),
        ("SIMPLE auto",            "\x16M\rIMGSNP;IMGSHP.\r"),
        ("REV_WA (solo test)",     "\x16M\rREV_WA.\r"),
    ]

    for idx, puerto, sn in escaneres:
        print(f"\n--- E{idx}  puerto={puerto}  SN={sn} ---")
        for etiqueta, cmd in COMANDOS:
            ok, size, dt, err = intentar(puerto, cmd, etiqueta)
            if ok:
                print(f"  ✅ {etiqueta}: JPEG {size/1024:.1f}KB en {dt:.2f}s")
            else:
                print(f"  ❌ {etiqueta}: {err[:100] if err else 'sin datos'} ({dt:.1f}s)")

    print("\n" + "=" * 70)
    print("Interpretación:")
    print("  - Si ✅ en VIEJO y ❌ en ACTUAL → problema con LEDs ON / q90")
    print("  - Si ❌ en todos pero ✅ en REV_WA → escáner responde pero no capta foto (config interna)")
    print("  - Si ❌ en todos incluido REV_WA → puerto no conecta / escáner colgado")
    print("=" * 70)
    input("\nEnter para salir…")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
        input("Enter…")
