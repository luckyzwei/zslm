# -*- coding:utf-8 -*-

from __future__ import division
import time
import json
from flask import render_template, jsonify
from flask.globals import session, request, current_app
from zs_backend import SqlOperate
from zs_backend.busi import busi
from zs_backend.utils.channel_qry import LogQry, GameWeb
from zs_backend.utils.common import login_require, rand, md5
from zs_backend.utils import time_util, html_translate, httpc_util
from zs_backend.utils.const import *
from zs_backend import redis_conn
from zs_backend.utils.recharge_util import get_coin_recharge_discounts, gen_order_no, do_add_order_menual


def qry_topup_html(paytype, paystate):
    SELECTED0, SELECTED1, SELECTED2 = "", "", ""
    if paytype == 1:
        SELECTED1 = "selected"
    elif paytype == 2:
        SELECTED2 = "selected"

    paytype_html = u'''
        <td>充值类型：
            <select id="type" name="type"> 
                <option value="0" %s>全部</option> 
                <option value="1" %s>公司入款</option> 
                <option value="2" %s>客服充值</option> 
            </select>
        </td>''' % (SELECTED0, SELECTED1, SELECTED2)

    SELECTED_1, SELECTED0, SELECTED1, SELECTED2, SELECTED3 = "", "", "", "", ""
    if paystate == 1:
        SELECTED1 = "selected"
    elif paystate == 2:
        SELECTED2 = "selected"
    elif paystate == 3:
        SELECTED3 = "selected"
    elif paystate == 0:
        SELECTED0 = "selected"

    paystate_html = u'''
        <td>充值状态：
            <select id="paystate" name="paystate"> 
                <option value="-1" %s>全部</option> 
                <option value="0" %s>待支付</option> 
                <option value="1" %s>成功</option> 
                <option value="2" %s>失败</option> 
                <option value="3" %s>待审核</option> 
            </select>
        </td>''' % (SELECTED_1, SELECTED0, SELECTED1, SELECTED2, SELECTED3)

    return [paytype_html, paystate_html]


@busi.route('/games/topup/detail', methods=['GET'])
@login_require
def get_topup_order_detail():
    page = {}
    page["beginDate"] = 11
    page["endDate"] = 11
    page["channel"] = ""
    page["player_id"] = ""
    page["account"] = ""
    page["OThers"] = qry_topup_html(0, -1)
    name = session['name']
    return render_template('topup_detail.html', page=page, username=name)


## 订单详情查询
@busi.route('/search/topup/detail', methods=['GET'])
@login_require
def search_topup_order_detail():
    start = request.args.get('beginDate')
    end = request.args.get('endDate')
    player_id = request.args.get('PlayerID', '')
    account = request.args.get('Account', '')
    stype = request.args.get('type')
    pay_state = request.args.get('pay_state')
    offset = int(request.args.get("offset", "0"))
    pagesize = int(request.args.get("size", "100"))

    # 接收渠道id
    channel = session['select_channel']

    start_date = time_util.formatTimestamp(start)
    end_date = time_util.formatTimestamp(end)

    where = ""
    use_index = "force index(time)"
    if stype != "0":
        where += "and type = %s " % stype
    if pay_state != "-1":
        where += "and state = %s " % pay_state
    if player_id != "":
        use_index = "force index(pid)"
        where += "and pid = %s " % player_id
    if account != "":
        use_index = "force index(pid)"
        where += "and pid = (select id from player where account_id = '%s') " % account

    ## 查询满足条件的总数
    count_sql = '''
        select count(1)
        from admin_recharge
        %s
        where time >= %d 
        and time <= %d
        %s
    ''' % (use_index, start_date, end_date, where)
    total_count = LogQry(channel).qry(count_sql)[0][0]

    ## 查询支付通道名字
    pc = {}
    sql = '''
        select id, name, config
        from admin_pay_channel
    '''
    for line in LogQry(channel).qry(sql):
        pc[line[0]] = [line[1], line[2]]

    sql = '''
        select id, api_name
        from admin_online_payment
        where channel_id = %d
    ''' % (channel)
    for line in LogQry(channel).qry(sql):
        pc[line[0]] = [line[1], ""]

    ml = {}
    ml[0] = u"默认"
    sql = '''
        select id, member_level_name
        from admin_member_level
        where channel_id = %d
    ''' % channel
    for line in LogQry(channel).qry(sql):
        ml[line[0]] = line[1]

    ## 操作员查询
    operator = {0: ""}
    sql = '''
        select id, name
        from user
    '''
    for line in SqlOperate().select(sql):
        operator[line[0]] = line[1]

    ## 查询满足条件的订单详情
    sql = '''
        select time, pid, vip, (select account_id from player where id = pid),
                (select nick from player where id = pid),
            orderno, platformno, cost, state, type,
            pay_channel, request_pid, review_time, review_pid, memo,
            coin, pay_name
        from admin_recharge
        %s
        where time >= %d 
        and time <= %d
        %s 
        order by state desc, time desc
        limit %s, %s
    ''' % (use_index, start_date, end_date, where, offset, pagesize)
    datas = []
    for line in LogQry(channel).qry(sql):
        d = {}
        d["request_time"] = line[0]
        d["id"] = line[1]
        d["vip"] = ml.get(line[2])
        d["account"] = line[3]
        d["nick"] = line[4]

        d["order_no"] = line[5]
        d["cost"] = line[7]
        d["state"] = line[8]
        d["pay_type"] = line[9]

        d["pay_chanel"] = pc[line[10]][0]
        d["request_pid"] = operator[line[11]]
        d["review_time"] = line[12]
        d["review_pid"] = operator[line[13]]
        d["memo"] = line[14]
        d["coin"] = line[15]
        d["name"] = line[16]

        d["pay_chanel_config"] = pc[line[10]][1]

        datas.append(d)

    return jsonify({"errcode": 0, "dataLength": total_count, "rowDatas": datas})


