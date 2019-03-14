# -*- coding:utf-8 -*-

from flask import render_template, jsonify
from flask.globals import session, request, g, current_app
from zs_backend.busi import busi
from zs_backend.utils.channel_qry import GameWeb, LogQry
from zs_backend.utils.common import login_require
from zs_backend.utils import time_util
from zs_backend.busi import game_parameter
from zs_backend import SqlOperate
import json
from zs_backend.utils.log_table import *

items_dict = {20010001: u'喇叭'}


@busi.route('/games/datas/rt', methods=['GET'])
@login_require
def rt():
    channel = session['select_channel']

    today0 = time_util.today0()

    ## 今日充值
    sql = '''
        select ifnull(sum(cost), 0)
        from admin_recharge
        where time >= %d and state = 1
    ''' % today0
    recharge = LogQry(channel).qry(sql)[0][0]

    ## todo 今日提现
    withdraw = 0

    ## 在线人数
    onlinenum = GameWeb(channel).post("/api/online_num", {})['result']

    ## 注册人数
    sql = '''
        select count(1)
        from log_role_reg
        where time >= %d
    ''' % today0
    reg_count = LogQry(channel).qry(sql)[0][0]

    ## 活跃人数
    sql = '''
        select count(distinct pid)
        from log_account_login
        where time >= %d
    ''' % today0
    active_count = LogQry(channel).qry(sql)[0][0]

    ## ##玩家总押注 玩家总产出 全服总税收
    sql = '''
        select ifnull(sum(pump), 0), ifnull(sum(stake_coin), 0), ifnull(sum(output_coin), 0)
        from %s
        where time >= %d
    ''' % (get_table_log_subgame(today0), today0)
    (pump1, stake, output) = LogQry(channel).qry(sql)[0]

    sql = '''
        select ifnull(sum(pump), 0)
        from log_bank_give
        where time >= %d
    ''' % today0
    pump2 = LogQry(channel).qry(sql)[0][0]
    pump = pump1 + pump2

    ## 查询代理
    sql = '''
        select pid
        from admin_agent_list
    '''
    agentlist = [x[0] for x in LogQry(channel).qry(sql)]

    ## 统计玩家身上金币 银行金币
    sql = 'select ifnull(sum(coin + lottery), 0) from player'
    total_coin = int(LogQry(channel).qry(sql)[0][0])
    sql = 'select ifnull(sum(coin + lottery), 0) from player where id in (select pid from admin_agent_list) '
    agent_coin = int(LogQry(channel).qry(sql)[0][0])
    player_coin = total_coin - agent_coin

    ## 查询代理卖分
    sql = '''
        select ifnull(sum(money), 0)
        from log_bank_give
        where give_agent = 1 and recv_agent = 0
        and time > %d
    ''' % today0
    agent_sell = LogQry(channel).qry(sql)[0][0]

    ## 代理买分
    sql = '''
        select ifnull(sum(money), 0)
        from log_bank_give
        where give_agent = 0 and recv_agent = 1
        and time > %d
    ''' % today0
    agent_buy = LogQry(channel).qry(sql)[0][0]

    ## 游戏活跃人数
    sql = '''
        select count(distinct pid)
        from %s
        where time >= %d
    ''' % (get_table_log_player_subgame(today0), today0)
    game_active_count = LogQry(channel).qry(sql)[0][0]

    data = {"recharge": int(recharge), "withdraw": int(withdraw), "onlinenum": onlinenum,
            "reg_count": int(reg_count), "active_count": int(active_count),
            "stake": int(stake), "output": int(output), "player_coin": int(player_coin),
            "agent_coin": int(agent_coin), "agent_sell": int(agent_sell),
            "agent_buy": int(agent_buy), "pump": int(pump),
            "game_active_count": game_active_count}

    return jsonify(data)

@busi.route('/games/datas', methods=['GET'])
@login_require
def get_game_data():
    status_msg = dict()
    status_msg['beginDate'] = 7
    status_msg['endDate'] = True

    return render_template('data_daily.html', status_msg=status_msg)


