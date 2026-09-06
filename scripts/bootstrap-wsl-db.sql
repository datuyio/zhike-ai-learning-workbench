-- 初始化本地 WSL PostgreSQL，供 Windows 后端开发服务连接。
SELECT 'CREATE ROLE zhike WITH LOGIN PASSWORD ''zhike_password'''
WHERE NOT EXISTS (
  SELECT 1 FROM pg_roles WHERE rolname = 'zhike'
)\gexec

SELECT 'CREATE DATABASE zhike_workshop OWNER zhike'
WHERE NOT EXISTS (
  SELECT 1 FROM pg_database WHERE datname = 'zhike_workshop'
)\gexec

\connect zhike_workshop

CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pgcrypto;
ALTER DATABASE zhike_workshop OWNER TO zhike;
