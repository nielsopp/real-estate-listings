from branca.colormap import linear
import datetime
import folium
import geojson
import geopandas as gpd
from geopy.geocoders import ArcGIS
from homeharvest import scrape_property
import numpy as np
import pandas as pd
import shapely


def assemble_map():

    m = folium.Map(location=(32.31,-110.89),tiles='esri natgeoworldmap',zoom_start=13)

    # load sewer data
    sewer_data = gpd.read_file('Sewers_-_Pima_County_RWRD_Service_Area.geojson')

    with open('School_Attendance_Areas.geojson','r') as f:
        school_data = geojson.load(f)

    schoolcolors = {'SUNRISE DRIVE ELEMENTARY SCHOOL':'green',
                    'MANZANITA ELEMENTARY SCHOOL':'orange',
                    'VENTANA VISTA ELEMENTARY SCHOOL':'red'}

    featlist = []
    for feat in school_data['features']:
        if feat['properties']['NAME'] in schoolcolors.keys():
            featlist.append(feat)
    school_data = gpd.GeoDataFrame.from_features(featlist,crs='EPSG:4326')
    # school_data['features'] = featlist


    folium.GeoJson(sewer_data,
                   style_function=lambda feature:{
                    'fillColor':'cyan',
                    'fillOpacity':0.2,
                    'weight':1,
                    'color':'cyan'
                   },
                   name='Sewer coverage'
                  ).add_to(m)

    popup = folium.GeoJsonPopup(fields=['NAME'])

    folium.GeoJson(school_data,
                   style_function=lambda feature:{
                    'fillColor':schoolcolors[feature['properties']['NAME']],
                    'fillOpacity':0.1,
                    'weight':2,
                    'color':schoolcolors[feature['properties']['NAME']]
                   },
                   highlight_function=lambda feature:{'fillOpacity':0.2},
                   popup=popup,
                   popup_keep_highlighted=True,
                   name='Elementary school zones'
                  ).add_to(m)

    return m, sewer_data, school_data


def convert_date(d):
    if pd.isnull(d):
        return None
    try:
        return d.strftime('%Y-%m-%d')
    except:
        raise ValueError('malformatted date')


def read_listing_data():
    df_sale = scrape_property(location='Tucson, AZ',
                              listing_type=['for_sale'],
                              property_type=['single_family','townhomes','duplex_triplex'],
                              radius=2)
    df_land = scrape_property(location='Tucson, AZ',
                              listing_type=['for_sale'],
                              property_type=['land'],
                              radius=2)
    df_rent = scrape_property(location='Tucson, AZ',
                              listing_type=['for_rent'],
                              property_type=['single_family','townhomes','duplex_triplex'],
                              radius=2)
    df_sale['proptype'] = 'Residential'
    df_land['proptype'] = 'Land'
    df_rent['proptype'] = 'Residential Lease'
    df = pd.concat([df_sale,df_land,df_rent],ignore_index=True)
    df = df.rename(columns={'full_street_line':'Address',
                            'property_url':'Link',
                            'status':'Status',
                            'beds':'Bedrooms',
                            'sqft':'BuildingSqft',
                            'year_built':'YearBuilt',
                            'list_price':'Price',
                            'list_date':'ListDate',
                            'new_construction':'NewConstruction',
                            'lot_sqft':'LotSqft',
                            'stories':'Stories',
                            'hoa_fee':'HOAFee',
                            'parking_garage':'Garage'})
    df['full_baths'] = np.where(pd.isnull(df.full_baths.values),0,df.full_baths.values)
    df['half_baths'] = np.where(pd.isnull(df.half_baths.values),0,df.half_baths.values)
    df['Bathrooms'] = df.apply(lambda x: float(x.full_baths) + float(x.half_baths),axis=1)
    # df['ListDate'] = df.ListDate.apply(convert_date)
    return df


def check_sewer_coverage(row,df_sewer):
    if np.any(df_sewer.geometry.contains(row.geometry).values):
        return True
    else:
        return False


def check_school_area(row,df_school):
    schools = df_school.NAME.values
    contained = df_school.geometry.contains(row.geometry).values
    school = schools[contained]
    if len(school) == 1:
        return school[0]
    elif len(school) > 1:
        print('More than one school zone covers Address %s'%row.Address)
        return 'UNKNOWN'
    else:
        return 'UNKNOWN'


