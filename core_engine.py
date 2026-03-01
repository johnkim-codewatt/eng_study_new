import os
from typing import TypedDict, Annotated, List, Dict, Any
from langgraph.graph import StateGraph, END
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from database import search_history, save_history
from dotenv import load_dotenv

load_dotenv()

# 유저 설정에 따른 라우팅을 지원하는 기본 모델 설정 (gpt-4o-mini)
llm = ChatOpenAI(model="gpt-4o-mini", temperature=0.3)
CORRECTNESS_THRESHOLD = 8  # 정답 인정 기준 점수 (0~10)

# 0. 문제 출제 엔진 추가 (Step 4.1)
def generate_question(level: str, topic: str, target_grammar: str = None) -> Dict[str, str]:
    """유저의 레벨과 주제에 맞춰 학습할 문법, 예문, 그리고 영작할 한국어 문장을 출제합니다. target_grammar가 주어지면 해당 문법을 무조건 출제합니다."""
    print(f"\n[GenerateQuestion] {level} 레벨의 '{topic}' 주제로 문제 생성 중...")
    
    grammar_instruction = f"유저가 오늘 영작해 볼 만한 핵심 문법 패턴 '{target_grammar}'에 대해 집중적으로 다루어 줘." if target_grammar else "유저가 오늘 영작해 볼 만한 핵심 문법 패턴 1가지를 랜덤하게 선정해."
    
    system_prompt = f"""너는 친절하고 전문적인 영어 학습 튜터야.
주어진 학습 레벨과 주제에 맞춰, {grammar_instruction}
그리고 그 문법에 대한 간단한 설명, 영어 예문 1개, 그리고 유저가 직접 영작해 볼 한국어 문제 1개를 출제해 줘.

[매우 중요] 출제하는 '한국어 영작 문제(Question)'는 반드시 네가 선정한 '오늘의 문법(Grammar)' 패턴을 100% 정확하게 평가할 수 있어야 하며, 문법적으로 모순이 없어야 해.
예를 들어, '현재완료형(Present Perfect)'을 주제로 잡았다면, 한국어 문제에 '어제, 지난 주말' 같은 명백한 과거 시제 부사를 넣어서 유저가 오답을 쓰도록 유도하면 절대 안 돼!

모든 설명과 출력은 반드시 **한국어**로 작성해야 해. 

다음과 같은 항목들로 명확히 구분해서 출력해줘:
1. 오늘의 문법 (Grammar)
2. 간단한 설명 (Explanation)
3. 예문 (Example)
4. 영작 문제 (Question) - 유저가 영어로 번역해야 할 한국어 문장
"""
    
    human_prompt = "레벨: {level}, 주제: {topic}\n오늘의 문제를 내 줘!"
    
    prompt = ChatPromptTemplate.from_messages([
        ("system", system_prompt),
        ("human", human_prompt)
    ])
    # 무논리 환각을 줄이기 위해 온도를 0.4로 조정
    diverse_llm = ChatOpenAI(model="gpt-4o-mini", temperature=0.4)
    chain = prompt | diverse_llm
    response = chain.invoke({"level": level, "topic": topic})
    raw_content = response.content
    
    # 문제 파싱 로직
    # 단순화를 위해 일단 출력된 내용 전체와 가장 나중에 유저에게 던질 '문제'만 가볍게 파싱
    question_text = ""
    if "영작 문제" in raw_content:
        question_text = raw_content.split("영작 문제")[1].replace("(", "").replace("Question)", "").replace(":", "").strip()
    
    return {
        "full_guide": raw_content,
        "question_text": question_text
    }

