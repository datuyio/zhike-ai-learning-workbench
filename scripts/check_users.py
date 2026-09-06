# -*- coding: utf-8 -*-
"""查看当前所有用户角色分布（排查是否注册了新的教师账号）。"""
import psycopg

conn = psycopg.connect('postgresql://zhike:zhike_password@localhost:5432/zhike_workshop')
cur = conn.cursor()
cur.execute("SELECT email, display_name, role_code, external_id, status FROM users ORDER BY role_code, created_at")
for r in cur.fetchall():
    print(r)
conn.close()