## 手工增加一条订单
@busi.route('/topup/menual_add', methods=['GET'])
@login_require
def menual_add_order():
    ## 玩家ID
    player_id = int(request.args.get('player_id'))
    # 接收渠道id
    channel = session['select_channel']
    ## 支付通道
    pay_channel = int(request.args.get('pay_channel'))
    ## 充值金币
    money = int(request.args.get('money'))
    ## 充值时间 时间戳
    request_time = int(request.args.get('request_time'))
    ## 备注
    memo = request.args.get('memo', '')

    ## 生成本次订单编号
    orderno = "kf_%s" % gen_order_no(channel, pay_channel)

    return do_add_order_menual(channel, orderno, player_id, pay_channel, money,
                               request_time, memo, session['user_id'])

## 审核
@busi.route('/topup/review', methods=['GET'])
@login_require
def review_order():
    # 接收渠道id
    channel = session['select_channel']
    ## 备注
    memo = request.args.get('memo', '')
    ## 订单号
    orderno = request.args.get('orderno', '')
    ## 状态
    state = int(request.args.get('result', ''))

    ## 查询订单状态
    sql = '''
        select pid, cost
        from admin_recharge
        where orderno = '%s' and (state = %d or (state = %d and review_pid = %d))
    ''' % (orderno, PAY_STATE_REVIEW, PAY_STATE_LOCK, session["user_id"])
    data = LogQry(channel).qry(sql)
    if not data:
        return jsonify(result="fail")
    pid, money = data[0]

    ## 根据充值优惠重新计算实际到账的钱
    recharge_info = get_coin_recharge_discounts(channel, money, pid)
    recharge_id, add_recharge, coin = recharge_info

    sql = '''
        update admin_recharge
        set memo = '%s', state = %d, review_time = %d, review_pid = %d, rechargeid = %d, 
            add_recharge = %d, coin = %d
        where orderno = '%s'
    ''' % (memo, state, time_util.now_sec(), session["user_id"], recharge_id, \
           add_recharge, coin, orderno)
    LogQry(channel).execute(sql)

    ## todo 给游戏后台发送消息
    if state == PAY_STATE_SUCC:
        pay_load = {
            "pid": pid,
            "money": money,
            "coin": coin,
            "type": COIN_CHANGE_RECHARGE,
        }
        GameWeb(channel).post("/api/set_player_coin", pay_load)

    return jsonify(result="ok")

@busi.route('/recharge/order/waiting/count', methods=['GET'])
@login_require
def recharge_order_waiting_count():
    """给首页返回待审核充值订单条数"""

    # 构造查询参数
    first_channel_id = session['select_channel']
    now_time = time_util.now_sec()
    seven_days_ago = now_time - 7 * 24 * 60 * 60

    # 查询数据库
    retrieve_sql = """SELECT count(1)
                      FROM admin_recharge
                      WHERE time>=%s
                      AND time<=%s
                      AND state=%s;""" \
                   % (seven_days_ago, now_time, PAY_STATE_REVIEW)
    data = LogQry(first_channel_id).qry(retrieve_sql)

    # 处理数据
    count = data[0][0]

    # 查询一分钟以内是否有新订单
    one_min_ago = now_time - 60
    retrieve_sql = """SELECT count(1)
                      FROM admin_recharge
                      WHERE time>=%s
                      AND time<=%s
                      AND state=%s;""" \
                   % (one_min_ago, now_time, PAY_STATE_REVIEW)
    data = LogQry(first_channel_id).qry(retrieve_sql)[0][0]
    if data == 0:
        is_new = 0
    else:
        is_new = 1

    # 返回数据
    return jsonify(count=count, is_new=is_new)


@busi.route('/recharge/order/lock', methods=['GET'])
@login_require
def recharge_order_lock():
    orderid = request.args.get('orderid')
    channel = session['select_channel']

    sql = '''
        select count(1) from admin_recharge where orderno = '%s' and state = %d
    ''' % (orderid, PAY_STATE_REVIEW)
    count = LogQry(channel).qry(sql)[0][0]
    if count == 0:
        return jsonify(result="fail", msg=u'订单已被锁定或者订单不存在')

    sql = '''
        update admin_recharge
        set state = %d, review_pid = %d, review_time = %d
        where orderno = '%s' and state = %d
    ''' % (PAY_STATE_LOCK, session["user_id"], time_util.now_sec(), orderid, PAY_STATE_REVIEW)

    return jsonify(result="ok")
