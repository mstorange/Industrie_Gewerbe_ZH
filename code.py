import geopandas as gpd
import pandas as pd
import numpy as np
import streamlit as st
from shapely.geometry import MultiPolygon
import folium
import json
from folium import Element
from numpy import float64
from datetime import datetime
import matplotlib.pyplot as plt
from streamlit_folium import st_folium
import math
from folium.plugins import Search, MiniMap
import branca

st.title("Industrie- und Gewerbeparzellen im Kanton Zürich")
st.write("Diese App zeigt die Industrie- und Gewerbeparzellen im Kanton Zürich. Du kannst die Parzellen nach Fläche, Baujahr der Gebäude und ÖV-Güteklasse filtern und auf einer interaktiven Karte anzeigen lassen.")

gebproparz = pd.read_json('https://raw.githubusercontent.com/mstorange/Industrie_Gewerbe_ZH/main/gebjahre_pro_parz2026.json')
igfrei = gpd.read_parquet('https://raw.githubusercontent.com/mstorange/Industrie_Gewerbe_ZH/main/igfrei2026.parquet', filesystem='http')
igbebaut = gpd.read_parquet('https://raw.githubusercontent.com/mstorange/Industrie_Gewerbe_ZH/main/igbebaut2026.parquet', filesystem='http')
gwr_grundrisse = gpd.read_parquet('https://raw.githubusercontent.com/mstorange/Industrie_Gewerbe_ZH/main/gwr_grundrisse2026.parquet', filesystem='http')
bfsnr = pd.read_json("https://raw.githubusercontent.com/mstorange/Industrie_Gewerbe_ZH/main/BFSNummern.json")


alleguteklassen = sorted(igfrei.GK_main.unique(), reverse=True)

# hier nun die Flächenfilter und die Baujahrfilter für die pIGbebaut
with st.expander("Filter setzen: "):
    slider_flaeche = st.slider(label="Fläche der Parzelle (m2)", min_value=0, max_value=30000, value=(4000, 10000), step=500)
    slider_altermin = st.slider(label="Ab welchem Alter zählt ein Gebäude als alt?", min_value=0, max_value=100, value=36, step=1)
    slider_bmzmin = st.slider(label="BMZ (min.)", min_value=0, max_value=15, value=3, step=1)
    slider_hoehemin = st.slider(label="Mindesthöhe der Gebäude (m)", min_value=0, max_value=20, value=6, step=1)
    guteklasse_min_wert = st.text_input(label="Güteklasse (min.), Auswahl: [F, E, D, C, B, A]", value='B', key='gk_min')


flmin = slider_flaeche[0]
flmax = slider_flaeche[1]
altermin = slider_altermin
bmz_min = slider_bmzmin
hoehe_min = slider_hoehemin
jahrmax = datetime.today().year - altermin

# guteklasse_min_wert = 'B'
guteklasse_min = [i for i in alleguteklassen if i <= guteklasse_min_wert]

igfrei = igfrei[(igfrei['flaeche_ohne_str']>flmin) & (igfrei['flaeche_ohne_str']<flmax) & (igfrei['GK_main'].isin(guteklasse_min)) & (igfrei['hoehe_max']>=hoehe_min) & (igfrei['BMZmax']>=bmz_min)].reset_index(drop=True)

igbebaut = igbebaut[(igbebaut['flaeche_ohne_str']>flmin) & (igbebaut['flaeche_ohne_str']<flmax) & (igbebaut['GK_main'].isin(guteklasse_min)) & (igbebaut['hoehe_max']>=hoehe_min) & (igbebaut['BMZmax']>=bmz_min)].reset_index(drop=True)

# Altersstufe für die gesamte Parzelle definieren
def altersstufe(jahrliste):
    junge = [j for j in jahrliste if j > jahrmax]
    if len(junge) > 0:
        return 'jung'
    else:
        return 'alt'

gebproparz['alterskat'] = gebproparz['baujahr_gebaeude_kod'].apply(lambda x: altersstufe(x))

parzellalter = dict(zip(gebproparz['egrid'].tolist(), gebproparz['alterskat'].tolist()))

igbebaut['alterskat'] = igbebaut['egrid'].apply(lambda x: parzellalter[x])

