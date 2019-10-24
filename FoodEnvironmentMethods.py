#-------------------------------------------------------------------------------
# Name:        Methods for capturing the food environment of tracks in terms of
#               accessible (afforded) food outlets.   This includes identifying
#               fixed and flexible (food) events in a track, as well as calculating
#               space-time prisms over a network to capture affordance space.
# Purpose:       In order to assess the food environment from an affordance perspective
#
# Author:      Simon Scheider
#
# Created:     01/11/2018
# Copyright:   (c) Simon Scheider 2018
# Licence:     MIT license
#-----------------------------------------------------------------------------
import csv, sys
import glob
import time
import requests
import random
myappid   = 'omN8lWe0pRNExedt6Gh2'
myappcode = 'bS_F57D8weI6ZNzEYJ_UmQ'
import json
import shapely
from shapely import geometry
from shapely.geometry import shape, Point, mapping, Polygon, MultiLineString, LineString
from shapely.wkt import loads
import fiona
import geopandas
from geopandas.tools import sjoin
import pandas as pd
import numpy as np

from datetime import  date, datetime, timedelta

import pyproj
#see https://github.com/jswhit/pyproj
from shapely.ops import transform
import rtree
from xlrd import open_workbook
import os


#--------------------------------------------------------------------------------------------------

"""Functions for computing space-time outlet accessibility within a prism defined by a flexible event"""

project = lambda x, y: pyproj.transform(pyproj.Proj(init='EPSG:4326'), pyproj.Proj(init='EPSG:28992'), x, y)
reproject =  lambda x, y: pyproj.transform(pyproj.Proj(init='EPSG:28992'), pyproj.Proj(init='EPSG:4326'), x, y)


"""Main Function for computing space-time prism based outlet accessibility for a flexible event"""
def getAffordances(user,eventid, startpoint, starttime, mode1, endpoint, endtime, mode2, mineventduration, sidx,ids, outlets, cat):
    print 'Finding afforded outlets for event ' +str(eventid)
    totalduration =  (endtime - starttime).total_seconds()
    traveltime = totalduration-mineventduration
    if traveltime > 0:
        traveltime1 =  traveltime/2
        traveltime2 =  traveltime/2
        print "totalduration :" +str(totalduration)
        print 'eventduration : '+str(mineventduration)
        print "modes: "+mode1 +' and '+mode2
        if mode1 =='Bike':
            print 'bike modeled by 3 times foot!'
            traveltime1  = ((traveltime1)*3)  #In order to compensate for missing bike mode we use the pedestrian mode and give it 4  times more time
        elif mode1 =='Car':
            traveltime1 = ((traveltime1)*1)  #This compensates for underestimating speed in the network?
        elif mode1 =='Train':
            traveltime1 = ((traveltime1)*1.2)
        if mode2 =='Bike':
            traveltime2 = ((traveltime2)*3)  #In order to compensate for missing bike mode we use the pedestrian mode and give it 4  times more time
            print 'bike modeled by 3 times foot!'
        elif mode2 =='Car':
            traveltime2 = ((traveltime2)*1)
        elif mode2 =='Train':
            traveltime2 = ((traveltime2)*1.2)
        totalduration = mineventduration +  traveltime1 + traveltime2
        mode1=convertMode(mode1)          #This is needed because there are only car and predestrian modes available
        mode2=convertMode(mode2)
        newpath =os.path.join(results,user)
        if not os.path.exists(newpath):
            os.makedirs(newpath)

        print "mode1 = "+mode1
        print "mode2 = "+mode2
        prism = getPrism(starttime.isoformat(),startpoint, endtime.isoformat(), endpoint, totalduration, mineventduration, mode1=mode1, mode2=mode2, save=os.path.join(newpath,str(eventid)+"prism.shp"))
        if prism.is_empty:
            print 'prism empty!!! continue without'
            return
        candidates, candidateids, candidatecats = getPrismOutlets(prism, sidx,ids, outlets, cat, save=os.path.join(newpath,str(eventid)+"preso.shp"))
        cansize = len(candidates)
        print str(cansize)+" outlets pre-selected!"
        if cansize > 2000:
            print "randomsample 2000"
            can = list(enumerate(candidates))
            sample = random.sample(can,k=2000)
            canix = [idx for idx, val in sample]
            candidates = [val for idx, val in sample]
            canids = [candidateids[idx] for idx in canix]
            candidateids = canids
            cancat = [candidatecats[idx] for idx in canix]
            candidatecats = cancat
        if len(candidates) >0:
            print "Get travel matrix v1: "+str(startpoint), starttime.isoformat(), mode1
            v1 = get1TravelMatrix(startpoint, starttime.isoformat(), candidates, mode=mode1)
            print "Get travel matrix v2 inverse: "+str(endpoint), endtime.isoformat(), mode2
            v2 = get1TravelMatrix(endpoint, endtime.isoformat(), candidates, mode=mode2, inverse=True)
            trips = getAffordedTrips(candidateids, candidates, candidatecats,v1,v2, mineventduration, totalduration)
            saveOutlets(trips,save=os.path.join(newpath,str(eventid)+"afo.shp"))
        else:
            "no cancdidates found within prism!"
    else:
        print 'no time left!'

def convertMode(mode):
    if mode == "Foot" or mode == "Bike" or mode =='unknown':
        return 'pedestrian'
    elif mode == 'Car' or mode=='Train' or mode == 'BusTram':
        return 'car'


def getPrism(starttime,startpoint, endtime, endpoint, timewindow, mineventduration=300, mode1="car", mode2="car", save=r"C:\Users\schei008\Dropbox\Schriften\Exchange\GOF\results\prism.shp"):
    print "Start getting accessibility prism"
    #starttime=starttime+datetime.timedelta()
    availabletime = timewindow-mineventduration #1 minute minimum to get to the destination
    #print "maxtraveltime: " +str(availabletime)
    #print "for "+ mode1 + " and for " +mode2
    polystart = transform(project, getisoline(startpoint,availabletime, mode= mode1, starttime=starttime))
    polyend = transform(project, getisoline(endpoint, availabletime, mode=mode2, starttime=endtime)) #De Uithof
    if polystart.is_empty or polyend.is_empty:
        print "polygon empty!"
    inters = polystart.intersection(polyend)
    #schema = {
    #    'geometry': 'Polygon',
    #    'properties': {'id': 'int'},
    #    }

    # Write a new Shapefile
    #with fiona.open(save, 'w', 'ESRI Shapefile', schema) as c:
    #    ## If there are multiple geometries, put the "for" loop here
    #        c.write({
    #            'geometry': mapping(inters),
    #            'properties': {'id': 0},
    #            })

    #c.close
    prism = inters
    #print prism
    return prism

def getisoline(startpoint, durationseconds, mode="car", starttime="2013-07-04T17:00:00"):   #pedestrian; publicTransport; bicycle
    ruri = "https://isoline.route.api.here.com/routing/7.2/calculateisoline.json?app_id="+myappid+"&app_code="+myappcode+"&mode=fastest;"+mode+";traffic:disabled&start=geo!"+str(startpoint.y)+","+str(startpoint.x)+"&range="+str(int(durationseconds))+"&rangetype=time&departure="+starttime+"&quality=2"
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
def getPrismOutlets(prism, sidx,ids, outlets, cat, save=r"C:\Users\schei008\Dropbox\Schriften\Exchange\GOF\results\presoutlets.shp"):
    print "start selecting outlets within prism"      # Define a polygon feature geometry with one attribute

    selection = sidx.intersection(prism.bounds)
    selection = [i for i in selection if outlets[int(i)].within(prism)]
    candidates  = [outlets[int(i)] for i in selection]
    candidateids  = [ids[int(i)] for i in selection]
    cats =   [cat[int(i)] for i in selection]
    #print candidates
    #print candidateids