## 查询当日系统数据
def search_daily_data_today():
    start = request.args.get('beginDate', '')
    channel = session['select_channel']
    today0 = time_util.today0()

    pre_record = {}
    pre_record['date_text'] = start

    # 注册人数
    sql = '''
        select count(1)
        from log_role_reg
        where time >= %d
    ''' % (today0)
    pre_record['reg_count'] = LogQry(channel).qry(sql)[0][0]

    # 活跃人数 登录次数统计
    sql = '''
        select count(distinct pid), count(pid)
        from log_account_login
        where time >= %d
    ''' % (today0)
    pre_record['active_count'], pre_record['login_count'] = LogQry(channel).qry(sql)[0]

    sql = '''
        select count(1), ifnull(sum(cost), 0), ifnull(sum(coin), 0)
        from admin_recharge
        where time >= %d
        and state = 1
    ''' % (today0)
    pre_record['recharge_count'], pre_record['total_recharge'], pre_record['recharge_coin'] = \
        LogQry(channel).qry(sql)[0]
    pre_record['total_recharge'], pre_record['recharge_coin'] = float(pre_record['total_recharge']), float(
        pre_record['recharge_coin'])

    # todo  日破产人数   日破产次数   提现总额
    pre_record['bankrupt_player_count'] = 0
    pre_record['bankrupt_count'] = 0
    pre_record['withdraw'] = 0

    # 游戏抽水 游戏总盈亏
    sql = '''
        select ifnull(sum(pump), 0), ifnull(sum(ai_coin), 0)
        from %s
        force index(time)
        where time >= %d
    ''' % (get_table_log_subgame(today0), today0)
    pre_record['pump'], pre_record['game_win'] = LogQry(channel).qry(sql)[0]
    pre_record['pump'], pre_record['game_win'] = float(pre_record['pump']), float(pre_record['game_win'])

    ## 赠送抽水
    sql = '''
        select ifnull(sum(pump), 0)
        from log_bank_give
        force index(time)
        where time >= %d
    ''' % today0
    give_pump = LogQry(channel).qry(sql)[0][0]
    pre_record['pump'] += give_pump
    pre_record['pump'] = float(pre_record['pump'])

    ## 2日留存
    pre_record['day2'] = 0

    ## 3日留存
    pre_record['day3'] = 0

    ## 7日留存
    pre_record['day7'] = 0

    ## 15日留存
    pre_record['day15'] = 0

    ## 30日留存
    pre_record['day30'] = 0

    # 日人均线时长
    pre_record['avg_online_time'] = 0
    sql = '''
        select ifnull(sum(online_time), 0)
        from log_account_login
        where time >= %d
        and opt = "account_logout"
    ''' % (today0)
    if pre_record['active_count'] > 0:
        pre_record['avg_online_time'] = int(LogQry(channel).qry(sql)[0][0] / pre_record['active_count'])

    # 最高在线人数
    sql = '''
        select ifnull(max(num), 0)
        from log_online
        where time >= %d
    ''' % (today0)
    pre_record['max_online_num'] = LogQry(channel).qry(sql)[0][0]

    pre_record['active_arpu'] = 0
    pre_record['active_arppu'] = 0
    if pre_record['active_count'] > 0:
        pre_record['active_arpu'] = pre_record['total_recharge'] / pre_record['active_count']
    if pre_record['recharge_count'] > 0:
        pre_record['active_arpu'] = pre_record['total_recharge'] / pre_record['recharge_count']

    ## 游戏活跃人数
    sql = '''
        select count(distinct pid)
        from %s
        where time >= %d
    ''' % (get_table_log_player_subgame(today0), today0)
    game_active_count = LogQry(channel).qry(sql)[0][0]
    pre_record['game_active_count'] = game_active_count

    ## 新增设备数
    sql = '''
        select count(distinct did)
        from player
        where reg_time >= %d
        and did not in 
        (select distinct did from player where reg_time < %d)
    ''' % (today0, today0)
    pre_record['new_device'] = LogQry(channel).qry(sql)[0][0]

    ## 赠送
    sql = '''
        select if(give_agent = 0, 'p', 'a'), if(recv_agent = 0, 'p', 'a'), count(1), 
                ifnull(sum(money), 0), ifnull(sum(pump), 0), 
            count(distinct give_id), count(distinct recv_id)
        from log_bank_give
        where time >= %d and time <= %d
        group by give_agent, recv_agent
    ''' % (today0, today0)
    Result = LogQry(channel).qry(sql)
    for give_agent, recv_agent, give_times, give_coin, give_pump, \
        give_player_num, recv_coin_player_num in Result:
        Data = {
            "give_times": int(give_times), "give_coin": int(give_coin),
            "give_pump": int(give_pump), "give_player_num": int(give_player_num),
            "recv_coin_player_num": int(give_player_num)
        }
        pre_record["give_coin_%s2%s" % (give_agent, recv_agent)] = json.dumps(Data)

    return jsonify(result='ok', data=[pre_record])