def format_search_string(row):
    addr = str(row.Address).replace(' ','+')
    addr = addr + '+Tucson'
    searchstr = f'https://duckduckgo.com/?q={addr}&t=newext&atb=v371-1&ia=web'
    searchstr = f'<a href="{searchstr}" target="_blank" rel="noopener noreferrer">Duckduckgo</a>'
    return searchstr


def format_link(row):
    linkstr = f'<a href="{row.Link}" target="_blank" rel="noopener noreferrer">Realtor.com</a>'
    return linkstr


def format_image(row):
    imstr = f'<img src="{row.primary_photo}" width=200px/>'
    return imstr

def add_derived_info(df,df_sewer,df_school):
    # app = ArcGIS()
    # for ii,row in df.iterrows():
        # addr = row.Address + ', Tucson, AZ'
        # loc = app.geocode(addr)
        # df.loc[ii,'Longitude'] = loc.longitude
        # df.loc[ii,'Latitude'] = loc.latitude
    df = gpd.GeoDataFrame(df,geometry=gpd.points_from_xy(df.longitude,df.latitude),crs='EPSG:4326')
    df['SewerCoverage'] = df.apply(check_sewer_coverage,axis=1,args=[df_sewer,])
    df['SchoolAttendanceArea'] = df.apply(check_school_area,axis=1,args=[df_school,])
    df['Search'] = df.apply(format_search_string,axis=1)
    df['Link'] = df.apply(format_link,axis=1)
    df['Image'] = df.apply(format_image,axis=1)
    # mamawork = app.geocode('950 N Cherry Ave, Tucson')
    # mamawork = gpd.GeoSeries(data=gpd.points_from_xy([mamawork.longitude],[mamawork.latitude]),crs='EPSG:4326')
    # df['DistanceToMamaWork'] = df.geometry.distance(mamawork.to_crs(epsg=4326).values[0])
    # papawork = app.geocode('3950 S Country Club Rd, Tucson')
    # papawork = gpd.GeoSeries(data=gpd.points_from_xy([papawork.longitude],[papawork.latitude]),crs='EPSG:4326')
    # df['DistanceToPapaWork'] = df.geometry.distance(papawork)
    return df


def add_listings_to_map(m,dfs):
    # columns_of_interest = ['Address','Status','ListDate','Bedrooms','Bathrooms','BuildingSqft','LotSqft','YearBuilt','Price','SewerCoverage','SchoolAttendanceArea','Garage','Stories','HOAFee','NewConstruction','TotalPoints','Search','Link']
    columns_of_interest = ['Image','Address','Status','Bedrooms','Bathrooms','BuildingSqft','YearBuilt','LotSqft','Price','SewerCoverage','SchoolAttendanceArea','Garage','Stories','HOAFee','NewConstruction','TotalPoints','Search','Link','ListDate']
    colormap = linear.YlGn_09.scale(0,70)
    for pt,df in dfs.items():
        folium.GeoJson(df,
                       name=pt,
                       marker=folium.CircleMarker(radius=5,fill_color='magenta',fill_opacity=0.4,color='black',weight=1),
                       tooltip=folium.GeoJsonTooltip(fields=columns_of_interest),
                       popup=folium.GeoJsonPopup(fields=columns_of_interest,max_width=800),
                       style_function=lambda feature: {'fillColor':colormap(feature['properties']['TotalPoints'])},
                       highlight_function=lambda feature: {'fillOpacity':0.8}
                      ).add_to(m)
    colormap.caption = f'TotalPoints'
    colormap.add_to(m)
    return m


