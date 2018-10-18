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
from shapely.wkt import loads
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



"""Functions for computing space-time outlet accessibility within a prism defined by a flexible event"""

project = lambda x, y: pyproj.transform(pyproj.Proj(init='EPSG:4326'), pyproj.Proj(init='EPSG:28992'), x, y)
reproject =  lambda x, y: pyproj.transform(pyproj.Proj(init='EPSG:28992'), pyproj.Proj(init='EPSG:4326'), x, y)


"""Main Function for computing space-time prism based outlet accessibility for a flexible event"""
def getAffordances(user,eventid, startpoint, starttime, mode1, endpoint, endtime, mode2, mineventduration, sidx,ids, outlets):
    print 'Finding afforded outlets for event ' +str(eventid)
    totalduration =  (endtime - starttime).total_seconds()
    print "totalduration :" +str(totalduration)
    newpath =os.path.join(results,user)
    if not os.path.exists(newpath):
        os.makedirs(newpath)
    prism = getPrism(starttime.isoformat(),startpoint, endtime.isoformat(), endpoint, totalduration, mineventduration, mode1=convertMode(mode1), mode2=convertMode(mode2), save=os.path.join(newpath,str(eventid)+"prism.shp"))
    if prism.is_empty:
        print 'prism empty!!! continue without'
        return
    candidates, candidateids = getPrismOutlets(prism, sidx,ids, outlets, save=os.path.join(newpath,str(eventid)+"preso.shp"))
    print str(len(candidates))+" outlets pre-selected!"
    v1 = get1TravelMatrix(startpoint, starttime.isoformat(), candidates, mode=convertMode(mode1))
    v2 = get1TravelMatrix(endpoint, endtime.isoformat(), candidates, mode=convertMode(mode2), inverse=True)
    trips = getAffordedTrips(candidateids, candidates,v1,v2, mineventduration, totalduration)
    saveOutlets(trips,save=os.path.join(newpath,str(eventid)+"afo.shp"))

def convertMode(mode):
    if mode == "Foot" or mode == "Bike" or 'unknown':
        return 'pedestrian'
    elif mode == 'Car' or mode=='Train':
        return'car'


def getPrism(starttime,startpoint, endtime, endpoint, timewindow, mineventduration=300, mode1="car", mode2="car", save=r"C:\Users\schei008\Dropbox\Schriften\Exchange\GOF\results\prism.shp"):
    print "Start getting accessibility prism"
    #starttime=starttime+datetime.timedelta()
    availabletime = timewindow-mineventduration-300 #5 minutes minimum to get to the destination
    print "maxtraveltime: " +str(availabletime)
    print "for "+ mode1 + " and for " +mode2
    polystart = transform(project, getisoline(startpoint,availabletime, mode= mode1, starttime=starttime))
    polyend = transform(project, getisoline(endpoint, availabletime, mode=mode2, starttime=endtime)) #De Uithof
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

"""Function for getting outlet candidates within a space time prism (an spatial intersection of traveltime isolines)"""
def getPrismOutlets(prism, sidx,ids, outlets, save=r"C:\Users\schei008\Dropbox\Schriften\Exchange\GOF\results\presoutlets.shp"):
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


"""Computes a complete time vector for traveling from an origin to all outlet  candidates"""
def get1TravelMatrix(startpoint, starttime, outlets, mode="car", inverse=False):
    if inverse:  #computes traveltimes to startpoint starting from outlets instead
        od = 'destination'
        outl = 'start'
    else:
        od = 'start'
        outl = 'destination'
    ruri0 = "https://matrix.route.api.here.com/routing/7.2/calculatematrix.json?app_id="+myappid+"&app_code="+myappcode+"&summaryAttributes=traveltime&mode=shortest;"+mode+";traffic:disabled&"+od+"0="+str(startpoint.y)+","+str(startpoint.x)+"&departure="+starttime
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
    print str(np.count_nonzero(traveltimes == 999999999))+" were API failures!"
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

