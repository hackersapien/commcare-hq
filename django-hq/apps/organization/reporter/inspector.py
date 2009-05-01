from django import template
from django.contrib.contenttypes.models import ContentType
from types import ListType,TupleType

import modelrelationship.traversal as traversal
from modelrelationship.models import *
from xformmanager.models import *
from organization.models import *
import xformmanager.adapter.querytools as qtools
import organization.utils as utils
        

import time
from datetime import timedelta
import dbanalyzer.dbhelper as dbhelper

xmldate_format= '%Y-%m-%dT%H:%M:%S'
output_format = '%Y-%m-%d %H:%M'

username_datecount_cache = {}

def get_daterange_header(startdate, enddate, format_string='%m/%d/%Y'):
    ret = []
    totalspan = enddate-startdate    
    for day in range(0,totalspan.days+1):   
        delta = timedelta(days=day)
        target_date = startdate + delta
        ret.append(target_date.strftime(format_string))
    return ret

def get_user_allforms_count(domain, username, startdate=None, enddate=None):
    ret  = ''
    totalspan = enddate-startdate    
    day_count_hash = {}
    #print 'get_user_allforms_count'
    for day in range(0,totalspan.days+1):
        delta = timedelta(days=day)
        target_date = startdate + delta
        #print "get_user_allforms_count: %s" % (str(target_date))
        day_count_hash[target_date.strftime('%m/%d/%Y')] = 0
    
    defs = FormDefData.objects.all().filter(uploaded_by__domain=domain)
    
    for fdef in defs:        
        table = fdef.element.table_name        
        helper = dbhelper.DbHelper(table, fdef.form_display_name)
        userdailies = helper.get_filtered_date_count(startdate, enddate,filters={'username': username})                        
        for dat in userdailies:         
            #dt = time.strptime(str(dat[1][0:-4]),xmldate_format)
            #datum = datetime(dt[0],dt[1],dt[2],dt[3],dt[4],dt[5],dt[6])
            #day_count_hash[datum.strftime('%m/%d/%Y')] += int(dat[0])    
            day_count_hash[dat[1]] += int(dat[0])
    
    #print day_count_hash
    return day_count_hash


def get_aggregate_count(content_obj, startdate, enddate):
    """For a given content object, presumably it's a organization or a user, it'll query all the xforms in its domain and see what the aggregate counts of all submissions it has under itself"""
    #report_query = "select '%s', (select TimeEnd from %s where username='%s' order by timeend desc limit 1), (select count(*) from %s where username='%s');"
    usernames_to_filter = []    

    totalspan = enddate-startdate    
    master_date_hash = {}
        
    for day in range(0,totalspan.days+1):
        delta = timedelta(days=day)
        target_date = startdate + delta
        master_date_hash[target_date.strftime('%m/%d/%Y')] = 0

    is_supervisor = False
    is_org = False
    is_member = False
    domain = None
    if isinstance(content_obj, Organization):
        is_org = True        
        domain  = content_obj.domain
        (members, supervisors) = utils.get_members_and_supervisors(content_obj)        
        for member in members:
            usernames_to_filter.append(member.username)
        for supervisor in supervisors:
            usernames_to_filter.append(supervisor.username)
    elif isinstance(content_obj, ExtUser):        
        domain  = content_obj.domain
        supervising_orgs = utils.get_supervisor_roles(content_obj)
        usernames_to_filter.append(content_obj.username)
        is_member = True
        
    
    for user in usernames_to_filter:
        if not username_datecount_cache.has_key(user):
            username_datecount_cache[user] = get_user_allforms_count(domain, user, startdate, enddate)
            
        for target_date in username_datecount_cache[user].keys():
            master_date_hash[target_date] += username_datecount_cache[user][target_date]
    
    row = []
    
    for day in range(0,totalspan.days+1):        
        delta = timedelta(days=day)        
        target_date = startdate + delta
        val = master_date_hash[target_date.strftime('%m/%d/%Y')]        
        row.append(val)        
    
    return row

def get_report_as_tuples(hierarchy_arr, startdate, enddate, depth):
    """Do a hierarchical query and flattens the recursive return into a simple array of items in the format [recursiondepth, descriptor, item, report_rowdata]"""
    fullret = []
        
    prior_edgetype = None
    group_edge = False
    
    for edges in hierarchy_arr:
        subitems = []
        sublist = []
        edge = None            
        
        if isinstance(edges,ListType):
            sublist = sublist + get_report_as_tuples(edges, startdate, enddate, depth + 1)
        else:            
            single_item = []
            single_item.append(depth)
            
            if edge == None:            
                edge = edges #it's just a single edge
            if edge.relationship.name == "Domain Chart":    #ugly hack.  we need to constrain by the relationship types we want to do
                return fullret
            
            #check to see if we're entering a new section/block of the relationships.
            if edge.relationship != prior_edgetype:      
                if group_edge:
                    group_edge = False              
                prior_edgetype = edge.relationship                
                #subitems += edge.relationship.description                
                group_edge = True            
                #we flipped the edgetype, so we're in a new group, put a descriptor!
                single_item.append(edge.relationship.description)
            else:
                single_item.append(None)

            single_item.append(edge.child_object)    
            single_item.append(get_aggregate_count(edge.child_object, startdate, enddate))                                     
            
            subitems.append(single_item)
        fullret += subitems
        fullret += sublist
    
    if depth == 0:
        username_datecount_cache.clear()    
    return fullret
