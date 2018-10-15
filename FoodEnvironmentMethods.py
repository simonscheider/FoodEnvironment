#-------------------------------------------------------------------------------
# Name:        Methods for capturing the food environment of tracks in terms of
#               accessible (afforded) food outlets.   This includes identifying
#               fixed and flexible (food) events in a track, as well as calculating
#               space-time prisms over a network to capture affordance space.
# Purpose:       In order to assess the food environment from an affordance perspective
#
# Author:      Simon Scheider
#
# Created:     05/10/2018
# Copyright:   (c) Simon Scheider 2018
# Licence:     MIT license
#-----------------------------------------------------------------------------
import csv
import time
import requests
myappid   = 'omN8lWe0pRNExedt6Gh2'
myappcode = 'bS_F57D8weI6ZNzEYJ_UmQ'
import json
import shapely
from shapely import geometry
from shapely.geometry import shape, Point, mapping, Polygon
import fiona
import geopandas
from geopandas.tools import sjoin
import pandas as pd
import numpy as np

from datetime import  date, datetime

import pyproj
#see https://github.com/jswhit/pyproj
from shapely.ops import transform
import rtree
from xlrd import open_workbook
import os


project = lambda x, y: pyproj.transform(pyproj.Proj(init='EPSG:4326'), pyproj.Proj(init='EPSG:28992'), x, y)
reproject =  lambda x, y: pyproj.transform(pyproj.Proj(init='EPSG:28992'), pyproj.Proj(init='EPSG:4326'), x, y)

"""Function for constructing fixed and flexible (food) events from a collection of trips"""
def constructEvents():
    pass


"""Main Function for computing space-time prism based outlet accessibility for a modifiable event"""
def getAffordances(eventid, startpoint, starttime, endpoint, endtime, mineventduration, sidx,ids, outlets):
    print 'Finding afforded outlets for event ' +str(eventid)
    totalduration =  (endtime - starttime).total_seconds()
    print "totalduration :" +str(totalduration)

    prism = getAccessibility(starttime.isoformat(),startpoint, endtime.isoformat(), endpoint, totalduration, mineventduration, save=os.path.join(r"C:\Users\schei008\Dropbox\Schriften\Exchange\GOF\results",str(eventid)+"prism.shp"))
    candidates, candidateids = getAccessibleOutlets(prism, sidx,ids, outlets, save=os.path.join(r"C:\Users\schei008\Dropbox\Schriften\Exchange\GOF\results",str(eventid)+"preso.shp"))
    print str(len(candidates))+" outlets pre-selected!"
    v1 = get1TravelMatrix(startpoint, candidates)
    v2 = get1TravelMatrix(endpoint, candidates, inverse=True)
    trips = getAffordedTrips(candidateids, candidates,v1,v2, mineventduration, totalduration)
    saveOutlets(trips,save=os.path.join(r"C:\Users\schei008\Dropbox\Schriften\Exchange\GOF\results",str(eventid)+"afo.shp"))


def getAccessibility(starttime,startpoint, endtime, endpoint, timewindow, mineventduration=300, mode="car", save=r"C:\Users\schei008\Dropbox\Schriften\Exchange\GOF\results\prism.shp"):
    print "Start getting accessibility prism"
    #starttime=starttime+datetime.timedelta()
    availabletime = timewindow-mineventduration-300 #5 minutes minimum to get to the destination
    print "maxtraveltime: " +str(availabletime)
    polystart = transform(project, getisoline(startpoint,availabletime, mode= mode, starttime=starttime))
    polyend = transform(project, getisoline(endpoint, availabletime, mode=mode, starttime=endtime)) #De Uithof
    inters = polystart.intersection(polyend)
    schema = {
        'geometry': 'Polygon',
        'properties': {'id': 'int'},
        }

    # Write a new Shapefile
    with fiona.open(save, 'w', 'ESRI Shapefile', schema) as c:
        ## If there are multiple geometries, put the "for" loop here
            c.write({
                'geometry': mapping(inters),
                'properties': {'id': 0},
                })

    c.close
    prism = inters
    #print prism
    return prism

