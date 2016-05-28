#!/usr/bin/python3

import tornado.ioloop
import tornado.web
from tornado.options import define, options

from bcrypt import hashpw, gensalt
from utils import fixed_feedparser_parse


import os
import time

import torndb

template_path = os.path.join(os.path.dirname(__file__), "template")
static_path   = os.path.join(os.path.dirname(__file__), "static")

import threading

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
        self.render("reg.html", error=None)
        
    def post(self):
        name = self.get_argument('name')
        passwd = self.get_argument('passwd')
        email = self.get_argument('email')
        xxxx = self.get_query_argument('xxxx', '')
        if not (name and passwd and email):
            self.render("reg.html", error="信息不完整！")
            return
        
        # 先检查有没有该用户
        sql = "SELECT uuid FROM site_user WHERE email=%s;"
        if db_conn.query(sql, email):
            self.render("reg.html", error="该Email已经被注册！")
            return
        passwd_hd = hashpw(passwd.encode(), gensalt())
        sql = "INSERT INTO site_user(username, passwd, email, xxxx) VALUES(%s, %s, %s, %s)"
        db_conn.execute(sql, name, passwd_hd, email, xxxx)
        self.render("reg_ok.html", title="readmeinfo - register", name=name)
        return

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
        self.render("sub.html", error=None)
        return
        
    @tornado.web.authenticated
    def post(self):
        userid_s = repr(self.current_user['uuid'])
        feeduri = self.get_argument('feeduri')    
        comments = self.get_query_argument('comments'," ")
        if not feeduri:
            self.render("sub.html", error="请提供Feed/Atom之URI")
            return
        d = fixed_feedparser_parse(feeduri)
        if not d.feed :
            self.render("sub.html", error="无法解析提交的地址")
            return
        sql = """ SELECT site_id FROM site_info where site_link=%s"""
        if db_conn.query(sql, d.feed.link):
            error_info = "谢谢！提交的%s(%s)已经存在！"%(d.feed.link, d.feed.title)
            self.render("sub.html", error=error_info)
            return
        sql = "INSERT INTO site_info(site_title, site_link, feed_uri, site_desc, create_date, valid, comments, create_usr) VALUES(%s, %s, %s, %s, NOW(), 1, %s," + userid_s + ");"
        db_conn.execute(sql, d.feed.title, d.feed.link, feeduri, d.feed.description, comments)
        self.render("sub_ok.html", title="readmeinfo - submit", sitename=d.feed.title)

class BrowseHandler(BaseHandler):
    @tornado.web.authenticated
    def get(self):
        userid_s = repr(self.current_user['uuid'])        
        types = self.get_query_argument('typeselect', "1") #默认浏览
        sql = """ SELECT * FROM (SELECT site_news.uuid, site_news.news_title, site_news.news_pubtime, site_news.news_link, site_news.news_sitefrom, site_news.news_desc, IFNULL(ATS.news_user_score, 1) as news_score, ATS.userid FROM site_news LEFT JOIN (SELECT news_user_score, newsid, userid FROM user_score WHERE userid="""
        sql += userid_s + """) ATS ON site_news.uuid = ATS.newsid WHERE DATE(site_news.time)=CURRENT_DATE()) ATT  WHERE news_score=""" + types + ";"
        articles = db_conn.query(sql)
        self.render("browse.html", title="readmeinfo - browse", items=articles, types=types)

class ReMaxentHandler(BaseHandler):
    @tornado.web.authenticated
    def get(self):
        self.write("Not implement! <a href='/'>返回主页</a>")
        pass

# JUST RESERVED FOR AJAX API
class ScoreHandler(BaseHandler):
    def post(self):
        userid_s = repr(self.current_user['uuid'])
        uuid = self.get_argument('uuid')
        score = self.get_argument('score')
        sql = "SELECT uuid FROM user_score WHERE userid=" + userid_s + " AND newsid=" + uuid + ";";
        if db_conn.query(sql):
            sql = "UPDATE user_score SET news_user_score=" + score + " WHERE userid=" + userid_s + " AND newsid=" + uuid + ";"
        else:
            sql = "INSERT INTO user_score(userid, newsid, news_user_score) VALUES(" + userid_s + "," + uuid + "," + score +");"
        db_conn.execute(sql)

tornado_handlers = [
        (r"/", IndexHandler),
        (r"/static/(.*)", tornado.web.StaticFileHandler, {"path": static_path}),
        (r"/register", RegisterHandler),
        (r"/login",    LoginHandler),
        (r"/logout",   LogoutHandler),
        (r"/submit",   SubmitHandler),
        (r"/browse",   BrowseHandler),
        (r"/remaxent", ReMaxentHandler),
        (r"/score",    ScoreHandler)]

settings = {
    "cookie_secret": "49955cc9cea186c37aeb66d13c0f559e",
    "login_url": "/login",
    "Debug": True }

class TornadoThread(threading.Thread):
    def __init__(self):
        global db_conn
        threading.Thread.__init__(self)  
        db_conn = torndb.Connection(options.dbhost, options.dbname, 
                                    options.dbuser, options.dbpass)
        return
    
    def run(self):
        print("TornadoThread Start....")
        app = tornado.web.Application(tornado_handlers, template_path=template_path, static_path=static_path, 
                                      **settings)
        app.listen(4000, address="0.0.0.0")
        tornado.ioloop.IOLoop.current().start()            
        return

    
