# Personalized History-RAG English Tutor

AI 기반의 개인화 맞춤형 영어 회화/영작 튜터 시스템입니다.
일반적인 챗봇 형태를 넘어서, 사용자의 **과거 오답 데이터를 기억하고 분석**하여 최적화된 맞춤형 피드백과 복습 문제를 제공하는 고도화된 AI 에이전트 파이프라인을 갖추고 있습니다.

## 🌟 핵심 기능 및 AI 아키텍처

본 프로젝트는 최신 LLM 에이전트 설계 패턴인 **LangGraph 기반 RAG + Self-RAG 복합 파이프라인**으로 구축되었습니다.

### 1. 문제 출제 엔진 (Zero-Shot Generation)
단순한 정적 문제은행 방식이 아닌, 사용자의 **레벨(초보/중급/고수)**, **주제(일상/비즈니스 등)**, **특정 타겟 문법**에 맞추어 매번 새로운 영어 영작 문제를 동적으로 창작(Generation)하여 제시합니다.

### 2. 하이브리드 벡터 검색 (Vector Retrieval - RAG)
사용자가 오답을 제출할 경우, 해당 문장을 숫자의 배열(Embedding Vector)로 변환하여 PostgreSQL(pgvector) 데이터베이스에서 이전에 틀렸던 유사한 문장들을 찾아옵니다.
특히 코사인 유사도뿐만 아니라 문법 태그(Grammar Point)가 일치할 경우 **가산점을 부여해 최상위로 끌어올리는 하이브리드 재정렬(Re-ranking)** 기법을 사용하여 검색 정확도를 극대화했습니다. 

### 3. '기억력' 기반 맞춤형 피드백 생상 (Retrieval-Augmented Generation)
검색된 과거 오답 기록을 프롬프트에 동적으로 주입(Inject)하여 튜터(LLM)에게 전달합니다. 이를 통해 튜터는 *"지난번에도 관사를 빼먹으셨는데, 이번에도 같은 실수가 보이네요!"* 와 같이 사용자의 취약점을 정확히 짚어주는 **개인화된 분석 피드백**을 제공합니다.

### 4. 자가 검증 시스템 (Self-RAG)
생성형 AI의 맹점인 환각(Hallucination) 현상을 방지하기 위해, 온도(Temperature)가 0으로 세팅된 냉정한 **'검수자(QA) LLM' 노드**가 튜터의 채점 결과를 한 번 더 검증합니다. 출제 의도와 맞지 않거나 억지 논리가 발견되면 즉각적으로 피드백을 교정 및 덮어씁니다.

### 5. 에이전트 상태 라우팅 (LangGraph)
이 모든 복잡한 과정(`의도 판별` -> `DB 검색` -> `피드백 생성` -> `자가 검증` -> `DB 저장`)을 `TutorState`라는 단일 객체 상태 머신(State Machine)으로 묶어, 안정적이고 체계적인 에이전트 워크플로우를 구현했습니다.

---

## 🛠️ 기술 스택 (Tech Stack)

* **언어 및 프레임워크:** Python 3, LangChain, LangGraph
* **LLM & 임베딩:** OpenAI API (`gpt-4o-mini`, `text-embedding-3-small`)
* **데이터베이스:** PostgreSQL, pgvector (Vector DB)
* **인프라:** Docker, Docker Compose

---

## 🚀 설치 및 실행 방법

### 1. 환경 설정 (.env)
프로젝트 루트 디렉토리에 `.env` 파일을 생성하고 아래와 같이 API 키와 DB 주소를 입력합니다.

```env
OPENAI_API_KEY="sk-your-openai-api-key-here"
DATABASE_URL="postgresql://myuser:mypassword@localhost:5433/eng_study_db"
```

### 2. Database (PostgreSQL + pgvector) 컨테이너 실행
Docker Compose를 사용하여 벡터 검색을 지원하는 데이터베이스를 띄웁니다.
```bash
docker-compose up -d
```

### 3. 패키지 설치
Python 가상환경(venv)을 만들고 필요한 라이브러리들을 설치합니다.
```bash
python -m venv .venv
source .venv/bin/activate  # Mac/Linux
# .venv\Scripts\activate   # Windows

pip install langchain-openai langgraph psycopg2-binary pgvector python-dotenv
```

### 4. 데이터베이스 초기화
최초 1회 실행하여 테이블 및 Vector 확장을 세팅합니다.
```bash
python database.py
```

### 5. 튜터 시스템 실행
메인 앱을 실행하여 학습을 시작합니다.
```bash
python app.py
```

## 🎮 인앱(In-app) 명령어 가이드
터미널에서 학습을 진행하는 동안 아래의 명령어들을 입력해 학습 환경을 실시간으로 바꿀 수 있습니다.

* **레벨 변경:** `!레벨 [초보/중급/고수/초고수]` (예: `!레벨 고수`)
* **주제 변경:** `!주제 [일상/비즈니스/여행/학교 등]` (예: `!주제 비즈니스`)
* **문법 지정:** `!문법 [원하는 문법]` (예: `!문법 현재완료`)
* **문법 지정 취소:** `!문법 리셋`
* **문제 당장 넘기기:** `다른문제` 혹은 `패스`
* **시스템 종료:** `quit` 혹은 `exit`
