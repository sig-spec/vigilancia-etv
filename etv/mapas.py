"""Ayudas de mapas (folium) y gráficos (plotly) con la identidad de la Gobernación."""
from __future__ import annotations

import copy

import folium
from folium.plugins import Fullscreen

AZUL, AZUL2, GRIS, LINEA, PANEL = '#004884', '#005eb0', '#5b6b7c', '#c9d3de', '#eef2f7'
PAL = ['#c0392b', '#2a6f97', '#7d3c98', '#d26a1c', '#16a085', '#8d6e63', '#b8860b', '#c2185b', '#1b5e20', '#455a64']


def mapa_base(centro=(2.1, -72.4), zoom=8):
    m = folium.Map(location=centro, zoom_start=zoom, tiles=None, control_scale=True, prefer_canvas=True)
    folium.TileLayer(tiles='https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Light_Gray_Base/MapServer/tile/{z}/{y}/{x}',
                     attr='Esri', name='Mapa claro', max_zoom=16).add_to(m)
    folium.TileLayer('OpenStreetMap', name='OpenStreetMap', show=False).add_to(m)
    folium.TileLayer(tiles='https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
                     attr='Esri', name='Satélite', show=False).add_to(m)
    Fullscreen(title='Pantalla completa', title_cancel='Salir').add_to(m)
    m.get_root().header.add_child(folium.Element('<style>.leaflet-control-attribution{font-size:10px!important}</style>'))
    return m


def capas_ref(m, geo, ref, encendidas=('muni', 'cab'), excluir=()):
    """Capas de referencia. Se agregan en orden: polígonos primero y puntos/líneas encima."""
    if 'manz' not in excluir and ref.get('manzanas'):
        folium.GeoJson(ref['manzanas'], name='Manzanas DANE (población 2026)', show='manz' in encendidas,
                       style_function=lambda f: {'color': '#5b6b7c', 'weight': .5, 'fillColor': '#3b76fb',
                                                 'fillOpacity': min(.55, (f['properties'].get('pob') or 0) / 250)},
                       tooltip=folium.GeoJsonTooltip(['cod', 'mun', 'viv', 'pob'], aliases=['Manzana', 'Municipio', 'Viviendas', 'Población 2026'])).add_to(m)
    if 'sec' not in excluir and ref.get('sectores_cal'):
        folium.GeoJson(ref['sectores_cal'], name='Sectores ETV Calamar', show='sec' in encendidas,
                       style_function=lambda f: {'color': AZUL, 'weight': 2, 'fillColor': PAL[(f['properties']['sector'] - 1) % len(PAL)], 'fillOpacity': .18},
                       tooltip=folium.GeoJsonTooltip(['nombre', 'barrios', 'manz', 'viv'], aliases=['Sector', 'Barrios', 'Manzanas', 'Viviendas'])).add_to(m)
    if 'mcal' not in excluir and ref.get('manzanas_cal'):
        folium.GeoJson(ref['manzanas_cal'], name='Manzanas Calamar por sector', show='mcal' in encendidas,
                       style_function=lambda f: {'color': PAL[(f['properties']['sector'] - 1) % len(PAL)], 'weight': 1, 'fillOpacity': .08},
                       tooltip=folium.GeoJsonTooltip(['manzana', 'sector', 'barrio', 'viv'], aliases=['Manzana', 'Sector', 'Barrio', 'Viviendas'])).add_to(m)
    if 'ver' not in excluir:
        folium.GeoJson(geo['veredas'], name='Veredas (límite)', show='ver' in encendidas,
                       style_function=lambda f: {'color': '#6b7f95', 'weight': .8, 'fill': False, 'dashArray': '3 3'},
                       tooltip=folium.GeoJsonTooltip(['nombre', 'mun'], aliases=['Vereda', 'Municipio'])).add_to(m)
    if 'bar' not in excluir:
        folium.GeoJson(geo['barrios'], name='Barrios San José (límite)', show='bar' in encendidas,
                       style_function=lambda f: {'color': '#3b76fb', 'weight': 1.2, 'fill': False},
                       tooltip=folium.GeoJsonTooltip(['nombre'], aliases=['Barrio'])).add_to(m)
    if 'muni' not in excluir:
        folium.GeoJson(geo['municipios'], name='Límite municipal (DANE)', show='muni' in encendidas, interactive=False,
                       style_function=lambda f: {'color': AZUL, 'weight': 2.4, 'fill': False, 'opacity': .95}).add_to(m)
    if 'cab' not in excluir:
        g = folium.FeatureGroup(name='Cabeceras municipales', show='cab' in encendidas)
        for f in geo['cabeceras']['features']:
            lon, lat = f['geometry']['coordinates']
            folium.CircleMarker((lat, lon), radius=5, color='#fff', weight=1.5, fill=True, fill_color=AZUL, fill_opacity=1,
                                tooltip=f['properties']['mun']).add_to(g)
        g.add_to(m)


