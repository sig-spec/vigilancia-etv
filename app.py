"""Vigilancia de ETV · Secretaría de Salud del Guaviare (PNEET).

Aplicación Streamlit: mapas y análisis de malaria, dengue, leishmaniasis, chikunguña y zika (SIVIGILA),
ovitrampas y encuesta larvaria (Epicollect5). La persona encargada carga los archivos con una clave.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import math
from pathlib import Path

import folium
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from folium.plugins import HeatMap
import streamlit.components.v1 as components

from etv import core as C
from etv import mapas as M
from etv.store import RAIZ, Almacen

st.set_page_config(page_title='Vigilancia ETV · Guaviare', page_icon='🦟', layout='wide', initial_sidebar_state='collapsed')
BASE = Path(__file__).parent


# =============================================================== estilo y encabezado
def _b64(p):
    return base64.b64encode((BASE / p).read_bytes()).decode()


st.markdown(f"""
<style>
  .block-container {{padding-top: 3.6rem; max-width: 1400px;}}
  .enc {{display:flex;align-items:center;gap:14px;padding:6px 0 10px;border-bottom:4px solid {M.AZUL};margin-bottom:10px;flex-wrap:wrap}}
  .enc img {{height:52px}} .enc .sep {{width:1px;height:44px;background:#c9d3de}}
  .enc h1 {{font-size:1.45rem;margin:0;color:{M.AZUL};font-weight:700;line-height:1.2}}
  .enc p {{margin:0;color:{M.GRIS};font-size:.9rem}}
  .kpi {{background:#f4f7fb;border-left:5px solid var(--c,{M.AZUL});border-radius:6px;padding:10px 12px;height:100%}}
  .kpi .v {{font-size:1.6rem;font-weight:700;color:var(--c,{M.AZUL});line-height:1.1}}
  .kpi .l {{font-size:.82rem;color:{M.GRIS}}} .kpi .d {{font-size:.8rem;margin-top:2px}}
  .up {{color:#b23a48}} .down {{color:#2f7d4f}}
  .nota {{color:{M.GRIS};font-size:.82rem}}
  div[data-testid="stMetricValue"] {{color:{M.AZUL}}}
  h3 {{color:{M.AZUL}}}
</style>
<div class="enc">
  <img src="data:image/png;base64,{_b64('assets/logo_gobernacion.png')}" alt="Gobernación del Guaviare">
  <span class="sep"></span>
  <img src="data:image/png;base64,{_b64('assets/logo_salud.png')}" alt="Secretaría de Salud del Guaviare">
  <div><h1>Vigilancia de enfermedades transmitidas por vectores</h1>
  <p>Secretaría de Salud del Guaviare · Programa ETV (PNEET) · SIVIGILA, ovitrampas y encuesta larvaria</p></div>
</div>""", unsafe_allow_html=True)


def kpi(col, valor, etiqueta, color=M.AZUL, detalle=''):
    col.markdown(f'<div class="kpi" style="--c:{color}"><div class="v">{valor}</div><div class="l">{etiqueta}</div>'
                 f'{"<div class=d>" + detalle + "</div>" if detalle else ""}</div>', unsafe_allow_html=True)


def ver_mapa(m, alto=560, clave=None):
    folium.LayerControl(collapsed=True).add_to(m)
    m.get_root().height = f'{alto}px'
    components.html(m.get_root().render(), height=alto + 4)


def grafico(fig, nombre):
    st.plotly_chart(fig, width='stretch', config=M.cfg_png(nombre))


def secreto(*claves, defecto=None):
    try:
        v = st.secrets
        for c in claves:
            v = v[c]
        return v
    except Exception:
        return defecto


# =============================================================== acceso de consulta (opcional)
CLAVE_CONSULTA = secreto('CLAVE_CONSULTA')
if CLAVE_CONSULTA and not st.session_state.get('consulta_ok'):
    st.info('Esta aplicación requiere clave de consulta.')
    c = st.text_input('Clave de consulta', type='password')
    if c and hmac.compare_digest(c, str(CLAVE_CONSULTA)):
        st.session_state.consulta_ok = True
        st.rerun()
    elif c:
        st.error('Clave incorrecta.')
    st.stop()


# =============================================================== datos
almacen = Almacen(secreto('github', defecto=None))


@st.cache_data(show_spinner=False)
def geo_ref():
    return (json.loads((RAIZ / 'geo.json').read_text(encoding='utf-8')),
            json.loads((RAIZ / 'ref.json').read_text(encoding='utf-8')))


GEO, REF = geo_ref()


@st.cache_resource(show_spinner=False)
def lugares(alias_json: str):
    return C.Lugares(GEO, json.loads(alias_json))


@st.cache_data(show_spinner='Cargando datos…')
def datos(version: str, alias_json: str):
    lug = lugares(alias_json)
    casos = Almacen.leer('casos')
    if len(casos):
        casos['u'] = casos['u'].map(lug.resolver)
        um = {u: lug.mun_de_unidad(u) for u in casos['u'].unique()}
        casos['mun'] = casos['u'].map(um)
        for c in ('anio', 'sem'):
            casos[c] = casos[c].astype(int)
    ovi = Almacen.leer('ovi')
    if len(ovi):
        ovi['pos'] = ovi['pos'].fillna(0).astype(int)
        ovi['fecha'] = ovi['fecha'].fillna('').astype(str)
    larv = Almacen.leer('larv')
    if len(larv):
        larv = larv.fillna({'mun': '', 'zona': '', 'lugar': '', 'fecha': ''})
        combos = {k: lug.unidad_lugar(*k) for k in set(zip(larv['mun'], larv['lugar'], larv['zona']))}
        larv['u'] = [combos[k] for k in zip(larv['mun'], larv['lugar'], larv['zona'])]
        larv['mun_n'] = [(C.mun_de(mm) or {}).get('nombre') or (lug.unidades.get(u) or {}).get('mun', '') for mm, u in zip(larv['mun'], larv['u'])]
    feb = Almacen.leer('feb')
    if len(feb):
        feb = feb.fillna({'mun': '', 'lugar': '', 'ini': ''})
        feb['u'] = [lug.unidad_lugar(mm, l, '') for mm, l in zip(feb['mun'], feb['lugar'])]
        feb['mun_n'] = [(C.mun_de(mm) or {}).get('nombre') or (lug.unidades.get(u) or {}).get('mun', '') for mm, u in zip(feb['mun'], feb['u'])]
    return casos, ovi, larv, feb


ALIAS = Almacen.leer_json('alias.json', {})
ALIAS_JSON = json.dumps(ALIAS, sort_keys=True)
LUG = lugares(ALIAS_JSON)
CASOS, OVI, LARV, FEB = datos(Almacen.version(), ALIAS_JSON)


def anios_ev(ev):
    return sorted(CASOS.loc[CASOS.ev == ev, 'anio'].unique().tolist()) if len(CASOS) else []


def filtro_casos(clave, eventos=None, permitir_todos=True, con_mun=True):
    """Fila de filtros común. Devuelve (ev, anio|None, s1, s2, mun|None)."""
    evs = eventos or [e for e in C.EV if (CASOS.ev == e).any()] or list(C.EV)
    c = st.columns([1.2, 1, 1.6, 1.3] if con_mun else [1.2, 1, 1.6])
    ev = c[0].selectbox('Evento', evs, format_func=lambda e: C.EV.get(e, {'nombre': e})['nombre'], key=clave + 'ev')
    an = anios_ev(ev)
    opciones = (['Todos'] if permitir_todos else []) + [str(a) for a in reversed(an)]
    anio = c[1].selectbox('Año', opciones, index=1 if permitir_todos and len(opciones) > 1 else 0, key=clave + 'an')
    s1, s2 = c[2].slider('Semanas epidemiológicas', 1, 53, (1, 53), key=clave + 'se')
    mun = None
    if con_mun:
        mun = c[3].selectbox('Municipio', ['Todos'] + [m['nombre'] for m in C.MUNS], key=clave + 'mu')
        mun = None if mun == 'Todos' else mun
    return ev, (None if anio == 'Todos' else int(anio)), s1, s2, mun


def cortes_cuantil(vals, n=5):
    vals = sorted(v for v in vals if v > 0)
    if not vals:
        return []
    q = lambda p: vals[min(len(vals) - 1, int(p * len(vals)))]
    ct = []
    for p in [(i + 1) / n for i in range(n - 1)] + [1]:
        v = q(p) if p < 1 else vals[-1]
        if not ct or v > ct[-1]:
            ct.append(v)
    return ct


def rampa(color, i, n):
    return C.mezclar('#ffffff', color, [0.22, 0.42, 0.62, 0.82, 1][min(4, round(i * 4 / max(1, n - 1)))])


# =============================================================== 1. TABLERO DE CASOS
def pagina_tablero():
    if not len(CASOS):
        st.warning('Todavía no hay casos cargados.')
        return
    ev, anio, s1, s2, mun = filtro_casos('t')
    info = C.EV[ev]
    todos = CASOS[CASOS.ev == ev]
    sel = todos[(todos['sem'].between(s1, s2)) & ((todos.anio == anio) if anio else True) & ((todos.mun == mun) if mun else True)]
    conteo = sel.groupby('u').size().to_dict()

    # KPIs
    k = st.columns(4)
    comp = ''
    if anio:
        ant = todos[(todos.anio == anio - 1) & todos['sem'].between(s1, s2) & ((todos.mun == mun) if mun else True)]
        if len(ant):
            d = (len(sel) - len(ant)) / len(ant) * 100
            comp = f'<span class="{"up" if d > 0 else "down"}">{"▲" if d > 0 else "▼"} {abs(d):.0f} % frente a {anio - 1} ({C.fmt(len(ant))})</span>'
        else:
            comp = f'<span class="nota">Sin datos de {anio - 1} para comparar</span>'
    kpi(k[0], C.fmt(len(sel)), f'Casos de {info["nombre"].lower()} {("en " + str(anio)) if anio else "(todos los años)"} · SE {s1}–{s2}', info['color'], comp)
    kpi(k[1], C.fmt(sum(1 for u in conteo if u[:1] in 'VB')), 'Veredas y barrios con al menos un caso')
    hv = sel[sel.hosp.isin([0, 1])]
    muertes = int((sel.cond == 'M').sum())
    kpi(k[2], f'{hv.hosp.mean() * 100:.0f} %' if len(hv) else 's/d', 'Hospitalizados', M.AZUL,
        f'<span class="{"up" if muertes else "nota"}">{C.fmt(muertes) + " fallecidos" if muertes else "Sin fallecidos registrados"}</span>')
    sin_u = int(sel.u.str.startswith('X:').sum())
    kpi(k[3], C.fmt(sin_u), 'Casos sin ubicar en el mapa', '#d26a1c' if sin_u else '#2f7d4f',
        'Asígnelos en <b>Cargar datos → Sin ubicar</b>' if sin_u else '')

    # mapa
    st.markdown(f'### {info["nombre"]}: casos por vereda y barrio')
    ct = cortes_cuantil([v for u, v in conteo.items() if u[:1] in 'VB'])

    def clase(n):
        if not n:
            return -1
        for i, c in enumerate(ct):
            if n <= c:
                return i
        return len(ct) - 1

    color = lambda v: '#f4f7fb' if not v else rampa(info['color'], clase(v), len(ct))
    m = M.mapa_base()
    tt = lambda p, v: f"<b>{p['nombre']}</b><br>{LUG.unidades.get(p['id'], {}).get('tipo', '')} · {LUG.unidades.get(p['id'], {}).get('mun', '')}<br>Casos: <b>{v or 0}</b>"
    filtro_mun = (lambda p: (LUG.unidades.get(p['id'], {}).get('mun') == mun)) if mun else (lambda p: True)
    M.coropleta(m, GEO['veredas'], lambda p: conteo.get(p['id']) if filtro_mun(p) else None, color, tt, 'Veredas')
    M.coropleta(m, GEO['barrios'], lambda p: conteo.get(p['id']) if filtro_mun(p) else None, color, tt, 'Barrios San José')
    M.capas_ref(m, GEO, REF, encendidas=('muni',), excluir=('ver', 'bar', 'cab'))
    gcab = folium.FeatureGroup(name='Cabeceras (casos sin barrio)')
    for uid, u in LUG.unidades.items():
        if 'll' not in u:
            continue
        n = conteo.get(uid, 0)
        folium.CircleMarker(u['ll'], radius=min(6 + math.sqrt(n) * 1.6, 22) if n else 4, color='#102a43', weight=1.2, fill=True,
                            fill_color=info['color'] if n else '#eef2f7', fill_opacity=.9,
                            tooltip=f"<b>{u['nombre']}</b><br>{C.fmt(n)} casos sin vereda o barrio").add_to(gcab)
    gcab.add_to(m)
    prev, pol = 0, []
    for i, c in enumerate(ct):
        pol.append((rampa(info['color'], i, len(ct)), f'{prev + 1}–{c}' if c > prev + 1 else f'{c}'))
        prev = c
    pol.append(('#f4f7fb', 'Sin casos'))
    M.leyenda(m, f'{info["nombre"]} (casos)', puntos=[(info['color'], 'Cabecera (casos sin barrio)')],
              lineas=[(M.AZUL, 'Límite municipal')], poligonos=pol)
    if mun:
        pts = [u['ll'] for u in LUG.unidades.values() if u.get('mun') == mun and 'll' in u]
        mm = next(f for f in GEO['municipios']['features'] if f['properties']['mun'] == mun)
        m.fit_bounds(M.limites({'features': [mm]}))
    else:
        m.fit_bounds(M.limites(GEO['municipios']))
    ver_mapa(m, 600, 'mapa_tablero')
    cab = int(sel.u.str.startswith('C:').sum())
    st.markdown(f'<p class="nota">{C.fmt(sin_u) + " casos sin ubicar no aparecen en el mapa. " if sin_u else ""}'
                f'{C.fmt(cab) + " casos están en la cabecera municipal sin barrio. " if cab else ""}'
                f'{"La base inicial de malaria no trae registros de 2025." if ev == "malaria" else ""}</p>', unsafe_allow_html=True)

    # series
    c1, c2 = st.columns([1.6, 1])
    with c1:
        sems = list(range(s1, s2 + 1))
        base_m = todos[todos.mun == mun] if mun else todos
        fig = go.Figure()
        if not anio:
            ans = anios_ev(ev)
            for i, a in enumerate(ans):
                y = base_m[base_m.anio == a].groupby('sem').size().reindex(sems, fill_value=0)
                fig.add_trace(go.Scatter(x=sems, y=y, name=str(a), mode='lines', line=dict(width=1.6, shape='spline',
                                         color=C.mezclar('#ffffff', info['color'], .25 + .75 * (i + 1) / len(ans)))))
            nota = 'Elija un año para ver el canal endémico.'
            titulo = 'Casos por semana, cada año'
        else:
            act = base_m[base_m.anio == anio].groupby('sem').size().reindex(sems, fill_value=0)
            tot = todos.groupby('anio').size()
            ant = [a for a in anios_ev(ev) if a < anio]
            med = sorted(tot.get(a, 0) for a in ant)[len(ant) // 2] if ant else 0
            prev_ = [a for a in ant if tot.get(a, 0) >= med * .2]
            fig.add_trace(go.Bar(x=sems, y=act, name=str(anio), marker_color=info['color']))
            if len(prev_) >= 3:
                mat = np.array([base_m[base_m.anio == a].groupby('sem').size().reindex(sems, fill_value=0).values for a in prev_])
                for q, n, col in [(.75, 'Q3 (zona de alerta)', '#b23a48'), (.5, 'Mediana (seguridad)', '#d26a1c'), (.25, 'Q1 (éxito)', '#2f7d4f')]:
                    fig.add_trace(go.Scatter(x=sems, y=np.quantile(mat, q, axis=0), name=n, mode='lines', line=dict(color=col, width=1.6, shape='spline')))
                fuera = [a for a in ant if a not in prev_]
                nota = f'Canal endémico por cuartiles de {", ".join(map(str, prev_))}' + (f' (se excluye {", ".join(map(str, fuera))} por registro incompleto).' if fuera else '.')
            else:
                nota = 'No hay suficientes años anteriores (mínimo 3) para el canal endémico.'
            titulo = f'Casos por semana epidemiológica, {anio}'
        grafico(M.estilo_fig(fig, titulo, 360), f'semanas_{ev}_{anio or "todos"}')
        st.markdown(f'<p class="nota">{nota}</p>', unsafe_allow_html=True)
    with c2:
        an = anios_ev(ev)
        ya = todos[todos['sem'].between(s1, s2) & ((todos.mun == mun) if mun else True)].groupby('anio').size().reindex(an, fill_value=0)
        fig = go.Figure(go.Bar(x=[str(a) for a in an], y=ya.values, text=ya.values, textposition='outside',
                               marker_color=[info['color'] if a == anio else C.mezclar('#ffffff', info['color'], .5) for a in an]))
        grafico(M.estilo_fig(fig, f'Casos por año (SE {s1}–{s2})', 360), f'anios_{ev}')

    c1, c2, c3 = st.columns(3)
    with c1:
        mm_ = sel[sel.sexo == 'M'].groupby('edad').size().reindex(C.EDADES, fill_value=0)
        ff_ = sel[sel.sexo == 'F'].groupby('edad').size().reindex(C.EDADES, fill_value=0)
        fig = go.Figure([go.Bar(y=C.EDADES, x=-mm_.values, name='Hombres', orientation='h', marker_color='#5b6b7c',
                                customdata=mm_.values, hovertemplate='%{y}: %{customdata} hombres<extra></extra>'),
                         go.Bar(y=C.EDADES, x=ff_.values, name='Mujeres', orientation='h', marker_color=info['color'],
                                hovertemplate='%{y}: %{x} mujeres<extra></extra>')])
        fig.update_layout(barmode='relative')
        mx = max(1, mm_.max(), ff_.max())
        fig.update_xaxes(tickvals=[-mx, -mx / 2, 0, mx / 2, mx], ticktext=[C.fmt(mx), C.fmt(mx / 2), '0', C.fmt(mx / 2), C.fmt(mx)])
        grafico(M.estilo_fig(fig, 'Pirámide por grupo de edad y sexo', 330), f'piramide_{ev}')
    with c2:
        d = sel.det.fillna('Sin dato').value_counts()
        fig = go.Figure(go.Bar(y=d.index[::-1], x=d.values[::-1], orientation='h', text=d.values[::-1], textposition='outside',
                               marker_color=[C.mezclar('#ffffff', info['color'], max(.35, 1 - i * .15)) for i in range(len(d))][::-1]))
        grafico(M.estilo_fig(fig, info['det'], 330), f'detalle_{ev}')
    with c3:
        dm = sel.groupby('mun').size().reindex([m_['nombre'] for m_ in C.MUNS], fill_value=0)
        fig = go.Figure(go.Bar(x=dm.index, y=dm.values, text=dm.values, textposition='outside', marker_color=M.AZUL2))
        grafico(M.estilo_fig(fig, 'Casos por municipio', 330), f'municipios_{ev}')

    st.markdown('### Veredas y barrios con más casos')
    top = sel.groupby('u').size().sort_values(ascending=False).reset_index(name='Casos')
    top.insert(0, 'Vereda / barrio', top.u.map(LUG.nombre))
    top.insert(1, 'Municipio', top.u.map(LUG.mun_de_unidad))
    top.insert(2, 'Tipo', top.u.map(lambda u: LUG.unidades.get(u, {}).get('tipo', 'Sin ubicar')))
    top['% del total'] = (top.Casos / max(1, len(sel)) * 100).round(1)
    top = top.drop(columns='u')
    st.dataframe(top, width='stretch', hide_index=True, height=360,
                 column_config={'Casos': st.column_config.ProgressColumn('Casos', format='%d', min_value=0, max_value=int(top.Casos.max()) if len(top) else 1)})
    st.download_button('⬇ Descargar tabla (CSV)', top.to_csv(index=False, sep=';').encode('utf-8-sig'),
                       f'casos_{ev}_{anio or "todos"}_SE{s1}-{s2}.csv', 'text/csv')
    fuentes = sel.drop_duplicates('_clave')[['_clave', '_origen']].sort_values('_clave')
    reg = Almacen.leer_json('registro.json', {}).get('casos', {})
    st.markdown('<p class="nota">Fuente: SIVIGILA – Secretaría de Salud del Guaviare. ' + ' · '.join(
        f'{k.split("_")[1]}: {"base PNEET" if o == "base" else "cargue " + reg.get(k, {}).get("fecha", "")}' for k, o in fuentes.values) + '</p>',
                unsafe_allow_html=True)


# =============================================================== 2. ANÁLISIS ESPACIAL
FUENTES_EXTRA = {'vpos': {'nombre': 'Viviendas positivas (encuesta larvaria)', 'color': '#d26a1c'},
                 'feb': {'nombre': 'Pacientes con síntomas (encuesta)', 'color': '#7d3c98'}}


def filas_fuente(ev) -> pd.DataFrame:
    if ev == 'vpos':
        if not len(LARV):
            return pd.DataFrame(columns=['anio', 'sem', 'u', 'lat', 'lon'])
        P = LARV[[f'P{i}' for i in range(6)]].fillna(0).sum(axis=1)
        d = LARV[(P > 0) & (LARV.fecha != '')]
        return pd.DataFrame({'anio': d.fecha.str[:4].astype(int), 'sem': d.fecha.map(C.semana_de), 'u': d.u.fillna('X:|' + d.lugar),
                             'lat': d.lat, 'lon': d.lon})
    if ev == 'feb':
        if not len(FEB):
            return pd.DataFrame(columns=['anio', 'sem', 'u', 'lat', 'lon'])
        d = FEB[FEB.ini != '']
        return pd.DataFrame({'anio': d.ini.str[:4].astype(int), 'sem': d.ini.map(C.semana_de), 'u': d.u.fillna('X:|' + d.lugar),
                             'lat': d.lat, 'lon': d.lon})
    return CASOS[CASOS.ev == ev][['anio', 'sem', 'u', 'lat', 'lon']]


def puntos(ev, anio, s1, s2, aprox):
    d = filas_fuente(ev)
    d = d[d['sem'].between(s1, s2) & ((d.anio == anio) if anio else True)].copy()
    con = d.lat.notna() & d.lon.notna()
    out = d[con].assign(aprox=False)
    sin = d[~con]
    n_aprox = 0
    if aprox and len(sin):
        cen = LUG.centros()
        ll = sin.u.map(cen)
        ok = ll.notna()
        a = sin[ok].copy()
        a['lat'] = [p[0] for p in ll[ok]]
        a['lon'] = [p[1] for p in ll[ok]]
        a['aprox'] = True
        n_aprox = len(a)
        out = pd.concat([out, a], ignore_index=True)
        sin_c = int((~ok).sum())
    else:
        sin_c = len(sin)
    out['t'] = out.anio * 53 + out['sem']
    return out.reset_index(drop=True), sin_c, n_aprox


def nota_ubic(sin_c, n_aprox, aprox):
    p = []
    if sin_c:
        p.append(f'{C.fmt(sin_c)} casos sin coordenadas quedaron por fuera' + ('' if aprox else ' (active "Ubicar sin coordenadas" para ponerlos en el centro de su barrio o vereda)'))
    if n_aprox:
        p.append(f'{C.fmt(n_aprox)} casos ubicados de forma aproximada en el centro de su barrio o vereda')
    p.append('Las coordenadas de la base 2019–2026 ubican cada caso dentro de su barrio o vereda; no se ha confirmado que correspondan a la vivienda')
    st.markdown('<p class="nota">' + '. '.join(p) + '.</p>', unsafe_allow_html=True)


def foco(pts):
    """Encuadre: el municipio (o zona urbana) con más puntos si concentra al menos 40 %."""
    if not len(pts):
        return []
    g = pts.u.map(lambda u: 'urb' if str(u).startswith('B:') else LUG.mun_de_unidad(u))
    top = g.value_counts()
    sub = pts[g == top.index[0]] if top.iloc[0] >= .4 * len(pts) else pts
    return list(zip(sub.lat, sub.lon))


def pagina_analisis():
    tipos = {'buffer': '◎ Radio de acción', 'cluster': '⬡ Conglomerados', 'calor': '🔥 Mapa de calor',
             'tasa': '▦ Incidencia por barrio', 'persist': '▤ Persistencia', 'riesgo': '⚑ Estratificación de riesgo'}
    tipo = st.segmented_control('Análisis', list(tipos), format_func=tipos.get, default='buffer', key='a_tipo') or 'buffer'
    evs = [e for e in C.EV if (CASOS.ev == e).any()] + [e for e in FUENTES_EXTRA if (len(LARV) if e == 'vpos' else len(FEB))]
    nombre_ev = lambda e: (C.EV.get(e) or FUENTES_EXTRA[e])['nombre']
    color_ev = lambda e: (C.EV.get(e) or FUENTES_EXTRA[e])['color']

    if tipo in ('buffer', 'cluster', 'calor'):
        c = st.columns([1.3, .9, 1.5, 1.6, 1.1])
        ev = c[0].selectbox('Datos', evs, index=evs.index('dengue') if 'dengue' in evs else 0, format_func=nombre_ev, key='a_ev')
        an = sorted(filas_fuente(ev).anio.unique().tolist())
        anio = c[1].selectbox('Año', ['Todos'] + [str(a) for a in reversed(an)], index=1 if an else 0, key='a_an')
        anio = None if anio == 'Todos' else int(anio)
        s1, s2 = c[2].slider('Semanas', 1, 53, (1, 53), key='a_se')
        aprox = c[4].toggle('Ubicar sin coordenadas', value=False, help='Pone los casos sin coordenadas en el centro de su barrio o vereda', key='a_ap')
        pts, sin_c, n_aprox = puntos(ev, anio, s1, s2, aprox)
        col = color_ev(ev)
        sub = f'{anio or "Todos los años"} · SE {s1}–{s2}'
        if tipo == 'buffer':
            R = c[3].slider('Radio de acción (m)', 50, 2000, 200, 50, key='a_r')
            an_buffer(ev, pts, R, col, nombre_ev(ev), sub, anio)
        elif tipo == 'cluster':
            with c[3]:
                D = st.slider('Distancia máxima (m)', 50, 2000, 300, 50, key='a_d')
            c2 = st.columns([1, 1, 3])
            W = c2[0].slider('Ventana (semanas)', 1, 12, 4, key='a_w')
            MIN = c2[1].number_input('Mínimo de casos', 2, 50, 3, key='a_min')
            an_cluster(ev, pts, D, W, MIN, nombre_ev(ev), sub)
        else:
            rad = c[3].slider('Suavizado (píxeles)', 8, 50, 22, key='a_cal')
            an_calor(pts, rad, nombre_ev(ev), sub)
        nota_ubic(sin_c, n_aprox, aprox)
    elif tipo == 'tasa':
        c = st.columns([1, 1.6, 3])
        an = anios_ev('dengue')
        anio = c[0].selectbox('Año', ['Promedio anual'] + [str(a) for a in reversed(an)], index=1 if an else 0, key='a_tan')
        s1, s2 = c[1].slider('Semanas', 1, 53, (1, 53), key='a_tse')
        an_tasa(None if anio == 'Promedio anual' else int(anio), s1, s2)
    elif tipo == 'persist':
        evp = [e for e in C.EV if (CASOS.ev == e).any()]
        ev = st.selectbox('Evento', evp, index=evp.index('dengue') if 'dengue' in evp else 0, format_func=nombre_ev, key='a_pev')
        an_persist(ev)
    else:
        an_riesgo()


def an_buffer(ev, pts, R, col, nombre, sub, anio):
    st.markdown(f'### Radio de acción de {R} m alrededor de los casos de {nombre.lower()}')
    st.caption(sub)
    m = M.mapa_base(zoom=13)
    M.capas_ref(m, GEO, REF, encendidas=('muni', 'cab', 'bar'), excluir=())
    cmap, cres = st.columns([2.2, 1])
    if not len(pts):
        with cmap:
            m.fit_bounds(M.limites(GEO['municipios']))
            ver_mapa(m, 600, 'm_buf')
        cres.info('No hay casos con ubicación en este filtro.')
        return
    dibujar = len(pts) <= 4000
    gr = folium.FeatureGroup(name=f'Radio de {R} m')
    gp = folium.FeatureGroup(name='Casos')
    if dibujar:
        for p in pts.itertuples():
            folium.Circle((p.lat, p.lon), radius=R, color=col, weight=.6, opacity=.5, fill=True, fill_color=col, fill_opacity=.12, interactive=False).add_to(gr)
            folium.CircleMarker((p.lat, p.lon), radius=3, color='#102a43', weight=.6, fill=True, fill_color=col, fill_opacity=1,
                                tooltip=f'{LUG.nombre(p.u)} · {p.anio} SE {p.sem}{" (aproximado)" if p.aprox else ""}').add_to(gp)
    # cálculos en metros
    P = C.proyector(float(pts.lat.iloc[0]))
    xy = [P(a, b) for a, b in zip(pts.lat, pts.lon)]
    arr = np.array(xy)
    celda = max(10.0, R / 8)
    rc = math.ceil(R / celda)
    off = np.array([(i, j) for i in range(-rc, rc + 1) for j in range(-rc, rc + 1)])
    cx, cy = np.floor(arr[:, 0] / celda), np.floor(arr[:, 1] / celda)
    cub = set()
    for s in range(0, len(arr), 2000):
        X = (cx[s:s + 2000, None] + off[None, :, 0] + .5) * celda - arr[s:s + 2000, 0:1]
        Y = (cy[s:s + 2000, None] + off[None, :, 1] + .5) * celda - arr[s:s + 2000, 1:2]
        ok = X ** 2 + Y ** 2 <= R * R
        ii, jj = np.nonzero(ok)
        cub.update(zip((cx[s:s + 2000][ii] + off[jj, 0]).astype(int), (cy[s:s + 2000][ii] + off[jj, 1]).astype(int)))
    area = len(cub) * celda * celda / 1e6
    rej = C.Rejilla(xy, R)
    pob, nmz = 0.0, 0
    for la, lo, pp in GEO['manzanas']:
        if rej.dentro(*P(la, lo), R):
            pob += pp; nmz += 1
    juntos = sum(1 for i, (x, y) in enumerate(xy) if any(j != i and (xy[j][0] - x) ** 2 + (xy[j][1] - y) ** 2 <= R * R for j in rej.vecinos(x, y)))
    # ovitrampas dentro
    go_ = folium.FeatureGroup(name='Ovitrampas en el radio')
    ntr = nrev = npos = 0
    if len(OVI):
        o = OVI.dropna(subset=['lat', 'lon'])
        if anio:
            o = o[(o.fecha.str[:4] == str(anio)) | (o.fecha == '')]
        tr = {}
        for r in o.itertuples():
            if rej.dentro(*P(r.lat, r.lon), R):
                x = tr.setdefault(r.id, [0, 0, r.lat, r.lon])
                x[0] += 1; x[1] += r.pos
        ntr = len(tr); nrev = sum(x[0] for x in tr.values()); npos = sum(x[1] for x in tr.values())
        for i_, x in tr.items():
            ipo = x[1] / x[0] * 100
            folium.CircleMarker((x[2], x[3]), radius=5, color='#7d3c98', weight=2, fill=True, fill_color=C.col_ipo(ipo),
                                fill_opacity=1, tooltip=f'Ovitrampa {i_} · IPO {ipo:.0f} %').add_to(go_)
    gr.add_to(m); gp.add_to(m); go_.add_to(m)
    M.leyenda(m, nombre, puntos=[(col, 'Caso'), ('#7d3c98', 'Ovitrampa en el radio (relleno según IPO)')], lineas=[(M.AZUL, 'Límite municipal'), ('#3b76fb', 'Barrio')],
              poligonos=[(C.mezclar('#ffffff', col, .3), f'Radio de {R} m')])
    M.encuadrar(m, foco(pts), 0.004)
    with cmap:
        ver_mapa(m, 620, 'm_buf')
        if not dibujar:
            st.warning(f'Son {C.fmt(len(pts))} casos: el mapa no los dibuja todos. Filtre por año o semanas; los cálculos sí incluyen todos.')
    with cres:
        st.markdown(f'**Dentro del radio de {R} m**')
        a, b = st.columns(2)
        kpi(a, C.fmt(len(pts)), 'casos con ubicación', col)
        kpi(b, C.fmt(area, 2) + ' km²', 'área cubierta por los radios')
        a, b = st.columns(2)
        kpi(a, C.fmt(round(pob)), f'personas estimadas ({C.fmt(nmz)} manzanas DANE)')
        kpi(b, f'{juntos / len(pts) * 100:.0f} %', 'casos con otro caso dentro del radio', '#b23a48')
        kpi(st, C.fmt(ntr), 'ovitrampas dentro' + (f' · IPO {npos / nrev * 100:.0f} %' if nrev else ''), '#7d3c98')
        top = pts.u.value_counts().head(10)
        st.dataframe(pd.DataFrame({'Barrio / vereda': top.index.map(LUG.nombre), 'Casos': top.values}), hide_index=True, width='stretch')
        st.caption('La población se estima con los centroides de manzana DANE (zonas urbanas) que caen dentro de algún radio.')
        exp = pts.assign(lugar=pts.u.map(LUG.nombre), municipio=pts.u.map(LUG.mun_de_unidad))[['lugar', 'municipio', 'anio', 'sem', 'lat', 'lon', 'aprox']]
        st.download_button('⬇ Casos del análisis (CSV)', exp.to_csv(index=False, sep=';').encode('utf-8-sig'), f'radio_{ev}_{R}m.csv')


def an_cluster(ev, pts, D, W, MIN, nombre, sub):
    st.markdown(f'### Conglomerados de {nombre.lower()}: casos a menos de {D} m y {W} semanas entre sí')
    st.caption(sub)
    m = M.mapa_base(zoom=13)
    M.capas_ref(m, GEO, REF, encendidas=('muni', 'cab'), excluir=())
    cmap, cres = st.columns([2.2, 1])
    if not len(pts):
        with cmap:
            ver_mapa(m, 600, 'm_clu')
        cres.info('No hay casos con ubicación en este filtro.')
        return
    P = C.proyector(float(pts.lat.iloc[0]))
    xy = [P(a, b) for a, b in zip(pts.lat, pts.lon)]
    rej = C.Rejilla(xy, D)
    par = list(range(len(xy)))

    def f(i):
        while par[i] != i:
            par[i] = par[par[i]]
            i = par[i]
        return i

    t = pts.t.values
    for i, (x, y) in enumerate(xy):
        for j in rej.vecinos(x, y):
            if j <= i or abs(t[i] - t[j]) > W or (xy[j][0] - x) ** 2 + (xy[j][1] - y) ** 2 > D * D:
                continue
            par[f(i)] = f(j)
    grupos = {}
    for i in range(len(xy)):
        grupos.setdefault(f(i), []).append(i)
    lista = sorted([g for g in grupos.values() if len(g) >= MIN], key=len, reverse=True)
    en = {i for g in lista for i in g}
    tmax = int(t.max())
    gl = folium.FeatureGroup(name='Casos aislados')
    for i, p in enumerate(pts.itertuples()):
        if i not in en:
            folium.CircleMarker((p.lat, p.lon), radius=2.5, color='#8a9bb0', weight=0, fill=True, fill_opacity=.6, interactive=False).add_to(gl)
    gl.add_to(m)
    gc = folium.FeatureGroup(name='Conglomerados')
    filas = []
    sem_txt = lambda tt: f'{(tt - 1) // 53} SE {(tt - 1) % 53 + 1}'
    for k, g in enumerate(lista):
        col = M.PAL[k % len(M.PAL)]
        ps = pts.iloc[g]
        h = C.hull(list(zip(ps.lat, ps.lon)))
        if len(h) >= 3:
            folium.Polygon(h, color=col, weight=2, fill=True, fill_color=col, fill_opacity=.18, tooltip=f'Conglomerado {k + 1}: {len(g)} casos').add_to(gc)
        for p in ps.itertuples():
            folium.Circle((p.lat, p.lon), radius=D / 2, color=col, weight=.5, fill=True, fill_opacity=.1, interactive=False).add_to(gc)
            folium.CircleMarker((p.lat, p.lon), radius=3.5, color='#fff', weight=.8, fill=True, fill_color=col, fill_opacity=1,
                                tooltip=f'{LUG.nombre(p.u)} · {p.anio} SE {p.sem}').add_to(gc)
        t0, t1 = int(ps.t.min()), int(ps.t.max())
        lug = ps.u.value_counts().head(3).index.map(LUG.nombre)
        filas.append({'#': k + 1, 'Casos': len(g), 'Periodo': sem_txt(t0) + (f' a {sem_txt(t1)}' if t1 != t0 else ''),
                      'Dónde': ', '.join(lug), 'Estado': 'Activo' if tmax - t1 <= W else 'Cerrado'})
    gc.add_to(m)
    M.leyenda(m, 'Conglomerados', puntos=[('#8a9bb0', 'Caso aislado'), (M.PAL[0], 'Caso en conglomerado')], lineas=[(M.AZUL, 'Límite municipal')],
              poligonos=[(C.mezclar('#ffffff', M.PAL[0], .3), 'Área del conglomerado (un color por cada uno)')])
    M.encuadrar(m, foco(pts), 0.004)
    with cmap:
        ver_mapa(m, 620, 'm_clu')
    with cres:
        a, b = st.columns(2)
        kpi(a, C.fmt(len(lista)), f'conglomerados de {MIN} o más casos', '#b23a48')
        kpi(b, f'{len(en) / len(pts) * 100:.0f} %', 'de los casos están en un conglomerado')
        kpi(st, C.fmt(sum(1 for r in filas if r['Estado'] == 'Activo')), f'activos (con casos en las últimas {W} semanas del filtro)', '#d26a1c')
        df = pd.DataFrame(filas)
        if len(df):
            st.dataframe(df, hide_index=True, width='stretch', height=330)
            st.download_button('⬇ Conglomerados (CSV)', df.to_csv(index=False, sep=';').encode('utf-8-sig'), f'conglomerados_{ev}.csv')
        else:
            st.info('Ningún grupo alcanza el mínimo de casos.')
        st.caption(f'Dos casos quedan en el mismo conglomerado si están a menos de {D} m y a menos de {W} semanas; la relación se encadena entre casos.')


def an_calor(pts, rad, nombre, sub):
    st.markdown(f'### Densidad de casos de {nombre.lower()}')
    st.caption(sub)
    m = M.mapa_base(zoom=12)
    M.capas_ref(m, GEO, REF, encendidas=('muni', 'cab'), excluir=())
    if len(pts):
        HeatMap(list(zip(pts.lat, pts.lon)), radius=rad, blur=int(rad * .8), min_opacity=.25, name='Densidad').add_to(m)
        M.encuadrar(m, foco(pts), 0.01)
    M.leyenda(m, 'Densidad de casos', lineas=[(M.AZUL, 'Límite municipal')],
              poligonos=[('#2b83ba', 'Baja'), ('#ffffbf', 'Media'), ('#d7191c', 'Alta')])
    cmap, cres = st.columns([2.2, 1])
    with cmap:
        ver_mapa(m, 620, 'm_cal')
    with cres:
        st.markdown('**Zonas con más casos**')
        top = pts.u.value_counts().head(12)
        st.dataframe(pd.DataFrame({'Barrio / vereda': top.index.map(LUG.nombre), 'Municipio': top.index.map(LUG.mun_de_unidad), 'Casos': top.values}),
                     hide_index=True, width='stretch')
        st.caption(f'{C.fmt(len(pts))} casos en el mapa. El suavizado está en píxeles: al acercar el mapa la mancha se hace más precisa.')


def an_tasa(anio, s1, s2):
    d = CASOS[(CASOS.ev == 'dengue') & CASOS.u.str.startswith('B:') & CASOS['sem'].between(s1, s2) & ((CASOS.anio == anio) if anio else True)]
    c = d.groupby('u').size().to_dict()
    n_an = 1 if anio else max(1, len(anios_ev('dengue')))
    tasa = lambda p: None if not p.get('pob') else c.get(p['id'], 0) / p['pob'] * 1000 / n_an
    vals = sorted(v for f in GEO['barrios']['features'] if (v := tasa(f['properties'])) and v > 0)
    q = lambda p: vals[min(len(vals) - 1, int(p * len(vals)))] if vals else 0
    cts = [q(.25), q(.5), q(.75), vals[-1] if vals else 1]
    cols = ['#f4f7fb'] + [C.mezclar('#ffffff', '#d26a1c', t) for t in (.3, .55, .8, 1)]

    def color(v):
        if v is None:
            return '#e6ebf1'
        if v == 0:
            return cols[0]
        for i, ct in enumerate(cts):
            if v <= ct:
                return cols[i + 1]
        return cols[-1]

    st.markdown('### Incidencia de dengue por barrio, San José del Guaviare')
    st.caption(f'{anio or "Promedio anual de todos los años"} · SE {s1}–{s2}')
    m = M.mapa_base(zoom=14)
    M.coropleta(m, GEO['barrios'], lambda p: tasa(p), color,
                lambda p, v: f"<b>{p['nombre']}</b><br>Casos: {c.get(p['id'], 0)}<br>Población 2026: {C.fmt(p.get('pob'))}<br><b>Tasa: {C.fmt(v or 0, 1)} por 1.000 hab.</b>",
                'Incidencia por barrio')
    M.capas_ref(m, GEO, REF, encendidas=('muni',), excluir=('bar',))
    f1 = lambda v: C.fmt(v, 1)
    M.leyenda(m, 'Casos por 1.000 hab.', lineas=[(M.AZUL, 'Límite municipal')],
              poligonos=[(cols[0], '0')] + [(cols[i + 1], f'{f1(cts[i - 1]) if i else "0"}–{f1(cts[i])}') for i in range(4)])
    m.fit_bounds(M.limites(GEO['barrios']))
    cmap, cres = st.columns([2, 1.2])
    with cmap:
        ver_mapa(m, 620, 'm_tasa')
    with cres:
        ls = pd.DataFrame([{'Barrio': f['properties']['nombre'], 'Casos': c.get(f['properties']['id'], 0), 'Población': f['properties'].get('pob'),
                            'Tasa x 1.000': round(tasa(f['properties']), 2)} for f in GEO['barrios']['features'] if tasa(f['properties']) is not None])
        ls = ls.sort_values('Tasa x 1.000', ascending=False)
        st.dataframe(ls, hide_index=True, width='stretch', height=470)
        st.download_button('⬇ Tasa por barrio (CSV)', ls.to_csv(index=False, sep=';').encode('utf-8-sig'), 'incidencia_dengue_barrios.csv')
        st.caption('Población 2026 estimada con las viviendas de las manzanas DANE. Solo casos ubicados en barrios de San José.')


def an_persist(ev):
    info = C.EV[ev]
    an = anios_ev(ev)
    n = len(an)
    d = CASOS[(CASOS.ev == ev) & CASOS.u.str[:2].isin(['V:', 'B:'])]
    yrs = d.groupby('u').anio.apply(lambda s: sorted(set(s))).to_dict()
    cts = sorted(set([max(1, math.ceil(n * .25)), max(1, math.ceil(n * .5)), max(1, math.ceil(n * .75)), n]))
    cols = [C.mezclar('#ffffff', info['color'], t) for t in (.3, .55, .8, 1)][-len(cts):]

    def color(v):
        if not v:
            return '#f4f7fb'
        for i, ct in enumerate(cts):
            if v <= ct:
                return cols[i]
        return cols[-1]

    st.markdown(f'### Persistencia de {info["nombre"].lower()}: años con al menos un caso')
    st.caption(f'{an[0]}–{an[-1]} ({n} años con datos)' if an else '')
    m = M.mapa_base()
    tt = lambda p, v: f"<b>{p['nombre']}</b><br>Años con casos: <b>{v or 0} de {n}</b><br>{', '.join(map(str, yrs.get(p['id'], [])))}"
    M.coropleta(m, GEO['veredas'], lambda p: len(yrs.get(p['id'], [])), color, tt, 'Veredas')
    M.coropleta(m, GEO['barrios'], lambda p: len(yrs.get(p['id'], [])), color, tt, 'Barrios')
    M.capas_ref(m, GEO, REF, encendidas=('muni', 'cab'), excluir=('ver', 'bar'))
    prev, pol = 0, []
    for c_, ct in zip(cols, cts):
        pol.append((c_, f'{prev + 1}–{ct}' if ct > prev + 1 else str(ct)))
        prev = ct
    M.leyenda(m, 'Años con casos', puntos=[(M.AZUL, 'Cabecera municipal')], lineas=[(M.AZUL, 'Límite municipal')], poligonos=pol + [('#f4f7fb', 'Ninguno')])
    m.fit_bounds(M.limites(GEO['municipios']))
    cmap, cres = st.columns([2, 1.2])
    with cmap:
        ver_mapa(m, 620, 'm_per')
    with cres:
        dist = pd.Series([len(v) for v in yrs.values()]).value_counts().sort_index(ascending=False)
        fig = go.Figure(go.Bar(x=[f'{k} de {n}' for k in dist.index], y=dist.values, text=dist.values, textposition='outside', marker_color=info['color']))
        grafico(M.estilo_fig(fig, 'Veredas y barrios según años con casos', 300), f'persistencia_{ev}')
        ult = an[-3:]
        cron = sorted(LUG.nombre(u) for u, s in yrs.items() if all(y in s for y in ult))
        st.markdown(f'**{len(cron)}** con casos en cada uno de los últimos 3 años con datos ({", ".join(map(str, ult))}):')
        st.markdown('<p class="nota">' + ', '.join(cron) + '</p>', unsafe_allow_html=True)
        if ev == 'malaria':
            st.caption('La base de malaria no trae 2025: ese año no cuenta en la persistencia.')


def an_riesgo():
    CL = {'Bajo': '#2f7d4f', 'Medio': '#e3c84a', 'Alto': '#d26a1c', 'Muy alto': '#b23a48'}
    an = anios_ev('dengue')
    anio = an[-1] if an else None
    st.markdown('### Estratificación de riesgo para Aedes por barrio, San José del Guaviare')
    st.caption(f'Puntaje de 4 componentes (0–3 c/u) · puntos: casos de dengue {anio}')
    m = M.mapa_base(zoom=14)
    tt = lambda p, v: (f"<b>{p['nombre']}</b><br>Estrato: <b>{p.get('estrato') or 's/d'}</b> (puntaje {p.get('score', 's/d')} de 12)<br>"
                       f"Entomológico {p.get('s_ento', '–')} · Persistencia {p.get('s_pers', '–')} · Incidencia {p.get('s_ia', '–')} · Socioeconómico {p.get('s_socio', '–')}<br>"
                       f"IPO {p.get('ipo', '–')} % · Incidencia acumulada 2023–2025: {p.get('ia', '–')}")
    M.coropleta(m, GEO['barrios'], lambda p: p.get('estrato'), lambda v: CL.get(v, '#e6ebf1'), tt, 'Estrato de riesgo', opac=.85)
    d = CASOS[(CASOS.ev == 'dengue') & (CASOS.anio == anio) & CASOS.u.str.startswith('B:')] if anio else CASOS.iloc[:0]
    g = folium.FeatureGroup(name=f'Casos de dengue {anio}')
    for r in d.dropna(subset=['lat', 'lon']).itertuples():
        folium.CircleMarker((r.lat, r.lon), radius=2.5, color='#102a43', weight=.5, fill=True, fill_opacity=.7, interactive=False).add_to(g)
    g.add_to(m)
    M.capas_ref(m, GEO, REF, encendidas=('muni',), excluir=('bar',))
    M.leyenda(m, 'Estrato de riesgo', puntos=[('#102a43', f'Caso de dengue {anio}')], lineas=[(M.AZUL, 'Límite municipal')], poligonos=list((c, k) for k, c in CL.items()))
    m.fit_bounds(M.limites(GEO['barrios']))
    cmap, cres = st.columns([2, 1.2])
    with cmap:
        ver_mapa(m, 620, 'm_rie')
    with cres:
        cb = d.groupby('u').size().to_dict()
        filas = {}
        for f in GEO['barrios']['features']:
            p = f['properties']
            e = p.get('estrato') or 'Sin dato'
            x = filas.setdefault(e, {'Estrato': e, 'Barrios': 0, 'Población': 0, f'Casos {anio}': 0})
            x['Barrios'] += 1
            x['Población'] += p.get('pob') or 0
            x[f'Casos {anio}'] += cb.get(p['id'], 0)
        df = pd.DataFrame([filas[k] for k in ['Muy alto', 'Alto', 'Medio', 'Bajo', 'Sin dato'] if k in filas])
        st.dataframe(df, hide_index=True, width='stretch')
        fig = go.Figure(go.Bar(x=df.Estrato, y=df['Población'], marker_color=[CL.get(e, '#c9d3de') for e in df.Estrato], text=df['Población'], textposition='outside'))
        grafico(M.estilo_fig(fig, 'Población por estrato de riesgo', 300), 'riesgo_poblacion')
        st.caption('La estratificación es la de la base inicial (2023–2025); no cambia con los cargues.')


# =============================================================== 3. AEDES · OVITRAMPAS
def pagina_ovitrampas():
    if not len(OVI):
        st.warning('Todavía no hay revisiones de ovitrampas cargadas.')
        return
    o = OVI.copy()
    meses = sorted(o.loc[o.fecha != '', 'fecha'].str[:7].unique())
    c = st.columns([2.5, 1.2])
    d1, d2 = c[0].select_slider('Periodo (mes)', options=meses, value=(meses[0], meses[-1]), key='o_per') if len(meses) > 1 else (meses[0], meses[0])
    muns = sorted(m_ for m_ in o.mun.dropna().unique() if m_)
    mun = c[1].selectbox('Municipio', ['Todos'] + muns, key='o_mun')
    coords = o.dropna(subset=['lat', 'lon']).groupby('id').last()[['lat', 'lon', 'barrio', 'tipo', 'mun']]
    r = o[(o.fecha.str[:7] >= d1) & (o.fecha.str[:7] <= d2) & ((o.mun == mun) if mun != 'Todos' else True)]
    n, pos, hv = len(r), int(r.pos.sum()), float(r.huevos.sum())
    ipo = pos / n * 100 if n else 0
    k = st.columns(4)
    kpi(k[0], C.fmt(ipo, 1) + ' %', 'Índice de positividad de ovitrampas (IPO)', C.col_ipo(ipo))
    kpi(k[1], C.fmt(n), f'Revisiones ({C.fmt(pos)} positivas)')
    kpi(k[2], C.fmt(r.id.nunique()), 'Trampas revisadas')
    kpi(k[3], C.fmt(hv / pos) if pos else '0', 'Huevos por trampa positiva (IDH)', '#7d3c98')
    pt = r.groupby('id').agg(n=('pos', 'size'), pos=('pos', 'sum'), huevos=('huevos', 'sum')).join(coords, how='inner')
    m = M.mapa_base(zoom=14)
    M.capas_ref(m, GEO, REF, encendidas=('muni', 'bar'), excluir=('ver',))
    g = folium.FeatureGroup(name='Ovitrampas')
    for i_, p in pt.iterrows():
        v = p.pos / p.n * 100
        folium.CircleMarker((p.lat, p.lon), radius=6, color='#102a43', weight=.8, fill=True, fill_color=C.col_ipo(v), fill_opacity=.95,
                            popup=folium.Popup(f'<b>Ovitrampa {i_}</b><br>{p.barrio} · {p.mun}<br>{p.tipo}<br>Revisiones: {p.n} · positivas: {int(p.pos)}<br>'
                                               f'<b>IPO {v:.1f} %</b> · huevos: {C.fmt(p.huevos)}', max_width=260)).add_to(g)
    g.add_to(m)
    M.leyenda(m, 'IPO de la trampa', puntos=[(c_, t) for t, _, c_ in C.CLASES_IPO], lineas=[(M.AZUL, 'Límite municipal'), ('#3b76fb', 'Barrio')])
    if len(pt):
        gm = pt.groupby('mun').size()
        sub = pt if mun != 'Todos' or not len(gm) else pt[pt.mun == gm.idxmax()]
        M.encuadrar(m, list(zip(sub.lat, sub.lon)), 0.003)
    c1, c2 = st.columns([1.7, 1])
    with c1:
        ver_mapa(m, 560, 'm_ovi')
    with c2:
        b = r.groupby(r.barrio.replace('', 'Sin barrio')).agg(Trampas=('id', 'nunique'), Revisiones=('pos', 'size'), Positivas=('pos', 'sum'), Huevos=('huevos', 'sum'))
        b['IPO %'] = (b.Positivas / b.Revisiones * 100).round(1)
        b = b.sort_values('IPO %', ascending=False).reset_index().rename(columns={'barrio': 'Barrio'})
        st.dataframe(b, hide_index=True, width='stretch', height=520,
                     column_config={'IPO %': st.column_config.ProgressColumn('IPO %', format='%.1f', min_value=0, max_value=100)})
    mm = r[r.fecha != ''].groupby(r.fecha.str[:7]).agg(n=('pos', 'size'), pos=('pos', 'sum'), h=('huevos', 'sum'))
    fig = go.Figure([go.Bar(x=mm.index, y=mm.h, name='Huevos', marker_color=C.mezclar('#ffffff', '#d26a1c', .55), yaxis='y2'),
                     go.Scatter(x=mm.index, y=(mm.pos / mm.n * 100).round(1), name='IPO %', mode='lines+markers', line=dict(color='#b23a48', width=2.4))])
    fig.update_layout(yaxis=dict(title='IPO %', range=[0, 100]), yaxis2=dict(title='Huevos', overlaying='y', side='right', showgrid=False))
    c1, c2 = st.columns([1.6, 1])
    with c1:
        grafico(M.estilo_fig(fig, 'IPO y huevos por mes', 340), 'ovitrampas_mensual')
    with c2:
        cl = pt.assign(ipo=pt.pos / pt.n * 100)
        cuenta = [int(((cl.ipo <= mx) & (cl.ipo > (C.CLASES_IPO[i - 1][1] if i else -1))).sum()) for i, (_, mx, _) in enumerate(C.CLASES_IPO)]
        fig = go.Figure(go.Bar(x=[t for t, _, _ in C.CLASES_IPO], y=cuenta, text=cuenta, textposition='outside', marker_color=[c_ for _, _, c_ in C.CLASES_IPO]))
        grafico(M.estilo_fig(fig, 'Trampas por clase de IPO', 340), 'ovitrampas_clases')
    st.download_button('⬇ IPO por barrio (CSV)', b.to_csv(index=False, sep=';').encode('utf-8-sig'), 'ipo_barrios.csv')


# =============================================================== 4. ENCUESTA LARVARIA
def pagina_encuesta():
    if not len(LARV):
        st.warning('Todavía no hay encuestas larvarias cargadas.')
        return
    L_ = LARV[LARV.fecha != '']
    meses = sorted(L_.fecha.str[:7].unique())
    ini = meses[max(0, len(meses) - 12)]
    c = st.columns([2.5, 1.2])
    d1, d2 = c[0].select_slider('Periodo (mes)', options=meses, value=(ini, meses[-1]), key='e_per') if len(meses) > 1 else (meses[0], meses[0])
    muns = sorted(x for x in L_.mun_n.unique() if x)
    mun = c[1].selectbox('Municipio', ['Todos'] + muns, key='e_mun')
    r = L_[(L_.fecha.str[:7] >= d1) & (L_.fecha.str[:7] <= d2) & ((L_.mun_n == mun) if mun != 'Todos' else True)]
    fb = FEB[(FEB.ini.str[:7] >= d1) & (FEB.ini.str[:7] <= d2) & ((FEB.mun_n == mun) if mun != 'Todos' else True)] if len(FEB) else FEB
    X = C.indices_larv(r)
    cb = C.clase_breteau(X['ib'])
    k = st.columns(6)
    kpi(k[0], C.fmt(X['n']), f'Viviendas visitadas ({C.fmt(X["cerradas"])} cerradas)')
    kpi(k[1], C.fmt(X['ib'], 1), 'Índice de Breteau (recipientes positivos por 100 viviendas)', M.AZUL if cb is None else C.CLASES_BRETEAU[cb][1])
    kpi(k[2], C.fmt(X['iv'], 1) + ' %', f'Índice de vivienda ({C.fmt(X["pos"])} positivas)')
    kpi(k[3], C.fmt(X['ir'], 1) + ('' if X['ir'] is None else ' %'), f'Índice de recipientes ({C.fmt(X["nI"])} con formulario completo)')
    kpi(k[4], C.fmt(X['pup']), 'Pupas encontradas' + (f' · {C.fmt(X["ppp"], 2)} por habitante' if X['ppp'] is not None else ''), '#b23a48')
    kpi(k[5], C.fmt(len(fb)), 'Pacientes con síntomas reportados', '#7d3c98')

    pb = {u: g for u, g in r[r.u.fillna('').str.startswith('B:')].groupby('u')}
    ixb = {u: C.indices_larv(g) for u, g in pb.items()}
    cl_col = lambda v: '#eef2f7' if v is None else C.CLASES_BRETEAU[C.clase_breteau(v)][1]
    m = M.mapa_base(zoom=14)
    M.coropleta(m, GEO['barrios'], lambda p: ixb[p['id']]['ib'] if p['id'] in ixb and ixb[p['id']]['n'] >= 10 else None, cl_col,
                lambda p, v: (f"<b>{p['nombre']}</b><br>Visitas: {ixb[p['id']]['n']} · positivas: {ixb[p['id']]['pos']}<br>Breteau: <b>{C.fmt(ixb[p['id']]['ib'], 1)}</b> · IV {C.fmt(ixb[p['id']]['iv'], 1)} %<br>Pupas: {C.fmt(ixb[p['id']]['pup'])}"
                              if p['id'] in ixb else f"<b>{p['nombre']}</b><br>Sin visitas en el periodo"), 'Índice de Breteau por barrio', opac=.55)
    M.capas_ref(m, GEO, REF, encendidas=('muni', 'cab'), excluir=('bar',))
    gv = folium.FeatureGroup(name='Viviendas visitadas')
    P = r[[f'P{i}' for i in range(6)]].fillna(0).sum(axis=1)
    rr = r.assign(npos=P).dropna(subset=['lat', 'lon'])
    if len(rr) > 6000:
        rr = rr.sample(6000, random_state=1)
    for v in rr.itertuples():
        colr = ('#b23a48' if v.npos > 0 else '#2f7d4f') if v.estado in (1,) or pd.isna(v.estado) else '#8a9bb0'
        folium.CircleMarker((v.lat, v.lon), radius=3.5, color='#102a43', weight=.4, fill=True, fill_color=colr, fill_opacity=.95,
                            tooltip=f'{v.lugar} · {v.fecha}' + (f' · {int(v.npos)} recipientes positivos' if v.npos else '')).add_to(gv)
    gv.add_to(m)
    gf = folium.FeatureGroup(name='Pacientes con síntomas')
    cen = LUG.centros()
    for f_ in fb.itertuples() if len(fb) else []:
        p = (f_.lat, f_.lon) if pd.notna(f_.lat) else cen.get(f_.u)
        if p:
            folium.CircleMarker(p, radius=6, color='#ffffff', weight=2, fill=True, fill_color='#7d3c98',
                                fill_opacity=1, tooltip=f'Paciente con síntomas · inicio {f_.ini}').add_to(gf)
    gf.add_to(m)
    M.leyenda(m, 'Encuesta larvaria',
              puntos=[('#b23a48', 'Vivienda con recipientes positivos'), ('#2f7d4f', 'Inspeccionada sin positivos'), ('#8a9bb0', 'Cerrada o no inspeccionada'),
                      ('#7d3c98', 'Paciente con síntomas')],
              lineas=[(M.AZUL, 'Límite municipal')],
              poligonos=[(c_, 'Breteau ' + t) for t, c_ in C.CLASES_BRETEAU] + [('#eef2f7', 'Menos de 10 visitas')])
    m.fit_bounds(M.limites(GEO['barrios']))
    c1, c2 = st.columns([1.7, 1])
    with c1:
        ver_mapa(m, 580, 'm_larv')
    with c2:
        pl = {}
        for (u, lug), g in r.assign(_u=r.u.fillna('')).groupby(['_u', 'lugar']):
            nm = LUG.nombre(u) if u else (lug or 'Sin dato')
            pl.setdefault(nm, []).append(g)
        tl = []
        for nm, gs in pl.items():
            x = C.indices_larv(pd.concat(gs))
            if x['n'] >= 5:
                tl.append({'Barrio / vereda': nm, 'Visitas': x['n'], 'Positivas': x['pos'], 'IV %': round(x['iv'] or 0, 1),
                           'Breteau': round(x['ib'] or 0, 1), 'Pupas': int(x['pup'])})
        tdf = pd.DataFrame(tl).sort_values('Breteau', ascending=False) if tl else pd.DataFrame()
        st.dataframe(tdf, hide_index=True, width='stretch', height=540)
    c1, c2 = st.columns([1.6, 1])
    with c1:
        mm = {k_: C.indices_larv(g) for k_, g in r.groupby(r.fecha.str[:7])}
        ks = sorted(mm)
        fig = go.Figure([go.Bar(x=ks, y=[mm[x]['n'] for x in ks], name='Visitas', marker_color=C.mezclar('#ffffff', M.AZUL2, .35), yaxis='y2'),
                         go.Scatter(x=ks, y=[None if mm[x]['ib'] is None else round(mm[x]['ib'], 1) for x in ks], name='Índice de Breteau', mode='lines+markers', line=dict(color='#b23a48', width=2.4)),
                         go.Scatter(x=ks, y=[None if mm[x]['iv'] is None else round(mm[x]['iv'], 1) for x in ks], name='Índice de vivienda %', mode='lines+markers', line=dict(color='#d26a1c', width=2))])
        fig.update_layout(yaxis2=dict(title='Visitas', overlaying='y', side='right', showgrid=False))
        grafico(M.estilo_fig(fig, 'Índices por mes', 340), 'indices_larvarios_mes')
    with c2:
        pt = [float(r[f'P{i}'].fillna(0).sum()) for i in range(6)]
        pu = [float(r[f'U{i}'].fillna(0).sum()) for i in range(6)]
        nombres = [t['n'] for t in C.TIPOS_R]
        fig = go.Figure([go.Bar(y=nombres, x=pt, name='Recipientes positivos', orientation='h', marker_color='#d26a1c'),
                         go.Bar(y=nombres, x=pu, name='Pupas', orientation='h', marker_color='#b23a48')])
        grafico(M.estilo_fig(fig, 'Tipo de recipiente', 340), 'tipos_recipiente')
    sin_c = int(r.lat.isna().sum())
    st.markdown(f'<p class="nota">{C.fmt(sin_c) + " visitas sin coordenadas no aparecen como punto; cuentan en el índice de su barrio. " if sin_c else ""}'
                'Las visitas que llegaron sin respuestas del formulario se cuentan como inspeccionadas y sus recipientes positivos salen de las ramas, '
                'así que el índice de vivienda y el de Breteau son aproximados. Umbrales de Breteau de referencia OPS/OMS.</p>', unsafe_allow_html=True)
    if len(tdf):
        st.download_button('⬇ Índices por barrio/vereda (CSV)', tdf.to_csv(index=False, sep=';').encode('utf-8-sig'), 'indices_larvarios.csv')


# =============================================================== 5. CARGAR DATOS
@st.cache_data(show_spinner='Leyendo el archivo…', max_entries=6)
def leer_subido(nombre, datos_):
    return C.leer_tabla(nombre, datos_)


def selector_columnas(df, campos, etiquetas, auto, prefijo, obligatorios):
    cols = ['— no viene —'] + list(df.columns)
    m = {}
    with st.expander('Revisar a qué columna corresponde cada dato', expanded=bool([c for c in obligatorios if c not in auto])):
        cc = st.columns(3)
        for i, c in enumerate(campos):
            v = cc[i % 3].selectbox(etiquetas[c] + (' *' if c in obligatorios else ''), cols,
                                    index=cols.index(auto[c]) if c in auto else 0, key=prefijo + c)
            if v != '— no viene —':
                m[c] = v
    return m


def guardar_lote(tipo, partes: dict, archivo):
    barra = st.progress(0.0, 'Guardando…')
    for i, (k, df) in enumerate(partes.items()):
        barra.progress(i / len(partes), f'Guardando {k}…')
        partes[k] = df.drop(columns=[c for c in df.columns if c.startswith('_')], errors='ignore')
    barra.progress(.5, 'Guardando (un solo envío)…')
    almacen.guardar_lote(tipo, partes, archivo)
    barra.progress(1.0, 'Listo')
    st.cache_data.clear()


def pagina_cargar():
    clave = secreto('CLAVE_CARGUE')
    if not clave:
        st.error('Falta configurar la clave de cargue (CLAVE_CARGUE) en los secretos de la app. Vea el README.')
        return
    if not st.session_state.get('cargue_ok'):
        st.markdown('### Acceso para cargar datos')
        c = st.text_input('Clave de cargue', type='password', key='clave_cargue')
        if c and hmac.compare_digest(c, str(clave)):
            st.session_state.cargue_ok = True
            st.rerun()
        elif c:
            st.error('Clave incorrecta.')
        return
    st.caption(almacen.probar_github())
    t1, t2, t3, t4, t5 = st.tabs(['SIVIGILA (casos)', 'Ovitrampas', 'Encuesta larvaria (Epicollect5)', 'Datos en la base', f'Sin ubicar'])
    with t1:
        cargar_sivigila()
    with t2:
        cargar_ovi()
    with t3:
        cargar_ec5()
    with t4:
        datos_en_base()
    with t5:
        sin_ubicar()
    if st.button('Cerrar sesión de cargue'):
        st.session_state.cargue_ok = False
        st.rerun()


def cargar_sivigila():
    st.markdown('Suba la exportación de SIVIGILA (Excel .xls/.xlsx o CSV). Cada **evento y año** del archivo reemplaza lo que haya en la base para ese evento y año. '
                'Se excluyen los descartados (ajuste 6 o D) y los casos procedentes de otros departamentos.')
    f = st.file_uploader('Archivo de SIVIGILA', type=['xls', 'xlsx', 'csv', 'txt'], key='up_s')
    if not f:
        return
    try:
        df = leer_subido(f.name, f.getvalue())
    except Exception as e:
        st.error(f'No se pudo leer el archivo: {e}')
        return
    st.caption(f'{C.fmt(len(df))} filas, {len(df.columns)} columnas.')
    auto = C.mapear_cols(df, C.CAMPOS_SIVIGILA)
    m = selector_columnas(df, C.CAMPOS_SIVIGILA, C.ETQ_SIVIGILA, auto, 'cs_', ['anio', 'semana', 'municipio'])
    forz = st.selectbox('Si el archivo no trae columna de evento, todo es de:', ['— usar la columna de evento —'] + list(C.EV),
                        format_func=lambda e: C.EV[e]['nombre'] if e in C.EV else e)
    forz = forz if forz in C.EV else None
    faltan = [C.ETQ_SIVIGILA[c] for c in ('anio', 'semana', 'municipio') if c not in m]
    if 'evento' not in m and not forz:
        faltan.append('Evento')
    if 'lugar' not in m and 'barrio' not in m:
        faltan.append('Vereda o barrio')
    if faltan:
        st.error('Falta indicar la columna de: ' + ', '.join(faltan))
        return
    proc, desc = C.procesar_sivigila(df, m, LUG, forz)
    if not len(proc):
        st.error('Ninguna fila es de malaria, dengue, leishmaniasis, chikunguña o zika con año y semana válidos.')
        return
    proc['k'] = proc.ev + '_' + proc.anio.astype(str)
    hoy = CASOS.groupby('_clave').size() if len(CASOS) else pd.Series(dtype=int)
    orig = CASOS.groupby('_clave')['_origen'].first() if len(CASOS) else pd.Series(dtype=str)
    res = proc.groupby('k').agg(Casos=('u', 'size'), Sin_ubicar=('u', lambda s: int(s.str.startswith('X:').sum()))).reset_index()
    res.insert(0, 'Reemplazar', True)
    res['Evento y año'] = res.k.map(lambda k: f'{C.EV[k.split("_")[0]]["nombre"]} {k.split("_")[1]}')
    res['Hoy en la base'] = res.k.map(lambda k: f'{C.fmt(hoy[k])} ({"base PNEET" if orig[k] == "base" else "cargue"})' if k in hoy else '—')
    sd_base = CASOS.groupby('_clave').det.apply(lambda s: (s == 'Sin dato').mean()) if len(CASOS) else pd.Series(dtype=float)
    sd_new = proc.groupby('k').det.apply(lambda s: (s == 'Sin dato').mean())
    res['Aviso'] = res.k.map(lambda k: 'El archivo no trae la especie y la base sí' if k.startswith('malaria') and sd_new.get(k, 0) > .5 and sd_base.get(k, 1) < .5 else '')
    ed = st.data_editor(res[['Reemplazar', 'Evento y año', 'Casos', 'Sin_ubicar', 'Hoy en la base', 'Aviso', 'k']], hide_index=True, width='stretch',
                        disabled=['Evento y año', 'Casos', 'Sin_ubicar', 'Hoy en la base', 'Aviso', 'k'], column_config={'k': None, 'Sin_ubicar': 'Sin ubicar'}, key='ed_s')
    n, nsin = len(proc), int(proc.u.str.startswith('X:').sum())
    st.markdown(f'<p class="nota">{C.fmt(n - nsin)} de {C.fmt(n)} casos quedaron ubicados en vereda, barrio o cabecera ({(n - nsin) / n * 100:.0f} %). '
                f'Descartados por ajuste: {C.fmt(desc["descartados"])}. De otro departamento (excluidos): {C.fmt(desc["otro_dpto"])}. '
                f'Filas de otros eventos: {C.fmt(desc["sin_evento"])}. Sin año o semana: {C.fmt(desc["sin_anio"])}.</p>', unsafe_allow_html=True)
    top = proc[proc.u.str.startswith('X:')].u.value_counts().head(8)
    if len(top):
        st.markdown('<p class="nota">Textos sin ubicar más frecuentes (asígnelos después en <b>Sin ubicar</b>): ' +
                    ', '.join(f'{u.split("|")[1]} – {LUG.mun_de_unidad(u) or "sin municipio"} ({c})' for u, c in top.items()) + '</p>', unsafe_allow_html=True)
    if st.button('Guardar en la base', type='primary', key='sv_s'):
        ks = ed[ed.Reemplazar].k.tolist()
        if not ks:
            st.warning('Marque al menos un evento y año.')
            return
        try:
            guardar_lote('casos', {k: proc[proc.k == k].drop(columns='k') for k in ks}, f.name)
            st.success(f'✓ Guardados {C.fmt(int(proc.k.isin(ks).sum()))} casos.')
        except Exception as e:
            st.error(f'No se pudo guardar: {e}')


def cargar_ovi():
    st.markdown('Suba la base de revisiones de ovitrampas (una fila por revisión). Cada **mes** del archivo reemplaza el mismo mes en la base.')
    f = st.file_uploader('Archivo de ovitrampas', type=['xls', 'xlsx', 'csv', 'txt'], key='up_o')
    if not f:
        return
    try:
        df = leer_subido(f.name, f.getvalue())
    except Exception as e:
        st.error(f'No se pudo leer el archivo: {e}')
        return
    auto = C.mapear_cols(df, C.CAMPOS_OVI)
    m = selector_columnas(df, C.CAMPOS_OVI, C.ETQ_OVI, auto, 'co_', ['id', 'fecha'])
    if 'id' not in m or 'fecha' not in m:
        st.error('Indique al menos la columna del código de la trampa y la fecha.')
        return
    proc, sin_id = C.procesar_ovi(df, m)
    proc['k'] = proc.fecha.str[:7].str.replace('-', '').replace('', 'sinfecha')
    res = proc.groupby('k').agg(Revisiones=('id', 'size'), Positivas=('pos', 'sum')).reset_index()
    res['Mes'] = res.k.map(lambda k: 'Sin fecha' if k == 'sinfecha' else f'{k[:4]}-{k[4:]}')
    st.dataframe(res[['Mes', 'Revisiones', 'Positivas']], hide_index=True, width='stretch')
    sinc = int((proc.lat.isna() | proc.lon.isna()).sum())
    st.markdown(f'<p class="nota">{C.fmt(sin_id) + " filas sin código de trampa se ignoraron. " if sin_id else ""}'
                f'{C.fmt(sinc) + " revisiones sin coordenadas: se ubican con la última posición conocida de la trampa." if sinc else ""}</p>', unsafe_allow_html=True)
    if st.button('Guardar en la base', type='primary', key='sv_o'):
        try:
            guardar_lote('ovi', {k: g.drop(columns='k') for k, g in proc.groupby('k')}, f.name)
            st.success(f'✓ Guardadas {C.fmt(len(proc))} revisiones.')
        except Exception as e:
            st.error(f'No se pudo guardar: {e}')


def cargar_ec5():
    st.markdown('Suba **todos** los CSV que exporta Epicollect5 del proyecto de encuesta larvaria: el formulario principal (form-1) y las ramas '
                '(recipientes positivos y pacientes con síntomas). **No abra los CSV en Excel antes de cargarlos**: Excel daña las coordenadas y '
                'borra respuestas. De los pacientes solo se guardan sexo, edad, fecha de inicio y síntomas.')
    fs = st.file_uploader('Archivos de Epicollect5', type=['csv', 'txt'], accept_multiple_files=True, key='up_e')
    if not fs:
        return
    arch = []
    for f in fs:
        filas = C.filas_texto(f.getvalue())
        arch.append({'nombre': f.name, 'filas': filas, 'c': C.clasificar_ec5(filas[0]) if filas else None})
    for a in arch:
        c = a['c']
        desc = 'no reconocido' if not c else 'encuesta principal' if c['tipo'] == 'form' else 'pacientes con síntomas' if c['tipo'] == 'pac' else 'recipientes positivos · ' + C.TIPOS_R[c['idx']]['n']
        st.markdown(f'- {a["nombre"]}: **{desc}** ({C.fmt(max(0, len(a["filas"]) - 1))} filas)')
    p = C.procesar_ec5(arch)
    if 'error' in p:
        st.error(p['error'])
        return
    s = p['st']
    lv = p['larv']
    meses = sorted(lv.fecha.str[:7].unique())
    st.markdown(f'**{C.fmt(s["visitas"])}** visitas entre {meses[0]} y {meses[-1]}. Con el formulario completo: {C.fmt(s["completas"])}. '
                f'Solo con código, fecha y barrio: {C.fmt(s["sin_datos"])}. Con coordenadas: {C.fmt(s["coords"])}. Pacientes con síntomas: {C.fmt(s["febriles"])}.')
    faltan = [t['n'] for i, t in enumerate(C.TIPOS_R) if not any(a['c'] and a['c']['tipo'] == 'rama' and a['c']['idx'] == i for a in arch)]
    if faltan:
        st.info('No se cargó la rama de: ' + ', '.join(faltan))
    if s['sin_datos'] > s['completas']:
        st.warning('La mayoría de las visitas llegaron sin sus respuestas. Suele pasar cuando el CSV se abre y se guarda en Excel. '
                   'Exporte de nuevo desde Epicollect5 y cárguelo sin abrirlo.')
    st.caption(f'Se reemplazarán {len(meses)} meses de encuesta.')
    if st.button('Guardar en la base', type='primary', key='sv_e'):
        nombre = ', '.join(a['nombre'] for a in arch)
        try:
            lv['k'] = lv.fecha.str[:7].str.replace('-', '').replace('', '000000')
            guardar_lote('larv', {k: g.drop(columns='k') for k, g in lv.groupby('k')}, nombre)
            fb = p['feb']
            if len(fb):
                fb['k'] = fb.ini.str[:7].str.replace('-', '')
                guardar_lote('feb', {k: g.drop(columns='k') for k, g in fb.groupby('k')}, nombre)
            st.success(f'✓ Guardadas {C.fmt(len(lv))} visitas y {C.fmt(len(fb))} pacientes.')
        except Exception as e:
            st.error(f'No se pudo guardar: {e}')


def datos_en_base():
    reg = Almacen.leer_json('registro.json', {})
    nombres = {'casos': 'Casos', 'ovi': 'Ovitrampas', 'larv': 'Encuesta larvaria', 'feb': 'Pacientes con síntomas'}
    filas = []
    for t in nombres:
        for k, info in Almacen.claves(t).items():
            r = reg.get(t, {}).get(k, {})
            if t == 'casos':
                desc = f'{C.EV.get(k.split("_")[0], {"nombre": k})["nombre"]} {k.split("_")[1]}'
            else:
                desc = f'{nombres[t]} {"sin fecha" if not k[:1].isdigit() else k[:4] + "-" + k[4:]}'
            base_existe = (RAIZ / 'base' / t / f'{k}.csv.gz').exists()
            filas.append({'Quitar cargue': False, 'Datos': desc, 'Origen': 'Base 2019–2026' if info['origen'] == 'base' else 'Cargue',
                          'Registros': r.get('n'), 'Archivo': r.get('archivo', '—'), 'Fecha': r.get('fecha', '—'),
                          'Al quitar': ('vuelve a la base' if base_existe else 'se elimina') if info['origen'] == 'cargue' else '', '_t': t, '_k': k})
    df = pd.DataFrame(filas)
    ed = st.data_editor(df, hide_index=True, width='stretch', height=480, column_config={'_t': None, '_k': None},
                        disabled=[c for c in df.columns if c != 'Quitar cargue'], key='ed_hist')
    sel = ed[ed['Quitar cargue'] & (ed.Origen == 'Cargue')]
    if len(sel) and st.button(f'Quitar {len(sel)} cargue(s)', type='primary'):
        almacen.quitar([tuple(x) for x in sel[['_t', '_k']].values])
        st.cache_data.clear()
        st.success('Listo.')
        st.rerun()


def sin_ubicar():
    st.markdown('Textos de SIVIGILA que no coinciden con ninguna vereda o barrio. Asígnelos una vez y quedan guardados para próximos cargues.')
    raw = Almacen.leer('casos')
    if not len(raw):
        return
    x = raw[raw.u.str.startswith('X:')]
    if not len(x):
        st.success('Todos los casos están ubicados.')
        return
    g = x.groupby('u').agg(Casos=('ev', 'size'), Eventos=('ev', lambda s: ', '.join(sorted({C.EV[e]['nombre'] for e in s})))).sort_values('Casos', ascending=False)
    opciones = sorted(((f"{v['nombre']} — {v['mun']} ({v['tipo']})", k) for k, v in LUG.unidades.items()))
    etiquetas = ['— elegir —'] + [o[0] for o in opciones]
    ids = dict(opciones)
    st.caption(f'{C.fmt(len(g))} textos distintos sin ubicar ({C.fmt(int(g.Casos.sum()))} casos). Se muestran los 60 con más casos.')
    for u, r in g.head(60).iterrows():
        mk, txt = u[2:].split('|', 1)
        c = st.columns([2, 1.2, .6, 3, 1])
        c[0].markdown(f'**{txt}**<br><span class="nota">{r.Eventos}</span>', unsafe_allow_html=True)
        c[1].write(C.MUN_POR_K.get(mk, {}).get('nombre', mk))
        c[2].write(int(r.Casos))
        if u in ALIAS:
            c[3].success(LUG.nombre(ALIAS[u]))
            if c[4].button('Quitar', key='q' + u):
                a = dict(ALIAS); a.pop(u, None)
                almacen.guardar_json('alias.json', a)
                st.cache_data.clear(); st.cache_resource.clear(); st.rerun()
        else:
            v = c[3].selectbox('Asignar a', etiquetas, key='s' + u, label_visibility='collapsed')
            if c[4].button('Asignar', key='a' + u, type='primary', disabled=v == '— elegir —'):
                a = dict(ALIAS); a[u] = ids[v]
                almacen.guardar_json('alias.json', a)
                st.cache_data.clear(); st.cache_resource.clear(); st.rerun()


# =============================================================== navegación
import os
_ini = os.environ.get('ETV_PAGINA', 'casos')  # solo para pruebas
_pag = [(pagina_tablero, 'Casos', '📍', 'casos'), (pagina_analisis, 'Análisis espacial', '🗺️', 'analisis'),
        (pagina_ovitrampas, 'Aedes · ovitrampas', '🦟', 'ovitrampas'), (pagina_encuesta, 'Encuesta larvaria', '🪣', 'encuesta'),
        (pagina_cargar, 'Cargar datos', '⬆️', 'cargar')]
pg = st.navigation([st.Page(f, title=t, icon=i, url_path=u, default=(u == _ini)) for f, t, i, u in _pag], position='top')
pg.run()
st.markdown('<hr style="margin-top:30px"><p class="nota">Gobernación del Guaviare · Secretaría de Salud · Programa de Enfermedades Transmitidas por Vectores. '
            'Los casos se muestran agregados por vereda o barrio; no se publican datos de identificación de pacientes.</p>', unsafe_allow_html=True)
