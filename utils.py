#!/usr/bin/python3 

import time
import os
import pickle
import feedparser
import datetime

import torndb
from tornado.options import define, options

import jieba

def utc2local (utc):
    epoch = time.mktime(utc.timetuple())
    offset = datetime.datetime.fromtimestamp(epoch) - datetime.datetime.utcfromtimestamp(epoch)
    return utc + offset

def fixed_feedparser_parse(uri):
    try:
        return feedparser.parse(uri)
    except TypeError:
        if 'drv_libxml2' in feedparser.PREFERRED_XML_PARSERS:
            feedparser.PREFERRED_XML_PARSERS.remove('drv_libxml2')
            return feedparser.parse(uri)
        else:
            raise  
        
# NLP Global Data
class NLPMaster():
    def __init__(self):
        today = datetime.date.today()
        self.stopfile = "stopwords.txt"
        self.dumpfile = "dumpdir/nlpmaster_dump.%d_%d" %(today.month, today.day)
        
        self._train_word_id = ['NULL']    
        self._stop_words = set()
        self._id_docs = dict()
        self._cached_today = dict()  #今日新闻的缓存
        self.db_conn = torndb.Connection(options.dbhost, options.dbname, 
                                         options.dbuser, options.dbpass,
                                         time_zone=options.dbtimezone)
        
        if os.path.exists(self.dumpfile):
            print("dumpfile %s exists, just load it!" %(self.dumpfile))

            with open(self.dumpfile,'rb') as fp:
                dump_data = pickle.load(fp)
                self._train_word_id = dump_data[0]
                self._stop_words = dump_data[1]
                self._id_docs = dump_data[2]            
            
        else:
            print("Do the fresh nlp master!")
            self.build_wordcorpus()
            
            with open(self.dumpfile,'wb', -1) as fp:
                dump_data = []
                dump_data.append(self._train_word_id)
                dump_data.append(self._stop_words)
                dump_data.append(self._id_docs)
                pickle.dump(dump_data, fp, -1)           
        
        return 
        
    def get_today_vect(self, news_id):
        if news_id in self._cached_today:
            return self._cached_today[news_id]
        else:
            sql = """ SELECT news_title, news_desc FROM site_news WHERE news_uuid=%d;""" %(news_id)
            item = self.db_conn.get(sql)
            if item:
                str_l = item['news_title'] + " " + item['news_desc']
                seg_list = list(jieba.cut(str_l, cut_all=False))
                while '' in seg_list:
                    seg_list.remove('')
                tmp_col = []
                for i in seg_list:
                    if i in self._stop_words:
                        continue
                    if i[0] in '0123456789':
                        continue
                    i_id = self._term2id(i)
                    tmp_col.append(i_id) 
                self._cached_today[news_id] = tmp_col
                return self._cached_today[news_id]
            return None
    
    def _term2id(self, term):
        if term not in self._train_word_id:
            self._train_word_id.append(term)
        voca_id = self._train_word_id.index(term)
        return voca_id    
    
    def term2id(self, term):
        if term not in self._train_word_id:
            return 0
        return self._train_word_id.index(term)

    def build_wordcorpus(self):
        with open(self.stopfile, 'r') as fin:
            for line in fin:
                line = line.strip()
                self._stop_words.add(line)        
    
        sql = """ SELECT news_uuid, news_title, news_desc FROM site_news WHERE DATE(time) < CURRENT_DATE() AND DATE(time) > DATE_SUB(CURRENT_DATE(),INTERVAL 5 DAY); """
        items = self.db_conn.query(sql)
        for item in items:
            str_l = item['news_title'] + " " + item['news_desc']
            seg_list = list(jieba.cut(str_l, cut_all=False))
            while '' in seg_list:
                seg_list.remove('')
            tmp_col = []
            for i in seg_list:
                if i in self._stop_words:
                    continue
                if i[0] in '0123456789':
                    continue
                i_id = self._term2id(i)
                tmp_col.append(i_id) 
            self._id_docs[item['news_uuid']] = tmp_col
            
        print("Dump the dat to file")
        today = datetime.date.today()
        self.dumpfile = "dumpdir/nlpmaster_dump.%d_%d" %(today.month, today.day)
        with open(self.dumpfile,'wb', -1) as fp:
            dump_data = []
            dump_data.append(self._train_word_id)
            dump_data.append(self._stop_words)
            dump_data.append(self._id_docs)
            pickle.dump(dump_data, fp, -1)             
        return
    
    def get_old_vect(self, news_id):
        if news_id in self._id_docs:
            return self._id_docs[news_id]
        else:
            return None
        
    def is_stop_word(self, word):
        if word in self._stop_words:
            return True
        else:
            return False
    
