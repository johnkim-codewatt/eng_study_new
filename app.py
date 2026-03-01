# app.py
# Personalized History-RAG Tutor - Initial Setup

def main():
    print("=== Personalized History-RAG Tutor ===")
    
    # 1. 유저 진입 (하드코딩)
    USER_ID = "test_user_001"
    print(f"\n[System] 유저 식별 완료: {USER_ID}")
    
    # 2. 공부 레벨 선택 (하드코딩 - 초보/중급/고수/초고수)
    STUDY_LEVEL = "중급"
    print(f"[System] 레벨 선택 완료: {STUDY_LEVEL}")
    
    # 3. 주제 선택 (기본 - 일상생활)
    STUDY_TOPIC = "일상생활"
    print(f"[System] 주제 선택 완료: {STUDY_TOPIC}")
    
    # 4. 타겟 문법 (기본 - 랜덤)
    TARGET_GRAMMAR = None
    
    print("\n[System] 초기 설정이 완료되었습니다. 학습을 시작합니다...")
    print("[Tip] 학습 중 언제든지 아래의 명령어를 입력해 설정을 바꿀 수 있습니다.")
    print("  - 레벨 변경: '!레벨 [초보/중급/고수/초고수]' (예: !레벨 초보)")
    print("  - 주제 변경: '!주제 [일상/비즈니스/여행/학교 등]' (예: !주제 비즈니스)")
    print("  - 문법 지정: '!문법 [원하는문법]' (예: !문법 가정법) / 취소: '!문법 리셋'")
    print("  - 문제 넘기기: '다른문제' 또는 '패스'\n")
    
    # 코어 엔진 조립 (LangGraph 및 LLM 체인 로드)
    # 💡 [AI 스터디 포인트] 
    # AI 구동을 위한 핵심 함수들(문제 생성, 복습 생성, 채점 파이프라인)을 호출할 준비를 합니다.
    from core_engine import build_tutor_graph, generate_question, generate_review_question
    from database import get_recent_mistakes
    tutor_graph = build_tutor_graph()
    
    # [신규 추가] 오답 복습 모드 설정
    ENABLE_REVIEW = True
    
    if ENABLE_REVIEW:
        review_items = get_recent_mistakes(USER_ID, limit=3)
        if review_items:
            print("\n[System] 💡 오답 복습 모드를 시작합니다. 지난번에 틀렸던 문제들을 먼저 복습할게요!")
            for idx, item in enumerate(review_items, 1):
                print(f"\n==================== [복습 문제 {idx}/{len(review_items)}] ====================")
                review_data = generate_review_question(item)
                print(f"\n{review_data['full_guide']}")
                print("=======================================================\n")
                
                while True:
                    user_input = input("[User] 위 복습 '영작 문제'를 영작하시거나 질문을 입력하세요 (종료: 'quit', 패스: '패스'): ")
                    if user_input.lower() in ['quit', 'exit']:
                        print("\n[System] 학습 시스템을 종료합니다.")
                        return
                    
                    if user_input.strip() == "패스":
                        break
                        
                    tutor_state = {
                        "user_id": USER_ID,
                        "current_question": review_data["question_text"],
                        "current_input": user_input,
                        "intent": "translation",
                        "is_correct": False,
                        "expected_tag": "",
                        "history_context": "",
                        "feedback": "",
                        "corrected_text": "",
                        "grammar_tag": "",
                        "explanation": ""
                    }
                    
                    # LangGraph 실행 (Retrieve -> Feedback -> Save 순차 실행)
                    # 💡 [AI 스터디 포인트] 
                    # StateGraph 객체인 tutor_graph에 초기 상태(tutor_state)를 주입하면,
                    # 정의된 노드(함수)들을 거치며 State 딕셔너리가 업데이트되고 최종 결과를 반환합니다.
                    result = tutor_graph.invoke(tutor_state)
                    
                    print(f"\n=== [Tutor Feedback] ===")
                    print(result["feedback"])
                    
                    intent = result.get("intent", "translation")
                    if intent == "translation":
                        input("\n[System] 계속하시려면 Enter를 누르세요...")
                        break
                        
            print("\n[System] 🎉 복습이 모두 끝났습니다! 이제 오늘의 새로운 학습 메인 루틴으로 넘어갑니다.")
    
    # 핵심 학습 사이클
    current_question_data = None
    
    while True:
        try:
            # 4.1 가이드 및 문제 생성 (Step 1)
            if not current_question_data:
                print(f"\\n=================== [현재 설정: {STUDY_LEVEL} | {STUDY_TOPIC} | {TARGET_GRAMMAR or '랜덤 문법'}] ===================")
                # 💡 [AI 스터디 포인트] Zero-shot Generation (단발성 프롬프팅 적용)
                # 단순히 LLM에게 규칙만 주고 즉석에서 문제, 해설, 예문을 통째로 지어내게 만드는 기술입니다.
                current_question_data = generate_question(level=STUDY_LEVEL, topic=STUDY_TOPIC, target_grammar=TARGET_GRAMMAR)
                print("\\n[오늘의 학습 가이드]")
                print(current_question_data["full_guide"])
                print("==========================================================================\n")
            
            # 유저 측 대기
            user_input = input("[User] 영작 번역이나 궁금한 질문, 또는 명령어(!레벨, !주제, !문법)를 입력하세요 (종료: 'quit'): ").strip()
            
            if not user_input:
                continue
                
            if user_input.lower() in ['quit', 'exit']:
                break
                
            # 명령어 처리 로직
            if user_input.startswith("!레벨"):
                parts = user_input.split(maxsplit=1)
                if len(parts) > 1:
                    STUDY_LEVEL = parts[1]
                    print(f"\n[System] 📈 학습 레벨이 '{STUDY_LEVEL}'(으)로 변경되었습니다. 새로운 문제를 즉시 출제합니다.")
                    current_question_data = None
                else:
                    print("\n[System] ⚠️ 사용법: !레벨 [초보/중급/고수/초고수]")
                continue
                
            if user_input.startswith("!주제"):
                parts = user_input.split(maxsplit=1)
                if len(parts) > 1:
                    STUDY_TOPIC = parts[1]
                    print(f"\n[System] 🎨 학습 주제가 '{STUDY_TOPIC}'(으)로 변경되었습니다. 새로운 문제를 즉시 출제합니다.")
                    current_question_data = None
                else:
                    print("\n[System] ⚠️ 사용법: !주제 [일상/비즈니스/여행/학교 등]")
                continue
                
            if user_input.startswith("!문법"):
                parts = user_input.split(maxsplit=1)
                if len(parts) > 1:
                    target = parts[1]
                    if target == "리셋":
                        TARGET_GRAMMAR = None
                        print("\n[System] 🎲 타겟 문법이 '랜덤'으로 초기화되었습니다. 새로운 문제를 즉시 출제합니다.")
                    else:
                        TARGET_GRAMMAR = target
                        print(f"\n[System] 🎯 타겟 문법이 '{TARGET_GRAMMAR}'(으)로 고정되었습니다. 새로운 문제를 즉시 출제합니다.")
                    current_question_data = None
                else:
                    print("\n[System] ⚠️ 사용법: !문법 [원하는문법] (예: !문법 가정법) / 취소: !문법 리셋")
                continue
            
            # 초기 State 설정
            tutor_state = {
                "user_id": USER_ID,
                "current_question": current_question_data["question_text"],
                "current_input": user_input,
                "intent": "translation",
                "is_correct": False,
                "expected_tag": "",
                "history_context": "",
                "feedback": "",
                "corrected_text": "",
                "grammar_tag": "",
                "explanation": ""
            }
            
            # LangGraph 실행 (Retrieve -> Feedback -> Save)
            # 💡 [AI 스터디 포인트] 핵심 채점 파이프라인 (RAG + Self-RAG 복합체)
            # 유저의 입력을 단순히 LLM 하나로 채점하는 것이 아니라,
            # 의도 파악 -> 과거 DB 검색(RAG) -> 답변 생성 -> 자체 검증(Self-RAG) -> DB 저장 의
            # 체계적인 에이전트 파이프라인을 거쳐 환각(Hallucination) 없는 고품질 피드백을 만들어냅니다.
            result = tutor_graph.invoke(tutor_state)
            
            print("\\n=== [Tutor Feedback] ===")
            print(result["feedback"])
            
            intent = result.get("intent", "translation")
            
            # 영작을 시도했거나 다른 문제를 요청한 경우에만 현재 문제 클리어
            if intent in ["translation", "new_question"]:
                current_question_data = None
                
            if intent != "new_question":
                input("\\n[System] 계속하시려면 Enter를 누르세요...")
            
        except KeyboardInterrupt:
            break
            
    print("\\n[System] 학습이 종료되었습니다.")

if __name__ == '__main__':
    main()
