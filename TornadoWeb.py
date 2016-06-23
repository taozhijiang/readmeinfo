#!/usr/bin/python3


import tornado.ioloop
import tornado.web
import tornado.gen

from tornado.options import define, options
from tornado.httpclient import AsyncHTTPClient

from bcrypt import hashpw, gensalt
from utils import fixed_feedparser_parse


import os
import time
import threading
import re

import copy

import torndb

template_path = os.path.join(os.path.dirname(__file__), "template")
static_path   = os.path.join(os.path.dirname(__file__), "static")

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
        sql = "SELECT user_uuid FROM site_user WHERE email=%s;"
        if db_conn.query(sql, email):
            self.render("reg.html", error="该Email已经被注册！")
            return
        passwd_hd = hashpw(passwd.encode(), gensalt())
        sql = "INSERT INTO site_user(username, passwd, email, xxxx) VALUES(%s, %s, %s, %s)"
        db_conn.execute(sql, name, passwd_hd, email, xxxx)
        
        # 检测
        sql = "SELECT user_uuid, username FROM site_user WHERE email=%s; "
        rets = db_conn.get(sql, email)
        if rets:
            self.render("reg_ok.html", title="readmeinfo - register", info=rets)
        else:
            self.render("reg.html", error="失败，请重试！")
        return

class LoginHandler(BaseHandler):
    def initialize(self, *args, **kwargs):
        self.remote_ip = self.request.headers.get('X-Forwarded-For', 
                                                  self.request.headers.get('X-Real-Ip', 
                                                                           self.request.remote_ip))
        
    def get(self):
        self.render("login.html", error=None)
        
        # 0 登陆成功， 1 信息不全　2 未注册用户　3 密码错误
    def post(self):
        email = self.get_argument('email')
        passwd = self.get_argument('passwd')
        if not email or not passwd:            
            sql = "INSERT INTO site_log( email, remote_ip, action, result, time) VALUES (%s, %s, 1, 1, NOW())" 
            db_conn.execute(sql, email, self.remote_ip)
            self.render("login.html", error="登陆信息不全")
            return            
        sql = "SELECT username, email, passwd FROM site_user WHERE email=%s and valid=1;"
        rets = db_conn.get(sql, email)
        if not rets:
            sql = "INSERT INTO site_log( email, remote_ip, action, result, time) VALUES (%s, %s, 1, 2, NOW())" 
            db_conn.execute(sql, email, self.remote_ip)     
            self.render("login.html", error="未注册账户")
            return
        passwd_x = hashpw(passwd.encode(), rets['passwd'].encode())
        if passwd_x == rets['passwd'].encode():
            sql = "INSERT INTO site_log( email, remote_ip, action, result, time) VALUES (%s, %s, 1, 0, NOW())"
            db_conn.execute(sql, email, self.remote_ip)   
            self.set_secure_cookie("siteuseremail", rets['email'])
            self.redirect(self.get_argument("next", "/"))            
        else:
            sql = "INSERT INTO site_log( email, remote_ip, action, result, time) VALUES (%s, %s, 1, 3, NOW())" 
            db_conn.execute(sql, email, self.remote_ip)      
            self.render("login.html", error="密码错误")
        return            

class LogoutHandler(BaseHandler):
    def initialize(self, *args, **kwargs):
        self.remote_ip = self.request.headers.get('X-Forwarded-For', 
                                                  self.request.headers.get('X-Real-Ip', 
                                                                           self.request.remote_ip))
        self.email = self.current_user['email']
        
    def get(self):
        sql = "INSERT INTO site_log( email, remote_ip, action, result, time) VALUES (%s, %s, 2, 0, NOW())"
        db_conn.execute(sql, self.email, self.remote_ip)     
        self.clear_cookie("siteuseremail")
        self.redirect(self.get_argument("next", "/"))
        
        
class SubmitHandler(BaseHandler):
    @tornado.web.authenticated
    def get(self):
        self.render("sub.html", error=None)
        return
        
    @tornado.web.authenticated
    def post(self):
        user_id = self.current_user['user_uuid']
        feeduri = self.get_argument('feeduri')    
        comments = self.get_query_argument('comments'," ")
        if not feeduri:
            self.render("sub.html", error="请提供Feed/Atom之URI")
            return
        d = fixed_feedparser_parse(feeduri)
        if not d.feed :
            self.render("sub.html", error="无法解析提交的地址")
            return
        sql = """ SELECT site_id FROM site_info where site_link=%s and site_title=%s"""
        if db_conn.query(sql, d.feed.link, d.feed.title):
            error_info = "谢谢！提交的%s(%s)已经存在！"%(d.feed.link, d.feed.title)
            self.render("sub.html", error=error_info)
            return
        sql = "INSERT INTO site_info(site_title, site_link, feed_uri, site_desc, create_date, valid, comments, create_usr) VALUES(%s, %s, %s, %s, NOW(), 1, %s," + repr(user_id) + ");"
        db_conn.execute(sql, d.feed.title, d.feed.link, feeduri, d.feed.description, comments)
        self.render("sub_ok.html", title="readmeinfo - submit", sitename=d.feed.title)