@busi.route('/search/daily/datas', methods=['GET'])
@login_require
def search_daily_data():
    ## 计算留存
    def calc_liucun(d, t, reg_num, offset):
        nt = time_util.date_add(t, offset - 1)
        if nt in d and reg_num > 0:
            return int(d[nt][offset] * 100 / reg_num)
        return 0

    start = request.args.get('beginDate', '')
    end = request.args.get('endDate', '')
    channel = session['select_channel']

    start_date = time_util.formatDatestamp(start)
    end_date = time_util.formatDatestamp(end)
    today0 = time_util.today0()
    if start_date == today0 and end_date == today0:
        return search_daily_data_today()

    if start_date > end_date:
        return jsonify(result='fail', msg=u'结束时间不能小于开始时间！')

    start_date = int(time_util.formatTimeWithDesc(start_date, "%Y%m%d"))
    end_date = int(time_util.formatTimeWithDesc(end_date, "%Y%m%d"))

    sql = '''
        select time, sum(day2), sum(day3), sum(day7), sum(day15), sum(day30)
        FROM t_system 
        group by time;
    '''
    reg_count_d = {}
    for time, day2, day3, day7, day15, day30 in LogQry(channel).qry(sql):
        reg_count_d[time] = {2: float(day2), 3: float(day3), 7: float(day7), 15: float(day15), 30: float(day30)}

    search_sql = """
        SELECT time, sum(reg_count), sum(active_count), sum(login_count), sum(recharge_count), 
            sum(bankrupt_player_count), sum(bankrupt_count), sum(total_recharge), sum(game_win), sum(pump), 
            sum(recharge_coin), sum(withdraw), sum(day2), sum(day3), sum(day7), 
            sum(day15), sum(day30), sum(total_online_time), sum(max_online_num), sum(give_pump),
            sum(new_device), sum(game_active_count), give_coin_a2p, give_coin_p2a
        FROM t_system 
        WHERE time>=%d AND time<=%d 
        group by time;
    """ % (start_date, end_date)

    allday_search_data = []
    pre_date = 0
    pre_os = 0
    pre_record = {}
    for search_data in LogQry(channel).qry(search_sql):
        pre_record = dict()
        pre_record['date_text'] = time_util.date_str(search_data[0])
        pre_record['reg_count'] = float(search_data[1])
        pre_record['active_count'] = float(search_data[2])
        pre_record['login_count'] = float(search_data[3])
        pre_record['recharge_count'] = float(search_data[4])

        pre_record['bankrupt_player_count'] = float(search_data[5])
        pre_record['bankrupt_count'] = float(search_data[6])
        pre_record['total_recharge'] = float(search_data[7])
        pre_record['game_win'] = float(search_data[8])
        pre_record['pump'] = float(search_data[9] + search_data[19])

        pre_record['recharge_coin'] = float(search_data[10])
        pre_record['withdraw'] = float(search_data[11])
        pre_record['day2'] = calc_liucun(reg_count_d, search_data[0], float(search_data[1]), 2)
        pre_record['day3'] = calc_liucun(reg_count_d, search_data[0], float(search_data[1]), 3)
        pre_record['day7'] = calc_liucun(reg_count_d, search_data[0], float(search_data[1]), 7)

        pre_record['day15'] = calc_liucun(reg_count_d, search_data[0], float(search_data[1]), 15)
        pre_record['day30'] = calc_liucun(reg_count_d, search_data[0], float(search_data[1]), 30)
        pre_record['avg_online_time'] = 0
        if search_data[2] > 0:
            pre_record['avg_online_time'] = int(search_data[17] / search_data[2])
        pre_record['max_online_num'] = float(search_data[18])
        pre_record['active_arpu'] = 0
        pre_record['active_arppu'] = 0
        if search_data[2] > 0:
            pre_record['active_arpu'] = pre_record['total_recharge'] / float(search_data[2])
        if search_data[4] > 0:
            pre_record['active_arpu'] = pre_record['total_recharge'] / float(search_data[4])

        pre_record["new_device"] = float(search_data[20])
        pre_record["game_active_count"] = float(search_data[21])
        pre_record["give_coin_a2p"] = search_data[22]
        pre_record["give_coin_p2a"] = search_data[23]
        allday_search_data.append(pre_record)

    return jsonify(result='ok', data=allday_search_data)


@busi.route('/daily/datas/detail', methods=['GET'])
@login_require
def get_daily_data_detail():
    status_msg = {}
    status_msg['beginDate'] = True
    status_msg['endDate'] = False

    page = {}
    page["yesterday"] = [0 for x in range(0, 24)]
    page["currday"] = page["yesterday"]

    return render_template('data_daily_detail.html',
                           status_msg=status_msg, datas=[], page=page)