"""Selects all afforded trips from an origin via some candidate outlet to a destination taking into account eventtimes"""
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
    print 'Loading outlets!'
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



#-----------------------------------------------------------------------------------------

"""Functions for generating and handling trip events"""

class FlexEvent():
    def __init__(self, user, mod1, st1, sp1, pt1, pp1, mod2, st2, pt2, pp2):
         self.user = user
         self.mod1 =mod1
         self.st1 = st1
         self.sp1= sp1
         self.pt1 =pt1
         self.pp1 =pp1
         self.mod2 =mod2
         self.st2 = st2
         self.pt2 =pt2
         self.pp2 =pp2
         self.eventduration = (self.st2 -  self.pt1 ).total_seconds()
         self.category = (self.pp1['label']).split(':')[0]

    def serialize(self):
        return {
         'user':str(self.user),
         'trip1': {'mod1':str(self.mod1),
         'starttime1':str(self.st1),
         'startplace1': {'label':self.sp1['label'], 'geo':str(self.sp1['geo'])},
         'stoptime1':str(self.pt1),
         'stopplace1':{'label':self.pp1['label'], 'geo':str(self.pp1['geo'])}} ,
          'trip2': {
         'mod2':self.mod2,
         'starttime2':str(self.st2),
         'stoptime2':str(self.pt2),
         'stopplace2':{'label':self.pp2['label'], 'geo':str(self.pp2['geo'])}},
         'eventduration':str(self.eventduration),
         'category':str(self.category)
        }
    def map(self, id):
        newpath=os.path.join(results,str(self.user))
        if not os.path.exists(newpath):
            os.makedirs(newpath)

        save = os.path.join(newpath,str(id)+".shp" )
        schema = {
            'geometry': 'Point',
            'properties': { 'label':'str'},
            }

        # Write a new Shapefile
        with fiona.open(save, 'w', 'ESRI Shapefile', schema) as c:
            ## If there are multiple geometries, put the "for" loop here
                    c.write({
                        'geometry': mapping(transform(project,self.sp1['geo'])),
                        'properties': {'label':self.sp1['label']},
                        })
                    c.write({
                        'geometry': mapping(transform(project,self.pp1['geo'])),
                        'properties': {'label':self.pp1['label']},
                        })
                    c.write({
                        'geometry': mapping(transform(project,self.pp2['geo'])),
                        'properties': {'label':self.pp2['label']},
                        })
        c.close




"""Function for constructing fixed and flexible (food) events from a collection of trips"""
def constructEvents(trips, places, sidx,ids, outlets):
    for t in trips:
        track = t[1]
        user = str(t[0])
        print user
        userplaces = places[user]
        activityMap(user, userplaces)
        store = os.path.join(results,str(user)+"events.json")
        lastrow = pd.Series()
        dump = {}
        eventnr = 0
        for index, row in track.iterrows():
            if not lastrow.empty:
                mod1, st1, sp1, pt1, pp1 =  getTripInfo(lastrow)
                mod2, st2, sp2, pt2, pp2 =  getTripInfo(row)
                if flexibleEvent(userplaces,mod1, st1, sp1, pt1, pp1, mod2, st2, sp2, pt2, pp2):
                      fe = FlexEvent(user,mod1, st1, userplaces[sp1], pt1, userplaces[pp1], mod2, st2, pt2, userplaces[pp2])
                      eventnr +=1
                      fe.map(eventnr)
                      dump[eventnr]=fe.serialize()
                      getAffordances(user, eventnr, fe.sp1['geo'], fe.st1, fe.mod1, fe.pp2['geo'], fe.pt2, fe.mod2, int(float(fe.eventduration)), sidx,ids, outlets)
                      break
            lastrow  =row
        print str(len(dump.keys()))+' flexible events detected for user ' + str(user)
        with open(store, 'w') as fp:
            json.dump(dump, fp)
        fp.close
        break

