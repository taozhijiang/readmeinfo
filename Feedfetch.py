#!/usr/bin/python3

import os
import time
import datetime
import threading

import torndb
from tornado.options import define, options

import feedparser
from bs4 import BeautifulSoup

desc_first_tag = {'jobbole.com':'p', 'ifanr.com':'p', 'williamlong.info':'p', 'pansci.asia':'p', 'zhihu.com':'p', 
                  'geekpark.net':'h2', 'dajia.qq.com':'p', '36kr.com':'p' };

class FeedfetchThread(threading.Thread):
    def __init__(self):
        threading.Thread.__init__(self)  
        self.db_conn = torndb.Connection(options.dbhost, options.dbname, 
                                         options.dbuser, options.dbpass,
                                         time_zone=options.dbtimezone)
        return
        
    def fixed_feedparser_parse(self, uri):
        try:
            return feedparser.parse(uri)
        except TypeError:
            if 'drv_libxml2' in feedparser.PREFERRED_XML_PARSERS:
                feedparser.PREFERRED_XML_PARSERS.remove('drv_libxml2')
                return feedparser.parse(uri)
            else:
                raise    
    
    def do_this_uri(self, uri):
        print('Processing: %s' %(uri))        
        d = self.fixed_feedparser_parse(uri)
        if not d.feed or 'link' not in d.feed:
            return None
        print("==> LINK: %s" %(d.feed.link))
        news_count = 0
        for item in d.entries:
            sql = """ SELECT news_link FROM site_news WHERE news_link=%s """
            if self.db_conn.execute_rowcount(sql, item.link):
                print(" Already done for %s" %(d.feed.link))
                print(" Done with[%d]" %(news_count))
                return
            if item.updated_parsed:
                tm = datetime.datetime(item.updated_parsed[0],item.updated_parsed[1],item.updated_parsed[2],
                                   item.updated_parsed[3],item.updated_parsed[4],item.updated_parsed[5])
            else:
                tm = datetime.datetime.now()
            
            # 对每个站点的description净化特殊处理
            for site_d in desc_first_tag:
                if site_d in item.link:
                    soup = BeautifulSoup(item.description, "html.parser")
                    if soup.find(desc_first_tag[site_d]):
                        item.description = soup.find(desc_first_tag[site_d]).text
            
            sql = """ INSERT INTO site_news (news_title, news_link, news_pubtime, news_desc, news_sitefrom, time) 
            VALUES (%s, %s, %s, %s, %s, NOW()) """
            self.db_conn.execute(sql, item.title, item.link, tm, item.description, d.feed.title)
            news_count += 1
            
        print(" Done with[%d]" %(news_count))
            
        return
    
    def run(self):
        print("FeedfetchThread Start....")
        
        # 每隔300秒，检查一下数据库，看最近一小时是不是还有没有爬的站点
        
        while True:
            sql = """ SELECT feed_uri FROM site_info WHERE crawl_date < DATE_SUB(NOW(),INTERVAL 5 MINUTE) and valid = 1; """
            feed_uris = self.db_conn.query(sql)
            if feed_uris:
                for item in feed_uris:
                    self.do_this_uri(item['feed_uri'])
                    sql = """ UPDATE site_info SET crawl_date=NOW() WHERE feed_uri=%s and valid = 1; """
                    self.db_conn.execute(sql, item['feed_uri'])
                    
            time.sleep(300)
            print('FeedfetchThread:A time:' + repr(datetime.datetime.now()))
            
        return


    