@busi.route('/search/daily/datas/detail', methods=['GET'])
@login_require
def search_daily_data_detail():
    start1 = request.args.get('beginDate')
    start2 = request.args.get('endDate')
    channel = session['select_channel']

    start_timeStamp_1 = time_util.formatDatestamp(start1)
    end_timeStamp_1 = start_timeStamp_1 + 86400

    datas1 = []
    while start_timeStamp_1 < end_timeStamp_1:
        day_data_dict = {}

        # 时间
        day_data_dict['time'] = time_util.formatTimeWithDesc(start_timeStamp_1, "%H")

        # 注册人数
        retrieve_sql = """SELECT count(1)
                          FROM log_role_reg
                          WHERE time>=%s
                          AND time<%s;""" \
                       % (start_timeStamp_1, start_timeStamp_1 + 3600)
        day_data_dict['reg_count'] = LogQry(channel).qry(retrieve_sql)[0][0]

        # 登录
        retrieve_sql = """SELECT count(distinct pid),count(1)
                          FROM log_account_login
                          force index(time)
                          WHERE time>=%s
                          AND time<%s;""" \
                       % (start_timeStamp_1, start_timeStamp_1 + 3600)
        day_data_dict['active_count'], day_data_dict['login_count'] = LogQry(channel).qry(retrieve_sql)[0]

        # 充值
        retrieve_sql = """SELECT count(distinct pid),ifnull(sum(cost),0)
                          FROM admin_recharge
                          WHERE time>=%s
                          AND time<=%s
                          AND state=1;""" \
                       % (start_timeStamp_1, start_timeStamp_1 + 3600)
        day_data_dict['recharge_count'], day_data_dict['total_recharge'] = LogQry(channel).qry(retrieve_sql)[0]
        day_data_dict['total_recharge'] = float(day_data_dict['total_recharge'])

        # 新增充值
        retrieve_sql = """SELECT count(distinct pid)
                          FROM admin_recharge
                          WHERE time >=%s
                          AND time<=%s
                          AND state=1
                          AND pid NOT IN (select pid from admin_recharge where state=1 and time<%s);""" \
                       % (start_timeStamp_1, start_timeStamp_1 + 3600, start_timeStamp_1)
        day_data_dict['new_recharge_count'] = LogQry(channel).qry(retrieve_sql)[0][0]

        # 游戏盈亏
        day_data_dict['game_win'] = 0
        day_data_dict['pump'] = 0
        retrieve_sql = """SELECT ifnull(sum(ai_coin),0),ifnull(sum(pump),0),ifnull(sum(stake_coin),0),ifnull(sum(output_coin),0)
                          FROM %s
                          force index(time)
                          WHERE time>=%s
                          AND time<=%s;""" \
                       % (get_table_log_subgame(start_timeStamp_1), start_timeStamp_1, start_timeStamp_1 + 3600)
        day_data_dict['game_win'], day_data_dict['pump'], day_data_dict['total_stake'], day_data_dict['total_output'] = \
            LogQry(channel).qry(retrieve_sql)[0]
        day_data_dict['game_win'] = float(day_data_dict['game_win'])
        day_data_dict['pump'] = float(day_data_dict['pump'])
        day_data_dict['total_stake'] = float(day_data_dict['total_stake'])
        day_data_dict['total_output'] = float(day_data_dict['total_output'])

        # TODO 提现
        day_data_dict['withdraw'] = 0

        # 最高在线
        retrieve_sql = """SELECT ifnull(max(num),0)
                          FROM (select sum(num) as num from log_online where time>=%s and time<%s group by time) AS a;""" \
                       % (start_timeStamp_1, start_timeStamp_1 + 3600)
        day_data_dict['max_online_num'] = LogQry(channel).qry(retrieve_sql)[0][0]
        day_data_dict['max_online_num'] = float(day_data_dict['max_online_num'])

        datas1.append(day_data_dict)
        start_timeStamp_1 += 3600

    start_timeStamp_2 = time_util.formatDatestamp(start2)
    end_timeStamp_2 = start_timeStamp_2 + 86400

    datas2 = []
    while start_timeStamp_2 < end_timeStamp_2:
        day_data_dict = {}

        # 时间
        day_data_dict['time'] = time_util.formatTimeWithDesc(start_timeStamp_2, "%H")

        # 注册人数
        retrieve_sql = """SELECT count(1)
                          FROM log_role_reg
                          WHERE time>=%s
                          AND time<%s;""" \
                       % (start_timeStamp_2, start_timeStamp_2 + 3600)
        day_data_dict['reg_count'] = LogQry(channel).qry(retrieve_sql)[0][0]

        # 登录
        retrieve_sql = """SELECT count(distinct pid),count(1)
                          FROM log_account_login
                          force index(time)
                          WHERE time>=%s
                          AND time<%s;""" \
                       % (start_timeStamp_2, start_timeStamp_2 + 3600)
        day_data_dict['active_count'], day_data_dict['login_count'] = LogQry(channel).qry(retrieve_sql)[0]

        # 充值
        retrieve_sql = """SELECT count(distinct pid),ifnull(sum(cost),0)
                          FROM admin_recharge
                          WHERE time>=%s
                          AND time<=%s
                          AND state=1;""" \
                       % (start_timeStamp_2, start_timeStamp_2 + 3600)
        day_data_dict['recharge_count'], day_data_dict['total_recharge'] = LogQry(channel).qry(retrieve_sql)[0]
        day_data_dict['total_recharge'] = float(day_data_dict['total_recharge'])

        # 新增充值
        retrieve_sql = """SELECT count(distinct pid)
                          FROM admin_recharge
                          WHERE time >=%s
                          AND time<=%s
                          AND state=1
                          AND pid NOT IN (select pid from admin_recharge where state=1 and time<%s);""" \
                       % (start_timeStamp_2, start_timeStamp_2 + 3600, start_timeStamp_2)
        day_data_dict['new_recharge_count'] = LogQry(channel).qry(retrieve_sql)[0][0]

        # 游戏盈亏
        day_data_dict['game_win'] = 0
        day_data_dict['pump'] = 0
        retrieve_sql = """SELECT ifnull(sum(ai_coin),0),ifnull(sum(pump),0),ifnull(sum(stake_coin),0),ifnull(sum(output_coin),0)
                          FROM %s
                          force index(time)
                          WHERE time>=%s
                          AND time<=%s;""" \
                       % (get_table_log_subgame(start_timeStamp_2), start_timeStamp_2, start_timeStamp_2 + 3600)
        day_data_dict['game_win'], day_data_dict['pump'], day_data_dict['total_stake'], day_data_dict['total_output'] = \
            LogQry(channel).qry(retrieve_sql)[0]
        day_data_dict['game_win'] = float(day_data_dict['game_win'])
        day_data_dict['pump'] = float(day_data_dict['pump'])
        day_data_dict['total_stake'] = float(day_data_dict['total_stake'])
        day_data_dict['total_output'] = float(day_data_dict['total_output'])

        # TODO 提现
        day_data_dict['withdraw'] = 0

        # 最高在线
        retrieve_sql = """SELECT ifnull(max(num), 0)
                          FROM (select sum(num) as num from log_online where time>=%s and time<%s group by time) AS a;""" \
                       % (start_timeStamp_2, start_timeStamp_2 + 3600)
        day_data_dict['max_online_num'] = LogQry(channel).qry(retrieve_sql)[0][0]
        day_data_dict['max_online_num'] = float(day_data_dict['max_online_num'])

        datas2.append(day_data_dict)
        start_timeStamp_2 += 3600

    return jsonify(result='ok', data1=datas1, data2=datas2)


@busi.route('/sub_game/datas', methods=['GET'])
@login_require
def get_sub_data():
    status_msg = dict()
    status_msg['beginDate'] = 11
    status_msg['endDate'] = 11

    return render_template('data_subgame.html', status_msg=status_msg)