# wichtige Spalten wählen
igfrei = igfrei[['egrid', 'parzellenNR', 'flaeche_parzelle','flaeche_ohne_str', 'bfsnr', 'geometry', 'zid', 'zone', 'Gesamthoehe', 'hoehe_max', 'Firsthoehe_Max', 'Gewerbeanteil_Max', 'Vollgeschosse_Max', 'AZmax', 'BMZmax', 'Baumasse_max', 'guteklasse_anteile', 'guteklasse_anteile_pretty', 'GK_main']]

# bebaute aggregieren, damit jede Parzelle nur einmal vorkommt
igbebaut = igbebaut.groupby('egrid').agg({'parzellenNR':'first', 'flaeche_parzelle':'first','flaeche_ohne_str':'first', 'bfsnr':'first', 'geometry':'first', 'zid':'first', 'zone':'first', 'Gesamthoehe':'first', 'hoehe_max':'first', 'Firsthoehe_Max':'first', 'Gewerbeanteil_Max':'first', 'Vollgeschosse_Max':'first', 'AZmax':'first', 'BMZmax':'first', 'Baumasse_max':'first', 'guteklasse_anteile':'first', 'guteklasse_anteile_pretty':'first', 'GK_main':'first', 'alterskat':'first'}).reset_index()
igbebaut = gpd.GeoDataFrame(igbebaut, crs='EPSG:2056', geometry=igbebaut['geometry'])


# BFSnr
bfsdict = dict(zip(bfsnr.bfsnr.tolist(), bfsnr.name.tolist()))
igfrei['gemeinde'] = igfrei['bfsnr'].apply(lambda x: bfsdict[x])
igbebaut['gemeinde'] = igbebaut['bfsnr'].apply(lambda x: bfsdict[x])

# Farben dazufügen
def farbe_alterskat(row):
    if row['alterskat'] == 'jung':
        return "#5E7AC4" # grün
    else:
        return "#2A3E85" # blau

igbebaut['farbe'] = igbebaut.apply(farbe_alterskat, axis=1)

# inkompakte Parzellen entfernen
class CompactObj:
    def __init__(self, poly):
        self.perimeter = poly.length # Umfang
        self.area = poly.area
        self.centroid = poly.centroid
        # self.coordinaten = poly.exterior.coords

    def __str__(self):
        '''definiert, was bei print() rauskommt'''
        return f"Shapely.Polygon als CompactObj"
    
    def pp(self):
        '''Polsby-Popper: Fläche Polygon/Fläche eines Kreises mit dem Umfang des Polygonumfangs.. grosser Wert: kompakter'''
        pp = (4*np.pi*self.area)/(self.perimeter**2)
        return pp
    
from shapely.geometry import MultiPolygon
# from shapely.ops import unary_union
mpw = len(igfrei[igfrei['geometry'].apply(lambda x: isinstance(x, MultiPolygon))])
mpi = len(igbebaut[igbebaut['geometry'].apply(lambda x: isinstance(x, MultiPolygon))])

igfrei['pp'] = igfrei['geometry'].apply(lambda x: CompactObj(x).pp())
igbebaut['pp'] = igbebaut['geometry'].apply(lambda x: CompactObj(x).pp())

igfrei = igfrei[igfrei['pp'] > 0.25].reset_index(drop=True)
igbebaut = igbebaut[igbebaut['pp'] > 0.25].reset_index(drop=True)


# nur die Grundrisse, welche auch mit den bebauten IGP schneiden
gwr_grundrisse = gwr_grundrisse.drop(columns='index_right')
grundrisse_pIG = gpd.sjoin(gwr_grundrisse, igbebaut.to_crs(epsg=2056), how='inner', predicate='intersects')


# Gebäudestring gestalten
def hoverstring_gebäude(row):
    # art = row['klasse']
    egid = int(row['egid'])
    # baujahr = row['Baujahr']
    # wf = round(row['wohnflaeche'], 2)
    centroid = row['geometry'].centroid
    gwr = f'https://map.geo.admin.ch/#/map?lang=de&center={centroid.x},{centroid.y}&z=13&topic=ech&layers=ch.swisstopo.zeitreihen@year=1864,f;ch.bfs.gebaeude_wohnungs_register;ch.bav.haltestellen-oev,f;ch.swisstopo.swisstlm3d-wanderwege,f;ch.vbs.schiessanzeigen,f;ch.astra.wanderland-sperrungen_umleitungen,f&bgLayer=ch.swisstopo.pixelkarte-farbe'
    gwr_hyperlink = f'<a href={gwr}>GWR</a>'
    gwr_zusatzinfo = f'https://api3.geo.admin.ch/rest/services/ech/MapServer/ch.bfs.gebaeude_wohnungs_register/{egid}_0/extendedHtmlPopup?lang=de'
    gwr_zusatzinfo_hyperlink = f'<a href={gwr_zusatzinfo}>GWRInfos</a>'
    return f'{gwr_hyperlink}<br>{gwr_zusatzinfo_hyperlink}'