##    schema = {
##        'geometry': 'Point',
##        'properties': {'id': 'int'},
##    }
##    # Write a new Shapefile
##    with fiona.open(save, 'w', 'ESRI Shapefile', schema) as c:
##        ## If there are multiple geometries, put the "for" loop here
##        for id, g in enumerate(candidates):
##            c.write({
##                'geometry': mapping(g),
##                'properties': {'id': candidateids[id]},
##                })
    return candidates, candidateids, cats


"""Computes a complete time vector for traveling from an origin to all outlet  candidates"""
def get1TravelMatrix(startpoint, starttime, outlets, mode="car", inverse=False):
    if inverse:  #computes traveltimes to startpoint starting from outlets instead
        od = 'destination'
        outl = 'start'
    else:
        od = 'start'
        outl = 'destination'
    ruri0 = "https://matrix.route.api.here.com/routing/7.2/calculatematrix.json?app_id="+myappid+"&app_code="+myappcode+"&summaryAttributes=traveltime&mode=fastest;"+mode+";traffic:disabled&"+od+"0="+str(startpoint.y)+","+str(startpoint.x)+"&departure="+starttime
    print "getting routing matrix"
    traveltimes = np.array([])
    c =0
    ruri = ruri0
    print "... fire matrix requests!"
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
    if c != 0 :
        r = fireTTrequest(ruri)
    if r.any():
        traveltimes = np.append(traveltimes,r)
    print str(traveltimes.size)+" outlet distances computed!"
    print str(np.count_nonzero(traveltimes == 999999999))+" were API failures!"
    return traveltimes

def fireTTrequest(ruri):
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
def getAffordedTrips(ids, outlets, cat, vOrigin, vDestination, mineventduration, timemax):
    vsum = (np.add(np.add(vOrigin, vDestination),mineventduration))
    #print vsum
    trips =   [(id, outlets[ix], cat[ix]) for ix,id in enumerate(ids) if vsum[ix]<=timemax]
    print str(len(trips)) + " trips afforded timewise!"
    return trips

def saveOutlets(trips, save=r"C:\Users\schei008\Dropbox\Schriften\Exchange\GOF\results\accoutlets.shp"):
    schema = {
        'geometry': 'Point',
        'properties': {'id': 'int', 'label':'str'},
        }

    # Write a new Shapefile
    with fiona.open(save, 'w', 'ESRI Shapefile', schema) as c:
        with open(os.path.splitext(save)[0]+'.csv', 'wb') as csvfile:
            writer = csv.writer(csvfile, delimiter=',', quotechar='"', quoting=csv.QUOTE_MINIMAL)
        ## If there are multiple geometries, put the "for" loop here
            for i in trips:
                writer.writerow([i[0], i[1], (i[2]).encode('utf-8')])
                c.write({
                    'geometry': mapping(i[1]),
                    'properties': {'id': str(int(i[0])), 'label': (i[2]).encode('utf-8')},
                    })
    c.close
    csvfile.close




#-----------------------------------------------------------------------------------------

"""Functions for generating and handling modifiable food events"""

###This class captures modifiable food events consisting of: travel - food activity - travel
##class FlexEvent():
##    def __init__(self, user, category, mod1, st1, sp1, pt1, pp1, mod2, st2, pt2, pp2, constructiontype = 'RecEvent'):
##         self.user = user
##         self.mod1 =mod1
##         self.st1 = st1
##         self.sp1= sp1
##         self.pt1 =pt1
##         self.pp1 =pp1
##         self.mod2 =mod2
##         self.st2 = st2
##         self.pt2 =pt2
##         self.pp2 =pp2
##         self.eventduration = (self.st2 -  self.pt1 ).total_seconds()
##         self.category = category #(self.pp1['label']).split(':')[0]
##         self.constype = constructiontype
##         print "Event: "+str(constructiontype)+" "+str(st1) +" "+ str(pt1) +" "+  str(st2)  +" "+ str(pt2)
##
##    def serialize(self):
##        return {
##         'user':str(self.user),
##         'trip1': {'mod1':str(self.mod1),
##         'starttime1':str(self.st1),
##         'startplace1': {'label':self.sp1['label'], 'geo':str(self.sp1['geo'])},
##         'stoptime1':str(self.pt1),
##         'stopplace1':{'label':self.pp1['label'], 'geo':str(self.pp1['geo'])}} ,
##          'trip2': {
##         'mod2':self.mod2,
##         'starttime2':str(self.st2),
##         'stoptime2':str(self.pt2),
##         'stopplace2':{'label':self.pp2['label'], 'geo':str(self.pp2['geo'])}},
##         'eventduration':str(self.eventduration),
##         'category':self.category,#).encode('utf-8').strip(),
##         'constype': self.constype#).encode('utf-8').strip()
##        }
##    def map(self, id):
##        newpath=os.path.join(results,str(self.user))
##        if not os.path.exists(newpath):
##            os.makedirs(newpath)
##
##        save = os.path.join(newpath,str(id)+".shp" )
##        schema = {
##            'geometry': 'Point',
##            'properties': { 'label':'str'},
##            }
##
##        # Write a new Shapefile
##        with fiona.open(save, 'w', 'ESRI Shapefile', schema) as c:
##            ## If there are multiple geometries, put the "for" loop here
##                    c.write({
##                        'geometry': mapping(transform(project,self.sp1['geo'])),
##                        'properties': {'label':self.sp1['label']},
##                        })
##                    c.write({
##                        'geometry': mapping(transform(project,self.pp1['geo'])),
##                        'properties': {'label':self.pp1['label']},
##                        })
##                    c.write({
##                        'geometry': mapping(transform(project,self.pp2['geo'])),
##                        'properties': {'label':self.pp2['label']},
##                        })
##        c.close