def getisoline(startpoint, durationseconds, mode="car", starttime="2013-07-04T17:00:00"):   #pedestrian; publicTransport; bicycle
    ruri = "https://isoline.route.api.here.com/routing/7.2/calculateisoline.json?app_id="+myappid+"&app_code="+myappcode+"&mode=shortest;"+mode+";traffic:disabled&start=geo!"+str(startpoint.y)+","+str(startpoint.x)+"&range="+str(int(durationseconds))+"&rangetype=time&departure="+starttime
    myResponse = requests.get(ruri)
    # For successful API call, response code will be 200 (OK)
    if(myResponse.ok):
        # Loading the response data into a dict variable
        # json.loads takes in only binary or string variables so using content to fetch binary content
        # Loads (Load String) takes a Json file and converts into python data structure (dict or list, depending on JSON)
        jData = json.loads(myResponse.content)
        coords = ((jData["response"]['isoline'][0])['component'][0])['shape']
        #print coords
        polygon = Polygon([[float(i.split(",")[1]), float(i.split(",")[0])] for i in coords ])
        #print polygon
        #with open("test.json", 'w') as fp:
            #json.dump(jData, fp)
        return polygon
    else:
            # If response code is not ok (200), print the resulting http error code with description
            myResponse.raise_for_status()

def get1TravelMatrix(startpoint, outlets, mode="car", inverse=False):
    if inverse:  #computes traveltimes to startpoint starting from outlets instead
        od = 'destination'
        outl = 'start'
    else:
        od = 'start'
        outl = 'destination'
    ruri0 = "https://matrix.route.api.here.com/routing/7.2/calculatematrix.json?app_id="+myappid+"&app_code="+myappcode+"&summaryAttributes=traveltime&mode=shortest;"+mode+";traffic:disabled&"+od+"0="+str(startpoint.y)+","+str(startpoint.x)
    print "getting routing matrix"
    traveltimes = np.array([])
    c =0
    ruri = ruri0
    for count,g in enumerate(outlets):
        g = transform(reproject, g)
        ruri = ruri+"&"+outl+str(c)+"="+str(g.y)+","+str(g.x)
        c +=1
        if c == 100:
            r = fireTTrequest(ruri)
            c = 0
            ruri = ruri0
            if r.any():
                traveltimes = np.append(traveltimes,r)
            #break
    #print ruri
    r = fireTTrequest(ruri)
    if r.any():
        traveltimes = np.append(traveltimes,r)
    print str(traveltimes.size)+" outlet distances computed!"
    return traveltimes

def fireTTrequest(ruri):
    print "... fire matrix request!"
    myResponse = requests.get(ruri)
    # For successful API call, response code will be 200 (OK)
    if(myResponse.ok):
        # Loading the response data into a dict variable
        # json.loads takes in only binary or string variables so using content to fetch binary content
        # Loads (Load String) takes a Json file and converts into python data structure (dict or list, depending on JSON)
        jData = json.loads(myResponse.content)
        #print jData
        listofmatrixcells = jData['response']['matrixEntry']
        #print listofmatrixcells
        #We assume here long distances for all failed matrix calculations
        traveltimes = np.array([ [999999999] if 'status' in e.keys() and e['status'] == 'failed' else [e['summary']['travelTime']] for e in listofmatrixcells])
        return traveltimes #This is a vector of traveltimes in seconds

    else:
            # If response code is not ok (200), print the resulting http error code with description
            myResponse.raise_for_status()

def getAffordedTrips(ids, outlets, vOrigin, vDestination, mineventduration, timemax):
    vsum = (np.add(np.add(vOrigin, vDestination),mineventduration))
    #print vsum
    trips =   [(id, outlets[ix]) for ix,id in enumerate(ids) if vsum[ix]<=timemax]
    print str(len(trips)) + " trips afforded timewise!"
    return trips

def saveOutlets(trips, save=r"C:\Users\schei008\Dropbox\Schriften\Exchange\GOF\results\accoutlets.shp"):
    schema = {
        'geometry': 'Point',
        'properties': {'id': 'int'},
        }

    # Write a new Shapefile
    with fiona.open(save, 'w', 'ESRI Shapefile', schema) as c:
        with open(os.path.splitext(save)[0]+'.csv', 'wb') as csvfile:
            writer = csv.writer(csvfile, delimiter=',', quotechar='"', quoting=csv.QUOTE_MINIMAL)
        ## If there are multiple geometries, put the "for" loop here
            for i in trips:
                writer.writerow([i[0], i[1]])
                c.write({
                    'geometry': mapping(i[1]),
                    'properties': {'id': i[0]},
                    })
    c.close
    csvfile.close


def loadOutlets(outletdata= r"C:\Temp\Locatus\outlets.shp", colx = 1, coly = 2):
    workbook = r"C:\Temp\Locatus\Levensmiddel_Horeca_311217.xlsx"
    w = open_workbook(workbook)
    sheet = w.sheet_by_index(0)
    outlets = []
    ids = []
    for rowidx in range(1,sheet.nrows):
            x = float(sheet.cell(rowidx, sheet.ncols - colx).value)
            y = float(sheet.cell(rowidx, sheet.ncols - coly).value)
            p = transform(project, Point(x,y))
            outlets.append(p)
            ids.append(sheet.cell(rowidx, 0).value)