grundrisse_pIG['Links'] = grundrisse_pIG.apply(hoverstring_gebäude, axis=1)

grundrisse_pIG['Baujahr'] = grundrisse_pIG['Baujahr'].apply(lambda x: str(int(x)) if not math.isnan(x) else 'kein Jahr')


# Zahlen prettify
def prettify_numbers(zahl, kommastellen):
    if pd.isna(zahl):
        pass
    elif isinstance(zahl, int):
        return str(zahl)
    elif kommastellen == 0:
        return str(int(zahl))
    else:
        return str(round(zahl, kommastellen))
    
# schöner gestalten
grundrisse_pIG['egid'] = grundrisse_pIG['egid'].apply(lambda x: prettify_numbers(x, 0))

igfrei['flaeche_parzelle'] = igfrei['flaeche_parzelle'].apply(lambda x: prettify_numbers(x, 0))
igfrei['flaeche_ohne_str'] = igfrei['flaeche_ohne_str'].apply(lambda x: prettify_numbers(x, 0))
igfrei['Baumasse_max'] = igfrei['Baumasse_max'].apply(lambda x: prettify_numbers(x, 0))

igbebaut['flaeche_parzelle'] = igbebaut['flaeche_parzelle'].apply(lambda x: prettify_numbers(x, 0))
igbebaut['flaeche_ohne_str'] = igbebaut['flaeche_ohne_str'].apply(lambda x: prettify_numbers(x, 0))
igbebaut['Baumasse_max'] = igbebaut['Baumasse_max'].apply(lambda x: prettify_numbers(x, 0))


# Karte
igfrei = igfrei.to_crs(epsg=4326)
igbebaut = igbebaut.to_crs(epsg=4326)
grundrisse_pIG = grundrisse_pIG.to_crs(epsg=4326)
igfrei['GoogleMaps'] = igfrei.apply(f.get_gmaps_links,axis=1)
igbebaut['GoogleMaps'] = igbebaut.apply(f.get_gmaps_links,axis=1)
# lidls = lidls.to_crs(epsg=4326)

m = folium.Map(location = [47.417, 8.637], zoom_start=11, tiles= 'CartoDB positron') # CartoDB positron

info = folium.GeoJsonPopup(fields=['egrid','gemeinde','parzellenNR','flaeche_parzelle', 'flaeche_ohne_str','zone', 'Gesamthoehe',
       'hoehe_max', 'Firsthoehe_Max', 'Gewerbeanteil_Max', 'Vollgeschosse_Max', 'BMZmax','Baumasse_max',
       'guteklasse_anteile_pretty', 'GK_main', 'GoogleMaps'], 
aliases=['EGRID','Gemeinde','Parzellen-Nr.','Fläche Parzelle', 'Fläche ohne Strassen','Zone', 'Gesamthöhe',
       'max. Höhe', 'max. Firsthöhe', 'max. Gewerbeanteil', 'max. Vollgeschosse', 'BMZ (max.)','Baumasse (max.)',
       'Anteil ÖV-Güteklasse', 'Güteklasse (main)', 'Google Maps'])

info2 = folium.GeoJsonPopup(fields=['egrid','gemeinde','parzellenNR','flaeche_parzelle', 'flaeche_ohne_str', 'alterskat','zone', 'Gesamthoehe',
       'hoehe_max', 'Firsthoehe_Max', 'Gewerbeanteil_Max', 'Vollgeschosse_Max', 'BMZmax','Baumasse_max',
       'guteklasse_anteile_pretty', 'GK_main', 'GoogleMaps'], 
aliases=['EGRID','Gemeinde','Parzellen-Nr.','Fläche Parzelle', 'Fläche ohne Strassen', 'Alterskategorie (Parzelle)','Zone', 'Gesamthöhe',
       'max. Höhe', 'max. Firsthöhe', 'max. Gewerbeanteil', 'max. Vollgeschosse', 'BMZ (max.)','Baumasse (max.)',
       'Anteil ÖV-Güteklasse', 'Güteklasse (main)', 'Google Maps'])