## 查询当日子游戏数据
def search_subgame_data_today():
    start = request.args.get('beginDate', '')
    channel = session['select_channel']

    start_date = time_util.formatDatestamp(start)

    sql = '''
        select gameid, count(1), ifnull(sum(pump), 0), ifnull(sum(stake_coin), 0), ifnull(sum(output_coin), 0),
            roomtype
        from %s
        force index(time)
        where time >= %d
        group by gameid, roomtype
    ''' % (get_table_log_subgame(start_date), start_date)
    datas = []
    SubGameList = game_parameter.get_subgame_list()
    room_define = game_parameter.room_define()
    for search_data in LogQry(channel).qry(sql):
        try:
            roomname = room_define[search_data[0]][search_data[5]]
        except:
            roomname = search_data[5]

        pre_record = {
            'gameid': search_data[0],
            'game_name': game_parameter.get_subgame_by_id(SubGameList, search_data[0]),
            'roomid': roomname,
            'active_count': 0,
            'total_game_times': int(search_data[1]),
            'total_stake_coin': int(search_data[3]),
            'total_get_coin': int(search_data[4]),
            'win_player_num': 0,
            'lose_player_num': 0,
            'total_win': 0,
            'total_lose': 0,
            'average_game_count': 0,
            'pump': int(search_data[2]),
            'ai_win': int(search_data[3] - search_data[4])
        }

        ## 查询当日赢钱玩家数 输钱玩家数
        pre_record["active_count"] = 0
        sql = '''
            select pid, sum(stake_coin), sum(output_coin)
            from %s
            where time >= %d
            and gameid = %d
            and roomtype = %d
            group by pid
        ''' % (get_table_log_player_subgame(start_date), start_date, search_data[0], search_data[5])

        for line in LogQry(channel).qry(sql):
            pre_record["active_count"] += 1
            if line[1] > line[2]:
                pre_record["lose_player_num"] += 1
                pre_record["total_lose"] += (line[2] - line[1])
            else:
                pre_record["win_player_num"] += 1
                pre_record["total_win"] += (line[2] - line[1])
        pre_record["total_lose"] = float(pre_record["total_lose"])
        pre_record["total_win"] = float(pre_record["total_win"])

        if pre_record["active_count"] > 0:
            pre_record['average_game_count'] = int(pre_record["total_game_times"] / pre_record["active_count"])

        datas.append(pre_record)

    return jsonify(result='ok', data=datas)


@busi.route('/search/subgame/datas', methods=['GET'])
@login_require
def search_subgame_data():
    start = request.args.get('beginDate', '')
    end = request.args.get('endDate', '')
    channel = session['select_channel']

    start_date = time_util.formatDatestamp(start)
    end_date = time_util.formatDatestamp(end)

    today0 = time_util.today0()
    if start_date == today0:
        return search_subgame_data_today()

    if start_date > end_date:
        return jsonify(result='fail', msg=u'结束日期不能大于开始日期！')

    start_date = int(time_util.formatTimeWithDesc(start_date, "%Y%m%d"))
    end_date = int(time_util.formatTimeWithDesc(end_date, "%Y%m%d"))
    search_sql = """
        select gameid, roomtype, sum(total_game_times), sum(total_stake_coin), sum(total_output_coin), 
            sum(pump)
        FROM t_subgame
        WHERE time>=%d AND time<=%d
        group by gameid, roomtype
    """ % (start_date, end_date)

    allgame_search_datas = []
    SubGameList = game_parameter.get_subgame_list()
    room_define = game_parameter.room_define()
    for search_data in LogQry(channel).qry(search_sql):
        try:
            roomname = room_define[search_data[0]][search_data[1]]
        except:
            roomname = search_data[1]

        pre_record = {
            'gameid': search_data[0],
            'game_name': game_parameter.get_subgame_by_id(SubGameList, search_data[0]),
            'roomid': roomname,
            'active_count': 0,
            'total_game_times': float(search_data[2]),
            'total_stake_coin': float(search_data[3]),
            'total_get_coin': float(search_data[4]),
            'win_player_num': 0,
            'lose_player_num': 0,
            'total_win': 0,
            'total_lose': 0,
            'average_game_count': 0,
            'pump': float(search_data[5]),
            'ai_win': float(search_data[3] - search_data[4])
        }

        ## 查询这段时间玩家在该游戏里边的总体输赢情况
        sql = '''
            select pid, sum(stake_coin), sum(output_coin)
            from t_player_subgame
            where time>=%d AND time<=%d
            and gameid = %d
            and roomtype = %d
            group by pid
        ''' % (start_date, end_date, search_data[0], search_data[1])
        for line in LogQry(channel).qry(sql):
            pre_record["active_count"] += 1
            if line[1] > line[2]:
                pre_record["lose_player_num"] += 1
                pre_record["total_lose"] += (line[2] - line[1])
            else:
                pre_record["win_player_num"] += 1
                pre_record["total_win"] += (line[2] - line[1])

        if pre_record["active_count"] > 0:
            pre_record['average_game_count'] = int(search_data[2] / pre_record["active_count"])

        pre_record["total_lose"] = float(pre_record["total_lose"])
        pre_record["total_win"] = float(pre_record["total_win"])

        allgame_search_datas.append(pre_record)

    return jsonify(result='ok', data=allgame_search_datas)


