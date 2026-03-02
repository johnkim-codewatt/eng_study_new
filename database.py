import os
import psycopg2
from pgvector.psycopg2 import register_vector
from langchain_openai import OpenAIEmbeddings
from dotenv import load_dotenv

load_dotenv()

# 데이터베이스 연결 설정
DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise ValueError(".env 파일에서 DATABASE_URL을 찾을 수 없습니다.")

# OpenAI 임베딩 설정 (기본값)
# 💡 [AI 스터디 포인트] Embedding (임베딩)
# 사람이 쓰는 텍스트(문장)를 인공지능이 이해할 수 있는 숫자의 배열(벡터)로 변환해주는 모델입니다.
# 뜻이 비슷한 문장들은 숫자(좌표)상으로도 가까운 곳에 위치하게 됩니다. (의미 기반 검색의 핵심)
embeddings = OpenAIEmbeddings(model="text-embedding-3-small")

def get_connection():
    """데이터베이스 커넥션을 반환하고 pgvector 확장을 등록합니다."""
    conn = psycopg2.connect(DATABASE_URL)
    # pgvector 타입 등록
    register_vector(conn)
    return conn

def init_db():
    """초기 테이블 및 확장 설정을 진행합니다."""
    conn = get_connection()
    cur = conn.cursor()
    
    # pgvector 확장 활성화
    cur.execute("CREATE EXTENSION IF NOT EXISTS vector;")
    
    # mistake_history 테이블 생성
    cur.execute("""
        CREATE TABLE IF NOT EXISTS mistake_history (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id VARCHAR(50) NOT NULL,
            original_sentence TEXT NOT NULL,
            corrected_sentence TEXT NOT NULL,
            explanation TEXT,
            grammar_point VARCHAR(100),
            -- 💡 [AI 스터디 포인트] pgvector를 활용한 벡터 저장소
            -- 텍스트가 의미 단위로 수치화된 '리스트'를 저장하는 특수 컬럼입니다. 
            -- text-embedding-3-small 모델이 1536개의 숫자로 문장을 압축하므로 크기를 1536으로 맞춥니다.
            embedding VECTOR(1536), -- OpenAI 임베딩 규격
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        );
    """)
    
    # 검색 성능 향상을 위한 인덱스 생성
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_mistake_history_user_id ON mistake_history(user_id);
    """)
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_mistake_history_embedding ON mistake_history 
        USING hnsw (embedding vector_cosine_ops);
    """)
    
    conn.commit()
    cur.close()
    conn.close()

def save_history(user_id: str, original: str, corrected: str, grammar_point: str = None, explanation: str = None):
    """새로운 오답 발생 시 텍스트를 벡터화하여 저장합니다."""
    conn = get_connection()
    cur = conn.cursor()
    
    # 입력 문장 임베딩 생성
    vector = embeddings.embed_query(original)
    
    cur.execute("""
        INSERT INTO mistake_history (user_id, original_sentence, corrected_sentence, grammar_point, explanation, embedding)
        VALUES (%s, %s, %s, %s, %s, %s::vector)
    """, (user_id, original, corrected, grammar_point, explanation, vector))
    
    conn.commit()
    cur.close()
    conn.close()

def search_history(user_id: str, current_input: str, limit: int = 10, expected_tag: str = "None"):
    """현재 문장과 유사한 과거 오답 이력을 검색하되, expected_tag와 일치하는 이력에 가산점을 부여(Re-ranking)합니다."""
    conn = get_connection()
    cur = conn.cursor()
    
    # 쿼리 문장 벡터화
    query_vector = embeddings.embed_query(current_input)
    
    # 코사인 유사도(1 - 코사인거리)를 구하고, expected_tag와 grammar_point가 일치하면(대소문자 무시) 가산점(0.5)을 더해 정렬
    # 💡 [AI 스터디 포인트] Hybrid Search & Re-ranking (하이브리드 검색 및 재정렬)
    # 단순히 문장의 뜻이 비슷한 것(벡터 유사도, 1 - 코사인거리)만 찾는 것이 아니라,
    # 문법 태그(grammar)가 완벽히 일치하는 데이터에 인위적으로 +0.5 점수를 더해서(부스팅)
    # 최상단으로 끌어올리는 아주 실용적인 RAG 검색 기법입니다.
    cur.execute("""
        SELECT original_sentence, corrected_sentence, grammar_point, explanation 
        FROM mistake_history
        WHERE user_id = %s
        ORDER BY 
            (1 - (embedding <=> %s::vector)) + 
            CASE WHEN grammar_point ILIKE %s THEN 0.5 ELSE 0 END DESC
        LIMIT %s
    """, (user_id, query_vector, f"%{expected_tag}%", limit))
    
    results = cur.fetchall()
    
    cur.close()
    conn.close()
    
    return results

# [신규 추가] 최근 오답 이력 조회
# 최근 3개의 오답 이력을 가져옴
def get_recent_mistakes(user_id: str, limit: int = 3):
    """지정된 유저의 가장 최근 오답 이력을 가져옵니다. 복습용으로 사용됩니다."""
    conn = get_connection()
    cur = conn.cursor()
    
    cur.execute("""
        SELECT original_sentence, corrected_sentence, grammar_point, explanation 
        FROM mistake_history
        WHERE user_id = %s
        ORDER BY created_at DESC
        LIMIT %s
    """, (user_id, limit))
    
    results = cur.fetchall()
    
    cur.close()
    conn.close()
    
    return results

def get_top_mistake_grammars(user_id: str, limit: int = 10):
    """가장 많이 틀린 문법 태그 기준으로 대표 오답 1건씩 반환합니다. 복습 모드에서 사용됩니다."""
    conn = get_connection()
    cur = conn.cursor()

    # grammar_point별 오답 횟수를 집계하고, 각 태그에서 가장 최근 레코드 1건만 추출
    cur.execute("""
        WITH ranked AS (
            SELECT
                original_sentence, corrected_sentence, grammar_point, explanation,
                COUNT(*) OVER (PARTITION BY grammar_point) AS cnt,
                ROW_NUMBER() OVER (PARTITION BY grammar_point ORDER BY created_at DESC) AS rn
            FROM mistake_history
            WHERE user_id = %s
              AND grammar_point IS NOT NULL
              AND grammar_point != ''
        )
        SELECT original_sentence, corrected_sentence, grammar_point, explanation
        FROM ranked
        WHERE rn = 1
        ORDER BY cnt DESC
        LIMIT %s
    """, (user_id, limit))

    results = cur.fetchall()
    cur.close()
    conn.close()
    return results

# 모듈 단독 실행 시 테이블 자동 생성 보장
if __name__ == "__main__":
    init_db()
    print("Database Initialized Successfully.")
