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
#-------------------------------------------------------------------------------

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

"""Function for computing space-time prism accessibility for a type of (food) event"""
def getAccessibility(starttime, startpoint, endtime, endpoint, mode="car", mineventduration=5):
    print "Start getting accessibility prism"
    #starttime=starttime+datetime.timedelta()

    polystart = transform(project, getisoline(startpoint, 700,mode= mode, starttime=starttime))
    polyend = transform(project, getisoline(endpoint, 700, mode=mode, starttime=endtime)) #De Uithof
    inters = polystart.intersection(polyend)
    #Read from Shapefile
##    fc = fiona.open('test.shp')
##    fc.next()
##    fc.next()
##    feat =fc.next()
##    inters = shape(feat['geometry'])
    prism = inters
    return prism

def getisoline(startpoint, durationseconds, mode="car", starttime="2013-07-04T17:00:00"):   #pedestrian; publicTransport; bicycle
    ruri = "https://isoline.route.api.here.com/routing/7.2/calculateisoline.json?app_id="+myappid+"&app_code="+myappcode+"&mode=shortest;"+mode+";traffic:disabled&start=geo!"+str(startpoint.y)+","+str(startpoint.x)+"&range="+str(durationseconds)+"&rangetype=time&departure="+starttime
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
        print polygon
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
    ruri = "https://matrix.route.api.here.com/routing/7.2/calculatematrix.json?app_id="+myappid+"&app_code="+myappcode+"&summaryAttributes=traveltime&mode=shortest;"+mode+";traffic:disabled&"+od+"0="+str(startpoint.y)+","+str(startpoint.x)
    print "getting routing matrix"
    for count,g in enumerate(outlets):
        g = transform(reproject, g)
        ruri = ruri+"&"+outl+str(count)+"="+str(g.y)+","+str(g.x)
        if count == 9:
            break
    print ruri
    myResponse = requests.get(ruri)
    # For successful API call, response code will be 200 (OK)
    if(myResponse.ok):
        # Loading the response data into a dict variable
        # json.loads takes in only binary or string variables so using content to fetch binary content
        # Loads (Load String) takes a Json file and converts into python data structure (dict or list, depending on JSON)
        jData = json.loads(myResponse.content)
        #print jData
        listofmatrixcells = jData['response']['matrixEntry']
        traveltimes = np.array([[e['summary']['travelTime']] for e in listofmatrixcells] )
        return traveltimes #This is a vector of traveltimes in seconds

    else:
            # If response code is not ok (200), print the resulting http error code with description
            myResponse.raise_for_status()

def getAffordedTrips(ids, vOrigin, vDestination, mineventduration, timemax):
    vsum = (np.add(np.add(vOrigin, vDestination),mineventduration))
    #print vsum
    trips =   [id for ix,id in enumerate(ids) if ix <10 and vsum[ix]<timemax]
    print str(trips) + " trips afforded timewise!"
    return trips


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
def getAccessibleOutlets(prism, outletselectiondata):
    print "start selecting outlets within prism"
    # Define a polygon feature geometry with one attribute
    sidx,ids, outlets = loadOutlets()
##    for i, pt in enumerate(outlets):
##        if pt.within(prism):
##            candidates.append(pt)
##            candidateids.append(ids[i])
    selection = sidx.intersection(prism.bounds)
    selection = [i for i in selection if outlets[int(i)].within(prism)]
    candidates  = [outlets[int(i)] for i in selection]
    candidateids  = [ids[int(i)] for i in selection]

    #print candidates
    #print candidateids


##    schema = {
##        'geometry': 'Point',
##        'properties': {'id': 'int'},
##    }
##    # Write a new Shapefile
##    with fiona.open(outletselectiondata, 'w', 'ESRI Shapefile', schema) as c:
##        ## If there are multiple geometries, put the "for" loop here
##        for id, g in enumerate(candidates):
##            c.write({
##                'geometry': mapping(g),
##                'properties': {'id': candidateids[id]},
##                })
    return candidates, candidateids


#Turns point list into geopandas data frame
def Polygon2GDF(polygon):
        rt = pd.DataFrame({'polygons': [polygon]})
        outputframe = geopandas.GeoDataFrame(rt, geometry='polygons')['polygons']
        return outputframe

def main():
    #Lat 52.088816 | Longitude: 5.095833
    #isoline = getisoline(Point(52.088816,5.095833), 600)
    startpoint = Point(5.095833, 52.088816)
    endpoint = Point(5.178099,52.085665)
    starttime = datetime.strptime("2013-07-04T17:00:00",'%Y-%m-%dT%H:%M:%S')
    endtime =   datetime.strptime("2013-07-04T18:00:00",'%Y-%m-%dT%H:%M:%S')

    mineventduration = 300
    totalduration =  (starttime - endtime).seconds
    print "totalduration :" +str(totalduration)

    prism = getAccessibility(starttime.isoformat(), startpoint, endtime.isoformat(), endpoint)
    candidates, candidateids = getAccessibleOutlets(prism,'selectedoutlets.shp')
    print str(len(candidates))+" outlets pre-selected!"
    v1 = get1TravelMatrix(startpoint, candidates)
    v2 = get1TravelMatrix(endpoint, candidates, inverse=True)
    trips = getAffordedTrips(candidateids,v1,v2, mineventduration, totalduration)






if __name__ == '__main__':
    main()
