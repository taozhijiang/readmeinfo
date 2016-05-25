#!/usr/bin/python3

import tornado.ioloop
import tornado.web

from bcrypt import hashpw, gensalt

import os

import torndb

template_path = os.path.join(os.path.dirname(__file__), "template")
static_path   = os.path.join(os.path.dirname(__file__), "static")

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
        self.render("reg_ok.html", title="Register", name=name)
        
class SubmitHandler(tornado.web.RequestHandler):
    def post(self):
        name = self.get_argument('name')
        url = self.get_argument('url')
        feeduri = self.get_argument('feeduri')    
        desc = self.get_argument('desc') 
        if not (name and url and feeduri and desc):
            self.write('<html><head><meta charset=utf-8></head><body>Infomation Missing, return <a href="/static/sub.html">Register Page</a></body></html>')

        sql = "INSERT INTO site_info(site_title, site_link, feed_uri, site_desc, valid) VALUES(%s, %s, %s, %s, 1)"
        db_conn.execute(sql, name, url, feeduri, desc)
        self.render("sub_ok.html", title="Submit", url=url)

class ReadHandler(tornado.web.RequestHandler):
    def get(self):
        self.write("Not Implemented!!!")    


tornado_handlers = [
        (r"/", IndexHandler),
        (r"/static/(.*)", tornado.web.StaticFileHandler, {"path": static_path}),
        (r"/reg", RegisterHandler),
        (r"/sub", SubmitHandler),
        (r"/read", ReadHandler)]

if __name__ == "__main__":
    print("readmeinfo started...")

    db_conn = torndb.Connection("192.168.122.1", "readmeinfo", "v5kf", "v5kf")
    
    app = tornado.web.Application(tornado_handlers, template_path=template_path, static_path=static_path, debug=True)
    app.listen(4000, address="0.0.0.0")
    tornado.ioloop.IOLoop.current().start()    