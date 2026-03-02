# 테스트 런 (Test Run) 실행 명령어 모음

현재 프로젝트는 **백엔드(FastAPI)**와 **프론트엔드(Next.js)** 두 개의 서버를 각각 실행해야 웹 서비스가 온전히 동작합니다. 터미널 창을 2개 열어서 아래 명령어를 각각 실행해 주세요.

### 1. 백엔드 (FastAPI) 기동
AI 채점 및 통신을 담당하는 메인 파이썬 서버입니다. (포트: 8000)

```bash
cd /Users/kimbb/workspace/eng_study_new
source .venv/bin/activate
uvicorn api:app --host 0.0.0.0 --port 8000 --reload
```

### 2. 프론트엔드 (Next.js) 기동
사용자가 실제로 접속해서 보는 브라우저 UI 서버입니다. (포트: 3000)

```bash
cd /Users/kimbb/workspace/eng_study_new/client
npm run dev
```

### 접속 방법
위 두 개의 터미널이 모두 에러 없이 구동되었다면, 웹 브라우저를 열고 아래 주소로 접속하세요.
👉 **http://localhost:3000**
