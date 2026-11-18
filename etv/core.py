"""Lógica sin interfaz: normalización de lugares, lectores de SIVIGILA, ovitrampas y Epicollect5, e índices.

Porta la lógica de la página "Vigilancia ETV Guaviare".
"""
from __future__ import annotations

import csv
import io
import math
import re
import unicodedata
from datetime import date, datetime, timedelta

import numpy as np
import pandas as pd

# ---------------------------------------------------------------- constantes
EV = {
    'malaria': {'nombre': 'Malaria', 'color': '#b23a48', 'det': 'Especie',
                'codigos': {'465': None, '470': 'Falciparum', '480': 'Malariae', '490': 'Vivax', '495': 'Complicada'}},
    'dengue': {'nombre': 'Dengue', 'color': '#d26a1c', 'det': 'Clasificación',
               'codigos': {'210': None, '220': 'Dengue grave', '580': 'Mortalidad por dengue'}},
    'leish': {'nombre': 'Leishmaniasis', 'color': '#2a6f97', 'det': 'Forma clínica',
              'codigos': {'420': 'Cutánea', '430': 'Mucosa', '440': 'Visceral'}},
    'chik': {'nombre': 'Chikunguña', 'color': '#7d3c98', 'det': 'Tipo de caso', 'codigos': {'217': None}},
    'zika': {'nombre': 'Zika', 'color': '#16a085', 'det': 'Tipo de caso', 'codigos': {'895': None}},
}
MUNS = [
    {'k': 'SAN JOSE DEL GUAVIARE', 'nombre': 'San José del Guaviare', 'cod': '001', 'pat': re.compile(r'SAN\s*JOSE')},
    {'k': 'EL RETORNO', 'nombre': 'El Retorno', 'cod': '025', 'pat': re.compile(r'RETORNO')},
    {'k': 'CALAMAR', 'nombre': 'Calamar', 'cod': '015', 'pat': re.compile(r'CALAMAR')},
    {'k': 'MIRAFLORES', 'nombre': 'Miraflores', 'cod': '200', 'pat': re.compile(r'MIRAFLORES')},
]
MUN_POR_K = {m['k']: m for m in MUNS}
EDADES = ['0-4', '5-14', '15-29', '30-44', '45-59', '60 y más']
TIPOS_R = [
    {'k': 'elev', 'n': 'Tanques elevados', 'c': '131', 'b': '13121'},
    {'k': 'bajo', 'n': 'Tanques bajos', 'c': '132', 'b': '13221'},
    {'k': 'llan', 'n': 'Llantas', 'c': '133', 'b': '13321'},
    {'k': 'plan', 'n': 'Plantas', 'c': '134', 'b': '13421'},
    {'k': 'divu', 'n': 'Diversos en uso', 'c': '135', 'b': '13521'},
    {'k': 'divs', 'n': 'Diversos sin uso', 'c': '136', 'b': '13621'},
]
CLASES_IPO = [('0 %', 0, '#2f7d4f'), ('1–20 %', 20, '#e3c84a'), ('21–40 %', 40, '#d26a1c'), ('41–60 %', 60, '#d0582b'), ('Más de 60 %', 101, '#b23a48')]
CLASES_BRETEAU = [('Bajo (< 5)', '#2f7d4f'), ('Intermedio (5 a 50)', '#d26a1c'), ('Alto (> 50)', '#b23a48')]

COLS_CASOS = ['ev', 'anio', 'sem', 'u', 'sexo', 'edad', 'hosp', 'cond', 'det', 'lat', 'lon']
COLS_OVI = ['id', 'fecha', 'mun', 'barrio', 'tipo', 'pos', 'huevos', 'larvas', 'pupas', 'lat', 'lon']
COLS_LARV = (['fecha', 'mun', 'zona', 'lugar', 'lat', 'lon', 'estado', 'hab'] + [f'I{i}' for i in range(6)]
             + [f'P{i}' for i in range(6)] + [f'U{i}' for i in range(6)] + ['feb'])
COLS_FEB = ['ini', 'fecha', 'lat', 'lon', 'sexo', 'edad', 'mun', 'lugar', 'fiebre', 'nsint']


# ---------------------------------------------------------------- texto y lugares
def norm(s) -> str:
    s = '' if s is None or (isinstance(s, float) and math.isnan(s)) else str(s)
    s = unicodedata.normalize('NFD', s)
    s = ''.join(c for c in s if unicodedata.category(c) != 'Mn').upper()
    s = re.sub(r'[^A-Z0-9 ]', ' ', s)
    return re.sub(r'\s+', ' ', s).strip()


PREF = re.compile(r'^(VDA|VEREDA|VER|VRDA|BARRIO|BRR|BR|B|BARRRIO|CP|C P|CENTRO POBLADO|INSPECCION|INSP|CASERIO|URB|URBANIZACION|SECTOR|'
                  r'ASENTAMIENTO|RESGUARDO INDIGENA|RESGUARDO|R I|RI|COMUNIDAD|LA VEREDA|EL BARRIO)\s+')


