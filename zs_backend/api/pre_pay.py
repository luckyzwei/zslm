# -*- coding:utf-8 -*-
from flask import redirect
from flask import render_template, jsonify
from flask import url_for
from flask.globals import current_app, request, g
from zs_backend.sql import SqlOperate
from zs_backend.utils.common import login_require, md5, rand
from zs_backend.utils.const import *
from zs_backend.utils import httpc_util
from zs_backend.utils import time_util
import time
from zs_backend import redis_conn
from zs_backend.utils import qrcode_util
import json
import sys
from flask import make_response
from config import Config

html = '''
<html lang="zh-CN">
<head>
    <title>支付</title>
</head>
<body>
<div class="container">
    <div class="row" style="margin:15px;">
        <div class="col-md-12">
            <form class="form-inline" method="post" action="%s">
                %s
                <button type="submit" id="zhifu">确认支付</button>
            </form>
        </div>
    </div>
</div>
</body>
<script>
document.getElementById('zhifu').click()
</script>
</html>
'''

## 易知富支付
def pre_pay_after_for_yi_zhi_fu(money, channel, pay_channel, data, callback_url):
	AppID = data["appid"]
	MchID = data["mch_id"]
	OrderNo = data["orderno"]
	MchKey = data["mch_key"]
	URL = data["url"]

	## 支付方式选择
	PayType = ""
	if data["pay_type"] == PAY_TYPE_WX_QRCODE:
		PayType = "WX_CODE"
	if data["pay_type"] == PAY_TYPE_WX_WAP:
		PayType = "WX_H5"
	if data["pay_type"] == PAY_TYPE_ZFB_QRCODE:
		PayType = "ALI"
	if data["pay_type"] == PAY_TYPE_ZFB_WAP:
		PayType = "ALI_WAP"

	## 预创建订单成功
	payload = {
		"mchId":MchID,
		"sign":"",
		"body":u"会员充值",
		"outTradeNo":OrderNo,
		"totalFee":"%.2f" % (float(money) / 100),
		"spbillCreateIp":request.remote_addr,
		"notifyUrl":callback_url,
		"tradeType":PayType,
	}
	payload["sign"] = httpc_util.gen_sign(payload, MchKey, lower = False)

	data = httpc_util.post(URL, payload)
	return data.text

## 新宝支付
def pre_pay_after_for_xin_bao(money, channel, pay_channel, data, callback_url):
	AppID = data["appid"]
	MchID = data["mch_id"]
	OrderNo = data["orderno"]
	MchKey = data["mch_key"]
	URL = data["url"]

	## 支付方式选择
	PayType = ""
	if data["pay_type"] == PAY_TYPE_WX_QRCODE:
		PayType = "0002"
	if data["pay_type"] == PAY_TYPE_WX_WAP:
		PayType = "0004"
	if data["pay_type"] == PAY_TYPE_ZFB_QRCODE:
		PayType = "0003"
	if data["pay_type"] == PAY_TYPE_ZFB_WAP:
		PayType = "0005"

	## 预创建订单成功
	payload = {
		"version":"V1.0",
		"partner_id":MchID,
		"pay_type":PayType,
		"order_no":OrderNo,
		"amount":"%.2f" % (float(money) / 100),
		"notify_url":callback_url,
		"sign":"",
		"summary":u"会员充值",	
	}
	payload["sign"] = httpc_util.gen_sign(payload, MchKey, connect_key = False)

	data = httpc_util.post(URL, payload)
	return data.text

## 支付宝支付
def pre_pay_after_for_zfb(money, channel, pay_channel, data, callback_url):
	AppID = data["appid"]
	OrderNo = data["orderno"]
	PrivateKey = data["private_key"]
	URL = data["url"]

	## 预创建订单成功
	payload = {
		"app_id":AppID,
		"method":"alipay.trade.precreate",
		"charset":"utf-8",
		"sign_type":"RSA2",
		"timestamp":time_util.formatDateTime(time_util.now_sec()),
		"version":"1.0",
		"notify_url":callback_url,
		"biz_content":json.dumps({
			"out_trade_no":OrderNo,
			"total_amount":"%.2f" % (float(money) / 100),
			"subject":u"会员充值"
			})
	}
	## 重新拼私钥（可能因为提交表单时 把换行符给干掉了） 加上前后一段
	private_key = '''-----BEGIN RSA PRIVATE KEY-----
%s
-----END RSA PRIVATE KEY-----
''' % "\n".join(PrivateKey.split())

	payload["sign"] = httpc_util.gen_sign(payload, private_key, lower = None, sign_type = "RSA2")

	## 发消息给支付宝产生一条订单
	data = httpc_util.get(URL, payload, charset = None)
	jdata = data.json()
	res = jdata['alipay_trade_precreate_response']

	if res["code"] == "10000":
		path = qrcode_util.qc(res["qr_code"])
		return '<html><body><img src="%s" /></body></html>' % path
	else:
		return jsonify(result = "fail", msg = "zfb err")