# 0.5 오답 복습 문제 출제 엔진 (Step 1.5)
def generate_review_question(history_record: tuple) -> Dict[str, str]:
    """유저의 과거 오답 기록을 바탕으로 관련 문법 복습 문제와 안내문을 생성합니다."""
    original, corrected, grammar_point, explanation = history_record
    print(f"\n[ReviewQuestion] 과거 오답 '{grammar_point}' 복습 문제 생성 중...")
    
    system_prompt = """너는 친절하고 꼼꼼한 영어 학습 튜터야.
유저가 과거에 틀렸던 아래의 오답 내용을 바탕으로, 유저가 다시 비슷한 형태의 문장을 영작해 보며 연습할 수 있도록 새로운 한국어 영작문 1개를 출제해 줘.

[과거 오답 기록]
- 유저 제출: {original}
- 올바른 문장: {corrected}
- 핵심 문법 주제: {grammar_point}
- 당시 튜터 설명: {explanation}

반드시 다음과 같은 항목들로 명확히 구분해서 **한국어**로 출력해 줘.

1. 복습 도입부 (Intro): "복습 시간입니다. 지난번 틀렸던 [문법주제]에 대해서 살펴볼게요." 와 같은 친절하고 격려하는 도입부 및 문법 설명 요약
2. 새로운 예문 (Example): {grammar_point} 문법을 잘 보여주는 완전히 새로운 영어 예문 1개와 한국어 뜻
3. 영작 문제 (Question): 유저가 직접 다시 영어로 번역해야 할 **새로운 한국어 문장 1개** (오직 한국어 문제만 제시하고, 절대 정답이나 이유를 미리 출력하지 마세요)
"""
    
    human_prompt = "나의 과거 실수를 바탕으로 복습 문제를 하나 내 줘."
    
    prompt = ChatPromptTemplate.from_messages([
        ("system", system_prompt),
        ("human", human_prompt)
    ])
    
    diverse_llm = ChatOpenAI(model="gpt-4o-mini", temperature=0.7)
    chain = prompt | diverse_llm
    response = chain.invoke({
        "original": original,
        "corrected": corrected,
        "grammar_point": grammar_point,
        "explanation": explanation
    })
    
    raw_content = response.content
    question_text = ""
    if "영작 문제" in raw_content:
        # 간단 파싱
        try:
            question_text = raw_content.split("영작 문제")[1].replace("(", "").replace("Question)", "").replace(":", "").strip()
        except:
            pass
            
    return {
        "full_guide": raw_content,
        "question_text": question_text
    }

# 1. State 정의
# 💡 [AI 스터디 포인트] LangGraph State (상태 관리)
# 각각의 노드(함수)들이 독립적으로 돌아가는 대신, 하나의 큰 딕셔너리(State) 객체를 돌려보며 
# 각 파이프라인 단계에서 필요한 데이터(intent, history_context 등)를 끼워넣어 누적시킵니다.
class TutorState(TypedDict):
    user_id: str
    current_question: str   # (신규) 출제된 문제
    current_input: str      # 유저가 방금 입력한 영작문(또는 질문)
    intent: str             # (신규) 분류: translation, question, unrelated, new_question
    is_correct: bool        # (신규) 1단계 검증: 문장이 정답인지 여부
    expected_tag: str       # (신규) 오답일 경우 예상되는 핵심 문법 테그
    history_context: str    # DB에서 조회된 과거 이력
    feedback: str           # LLM이 생성한 피드백 (과거 이력 + 현재 교정)
    corrected_text: str     # LLM이 수정한 올바른 문장 (정답)
    grammar_tag: str        # 주요 문법 에러 태그 (예: "article", "tense")
    explanation: str        # 추가된 설명 필드 (선택 사항)
    better_expression: str  # (신규) 일상/구어체 추천 표현