def clave(s) -> str:
    t = norm(s)
    while True:
        p = t
        t = PREF.sub('', t)
        if t == p:
            break
    return re.sub(r'^(EL|LA|LOS|LAS) ', '', t)


def mun_de(txt, cod=None):
    t = norm(txt)
    if t:
        for m in MUNS:
            if m['pat'].search(t):
                return m
    if cod is not None and str(cod).strip() != '':
        c = re.sub(r'\D', '', str(cod))[-3:].zfill(3)
        for m in MUNS:
            if m['cod'] == c:
                return m
    return None


class Lugares:
    """Unidades geográficas (veredas, barrios, cabeceras) y búsqueda por texto."""

    def __init__(self, geo: dict, alias: dict | None = None):
        self.geo = geo
        self.alias = alias or {}
        self.unidades: dict[str, dict] = {}
        self.ix_ver: dict[str, list] = {}
        self.ix_bar: list = []
        for f in geo['veredas']['features']:
            p = f['properties']
            self.unidades[p['id']] = {'nombre': p['nombre'], 'mun': p['mun'], 'tipo': p.get('tipo') or 'Vereda'}
            self.ix_ver.setdefault(norm(p['mun']), []).append((clave(p['nombre']), p['id']))
        for f in geo['barrios']['features']:
            p = f['properties']
            self.unidades[p['id']] = {'nombre': p['nombre'], 'mun': 'San José del Guaviare', 'tipo': 'Barrio'}
            self.ix_bar.append((clave(p['nombre']), p['id']))
        for f in geo['cabeceras']['features']:
            m = mun_de(f['properties']['mun'])
            if m:
                lon, lat = f['geometry']['coordinates']
                self.unidades['C:' + m['k']] = {'nombre': 'Cabecera ' + m['nombre'], 'mun': m['nombre'], 'tipo': 'Cabecera', 'll': (lat, lon)}
        self._centros = None
        self._cache: dict = {}

    # -- búsqueda
    @staticmethod
    def _buscar(lista, t):
        if not t:
            return None
        for k, i in lista:
            if k == t:
                return i
        if len(t) >= 5:
            c = [i for k, i in lista if len(k) >= 4 and (t in k or k in t)]
            if len(c) == 1:
                return c[0]
        return None

    def ubicar(self, mun, texto, area) -> str:
        """Devuelve el id de la vereda/barrio, 'C:MUN' (cabecera) o 'X:MUN|TEXTO' (sin ubicar)."""
        t = clave(texto)
        urbano = bool(re.search(r'^1$|CABECERA|URBAN', norm(area)))
        if mun:
            if mun['k'] == 'SAN JOSE DEL GUAVIARE' and (urbano or not area):
                b = self._buscar(self.ix_bar, t)
                if b:
                    return b
            v = self._buscar(self.ix_ver.get(mun['k'], []), t)
            if v:
                return v
            if mun['k'] == 'SAN JOSE DEL GUAVIARE':
                b = self._buscar(self.ix_bar, t)
                if b:
                    return b
        else:
            hits = [v for lista in self.ix_ver.values() if (v := self._buscar(lista, t))]
            if len(hits) == 1:
                return hits[0]
        mk = mun['k'] if mun else 'SIN MUNICIPIO'
        if urbano and not t:
            return 'C:' + mk
        if mun and t:
            hits = [v for k, lista in self.ix_ver.items() if k != mun['k'] and (v := self._buscar(lista, t))]
            if len(hits) == 1:
                return hits[0]
        x = 'X:' + mk + '|' + (t or 'SIN LUGAR')
        if x in self.alias:
            return x
        if urbano and mun:
            return 'C:' + mk
        return x

    def unidad_lugar(self, mun_txt, lugar, zona):
        """Para la encuesta larvaria: barrio o vereda de una visita (None si no se encuentra)."""
        k = (mun_txt, lugar, zona)
        if k in self._cache:
            return self._cache[k]
        mun = mun_de(mun_txt)
        t = clave(lugar)
        r = None
        if t:
            if not mun or mun['k'] == 'SAN JOSE DEL GUAVIARE':
                b = self._buscar(self.ix_bar, t)
                if b and zona != 'R':
                    r = b
            if r is None and mun:
                r = self._buscar(self.ix_ver.get(mun['k'], []), t)
            elif r is None:
                hits = [v for lista in self.ix_ver.values() if (v := self._buscar(lista, t))]
                if len(hits) == 1:
                    r = hits[0]
            if r is None and not mun:
                r = self._buscar(self.ix_bar, t)
        self._cache[k] = r
        return r

    def resolver(self, u):
        return self.alias.get(u, u)

    def nombre(self, u) -> str:
        x = self.unidades.get(u)
        if x:
            return x['nombre']
        m = re.match(r'^X:[^|]*\|(.*)$', str(u))
        return (m.group(1) + ' (sin ubicar)') if m else str(u)

    def mun_de_unidad(self, u) -> str:
        x = self.unidades.get(u)
        if x:
            return x['mun']
        m = re.match(r'^[CX]:([^|]+)', str(u))
        return MUN_POR_K.get(m.group(1), {}).get('nombre', '') if m else ''

    def centros(self) -> dict:
        if self._centros is None:
            c = {}
            for fc in (self.geo['veredas'], self.geo['barrios']):
                for f in fc['features']:
                    xs, ys = [], []
                    g = f['geometry']
                    polys = g['coordinates'] if g['type'] == 'MultiPolygon' else [g['coordinates']]
                    for poly in polys:
                        for x, y in poly[0]:
                            xs.append(x); ys.append(y)
                    c[f['properties']['id']] = ((min(ys) + max(ys)) / 2, (min(xs) + max(xs)) / 2)
            for k, v in self.unidades.items():
                if 'll' in v:
                    c[k] = v['ll']
            self._centros = c
        return self._centros