def coropleta(m, fc, valor, color, tooltip, nombre, opac=.9, show=True):
    """valor(props) -> número o None; color(v) -> color; tooltip(props, v) -> html."""
    fc = copy.deepcopy(fc)
    for f in fc['features']:
        v = valor(f['properties'])
        f['properties']['_c'] = color(v)
        f['properties']['_o'] = .35 if v is None else opac
        f['properties']['_t'] = tooltip(f['properties'], v)
    folium.GeoJson(fc, name=nombre, show=show,
                   style_function=lambda f: {'color': '#8a9bb0', 'weight': .7, 'fillColor': f['properties']['_c'], 'fillOpacity': f['properties']['_o']},
                   highlight_function=lambda f: {'weight': 2.2, 'color': AZUL},
                   tooltip=folium.GeoJsonTooltip(['_t'], labels=False)).add_to(m)


def leyenda(m, titulo, puntos=(), lineas=(), poligonos=(), nota=''):
    """Leyenda: primero puntos y líneas, después polígonos."""
    filas = [f'<div style="font-weight:700;color:{AZUL};margin-bottom:4px">{titulo}</div>']
    for c, t in puntos:
        filas.append(f'<div><span style="display:inline-block;width:10px;height:10px;border-radius:50%;background:{c};border:1px solid #333;margin-right:6px"></span>{t}</div>')
    for c, t in lineas:
        filas.append(f'<div><span style="display:inline-block;width:16px;height:0;border-top:3px solid {c};margin:0 6px 3px 0;vertical-align:middle"></span>{t}</div>')
    for c, t in poligonos:
        filas.append(f'<div><span style="display:inline-block;width:14px;height:10px;background:{c};border:1px solid #8a9bb0;margin-right:6px"></span>{t}</div>')
    if nota:
        filas.append(f'<div style="color:{GRIS};margin-top:4px;max-width:200px">{nota}</div>')
    html = ('<div style="position:absolute;bottom:34px;left:10px;z-index:9999;background:rgba(255,255,255,.95);padding:8px 10px;'
            'border:1px solid #c9d3de;border-radius:6px;font:12px Segoe UI,Arial,sans-serif;color:#102a43;line-height:1.5">' + ''.join(filas) + '</div>')
    m.get_root().html.add_child(folium.Element(html))


def encuadrar(m, latlons, pad=0.01):
    if not latlons:
        return
    la = [p[0] for p in latlons]
    lo = [p[1] for p in latlons]
    m.fit_bounds([[min(la) - pad, min(lo) - pad], [max(la) + pad, max(lo) + pad]])


def limites(fc):
    xs, ys = [], []
    for f in fc['features']:
        g = f['geometry']
        polys = g['coordinates'] if g['type'] == 'MultiPolygon' else [g['coordinates']]
        for p in polys:
            for x, y in p[0]:
                xs.append(x); ys.append(y)
    return [[min(ys), min(xs)], [max(ys), max(xs)]]


# ------------------------------------------------------------------ plotly
def estilo_fig(fig, titulo='', alto=330, leyenda_abajo=True):
    fig.update_layout(
        title=dict(text=titulo, font=dict(size=14, color=AZUL), x=0, xanchor='left'),
        height=alto, margin=dict(l=10, r=10, t=40 if titulo else 10, b=10),
        paper_bgcolor='white', plot_bgcolor='white', font=dict(family='Segoe UI, Arial', size=12, color='#102a43'),
        legend=dict(orientation='h', y=-0.18, x=0) if leyenda_abajo else None, bargap=.18,
        separators=',.')
    fig.update_xaxes(showgrid=False, linecolor=LINEA)
    fig.update_yaxes(gridcolor='#e6ebf1', zeroline=False)
    return fig


def cfg_png(nombre):
    return {'displaylogo': False, 'toImageButtonOptions': {'format': 'png', 'filename': nombre, 'scale': 2},
            'modeBarButtonsToRemove': ['lasso2d', 'select2d']}
