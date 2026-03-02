import os
import yaml
from typing import TypedDict, Annotated, List, Dict, Any
from langgraph.graph import StateGraph, END
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from database import search_history, save_history
from dotenv import load_dotenv

load_dotenv()

# 프롬프트 YAML 로드 (prompts/prompts.yaml)
_PROMPT_PATH = os.path.join(os.path.dirname(__file__), "prompts", "prompts.yaml")
with open(_PROMPT_PATH, encoding="utf-8") as _f:
    PROMPTS = yaml.safe_load(_f)

# 유저 설정에 따른 라우팅을 지원하는 기본 모델 설정 (gpt-4o-mini)
llm = ChatOpenAI(model="gpt-4o-mini", temperature=0.5)
CORRECTNESS_THRESHOLD = 7  # 정답 인정 기준 점수 (0~10)


# 0. 문제 출제 엔진 추가 (Step 4.1)
def generate_question(level: str, topic: str, target_grammar: str = None, current_question: str = "") -> Dict[str, str]:
    # null처리
    current_question = current_question if current_question else ""

    """유저의 레벨과 주제에 맞춰 학습할 문법, 예문, 그리고 영작할 한국어 문장을 출제합니다. target_grammar가 주어지면 해당 문법을 무조건 출제합니다."""
    print(f"\n[GenerateQuestion] {level} 레벨의 '{topic}' 주제로 문제 생성 중...")
    
    grammar_instruction = f"유저가 오늘 영작해 볼 만한 핵심 문법 패턴 '{target_grammar}'에 대해 집중적으로 다루어 줘." if target_grammar else "유저가 오늘 영작해 볼 만한 핵심 문법 패턴 1가지를 랜덤하게 선정해."
    
    system_prompt = PROMPTS["generate_question"]["system"].format(
        grammar_instruction=grammar_instruction,
        current_question=current_question
    )
    human_prompt = PROMPTS["generate_question"]["human"]
    
    prompt = ChatPromptTemplate.from_messages([
        ("system", system_prompt),
        ("human", human_prompt)
    ])
    # 무논리 환각을 줄이기 위해 온도를 조정 0.4X
    # 이렇게 하면 문제 생성시, 매번 같은 문제만 출제함. 0.8로 수정하니 굉장히 다양한 문제 출제됨.
    diverse_llm = ChatOpenAI(model="gpt-4o", temperature=0.8)
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
    
    system_prompt = PROMPTS["generate_review"]["system"]
    human_prompt = PROMPTS["generate_review"]["human"]
    
    prompt = ChatPromptTemplate.from_messages([
        ("system", system_prompt),
        ("human", human_prompt)
    ])
    
    diverse_llm = ChatOpenAI(model="gpt-4o", temperature=0.7)
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
    retry_count: int        # (신규) 검증 피드백 반복 횟수
    reviewer_feedback: str  # (신규) 검증관이 재작성을 요청한 피드백 내용