# ---------------------------------------------------------------- lectura de archivos
def hnorm(h) -> str:
    s = unicodedata.normalize('NFD', str(h))
    s = ''.join(c for c in s if unicodedata.category(c) != 'Mn').lower()
    return re.sub(r'[^a-z0-9]+', '_', s).strip('_')


def leer_tabla(nombre: str, datos: bytes) -> pd.DataFrame:
    """Lee CSV/XLS/XLSX como texto (todas las hojas de un Excel se concatenan)."""
    ext = nombre.rsplit('.', 1)[-1].lower()
    if ext in ('xls', 'xlsx', 'xlsm'):
        hojas = pd.read_excel(io.BytesIO(datos), sheet_name=None, dtype=object, engine='xlrd' if ext == 'xls' else 'openpyxl')
        dfs = [h for h in hojas.values() if len(h)]
        df = pd.concat(dfs, ignore_index=True) if dfs else pd.DataFrame()
    else:
        txt = decodificar(datos)
        prim = txt.split('\n', 1)[0]
        sep = ';' if prim.count(';') > prim.count(',') else ','
        df = pd.read_csv(io.StringIO(txt), sep=sep, dtype=str, keep_default_na=False)
    df.columns = [str(c).strip() for c in df.columns]
    return df.fillna('')


def decodificar(datos: bytes) -> str:
    try:
        t = datos.decode('utf-8')
    except UnicodeDecodeError:
        t = datos.decode('latin-1')
    return t.lstrip('﻿')


def mapear_cols(df: pd.DataFrame, campos: dict) -> dict:
    nc = {hnorm(c): c for c in df.columns}
    m = {}
    for campo, alias in campos.items():
        for a in alias:
            if a in nc:
                m[campo] = nc[a]
                break
    return m


def _s(v) -> str:
    if v is None:
        return ''
    if isinstance(v, float) and math.isnan(v):
        return ''
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return str(v).strip()


def _num(v, defecto=None):
    try:
        n = float(_s(v).replace(',', '.'))
        return defecto if math.isnan(n) else n
    except ValueError:
        return defecto


# ---------------------------------------------------------------- SIVIGILA
CAMPOS_SIVIGILA = {
    'evento': ['cod_eve', 'codigo_evento', 'cod_evento', 'evento', 'nom_eve', 'nombre_evento'],
    'anio': ['ano', 'anio', 'ano_epi', 'year', 'vigencia'],
    'semana': ['semana', 'semana_epi', 'se', 'sem', 'semana_epidemiologica'],
    'municipio': ['nmun_proce', 'cod_mun_o', 'nmun_resi', 'nom_mun_resi', 'municipio_residencia', 'mun_resi', 'municipio', 'cod_mun_r', 'cod_mun_resi'],
    'lugar': ['vereda', 'vereda_', 'nom_vereda', 'vereda_barrio', 'ubicacion', 'localidad'],
    'barrio': ['bar_ver', 'bar_ver_', 'barrio', 'barrio_vereda'],
    'cpob': ['cen_pobla', 'cen_pobla_', 'centro_poblado'],
    'area': ['area', 'area_', 'area_res', 'area_ocurrencia'],
    'dpto': ['ndep_proce', 'cod_dpto_o', 'ndep_resi', 'cod_dpto_r', 'departamento_residencia', 'dpto_resi'],
    'sexo': ['sexo', 'sexo_', 'sex'],
    'edad': ['edad', 'edad_', 'edad_anos'],
    'unimed': ['uni_med', 'uni_med_', 'unidad_medida', 'uni_med_edad'],
    'gredad': ['gr_edad', 'grupo_edad', 'grupo_de_edad'],
    'tipcas': ['tip_cas', 'tip_cas_', 'tipo_caso', 'tipo_de_caso', 'clasificacion'],
    'hosp': ['pac_hos', 'pac_hos_', 'hospitalizado', 'hospital', 'paciente_hospitalizado'],
    'confin': ['con_fin', 'con_fin_', 'condicion_final', 'cond_fin'],
    'especie': ['especie', 'esp_pla', 'plasmodium', 'especie_plasmodium'],
    'complic': ['complicaci', 'complicada'],
    'ajuste': ['ajuste', 'ajuste_'],
    'lat': ['lat_dir', 'latitud', 'lat', 'coord_y', 'y', 'latitud_residencia'],
    'lon': ['long_dir', 'longitud', 'lon', 'long', 'coord_x', 'x', 'longitud_residencia'],
}
ETQ_SIVIGILA = {'evento': 'Evento (código o nombre)', 'anio': 'Año', 'semana': 'Semana epidemiológica',
                'municipio': 'Municipio de procedencia (o residencia)', 'lugar': 'Vereda', 'barrio': 'Barrio (o barrio/vereda)',
                'cpob': 'Centro poblado', 'area': 'Área (cabecera, rural)', 'dpto': 'Departamento de procedencia', 'sexo': 'Sexo',
                'edad': 'Edad', 'unimed': 'Unidad de medida de la edad', 'gredad': 'Grupo de edad', 'tipcas': 'Tipo de caso',
                'hosp': 'Hospitalizado', 'confin': 'Condición final', 'especie': 'Especie (malaria)', 'complic': 'Malaria complicada',
                'ajuste': 'Ajuste (descartes)', 'lat': 'Latitud', 'lon': 'Longitud'}