##    schema = {
##        'geometry': 'Point',
##        'properties': {'id': 'int'},
##    }
    sidx = generate_index(outlets)  #, os.path.dirname(outletdata)
    #points = geopandas.GeoDataFrame.from_file(outletdata)
    return sidx,ids, outlets

##    # Write a new Shapefile
##    with fiona.open(outletdata, 'w', 'ESRI Shapefile', schema) as c:
##        ## If there are multiple geometries, put the "for" loop here
##        for id, g in enumerate(outlets):
##            c.write({
##                'geometry': mapping(g),
##                'properties': {'id': ids[id]},
##                })


#see https://blog.maptiks.com/spatial-queries-in-python/
def generate_index(records, index_path=None):
    prop = rtree.index.Property()
    if index_path is not None:
        prop.storage = rtree.index.RT_Disk
        prop.overwrite = index_path

    sp_index = rtree.index.Index(index_path, properties=prop)
    for n,g in enumerate(records):
        if g is not None:

            sp_index.insert(int(n), (g.x,g.y,g.x,g.y))
    return sp_index


"""Function for getting accessible outlets, given an accessibility prism"""
def getAccessibleOutlets(prism, sidx,ids, outlets, save=r"C:\Users\schei008\Dropbox\Schriften\Exchange\GOF\results\presoutlets.shp"):
    print "start selecting outlets within prism"      # Define a polygon feature geometry with one attribute

    selection = sidx.intersection(prism.bounds)
    selection = [i for i in selection if outlets[int(i)].within(prism)]
    candidates  = [outlets[int(i)] for i in selection]
    candidateids  = [ids[int(i)] for i in selection]

    #print candidates
    #print candidateids


    schema = {
        'geometry': 'Point',
        'properties': {'id': 'int'},
    }
    # Write a new Shapefile
    with fiona.open(save, 'w', 'ESRI Shapefile', schema) as c:
        ## If there are multiple geometries, put the "for" loop here
        for id, g in enumerate(candidates):
            c.write({
                'geometry': mapping(g),
                'properties': {'id': candidateids[id]},
                })
    return candidates, candidateids


#Turns point list into geopandas data frame
def Polygon2GDF(polygon):
        rt = pd.DataFrame({'polygons': [polygon]})
        outputframe = geopandas.GeoDataFrame(rt, geometry='polygons')['polygons']
        return outputframe


