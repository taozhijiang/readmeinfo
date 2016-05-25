#!/usr/bin/python3
import os
import time
import threading

import torndb
import gensim

class SvdCalcThread(threading.Thread):
    def __init__(self, db_conn):
        threading.Thread.__init__(self)  
        self.db_conn = db_conn
        return
    
    def run(self):
        print("SvdCalcThread Start....")
        
        while True:
            time.sleep(20)

        return