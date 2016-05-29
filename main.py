#!/usr/bin/python3

import os
import time

from tornado.options import define, options

from SvdCalc import SvdCalcThread
from Feedfetch import FeedfetchThread
from TornadoWeb import TornadoThread

import threading
thread_dict = dict()

define("dbhost", default="127.0.0.1", help="database host name/ip")
define("dbname", default="readmeinfo", help="database name")
define("dbuser", default="v5kf", help="database username")
define("dbpass", default="v5kf", help="database passwd")
define("dbtimezone", default="+8:00")


if __name__ == "__main__":
    print("readmeinfo started...")
    
    t = TornadoThread()
    t.start()
    thread_dict["TornadoThread"] = t
    
    t = FeedfetchThread()
    t.start()
    thread_dict["FeedfetchThread"] = t    

    t = SvdCalcThread()
    t.start()
    thread_dict["SvdCalcThread"] = t    
    
    while True:
        time.sleep(10)
        for (k,v) in thread_dict.items():
            if v.isAlive():
                print (k+':A ', end = '')
            else:
                print (k+':D ', end = '')        
        print()
    
    
    