VACIO = re.compile(r'^(SIN DATO|SIN INFORMACION|NO APLICA|NO REFIERE|NA|N A|ND|0|NULL)$')


def ev_de(v, forzado=None):
    if forzado:
        return forzado, None
    t = _s(v)
    cod = re.search(r'\d{3}', t)
    if cod:
        for e, info in EV.items():
            if cod.group(0) in info['codigos']:
                return e, info['codigos'][cod.group(0)]
    n = norm(t)
    if 'MALARIA' in n:
        return 'malaria', ('Falciparum' if 'FALCIP' in n else 'Vivax' if 'VIVAX' in n else 'Complicada' if 'COMPLIC' in n else None)
    if 'DENGUE' in n:
        return 'dengue', ('Dengue grave' if 'GRAVE' in n else 'Mortalidad por dengue' if 'MORTAL' in n else None)
    if 'LEISH' in n:
        return 'leish', ('Mucosa' if 'MUCO' in n else 'Visceral' if 'VISCER' in n else 'Cutánea')
    if 'CHIK' in n:
        return 'chik', None
    if 'ZIKA' in n:
        return 'zika', None
    return None


def grupo_edad(f, m):
    if m.get('gredad') and _s(f[m['gredad']]):
        g = _s(f[m['gredad']]).replace(' ', '')
        for e in EDADES:
            if e.replace(' ', '') == g:
                return e
    if not m.get('edad'):
        return ''
    e = _num(f[m['edad']])
    if e is None:
        return ''
    u = _s(f[m['unimed']]) if m.get('unimed') else '1'
    if u and u != '1' and not u.upper().startswith('A'):
        e = 0
    return '0-4' if e < 5 else '5-14' if e < 15 else '15-29' if e < 30 else '30-44' if e < 45 else '45-59' if e < 60 else '60 y más'


def sexo(v):
    t = norm(v)
    return 'M' if t[:1] == 'M' else 'F' if t[:1] == 'F' else ''


def sino(v):
    t = norm(v)
    if t == '1' or t[:1] == 'S':
        return 1
    if t == '2' or t[:1] == 'N' or t == '0':
        return 0
    return None


def tip_cas(v):
    t = norm(v)
    return {'1': 'Sospechoso', '2': 'Probable', '3': 'Conf. lab.', '4': 'Conf. clínica', '5': 'Conf. nexo'}.get(t, _s(v))


def coord_ok(v, tipo):
    n = _num(v)
    if n is None or n == 0:
        return None
    ok = (lambda x: -1 < x < 5) if tipo == 'lat' else (lambda x: -76 < x < -68)
    k = 0
    while not ok(n) and abs(n) > 5 and k < 8:
        n /= 10
        k += 1
    return round(n, 6) if ok(n) else None


def lugar_txt(f, m):
    urb = m.get('area') and _s(f[m['area']]) == '1'
    orden = ['barrio', 'lugar', 'cpob'] if urb else ['lugar', 'barrio', 'cpob']
    for c in orden:
        if not m.get(c):
            continue
        t = re.sub(r'^\s*\d{5,}\s*', '', _s(f[m[c]])).strip()
        if t and not VACIO.match(norm(t)):
            return t
    return ''


