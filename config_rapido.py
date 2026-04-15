#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Genera config.json automáticamente a partir de los dispositivos conectados.
Útil para modo test con 1 solo escáner, o para usar sin GPS, etc.
"""
import serial
import serial.tools.list_ports
import json
import os

HONEYWELL_VIDS = {0x0C2E, 0x05E0}
GPS_VIDS = {0x1546, 0x10C4, 0x067B}  # u-blox, CP210x, Prolific


def main():
    print("\n" + "=" * 60)
    print("  CONFIG RÁPIDO — autodetecta dispositivos y genera config.json")
    print("=" * 60 + "\n")

    escaneres = []
    gps_puerto = None
    gps_sn = None

    for p in serial.tools.list_ports.comports():
        if p.vid in HONEYWELL_VIDS:
            escaneres.append({
                'puerto': p.device,
                'serial_number': p.serial_number or "",
                'desc': p.description,
            })
            print(f"  ✓ Honeywell detectado: {p.device} (SN={p.serial_number})")
        elif p.vid in GPS_VIDS:
            gps_puerto = p.device
            gps_sn = p.serial_number or ""
            print(f"  ✓ GPS detectado: {p.device} (VID={hex(p.vid)})")

    if not escaneres and not gps_puerto:
        print("\n❌ No se detectó ningún Honeywell ni GPS conocido.")
        print("   Revisa:")
        print("   - Los drivers Honeywell USB Serial instalados")
        print("   - Los escáneres NO están en modo HID (deben ser USB Serial)")
        print("   - El GPS u-blox conectado y reconocido por Windows")
        input("\nEnter para salir...")
        return

    print(f"\n  → {len(escaneres)} escáner(es) + {'GPS' if gps_puerto else 'SIN GPS'}")

    # Construir config
    config = {}
    for i, e in enumerate(escaneres[:3], start=1):
        config[f"escaner_fotos_{i}"] = {
            "puerto": e['puerto'],
            "serial_number": e['serial_number'],
            "targetWhite": 80,
            "leds": True,
        }
    # Rellenar los que falten con puerto vacío (captura_v5 los ignora)
    for i in range(len(escaneres) + 1, 4):
        config[f"escaner_fotos_{i}"] = {
            "puerto": "",
            "serial_number": "",
            "targetWhite": 80,
            "leds": True,
        }

    if gps_puerto:
        config["puerto_gps"] = gps_puerto
        config["gps_serial_number"] = gps_sn
    else:
        config["puerto_gps"] = ""
        config["gps_serial_number"] = ""
    config["gps_baudrate"] = 9600

    ruta = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")
    with open(ruta, 'w', encoding='utf-8') as f:
        json.dump(config, f, indent=4)

    print(f"\n✓ config.json guardado en:\n  {ruta}\n")
    print("Contenido:")
    print(json.dumps(config, indent=2))
    print("\n¡Listo! Ahora ejecuta EJECUTAR_CAPTURA.bat")
    input("\nEnter para salir...")


if __name__ == "__main__":
    main()
