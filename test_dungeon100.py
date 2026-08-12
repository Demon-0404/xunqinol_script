# -*- coding: utf-8 -*-
"""单独测试提交任务"""
import sys, os, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from airtest.core.api import connect_device
connect_device("Android:///127.0.0.1:16480")
from tasks.dungeon100_task import Dungeon100Task
task = Dungeon100Task(serial="127.0.0.1:16480")
task.set_log_callback(None)
task._running = True
print("\n>>> 提交任务")
task._submit_quest()
print("完成!")
