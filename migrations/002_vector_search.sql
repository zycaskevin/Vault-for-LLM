-- ============================================================
-- Guardrails 百科語義搜尋 — pgvector 設置
-- 在 Supabase Dashboard SQL Editor 執行
-- ============================================================

-- 1. 啟用 pgvector 擴展
CREATE EXTENSION IF NOT EXISTS vector;

-- 2. 新增 embedding 欄位（384 維，用 bge-m3 或 all-MiniLM-L6-v2）
ALTER TABLE guardrails_knowledge
ADD COLUMN IF NOT EXISTS embedding vector(384);

-- 3. 建立語義搜尋函數
CREATE OR REPLACE FUNCTION match_guardrails(
  query_embedding vector(384),
  match_threshold float DEFAULT 0.5,
  match_count int DEFAULT 5,
  filter_layer int DEFAULT NULL,
  filter_category text DEFAULT NULL
)
RETURNS TABLE (
  id uuid,
  layer smallint,
  category text,
  title text,
  content_aaak text,
  trust float,
  source text,
  similarity float
)
LANGUAGE plpgsql
AS $$
BEGIN
  RETURN QUERY
  SELECT
    gk.id,
    gk.layer,
    gk.category,
    gk.title,
    gk.content_aaak,
    gk.trust,
    gk.source,
    1 - (gk.embedding <=> query_embedding) AS similarity
  FROM guardrails_knowledge gk
  WHERE gk.embedding IS NOT NULL
    AND (filter_layer IS NULL OR gk.layer = filter_layer)
    AND (filter_category IS NULL OR gk.category = filter_category)
    AND 1 - (gk.embedding <=> query_embedding) >= match_threshold
  ORDER BY gk.embedding <=> query_embedding
  LIMIT match_count;
END;
$$;

-- 4. 建立向量索引（IVFFlat，適合 <100萬筆）
CREATE INDEX IF NOT EXISTS idx_guardrails_embedding
ON guardrails_knowledge
USING ivfflat (embedding vector_cosine_ops)
WITH (lists = 10);

-- 5. 測試查詢（執行嵌入生成後再用）
-- SELECT * FROM match_guardrails(
--   '[0.1, 0.2, ...]'::vector(384),
--   0.5, 5, NULL, NULL
-- );