#This class is more tolerant and captures also single trip events (without goal activity)
class FlexTrip():
    def __init__(self, user, mod1, st1, sp1, pt1, pp1):
         self.user = user
         self.mod1 =mod1
         self.st1 = st1
         self.sp1= sp1
         self.pt1 =pt1
         self.pp1 =pp1
         self.eventduration = (self.st1 -  self.pt1 ).total_seconds()
         #self.category = (self.pp1['label']).split(':')[0]

    def serialize(self):
        return {
         'user':str(self.user),
         'trip1': {'mod1':str(self.mod1),
         'starttime1':str(self.st1),
         'startplace1': {'label':self.sp1['label'], 'geo':str(self.sp1['geo'])},
         'stoptime1':str(self.pt1),
         'stopplace1':{'label':self.pp1['label'], 'geo':str(self.pp1['geo'])}} ,
         'eventduration':str(self.eventduration)
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

        c.close




##"""Function for constructing fixed and flexible (food) events from a collection of trips"""
##def constructEvents(trips, places, outletdata, tripeventsOn):
##    for t in trips:
##        print t
##        track = t
##        user = str(t['deviceId'].iloc[0])
##        print user
##        userplaces = places[user]
##        #generating simple methods first:
##        activitySpace(user,userplaces,track, outletdata)
##        homeBuffer(user,userplaces, outletdata,'Bike')
##        activityMap(user, userplaces)
##        store = os.path.join(results,str(user)+"events.json")
##        lastrow = pd.Series()
##        dump = {}
##        eventnr = 0
##        print str(len(track))+ ' trips for this user in total!'
##        for index, row in track.iterrows():
##            if not lastrow.empty:
##                mod1, st1, sp1, pt1, pp1 =  getTripInfo(lastrow)
##                mod2, st2, sp2, pt2, pp2 =  getTripInfo(row)
##                category = (userplaces[pp1]['label']).split(':')[0]
##                if flexibleEvent(userplaces,mod1, st1, sp1, pt1, pp1, mod2, st2, sp2, pt2, pp2):
##                      fe = FlexEvent(user,category, mod1, st1, userplaces[sp1], pt1, userplaces[pp1], mod2, st2, pt2, userplaces[pp2])
##                      if category.split('_')[0]== 'FOOD': #Horeca outlets
##                        sidx,ids, outlets, cat = outletdata[0],outletdata[1],outletdata[2],outletdata[3]
##                        print 'simulated HORECA event'
##                      else:                                 #Shop outlets
##                        sidx,ids, outlets,cat = outletdata[4],outletdata[5],outletdata[6],outletdata[7]
##                        print 'simulated SHOP event'
##                      eventnr +=1
##                      fe.map(eventnr)
##                      dump[eventnr]=fe.serialize()
##                      getAffordances(user, eventnr, fe.sp1['geo'], fe.st1, fe.mod1, fe.pp2['geo'], fe.pt2, fe.mod2, int(float(fe.eventduration)), sidx,ids, outlets, cat)
##                elif tripeventsOn and flexibleTripEvent(userplaces,mod1, st1, sp1, pt1+timedelta(seconds=600), pp1, 600): #simulated Shop event within a single trip: 10 minutes, assuming 10 minutes more time
##                    fe = FlexTrip(user,mod1, st1, userplaces[sp1], pt1+timedelta(seconds=600), userplaces[pp1])
##                    sidx,ids, outlets,cat = outletdata[4],outletdata[5],outletdata[6],outletdata[7]
##                    print 'simulated SHOP trip'
##                    eventnr +=1
##                    fe.map(eventnr)
##                    dump[eventnr]=fe.serialize()
##                    getAffordances(user, eventnr, fe.sp1['geo'], fe.st1, fe.mod1, fe.pp1['geo'], fe.pt1, fe.mod1, 600, sidx,ids, outlets, cat)
##                elif tripeventsOn and flexibleTripEvent(userplaces,mod1, st1, sp1, pt1+timedelta(seconds=600), pp1, 1200): #simulated HORECA event within a single trip: 20 minutes, assuming 10 minutes more time
##                    fe = FlexTrip(user,mod1, st1, userplaces[sp1], pt1+timedelta(seconds=600), userplaces[pp1])
##                    sidx,ids, outlets, cat = outletdata[0],outletdata[1],outletdata[2],outletdata[3]
##                    print 'simulated HORECA trip'
##                    eventnr +=1
##                    fe.map(eventnr)
##                    dump[eventnr]=fe.serialize()
##                    getAffordances(user, eventnr, fe.sp1['geo'], fe.st1, fe.mod1, fe.pp1['geo'], fe.pt1, fe.mod1, 1200, sidx,ids, outlets, cat)
##                else:
##                    print "not a flexible event!"
##            lastrow  =row
##
##        print str(len(dump.keys()))+' flexible events detected for user ' + str(user)
##        with open(store, 'w') as fp:
##            json.dump(dump, fp)
##        fp.close

##def flexibleEvent(userplaces,mod1, st1, sp1, pt1, pp1, mod2, st2, sp2, pt2, pp2):
##    maxeventduration = (st2 -  pt1 ).total_seconds()
##    if sp1 in userplaces.keys() and pp1 in userplaces.keys() and sp2 in userplaces.keys() and pp2 in userplaces.keys(): #Places available in place set?
##        if  pp1 == sp2:
##            if  maxeventduration < 2*3600:
##                category = (userplaces[pp1]['label']).split(':')[0]
##                if category in foodOutletLabels:
##                    if mod1 != "":
##                        return True
##                    else:
##                        print 'modus 1 not available'
##                        return False
##                else:
##                    print 'place category not in foodlabels'
##                    return False
##            else:
##                print 'beyond maxeventduration'
##                return False
##        else:
##            print 'stopplace 1 != startplace 2'
##            return False
##    else:
##        print 'place not in userplaces!'
##        return False


"""This function checks whether recorded event is between two consecutive framing trips based on  time"""
def checkRecEvent(userplaces, mod1, sp1, pt1, pp1, pos, start, end, mod2, st2, pp2):
    maxeventduration = (st2 -  pt1 ).total_seconds()
    eventduration = (end - start).total_seconds()
    out = False
    if sp1 in userplaces.keys() and pp2 in userplaces.keys() : #Places available in place set?
        if (pt1-timedelta(seconds=300) <= start <=end<= st2+timedelta(seconds=300) ): #Event within stoppingtime, allowing for a five minutes tolerance interval?
            #if mod1 == mod2:
                if eventduration*4>=maxeventduration: #Stoppingtime not too large for eventime (excluding e.g. overnight stops)
                    #print 'event duration: '+str(eventduration)
                    #print 'max event duration: '+str(maxeventduration)
                        #ep = transform(project,loads(pos))
                        #tp1 = transform(project,userplaces[pp1]['geo'])
                        #tp2 = transform(project,userplaces[sp2]['geo'])
                        #if ep.distance(tp1) < 500 or ep.distance(tp2)<=500 : #Test whether stopplaces and eventplace is within 500 meters
                        print "Checking rec event successful!"
                        out = True

    return out
                    #print "distance 1:" +str(ep.distance(tp1))

"""This function checks whether recorded event is between two consecutive trips which are not framing the event (might belong to other events), and thus might only border the trip to the event (not recorded)"""
def checkRecBorderEvent(userplaces, mod1, pt1, pp1, pos, start, end, mod2, st2, sp2):
    maxeventduration = (st2 -  pt1 ).total_seconds()
    eventduration = (end - start).total_seconds()
    out = False
    if pp1 in userplaces.keys() and sp2 in userplaces.keys() : #Places available in place set?
        if (pt1 <= start <=end<= st2): #Event within stoppingtime?
            #borderint1 = (start -  pt1).total_seconds()
            #borderint2 =  (st2 - end).total_seconds()
            #if mod1 == mod2:
            print "Checking rec border event successful!"
            print pt1, start, end, st2
            out = True
    return out

def checkWithinTripEvent(userplaces, mod1, st1, sp1, start, end, pt1, pp1):
    out = False
    if sp1 in userplaces.keys() and pp1 in userplaces.keys() : #Places available in place set?
        if (st1 <= start <=end<= pt1): #Event within stoppingtime?
            print "Checking Within trip event successful!"
            print mod1, st1, sp1, start, end, pt1, pp1
            out = True
    return out


#Handle recorded events
def constructRecordedEvents(trips,places,outletdata,recordedevents, overwrite = False):
    userswithresults = []
    for index, evs in enumerate(recordedevents):
        #print evs
        user = str(int(evs['DEVICECODE'].iloc[0]))
        print user
        userplaces = places[user]
        #generating simple methods first:
        store = os.path.join(results,str(user)+"Recevents.json")
        #Prevent overvwriting results in case overwrite is false
        goon = True
        if not overwrite:
            goon = False
            try:
                exdata = json.load(open(store, 'r'))
            except IOError:
                goon = True
        t = trips[user]
        if goon:
            activitySpace(user,userplaces,t, outletdata)
            homeBuffer(user,userplaces, outletdata,'Bike')
            activityMap(user, userplaces)
        if t.empty:
            print "User "+str(user)+" does not have any trips! Break!"
        else:
            print str(t['deviceId'].iloc[0]) ==user
            dump = {}
            eventnr = 0
            print str(len(evs))+ ' recorded food events for this user in total!'
            dump['norecevs']=str(len(evs))
            for index, row in evs.iterrows():
                category = row['type of outlet of purchase']
                if category != np.nan:
                    #if row['LOCATIE'].split(';')[0] != '999':
                        if not isinstance(category,basestring):
                            category = str(category)
                        category = category.encode('utf-8').strip()
                        print category
                        if category== 'Supermarkt': #Shop outlets
                                        sidx,ids, outlets,cat = outletdata[4],outletdata[5],outletdata[6],outletdata[7]
                                        print 'SHOP  event'
                        else:               #Horeca outlets
                                        sidx,ids, outlets, cat = outletdata[0],outletdata[1],outletdata[2],outletdata[3]
                                        print 'HORECA event'

                        purchaseloc = False
                        if isinstance(row['LOCATIE'],basestring)  and row['LOCATIE']!= '999' and ';' in row['LOCATIE']:
                            pos = row['LOCATIE'].split(';')[0]
                            label =row['LOCATIE'].split(';')[1]
                            poss = {'geo':loads(pos), 'label':label}
                            purchaseloc = True

                        start =dateparse2(row['Start date'])
                        end = dateparse2(row['End date'])
                        eventduration = (end - start).total_seconds()
                        print category,start,end
                        lastrow = pd.Series()
                        #print t.iloc[0]
                        for index,row in t.iterrows():
                            if not lastrow.empty:
                                mod1, st1, sp1, pt1, pp1 =  getTripInfo(lastrow)
                                mod2, st2, sp2, pt2, pp2 =  getTripInfo(row)
                                #print lastrow
                                if not purchaseloc and pp1 in userplaces.keys(): #If location of purchase is not available
                                    poss = userplaces[pp1]
                                    pos = userplaces[pp1]['geo'].wkt
                                if checkRecEvent(userplaces, mod1, sp1, pt1, pp1, pos, start, end, mod2, st2, pp2):
                                    fe = FlexEvent(user,category,mod1, st1, userplaces[sp1], pt1, poss, mod2, st2, pt2, userplaces[pp2], constructiontype = 'RecEvent')
                                    eventnr +=1
                                    dump[eventnr]=fe.serialize()
                                    if not goon:
                                        if str(eventnr) in exdata.keys():
                                            break
                                        else:
                                            goon = True
                                    fe.map(eventnr)
                                    getAffordances(user, eventnr, userplaces[sp1]['geo'], st1, mod1, userplaces[pp2]['geo'], pt2, mod2, int(float(eventduration)), sidx,ids, outlets, cat)
                                elif checkWithinTripEvent(userplaces, mod1, st1, sp1, start, end, pt1, pp1):
                                    fe = FlexEvent(user,category,mod1, st1, userplaces[sp1], start, poss, mod1, end, pt1, userplaces[pp1], constructiontype = 'WithinTripEvent')
                                    eventnr +=1
                                    dump[eventnr]=fe.serialize()
                                    if not goon:
                                        if str(eventnr) in exdata.keys():
                                            break
                                        else:
                                            goon = True
                                    fe.map(eventnr)
                                    getAffordances(user, eventnr, userplaces[sp1]['geo'], st1-timedelta(seconds=30), mod1, userplaces[pp1]['geo'], pt1+timedelta(seconds=30), mod1, int(float(eventduration)), sidx,ids, outlets, cat)
                                    #adding a small (1 minute) time tolerance for stopping and purchasing something on the way
                                    break
                                elif checkRecBorderEvent(userplaces, mod1, pt1, pp1, pos, start, end, mod2, st2, sp2, ):
                                    fe = FlexEvent(user,category,mod1, start-timedelta(seconds=1800), userplaces[pp1], start, poss, mod2, end, end+timedelta(seconds=1800), userplaces[sp2], constructiontype = 'RecBorderEvent')
                                    eventnr +=1
                                    dump[eventnr]=fe.serialize()
                                    if not goon:
                                        if str(eventnr) in exdata.keys():
                                            break
                                        else:
                                            goon = True
                                    fe.map(eventnr)
                                    getAffordances(user, eventnr, userplaces[pp1]['geo'], start-timedelta(seconds=1800), mod1,  userplaces[sp2]['geo'], end+timedelta(seconds=1800), mod2, int(float(eventduration)), sidx,ids, outlets, cat)

                            lastrow = row
            det = str(len(dump.keys()))
            print det+' flexible events detected for user ' + str(user)
            userswithresults.append(user)
            dump['nodetevs']=det
            if goon:
                with open(store, 'w') as fp:
                    json.dump(dump, fp)
                fp.close


        #break
    print "Recorded users with reconstructed food events: "+str(len(userswithresults))
    print userswithresults


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



def flexibleTripEvent(userplaces,mod1, st1, sp1, pt1, pp1, eventduration):
    tripduration = ( pt1 - st1).total_seconds()
    if sp1 in userplaces.keys() and pp1 in userplaces.keys(): #Places available in place set?
            if  tripduration >= eventduration: #trip must at least last for eventduration + 1 minutes to enable food event
                #category = (userplaces[pp1]['label']).split(':')[0]
                #if category in foodOutletLabels:
                    if mod1 != "":
                        return True
                    else:
                        print 'modus 1 not available'
                        return False
                #else:
                #    print 'place category not in foodlabels'
                #    return False
            else:
                print 'beyond tripduration'
                return False
    else:
        print 'place not in userplaces!'
        return False

def getTripInfo(row):
    return row['modality'],dateparse(row['startTime']), cn(row['startPlaceId']), dateparse(row['stopTime']),cn(row['stopPlaceId'])

def cn(n):
    if str(n) != 'nan':
        return str(int(n))
    else:
        return None



#-------------------------------------------Simple methods for comparison

def homeBuffer(user,userplaces, outletdata, mode, home=None):
    #home = None
    print "Home buffers are generated"
    availabletime = 1800 #30 minutes from home buffer
    if mode =='Bike':
        print 'bike modeled by 3 times foot!'
        availabletime  = ((availabletime)*3)  #In order to compensate for missing bike mode we use the pedestrian mode and give it 4  times more time

    mode=convertMode(mode)          #This is needed because there are only car and predestrian modes available

    newpath =os.path.join(results,user)
    if not os.path.exists(newpath):
        os.makedirs(newpath)
    if home is None:
        for p in userplaces.values():
            if p['label']=='Home':
                home = p['geo']
                break
    if home !=None:
    #Travel based buffer
        poly = transform(project, getisoline(home,availabletime, mode = mode)) #assuming the car default
        simple_poly = transform(project,home).buffer(500) #Buffer of 500 m
        sidx,ids, outlets, cat = outletdata[0],outletdata[1],outletdata[2],outletdata[3]
        if poly.is_empty:
            print "Prism empty! No buffer outlets selected"
        else:
            print 'simulated HORECA buffer'
            candidates, candidateids, candidatecats = getPrismOutlets(poly, sidx,ids, outlets, cat)
            saveOutlets([[candidateids[i],candidates[i],candidatecats[i]] for i,v in enumerate(candidates)], save=os.path.join(newpath,"bufferHORECA.shp"))
            print 'simple H buffer'
            candidates, candidateids, candidatecats = getPrismOutlets(simple_poly, sidx,ids, outlets, cat)
            saveOutlets([[candidateids[i],candidates[i],candidatecats[i]] for i,v in enumerate(candidates)], save=os.path.join(newpath,"bufferHORECAsimple.shp"))
                                     #Shop outlets
            sidx,ids, outlets, cat = outletdata[4],outletdata[5],outletdata[6],outletdata[7]
            print 'simulated SHOP buffer'
            candidates, candidateids, candidatecats = getPrismOutlets(poly, sidx,ids, outlets, cat)
            saveOutlets([[candidateids[i],candidates[i],candidatecats[i]] for i,v in enumerate(candidates)], save=os.path.join(newpath,"bufferSHOP.shp"))
            print 'simple S buffer'
            candidates, candidateids, candidatecats = getPrismOutlets(simple_poly, sidx,ids, outlets, cat)
            saveOutlets([[candidateids[i],candidates[i],candidatecats[i]] for i,v in enumerate(candidates)], save=os.path.join(newpath,"bufferSHOPsimple.shp"))
    else:
        print "no home location for generating home buffer!"


def activitySpace(user,userplaces,track, outletdata):
     newpath =os.path.join(results,user)
     if not os.path.exists(newpath):
        os.makedirs(newpath)
     lines = []
     for index, row in track.iterrows():
                mod, st, sp, pt, pp =  getTripInfo(row)
                if sp in userplaces.keys() and pp in userplaces.keys():
                    frompl =  userplaces[sp]
                    topl = userplaces[pp]
                    lines.append(LineString([transform(project,frompl['geo']), transform(project,topl['geo'])]))
     #print lines #transform(project, transform(project,
     multiline = MultiLineString(lines)
     linestringbuffer = shape(multiline).buffer(100)
     #print linestringbuffer
     save = os.path.join(newpath,"aspace.shp" )
     schema = {
            'geometry': 'Polygon',
            'properties': { 'user':'str'},
            }

        # Write a new Shapefile
     with fiona.open(save, 'w', 'ESRI Shapefile', schema) as c:
            ## If there are multiple geometries, put the "for" loop here
                    c.write({
                        'geometry': mapping(linestringbuffer),
                        'properties': {'user':str(user)},
                        })


     c.close
     sidx,ids, outlets, cat = outletdata[0],outletdata[1],outletdata[2],outletdata[3]
     if linestringbuffer.is_empty:
        print "Linestringbuffer empty! No outlets selected"
     else:
         print 'simulated HORECA aSpace'
         candidates, candidateids, candidatecats = getPrismOutlets(linestringbuffer, sidx,ids, outlets, cat)
         saveOutlets([[candidateids[i],candidates[i],candidatecats[i]] for i,v in enumerate(candidates)], save=os.path.join(newpath,"aSpaceHORECA.shp"))
                                         #Shop outlets
         sidx,ids, outlets,cat = outletdata[4],outletdata[5],outletdata[6],outletdata[7]
         print 'simulated SHOP aSpace'
         candidates, candidateids, candidatecats = getPrismOutlets(linestringbuffer, sidx,ids, outlets, cat)
         saveOutlets([[candidateids[i],candidates[i],candidatecats[i]] for i,v in enumerate(candidates)], save=os.path.join(newpath,"aSpaceSHOP.shp"))




#-------------------------------------------Statistics, maps and plots

def summarystats(simplebuffer=False):
    search = os.path.join(results,"*"+"Recevents.json")
    files = glob.glob(search)
    allafoS = []
    allafoH = []
    allbufferS = []
    allbufferH = []
    allaspaceS = []
    allaspaceH = []
    out1 = os.path.join(results,"evstats.csv")
    out2 = os.path.join(results,"stats.csv")
    evdf = pd.DataFrame(columns=['user','event','category','constype', 'mode1', 'mode2', 'nooutlets'])
    df = pd.DataFrame(columns=['user', 'evdetected', 'evrecorded', 'aspaceH', 'aspaceS', 'bufferH', 'bufferS', 'afoH', 'afoS', 'bufferaspaceSJacc', 'bufferaspaceHJacc', 'afobufferSJacc', 'afobufferHJacc', 'afoaspaceSJacc', 'afoaspaceHJacc'])
    for f in files:
        try:
                data = json.load(open(f, 'r'))
        except IOError:
            pass
        user = os.path.basename(f).split('Recevents.')[0]
        withinuserfiles = os.path.join(results,user)
        noevents = int(data['nodetevs']) -1
        norecorded = int(data['norecevs']) -1
        afoS = [] # list of event frames for shop
        afoH = [] # list of event frames for horeca
        aspaceshop = os.path.join(withinuserfiles, 'aSpaceSHOP.csv')
        aspacehoreca = os.path.join(withinuserfiles, 'aSpaceHORECA.csv')
        s = ('simple' if  simplebuffer else '')
        buffershop = os.path.join(withinuserfiles, 'bufferSHOP'+s+'.csv')
        bufferhoreca = os.path.join(withinuserfiles, 'bufferHORECA'+s+'.csv')
        aspaceshopl = csvfilelength(aspaceshop)
        aspacehorecal = csvfilelength(aspacehoreca)
        buffershopl = csvfilelength(buffershop)
        bufferhorecal = csvfilelength(bufferhoreca)
        for i in range(1,noevents+1):
            ev = data[str(i)]
            cat = ev['category']
            constype = ev['constype']
            modes = [ev['trip1']['mod1'] , ev['trip2']['mod2']]
            print user, i
            afofile = os.path.join(withinuserfiles, str(i)+'afo.csv')
            length = csvfilelength(afofile)
            if length>0:
                if cat == "Supermarkt":
                        afoS.append(pd.read_csv(afofile,  header=None, index_col= 0, encoding="utf-8"))
                else:
                        afoH.append(pd.read_csv( afofile,  header=None, index_col= 0, encoding="utf-8"))
            #print afodf[2].value_counts()
            evdf = evdf.append({ 'user': user.encode('utf-8'),'event' : i,'category' : cat.encode('utf-8'),'constype' : constype.encode('utf-8'), 'mode1' : ev['trip1']['mod1'], 'mode2' :ev['trip2']['mod2'] , 'nooutlets' : length }, ignore_index=True)
        afoS = (pd.concat(afoS).drop_duplicates() if afoS !=[] else None)
        afoH = (pd.concat(afoH).drop_duplicates() if afoH !=[] else None)
        H = []
        Hnames = []
        S = []
        Snames = []
        if afoH is not None:
            allafoH.append(afoH)
            H.append(afoH)
            Hnames.append('afoH')
            #savediagrams(afoH, withinuserfiles, 'afoH')
        if afoS is not None:
            allafoS.append(afoS)
            S.append(afoS)
            Snames.append('afoS')
            #savediagrams(afoS, withinuserfiles, 'afoS')
        if csvfilelength(buffershop)>0:
            bufferS = pd.read_csv(buffershop,  header=None, index_col= 0, encoding="utf-8")
            allbufferS.append(bufferS)
            S.append(bufferS)
            Snames.append('bufferS')
            #savediagrams(bufferS, withinuserfiles, 'bufferS')
        if csvfilelength(bufferhoreca)>0:
            bufferH = pd.read_csv(bufferhoreca,  header=None, index_col= 0, encoding="utf-8")
            allbufferH.append(bufferH)
            H.append(bufferH)
            Hnames.append('bufferH')
            #savediagrams(bufferH, withinuserfiles, 'bufferH')
        if csvfilelength(aspaceshop)>0:
            aspaceS = pd.read_csv(aspaceshop,  header=None, index_col= 0, encoding="utf-8")
            allaspaceS.append(aspaceS)
            S.append(aspaceS)
            Snames.append('aspaceS')
            #savediagrams(aspaceS, withinuserfiles, 'aspaceS')
        if csvfilelength(aspacehoreca)>0:
            aspaceH = pd.read_csv(aspacehoreca,  header=None, index_col= 0, encoding="utf-8")
            allaspaceH.append(aspaceH)
            H.append(aspaceH)
            Hnames.append('aspaceH')
            #savediagrams(aspaceH, withinuserfiles, 'aspaceH')
        savediagrams(H, withinuserfiles, Hnames,'H')
        savediagrams(S, withinuserfiles, Snames, 'S')
        df = df.append({ 'user': user.encode('utf-8'), 'evdetected' : noevents, 'evrecorded': norecorded,
        'aspaceH': aspacehorecal, 'aspaceS': aspaceshopl, 'bufferH':bufferhorecal, 'bufferS': buffershopl, 'afoH': (len(afoH) if afoH is not None else 0), 'afoS': (len(afoS) if afoS is not None else 0),
        'bufferaspaceSJacc': (0 if (buffershopl ==0 or aspaceshopl ==0) else jaccard(readLocatusIds(aspaceshop),readLocatusIds(buffershop))),
        'bufferaspaceHJacc': (0 if (bufferhorecal ==0 or aspacehorecal==0) else jaccard(readLocatusIds(aspacehoreca),readLocatusIds(bufferhoreca))),
        'afobufferSJacc': (0 if (afoS is None or buffershopl==0) else jaccard(afoS.index,readLocatusIds(buffershop))),
        'afobufferHJacc': (0 if (afoH is None or bufferhorecal==0) else jaccard(afoH.index,readLocatusIds(bufferhoreca))),
        'afoaspaceSJacc': (0 if (afoS is None or aspaceshopl==0) else jaccard(afoS.index,readLocatusIds(aspaceshop))),
        'afoaspaceHJacc': (0 if (afoH is None  or aspacehorecal==0) else jaccard(afoH.index,readLocatusIds(aspacehoreca))),
        'afoaspaceHChi' : round((-1 if (afoH is None  or aspacehorecal==0) else ChiStest(afoH, 'afoH',aspaceH, 'aspaceH')),3),
        'afoaspaceSChi' : round((-1 if (afoS is None  or aspaceshopl==0) else ChiStest(afoS, 'afoS',aspaceS, 'aspaceS')),3),
        'afobufferHChi' : round((-1 if (afoH is None  or bufferhorecal==0) else ChiStest(afoH, 'afoH',bufferH, 'bufferH')),3),
        'afobufferSChi' : round((-1 if (afoS is None  or buffershopl==0) else ChiStest(afoS, 'afoS',bufferS, 'bufferS')),3),
        }, ignore_index=True)
        df[['evdetected','evrecorded', 'aspaceH', 'aspaceS', 'bufferH', 'bufferS','bufferaspaceSJacc', 'bufferaspaceHJacc', 'afobufferSJacc', 'afobufferHJacc', 'afoaspaceSJacc', 'afoaspaceHJacc']] = df[['evdetected','evrecorded', 'aspaceH', 'aspaceS', 'bufferH', 'bufferS','bufferaspaceSJacc', 'bufferaspaceHJacc', 'afobufferSJacc', 'afobufferHJacc', 'afoaspaceSJacc', 'afoaspaceHJacc']].astype(int)

    saveplaces(pd.concat(allafoH).drop_duplicates(), name='allafoH')
    #savediagrams(pd.concat(allafoH).drop_duplicates(), results, 'allafoH')
    saveplaces(pd.concat(allafoS).drop_duplicates(), name='allafoS')
    #savediagrams(pd.concat(allafoS).drop_duplicates(), results, 'allafoS')
    saveplaces(pd.concat(allbufferS).drop_duplicates(), name='allbufferS')
    #savediagrams(pd.concat(allbufferS), results, 'allbufferS')
    saveplaces(pd.concat(allbufferH).drop_duplicates(), name='allbufferH')
    #savediagrams(pd.concat(allbufferH), results, 'allbufferH')
    saveplaces(pd.concat(allaspaceS).drop_duplicates(), name='allaspaceS')
    #savediagrams(pd.concat(allaspaceS).drop_duplicates(), results, 'allaspaceS')
    saveplaces(pd.concat(allaspaceH).drop_duplicates(), name='allaspaceH')
    #savediagrams(pd.concat(allaspaceH).drop_duplicates(), results, 'allaspaceH')
    evdf.to_csv(out1)
    df.to_csv(out2)


def csvfilelength(file):
     if os.path.isfile(file) and os.path.getsize(file) > 0:
                length = int(len(pd.read_csv( file,  header=None, index_col= 0)))
     else:
                length = 0
     return length

def readLocatusIds(file):
    if os.path.isfile(file):
        f = pd.read_csv( file,  header=None, index_col= 0)
        #print f.first_valid_index()
        return f.index

def jaccard(file1, file2):
    #ids1 = readLocatusIds(file1)
    #ids2 = readLocatusIds(file2)
    file1l = float(len(file1))
    file2l = float(len(file2))
    if file1 is not None and len(file1)>0 and file2 is not None and len(file2)>0:
        inters =  float(len(file1.intersection(file2)))
    else:
        inters = 0.0
    print "inters:" +str(inters) + " file1: " +str(file1l) +" file2: " +str(file2l)
    jaccard = (0 if ((file1l-inters) +inters+  (file2l-inters)==0.0) else (inters/((file1l-inters) + inters+  (file2l-inters)))*100) #in percent
    print jaccard
    return jaccard

import scipy.stats as stats
def ChiStest(df1, name1, df2, name2):
    df1['cat'] =df1.apply(lambda x: ((x[2].split('-'))[1]),axis=1)
    df2['cat'] =df2.apply(lambda x: ((x[2].split('-'))[1]),axis=1)
    c1 = (df1['cat']).value_counts().to_frame()
    c2 = (df2['cat']).value_counts().to_frame()
    contingencytable = (c1).join(c2, lsuffix=name1, rsuffix=name2).dropna()
    contingencytable= contingencytable.rename(columns={'cat'+name1 : name1, 'cat'+name2 : name2})
    print contingencytable
    chi2_stat, p_val, dof, ex = stats.chi2_contingency(contingencytable)
    return p_val
##    print("===Chi2 Stat===")
##    print(chi2_stat)
##    print("\n")
##    print("===Degrees of Freedom===")
##    print(dof)
##    print("\n")
##    print("===P-Value===")
##    print(p_val)
##    print("\n")
##    print("===Contingency Table===")
##    print(ex)


from collections import Counter
from PIL import Image
from wordcloud import WordCloud
import operator
def wordcloud(dict):
    #print sorted_c
    wordcloud = WordCloud(background_color="white", min_font_size=5).fit_words(dict)
    image = wordcloud.to_image()
    return image

def savediagrams(dfs, folder, names, cls):
    sorted_cs = []
    for index,name in enumerate(names):
        savewc = os.path.join(folder,name+'wc.png')
        if dfs[index] is not None:
            dfs[index]['words'] =dfs[index].apply(lambda x: ((x[2].split('-'))[1]),axis=1)
            wordlist = dfs[index]['words'].tolist()
            c = {x:float(wordlist.count(x)) for x in wordlist}
            sorted_c = sorted(c.items(), key=operator.itemgetter(1), reverse=True)
            print folder+"/"+name
            print len(wordlist)
            sorted_cs.append(sorted_c)
            wc = wordcloud(c)
            wc.save(savewc)
    barplot(sorted_cs, folder, names, cls)
        #

def saveplaces(afodf, name='afo'):
    if afodf is not None:
        save = os.path.join(results,name+'pl.shp')
        schema = {
            'geometry': 'Point',
            'properties': {'id': 'int', 'label': 'str'},
            }
        # Write a new Shapefile
        with fiona.open(save, 'w', 'ESRI Shapefile', schema) as c:
            ## If there are multiple geometries, put the "for" loop here
                for index, i in afodf.iterrows():
                    c.write({
                        'geometry': mapping(loads(i[1])),
                        'properties': {'id': str(int(index)), 'label': (i[2])},
                        })
        c.close



# libraries
import numpy as np
import matplotlib
import matplotlib.pyplot as plt
def barplot(dicts, folder, names, cls = 'H'):
    out = os.path.join(folder,cls+'plt.png')
    colors = [(0.3,0.1,0.4,0.6), (0.3,0.5,0.4,0.6), (0.3,0.9,0.4,0.6)]
    barWidth = 0.35
    length = len(names)
    max = 8
    #plt.ylim(0,40)
    r1 = []
    cats = []
    if len(dicts) > 0:
        dict1 = dicts[0]
        cats = [i[0] for i in dict1]
    for index,name in enumerate(names):
         d = dicts[index]
         name = name.replace('afo', 'stp')
         print cats
         print d
         dd =  { i:j for i,j in d }
         if d is not None:
            total =  np.sum([i[1] for i in d])
            bars = [((float(dd[c])/total)*100 if c in dd.keys() else 0) for c in cats[0:max]]
            print bars
            n=index+1
            r = []
            for i in range(0,max):
                r.append(n)
                n = n+length
            if index == 0:
                r1 = r
            plt.bar(r, bars, width=barWidth, color = colors[index], label=name)

    # Make the plot

    # Add xticks on the middle of the group bars
    #plt.xlabel('group', fontweight='bold')
    plt.xticks(r1, cats, rotation=20)

    # Create legend & Show graphic
    plt.legend()
    print out
    plt.savefig(out)
    plt.close()


def barplotsimple(bars, cats, folder, name):
    out = os.path.join(folder,name+'plt.png')
    pos = np.arange(len(bars))
    plt.bar(pos, bars, color=(0.2, 0.4, 0.6, 0.6))
    plt.xticks(pos, cats, rotation=20, ha='right',wrap=True)
    for i,b in enumerate(bars):
        plt.text(x=pos[i]+0.3 , y =bars[i]+0.2 , s=str(int(bars[i])))

    # Create legend & Show graphic
    plt.legend()
    matplotlib.rcParams.update({'font.size': 20})

    plt.tight_layout()
    print out
    plt.savefig(out)
    plt.close()


def summarizeEvents(eventfile):
    events = pd.read_csv(eventfile,  header=0, index_col= 0, encoding="utf-8")
    catcount = events['category'].value_counts().to_frame()
    print catcount
    conscount = events['constype'].value_counts().to_frame()
    print conscount
    modecount1 = events['mode1'].value_counts().to_frame()
    modecount2 = events['mode2'].value_counts().to_frame()
    modecount = modecount1.join(modecount2).fillna(0)
    modecount['mode'] = (modecount['mode1']+modecount['mode2'])
    #modecount['mode'] =  (modecount['mode']/modecount['mode'].sum())*100
    print modecount
    barplotsimple(modecount['mode'].values.tolist(), modecount.index.tolist(), results, 'mode')
    barplotsimple(conscount['constype'].values.tolist(), conscount.index.tolist(), results, 'constype')
    barplotsimple(catcount['category'].values.tolist(), catcount.index.tolist(), results, 'category')

    #print modes

    #bars = [((float(dd[c])/total)*100 if c in dd.keys() else 0) for c in cats[0:max]]


#---------------------------------------------IO methods

def loadOutlets(outletdata= r"C:\Users\schei008\surfdrive\Temp\Locatus\outlets.shp", colx = 1, coly = 2):
    workbook = r"C:\Users\schei008\surfdrive\Temp\Locatus\Levensmiddel_Horeca_311217.xlsx"
    w = open_workbook(workbook)
    sheet = w.sheet_by_index(0)
    print 'Loading outlets!'
    outletsH = []  #Horeca
    idsH = []
    catH = []
    outletsF = []  #Food
    idsF = []
    catF = []
    for rowidx in range(1,sheet.nrows):
            x = float(sheet.cell(rowidx, sheet.ncols - colx).value)
            y = float(sheet.cell(rowidx, sheet.ncols - coly).value)
            p = transform(project, Point(x,y))
            category = sheet.cell(rowidx, 19).value
            if (category.split('-')[0]).split('.')[0]== '59':
                outletsH.append(p)
                idsH.append(sheet.cell(rowidx, 0).value)
                catH.append(category)
            else:
                outletsF.append(p)
                idsF.append(sheet.cell(rowidx, 0).value)
                catF.append(category)
##    schema = {
##        'geometry': 'Point',
##        'properties': {'id': 'int'},
##    }
    sidxH = generate_index(outletsH)  #, os.path.dirname(outletdata)
    sidxF = generate_index(outletsF)
    #points = geopandas.GeoDataFrame.from_file(outletdata)
    return (sidxH,idsH, outletsH, catH, sidxF,idsF, outletsF, catF)

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
def dateparse2 (timestamp):
    if isinstance(timestamp,basestring):
        return pd.datetime.strptime(timestamp, '%d-%m-%Y %H:%M')
    else:
        return timestamp
def dateparse3 (date, time):
    #'26-apr-18 12:35'
    date = date.replace('mei', 'may')
    return pd.datetime.strptime(date +' '+time, '%d-%b-%y %H:%M')


def loadTrips(trips, usersample):
    #headers = ['deviceId','modality','distance','startTime','stopTime','startCountry','startPc','startCity','startStreet','stopCountry','stopPc','stopCity','stopStreet','startPlaceId','stopPlaceId']
    #dtypes = [str, str, int, datetime, datetime, str, str, str, str,str,str,str,str,int,int]

    #dateCols = ['startTime','stopTime']
    tr = pd.read_csv(trips, sep=',', parse_dates=True, date_parser=dateparse,  encoding="utf-8-sig")
    #tr = pd.read_csv(trips)

    #print tr.keys()
    users= pd.read_csv(usersample, sep=';', parse_dates=True, date_parser=dateparse,  encoding="utf-8-sig")
    #print users['include']
    validids = users[users['include']==True]
    #print validids.keys()
    #print validids
    out = {}

    for index, row in validids.iterrows():
        #print row
        id = row['DeviceID']
        ti1 = datetime.strptime(row[u'START DATE'],'%Y-%m-%d')
        ti2 = datetime.strptime(row['END DATE ']+'T23:59:00','%Y-%m-%dT%H:%M:%S')
        print 'user: ',id, ti1, ti2
        usertrack =tr[tr['deviceId']== id ] #and
        usertrack =usertrack[usertrack['startTime'].apply(lambda x: dateparse(x) >=ti1 and dateparse(x) <=ti2)]
        out[str(int(id))]=usertrack
        #break

    #ti1 = datetime.strptime("2016-10-25T12:00:00",'%Y-%m-%dT%H:%M:%S')
    #ti2 =  datetime.strptime("2016-10-30T23:50:00",'%Y-%m-%dT%H:%M:%S')
    #tr = tr[tr['startTime'].apply(lambda x: dateparse(x) >=ti1 and dateparse(x) <=ti2)]
    #tr = list(tr.groupby('deviceId'))
    print 'number of users with trips: '+ str(len(out.keys()))
    print out.keys()
    return out


def loadRecords(recordedevents, usersample):
    ev = pd.read_csv(recordedevents, sep=';', parse_dates=True, date_parser=dateparse,  encoding="utf-8-sig")

        #print tr.keys()
    users= pd.read_csv(usersample, sep=';', parse_dates=True, date_parser=dateparse,  encoding="utf-8-sig")
    #print users['include']
    validids = users[users['include']==True]
    #print validids.keys()
    #print validids
    out = []
    userlist = []

    for index, row in validids.iterrows():
        #print row
        id = row['DeviceID']
        ti1 = datetime.strptime(row[u'START DATE'],'%Y-%m-%d')
        ti2 = datetime.strptime(row['END DATE ']+'T23:59:00','%Y-%m-%dT%H:%M:%S')
        #print 'user: ',id, ti1, ti2
        userevents =ev[ev['DEVICECODE']== id ] #and
        #userevents =userevents[userevents['Start date'].apply(lambda x: dateparse2(x) >=ti1 and dateparse2(x) <=ti2)]
        #userevents = userevents[['VoterID','Start date','End date', 'DEVICECODE','type of outlet of purchase', 'LOCATIE']].drop_duplicates()
        userevents = userevents[['VoterID','date_of_purchase', 'time_of_purchase', 'DEVICECODE','WAAR', 'Locatie']].drop_duplicates()
        #print userevents
        if not userevents.empty: #user not in records
            userevents['Start date'] = userevents.apply (lambda row: dateparse3(row['date_of_purchase'], row['time_of_purchase']), axis=1)
            userevents =userevents[userevents['Start date'].apply(lambda x: x >=ti1 and x <=ti2)]
            if not userevents.empty: #user not in records
                userevents['End date'] =  userevents.apply(lambda row: row['Start date']+timedelta(seconds=300), axis=1)
                userevents['type of outlet of purchase'] = userevents.apply(lambda row: row['WAAR'], axis=1)
                userevents['LOCATIE'] = userevents.apply(lambda row: row['Locatie'], axis=1)
                userevents = userevents[['VoterID','Start date','End date', 'DEVICECODE','type of outlet of purchase', 'LOCATIE']]
                #userevents = userevents.groupby(['VoterID', 'Start date','End date', 'DEVICECODE', 'type of outlet of purchase', 'LOCATIE'])["purchased products "].sum()
                #print (userevents)

                out.append(userevents)
                userlist.append(id)
        #break

    #ti1 = datetime.strptime("2016-10-25T12:00:00",'%Y-%m-%dT%H:%M:%S')
    #ti2 =  datetime.strptime("2016-10-30T23:50:00",'%Y-%m-%dT%H:%M:%S')
    #tr = tr[tr['startTime'].apply(lambda x: dateparse(x) >=ti1 and dateparse(x) <=ti2)]
    #tr = list(tr.groupby('deviceId'))
    print 'Number of users with records loaded: '+ str(len(out))
    print userlist
    return out

def addMissingHomes(outletdata):
    #places =r"C:\Users\schei008\Dropbox\Schriften\Exchange\GOF\foodtracker\places.csv"
    missing  = r"C:\Users\schei008\Dropbox\Schriften\Exchange\GOF\foodtracker\homes_missing.csv"
    with open(missing, 'rb') as csvfile:
        reader = csv.reader(csvfile, delimiter=',', quotechar='"')
        for row in reader:
            user = row[0]
            home = loads(row[2])
            homeBuffer(user,None, outletdata, 'Bike', home=home)
    csvfile.close










results = r"C:\Users\schei008\surfdrive\Temp\FoodResults"
def main():
      #print  getActivityLabels(r"C:\Users\schei008\Dropbox\Schriften\Exchange\GOF\foodtracker\places.csv")
    #outletdata = loadOutlets()
##    places =r"C:\Users\schei008\Dropbox\Schriften\Exchange\GOF\foodtracker\places.csv"
##    trips = r"C:\Users\schei008\Dropbox\Schriften\Exchange\GOF\foodtracker\trips.csv"
##    usersample =r"C:\Users\schei008\Dropbox\Schriften\Exchange\GOF\foodtracker\Simon_start_stop_date_per_device_ID_cleaned.csv"
##    ##recordedevents =r"C:\Users\schei008\Dropbox\Schriften\Exchange\GOF\foodtracker\SIMON_PURCHASES_INCOMPLETE_FILE.csv"
##    recordedevents =r"C:\Users\schei008\Dropbox\Schriften\Exchange\GOF\foodtracker\Purchases_total_inclTime_Simon.csv" # events with true purchase times
##
##    pl = loadPlaces(places)
##    tr = loadTrips(trips,usersample)
##    ev = loadRecords(recordedevents,usersample)
##    ##constructEvents(tr,pl,outletdata,tripeventsOn=True)
##    constructRecordedEvents(tr,pl,outletdata,ev)

    #addMissingHomes(outletdata)
    #summarystats(simplebuffer = True)
    summarystats()
    #summarizeEvents(os.path.join(results,'evstats.csv'))













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
    #Logging into file
    #sys.stdout = open(os.path.join(results,'log.txt'), 'w')
    main()
    print("--- %s seconds ---" % (time.time() - start_time))