class BrowseHandler(BaseHandler):
    @tornado.web.authenticated
    # 添加分页显示，每页10篇文章，可以加快页面显示速度
    def get(self):
        CNT_PER_PAGE = 10
        user_id = self.current_user['user_uuid']        
        types = self.get_query_argument('types', "1") #默认浏览
        page = self.get_query_argument('page', "0")
        sql = """SELECT * FROM (
                     SELECT site_news.news_uuid, site_news.news_title, site_news.news_pubtime, site_news.news_link, site_news.news_sitefrom, 
			    site_news.news_desc, IFNULL(ATS.news_user_score, 1) as news_score, ATS.userid FROM site_news 
                        LEFT JOIN (SELECT news_user_score, newsid, userid FROM user_score WHERE userid=%d ) ATS ON site_news.news_uuid = ATS.newsid 
                     WHERE DATE(site_news.time)=CURRENT_DATE()
		) ATT  
                WHERE news_score=%d ORDER BY news_pubtime DESC """ %(user_id, int(types))
        total_count = db_conn.execute_rowcount(sql + ";")
        page_num = int(total_count/CNT_PER_PAGE) + bool(total_count%CNT_PER_PAGE);
        sql += " LIMIT %d,%d ; " %(int(page) * CNT_PER_PAGE, CNT_PER_PAGE)
        articles = db_conn.query(sql)
        
        # fix
        if page_num == 0: page_num = 1
        self.render("browse.html", title="readmeinfo - browse", items=articles, types=types, page=page, page_num=page_num)

class ReMaxentHandler(BaseHandler):
    @tornado.web.authenticated
    def get(self):
        user_id = self.current_user['user_uuid']        
        sort = self.get_query_argument('sort', "0") #默认浏览
        sql = """ SELECT * FROM (
                        SELECT site_news.news_uuid, site_news.news_title, site_news.news_pubtime, site_news.news_link, 
                             site_news.news_sitefrom, site_news.news_desc, IFNULL(ATS.news_user_score, 1) as news_score, 
                             IFNULL(ATS.userid, %d) as userid FROM site_news 
                        LEFT JOIN (SELECT userid, newsid, news_user_score FROM user_score WHERE userid=%d) ATS 
                            ON site_news.news_uuid = ATS.newsid
                        WHERE DATE(site_news.time) = CURRENT_DATE()
                    ) ATT INNER JOIN user_rcd ON ATT.userid = user_rcd.userid AND ATT.news_uuid = user_rcd.newsid 
                    WHERE news_score=1 AND rcdmaxent IS NOT NULL ORDER BY rcdmaxent """ %(user_id, user_id)
        if sort == "0":
            sql += " DESC "
        else:
            sql += " ASC "
        sql += "LIMIT 0, 100;"
        articles = db_conn.query(sql)
        if articles:
            self.render("recmaxent.html", title="readmeinfo - Recommend MaxEnt", items=articles, sort=sort)
            return
        
        # 检查当天是否有新的新闻
        sql = """ SELECT news_uuid, time FROM site_news WHERE DATE(site_news.time)=CURRENT_DATE(); """
        uuids = db_conn.query(sql)
        if not uuids:
            self.write("今天还没有新的新闻，请稍后再尝试！")
            return
        else:
            for item in uuids:
                sql = """ SELECT rcd_uuid FROM user_rcd WHERE userid=%d AND newsid=%d; """ %(user_id, item['news_uuid'])
                if not db_conn.query(sql):
                    sql = """ INSERT INTO user_rcd(userid, newsid, date) VALUES (%d, %d, DATE('%s')); """ %(user_id, item['news_uuid'], item['time'])
                    db_conn.execute(sql)
                
            try:
                options['recmaxent_queue'].put(user_id, block=True, timeout=30)
                print("Queue %d from RecMaxEnt recommend!" %(user_id))
            except Exception as e:
                print("Queue %d from RecMaxEnt recommend Failed!" %(user_id))
                pass
            
            self.write("今天共有%d条新闻，调度建立推荐索引，请稍后再试！" %(len(uuids)) )
        return
    