def procesar_sivigila(df: pd.DataFrame, m: dict, lug: Lugares, forzado=None):
    filas = []
    desc = {'descartados': 0, 'otro_dpto': 0, 'sin_evento': 0, 'sin_anio': 0}
    for f in df.to_dict('records'):
        if m.get('ajuste') and re.match(r'^(6|D)$', _s(f[m['ajuste']]), re.I):
            desc['descartados'] += 1
            continue
        if m.get('dpto'):
            d = norm(f[m['dpto']])
            if d and not re.search(r'GUAVIARE|^95$', d):
                desc['otro_dpto'] += 1
                continue
        e = ev_de(f[m['evento']] if m.get('evento') else '', forzado)
        if not e:
            desc['sin_evento'] += 1
            continue
        ev, det = e
        anio, sem = _num(f[m['anio']]), _num(f[m['semana']])
        if not anio or not sem:
            desc['sin_anio'] += 1
            continue
        mun = mun_de(f[m['municipio']], f[m['municipio']])
        u = lug.ubicar(mun, lugar_txt(f, m), f[m['area']] if m.get('area') else '')
        if ev == 'malaria' and m.get('especie') and _s(f[m['especie']]):
            t = norm(f[m['especie']])
            det = ('Vivax' if re.search(r'VIV|^1$', t) else 'Falciparum' if re.search(r'FAL|^2$', t) else 'Mixta' if re.search(r'MIX|^4$', t)
                   else 'Malariae' if re.search(r'MALARIAE|^3$', t) else det if t == '0' else _s(f[m['especie']]))
        if ev in ('dengue', 'chik', 'zika') and not det:
            det = tip_cas(f[m['tipcas']]) if m.get('tipcas') else ''
        if ev == 'malaria' and m.get('complic') and _s(f[m['complic']]) == '1':
            det = 'Complicada'
        filas.append({'ev': ev, 'anio': int(anio), 'sem': int(sem), 'u': u,
                      'sexo': sexo(f[m['sexo']]) if m.get('sexo') else '', 'edad': grupo_edad(f, m),
                      'hosp': sino(f[m['hosp']]) if m.get('hosp') else None,
                      'cond': 'M' if m.get('confin') and re.match(r'^(2|M)', norm(f[m['confin']])) else 'V',
                      'det': det or 'Sin dato',
                      'lat': coord_ok(f[m['lat']], 'lat') if m.get('lat') else None,
                      'lon': coord_ok(f[m['lon']], 'lon') if m.get('lon') else None})
    return pd.DataFrame(filas, columns=COLS_CASOS), desc


# ---------------------------------------------------------------- ovitrampas
CAMPOS_OVI = {
    'id': ['id_trampa', 'trampa', 'codigo_trampa', 'cod_trampa', 'no_trampa', 'numero_trampa', 'id'],
    'fecha': ['fecha', 'fecha_revision', 'fecha_de_revision', 'fecha_inspeccion', 'fecha_visita'],
    'mun': ['municipio', 'mpio'],
    'barrio': ['barrio', 'sector', 'localidad'],
    'tipo': ['tipo_pred', 'tipo_predio', 'tipo_de_predio', 'uso_predio'],
    'pos': ['positivo', 'positiva', 'resultado', 'estado'],
    'huevos': ['huevos', 'n_huevos', 'no_huevos', 'cantidad_huevos'],
    'larvas': ['larvas', 'n_larvas'],
    'pupas': ['pupas', 'n_pupas'],
    'lat': ['lat', 'latitud', 'y', 'coord_y'],
    'lon': ['lon', 'long', 'longitud', 'x', 'coord_x'],
}
ETQ_OVI = {'id': 'Código de la trampa', 'fecha': 'Fecha de revisión', 'mun': 'Municipio', 'barrio': 'Barrio', 'tipo': 'Tipo de predio',
           'pos': 'Positiva (1/0, Sí/No)', 'huevos': 'Huevos', 'larvas': 'Larvas', 'pupas': 'Pupas', 'lat': 'Latitud', 'lon': 'Longitud'}


def fecha_iso(v) -> str:
    if isinstance(v, (datetime, date, pd.Timestamp)):
        return v.strftime('%Y-%m-%d')
    t = _s(v)
    m = re.match(r'^(\d{4})-(\d{1,2})-(\d{1,2})', t)
    if m:
        return f'{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}'
    m = re.match(r'^(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{2,4})', t)
    if m:
        y = ('20' + m.group(3)) if len(m.group(3)) == 2 else m.group(3)
        return f'{y}-{int(m.group(2)):02d}-{int(m.group(1)):02d}'
    if re.match(r'^\d{5}$', t):
        return (date(1899, 12, 30) + timedelta(days=int(t))).isoformat()
    return ''


def procesar_ovi(df: pd.DataFrame, m: dict):
    filas, sin_id = [], 0
    for f in df.to_dict('records'):
        id_ = _s(f[m['id']])
        if not id_:
            sin_id += 1
            continue
        fecha = fecha_iso(f[m['fecha']]) if m.get('fecha') else ''
        hv = _num(f[m['huevos']], 0) if m.get('huevos') else 0
        lv = _num(f[m['larvas']], 0) if m.get('larvas') else 0
        pp = _num(f[m['pupas']], 0) if m.get('pupas') else 0
        if m.get('pos') and _s(f[m['pos']]):
            t = norm(f[m['pos']])
            pos = 1 if (t == '1' or t[:1] == 'S' or t.startswith('POS')) else 0
        else:
            pos = 1 if hv + lv + pp > 0 else 0
        filas.append({'id': id_, 'fecha': fecha, 'mun': _s(f[m['mun']]) if m.get('mun') else '',
                      'barrio': re.sub(r'\s+', ' ', _s(f[m['barrio']])) if m.get('barrio') else '',
                      'tipo': _s(f[m['tipo']]) if m.get('tipo') else '', 'pos': pos, 'huevos': hv, 'larvas': lv, 'pupas': pp,
                      'lat': _num(f[m['lat']]) if m.get('lat') else None, 'lon': _num(f[m['lon']]) if m.get('lon') else None})
    return pd.DataFrame(filas, columns=COLS_OVI), sin_id


