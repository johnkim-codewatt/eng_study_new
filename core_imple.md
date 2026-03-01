Core Routine 구현 방식 제안
1. Database Interface (database.py)
가장 먼저 데이터가 오가는 통로를 정의합니다. psycopg2와 pgvector를 사용하여 아주 간결하게 구현합니다.

search_history(user_id, current_input): 현재 문장과 유사한 과거 오답을 벡터 검색으로 가져옵니다.

save_history(user_id, original, corrected, tag): 새로운 오답 발생 시 벡터화하여 저장합니다.

2. LangGraph 노드 설계 (The Core Logic)
그래프의 각 노드는 독립적인 기능을 수행하며 상태(State)를 업데이트합니다.

RetrieveNode: 유저의 입력이 들어오면 DB에서 과거 이력을 뽑아 history 상태에 저장합니다.

FeedbackNode: (중요) LLM에게 **"현재 문장"**과 **"과거 이력"**을 동시에 전달합니다.

Prompt 전략: "유저가 이번에 A를 틀렸는데, 과거에 B와 C도 틀린 적이 있습니다. 이 패턴을 엮어서 잔소리(?)를 해주세요."

SaveNode: 피드백이 완료된 후, 이번 실수를 다음번 RAG를 위해 DB에 기록합니다.

3. 피드백 엔진의 '기억력' 구현 (Prompting)
단순히 "틀렸어요"가 아니라, 아래와 같은 구조의 프롬프트를 구성하여 RAG의 효용을 극대화합니다.

System Prompt 예시:
"너는 유저의 오답 패턴을 분석하는 튜터다. 제공된 history_context를 살펴보고, 유저가 반복적으로 범하는 문법적 오류가 있다면 반드시 언급해라. 만약 처음 틀리는 거라면 친절하게 설명만 해줘."

---