# 2. RetrieveNode 구현 (사전 판별 + 스마트 검색)
# 💡 [AI 스터디 포인트] Intent Classification & Routing (의도 분류 및 라우팅)
# 무작정 무거운 메인 LLM을 부르기 전에, 
# 1. 유저의 텍스트가 번역 시도인지 단순 잡담인지를 판별하고
# 2. 만약 정답이라면 뒤의 무거운 RAG 단계를 아예 스킵해버리는 비용/속도 최적화 기법입니다.
def retrieve_node(state: TutorState) -> Dict[str, Any]:
    print(f"\n[RetrieveNode] 유저 입력 분석 및 1차 검증 시작(잡담 필터링)...")

    pre_eval_prompt = PROMPTS["retrieve"]["pre_eval"]
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
            # 💡 연관성 1위(Top 1) 오답 1개만 추출하여 LLM 채점관에게 컨텍스트로 제공
            top1_original, top1_corrected, top1_grammar, _ = raw_history[0]
            history_context = f"1. 이전입력: '{top1_original}' -> 피드백: '{top1_corrected}' (태그: {top1_grammar})"
            
            debug_lines = [f"{idx}. {r[0]} ({r[2]})" for idx, r in enumerate(raw_history[:3], 1)]
            
            # [디버깅] 검색된 내용 터미널 출력
            print(f"\n---------------------------------------")
            print(f"[디버깅] 검색top3 : {', '.join(debug_lines)}")
            print(f"[디버깅] 최종 선택된 오답 : {top1_original} / {top1_grammar} 문법틀림")
            print(f"------------------------------------------")
            
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
            ("system", PROMPTS["feedback"]["question_system"]),
            ("human", "{current_input}")
        ])
        ans = (prompt | llm).invoke({"current_input": state["current_input"]}).content
        return {"feedback": ans, "corrected_text": "", "grammar_tag": "", "explanation": "", "better_expression": ""}
        
    """검색된 '과거 오답 이력'과 '현재 입력 문장'을 LLM에 전달하여 '기억력' 기반 피드백을 생성합니다."""
    # 💡 [AI 스터디 포인트] RAG (Retrieval-Augmented Generation)
    # 데이터베이스에서 찾아온 유저의 과거 오답 이력(<history_context>)을 시스템 프롬프트에 동적으로 "주입"합니다.
    # LLM은 원래 유저를 모르지만, 이 주입된 컨텍스트 덕분에 "지난번에도 틀렸네요!"라는 개인화된 대답이 가능해집니다.
    print("[FeedbackNode] LLM 번역 피드백 생성 중...")
    
    current_question = state.get("current_question", "")
    current_input = state.get("current_input", "")

    system_prompt = PROMPTS["feedback"]["translation_system"].format(
        current_question=current_question,
        current_input=current_input,
        expected_tag=state.get("expected_tag", ""),
        history_context=state["history_context"]
    )

    reviewer_feedback = state.get("reviewer_feedback", "")
    if reviewer_feedback:
        print(f"[FeedbackNode] ⚠️ 수석 교사(QA)의 지시를 받아 피드백을 재작성 중입니다... (재시도: {state.get('retry_count', 0)}회)")
        human_prompt = PROMPTS["feedback"]["human_retry"].format(reviewer_feedback=reviewer_feedback)
    else:
        human_prompt = PROMPTS["feedback"]["human_normal"]
        
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
    
    # 안전한 파싱을 위한 초기값 할당
    corrected_text = ""
    grammar_tag = ""
    explanation = ""
    better_expression = ""
    
    if "Corrected Text" in raw_feedback:
        try:
            # 예시 파싱 (추후 Structured Output 등 도입 시 수정)
            corrected_text = raw_feedback.split("Corrected Text")[1].split("\n")[0].replace(":", "").strip()
        except:
            pass
            
    if "Grammar Tag" in raw_feedback:
         try:
            # "Grammar Tag" 텍스트 이후부터 다음 번호 매기기 전까지 혹은 첫 줄바꿈까지만 추출
            grammar_tag_raw = raw_feedback.split("Grammar Tag")[1].split("4. 오답")[0]
            grammar_tag = grammar_tag_raw.split("\n")[0].replace(":", "").replace(")", "").strip()
            # 만약 줄바꿈이 없어서 설명까지 딸려왔다면 대비책
            if len(grammar_tag) > 30:
                grammar_tag = state.get("expected_tag", "None")
         except:
             pass

    if "Explanation" in raw_feedback:
         try:
            explanation_raw = raw_feedback.split("Explanation")[1].split("5. 추천")[0]
            explanation = explanation_raw.split("\n")[0].replace(":", "").strip()
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
    
    qa_prompt = PROMPTS["verify"]["qa_prompt"].format(
        current_question=state.get('current_question', ''),
        current_input=state['current_input'],
        feedback=state.get('feedback', '')
    )
    
    reviewer_llm = ChatOpenAI(model="gpt-4o", temperature=0.0)
    validation_res = reviewer_llm.invoke(qa_prompt).content.strip()
    
    if "PASS" in validation_res.upper()[:10]:
        print("[VerifyNode] 검증 통과 (오류 없음).")
        return {"reviewer_feedback": ""} # 검증 통과 시 루프 종료 신호
    
    retry_count = state.get("retry_count", 0)
    
    if retry_count >= 2:
        print("[VerifyNode] ⚠️ 최대 재시도 횟수 초과. 더 이상 반복하지 않고 현재 생성된 피드백을 강제로 채택합니다.")
        return {"reviewer_feedback": ""}
        
    print(f"[VerifyNode] ⚠️ 피드백에서 오류를 발견했습니다! 튜터에게 재작성을 요청합니다. (재시도 {retry_count + 1}/2)")
    print(f"=== 검증관 피드백: {validation_res}")

    # 생성된 피드백 텍스트 내용을 직접 덮어쓰지 않고, 
    # 검증관의 피드백만 상태에 담아서 돌려보내면 LangGraph 루프가 FeedbackNode로 돌아감.
    return {
        "reviewer_feedback": validation_res,
        "retry_count": retry_count + 1
    }


    

# # 루브릭 검증 적용
# def verify_node(state: TutorState) -> Dict[str, Any]:
#     intent = state.get("intent", "translation")
    
#     # 일반 질문이거나 완벽한 정답인 경우 검증을 패스합니다.
#     if intent != "translation" or state.get("is_correct"):
#         print("[VerifyNode] 완벽한 정답이거나 오답 피드백이 아니므로 검증을 스킵합니다.")
#         return {"reviewer_feedback": ""}
        
#     print("[VerifyNode] 루브릭(Rubric) 기반 정밀 검증 및 환각 체크 중...")
    