# 2. RetrieveNode 구현 (사전 판별 + 스마트 검색)
# 💡 [AI 스터디 포인트] Intent Classification & Routing (의도 분류 및 라우팅)
# 무작정 무거운 메인 LLM을 부르기 전에, 유저의 텍스트가 번역 시도인지 단순 잡담인지를 판별하고
# 만약 정답이라면 뒤의 무거운 RAG 단계를 아예 스킵해버리는 비용/속도 최적화 기법입니다.
def retrieve_node(state: TutorState) -> Dict[str, Any]:
    print(f"\n[RetrieveNode] 유저 입력 분석 및 1차 검증 시작...")
    
    pre_eval_prompt = """유저의 입력을 분석하고 평가해 줘.
출제된 한국어 영작 문제: {current_question}
유저 입력: {current_input}

분류 기준:
1. Intent: 다음 중 하나로 분류해.
   - 'new_question': 유저가 명시적으로 다른 문제나 새로운 영작 문제를 내달라고 요구하는 경우 (예: "다른문제", "패스", "다른 문장")
   - 'unrelated': 영어 학습과 전혀 무관한 질문이나 대화 (예: "안녕", "오늘 날씨 어때", "배고파")
   - 'question': 영작 시도와 무관한 일반적인 영어 문법, 단어, 학습 방법에 대한 질문인 경우 (예: "현재완료가 뭐야?", "이 단어 뜻 알려줘")
   - 'translation': 출제된 한국어 영작 문제에 대해 영어로 번역/작문을 직접 시도한 경우 (기본)

2. Score: 만약 Intent가 'translation'이라면, 이 영작의 정확도와 자연스러움을 0에서 10 사이의 점수로 평가해 (10점이 완벽한 원어민 수준). 그 외 Intent는 0점.
3. Tag: 만약 Intent가 'translation'이고 문법적 오류가 있다면 가장 핵심적인 문법 규칙 1단어(예: Article, Tense). 완벽한 문장(10점)이거나 그 외 Intent는 'None'.

출력 형식:
Intent: [분류단어]
Score: [점수]
Tag: [태그 단어]
"""
    chain = ChatPromptTemplate.from_template(pre_eval_prompt) | llm
    eval_res = chain.invoke({
        "current_question": state.get("current_question", "없음"),
        "current_input": state["current_input"]
    }).content
    
    intent = "translation"
    score = 0
    expected_tag = "None"
    
    for line in eval_res.split('\n'):
        if line.startswith("Intent:"):
            intent = line.split("Intent:")[1].strip().lower()
        elif line.startswith("Score:"):
            try:
                score = int(line.split("Score:")[1].strip())
            except:
                pass
        elif line.startswith("Tag:"):
            expected_tag = line.split("Tag:")[1].strip()

    is_correct = False
    if intent == "translation" and score >= CORRECTNESS_THRESHOLD:
        is_correct = True

    print(f"[RetrieveNode] 결과 -> 의도: {intent}, 정답여부: {is_correct} (점수: {score}), 예상태그: {expected_tag}")

    history_context = ""
    # 2.2 의도가 번역이 아니면 DB 검색 스킵
    if intent != "translation":
        print(f"[RetrieveNode] '{intent}' 의도 감지. DB 검색 스킵.")
    # 2.3 정답이면 DB 검색 스킵
    elif is_correct:
        print("[RetrieveNode] 정답이므로 과거 오답 이력 검색을 스킵합니다.")
        history_context = "해당 문장은 완벽한 정답입니다. 칭찬만 해주세요."
    else:
        print(f"[RetrieveNode] {expected_tag} 오류 감지. DB에서 과거 유사 사례 검색 중...")
        # (임시) 현재 search_history는 expected_tag 지원 전이므로 기존처럼 호출, database.py 업데이트 후 인자 추가 요망
        raw_history = search_history(user_id=state["user_id"], current_input=state["current_input"], limit=10, expected_tag=expected_tag)
        
        if not raw_history:
            history_context = "과거 오답 기록이 없습니다."
            print("[디버깅] 검색top3 : 없음")
        else:
            history_lines = []
            debug_lines = []
            for idx, row in enumerate(raw_history, 1):
                original, corrected, grammar, explanation = row
                history_lines.append(f"{idx}. 이전입력: '{original}' -> 피드백: '{corrected}' (태그: {grammar})")
                debug_lines.append(f"{idx}. {original} ({grammar})")
            
            history_context = "\\n".join(history_lines)
            
            # [디버깅] 검색된 내용 터미널 출력
            print(f"\n---")
            print(f"[디버깅] 검색top3 : {', '.join(debug_lines[:3])}")
            print(f"[디버깅] 최종문장(입력) : {state['current_input']}")
            print(f"---")
            
        print(f"[RetrieveNode] 검색 완료. 컨텍스트 길이: {len(history_context)}")
        
    return {
        "intent": intent,
        "is_correct": is_correct,
        "expected_tag": expected_tag,
        "history_context": history_context
    }

