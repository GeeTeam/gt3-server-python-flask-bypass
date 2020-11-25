import json
import time
import redis
import requests
import threading
from flask import Flask, request, Response, jsonify

from geetest_config import GEETEST_ID, GEETEST_KEY, REDIS_HOST, REDIS_PORT, CYCLE_TIME, BYPASS_URL, GEETEST_BYPASS_STATUS_KEY

from sdk.geetest_lib import GeetestLib

app = Flask(__name__)


# 建立redis连接池
def init_redis_connect():
    try:
        host = REDIS_HOST
        port = REDIS_PORT
        pool = redis.ConnectionPool(host=host, port=port)
        redis_connect = redis.Redis(connection_pool=pool)
        return redis_connect
    except Exception as e:
        return None


redis_connect = init_redis_connect()


# 发送bypass请求，获取bypass状态并进行缓存（如何缓存可根据自身情况合理选择,这里是使用redis进行缓存）
def check_bypass_status():
    while True:
        response = ""
        params = {"gt": GEETEST_ID}
        try:
            response = requests.get(url=BYPASS_URL, params=params)
        except Exception as e:
            print(e)
        if response and response.status_code == 200:
            print(response.content)
            bypass_status_str = response.content.decode("utf-8")
            bypass_status = json.loads(bypass_status_str).get("status")
            redis_connect.set(GEETEST_BYPASS_STATUS_KEY, bypass_status)
        else:
            bypass_status = "fail"
            redis_connect.set(GEETEST_BYPASS_STATUS_KEY, bypass_status)
        print("bypass状态已经获取并存入redis，当前状态为-{}".format(bypass_status))
        time.sleep(CYCLE_TIME)


# 从缓存中取出当前缓存的bypass状态(success/fail)
def get_bypass_cache():
    bypass_status_cache = redis_connect.get(GEETEST_BYPASS_STATUS_KEY)
    bypass_status = bypass_status_cache.decode("utf-8")
    return bypass_status


@app.route("/favicon.ico")
def favicon():
    return app.send_static_file('favicon.ico')


@app.route("/")
def index():
    return app.send_static_file("index.html")


# 验证初始化接口，GET请求
@app.route("/register", methods=["GET"])
def first_register():
    # 必传参数
    #     digestmod 此版本sdk可支持md5、sha256、hmac-sha256，md5之外的算法需特殊配置的账号，联系极验客服
    # 自定义参数,可选择添加
    #     user_id 客户端用户的唯一标识，确定用户的唯一性；作用于提供进阶数据分析服务，可在register和validate接口传入，不传入也不影响验证服务的使用；若担心用户信息风险，可作预处理(如哈希处理)再提供到极验
    #     client_type 客户端类型，web：电脑上的浏览器；h5：手机上的浏览器，包括移动应用内完全内置的web_view；native：通过原生sdk植入app应用的方式；unknown：未知
    #     ip_address 客户端请求sdk服务器的ip地址
    bypass_status = get_bypass_cache()
    gt_lib = GeetestLib(GEETEST_ID, GEETEST_KEY)
    digestmod = "md5"
    user_id = "test"
    param_dict = {"digestmod": digestmod, "user_id": user_id, "client_type": "web", "ip_address": "127.0.0.1"}
    if bypass_status == "success":
        result = gt_lib.register(digestmod, param_dict)
    else:
        result = gt_lib.local_init()
    # 注意，不要更改返回的结构和值类型
    return Response(result.data, content_type='application/json;charset=UTF-8')


# 二次验证接口，POST请求
@app.route("/validate", methods=["POST"])
def second_validate():
    challenge = request.form.get(GeetestLib.GEETEST_CHALLENGE, None)
    validate = request.form.get(GeetestLib.GEETEST_VALIDATE, None)
    seccode = request.form.get(GeetestLib.GEETEST_SECCODE, None)
    bypass_status = get_bypass_cache()
    gt_lib = GeetestLib(GEETEST_ID, GEETEST_KEY)
    if bypass_status == "success":
        result = gt_lib.successValidate(challenge, validate, seccode)
    else:
        result = gt_lib.failValidate(challenge, validate, seccode)
    # 注意，不要更改返回的结构和值类型
    if result.status == 1:
        response = {"result": "success", "version": GeetestLib.VERSION}
    else:
        response = {"result": "fail", "version": GeetestLib.VERSION, "msg": result.msg}
    return jsonify(response)


if __name__ == "__main__":
    thread = threading.Thread(target=check_bypass_status)
    thread.start()
    app.secret_key = GeetestLib.VERSION
    app.run(host="0.0.0.0", port=5000, debug=True)
