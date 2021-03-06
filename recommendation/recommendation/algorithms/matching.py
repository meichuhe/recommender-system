"""
Matching阶段通过i2i/u2i/u2u/user profile等方式“粗糙”的召回候选商品，Matching阶段视频的数量是百级别了
"""
from collections import defaultdict
from concurrent import futures

from recommendation.algorithms.common.constants import MatchAlgorithmEnum
from recommendation.algorithms.recall.content_base import ContentBase
from recommendation.algorithms.recall.rule_base import RuleBase
from recommendation.dao.memory import Memory


class Matching(object):
    def __init__(self):
        self.memory = Memory()
        self.rule_base = RuleBase()
        self.content_base = ContentBase()

    def concurrent_match(self, user, num=1000):
        """ 召回
        :param user:  User Object 用户
        :param num:   int 推荐的商品个数
        :return:    list of ResultPoem Object  推荐视频列表
        """
        recall_num = num + len(user.history)  # 避免筛除历史后数量不够;每个规则召回数量必定大于此数目
        match_funcs = [
            (self.rule_base.get_popular_poems, num * 5),
        ]  # [(match_func,num)]
        with futures.ThreadPoolExecutor(max_workers=len(match_funcs)) as pool:
            to_do = [pool.submit(match_func, user, _num) for match_func, _num in match_funcs]
        result_poems = [future.result() for future in futures.as_completed(to_do)]
        matched_poems = self.filter(user=user, num=num, result_poems=result_poems)
        return matched_poems

    def filter(self, user, num, result_poems):
        """来自各个推荐算法的结果按规则组合筛选;
                1.各个算法可能推荐出相同视频，需要在此去重
                2.每个召回算法召回num个feed，总数为n*num个feed，过滤后留下num个
        :param user:  User Object 用户
        :param num:   int 推荐的商品个数
        :param result_poems: list of ResultPoem Object list；[[ResultPoem,ResultPoem],[ResultPoem,ResultPoem]]
        :return:  list of ResultPoem Object；[ResultPoem,ResultPoem，ResultPoem]
        """
        poem_queues = defaultdict(list)
        for _poems in result_poems:
            for _feed in _poems:
                poem_id = _feed.poem_id
                if poem_id not in user.history:  # 剔除观看历史
                    poem_queues[_feed.match_algorithm].append(_feed)
        _result_poems = []
        all_poem_ids = set()
        algorithm_count = defaultdict(int)
        queue_empty_count = 0
        while len(_result_poems) < num and queue_empty_count < len(poem_queues):  # 若某一算法视频缺失，使用高优先级算法填补
            queue_empty_count = 0
            for _algorithm, _proportion in MatchAlgorithmEnum:  # 顺序即是优先级
                if _proportion and len(_result_poems) < num:
                    start_pos = algorithm_count[_algorithm]  # 开始位置，跳过已取出的视频
                    needed_count = int(num * _proportion)  # 当前算法按比例应该取出多少视频
                    get_count = 0
                    if start_pos < len(poem_queues[_algorithm]):
                        for feed in poem_queues[_algorithm][start_pos:]:
                            algorithm_count[_algorithm] += 1  # 更新已取出的视频数作为下一次开始位置
                            if feed.poem_id not in all_poem_ids:
                                _result_poems.append(feed)
                                get_count += 1
                                all_poem_ids.add(feed.poem_id)
                                if get_count >= needed_count:
                                    break
                    else:
                        queue_empty_count += 1
        return _result_poems