# 3. FeedbackNode (LLM 코어) 구현
def feedback_node(state: TutorState) -> Dict[str, Any]:
    intent = state.get("intent", "translation")
    
    if intent == "unrelated":
        return {"feedback": "학습과 관련된 질문을 해주세요.", "corrected_text": "", "grammar_tag": "", "explanation": "", "better_expression": ""}
    elif intent == "new_question":
        return {"feedback": "네, 다른 문제를 준비할게요!", "corrected_text": "", "grammar_tag": "", "explanation": "", "better_expression": ""}
    elif intent == "question":
        print("[FeedbackNode] 일반 학습 질문에 답변 생성 중...")
        prompt = ChatPromptTemplate.from_messages([
            ("system", "너는 친절하고 전문적인 영어 학습 튜터야. 유저의 영어 학습 관련 일반적인 질문에 알기 쉽고 친절하게 한국어로 대답해줘."),
            ("human", "{current_input}")
        ])
        ans = (prompt | llm).invoke({"current_input": state["current_input"]}).content
        return {"feedback": ans, "corrected_text": "", "grammar_tag": "", "explanation": "", "better_expression": ""}
        
    """검색된 과거 이력과 현재 입력 문장을 LLM에 전달하여 '기억력' 기반 피드백을 생성합니다."""
    # 💡 [AI 스터디 포인트] RAG (Retrieval-Augmented Generation)
    # 데이터베이스에서 찾아온 유저의 과거 오답 이력(<history_context>)을 시스템 프롬프트에 동적으로 "주입"합니다.
    # LLM은 원래 유저를 모르지만, 이 주입된 컨텍스트 덕분에 "지난번에도 틀렸네요!"라는 개인화된 대답이 가능해집니다.
    print("[FeedbackNode] LLM 번역 피드백 생성 중...")
    
    # System Prompt: '기억력' 구현 전략 + 한국어 응답 강제 + 과거 이력 멘션
    system_prompt = f"""너는 유저의 오답 패턴을 분석하는 훌륭하고 매우 친절한 영어 튜터다.
유저가 번역해야 할 '한국어 원래 문제'의 의도와 문맥을 바탕으로 유저의 영작을 평가해야 해.
단순히 유저가 만든 영어 문장이 문법적으로 맞는지 틀린지만 보지 말고, 원래 한국어 문제에서 의도했던 시제나 핵심 문법(예: 현재완료형 등)을 제대로 구현했는지 확인해 줘.
만약 한국어 문제에 제시된 시간 부사(예: 지난 주말)와 요구되는 문법(예: 현재완료형) 사이에 문법적 충돌이 생긴다면, 어느 한쪽으로 맞추어(예: 부사를 빼거나, 과거형으로만 쓰거나) 친절하게 대안 두 가지를 모두 설명해 주는 것도 좋아.

제공된 <history_context>를 살펴보고, 만약 유저가 과거에도 이번과 유사한 문법(특히 {state.get("expected_tag", "")})을 틀린 적이 있다면, 피드백 메시지에 반드시 그 점을 상기시켜 줘. 
(예시: "자주 틀리는 오답이네요! 지난번에도 관사를 빠뜨리셨는데, 이번에도 같은 실수가 보이네요. 주의해 보세요!")
만약 처음 틀리는 부분이라면 친절하게 설명만 해 줘.

모든 피드백과 설명은 반드시 **한국어(Korean)**로 작성해야 해 (교정된 영어 문장 제외).

<history_context>
{state["history_context"]}
</history_context>

또한, 최종 결과로 다음 항목들은 반드시 별도로 구분해서 출력해줘.
1. 따뜻하고 분석적인 피드백 메시지 (과거 이력이 반영된 내용)
2. 수정된 완벽한 원어민 문장 (Corrected Text)
3. 핵심 문법 오류 태그 단어 1개 (Grammar Tag) - 짧은 영어 단어
4. 오답 이유에 대한 간단한 한국어 설명 (Explanation)
5. 추천 표현 (Better Expression) - "일상에서는 이렇게 쓰면 좋습니다: ~" 같이 원어민들이 더 자주 쓰는 자연스러운 구어체 대안 1개 제안
"""
    
    human_prompt = "출제된 한국어 문제: {current_question}\\n내 영작을 평가하고 교정해 줘: \\n{current_input}"
    
    prompt = ChatPromptTemplate.from_messages([
        ("system", system_prompt),
        ("human", human_prompt)
    ])
    
    chain = prompt | llm
    
    response = chain.invoke({
        "current_question": state.get("current_question", ""),
        "current_input": state["current_input"]
    })
    
    raw_feedback = response.content
    
    # 간단한 파싱 로직 (실무에서는 Structured Output 활용 권장)
    # 여기서는 간단히 전체를 feedback으로 담고, 추후 파싱 로직 고도화 필요
    feedback = raw_feedback
    corrected_text = state.get("current_input", "")
    grammar_tag = state.get("expected_tag", "None")
    explanation = ""
    
    if "Corrected Text" in raw_feedback:
        try:
            # 예시 파싱 (추후 Structured Output 등 도입 시 수정)
            corrected_text = raw_feedback.split("Corrected Text")[1].split("\\n")[0].replace(":", "").strip()
        except:
            pass
            
    if "Grammar Tag" in raw_feedback:
         try:
            # "Grammar Tag" 텍스트 이후부터 다음 번호 매기기 전까지 혹은 첫 줄바꿈까지만 추출
            grammar_tag_raw = raw_feedback.split("Grammar Tag")[1].split("4. 오답")[0]
            grammar_tag = grammar_tag_raw.split("\\n")[0].replace(":", "").replace(")", "").strip()
            # 만약 줄바꿈이 없어서 설명까지 딸려왔다면 대비책
            if len(grammar_tag) > 30:
                grammar_tag = state.get("expected_tag", "None")
         except:
             pass

    if "Explanation" in raw_feedback:
         try:
            explanation_raw = raw_feedback.split("Explanation")[1].split("5. 추천")[0]
            explanation = explanation_raw.split("\\n")[0].replace(":", "").strip()
         except:
             pass
             
    if "Better Expression" in raw_feedback:
         try:
            better_expression_raw = raw_feedback.split("Better Expression")[1]
            better_expression = better_expression_raw.replace(":", "").replace(")", "").strip()
         except:
             pass
    
    print("[FeedbackNode] 피드백 생성 완료.")
    
    return {
        "feedback": feedback,
        "corrected_text": corrected_text,
        "grammar_tag": grammar_tag,
        "explanation": explanation,
        "better_expression": better_expression
    }

