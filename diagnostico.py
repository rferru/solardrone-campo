#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Diagnóstico rápido de puertos serie.
Muestra TODO lo que Windows sabe de cada puerto COM, y prueba a leer.
"""
import serial
import serial.tools.list_ports
import time
import sys


def listar_puertos():
    print("\n" + "=" * 70)
    print("PUERTOS DETECTADOS POR WINDOWS")
    print("=" * 70)
    puertos = list(serial.tools.list_ports.comports())
    if not puertos:
        print("❌ NO SE DETECTA NINGÚN PUERTO")
        print("→ Revisa cables USB, drivers Honeywell instalados")
        return []

    for p in puertos:
        print(f"\n  {p.device}")
        print(f"    Descripción : {p.description}")
        print(f"    Fabricante  : {p.manufacturer}")
        print(f"    Producto    : {p.product}")
        print(f"    VID:PID     : {p.vid}:{p.pid}" if p.vid else "    VID:PID     : —")
        print(f"    Nº serie USB: {p.serial_number}")
        print(f"    HWID        : {p.hwid}")

        # Clasificar
        tipo = "?"
        if p.vid in (0x0C2E, 0x05E0):
            tipo = "HONEYWELL (escáner)"
        elif p.vid == 0x1546:
            tipo = "U-BLOX (GPS)"
        elif p.vid == 0x067B:
            tipo = "PROLIFIC (cable USB-serie genérico)"
        elif p.vid == 0x10C4:
            tipo = "CP210x (Silicon Labs, suele ser GPS)"
        print(f"    → Tipo      : {tipo}")
    return puertos


def probar_puerto(puerto, baud):
    """Intenta abrir y leer datos durante 2s"""
    try:
        ser = serial.Serial(puerto, baud, timeout=1.0)
        time.sleep(0.3)
        # Intentar leer datos espontáneos (GPS envía continuamente)
        t_fin = time.time() + 2.0
        data = bytearray()
        while time.time() < t_fin:
            if ser.in_waiting > 0:
                data.extend(ser.read(ser.in_waiting))
            time.sleep(0.1)
        ser.close()
        return bytes(data)
    except Exception as e:
        return f"ERROR: {e}".encode()


def test_escaner(puerto):
    """Envía comando de identificación al Honeywell"""
    print(f"\n  Probando {puerto} como escáner (115200)...")
    try:
        ser = serial.Serial(puerto, 115200, timeout=0.5)
        time.sleep(0.2)
        ser.reset_input_buffer()
        # Comando de REVISION (responde aunque no haya código delante)
        ser.write(b'\x16M\rREV_WA.\r')
        time.sleep(0.8)
        data = ser.read(ser.in_waiting) if ser.in_waiting > 0 else b''
        ser.close()
        if len(data) > 0:
            print(f"    ✓ RESPONDE: {data[:100]!r}")
            return True
        else:
            print("    ✗ No responde a REV_WA")
            return False
    except Exception as e:
        print(f"    ✗ Error: {e}")
        return False


def test_gps(puerto):
    """Intenta leer NMEA del GPS en 9600 baud"""
    print(f"\n  Probando {puerto} como GPS (9600)...")
    data = probar_puerto(puerto, 9600)
    if isinstance(data, bytes) and len(data) > 0:
        txt = data.decode('ascii', errors='ignore')
        if '$GP' in txt or '$GN' in txt:
            print(f"    ✓ GPS DETECTADO (NMEA)")
            print(f"    Muestra: {txt[:150]}")
            return True
        else:
            print(f"    Recibe datos pero no es NMEA: {txt[:80]!r}")
    else:
        print(f"    ✗ Sin datos")
    return False


def main():
    puertos = listar_puertos()
    if not puertos:
        input("\nPulsa ENTER para salir...")
        return

    print("\n" + "=" * 70)
    print("TESTS DE RESPUESTA")
    print("=" * 70)

    for p in puertos:
        # Si es Honeywell → probar como escáner
        if p.vid in (0x0C2E, 0x05E0):
            test_escaner(p.device)
        # Si es U-blox o CP210x → probar como GPS primero
        elif p.vid in (0x1546, 0x10C4):
            test_gps(p.device)
        else:
            # Desconocido: probar ambos
            if not test_gps(p.device):
                test_escaner(p.device)

    print("\n" + "=" * 70)
    print("RESUMEN")
    print("=" * 70)
    print("Si ves escáneres con VID Honeywell pero NO RESPONDEN:")
    print("  → Probablemente están en modo HID (teclado), no SERIE")
    print("  → Hay que reconfigurar escaneando el código PAP124 del manual")
    print("  → O escanear: USB IBM Serial = PAPSPP")
    print()
    print("Si no aparece ningún Honeywell:")
    print("  → Falta instalar drivers Honeywell USB Serial Driver")
    print()
    input("Pulsa ENTER para salir...")


if __name__ == "__main__":
    main()