class ReSVDHandler(BaseHandler):
    @tornado.web.authenticated
    def get(self):
        user_id = self.current_user['user_uuid']        
        sort = self.get_query_argument('sort', "0") #默认浏览
        sql = """ SELECT * FROM (
                        SELECT site_news.news_uuid, site_news.news_title, site_news.news_pubtime, site_news.news_link, 
                             site_news.news_sitefrom, site_news.news_desc, IFNULL(ATS.news_user_score, 1) as news_score, 
                             IFNULL(ATS.userid, %d) as userid FROM site_news 
                        LEFT JOIN (SELECT userid, newsid, news_user_score FROM user_score WHERE userid=%d) ATS 
                            ON site_news.news_uuid = ATS.newsid
                        WHERE DATE(site_news.time) = CURRENT_DATE()
                    ) ATT INNER JOIN user_rcd ON ATT.userid = user_rcd.userid AND ATT.news_uuid = user_rcd.newsid 
                    WHERE news_score=1 AND rcdsvd IS NOT NULL ORDER BY rcdsvd """ %(user_id, user_id)
        if sort == "0":
            sql += " DESC "
        else:
            sql += " ASC "
        sql += "LIMIT 0, 100;"
        articles = db_conn.query(sql)
        if articles:
            self.render("recsvd.html", title="readmeinfo - Recommend SVD", items=articles, sort=sort)
            return
        
        # 检查当天是否有新的新闻
        sql = """ SELECT news_uuid, time FROM site_news WHERE DATE(site_news.time)=CURRENT_DATE(); """
        uuids = db_conn.query(sql)
        if not uuids:
            self.write("今天还没有新的新闻，请稍后再尝试！")
            return
        else:
            for item in uuids:
                sql = """ SELECT rcd_uuid FROM user_rcd WHERE userid=%d AND newsid=%d; """ %(user_id, item['news_uuid'])
                if not db_conn.query(sql):
                    sql = """ INSERT INTO user_rcd(userid, newsid, date) VALUES (%d, %d, DATE('%s')); """ %(user_id, item['news_uuid'], item['time'])
                    db_conn.execute(sql)
                
            try:
                options['recsvd_queue'].put(user_id, block=True, timeout=30)
                print("Queue %d from RecSVD recommend!" %(user_id))
            except Exception as e:
                print("Queue %d from RecSVD recommend Failed!" %(user_id))
                pass
            
            self.write("今天共有%d条新闻，调度建立推荐索引，请稍后再试！" %(len(uuids)) )
        return    
   
class CacheHandler(BaseHandler):  
    @tornado.web.authenticated
    @tornado.gen.coroutine
    def get(self):
        cache_id = self.get_query_argument("id", None)
        if not cache_id:
            self.write("Internel Error!")
            return 
        
        target_os_file = "template/cached/"+cache_id
        target_td_file = "cached/"+cache_id
        
        if os.path.exists(target_os_file):
            self.write("<h3>ATTENTION: Content just been cached, all rights reserved to the original website!</h3>") 
            self.render(target_td_file)
            return
        
        sql = "SELECT news_link FROM site_news WHERE news_uuid="+cache_id+";"
        item = db_conn.get(sql)
        if not item:
            self.write("Internel Error!")
            return
        
        http_client = AsyncHTTPClient()
        try:
            response = yield http_client.fetch(item['news_link'])
        except tornado.httpclient.HTTPError as e:
            self.write("Original Server With Error: %d" %(e.code))
            return

        match = re.search(r"""(?<![-\w])              #1
                          (?:(?:en)?coding|charset)   #2
                          (?:=(["'])?([-\w]+)(?(1)\1) #3
                          |:\s*([-\w]+))""".encode("utf8"),
                                           response.body, re.IGNORECASE|re.VERBOSE)        
        encoding = match.group(match.lastindex) if match else b"utf8"
        
        try:
            with open(target_os_file, "w") as fout:
                fout.write(response.body.decode(encoding.decode("UTF-8"),'ignore'))            
                
        except Exception as e:
            self.write("Unicode convert error!")
            return
        
        self.write("<h3>ATTENTION: Content just been cached, all rights reserved to the original website!</h3>")           
        self.write(response.body.decode(encoding.decode("UTF-8"),'ignore'))        
        return
 
# JUST RESERVED FOR AJAX API
class ScoreHandler(BaseHandler):
    def post(self):
        user_id = self.current_user['user_uuid']
        news_uuid = int(self.get_argument('news_uuid'))
        score = int(self.get_argument('score'))
        sql = "SELECT score_uuid FROM user_score WHERE userid=%d AND newsid=%d ;" %(user_id, news_uuid)
        if db_conn.query(sql):
            sql = "UPDATE user_score SET news_user_score=%d WHERE userid=%d AND newsid=%d;" %(score, user_id, news_uuid)
        else:
            sql = "INSERT INTO user_score(userid, newsid, news_user_score) VALUES(%d, %d, %d);" %(user_id, news_uuid, score)
        db_conn.execute(sql)

tornado_handlers = [
        (r"/", IndexHandler),
        (r"/static/(.*)", tornado.web.StaticFileHandler, {"path": static_path}),
        (r"/register", RegisterHandler),
        (r"/login",    LoginHandler),
        (r"/logout",   LogoutHandler),
        (r"/submit",   SubmitHandler),
        (r"/cache",    CacheHandler),
        (r"/browse",   BrowseHandler),
        (r"/remaxent", ReMaxentHandler),
        (r"/resvd",    ReSVDHandler),
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
                                    options.dbuser, options.dbpass,
                                    time_zone=options.dbtimezone)
        return
    
    def run(self):
        print("TornadoThread Start....")
        AsyncHTTPClient.configure("tornado.curl_httpclient.CurlAsyncHTTPClient")
        app = tornado.web.Application(tornado_handlers, template_path=template_path, static_path=static_path, 
                                      **settings)
        app.listen(4000, address="0.0.0.0")
        tornado.ioloop.IOLoop.current().start()            
        return

    
