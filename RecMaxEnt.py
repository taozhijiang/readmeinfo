#!/usr/bin/python3

# 最大熵推荐模块
import jieba
import hanzi_util
import pickle
import os
import time
import datetime
import threading

import torndb
from tornado.options import define, options

# 统计词频
from nltk.probability import FreqDist, ConditionalFreqDist
from nltk.metrics import BigramAssocMeasures
from nltk.classify import MaxentClassifier


from utils import NLPMaster
nlp_master = NLPMaster()


class RecMaxEntThread(threading.Thread):
    def __init__(self):
        threading.Thread.__init__(self)  
        self.db_conn = torndb.Connection(options.dbhost, options.dbname, 
                                         options.dbuser, options.dbpass,
                                         time_zone=options.dbtimezone)
        today = datetime.date.today()
        self.dumpfile = "dumpdir/recmaxent_dump.%d_%d" %(today.month, today.day)
        self._user_classifier = dict()
        
        if os.path.exists(self.dumpfile):
            print("dumpfile %s exists, just load it!" %(self.dumpfile))
        
            with open(self.dumpfile,'rb') as fp:
                dump_data = pickle.load(fp)
                self._user_classifier = dump_data[0]  
        return
    
    def best_word_features(self, words, b_words):
        if not b_words: return None
        return dict([ word for word in words if word in b_words])
    
    def _train_mode_for_user(self, userid):
        if userid in self._user_classifier:
            print("Already exist!!!")
            self._user_classifier[userid] = None
        # 只需要好评和差评的，一般评论不做参考，所以INNER JOIN足够
        sql = """ SELECT site_news.news_uuid, user_score.news_user_score as news_score FROM site_news 
                        INNER JOIN user_score ON site_news.news_uuid = user_score.newsid 
                  WHERE DATE(site_news.time) < CURRENT_DATE() AND DATE(site_news.time) > DATE_SUB(CURRENT_DATE(),INTERVAL 30 DAY) 
                        AND user_score.news_user_score != 1 AND user_score.userid=%d; """ %(userid)
        train_items = self.db_conn.query(sql);

        print("建立POS/NEG特征")
        pos_feature = []
        neg_feature = []        
        for item in train_items:
            news_vector = nlp_master.get_old_vect(item['news_uuid']);
            if item['news_score'] == 0: #好评
                pos_feature.append((self.best_word_features(news_vector, news_vector),'pos'))
            elif item['news_score'] == 2: #差评
                neg_feature.append((self.best_word_features(news_vector, news_vector),'neg'))
        print("POS:%d, NEG:%d" %(len(pos_feature),len(neg_feature)))
        
        if len(pos_feature) <= 3 or len(neg_feature) <=3:
            print("特征太少，放弃。。。")
            self._user_classifier[userid] = None
            return
        
        trainSet = pos_feature + neg_feature
        self._user_classifier[userid] = MaxentClassifier.train(trainSet, max_iter=50)
        print("MaxEnt Classifier for %d build done!"%(userid))

        # 保存更新结果
        today = datetime.date.today()
        self.dumpfile = "dumpdir/recmaxent_dump.%d_%d" %(today.month, today.day)
        with open(self.dumpfile,'wb', -1) as fp:
            dump_data = []
            dump_data.append(self._user_classifier)
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
        sql = """ SELECT userid FROM user_rcd WHERE rcdmaxent IS NULL GROUP BY userid; """
        users = self.db_conn.query(sql)
        for user in users:
            if user['userid'] not in self._user_classifier or not self._user_classifier[user['userid']]:
                print("Building RecMaxEnt for user %d" %(user['userid']))
                self._train_mode_for_user(user['userid'])            
            
            # 没有推荐训练信息，放弃    
            if not self._user_classifier[user['userid']]:
                continue
            
            sql = """ SELECT rcd_uuid, userid, newsid FROM user_rcd WHERE userid=%d AND date=CURRENT_DATE() AND rcdmaxent IS NULL; """ %(user['userid'])
            items = self.db_conn.query(sql)
            for item in items:
                vect = nlp_master.get_today_vect(item['newsid'])
                vect_r = self.best_word_features(vect, vect)
                # calc here
                ret = self._user_classifier[user['userid']].prob_classify(vect_r)
                sql = """ UPDATE user_rcd SET rcdmaxent=%f WHERE newsid=%d AND userid=%d """ %( ret.prob('pos'), item['newsid'], user['userid'])
                self.db_conn.execute(sql)
            
        return
    
    def run(self):
        print("RecMaxEntThread Start....")
        
        pre_day = datetime.date.today().day        
        while True:

            if pre_day != datetime.date.today().day:
                nlp_master.build_wordcorpus()
                # Invalid classifer
                self._user_classifier = dict()
                pre_day = datetime.date.today().day   
            
            break_flag = 0
            while True:    
                try:
                    # 队列中为最紧急的任务
                    it_userid = options['recmaxent_queue'].get(block=True, timeout=120)
                    if it_userid not in self._user_classifier or not self._user_classifier[it_userid]:
                        print("Building RecMaxEnt for user %d" %(it_userid))
                        self._train_mode_for_user(it_userid)

                    # 没有推荐训练信息，放弃    
                    if not self._user_classifier[it_userid]:
                        continue                    
                        
                    sql = """ SELECT newsid FROM user_rcd WHERE userid=%d AND rcdmaxent IS NULL AND date=CURRENT_DATE(); """ %(it_userid)
                    items = self.db_conn.query(sql)
                    for item in items:
                        vect = nlp_master.get_today_vect(item['newsid'])
                        vect_r = self.best_word_features(vect, vect)
                        # calc here
                        ret = self._user_classifier[it_userid].prob_classify(vect_r)
                        sql = """ UPDATE user_rcd SET rcdmaxent=%f WHERE newsid=%d AND userid=%d """ %( ret.prob('pos'), item['newsid'], it_userid)
                        self.db_conn.execute(sql)
                except Exception as e:
                    break_flag = 1
                    pass
                
                if break_flag:
                    break
            #　推荐条目完整性    
            self._database_santy_check()
            
            print('RecMaxEntThread:A time:' + repr(datetime.datetime.now()))

        return