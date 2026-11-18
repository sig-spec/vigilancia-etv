"""Almacenamiento gratuito de los datos.

- Base inicial (PNEET 2019-2026): datos/base/<tipo>/<clave>.csv.gz, viene con el repositorio.
- Cargues: datos/cargue/<tipo>/<clave>.csv.gz. Un cargue reemplaza a la base de la misma clave
  (evento y año para casos; mes para ovitrampas y encuesta larvaria).
- Si en los secretos hay [github] token/repo, cada cargue se guarda además como commit en el
  repositorio (privado) para que no se pierda cuando Streamlit Cloud reinicia la app.
"""
from __future__ import annotations

import base64
import io
import json
import os
from datetime import datetime
from pathlib import Path

import pandas as pd
import requests

RAIZ = Path(__file__).resolve().parent.parent / 'datos'
TIPOS = ('casos', 'ovi', 'larv', 'feb')


class Almacen:
    def __init__(self, github: dict | None = None):
        self.gh = github if github and github.get('token') and github.get('repo') else None
        for t in TIPOS:
            (RAIZ / 'cargue' / t).mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------ lectura
    @staticmethod
    def version() -> str:
        """Cambia cuando cambia cualquier archivo de cargue (sirve para invalidar la caché)."""
        partes = []
        for p in sorted((RAIZ / 'cargue').rglob('*')):
            if p.is_file():
                st = p.stat()
                partes.append(f'{p.name}:{st.st_size}:{int(st.st_mtime)}')
        return '|'.join(partes)

    @staticmethod
    def claves(tipo: str) -> dict:
        """{clave: {'origen': 'base'|'cargue', 'ruta': Path}} (el cargue tapa a la base)."""
        out = {}
        for origen in ('base', 'cargue'):
            for p in sorted((RAIZ / origen / tipo).glob('*.csv.gz')):
                out[p.name[:-7]] = {'origen': origen, 'ruta': p}
        return out

    @classmethod
    def leer(cls, tipo: str) -> pd.DataFrame:
        dfs = []
        for k, info in cls.claves(tipo).items():
            df = pd.read_csv(info['ruta'], dtype={'u': str, 'id': str, 'barrio': str, 'lugar': str, 'mun': str, 'zona': str})
            df['_clave'] = k
            df['_origen'] = info['origen']
            dfs.append(df)
        return pd.concat(dfs, ignore_index=True) if dfs else pd.DataFrame()

    @staticmethod
    def leer_json(nombre: str, defecto):
        p = RAIZ / 'cargue' / nombre
        if p.exists():
            return json.loads(p.read_text(encoding='utf-8'))
        return defecto

    # ------------------------------------------------------------ escritura
    @staticmethod
    def _gz(df: pd.DataFrame) -> bytes:
        buf = io.BytesIO()
        df.to_csv(buf, index=False, compression={'method': 'gzip', 'mtime': 0})
        return buf.getvalue()

    def guardar_lote(self, tipo: str, partes: dict, archivo: str):
        """Guarda varias claves y el registro en un solo commit."""
        reg = self.leer_json('registro.json', {})
        ahora = datetime.now().strftime('%Y-%m-%d %H:%M')
        cambios = {}
        for k, df in partes.items():
            cambios[f'cargue/{tipo}/{k}.csv.gz'] = self._gz(df)
            reg.setdefault(tipo, {})[k] = {'n': int(len(df)), 'archivo': archivo, 'fecha': ahora}
        cambios['cargue/registro.json'] = json.dumps(reg, ensure_ascii=False, indent=1).encode('utf-8')
        self._aplicar(cambios, f'Cargue {tipo}: {", ".join(sorted(partes))[:120]}')

    def guardar_json(self, nombre: str, obj):
        self._aplicar({f'cargue/{nombre}': json.dumps(obj, ensure_ascii=False, indent=1).encode('utf-8')}, f'Actualiza {nombre}')

    def quitar(self, pares: list):
        """Elimina cargues [(tipo, clave)] y los saca del registro, en un solo commit."""
        reg = self.leer_json('registro.json', {})
        cambios = {}
        for tipo, k in pares:
            cambios[f'cargue/{tipo}/{k}.csv.gz'] = None
            reg.get(tipo, {}).pop(k, None)
        cambios['cargue/registro.json'] = json.dumps(reg, ensure_ascii=False, indent=1).encode('utf-8')
        self._aplicar(cambios, f'Quita {len(pares)} cargue(s)')

    def _aplicar(self, cambios: dict, mensaje: str):
        """cambios: {ruta relativa a datos/: bytes | None (borrar)}. Local y, si hay GitHub, un commit."""
        for rel, contenido in cambios.items():
            p = RAIZ / rel
            if contenido is None:
                if p.exists():
                    p.unlink()
            else:
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_bytes(contenido)
        if self.gh:
            self._commit(cambios, mensaje)

    # ------------------------------------------------------------ GitHub (API de datos de Git: un commit por operación)
    def _api(self, metodo, ruta, **kw):
        r = requests.request(metodo, f"https://api.github.com/repos/{self.gh['repo']}/{ruta}", headers=self._h(), timeout=120, **kw)
        if r.status_code >= 400:
            raise RuntimeError(f'GitHub {r.status_code}: {r.text[:200]}')
        return r.json() if r.text else {}

    def _commit(self, cambios: dict, mensaje: str):
        rama = self.gh.get('branch', 'main')
        carpeta = self.gh.get('carpeta', 'datos').strip('/')
        for intento in range(3):
            ref = self._api('GET', f'git/ref/heads/{rama}')['object']['sha']
            base = self._api('GET', f'git/commits/{ref}')['tree']['sha']
            arbol = []
            for rel, contenido in cambios.items():
                ruta = f'{carpeta}/{rel}'
                if contenido is None:
                    existe = requests.get(f"https://api.github.com/repos/{self.gh['repo']}/contents/{ruta}", headers=self._h(),
                                          params={'ref': rama}, timeout=60).status_code == 200
                    if existe:
                        arbol.append({'path': ruta, 'mode': '100644', 'type': 'blob', 'sha': None})
                else:
                    blob = self._api('POST', 'git/blobs', json={'content': base64.b64encode(contenido).decode(), 'encoding': 'base64'})['sha']
                    arbol.append({'path': ruta, 'mode': '100644', 'type': 'blob', 'sha': blob})
            if not arbol:
                return
            tree = self._api('POST', 'git/trees', json={'base_tree': base, 'tree': arbol})['sha']
            commit = self._api('POST', 'git/commits', json={'message': mensaje, 'tree': tree, 'parents': [ref]})['sha']
            try:
                self._api('PATCH', f'git/refs/heads/{rama}', json={'sha': commit})
                return
            except RuntimeError:
                if intento == 2:
                    raise  # otro cambio llegó al mismo tiempo: se reintenta sobre el nuevo estado

    def _h(self):
        return {'Authorization': f"Bearer {self.gh['token']}", 'Accept': 'application/vnd.github+json'}

    def probar_github(self) -> str:
        if not self.gh:
            return 'Sin GitHub: los cargues se guardan solo en el servidor (se pierden si la app se reinicia).'
        r = requests.get(f"https://api.github.com/repos/{self.gh['repo']}", headers=self._h(), timeout=30)
        if r.status_code != 200:
            return f'GitHub respondió {r.status_code}: revise el token y el nombre del repositorio.'
        return 'Conectado a GitHub: ' + self.gh['repo'] + (' (privado)' if r.json().get('private') else ' (¡PÚBLICO! cámbielo a privado)')
