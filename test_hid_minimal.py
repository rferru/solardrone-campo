#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test HID mínimo. Una ventana con un campo grande visible.
Click en el campo, dispara el escáner HID. Si el HID escribe en
Notepad, debe escribir aquí también.
"""
import tkinter as tk

contador = 0

def on_enter(_evento):
    global contador
    txt = entry.get()
    entry.delete(0, tk.END)
    if txt.strip():
        contador += 1
        codigos.insert(tk.END, f"{contador}. {txt}\n")
        codigos.see(tk.END)
        estado.config(text=f"✓ Leídos: {contador}", fg='green')

root = tk.Tk()
root.title("Test HID Mínimo")
root.geometry("700x500")
root.configure(bg='white')

tk.Label(root, text="TEST HID — escribe aquí lo que escanea el escáner",
         font=('Arial', 16, 'bold'), bg='white', fg='black').pack(pady=15)

tk.Label(root, text="1) Click DENTRO del recuadro amarillo  →  2) Dispara el escáner",
         font=('Arial', 12), bg='white', fg='black').pack(pady=5)

entry = tk.Entry(root, font=('Arial', 18), bg='#FFEB3B', fg='black',
                 relief=tk.SUNKEN, bd=4, justify='center')
entry.pack(fill=tk.X, padx=20, pady=10, ipady=15)
entry.bind('<Return>', on_enter)
entry.bind('<KP_Enter>', on_enter)
entry.focus_set()

estado = tk.Label(root, text="Esperando…", font=('Arial', 14, 'bold'),
                  bg='white', fg='gray')
estado.pack(pady=5)

tk.Label(root, text="Códigos leídos:", font=('Arial', 11, 'bold'),
         bg='white', fg='black').pack(anchor='w', padx=20)
codigos = tk.Text(root, font=('Courier', 12), height=10, bg='#F5F5F5')
codigos.pack(fill=tk.BOTH, expand=True, padx=20, pady=(0, 15))

root.mainloop()
