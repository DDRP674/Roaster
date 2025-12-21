import datetime
from logging.handlers import RotatingFileHandler
import sys, Framework
import time
from lib_helper import load_json_with_comments
import os, logging

settings = load_json_with_comments("settings.json")

# 日志系统
if settings["do_log"]:
    log_dir = settings["log_dir"]
    log_dir = os.path.normpath(log_dir)
    os.makedirs(log_dir, exist_ok=True)
    now = datetime.datetime.now()
    now = now.strftime("%Y%m%d%H%M%S")
    path = os.path.join(log_dir, f"log_{now}.txt")
    
    handler = RotatingFileHandler(
        filename=path,
        maxBytes=10 * 1024 * 1024, 
        backupCount=5,        
        encoding='utf-8'
    )
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            handler,
            logging.StreamHandler(sys.stdout)
        ]
    )
else:
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[logging.StreamHandler(sys.stdout)]
    )

# 主程序
start = time.time()
f = Framework.Framework()
logging.info(f"初始化用时：{round(time.time()-start,3)}秒")
f.run()
logging.info(f"完整用时：{round(time.time()-start,3)}秒")