#     print("=================")
#     print("1. 출제된 한국어 문제: ", state.get('current_question', ''))
#     print("2. 유저의 원본 입력: ", state['current_input'])
#     print("3. 과거 오답 이력(RAG): ", state.get('history_context', '없음'))
#     print("4. feedback : ", state.get('feedback', ''))
#     print("=================")


#     # 루브릭 기반의 엄격한 프롬프트 구성
#     qa_prompt = f"""당신은 까다롭기로 유명한 '수석 영어 교육 에디터'입니다.
# 아래 제공된 [데이터]를 바탕으로 튜터의 피드백을 검토하고, **단 하나의 루브릭이라도 미달되면 즉시 REJECT** 하십시오.

# [데이터]
# 1. 출제된 한국어 문제: {state.get('current_question', '')}
# 2. 유저의 원본 입력: {state['current_input']}
# 3. 과거 오답 이력(RAG): {state.get('history_context', '없음')}
# 4. 튜터 생성 피드백:
# ---
# {state.get('feedback', '')}
# ---

# [검수 루브릭 - 아래 중 하나라도 해당하면 REJECT]
# 1. **의도 불일치**: 튜터가 제시한 '튜터 생성 피드백'이 원래 '출제된 한국어 문제'의 시제, 강조점, 뉘앙스를 제대로 살리지 못했는가?
# 2. **역번역(Back-translation) 오류**: 튜터의 '튜터 생성 피드백'을 기반으로 다시 영어 문장을 만들면, 기존의 '출제된 한국어 문제' 와 문장 의미가 일치하는가?
# 3. **기억력 결핍**: [과거 오답 이력]이 존재함에도 불구하고, 피드백에서 이를 언급하며 유저의 습관을 지적하지 않았는가? (이력이 있을 때만 해당)
# 4. **설명 환각**: 튜터가 설명한 문법 규칙이 틀렸거나, 유저가 하지 않은 실수를 지적하는 등 환각 증상이 있는가?

# [응답 규칙]
# - 모든 루브릭을 완벽히 통과할 경우에만: 'PASS' 출력.
# - 하나라도 문제가 있을 경우: 'REJECT'라고 명시하고, 몇 번 루브릭 위반인지와 함께 **튜터가 다음 번에 어떻게 수정해야 하는지 구체적인 가이드라인**을 작성하십시오.
# """
    
#     # 검증 노드는 일관성을 위해 temperature를 0으로 고정합니다.
#     # 성능을 위해 gpt-4o를 사용하는 것을 강력 추천하지만, 기존 환경에 맞춰 유지합니다.
#     reviewer_llm = ChatOpenAI(model="gpt-4o", temperature=0.0) 
#     validation_res = reviewer_llm.invoke(qa_prompt).content.strip()
    
#     # 'PASS' 여부 확인 (대소문자 무관, 앞부분 일치 확인)
#     if validation_res.upper().startswith("PASS"):
#         print("[VerifyNode] ✅ 모든 루브릭 통과 (PASS).")
#         return {"reviewer_feedback": ""} 
    
#     retry_count = state.get("retry_count", 0)
    
#     # 최대 재시도 체크
#     if retry_count >= 2:
#         print("[VerifyNode] ⚠️ 최대 재시도(2회)를 초과했습니다. 품질이 낮더라도 현재 피드백을 종료합니다.")
#         return {"reviewer_feedback": ""}
        
#     print(f"[VerifyNode] ❌ REJECT 발생! 지적 사항: {validation_res[:100]}...")
#     print(f"            (재시도 카운트: {retry_count + 1}/2)")
    
#     # 검증 결과(비판)를 reviewer_feedback에 담아 FeedbackNode로 되돌려 보냄
#     return {
#         "reviewer_feedback": validation_res,
#         "retry_count": retry_count + 1
#     }





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
    
    # 💡 [AI 스터디 포인트] Conditional Edges (조건부 간선)
    # verify_node의 결과(reviewer_feedback 유무)에 따라 어디로 갈지 결정하는 라우팅 함수
    def route_after_verify(state: TutorState) -> str:
        if state.get("reviewer_feedback"):
            return "feedback" # 반려 사유가 있으면 다시 피드백을 작성하러 감
        return "save"         # 통과했으면 저장하러 감
        
    workflow.add_conditional_edges("verify", route_after_verify, {"feedback": "feedback", "save": "save"})
    
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
        "explanation": "",
        "better_expression": "",
        "retry_count": 0,
        "reviewer_feedback": ""
    }
    
    print("=== Core Engine Test Run ===")
    result = app_graph.invoke(test_state)
    
    print("\\n[최종 피드백 결과]")
    print(result["feedback"])
    print("\\n[추출 데이터]")
    print(f"- Corrected: {result['corrected_text']}")
    print(f"- Tag: {result['grammar_tag']}")