## 微信支付
def pre_pay_after_for_wx(money, channel, pay_channel, data, callback_url):
	AppID = data["appid"]
	MchID = data["mch_id"]
	OrderNo = data["orderno"]
	MchKey = data["mch_key"]
	URL = data["url"]

	## 预创建订单成功
	payload = {
		"appid":AppID,
		"mch_id":MchID,
		"nonce_str":md5("%d_%d" % (time_util.now_sec(), rand(1, 99999999))),
		"sign":"",
		"sign_type":"MD5",
		"body":u"会员充值",
		"out_trade_no":OrderNo,
		"total_fee":money,
		"spbill_create_ip":request.remote_addr,
		"notify_url":callback_url,
		"trade_type":"NATIVE",
	}
	payload["sign"] = httpc_util.gen_sign(payload, MchKey, lower = False)
	
	data = httpc_util.post(URL, payload, ctype = "xml")
	if data["return_code"] == "SUCCESS" and data["result_code"] == "SUCCESS":
		path = qrcode_util.qc(data["code_url"])
		return '<html><body><img src="%s" /></body></html>' % path
	elif data["return_code"] == "SUCCESS":
		return jsonify(result = "fail", code = data["err_code"], msg = data["err_code_des"])
	else:
		print data
		return jsonify(result = "fail", msg = "wx err")

## 68支付
def pre_pay_after_for_68(money, channel, pay_channel, data, callback_url):
	AppID = data["appid"]
	MchID = data["mch_id"]
	OrderNo = data["orderno"]
	MchKey = data["mch_key"]
	URL = data["url"]

	## 支付方式选择
	PayType = ""
	if data["pay_type"] == PAY_TYPE_WX_QRCODE:
		PayType = "0002"
	if data["pay_type"] == PAY_TYPE_WX_WAP:
		PayType = "0004"
	if data["pay_type"] == PAY_TYPE_ZFB_QRCODE:
		PayType = "0003"
	if data["pay_type"] == PAY_TYPE_ZFB_WAP:
		PayType = "0005"

	## 预创建订单成功
	payload = {
		"version":"V1.0",
		"partner_id":MchID,
		"pay_type":PayType,
		"order_no":OrderNo,
		"amount":"%.2f" % (float(money) / 100),
		"notify_url":callback_url,
		"sign":"",
		"summary":u"会员充值",	
	}
	payload["sign"] = httpc_util.gen_sign(payload, MchKey, connect_key = False)

	data = httpc_util.post(URL, payload)
	return data.text

## 陌陌付支付
def pre_pay_after_for_mo_mo_fu(money, channel, pay_channel, data, callback_url):
	AppID = data["appid"]
	MchID = data["mch_id"]
	OrderNo = data["orderno"]
	MchKey = data["mch_key"]
	URL = data["url"]

	## 支付方式选择
	PayType = ""
	if data["pay_type"] == PAY_TYPE_WX_QRCODE:
		PayType = "902"
	if data["pay_type"] == PAY_TYPE_WX_WAP:
		PayType = "902"
	if data["pay_type"] == PAY_TYPE_ZFB_QRCODE:
		PayType = "903"
	if data["pay_type"] == PAY_TYPE_ZFB_WAP:
		PayType = "903"

	## 预创建订单成功
	payload = {
		"pay_memberid":int(MchID),
		"pay_orderid":OrderNo,
		"pay_applydate":time_util.formatDateTime(time_util.now_sec()),
		"pay_bankcode":PayType,
		"pay_notifyurl":callback_url,
		"pay_amount":"%.2f" % (float(money) / 100),
	}
	payload["pay_md5sign"] = httpc_util.gen_sign(payload, MchKey, lower = False)
	payload["pay_callbackurl"] = ""
	payload["pay_productname"] = u"会员充值"

	data = httpc_util.post(URL, payload)
	if data.headers['Content-Type'] == 'image/png':
		response = make_response(data.content)
		response.headers['Content-Type'] = 'image/png'
		return response 
	else:
		print data.headers['Content-Type'], data.text
		return data.text

