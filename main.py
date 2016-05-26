#!/usr/bin/python3

import tornado.ioloop
import tornado.web

from bcrypt import hashpw, gensalt

from SvdCalc import SvdCalcThread
from Feedfetch import FeedfetchThread

import os
import time

import torndb

template_path = os.path.join(os.path.dirname(__file__), "template")
static_path   = os.path.join(os.path.dirname(__file__), "static")


import threading
thread_dict = dict()

db_conn = None

class IndexHandler(tornado.web.RequestHandler):
    def get(self):
        self.render("index.html")
        
class RegisterHandler(tornado.web.RequestHandler):
    def post(self):
        name = self.get_argument('name')
        passwd = self.get_argument('passwd')
        email = self.get_argument('email')    
        if not (name and passwd and email):
            self.write('<html><head><meta charset=utf-8></head><body>Infomation Missing, return <a href="/static/reg.html">Register Page</a></body></html>')
        passwd_hd = hashpw(passwd.encode(), gensalt())
        sql = "INSERT INTO site_user(username, passwd, email) VALUES(%s, %s, %s)"
        db_conn.execute(sql, name, passwd_hd, email)
        self.render("reg_ok.html", title="readmeinfo - register", name=name)
        
class SubmitHandler(tornado.web.RequestHandler):
    def post(self):
        name = self.get_argument('name')
        url = self.get_argument('url')
        feeduri = self.get_argument('feeduri')    
        desc = self.get_argument('desc') 
        if not (name and url and feeduri and desc):
            self.write('<html><head><meta charset=utf-8></head><body>Infomation Missing, return <a href="/static/sub.html">Register Page</a></body></html>')

        sql = "INSERT INTO site_info(site_title, site_link, feed_uri, site_desc, create_date, valid) VALUES(%s, %s, %s, %s, NOW(), 1)"
        db_conn.execute(sql, name, url, feeduri, desc)
        self.render("sub_ok.html", title="readmeinfo - submit", url=url)

class ReadHandler(tornado.web.RequestHandler):
    def get(self):
        types = self.get_query_argument('typeselect', "0") #默认喜欢
        sql = "SELECT uuid, news_score, news_title, news_link, news_pubtime, news_desc, news_sitefrom FROM site_news WHERE news_touched=0 AND news_score="
        sql += types + " ORDER BY news_pubtime DESC;"
        articles = db_conn.query(sql)
        self.render("read.html", title="readmeinfo - browse", items=articles, types=types)


class ScoreHandler(tornado.web.RequestHandler):
    def post(self):
        uuid = self.get_argument('uuid')
        score = self.get_argument('score')
        sql = "UPDATE site_news SET news_score=" + score + " WHERE uuid=" + uuid + ";"
        db_conn.execute(sql)

tornado_handlers = [
        (r"/", IndexHandler),
        (r"/static/(.*)", tornado.web.StaticFileHandler, {"path": static_path}),
        (r"/reg", RegisterHandler),
        (r"/sub", SubmitHandler),
        (r"/read", ReadHandler),
        (r"/score", ScoreHandler)]

class TornadoThread(threading.Thread):
    def __init__(self):
        threading.Thread.__init__(self)  
        self.db_conn = torndb.Connection("192.168.122.1", "readmeinfo", "v5kf", "v5kf")
        return
    
    def run(self):
        print("TornadoThread Start....")
        app = tornado.web.Application(tornado_handlers, template_path=template_path, static_path=static_path, debug=True)
        app.listen(4000, address="0.0.0.0")
        tornado.ioloop.IOLoop.current().start()            
        return


if __name__ == "__main__":
    print("readmeinfo started...")

    db_conn = torndb.Connection("192.168.122.1", "readmeinfo", "v5kf", "v5kf")
    
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
    
    
    