def col_ipo(v):
    for _, mx, c in CLASES_IPO:
        if v <= mx:
            return c
    return CLASES_IPO[-1][2]


# ---------------------------------------------------------------- Epicollect5 (encuesta larvaria)
RE_UUID = re.compile(r'^[0-9a-f]{8}-[0-9a-f]{4}-', re.I)
RE_ZONA = re.compile(r'^\d{1,2}[NS]$')


def utm2ll(N, E, zona):
    k0, a, e2 = 0.9996, 6378137.0, 0.00669438
    ep2 = e2 / (1 - e2)
    x, y = E - 500000, N
    zn = int(re.sub(r'\D', '', str(zona)) or 18)
    lon0 = math.radians((zn - 1) * 6 - 180 + 3)
    M = y / k0
    mu = M / (a * (1 - e2 / 4 - 3 * e2 * e2 / 64 - 5 * e2 ** 3 / 256))
    e1 = (1 - math.sqrt(1 - e2)) / (1 + math.sqrt(1 - e2))
    p1 = (mu + (3 * e1 / 2 - 27 * e1 ** 3 / 32) * math.sin(2 * mu) + (21 * e1 * e1 / 16 - 55 * e1 ** 4 / 32) * math.sin(4 * mu)
          + (151 * e1 ** 3 / 96) * math.sin(6 * mu) + (1097 * e1 ** 4 / 512) * math.sin(8 * mu))
    N1 = a / math.sqrt(1 - e2 * math.sin(p1) ** 2)
    T1, C1 = math.tan(p1) ** 2, ep2 * math.cos(p1) ** 2
    R1 = a * (1 - e2) / (1 - e2 * math.sin(p1) ** 2) ** 1.5
    D = x / (N1 * k0)
    lat = p1 - (N1 * math.tan(p1) / R1) * (D * D / 2 - (5 + 3 * T1 + 10 * C1 - 4 * C1 * C1 - 9 * ep2) * D ** 4 / 24
                                          + (61 + 90 * T1 + 298 * C1 + 45 * T1 * T1 - 252 * ep2 - 3 * C1 * C1) * D ** 6 / 720)
    lon = lon0 + (D - (1 + 2 * T1 + C1) * D ** 3 / 6 + (5 - 2 * C1 + 28 * T1 - 3 * C1 * C1 + 8 * ep2 + 24 * T1 * T1) * D ** 5 / 120) / math.cos(p1)
    return math.degrees(lat), math.degrees(lon)


def filas_texto(datos: bytes) -> list[list[str]]:
    t = decodificar(datos)
    l0 = t.split('\n', 1)[0]
    if l0.count(';') >= l0.count(','):
        return [x.split(';') for x in re.split(r'\r?\n', t) if x.strip()]
    return [r for r in csv.reader(io.StringIO(t)) if any(c.strip() for c in r)]


def clasificar_ec5(h):
    H = [str(x).lstrip('﻿').strip() for x in h]
    s = '|'.join(H)
    if re.search(r'ec5_branch_owner_uuid', s, re.I):
        if re.search(r'SINTOMAS|121_DIRECCION', s, re.I):
            return {'tipo': 'pac', 'H': H}
        for i, t in enumerate(TIPOS_R):
            if '_' + t['b'] + '_' in s:
                return {'tipo': 'rama', 'idx': i, 'H': H}
        return None
    if re.search(r'ec5_uuid', s, re.I) and re.search(r'FECHA', s, re.I):
        return {'tipo': 'form', 'H': H}
    return None


def iso_dmy(d):
    m = re.match(r'^(\d{1,2})/(\d{1,2})/(\d{4})', _s(d))
    return f'{m.group(3)}-{int(m.group(2)):02d}-{int(m.group(1)):02d}' if m else fecha_iso(d)


def n_int(v):
    t = _s(v)
    if re.match(r'^11 o', t, re.I):
        return 11
    return int(t) if re.match(r'^\d+$', t) else None