def score(v,col,proptype):
    if proptype == 'Land' and col in ['Bedrooms','Bathrooms','YearBuilt','BuildingSqft','Garage','Stories','NewConstruction']:
        return v

    if col == 'Bedrooms':
        if pd.isnull(v):
            points = -50
        elif v == '<NA>':
            points = -50
        else:
            v = float(v)
            if v == 3:
                points = 5
            elif v == 4:
                points = 4
            elif v == 5:
                points = 3
            elif v > 5:
                points = 0
            elif v == 2:
                points = -10
            else:
                points = -50
    elif col == 'Bathrooms':
        if pd.isnull(v):
            points = -50
        elif v > 2 and v < 4:
            points = 5
        elif v >= 4:
            points = 0
        elif v > 1:
            points = 0
        else:
            points = -50
    elif col == 'LotSqft':
        if pd.isnull(v):
            points = -50
        elif v == '<NA>':
            points = -50
        else:
            v = float(v)
            if v/43560 > 0.25 and v/43560 < 0.75:
                points = 5 - 8*np.abs(v/43560 - 0.5)
            elif v/43560 > 0.75:
                points = 3 - 12*np.abs(v/43560 - 0.75)
            else:
                points = 3 - 24*np.abs(v/43560 - 0.25)
    elif col == 'YearBuilt':
        if pd.isnull(v):
            points = -50
        elif v == '<NA>':
            points = -50
        else:
            v = float(v)
            points = 0.5*(v - 2000)
    elif col == 'Price':
        if pd.isnull(v):
            points = -50
        elif v == '<NA>':
            points = -50
        else:
            v = float(v)
            if proptype == 'Residential':
                points = np.min([7,(700000 - v)/15000])
            elif proptype == 'Residential Lease':
                points = (3250 - v)/50
            elif proptype == 'Land':
                points = (350000 - v)/7500
    elif col == 'SewerCoverage':
        if v == True:
            points = 10
        elif v == False:
            points = -10
        else:
            print('sewer coverage could not be assessed')
            points = 0
    elif col == 'SchoolAttendanceArea':
        if v == 'SUNRISE DRIVE ELEMENTARY SCHOOL':
            points = 25
        elif v == 'MANZANITA ELEMENTARY SCHOOL':
            points = 7.5
        elif v == 'VENTANA VISTA ELEMENTARY SCHOOL':
            points = -5
        else:
            points = -10
    elif col == 'BuildingSqft':
        if pd.isnull(v):
            points = 0
        elif v == '<NA>':
            points = 0
        else:
            v = float(v)
            if v >= 2000 and v <= 2500:
                points = 8
            elif v < 2000:
                points = 8 + (v - 2000)/50
            else:
                points = 8 - (v - 2500)/200
    elif col == 'Garage':
        if pd.isnull(v):
            points = -10
        else:
            v = float(v)
            if v > 2:
                points = 5
            elif v > 3:
                points = -2
            elif v < 1:
                points = -10
            elif v < 1.5:
                points = 0
            else:
                points = 10
    elif col == 'Stories':
        if pd.isnull(v):
            points = 0
        elif v == '<NA>':
            points = 0
        else:
            v = float(v)
            if v > 1:
                points = 5
            else:
                points = 0
    elif col == 'NewConstruction':
        if pd.isnull(v):
            points = 0
        elif v == False:
            points = 0
        else:
            points = 20
    elif col == 'HOAFee':
        if pd.isnull(v):
            points = 0
        elif v == '<NA>':
            points = 0
        else:
            v = float(v)
            points = -v/62.5
    return f'{v} ({points:.1f} Points)'


def add_total_points(row):
    tot = 0
    for v in row.values:
        try:
            if str(v)[-7:] == 'Points)':
                points = float(str(v).split('(')[-1].rstrip(' Points)'))
                tot += points
        except:
            print('issues with points value %s'%str(v))
    return tot


def add_points_and_split(df):
    propertytypes = df.proptype.unique()
    print(propertytypes)
    dfs = {pt:df[df.proptype == pt].reset_index() for pt in propertytypes}
    
    for pt,df in dfs.items():
        for col in ['Bedrooms','Bathrooms','LotSqft','YearBuilt','Price','SewerCoverage','SchoolAttendanceArea','BuildingSqft','Garage','Stories','NewConstruction','HOAFee']:
            df[col] = df[col].apply(score,args=[col,pt,])
        df['TotalPoints'] = df.apply(add_total_points,axis=1)
    return dfs


