-- Extensions required by AI Media OS
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";  -- full-text search on titles/keywords
CREATE EXTENSION IF NOT EXISTS "btree_gin"; -- composite GIN indexes

-- Alembic will create all tables via migrations.
-- This script only ensures extensions are available.
