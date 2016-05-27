#!/usr/bin/python3

import tornado.ioloop
import tornado.web
from tornado.options import define, options

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

define("dbhost", default="127.0.0.1", help="database host name/ip")
define("dbname", default="readmeinfo", help="database name")
define("dbuser", default="v5kf", help="database username")
define("dbpass", default="v5kf", help="database passwd")

db_conn = None

class BaseHandler(tornado.web.RequestHandler):
    def get_current_user(self):
        user_email = self.get_secure_cookie("siteuseremail")
        if not user_email: return None
        return db_conn.get("SELECT * FROM site_user WHERE email = %s", user_email)

class IndexHandler(BaseHandler):
    def get(self):
        self.render("index.html")
        
class RegisterHandler(BaseHandler):
    def get(self):
        self.render("reg.html")
        
    def post(self):
        name = self.get_argument('name')
        passwd = self.get_argument('passwd')
        email = self.get_argument('email')
        xxxx = self.get_query_argument('xxxx', '')
        if not (name and passwd and email):
            self.write('<html><head><meta charset=utf-8></head><body>Infomation Missing, return <a href="/static/reg.html">Register Page</a></body></html>')
        passwd_hd = hashpw(passwd.encode(), gensalt())
        sql = "INSERT INTO site_user(username, passwd, email, xxxx) VALUES(%s, %s, %s, %s)"
        db_conn.execute(sql, name, passwd_hd, email, xxxx)
        self.render("reg_ok.html", title="readmeinfo - register", name=name)

class LoginHandler(BaseHandler):
    def get(self):
        self.render("login.html", error=None)
        
    def post(self):
        email = self.get_argument('email')
        passwd = self.get_argument('passwd')
        if not email or not passwd:
            self.render("login.html", error="登陆信息不全")
            return            
        sql = "SELECT username, email, passwd FROM site_user WHERE email=%s and valid=1;"
        rets = db_conn.get(sql, email)
        if not rets:
            self.render("login.html", error="未注册账户")
            return
        passwd_x = hashpw(passwd.encode(), rets['passwd'].encode())
        if passwd_x == rets['passwd'].encode():
            self.set_secure_cookie("siteuseremail", rets['email'])
            self.redirect(self.get_argument("next", "/"))            
        else:
            self.render("login.html", error="密码错误")
            return            

class LogoutHandler(BaseHandler):
    def get(self):
        self.clear_cookie("siteuseremail")
        self.redirect(self.get_argument("next", "/"))
        
        
class SubmitHandler(BaseHandler):
    @tornado.web.authenticated
    def get(self):
        self.render("sub.html")
        
    def post(self):
        feeduri = self.get_argument('feeduri')    
        desc = self.get_argument('comment')
        if not (name and url and feeduri and desc):
            self.write('<html><head><meta charset=utf-8></head><body>Infomation Missing, return <a href="/static/sub.html">Register Page</a></body></html>')

        sql = "INSERT INTO site_info(site_title, site_link, feed_uri, site_desc, create_date, valid) VALUES(%s, %s, %s, %s, NOW(), 1)"
        db_conn.execute(sql, name, url, feeduri, desc)
        self.render("sub_ok.html", title="readmeinfo - submit", url=url)

class ReadHandler(BaseHandler):
    def get(self):
        types = self.get_query_argument('typeselect', "1") #默认浏览
        sql = "SELECT uuid, news_score, news_title, news_link, news_pubtime, news_desc, news_sitefrom FROM site_news WHERE news_touched=0 AND news_score="
        sql += types + " ORDER BY news_pubtime DESC;"
        articles = db_conn.query(sql)
        self.render("browse.html", title="readmeinfo - browse", items=articles, types=types)


# JUST RESERVED FOR AJAX API
class ScoreHandler(BaseHandler):
    def post(self):
        uuid = self.get_argument('uuid')
        score = self.get_argument('score')
        sql = "UPDATE site_news SET news_score=" + score + " WHERE uuid=" + uuid + ";"
        db_conn.execute(sql)

tornado_handlers = [
        (r"/", IndexHandler),
        (r"/static/(.*)", tornado.web.StaticFileHandler, {"path": static_path}),
        (r"/register", RegisterHandler),
        (r"/login",    LoginHandler),
        (r"/logout",   LogoutHandler),
        (r"/submit",   SubmitHandler),
        (r"/browse",   ReadHandler),
        (r"/score",    ScoreHandler)]

settings = {
    "cookie_secret": "49955cc9cea186c37aeb66d13c0f559e",
    "login_url": "/login",
    "Debug": True }

class TornadoThread(threading.Thread):
    def __init__(self):
        threading.Thread.__init__(self)  
        self.db_conn = torndb.Connection(options.dbhost, options.dbname, 
                                         options.dbuser, options.dbpass)
        return
    
    def run(self):
        print("TornadoThread Start....")
        app = tornado.web.Application(tornado_handlers, template_path=template_path, static_path=static_path, 
                                      **settings)
        app.listen(4000, address="0.0.0.0")
        tornado.ioloop.IOLoop.current().start()            
        return


if __name__ == "__main__":
    print("readmeinfo started...")

    db_conn = torndb.Connection(options.dbhost, options.dbname, 
                                options.dbuser, options.dbpass)
    
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
    
    
    