hoverinfo2 = folium.GeoJsonTooltip(fields=['parzellenNR', 'zone', 'Baumasse_max', 'alterskat', 'GK_main'], 
aliases=['Parzellen-Nr.', 'Zone','Baumasse (max.)', 'Alterskategorie (Parzelle)', 'Güteklasse (main)'])

hoverinfo = folium.GeoJsonTooltip(fields=['parzellenNR', 'zone', 'Baumasse_max', 'GK_main'], 
aliases=['Parzellen-Nr.', 'Zone','Baumasse (max.)', 'Güteklasse (main)'])

info_gebaeude = folium.GeoJsonPopup(fields=['egid', 'municipalityName', 'Baujahr','status','kategorie', 'klasse', 'wohnfläche_gebäude', 'Links'], 
                                    aliases=['EGID', 'Gemeinde', 'Baujahr','Status','Kategorie','Klasse','Wohnfläche','Links'])
baujahr_gebaeude = folium.GeoJsonTooltip(fields=['klasse', 'Baujahr'], aliases=['Klasse','Baujahr'])


fg_wohnen = folium.FeatureGroup(name="freie IG-Parzellen", show=True).add_to(m)
folium.GeoJson(data=igfrei, zoom_on_click=False, 
        style_function=lambda feature: {
        "fillColor": "#79AE6F",
        "fillOpacity":0.85,
        "color": "black",
        "weight": 1,
        #"dashArray": "2, 2",
        },
        highlight_function=lambda feature: {
        "fillColor": "#79AE6F",
        "fillOpacity": 1
        },
    popup=info,
    tooltip=hoverinfo, 
    popup_keep_highlighted=True
    ).add_to(fg_wohnen)


fg_wohnen2 = folium.FeatureGroup(name="bebaute IG-Parzellen", show=True).add_to(m)
folium.GeoJson(data=igbebaut, zoom_on_click=False, 
        style_function=lambda feature: {
        "fillColor": feature['properties']['farbe'],
        "fillOpacity":0.85,
        "color": "black",
        "weight": 1,
        # "dashArray": "2, 2",
        },
        highlight_function=lambda feature: {
        "fillColor": feature['properties']['farbe'],
        "fillOpacity": 1
        },
    popup=info2,
    tooltip=hoverinfo2, 
    popup_keep_highlighted=True
    ).add_to(fg_wohnen2)


# fg_lidls = folium.FeatureGroup(name="bestehende Filialen", show=True).add_to(m)
# folium.GeoJson(data=lidls.to_json(), zoom_on_click=False, marker=folium.Circle(radius=2), 
#         style_function=lambda feature: {
#         "fillColor": 'yellow',
#         "fillOpacity":1,
#         "color": "#df1f72",
#         "weight": 4.5
#         },
#     popup=folium.GeoJsonPopup(fields=['title', 'address', 'type'], aliases=['Filiale', 'Adresse', 'Typ']),
#     tooltip=folium.GeoJsonTooltip(fields=['title', 'address'], aliases=['Filiale', 'Adresse']),
#     ).add_to(fg_lidls)

fg_gebaeude = folium.FeatureGroup(name="Gebäude", show=True).add_to(m)
folium.GeoJson(data=grundrisse_pIG, zoom_on_click=False, 
        style_function=lambda feature: {
        "fillColor": "#e3e3dc",
        "fillOpacity":0.5,
        "color": "gray",
        "weight": 0.2,
        # "dashArray": "2, 2, 2",
        },
        highlight_function=lambda feature: {
        "fillColor": "#babab1",
        "fillOpacity": 1
        },
    popup=info_gebaeude,
    tooltip=baujahr_gebaeude, 
    popup_keep_highlighted=True
    ).add_to(fg_gebaeude)

statesearch = Search(
    layer=fg_wohnen2,
    geom_type="Polygon",
    placeholder="Nach Gemeinde suchen",
    collapsed=False,
    search_label="gemeinde",
    weight=1,
).add_to(m)


tile = folium.TileLayer(
        tiles = 'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
        attr = 'Esri',
        name = 'Esri Satellite',
        overlay = False,
        control = True
       ).add_to(m)