@busi.route('/sub_one_game/datas', methods=['GET'])
@login_require
def search_sub_detail():
    start = request.args.get('beginDate')
    end = request.args.get('endDate')
    channel = session['select_channel']

    status_msg = dict()
    status_msg['beginDate'] = time_util.formatDatestamp(start)
    status_msg['endDate'] = time_util.formatDatestamp(end)
    status_msg["channel"] = channel

    return render_template('data_single_game.html', status_msg=status_msg, datas=[])


@busi.route('/game/item_change/datas', methods=['GET'])
@login_require
def get_item_change_data():
    status_msg = dict()
    status_msg['beginDate'] = 11
    status_msg['endDate'] = 11

    context = {
        'which_page': -1,
        'page_count': -1,
        'page_datas': []
    }

    return render_template('data_item_change.html', status_msg=status_msg, datas=context)


@busi.route('/search/game/item_change/datas', methods=['GET'])
@login_require
def search_item_change_data():
    player_id = request.args.get('PlayerID', '')
    item_id = request.args.get('game_item', '')
    start = request.args.get('beginDate', '')
    end = request.args.get('endDate', '')
    offset = request.args.get('offset')
    size = request.args.get('size')
    channel = session['select_channel']

    start_date = time_util.start(start)
    end_date = time_util.end(end)

    if start_date > end_date:
        return jsonify(result='fail', msg=u'结束日期不能小于开始日期！')

    if player_id:
        play_id_str = " AND pid='%s'" % player_id
    else:
        play_id_str = ''

    if item_id:
        item_id_str = " AND itemid='%s'" % item_id
    else:
        item_id_str = ''

    search_sql = """SELECT time, pid, (SELECT nick FROM player WHERE id=pid), log_type, itemid, rest
                    FROM log_item
                    WHERE time>=%d 
                    AND time<%d%s%s 
                    ORDER BY time DESC LIMIT %s,%s;""" \
                 % (start_date, end_date, play_id_str, item_id_str, offset, size)

    search_count = """SELECT count(1) 
                      FROM log_item
                      WHERE time>=%d 
                      AND time<%d%s;""" \
                   % (start_date, end_date, play_id_str)

    log_db = LogQry(channel)
    item_change_data = log_db.qry(search_sql)
    page_count = log_db.qry(search_count)[0][0]

    log_coin_dict = game_parameter.get_coin_log_define()

    page_datas = list()
    item_change_dict = dict()
    for timeStamp, pid, nick, log_type, itemid, rest in item_change_data:
        item_change_dict['timeStamp'] = timeStamp
        item_change_dict['pid'] = pid
        item_change_dict['nick'] = nick
        item_change_dict['log_type'] = game_parameter.get_coin_log_name(log_coin_dict, log_type)
        item_change_dict['itemid'] = items_dict.get(itemid)
        item_change_dict['rest'] = rest
        page_datas.append(item_change_dict)
        item_change_dict = dict()

    pages_dict = dict()
    pages_dict['page_count'] = page_count
    pages_dict['page_datas'] = page_datas

    return jsonify(result='ok', data=pages_dict)


@busi.route('/game/coin_change/datas', methods=['GET'])
@login_require
def get_coin_change_data():
    status_msg = dict()
    status_msg['beginDate'] = 11
    status_msg['endDate'] = 11

    line = ['<option value="0">全部</option>']
    for k, v in game_parameter.get_subgame_list().items():
        l = '<option value="%d">%s</option>' % (k, v)
        line.append(l)

    game_select = u'''
            <td colspan=1>
                游戏：<select id="game" name="game">
                        %s
                    </select>
            </td>''' % "\n".join(line)

    status_msg['OThers'] = [game_select]

    context = {
        'which_page': -1,
        'page_count': -1,
        'page_datas': []
    }

    return render_template('data_coin_change.html', status_msg=status_msg, datas=context)


@busi.route('/search/game/coin_change/datas', methods=['GET'])
@login_require
def search_coin_change_data():
    player_id = request.args.get('PlayerID', '')
    Account = request.args.get('Account', '')
    gameid = request.args.get('game')
    start = request.args.get('beginDate', '')
    end = request.args.get('endDate', '')
    channel = session['select_channel']
    size = int(request.args.get('size', ''))
    offset = int(request.args.get('offset', ''))

    start_date = time_util.formatTimestamp(start)
    end_date = time_util.formatTimestamp(end)

    use_index = "force index(time)"
    if player_id:
        use_index = "force index(pid)"
        play_id_str = " AND pid=%s" % player_id
    else:
        play_id_str = ''

    if Account:
        use_index = "force index(pid)"
        play_id_str = " AND pid = (select id from player where account_id = '%s') " % Account

    if gameid == '0':
        subgame_str = ""
    else:
        subgame_ename = game_parameter.get_subgame_enname(int(gameid))
        subgame_str = " AND subgame LIKE '%s%%'" % subgame_ename

    search_sql = """
        SELECT time, pid, (SELECT nick FROM player WHERE id=pid), log_type, subgame, val, rest
        FROM %s
        %s
        WHERE time>=%d 
        AND time<%d%s%s 
        ORDER BY time DESC LIMIT %s,%s;
        """ % (get_table_log_coin(start_date), use_index, start_date, end_date, play_id_str, subgame_str, offset, size)

    count_sql = """
        SELECT count(1), ifnull(sum(val) , 0)
        FROM %s 
        %s
        WHERE time >= %d
        AND time < %d%s%s
    """ % (get_table_log_coin(start_date), use_index, start_date, end_date, play_id_str, subgame_str)

    log_db = LogQry(channel)
    item_change_data = log_db.qry(search_sql)
    total_count = log_db.qry(count_sql)[0][0]
    total_val = int(log_db.qry(count_sql)[0][1])

    page_datas = list()
    log_coin_dict = game_parameter.get_coin_log_define()
    subgame_dict = game_parameter.get_subgame_name_enname_d()
    for timeStamp, pid, nick, log_type, subgame, \
        val, rest in item_change_data:
        item_change_dict = dict()
        item_change_dict['timeStamp'] = time_util.formatDateTime(timeStamp)
        item_change_dict['pid'] = pid
        item_change_dict['nick'] = nick
        item_change_dict['log_type'] = game_parameter.get_coin_log_name(log_coin_dict, log_type)

        if subgame:
            subgame_k = subgame.split('-')[0]
            room = subgame.split('-')[1]
            subgame_name = game_parameter.get_subgame_name_by_ename(subgame_dict, subgame_k)
            item_change_dict['subgame'] = "%s(%s)" % (subgame_name, room)
        else:
            subgame_k = ""
            room = ""
            item_change_dict['subgame'] = ""

        item_change_dict['val'] = val
        item_change_dict['rest'] = rest
        page_datas.append(item_change_dict)

    ## 做下特殊处理 排序下
    page_datas.sort(key=lambda x: [x['timeStamp'], x['val']], reverse=True)

    return jsonify({"errcode": 0, "dataLength": total_count, "rowDatas": page_datas, "total_val": total_val})