def procesar_ec5(archivos: list[dict]):
    """archivos: [{'nombre', 'filas', 'c'}]. Devuelve dict con larv, feb (DataFrames) y estadísticas, o {'error'}."""
    form = next((a for a in archivos if a['c'] and a['c']['tipo'] == 'form'), None)
    if not form:
        return {'error': 'Falta el archivo principal de la encuesta (form-1, con la columna ec5_uuid).'}
    BP, BU, FEB = {}, {}, {}
    for a in archivos:
        if not (a['c'] and a['c']['tipo'] == 'rama'):
            continue
        H = a['c']['H']
        iP = next((i for i, x in enumerate(H) if re.search(r'_PUPAS$', x, re.I)), -1)
        for r in a['filas'][1:]:
            if not r or not RE_UUID.match(r[0] or ''):
                continue
            o = r[0]
            BP.setdefault(o, [0] * 6)[a['c']['idx']] += 1
            BU.setdefault(o, [0] * 6)[a['c']['idx']] += (n_int(r[iP]) if 0 <= iP < len(r) else 0) or 0
    pac = next((a for a in archivos if a['c'] and a['c']['tipo'] == 'pac'), None)
    if pac:
        H = pac['c']['H']
        ix = lambda rx: next((i for i, x in enumerate(H) if re.search(rx, x, re.I)), -1)
        iS, iE, iF, iY = ix(r'_SEXO$'), ix(r'_EDAD$'), ix(r'FECHA_DE_INIC'), ix(r'SINTOMAS')
        g = lambda r, i: r[i] if 0 <= i < len(r) else ''
        for r in pac['filas'][1:]:
            if not r or not RE_UUID.match(r[0] or ''):
                continue
            s = _s(g(r, iY))
            FEB.setdefault(r[0], []).append([iso_dmy(g(r, iF)), sexo(g(r, iS)), n_int(g(r, iE)),
                                             1 if re.search('fiebre', s, re.I) else 0, len([x for x in s.split(',') if x.strip()])])
    H = form['c']['H']
    col = lambda rx: next((i for i, x in enumerate(H) if re.search(rx, x, re.I)), -1)
    ix = {'fecha': col(r'^\d+_1_FECHA$'), 'mun': col(r'_MUNICIPIO$'), 'zona': col(r'^\d+_4_ZONA$'), 'barrio': col(r'_BARRIO$'),
          'vereda': col(r'_VEREDA$'), 'Z': col(r'^UTM_Zone'), 'N': col(r'^UTM_Northing'), 'E': col(r'^UTM_Easting'),
          'cerr': col(r'VIVIENDA_CERRA'), 'insp': col(r'INSPECCIONADA'), 'hab': col(r'HABITANT')}
    ci = [(col(r'^\d+_' + t['c'] + '_'), col(r'^\d+_' + t['c'] + '1_')) for t in TIPOS_R]
    larv, feb = [], []
    st = {'visitas': 0, 'completas': 0, 'sin_datos': 0, 'coords': 0}
    for r in form['filas'][1:]:
        if not r or not RE_UUID.match(r[0] or ''):
            continue
        st['visitas'] += 1
        g = lambda i: r[i] if 0 <= i < len(r) else ''
        uid = r[0]
        creado = _s(g(1))[:10]
        titulo = re.sub(r'\s+\d+$', '', _s(g(3))).strip()
        fecha, mun, zona, lugar = creado, '', '', titulo
        lat = lon = estado = hab = None
        I = P = None

        def ll(n, e, z):
            nonlocal lat, lon
            N_, E_ = _num(n), _num(e)
            if N_ is None or E_ is None:
                return
            p = utm2ll(N_, E_, z)
            if -1 < p[0] < 5 and -76 < p[1] < -68:
                lat, lon = round(p[0], 6), round(p[1], 6)

        alineada = ix['Z'] >= 0 and RE_ZONA.match(_s(g(ix['Z'])))
        if alineada:
            fecha = iso_dmy(g(ix['fecha'])) or creado
            mun = _s(g(ix['mun']))
            zona = _s(g(ix['zona']))[:1].upper()
            lugar = _s(g(ix['barrio'])) or _s(g(ix['vereda'])) or titulo
            ll(g(ix['N']), g(ix['E']), g(ix['Z']))
            if re.match(r'^s', _s(g(ix['cerr'])), re.I):
                estado = 0
            elif re.match(r'^n', _s(g(ix['insp'])), re.I):
                estado = 2
            elif re.match(r'^s', _s(g(ix['insp'])), re.I):
                estado = 1
                hab = n_int(g(ix['hab']))
                I = [n_int(g(c[0])) or 0 for c in ci]
                P = [n_int(g(c[1])) or 0 for c in ci]
                st['completas'] += 1
        else:
            f = [_s(v) for v in r if _s(v) != '']
            z = next((i for i, v in enumerate(f) if RE_ZONA.match(v)), -1)
            if z > 5 and len(f) > z + 4:
                if len(f) > 4 and re.match(r'^\d{1,2}/\d{1,2}/\d{4}$', f[4]):
                    fecha = iso_dmy(f[4])
                pre = f[5:z - 5] if z - 5 > 5 else []
                mun = pre[1] if len(pre) > 1 else ''
                zona = (pre[2] if len(pre) > 2 else '')[:1].upper()
                lugar = pre[3] if len(pre) > 3 else titulo
                ll(f[z - 2], f[z - 1], f[z])
                a = f[z + 1:]
                if len(a) > 3 and a[3] == 'Si':
                    estado = 0
                elif len(a) > 4 and a[4] == 'No':
                    estado = 2
                elif len(a) > 4 and a[4] == 'Si':
                    estado = 1
                    hab = n_int(a[5]) if len(a) > 5 else None
                    seq = []
                    for v in a[7:]:
                        n = n_int(v)
                        if n is None:
                            break
                        seq.append(n)
                    try:
                        if not seq:
                            raise ValueError
                        seq.pop(0)
                        I, P = [], []
                        for _ in TIPOS_R:
                            if not seq:
                                raise ValueError
                            i = seq.pop(0)
                            p = (seq.pop(0) if seq else None) if i else 0
                            if not seq and p is None:
                                raise ValueError
                            if seq:
                                seq.pop(0)  # conteo de la rama
                            I.append(i); P.append(p or 0)
                        st['completas'] += 1
                    except ValueError:
                        I = P = None
            else:
                st['sin_datos'] += 1
        if lat is not None:
            st['coords'] += 1
        if not P:
            P = BP.get(uid, [0] * 6)
        fb = FEB.get(uid, [])
        fila = {'fecha': fecha, 'mun': mun, 'zona': zona, 'lugar': lugar, 'lat': lat, 'lon': lon, 'estado': estado, 'hab': hab, 'feb': len(fb)}
        for i in range(6):
            fila[f'I{i}'] = I[i] if I else None
            fila[f'P{i}'] = P[i]
            fila[f'U{i}'] = BU.get(uid, [0] * 6)[i]
        larv.append(fila)
        for x in fb:
            feb.append({'ini': x[0] or fecha, 'fecha': fecha, 'lat': lat, 'lon': lon, 'sexo': x[1], 'edad': x[2],
                        'mun': mun, 'lugar': lugar, 'fiebre': x[3], 'nsint': x[4]})
    st['ramas'] = len(BP)
    st['febriles'] = sum(len(v) for v in FEB.values())
    return {'larv': pd.DataFrame(larv, columns=COLS_LARV), 'feb': pd.DataFrame(feb, columns=COLS_FEB), 'st': st}