def getActivityLabels(csvfile):
    ls = []
    with open(csvfile, 'rb') as csvfile:
        reader = csv.reader(csvfile, delimiter=',', quotechar='"')
        for row in reader:
         ls.append(row[2].split(':')[0])
    return set(ls)

   # set(['SHOP_GIFT', 'LANDUSE_CONIFEROUSDECIDUOUS', 'SHOP_SUPERMARKET', 'SHOP_HEARINGAIDS', 'POI_EMBASSY', 'TRANSPORT_SUBWAY', 'TOURIST_WINDMILL', 'SHOP_MOTORCYCLE', 'ACCOMMO_CHALET', 'FOOD_PUB', 'EDUCATION_COLLEGE', 'MONEY_EXCHANGE', 'SHOP_BICYCLE', 'SHOP_HAIRDRESSER', 'TOURIST_INFORMATION', 'POI_HAMLET', 'SHOP_TOYS', 'AMENITY_POSTOFFICE', 'SHOP_MUSIC', 'name', 'LANDUSE_ALLOTMENTS', 'TRANSPORT_TERMINAL', 'POI_CRANE', 'SHOP_GARDENCENTRE', 'TOURIST_BEACH', 'TOURIST_CASTLE2', 'FOOD_FASTFOOD', 'AMENITY_PUBLICBUILDING', 'SPORT_BASKETBALL', 'TRANSPORT_FUEL', 'ACCOMMO_CAMPING', 'SPORT_MOTORRACING', 'SHOP_LAUNDRETTE', 'SHOP_PET', 'SPORT_SWIMMING', 'POW_JEWISH', 'SHOP_GREENGROCER', 'SHOP_ALCOHOL', 'SHOP_NEWSPAPER', 'TOURIST_THEMEPARK', 'SPORT_TENNIS', 'AMENITY_PLAYGROUND', 'EDUCATION_NURSERY', 'POI_TOWERLOOKOUT', 'SHOP_COPYSHOP', 'Work', 'ACCOMMO_HOSTEL', 'TOURIST_MONUMENT', 'BARRIER_BLOCKS', 'SPORT_CLIMBING', 'SHOP_CAR', 'POI_TOWN', 'POW_BUDDHIST', 'SHOP_FLORIST', 'HEALTH_PHARMACY', 'SHOP_CONFECTIONERY', 'SHOP_FISH', 'SPORT_SOCCER', 'HEALTH_HOSPITAL', 'Home', 'TOURIST_CINEMA', 'POW_CHRISTIAN', 'SHOP_VENDINGMASCHINE', 'FOOD_CAFE', 'TOURIST_ATTRACTION', 'FOOD_BAR', 'TOURIST_MEMORIAL', 'WATER_TOWER', 'EDUCATION_SCHOOL', 'SHOP_BAKERY', 'TOURIST_FOUNTAIN', 'TOURIST_ART', 'TRANSPORT_STATION', 'SHOP_PHONE', 'MONEY_BANK', 'FOOD_ICECREAM', 'LANDUSE_QUARY', 'ACCOMMO_HOTEL', 'SHOP_COMPUTER', 'AMENITY_FIRESTATION', 'AMENITY_TOWNHALL', 'AMENITY_PRISON', 'TOURIST_ZOO', 'HEALTH_DOCTORS', 'AMENITY_LIBRARY', 'SHOP_BOOK', 'TOURIST_THEATRE', 'SPORT_GYM', 'SHOP_DIY', 'TRANSPORT_RENTALCAR', 'TRANSPORT_BUSSTOP', 'LANDUSE_MILITARY', 'SPORT_LEISURECENTER', 'TOURIST_ARCHAELOGICAL', 'TOURIST_NIGHTCLUB', 'SPORT_ICESKATING', 'Other', 'SHOP_TOBACCO', 'EDUCATION_UNIVERSITY', 'SPORT_BASEBALL', 'POW_ISLAMIC', 'TOURIST_CASTLE', 'SHOP_CONVENIENCE', 'SHOP_MARKETPLACE', 'SHOP_KIOSK', 'SHOP_CARREPAIR', 'SHOP_SHOES', 'AMENITY_POLICE', 'SHOP_CLOTHES', 'SHOP_BUTCHER', 'LANDUSE_GRASS', 'SPORT_SKIINGDOWNHILL', 'TOURIST_MUSEUM', 'POW_HINDU', 'SHOP_HIFI', 'HEALTH_DENTIST', 'FOOD_RESTAURANT', 'SPORT_STADIUM', 'POI_VILLAGE', 'SHOP_JEWELRY', 'SHOP_DEPARTMENTSTORE', 'TRANSPORT_TRAMSTOP', 'AMENITY_COURT', 'SPORT_SKATING'])

foodOutletLabels = ['SHOP_GREENGROCER', 'SHOP_ALCOHOL' ,'SHOP_SUPERMARKET','FOOD_PUB', 'FOOD_FASTFOOD', 'SHOP_CONFECTIONERY', 'SHOP_FISH', 'FOOD_CAFE', 'FOOD_BAR', 'SHOP_BAKERY', 'FOOD_ICECREAM', 'SHOP_TOBACCO','SHOP_CONVENIENCE', 'SHOP_MARKETPLACE', 'SHOP_KIOSK' ,'SHOP_BUTCHER', 'FOOD_RESTAURANT']
#Take the actual eventtime and assume all outlets can be visited within this time
#modifierabletransportevents = [eventime <<< timewindow]

def main():
      #print  getActivityLabels(r"C:\Users\schei008\Dropbox\Schriften\Exchange\GOF\foodtracker\places.csv")
    #Lat 52.088816 | Longitude: 5.095833
    #isoline = getisoline(Point(52.088816,5.095833), 600)
    eventid = 0
    startpoint = Point(5.095833, 52.088816)
    endpoint = Point(5.178099,52.085665)
    starttime = datetime.strptime("2013-07-04T17:00:00",'%Y-%m-%dT%H:%M:%S')
    endtime =   datetime.strptime("2013-07-04T17:50:00",'%Y-%m-%dT%H:%M:%S')

    mineventduration = 1800
    sidx,ids, outlets = loadOutlets()

    getAffordances(eventid, startpoint, starttime, endpoint, endtime, mineventduration, sidx,ids, outlets)







if __name__ == '__main__':
    start_time = time.time()
    main()
    print("--- %s seconds ---" % (time.time() - start_time))

