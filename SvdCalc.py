#!/usr/bin/python3
import os
import time
import datetime
import threading

import jieba
import hanzi_util
import pickle
import logging
logging.basicConfig(format='%(asctime)s : %(levelname)s : %(message)s', level=logging.INFO)

import torndb
from tornado.options import define, options

from gensim import corpora, models, similarities

class SvdCalcThread(threading.Thread):
    def __init__(self):
        threading.Thread.__init__(self)  
        self.db_conn = torndb.Connection(options.dbhost, options.dbname, 
                                         options.dbuser, options.dbpass)
        today = datetime.date.today()
        self.dumpfile = "svddump.%d_%d" %(today.month, today.day)
        self.stopfile = "stopwords.txt"

        self.k_value = 0;
        self.dictionary = None
        self.lsi = None
        self.index = None
        self.docid = None
        
        self.do_load_svd()
        return

    def do_calc_svd(self):
        stop_words = set()
        with open(self.stopfile, 'r') as fin:
            for line in fin:
                line = line.strip()
                stop_words.add(line)        
        
        docs = []
        self.docid = []
        # 从数据库加载数据，按照入库的时间计算
        sql = """ SELECT uuid, news_desc FROM site_news WHERE time < DATE_SUB(NOW(),INTERVAL 1 HOUR) AND time > DATE_SUB(NOW(),INTERVAL 8 DAY)"""
        items = self.db_conn.query(sql)
        for item in items:
            seg_list = list(jieba.cut(item['news_desc'], cut_all=False))
            while '' in seg_list:
                seg_list.remove('')
            line_t = [ x for x in seg_list if x not in stop_words and x[0] not in '0123456789' ]
            docs.append(line_t)
            self.docid.append(item['uuid'])
            
        self.dictionary = corpora.Dictionary(docs)
        self.k_value = 250
        print("字典大小:%d" %(len(self.dictionary)))
        print("k值：%d" %(int(self.k_value)))            
            
        corpus = [self.dictionary.doc2bow(doc) for doc in docs]
        
        tfidf = models.TfidfModel(corpus)
        tfidf_corpus = tfidf[corpus]
    
        # num_topics，起到降维的作用，推荐参数为 200–500
        self.lsi = models.LsiModel(tfidf_corpus, id2word=self.dictionary, num_topics=int(self.k_value))
        self.index = similarities.MatrixSimilarity(self.lsi[corpus]) # transform corpus to LSI space and index it
    
        del docs            
        
        if len(self.index) != len(self.docid):
            print("!!!!!!!!!!!BUGBUGBUG!!!!!!!!!!!!!!!!")
            
        return
            

    def do_load_svd(self):
        if os.path.exists(self.dumpfile):
            print("dumpfile %s exists, just load it!" %(self.dumpfile))

            with open(self.dumpfile,'rb') as fp:
                dump_data = pickle.load(fp)
                self.k_value = dump_data[0]
                self.dictionary = dump_data[1]
                self.lsi = dump_data[2]
                self.index = dump_data[3]
                self.docid = dump_data[4]                 
            
        else:
            print("Do the fresh svd calc!")
            self.do_calc_svd()
            
            with open(self.dumpfile,'wb', -1) as fp:
                dump_data = []
                dump_data.append(self.k_value)
                dump_data.append(self.dictionary)
                dump_data.append(self.lsi)
                dump_data.append(self.index)
                dump_data.append(self.docid)
                pickle.dump(dump_data, fp, -1)            
    
    
    def run(self):
        print("SvdCalcThread Start....")
        
        
        pre_day = datetime.date.today().day        
        while True:
            
            if pre_day != datetime.date.today().day:
                print("!!!Haviy Calc Here!!!")
                self.do_load_svd()
                pre_day = datetime.date.today().day            
                
            time.sleep(20)

        return