def activityMap(user, places):
    save=os.path.join(results,str(user)+"places.shp")
    schema = {
        'geometry': 'Point',
        'properties': {'id': 'int', 'label':'str'},
        }

    # Write a new Shapefile
    with fiona.open(save, 'w', 'ESRI Shapefile', schema) as c:
        ## If there are multiple geometries, put the "for" loop here
            for place in places.keys():
                c.write({
                    'geometry': mapping(transform(project,places[place]['geo'])),
                    'properties': {'id': place, 'label':places[place]['label']},
                    })
    c.close



def flexibleEvent(userplaces,mod1, st1, sp1, pt1, pp1, mod2, st2, sp2, pt2, pp2):
    maxeventduration = (st2 -  pt1 ).total_seconds()
    if sp1 in userplaces.keys() and pp1 in userplaces.keys() and sp2 in userplaces.keys() and pp2 in userplaces.keys():
        category = (userplaces[pp1]['label']).split(':')[0]
        return  pp1 == sp2 and maxeventduration < 2*3600 and category in foodOutletLabels
    else:
        return False

def getTripInfo(row):
    return row['modality'],dateparse(row['startTime']), cn(row['startPlaceId']), dateparse(row['stopTime']),cn(row['stopPlaceId'])

def cn(n):
    if str(n) != 'nan':
        return str(int(n))
    else:
        return None

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

def loadPlaces(places):
    ls = {}
    with open(places, 'rb') as csvfile:
        reader = csv.reader(csvfile, delimiter=',', quotechar='"')
        next(reader) #First line skipped
        for row in reader:
            user = row[1]
            place = row[0]
            if user not in  ls.keys():
                ls[user]={place:{'label':row[2], 'geo': loads(row[4])}}

            else:
                ls[user][place] = {'label':row[2], 'geo': loads(row[4])}

    csvfile.close
    #print ls
    return ls

def dateparse (timestamp):
        return pd.datetime.strptime(timestamp, '%Y-%m-%d %H:%M:%S.%f')

def loadTrips(trips):
    #headers = ['deviceId','modality','distance','startTime','stopTime','startCountry','startPc','startCity','startStreet','stopCountry','stopPc','stopCity','stopStreet','startPlaceId','stopPlaceId']
    #dtypes = [str, str, int, datetime, datetime, str, str, str, str,str,str,str,str,int,int]

    #dateCols = ['startTime','stopTime']
    tr = pd.read_csv(trips, sep=',', parse_dates=True, date_parser=dateparse)
    #tr = pd.read_csv(trips)
    tr = list(tr.groupby('deviceId'))
    print 'number of users loaded: '+ str(len(tr))
    return tr


results = r"C:\Temp\FoodResults"
def main():
      #print  getActivityLabels(r"C:\Users\schei008\Dropbox\Schriften\Exchange\GOF\foodtracker\places.csv")
    sidx,ids, outlets = loadOutlets()
    places =r"C:\Users\schei008\Dropbox\Schriften\Exchange\GOF\foodtracker\places.csv"
    trips = r"C:\Users\schei008\Dropbox\Schriften\Exchange\GOF\foodtracker\trips.csv"

    pl = loadPlaces(places)
    tr = loadTrips(trips)
    constructEvents(tr,pl,sidx,ids, outlets)







    #Lat 52.088816 | Longitude: 5.095833
    #isoline = getisoline(Point(52.088816,5.095833), 600)
##    eventid = 0
##    startpoint = Point(5.095833, 52.088816)
##    endpoint = Point(5.178099,52.085665)
##    starttime = datetime.strptime("2013-07-04T17:00:00",'%Y-%m-%dT%H:%M:%S')
##    endtime =   datetime.strptime("2013-07-04T17:50:00",'%Y-%m-%dT%H:%M:%S')
##
##    mineventduration = 1800
##
##
##    getAffordances(eventid, startpoint, starttime, endpoint, endtime, mineventduration, sidx,ids, outlets)







if __name__ == '__main__':
    start_time = time.time()
    main()
    print("--- %s seconds ---" % (time.time() - start_time))