@busi.route('/subgame/data/json', methods=['GET'])
@login_require
def subgame_data_json():
    """返回子游戏数据json数据"""

    # 获取参数
    start_time = request.args.get('start_time')
    end_time = request.args.get('end_time')
    channel_id = session['select_channel']

    # 处理参数
    start_time2 = time_util.formatDatestamp(start_time)
    end_time2 = time_util.formatDatestamp(end_time) + 86400
    start_time = start_time.replace('-', '')
    end_time = end_time.replace('-', '')
    channel_id = int(channel_id)

    if start_time2 == time_util.today0():
        retrieve_sql = '''
            select gameid, sum(stake_coin), sum(output_coin)
            from %s
            where time >= %d
            group by gameid
        ''' % (get_table_log_subgame(time_util.now_sec()), time_util.today0())
    else:
        # 从数据库获取数据
        retrieve_sql = """
            SELECT gameid, sum(total_stake_coin), sum(total_output_coin)
            FROM t_subgame
            WHERE time>=%s
            AND time<=%s
            GROUP BY gameid;
        """ % (start_time, end_time)

    data = LogQry(channel_id).qry(retrieve_sql)
    # 处理数据
    data_list = list()
    SubGameList = game_parameter.get_subgame_list()
    for one in data:
        data_dict = dict()
        data_dict['game_name'] = game_parameter.get_subgame_by_id(SubGameList, one[0])
        data_dict['total_stake_coin'] = int(one[1])
        data_dict['ai_win'] = int(one[1] - one[2])
        data_list.append(data_dict)

    # 返回数据
    return jsonify(data=data_list)


## 客户端 新老玩家分步
@busi.route('/player_device', methods=['GET'])
@login_require
def tj_player_device():
    # 获取参数
    start_time = request.args.get('start_time')
    end_time = request.args.get('end_time')
    channel_id = session['select_channel']

    # 处理参数
    start_time = time_util.formatDatestamp(start_time)
    end_time = time_util.formatDatestamp(end_time) + 86400
    channel_id = int(channel_id)

    sql = 'select distinct pid from log_account_login where time >= %d and time < %d' % (start_time, end_time)
    pids = ",".join([str(i[0]) for i in LogQry(channel_id).qry(sql)])

    ## 计算客户端分步
    d = {}
    if pids:
        sql = 'select device, count(1) from player where id in (%s) group by device' % pids
        for device, count in LogQry(channel_id).qry(sql):
            d[device] = int(count)

    ## 计算新老玩家分步
    old_p, new_p = 0, 0
    if pids:
        sql = '''
            select ifnull(sum(if(reg_time < %d, 1, 0)), 0) as old, ifnull(sum(if(reg_time >= %d, 1, 0)), 0) as new
            from player
            where id in (%s)
        ''' % (start_time, start_time, pids)
        old_p, new_p = LogQry(channel_id).qry(sql)[0]

    data = {
        "device": d,
        "player_count": {"old": int(old_p), "new": int(new_p)},
    }
    return jsonify(data)


