# Solar Drone v5 — Software de campo (Windows)

Todo lo necesario para capturar números de serie de paneles PV con pértiga Honeywell en la planta de Balbona.

## 📥 Descargar todo de golpe

1. Click en el botón **Code → Download ZIP** (arriba a la derecha)
2. Extrae en el Escritorio del PC Windows
3. Abre `README_instrucciones.html` con doble-click → tendrás la guía visual con pasos + botones de copiar

## Archivos

| Archivo | Qué hace |
|---|---|
| `captura_v5.py` | Software principal de captura + servidor web para el móvil |
| `servidor_movil.py` | Servidor HTTP que se integra con captura_v5 |
| `configurador_v5.py` | Configurador de puertos COM + test HID (1ª vez) |
| `diagnostico.py` | Detecta qué dispositivos hay en los puertos COM |
| `test_hid_minimal.py` | Mini test solo para verificar el HID |
| `EJECUTAR_CAPTURA.bat` | Doble-click para arrancar la captura |
| `EJECUTAR_CONFIGURADOR.bat` | Doble-click para configurar por primera vez |
| `EJECUTAR_DIAGNOSTICO.bat` | Doble-click para diagnosticar problemas |
| `SUBIR_DATOS.bat` | Subir capturas a GCS (opcional, al final del día) |
| `README_instrucciones.html` | Guía completa paso a paso |

## Flujo rápido

1. Configurar escáneres (1 sola vez): `EJECUTAR_CONFIGURADOR.bat`
2. Activar hotspot del móvil, conectar PC a ese WiFi
3. Arrancar captura: `EJECUTAR_CAPTURA.bat`
4. Apuntar la IP que sale en consola → abrir en el móvil
5. Trabajo normal: disparar HID contra código → mesa se inicia y se cierra sola a los 14
