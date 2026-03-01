
-- 1. 벡터 확장 활성화 (아직 안 했다면)
CREATE EXTENSION IF NOT EXISTS vector;

-- 2. 오답 이력 테이블 생성
CREATE TABLE IF NOT EXISTS mistake_history (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id VARCHAR(50) NOT NULL,
    original_sentence TEXT NOT NULL,
    corrected_sentence TEXT NOT NULL,
    explanation TEXT,
    grammar_point VARCHAR(100),
    embedding VECTOR(1536), -- OpenAI 임베딩 규격
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 3. 유저 ID 필터링용 인덱스
CREATE INDEX IF NOT EXISTS idx_mistake_history_user_id ON mistake_history(user_id);

-- 4. 벡터 유사도 검색용 HNSW 인덱스
CREATE INDEX IF NOT EXISTS idx_mistake_history_embedding ON mistake_history 
USING hnsw (embedding vector_cosine_ops);