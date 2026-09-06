# -*- coding: utf-8 -*-
"""将模型网关默认供应商从无 Key 的讯飞切换为已配置 Key 的 DeepSeek。"""
import psycopg

conn = psycopg.connect('postgresql://zhike:zhike_password@localhost:5432/zhike_workshop')
cur = conn.cursor()
cur.execute("UPDATE model_providers SET is_default = false WHERE is_default = true")
cur.execute("UPDATE model_providers SET is_default = true WHERE provider = 'deepseek'")
conn.commit()
cur.execute("SELECT provider, is_default, is_active FROM model_providers ORDER BY priority")
for r in cur.fetchall():
    print(r)
conn.close()