# 4. 자가 검증 (Self-RAG) Node 구현
# 💡 [AI 스터디 포인트] Self-RAG (자가 점검 / Hallucination 방지)
# 생성형 AI는 그럴듯한 거짓말(환각)을 할 리스크가 큽니다.
# 이를 방지하기 위해 생성(Feedback) 노드 다음에 무조건 온도(Temperature)가 0인 매우 엄격한 
# 평가자 LLM 노드를 하나 더 붙여서, 스스로의 결과물을 채점하고 이상하면 교정해버리는 안전장치입니다.
def verify_node(state: TutorState) -> Dict[str, Any]:
    intent = state.get("intent", "translation")
    
    # 일반 질문이거나 완벽한 정답인 경우 검증을 패스합니다.
    if intent != "translation" or state.get("is_correct"):
        print("[VerifyNode] 완벽한 정답이거나 오답 피드백이 아니므로 검증을 스킵합니다.")
        return {}
        
    print("[VerifyNode] 생성된 피드백의 정확성 및 환각(Hallucination) 검증 중...")
    
    qa_prompt = f"""너는 매우 꼼꼼한 최고 수석 영어 교사(QA 리뷰어)야.
아래에 제공된 '출제된 한국어 문제', '유저의 원본 입력', 그리고 '하급 튜터가 생성한 피드백'을 검토해 줘.

[출제된 한국어 문제]: {state.get('current_question', '')}
[유저 원본 입력]: {state['current_input']}
[튜터 생성 피드백]:
{state.get('feedback', '')}

검토 기준:
1. 튜터가 제시한 교정이 '출제된 한국어 문제'의 본래 의미와 문법적 의도를 잘 반영하여 채점했는가? (단순히 영어 문장 철자만 보지 말고, 원래 한국어 문장을 올바로 번역했는지 확인)
2. 튜터가 제시한 교정 문장(Corrected Text)이 원어민 기준으로 100% 자연스럽고 완벽한가?
3. 튜터가 설명(Explanation)한 문법 규칙이 사실에 부합하며 억지(Hallucination)가 없는가?

만약 위 기준을 완벽하게 통과한다면, 어떠한 설명도 없이 대문자로 딱 한 단어 'PASS'만 출력해.
만약 조금이라도 수정해야 할 부분이 있다면, 기존 튜터의 피드백 형식을 **그대로** 단 1자도 빼놓지 않고 지키면서 네가 직접 수정한 완벽한 버전의 전체 피드백을 다시 출력해 줘. 

형식:
1. 따뜻하고 분석적인 피드백 메시지 (과거 이력이 반영된 내용)
2. 수정된 완벽한 원어민 문장 (Corrected Text)
3. 핵심 문법 오류 태그 단어 1개 (Grammar Tag) - 짧은 영어 단어
4. 오답 이유에 대한 간단한 한국어 설명 (Explanation)
5. 추천 표현 (Better Expression) - "일상에서는 이렇게 쓰면 좋습니다: ~" 같이 원어민들이 더 자주 쓰는 자연스러운 구어체 대안 1개 제안
"""
    
    reviewer_llm = ChatOpenAI(model="gpt-4o-mini", temperature=0.0)
    validation_res = reviewer_llm.invoke(qa_prompt).content.strip()
    
    if validation_res == "PASS":
        print("[VerifyNode] 검증 통과 (오류 없음).")
        return {}
    
    print("[VerifyNode] ⚠️ 피드백에서 오류를 발견했습니다! 피드백을 교정 및 덮어씁니다.")
    
    raw_feedback = validation_res
    feedback = raw_feedback
    corrected_text = state.get("corrected_text", "")
    grammar_tag = state.get("grammar_tag", "")
    explanation = state.get("explanation", "")
    
    if "Corrected Text" in raw_feedback:
        try:
            corrected_text = raw_feedback.split("Corrected Text")[1].split("\\n")[0].replace(":", "").replace(")", "").strip()
        except:
            pass
            
    if "Grammar Tag" in raw_feedback:
         try:
            grammar_tag_raw = raw_feedback.split("Grammar Tag")[1].split("4. 오답")[0]
            grammar_tag = grammar_tag_raw.split("\\n")[0].replace(":", "").replace(")", "").strip()
            if len(grammar_tag) > 30:
                grammar_tag = state.get("expected_tag", "None")
         except:
             pass

    if "Explanation" in raw_feedback:
         try:
            explanation_raw = raw_feedback.split("Explanation")[1].split("5. 추천")[0]
            explanation = explanation_raw.split("\\n")[0].replace(":", "").replace(")", "").strip()
         except:
             pass
             
    if "Better Expression" in raw_feedback:
         try:
            better_expression_raw = raw_feedback.split("Better Expression")[1]
            better_expression = better_expression_raw.replace(":", "").replace(")", "").strip()
         except:
             pass
             
    return {
        "feedback": feedback,
        "corrected_text": corrected_text,
        "grammar_tag": grammar_tag,
        "explanation": explanation,
        "better_expression": better_expression
    }