def get_tops(dfs,date):
    lines = ['<header>','<title>Top-ten listings</title>','</header>','<body>']

    toptens = {}
    for pt in dfs:
        df = dfs[pt]
        df = df[df.SchoolAttendanceArea == 'SUNRISE DRIVE ELEMENTARY SCHOOL (25.0 Points)'].sort_values(by=['TotalPoints',],ascending=False).reset_index()
        toptens[pt] = []
        for ii in range(10):
            try:
                toptens[pt].append(df.Image.values[ii] + '<br />' + df.Link.values[ii].replace('Realtor.com',df.Address.values[ii]))
            except IndexError:
                pass
            
    lines.append('<h1>Sunrise Drive Elementary</h1>')
    lines.append('<table>')
    lines.append('<tr>')
    for pt in toptens:
        lines.append(f'<th>{pt}</th>')
    lines.append('</tr>')
    for ii in range(10):
        lines.append('<tr>')
        for pt in toptens:
            try:
                lines.append(f'<td>{toptens[pt][ii]}</td>')
            except IndexError:
                lines.append('<td>-</td>')
        lines.append('</tr>')
    lines.append('</table>')

    toptens = {}
    for pt in dfs:
        df = dfs[pt]
        df = df[(df.SchoolAttendanceArea != 'UNKNOWN (-10.0 Points)') & (df.SchoolAttendanceArea != 'SUNRISE DRIVE ELEMENTARY SCHOOL (25.0 Points)')].sort_values(by=['TotalPoints',],ascending=False).reset_index()
        toptens[pt] = []
        for ii in range(10):
            try:
                toptens[pt].append(df.Image.values[ii] + '<br />' + df.Link.values[ii].replace('Realtor.com',df.Address.values[ii]))
            except IndexError:
                pass
            
    lines.append('<h1>Neighboring Catalina Foothills Elementary Schools</h1>')
    lines.append('<table>')
    lines.append('<tr>')
    for pt in toptens:
        lines.append(f'<th>{pt}</th>')
    lines.append('</tr>')
    for ii in range(10):
        lines.append('<tr>')
        for pt in toptens:
            try:
                lines.append(f'<td>{toptens[pt][ii]}</td>')
            except IndexError:
                lines.append('<td>-</td>')
        lines.append('</tr>')
    lines.append('</table>')
    
    toptens = {}
    for pt in dfs:
        df = dfs[pt]
        df = df[df.SchoolAttendanceArea == 'UNKNOWN (-10.0 Points)'].sort_values(by=['TotalPoints',],ascending=False).reset_index()
        toptens[pt] = []
        for ii in range(10):
            try:
                toptens[pt].append(df.Image.values[ii] + '<br />' + df.Link.values[ii].replace('Realtor.com',df.Address.values[ii]))
            except IndexError:
                pass

    lines.append('<h1>Elsewhere</h1>')
    lines.append('<table>')
    lines.append('<tr>')
    for pt in toptens:
        lines.append(f'<th>{pt}</th>')
    lines.append('</tr>')
    for ii in range(10):
        lines.append('<tr>')
        for pt in toptens:
            try:
                lines.append(f'<td>{toptens[pt][ii]}</td>')
            except IndexError:
                lines.append('<td>-</td>')
        lines.append('</tr>')
    lines.append('</table>')

    with open(f'TopTen_{date}.html','w') as f:
        f.writelines(lines)
    return


if __name__ == '__main__':
    date = datetime.datetime.today().strftime('%Y-%m-%d')
    print('assembling map')
    m,df_sewer,df_school  = assemble_map()
    print('querying listings')
    df = read_listing_data()
    print('adding derived info')
    df = add_derived_info(df,df_sewer,df_school)
    print('saving')
    df.to_file(f'listing_{date}.geojson')
    df = gpd.GeoDataFrame.from_file(f'listing_{date}.geojson')
    del df['last_status_change_date']
    del df['last_update_date']
    print('scoring')
    dfs = add_points_and_split(df)
    pd.concat(dfs,ignore_index=True).to_csv(f'listing_{date}_scored.csv',index=False)
    print('mapping')
    m = add_listings_to_map(m,dfs)
    print('rendering')
    folium.LayerControl(collapsed=False).add_to(m)
    m.save(f'listing_{date}.html')
    get_tops(dfs,date)