#!/usr/bin/env python3
"""Servidor estatico para la presentacion, sin ruido de BrokenPipe.

Uso:  python3 serve.py            (puerto 8080)
      python3 serve.py 9000       (otro puerto)

El navegador cancela peticiones a medias (rangos de video, recargas), lo que
hace que http.server escupa BrokenPipeError. Aqui esos cortes se silencian:
no son errores, la presentacion se sirve bien igualmente.
"""
import sys
from http.server import HTTPServer, SimpleHTTPRequestHandler


class QuietHandler(SimpleHTTPRequestHandler):
    def copyfile(self, source, outputfile):
        try:
            super().copyfile(source, outputfile)
        except (BrokenPipeError, ConnectionResetError):
            pass  # el navegador cerro la conexion; no es un fallo

    def log_message(self, fmt, *args):
        # silencia el 404 de favicon.ico y demas ruido rutinario
        if "favicon.ico" in (args[0] if args else ""):
            return
        super().log_message(fmt, *args)


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8080
    print(f"Presentacion en http://localhost:{port}  (Ctrl+C para parar)")
    HTTPServer(("", port), QuietHandler).serve_forever()