# 5. SaveNode 구현
def save_node(state: TutorState) -> Dict[str, Any]:
    intent = state.get("intent", "translation")
    
    if intent != "translation":
        print("[SaveNode] 번역/작문 제출이 아니므로 히스토리에 기록하지 않습니다.")
        return {}
        
    if state.get("is_correct"):
        print("[SaveNode] 완벽한 정답이므로 오답 DB에 기록하지 않습니다.")
        return {}
        
    """피드백이 완성된 오답 문장을 다시 벡터 DB에 기록합니다."""
    print(f"[SaveNode] 이번 입력({state['current_input']})을 히스토리 DB에 기록합니다.")
    
    # 원문, 수정본, 태그 정보를 벡터화하여 저장
    save_history(
        user_id=state["user_id"],
        original=state["current_input"],
        corrected=state["corrected_text"],
        grammar_point=state["grammar_tag"],
        explanation=state.get("explanation", "")
    )
    
    print("[SaveNode] DB 기록 완료.")
    return {}

# 6. Graph 조립
# 💡 [AI 스터디 포인트] DAG (Directed Acyclic Graph)
# 노드(작업 단위)들을 가져와서 어떤 순서로 실행할지 선을 그어주는(Edge 연결) 파이프라인 조립체입니다.
def build_tutor_graph() -> StateGraph:
    """핵심 튜터링 사이클 LangGraph를 조립합니다."""
    workflow = StateGraph(TutorState)
    
    # 노드 추가 (함수를 그래프에 매핑)
    workflow.add_node("retrieve", retrieve_node)
    workflow.add_node("feedback", feedback_node)
    workflow.add_node("verify", verify_node)
    workflow.add_node("save", save_node)
    
    # 엣지 연결 (여기서는 순차 실행이지만, 조건부 라우팅도 가능합니다)
    workflow.set_entry_point("retrieve")
    workflow.add_edge("retrieve", "feedback")
    workflow.add_edge("feedback", "verify")
    workflow.add_edge("verify", "save")
    workflow.add_edge("save", END)
    
    return workflow.compile()

# 단독 실행 테스트용
if __name__ == "__main__":
    app_graph = build_tutor_graph()
    
    test_state = {
        "user_id": "test_user_001",
        "current_question": "나는 어제 병원에 갔다.",
        "current_input": "I go to hospital yesterday.",
        "intent": "translation",
        "is_correct": False,
        "expected_tag": "",
        "history_context": "",
        "feedback": "",
        "corrected_text": "",
        "grammar_tag": "",
        "explanation": ""
    }
    
    print("=== Core Engine Test Run ===")
    result = app_graph.invoke(test_state)
    
    print("\\n[최종 피드백 결과]")
    print(result["feedback"])
    print("\\n[추출 데이터]")
    print(f"- Corrected: {result['corrected_text']}")
    print(f"- Tag: {result['grammar_tag']}")
