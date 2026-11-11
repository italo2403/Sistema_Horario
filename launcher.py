"""Inicializador desktop Windows do Gestor de Horários (Tkinter + HTTP local)."""
import os
import shutil
import socket
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import messagebox
import webbrowser


def app_dir():
    base = os.environ.get('LOCALAPPDATA') or str(Path.home())
    return Path(base) / 'GestorHorariosDocentes'


def resources_dir():
    return Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parent))


DATA_DIR = app_dir()
DATA_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = DATA_DIR / 'horarios.sqlite3'
SEED_PATH = resources_dir() / 'dados_iniciais.sqlite3'
if not DB_PATH.exists() and SEED_PATH.exists():
    shutil.copy2(SEED_PATH, DB_PATH)

os.environ['HORARIOS_DB'] = str(DB_PATH)
os.environ['HORARIOS_HOST'] = '127.0.0.1'
# Mantenha porta fixa para evitar abrir servidores acessíveis na rede.
os.environ['HORARIOS_PORT'] = '8000'

import server  # noqa: E402, depois de configurar o caminho do banco
from http.server import ThreadingHTTPServer


def main():
    root = tk.Tk()
    root.title('Gestor de Horários Docentes')
    root.geometry('490x265')
    root.resizable(False, False)

    tk.Label(root, text='GESTOR DE HORÁRIOS DOCENTES', font=('Segoe UI', 15, 'bold')).pack(pady=(22, 8))
    status = tk.StringVar(value='Iniciando sistema local...')
    tk.Label(root, textvariable=status, font=('Segoe UI', 10)).pack(pady=6)
    tk.Label(root, text='Os dados ficam salvos neste computador.', fg='#555555').pack(pady=2)

    try:
        server.init_db()
        httpd = ThreadingHTTPServer((server.HOST, server.PORT), server.Handler)
    except OSError as exc:
        messagebox.showerror('Porta ocupada', f'Não foi possível iniciar o sistema em 127.0.0.1:8000.\n\n{exc}\n\nFeche outra instância do programa e tente novamente.')
        root.destroy()
        return
    except Exception as exc:
        messagebox.showerror('Erro ao iniciar', str(exc))
        root.destroy()
        return

    worker = threading.Thread(target=httpd.serve_forever, daemon=True)
    worker.start()
    url = 'http://127.0.0.1:8000'
    status.set('Sistema funcionando neste computador.')
    tk.Button(root, text='ABRIR SISTEMA NO NAVEGADOR', font=('Segoe UI', 10, 'bold'), width=35,
              command=lambda: webbrowser.open(url)).pack(pady=(18, 8))
    tk.Button(root, text='ABRIR PASTA DOS DADOS', width=35,
              command=lambda: os.startfile(str(DATA_DIR)) if sys.platform == 'win32' else None).pack(pady=5)

    def close():
        httpd.shutdown()
        httpd.server_close()
        root.destroy()

    root.protocol('WM_DELETE_WINDOW', close)
    root.after(250, lambda: webbrowser.open(url))
    root.mainloop()


if __name__ == '__main__':
    main()