# ---------------------------------------------------------------- índices entomológicos
def indices_larv(df: pd.DataFrame) -> dict:
    P = df[[f'P{i}' for i in range(6)]].fillna(0)
    U = df[[f'U{i}' for i in range(6)]].fillna(0)
    I = df[[f'I{i}' for i in range(6)]]
    den_m = ~df['estado'].isin([0, 2])
    den = int(den_m.sum())
    rp_v = P[den_m].sum(axis=1)
    pos = int((rp_v > 0).sum())
    rp = float(rp_v.sum())
    conI = den_m & I.notna().all(axis=1)
    ri = float(I[conI].sum().sum())
    rpI = float(P[conI].sum().sum())
    hab = pd.to_numeric(df['hab'], errors='coerce')
    conH = den_m & (hab > 0)
    habT = float(hab[conH].sum())
    return {'n': len(df), 'den': den, 'cerradas': int((df['estado'] == 0).sum()), 'pos': pos,
            'iv': pos / den * 100 if den else None, 'ib': rp / den * 100 if den else None,
            'ir': rpI / ri * 100 if ri else None, 'nI': int(conI.sum()), 'pup': float(U.sum().sum()),
            'ppp': float(U[conH].sum().sum()) / habT if habT else None, 'rp': rp}


def clase_breteau(ib):
    if ib is None:
        return None
    return 0 if ib < 5 else 1 if ib <= 50 else 2


def semana_de(iso: str):
    try:
        d = date.fromisoformat(str(iso)[:10])
    except ValueError:
        return None
    return min(53, (d - date(d.year, 1, 1)).days // 7 + 1)


# ---------------------------------------------------------------- geometría simple (metros locales)
def proyector(lat0):
    kx, ky = 111320 * math.cos(math.radians(lat0)), 110540
    return lambda lat, lon: (lon * kx, lat * ky)


def hull(ps):
    p = sorted(set(map(tuple, ps)))
    if len(p) < 3:
        return p
    cr = lambda o, a, b: (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])
    lo, up = [], []
    for q in p:
        while len(lo) >= 2 and cr(lo[-2], lo[-1], q) <= 0:
            lo.pop()
        lo.append(q)
    for q in reversed(p):
        while len(up) >= 2 and cr(up[-2], up[-1], q) <= 0:
            up.pop()
        up.append(q)
    return lo[:-1] + up[:-1]


class Rejilla:
    def __init__(self, xy, celda):
        self.xy, self.c = xy, celda
        self.g = {}
        for i, (x, y) in enumerate(xy):
            self.g.setdefault((math.floor(x / celda), math.floor(y / celda)), []).append(i)

    def vecinos(self, x, y):
        cx, cy = math.floor(x / self.c), math.floor(y / self.c)
        out = []
        for i in (-1, 0, 1):
            for j in (-1, 0, 1):
                out.extend(self.g.get((cx + i, cy + j), ()))
        return out

    def dentro(self, x, y, R):
        return any((self.xy[i][0] - x) ** 2 + (self.xy[i][1] - y) ** 2 <= R * R for i in self.vecinos(x, y))


def mezclar(a, b, t):
    pa = [int(a.lstrip('#')[i:i + 2], 16) for i in (0, 2, 4)]
    pb = [int(b.lstrip('#')[i:i + 2], 16) for i in (0, 2, 4)]
    return '#' + ''.join(f'{round(x + (y - x) * t):02x}' for x, y in zip(pa, pb))


def fmt(n, nd=0):
    if n is None or (isinstance(n, float) and math.isnan(n)):
        return 's/d'
    s = f'{n:,.{nd}f}'
    return s.replace(',', 'X').replace('.', ',').replace('X', '.')
