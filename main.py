#!/usr/bin/python3

import os
import time
import datetime
import queue

from tornado.options import define, options
define("dbhost", default="127.0.0.1", help="database host name/ip")
define("dbname", default="readmeinfo", help="database name")
define("dbuser", default="v5kf", help="database username")
define("dbpass", default="v5kf", help="database passwd")
define("dbtimezone", default="+8:00")

define("recmaxent_queue", default=queue.Queue())
define("recsvd_queue", default=queue.Queue())

import threading
thread_dict = dict()
from RecSvd import RecSvdThread
from Feedfetch import FeedfetchThread
from TornadoWeb import TornadoThread
from RecMaxEnt import RecMaxEntThread



if __name__ == "__main__":
    print("readmeinfo started...")
    
    t = TornadoThread()
    t.start()
    thread_dict["TornadoThread"] = t
    
    t = FeedfetchThread()
    t.start()
    thread_dict["FeedfetchThread"] = t    

    t = RecSvdThread()
    t.start()
    thread_dict["RecSvdThread"] = t   
    
    t = RecMaxEntThread()
    t.start()
    thread_dict["RecMaxEntThread"] = t      
    
    while True:
        time.sleep(120)
        for (k,v) in thread_dict.items():
            if v.isAlive():
                print (k+':A ', end = '')
            else:
                print (k+':D ', end = '')        
        print()
        print('main:A () time:' + repr(datetime.datetime.now()))
    
    
    