folium.TileLayer('CartoDB voyager').add_to(m)


MiniMap(minimized=False, tile_layer='CartoDB voyager', height=100, zoom_animation=False).add_to(m)

m.add_child(folium.map.LayerControl())
# url = "https://www.losinger-marazzi.ch/static/losingermarazzi/svg/LM_logo.svg"
# FloatImage(url, bottom=1, right=99).add_to(m)
text_box_html = f'''
<div style="
    position: fixed; 
    bottom: 10px; 
    left: 10px; 
    width: 180px; 
    height: auto; 
    padding: 10px;
    background-color: white; 
    border-radius: 0px;
    box-shadow: 0 0 15px rgba(0,0,0,0.2);
    font-family: Arial;
    font-size: 9px;
    z-index: 1000;
">
    <h3 style="margin-top: 0;">Info</h3>
    <p>Die Karte zeigt alle Zürcher Industrie und Gewerbe-Parzellen, welche die folgenden Bedingungen erfüllen:<br> - Parzellfläche von {flmin} bis {flmax} m2<br> - ÖV-Güteklasse mindestens {guteklasse_min_wert}<br> - Neuere Gebäude ab Baujahr {jahrmax} oder jünger</p>
</div>
'''
# farbenfrei = dict({'Basisfiliale':'#11782c', 'Metropolfiliale':'#65b57b', 'Höhe undefiniert, evtl. Metropolfiliale':'#a1ffb8', 'keine Filiale möglich':'#8c3252', 'Höhe undefiniert, prüfen, ob Filiale Platz hätte':'black'})
# farbenbebaut = dict({'Basisfiliale':'#1e0fbf', 'Metropolfiliale':'#5147bf', 'Höhe undefiniert, evtl. Metropolfiliale':'#746eb8', 'keine Filiale möglich':'#8c3252', 'Höhe undefiniert, prüfen, ob Filiale Platz hätte':'black'})

legend_html_blue = '''
{% macro html(this, kwargs) %}
<div style="position: fixed; 
     bottom: 200px; left: 10px; width: 300px; height: 80px; 
     border:0px solid grey; z-index:9999; font-size:14px;
     background-color:white; opacity: 0.95;">
     &nbsp; <b>Legende</b> <br>
     &nbsp; unbebaute Parzelle &nbsp; <i class="fa fa-square" style="color:#79AE6F"></i><br>
     &nbsp; bebaute Parzelle mit alten Gebäuden &nbsp; <i class="fa fa-square" style="color:#2A3E85"></i><br>
     &nbsp; bebaute Parzellen mit neueren Gebäuden &nbsp; <i class="fa fa-square" style="color:#5E7AC4"></i><br>
</div>
{% endmacro %}
'''

# legend_html_green = '''
# {% macro html(this, kwargs) %}
# <div style="position: fixed; 
#      bottom: 300px; left: 10px; width: 150px; height: 80px; 
#      border:0px solid grey; z-index:9999; font-size:14px;
#      background-color:white; opacity: 0.85;">
#      &nbsp; <b>unbebaut</b> <br>
#      &nbsp; Basisfiliale &nbsp; <i class="fa fa-square" style="color:#11782c"></i><br>
#      &nbsp; Metropolfiliale &nbsp; <i class="fa fa-square" style="color:#9DDE8B"></i><br>
#      &nbsp; evtl. Metropol &nbsp; <i class="fa fa-square" style="color:#E6FF94"></i><br>
# </div>
# {% endmacro %}
# '''

legend = branca.element.MacroElement()
legend._template = branca.element.Template(legend_html_blue)
# legend2 = branca.element.MacroElement()
# legend2._template = branca.element.Template(legend_html_green)

# Add the legend to the map
m.get_root().add_child(legend)
# m.get_root().add_child(legend2)

# Add the text box to the map
m.get_root().html.add_child(folium.Element(text_box_html))
# Save the map

map_title = f"Industrie- und Gewerbeparzellen ({len(igfrei)} unbebaute + {len(igbebaut)} bebaute)"
title_html = f'<h3 align="center" style="font-size:20px"><b>{map_title}</b></h3>'
m.get_root().html.add_child(folium.Element(title_html))

st_data = st_folium(m, height = 500, width = 1300, returned_objects=[])
