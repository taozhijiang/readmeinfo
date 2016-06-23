#!/usr/bin/python3
import os
import time
import datetime
import threading

import copy

import jieba
import hanzi_util
import pickle
import logging
logging.basicConfig(format='%(asctime)s : %(levelname)s : %(message)s', level=logging.INFO)

import torndb
from tornado.options import define, options

import numpy as np

from gensim import corpora, models, similarities, matutils

from utils import NLPMaster
nlp_master = NLPMaster()


class RecSvdThread(threading.Thread):
    def __init__(self):
        threading.Thread.__init__(self)  
        self.db_conn = torndb.Connection(options.dbhost, options.dbname, 
                                         options.dbuser, options.dbpass,
                                         time_zone=options.dbtimezone)
        today = datetime.date.today()
        self._user_classifier = dict()
        self.k_value = 0
        
        self.lsi = None
        self.MAX_INTEREST = 5
        self.THRESH_HOLD  = 0.5
        
        self.dumpfile = "dumpdir/recsvd_dump.%d_%d" %(today.month, today.day)
        
        if os.path.exists(self.dumpfile):
            print("dumpfile %s exists, just load it!" %(self.dumpfile))
        
            with open(self.dumpfile,'rb') as fp:
                dump_data = pickle.load(fp)
                self._user_classifier = dump_data[0]  
                self.k_value = dump_data[1]
                self.lsi = dump_data[2]
            del dump_data
        return

    def best_word_features(self, words, b_words):
        if not b_words: return None
        return [ word for word in words if word in b_words]   
        
    def _train_mode_for_user(self, userid):
        if not self.lsi:
            print("Calc SVD ....")
            self.do_calc_svd()
            
        if userid in self._user_classifier:
            print("Already exist!!!")
            self._user_classifier[userid] = dict()
        # 只需要好评和差评的，一般评论不做参考，所以INNER JOIN足够
        sql = """ SELECT site_news.news_uuid, user_score.news_user_score as news_score FROM site_news 
                        INNER JOIN user_score ON site_news.news_uuid = user_score.newsid 
                  WHERE DATE(site_news.time) < CURRENT_DATE() AND DATE(site_news.time) > DATE_SUB(CURRENT_DATE(),INTERVAL 30 DAY) 
                        AND user_score.news_user_score = 0 AND user_score.userid=%d; """ %(userid)  #好评文章
        train_items = self.db_conn.query(sql);
        
        good_lsi = []
        good_lsi_id = []
        for item in train_items:
            news_vector = nlp_master.get_old_vect(item['news_uuid']);
            good_lsi.append(self.lsi[news_vector])
            good_lsi_id.append(item['news_uuid'])
        good_idx = similarities.MatrixSimilarity(good_lsi)
        # 历史点赞文章索引建立完毕
        
        self._user_classifier[userid] = dict()
        
        best_good_id = {}
        for i in range(len(good_lsi)):
            sims = good_idx[good_lsi[i]]        # perform a similarity query against the corpus，　相似度检索
            sims = sorted(enumerate(sims), key=lambda item: -item[1])
            best_good_id[i] = [ item[0] for item in sims if item[1] > self.THRESH_HOLD ]
        
        # 计算兴趣点
        self._user_classifier[userid]['vect'] = self.extract_interests(good_lsi, best_good_id)
        
        return
    
    def prob_news(self, user_id, sent_bow):
        sent_lsi = self.lsi[sent_bow]
        sent_lsi_full = matutils.unitvec(matutils.sparse2full(sent_lsi, self.k_value))
        score = np.dot(self._user_classifier[user_id]['vect'], sent_lsi_full.T).T
        return np.max(score)

    def extract_interests(self, good_lsi, b_good_id):
        interests = []        
        while True:
            if len(interests) > self.MAX_INTEREST:
                print("已经达到最大兴趣点:%d" %(self.MAX_INTEREST))
                break
            
            max_id = 0
            max_list = []
            for k, v in b_good_id.items():
                if len(v) > len(max_list):
                    max_id = k
                    max_list = copy.deepcopy(v)
            
            if len(max_list) < 3:
                print("迭代结束！")
                break
            
            for rm_id in max_list:
                for k, v in b_good_id.items():
                    if rm_id in v:
                        v.remove(rm_id)
                        
            print("创建兴趣点：%d ~ %s" %(max_id, repr(max_list)))

            full_lsi = [ matutils.sparse2full(good_lsi[max_id], self.k_value) for id in max_list]
            full_lsi_array = np.array(full_lsi)
            interests.append(matutils.unitvec(np.average(full_lsi_array, axis=0)) )
        
        return np.array(interests)

        
    def do_calc_svd(self):
        
        print("字典长度：%d" %(nlp_master.get_dict_len()))
        self.k_value = int(0.2*(nlp_master.get_dict_len()))
        print("k值：%d" %(self.k_value))            
        
        tfidf = models.TfidfModel(list(nlp_master._id_docs.values()))
        tfidf_corpus = tfidf[list(nlp_master._id_docs.values())]
    
        # num_topics，起到降维的作用，推荐参数为 200–500
        # LSI空间
        self.lsi = models.LsiModel(tfidf_corpus, id2word=nlp_master.dictionary, num_topics=self.k_value)
        
        # 保存更新结果
        today = datetime.date.today()
        self.dumpfile = "dumpdir/recsvd_dump.%d_%d" %(today.month, today.day)        
        
        with open(self.dumpfile,'wb', -1) as fp:
            dump_data = []
            dump_data.append(self._user_classifier)
            dump_data.append(self.k_value)
            dump_data.append(self.lsi)
            pickle.dump(dump_data, fp, -1)
    
        return
            
            
    # 对插入的记录，NULL类型的
    # 增加分数外连接site_news表，对新加入的数据添加分数
    def _database_santy_check(self):
        sql = """ SELECT userid FROM user_rcd GROUP BY userid; """
        users = self.db_conn.query(sql)
        for user in users:
            sql = """ SELECT * FROM 
                          ( SELECT site_news.news_uuid, IFNULL(ATS.news_user_score, 1) as news_score, IFNULL(ATS.userid, %d) as userid, site_news.time FROM site_news 
                            LEFT JOIN (SELECT userid, newsid, news_user_score FROM user_score WHERE userid=%d) ATS 
                                ON site_news.news_uuid = ATS.newsid
                            WHERE DATE(site_news.time) = CURRENT_DATE() ) ATS
                      WHERE  ATS.news_score = 1 AND news_uuid NOT IN( SELECT newsid FROM user_rcd WHERE userid=%d AND date=CURRENT_DATE()) """ %(user['userid'], user['userid'], user['userid'])
            items = self.db_conn.query(sql)
            
            for item in items:
                sql = """ INSERT INTO user_rcd(userid, newsid, date) VALUES (%d, %d, DATE('%s')); """ %(user['userid'], item['news_uuid'], item['time'])
                self.db_conn.execute(sql)
                
        #第二步，将所有NULL进行估值计算
        sql = """ SELECT userid FROM user_rcd WHERE rcdsvd IS NULL GROUP BY userid; """
        users = self.db_conn.query(sql)
        for user in users:
            if user['userid'] not in self._user_classifier or not self._user_classifier[user['userid']]:
                print("Building RecSVD for user %d" %(user['userid']))
                self._train_mode_for_user(user['userid'])            
            
            # 没有推荐训练信息，放弃    
            if not self._user_classifier[user['userid']]:
                continue
            
            sql = """ SELECT rcd_uuid, userid, newsid FROM user_rcd WHERE userid=%d AND date=CURRENT_DATE() AND rcdsvd IS NULL; """ %(user['userid'])
            items = self.db_conn.query(sql)
            for item in items:
                vect = nlp_master.get_today_vect(item['newsid'])
                vect_r = self.best_word_features(vect, vect)
                # calc here
                ret = self.prob_news(user['userid'], vect_r)
                sql = """ UPDATE user_rcd SET rcdsvd=%f WHERE newsid=%d AND userid=%d """ %( ret, item['newsid'], user['userid'])
                self.db_conn.execute(sql)
            
        return            

    def run(self):
        print("SvdCalcThread Start....")
        
        pre_day = datetime.date.today().day        
        while True:
            
            if pre_day != datetime.date.today().day:
                nlp_master.build_wordcorpus()
                # Invalid classifer
                self.lsi = None
                self._user_classifier = dict()
                pre_day = datetime.date.today().day   
            
            break_flag = 0
            while True:    
                try:
                   # 队列中为最紧急的任务
                    it_userid = options['recsvd_queue'].get(block=True, timeout=10)
                    if it_userid not in self._user_classifier or not self._user_classifier[it_userid]:
                        print("Building RecSvd for user %d" %(it_userid))
                        self._train_mode_for_user(it_userid)

                    # 没有推荐训练信息，放弃    
                    if not self._user_classifier[it_userid]:
                        continue    
                    
                    self._train_mode_for_user(it_userid)    
                    sql = """ SELECT newsid FROM user_rcd WHERE userid=%d AND rcdsvd IS NULL AND date = CURRENT_DATE(); """ %(it_userid)
                    items = self.db_conn.query(sql)
                    for item in items:
                        vect = nlp_master.get_today_vect(item['newsid'])
                        vect_r = self.best_word_features(vect, vect)
                        # calc here
                        ret = self.prob_news(it_userid, vect_r)
                        sql = """ UPDATE user_rcd SET rcdsvd=%f WHERE newsid=%d AND userid=%d """ %( ret, item['newsid'], it_userid)
                        self.db_conn.execute(sql)
                except Exception as e:
                    break_flag = 1
                    pass
                
                if break_flag:
                    break
                
                
            #　推荐条目完整性    
            self._database_santy_check()
            
            print('RecSVDThread:A')

        return