## cs支付
def pre_pay_after_for_cs(money, channel, pay_channel, data, callback_url):
	AppID = data["appid"]
	MchID = data["mch_id"]
	OrderNo = data["orderno"]
	MchKey = data["mch_key"]
	URL = data["url"]

	## 支付方式选择
	PayType = ""
	if data["pay_type"] == PAY_TYPE_WX_QRCODE:
		PayType = "0002"
	if data["pay_type"] == PAY_TYPE_WX_WAP:
		PayType = "0004"
	if data["pay_type"] == PAY_TYPE_ZFB_QRCODE:
		PayType = "0003"
	if data["pay_type"] == PAY_TYPE_ZFB_WAP:
		PayType = "0005"

	## 预创建订单成功
	payload = {
		"version":"V1.0",
		"partner_id":MchID,
		"pay_type":PayType,
		"order_no":OrderNo,
		"amount":"%.2f" % (float(money) / 100),
		"notify_url":callback_url,
		"sign":"",
		"summary":u"会员充值",	
	}
	payload["sign"] = httpc_util.gen_sign(payload, MchKey, connect_key = True)

	data = httpc_util.post(URL, payload)
	return data.text

## 佰富支付
def pre_pay_after_for_bai_fu(money, channel, pay_channel, data, callback_url):
	AppID = data["appid"]
	MchID = data["mch_id"]
	OrderNo = data["orderno"]
	MchKey = data["mch_key"]
	URL = data["url"]

	## 支付方式选择
	PayType = ""
	if data["pay_type"] == PAY_TYPE_WX_QRCODE:
		PayType = "WX"
	if data["pay_type"] == PAY_TYPE_WX_WAP:
		PayType = "WX_WAP"
	if data["pay_type"] == PAY_TYPE_ZFB_QRCODE:
		PayType = "ZFB"
	if data["pay_type"] == PAY_TYPE_ZFB_WAP:
		PayType = "ZFB_WAP"

	## 预创建订单成功
	payload = {
		"merchantNo":MchID,
		"netwayCode":PayType,
		"randomNum":md5(str(rand(1, 99999))),
		"orderNum":OrderNo,
		"payAmount":"%d" % money,
		"goodsName":u"会员充值",
		"callBackUrl":callback_url,
		"callBackUrl":callback_url,
		"requestIP":request.remote_addr,
	}
	src = ",".join(['"%s":"%s"' % (i, payload[i]) for i in sorted(payload.keys())])
	src = "{%s}%s" % (src, MchKey)
	payload["sign"] = md5(src).upper()

	param = {"paramData":json.dumps(payload)}
	data = httpc_util.post(URL, param).json()
	if data["resultCode"] == "00":
		if PayType == "WX" or PayType == "ZFB":
			path = qrcode_util.qc(data["CodeUrl"])
			return '<html><body><img src="%s" /></body></html>' % path
		else:
			return redirect(data["CodeUrl"])
	else:
		print data["resultMsg"]
		return data["resultMsg"]

## 优码付支付
def pre_pay_after_for_you_ma_fu(money, channel, pay_channel, data, callback_url):
	AppID = data["appid"]
	MchID = data["mch_id"]
	OrderNo = data["orderno"]
	MchKey = data["mch_key"]
	URL = data["url"]

	## 支付方式选择
	PayType = ""
	if data["pay_type"] == PAY_TYPE_WX_QRCODE:
		PayType = "902"
	if data["pay_type"] == PAY_TYPE_WX_WAP:
		PayType = "901"
	if data["pay_type"] == PAY_TYPE_ZFB_QRCODE:
		PayType = "903"
	if data["pay_type"] == PAY_TYPE_ZFB_WAP:
		PayType = "904"

	## 预创建订单成功
	payload = {
		"pay_memberid":MchID,
		"pay_orderid":OrderNo,
		"pay_applydate":time_util.formatDateTime(time_util.now_sec()),
		"pay_bankcode":PayType,
		"pay_notifyurl":callback_url,
		"pay_callbackurl":callback_url,
		"pay_amount":"%.2f" % (float(money) / 100),
	}
	payload["pay_md5sign"] = httpc_util.gen_sign(payload, MchKey, lower = False, connect_key = True)
	payload["pay_productname"] = u"会员充值"

	params = "\n".join(['<input type="hidden" name="%s" value="%s">' % (k, v) for k, v in payload.items()])
	
	return html % (URL, params)