## 查询财务概况
@busi.route('/fiance', methods=['GET'])
@login_require
def fiance_tj():
    # 获取参数
    start_time = request.args.get('start_time')
    end_time = request.args.get('end_time')
    channel_id = session['select_channel']

    # 处理参数
    start_time2 = start_time.replace('-', '')
    end_time2 = end_time.replace('-', '')
    start_time = time_util.formatDatestamp(start_time)
    end_time = time_util.formatDatestamp(end_time) + 86400

    ## 充值
    sql = '''
        select ifnull(sum(cost), 0) 
        from admin_recharge 
        where state = 1
        and time >= %d
        and time < %d
    ''' % (start_time, end_time)
    recharge = LogQry(channel_id).qry(sql)[0][0]

    ## 提现
    sql = '''
        select ifnull(sum(withdraw_deposit_money), 0) 
        from admin_withdraw 
        where status = 1
        and application_time >= %d
        and application_time < %d
    ''' % (start_time, end_time)
    withdraw = LogQry(channel_id).qry(sql)[0][0]

    ## 查询代理卖分 
    sql = '''
        select ifnull(sum(money), 0)
        from log_bank_give
        where give_agent = 1 and recv_agent = 0
        and time >= %d
        and time < %d
    ''' % (start_time, end_time)
    agent_sell = LogQry(channel_id).qry(sql)[0][0]

    ## 代理买分
    sql = '''
        select ifnull(sum(money), 0)
        from log_bank_give
        where give_agent = 0 and recv_agent = 1
        and time >= %d
        and time < %d
    ''' % (start_time, end_time)
    agent_buy = LogQry(channel_id).qry(sql)[0][0]

    ## todo 返水
    fanshui = 0

    ## todo 返佣
    fanyong = 0

    # 查询游戏盈利
    sql = """
        SELECT ifnull(sum(total_stake_coin - total_output_coin), 0)
        FROM t_subgame
        WHERE time>={}
        AND time<={};
    """
    sql = sql.format(start_time2, end_time2)
    data2 = LogQry(channel_id).qry(sql)
    try:
        ai_win1 = int(data2[0][0])
    except TypeError:
        ai_win1 = 0

    sql = """
        SELECT ifnull(sum(stake_coin - output_coin), 0)
        FROM {}
        WHERE time>={}
        AND time<={};
    """
    sql = sql.format(get_table_log_player_subgame(time_util.now_sec()), time_util.today0(), end_time)
    data2 = LogQry(channel_id).qry(sql)
    try:
        ai_win2 = int(data2[0][0])
    except TypeError:
        ai_win2 = 0

    data = {
        "recharge": int(recharge),
        "withdraw": int(withdraw),
        "agent_sell": int(agent_sell),
        "agent_buy": int(agent_buy),
        "fanyong": fanyong,
        "fanshui": fanshui,
        "ai_win": ai_win1 + ai_win2,
    }

    return jsonify(data)


## 查询在线情况
@busi.route('/online', methods=['GET'])
@login_require
def online_tj():
    # 获取参数
    start_time = request.args.get('start_time')
    end_time = request.args.get('end_time')
    channel_id = session['select_channel']

    # 处理参数
    start_time = time_util.formatDatestamp(start_time)
    end_time = time_util.formatDatestamp(end_time)
    channel_id = int(channel_id)

    sql = '''
        select time, sum(num)
        from log_online
        force index(time)
        where time >= %d
        and time < %d
        group by time
    ''' % (start_time, start_time + 86400)
    data1 = LogQry(channel_id).qry(sql)

    sql = '''
        select time, sum(num)
        from log_online
        force index(time)
        where time >= %d
        and time < %d
        group by time
    ''' % (end_time, end_time + 86400)
    data2 = LogQry(channel_id).qry(sql)

    return jsonify(data1=[(i, int(j)) for i, j in data1], data2=[(i, int(j)) for i, j in data2])


## 查询玩家人数情况
@busi.route('/player_tj', methods=['GET'])
@login_require
def player_tj():
    # 获取参数
    start_time = request.args.get('start_time')
    end_time = request.args.get('end_time')
    channel_id = session['select_channel']

    # 处理参数
    start_time = time_util.formatDatestamp(start_time)
    end_time = time_util.formatDatestamp(end_time)
    channel_id = int(channel_id)

    ## 查询注册人数
    sql = '''
        select count(1)
        from player
        force index(reg_time)
        where reg_time >= %d
        and reg_time <= %d
    ''' % (start_time, end_time)
    reg_count = LogQry(channel_id).qry(sql)[0][0]

    ## 查询游戏人数 
    sql = '''
        select distinct pid
        from t_player_subgame
        force index(time)
        where time >= %s
        and time <= %s
    ''' % (time_util.formatTimeWithDesc(start_time, "%Y%m%d"), time_util.formatTimeWithDesc(end_time, "%Y%m%d"))
    pids = list(LogQry(channel_id).qry(sql))

    today0 = time_util.today0()
    if start_time >= today0 and end_time >= today0:
        sql = '''
            select distinct pid
            from %s
            force index(time)
            where time >= %d
            and time <= %d
        ''' % (get_table_log_player_subgame(today0), start_time, end_time)
        pids.extend(list(LogQry(channel_id).qry(sql)))
    player_count = len(set(pids))

    ## 查询活跃人数
    sql = '''
        select count(distinct pid)
        from log_account_login
        force index(time)
        where time >= %d
        and time <= %d
    ''' % (start_time, end_time)
    active_count = LogQry(channel_id).qry(sql)[0][0]

    ## 充值
    sql = '''
        select count(distinct pid)
        from admin_recharge 
        where state = 1
        and time >= %d
        and time <= %d
    ''' % (start_time, end_time)
    recharge = LogQry(channel_id).qry(sql)[0][0]

    ## 提现
    sql = '''
        select count(distinct pid)
        from admin_withdraw 
        where status = 1
        and application_time >= %d
        and application_time <= %d
    ''' % (start_time, end_time)
    withdraw = LogQry(channel_id).qry(sql)[0][0]

    data = {
        "reg_count": int(reg_count),
        "player_count": int(player_count),
        "active_count": int(active_count),
        "recharge": int(recharge),
        "withdraw": int(withdraw),
    }

    return jsonify(data)