# -*- coding: utf-8 -*-
"""测试 Phase 7: 任务传送"""
import sys, os, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from airtest.core.api import connect_device
connect_device("Android:///127.0.0.1:16480")
from tasks.dungeon100_task import Dungeon100Task
task = Dungeon100Task(serial="127.0.0.1:16480")
task.set_log_callback(None)
task._running = True
print("\n>>> Phase 7")
task._quest_teleport()
print("完成!")
