"use client";

import { useEffect, useState, useRef } from "react";

type Line = {
    type: "system" | "user" | "tutor" | "error" | "ascii";
    text: string;
};

type SessionInfo = {
    user: string;
    level: string;
    topic: string;
    target_grammar?: string;
    mode?: string;
    review_progress?: string;
};

export default function TerminalUI() {
    const [lines, setLines] = useState<Line[]>([]);
    const [inputVal, setInputVal] = useState("");
    const [loading, setLoading] = useState(false);
    const [session, setSession] = useState<SessionInfo | null>(null);

    // App Phase: "SETUP_TOPIC" -> "SETUP_GRAMMAR" -> "CHAT"
    const [phase, setPhase] = useState<"SETUP_TOPIC" | "SETUP_GRAMMAR" | "CHAT">("SETUP_TOPIC");

    // 상태 저장을 위한 임시 변수
    const [selectedTopicTemp, setSelectedTopicTemp] = useState<string>("");

    const bottomRef = useRef<HTMLDivElement>(null);
    const inputRef = useRef<HTMLInputElement>(null);

    const API_URL = "http://127.0.0.1:8000";

    const TOPIC_LIST = ["일상", "비즈니스", "여행", "학교", "연애", "취미"];
    const GRAMMAR_LIST = ["랜덤", "현재완료", "수동태", "가정법", "관계대명사", "조동사"];

    // 초기 로드 시 아트 및 테마 설정
    useEffect(() => {
        appendLine("ascii", `
========================================================
   ___   ___  ____    ___  _____  ____   ___   ____ 
  / _ \\ / _ \\/ __/___/ _ \\/ __/ |/ / _ \\/ __/  / __/
 / // // // /\\ \\/___/ ___/ _//    / // / _/   _\\ \\  
/____/ \\___/___/   /_/  /___/_/|_/____/___/  /___/  
                                                    
  C:\\\\> AI JUNIOR TUTOR SYSTEM v2.0 (MODEM LINK OK)
========================================================
    `);
        appendLine("system", "[Sys] 통신 모듈 초기화 중...");

        // SETUP 단계 돌입 (주제)
        setTimeout(() => {
            appendLine("system", "[Sys] 오늘의 학습 주제를 선택해 주십시오. (번호 입력 혹은 클릭)");
            TOPIC_LIST.forEach((t, idx) => {
                appendLine("system", `    [T${idx + 1}] ${t}`);
            });
        }, 500);

        // 자동 포커스
        if (inputRef.current) inputRef.current.focus();
    }, []);

    // 로그 자동 스크롤
    useEffect(() => {
        bottomRef.current?.scrollIntoView({ behavior: "smooth" });
    }, [lines, loading]);

    const appendLine = (type: Line["type"], text: string) => {
        setLines(prev => [...prev, { type, text }]);
    };

    const initChatPhase = async (selectedTopic: string, selectedGrammar: string) => {
        setPhase("CHAT");
        setLoading(true);

        try {
            const grammarCmdValue = selectedGrammar === "랜덤" ? "리셋" : selectedGrammar;
            appendLine("system", "[Sys] 메인 서버(Mainframe) 접속 요청 중...");

            // 주제와 문법 파라미터를 담아 초기화 요청 (새 문제 생성)
            const res = await fetch(`${API_URL}/api/init?topic=${selectedTopic}&grammar=${grammarCmdValue}`);
            const data = await res.json();

            if (data.session_info) setSession(data.session_info);

            appendLine("system", `[Sys] ${data.message}`);
            appendLine("tutor", `\\n[📝 Question]\\n${data.guide}`);
        } catch (err: any) {
            appendLine("error", `[Fatal] 서버 연결 실패: ${err.message}`);
        } finally {
            setLoading(false);
            setTimeout(() => inputRef.current?.focus(), 100);
        }
    };

    const handleCommand = async (fullInput: string) => {
        const parts = fullInput.split(" ");
        const cmd = parts[0].substring(1);
        const val = parts.slice(1).join(" ");

        setLoading(true);
        try {
            const res = await fetch(`${API_URL}/api/command`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ command_type: cmd, command_value: val })
            });
            const data = await res.json();
            appendLine("system", `[Sys] ${data.message}`);

            // 주제나 레벨이 바뀌었을 수 있으므로 시각화 갱신용으로 로컬 세션 패치
            if (data.session_info) {
                setSession(data.session_info);
            }
            if (data.next_question) {
                appendLine("tutor", `\n[📝 Question]\n${data.next_question}`);
            }
        } catch (err: any) {
            appendLine("error", `[Error] 명령어 처리 실패: ${err.message}`);
        } finally {
            setLoading(false);
        }
    };

    const handleChat = async (text: string) => {
        setLoading(true);
        try {
            const res = await fetch(`${API_URL}/api/chat`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ user_input: text })
            });
            const data = await res.json();

            if (data.session_info) {
                setSession(data.session_info);
            }

            if (data.feedback) {
                appendLine("tutor", `\\n================================\\n[Tutor Feedback]\\n${data.feedback}\\n================================`);
            }
            if (data.system_alert) {
                appendLine("system", `\\n[Sys] ${data.system_alert}`);
            }
            if (data.next_question) {
                appendLine("tutor", `\\n[📝 Next Question]\\n${data.next_question}`);
            }
        } catch (err: any) {
            appendLine("error", `[Error] 서버 응답 타임아웃: ${err.message}`);
        } finally {
            setLoading(false);
            setTimeout(() => inputRef.current?.focus(), 100);
        }
    };

    const onSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        if (!inputVal.trim() || loading) return;

        const currentInput = inputVal.trim();
        appendLine("user", `C:\\\\USER> ${currentInput}`);
        setInputVal("");

        if (phase === "SETUP_TOPIC") {
            const num = parseInt(currentInput.replace("T", ""));
            let topic = "";
            if (!isNaN(num) && num >= 1 && num <= TOPIC_LIST.length) {
                topic = TOPIC_LIST[num - 1];
            } else if (TOPIC_LIST.includes(currentInput)) {
                topic = currentInput;
            }

            if (topic) {
                appendLine("system", `[Sys] '${topic}' 테마가 선택되었습니다.`);
                setSelectedTopicTemp(topic);
                setPhase("SETUP_GRAMMAR");

                // 문법 선택 안내 출력
                setTimeout(() => {
                    appendLine("system", "\\n[Sys] 이어서 집중 학습할 문법을 선택해 주십시오.");
                    GRAMMAR_LIST.forEach((g, idx) => {
                        appendLine("system", `    [G${idx + 1}] ${g}`);
                    });
                }, 300);
            } else {
                appendLine("error", "[Error] 올바른 주제 번호나 이름을 입력하세요.");
            }
            return;
        }

        if (phase === "SETUP_GRAMMAR") {
            const num = parseInt(currentInput.replace("G", ""));
            let grammar = "";
            if (!isNaN(num) && num >= 1 && num <= GRAMMAR_LIST.length) {
                grammar = GRAMMAR_LIST[num - 1];
            } else if (GRAMMAR_LIST.includes(currentInput)) {
                grammar = currentInput;
            }

            if (grammar) {
                appendLine("system", `[Sys] '${grammar}' 문법이 선택되었습니다.`);
                await initChatPhase(selectedTopicTemp, grammar);
            } else {
                appendLine("error", "[Error] 올바른 문법 번호나 이름을 입력하세요.");
            }
            return;
        }

        // CHAT Phase
        if (currentInput.startsWith("!")) {
            await handleCommand(currentInput);
        } else {
            await handleChat(currentInput);
        }
    };

    const handleTopicClick = (topic: string) => {
        if (phase !== "SETUP_TOPIC" || loading) return;
        appendLine("user", `C:\\\\USER> ${topic}`);
        appendLine("system", `[Sys] '${topic}' 테마가 선택되었습니다.`);
        setSelectedTopicTemp(topic);
        setPhase("SETUP_GRAMMAR");

        setTimeout(() => {
            appendLine("system", "\\n[Sys] 이어서 집중 학습할 문법을 선택해 주십시오.");
            GRAMMAR_LIST.forEach((g, idx) => {
                appendLine("system", `    [G${idx + 1}] ${g}`);
            });
        }, 300);
    };

    const handleGrammarClick = async (grammar: string) => {
        if (phase !== "SETUP_GRAMMAR" || loading) return;
        appendLine("user", `C:\\\\USER> ${grammar}`);
        appendLine("system", `[Sys] '${grammar}' 문법이 선택되었습니다.`);
        await initChatPhase(selectedTopicTemp, grammar);
    };

    return (
        <div className="min-h-screen bg-[#050505] p-2 flex flex-col font-mono text-[#00ff41] select-none">
            {/* 고전 스타일 윈도우 프레임 */}
            <div className="flex-1 flex flex-col border-2 border-[#00ff41] p-[2px]">
                {/* 상태바 Header */}
                <div className="bg-[#00ff41] text-[#050505] font-bold px-2 py-1 flex justify-between items-center text-xs sm:text-sm">
                    <span>{session ? `USER: ${session.user}` : "STATUS: OFFLINE"}</span>
                    <span className="animate-pulse">_</span>
                    <span>
                        {session
                            ? `LV: [${session.level}] | TPC: [${session.topic}]` + (session.mode === "REVIEW" ? ` | MODE: [REVIEW ${session.review_progress}]` : "")
                            : "AWAITING CONNECTION..."}
                    </span>
                </div>

                {/* 대화 로그 영역 */}
                <div
                    className="flex-1 overflow-y-auto p-4 space-y-3 whitespace-pre-wrap word-break text-sm sm:text-base leading-relaxed"
                    onClick={() => inputRef.current?.focus()}
                >
                    {lines.map((line, i) => (
                        <div
                            key={i}
                            className={
                                line.type === "ascii" ? "text-amber-500 font-bold tracking-widest leading-tight" :
                                    line.type === "system" ? "text-amber-500" :
                                        line.type === "error" ? "text-red-500 font-bold bg-red-900/30 px-1 inline-block" :
                                            line.type === "user" ? "text-white font-bold opacity-90" :
                                                "text-[#00ff41]"
                            }
                        >
                            {(line.type === "system" && phase === "SETUP_TOPIC" && line.text.includes("[T")) ? (
                                // Setup 단계에서 선택지 클릭 가능하게 처리
                                <span
                                    className="cursor-pointer hover:bg-[#00ff41] hover:text-black hover:font-bold transition-colors px-1"
                                    onClick={() => {
                                        const match = line.text.match(/\\[T\\d+\\]\\s(.+)/);
                                        if (match) handleTopicClick(match[1]);
                                    }}
                                >
                                    {line.text}
                                </span>
                            ) : (line.type === "system" && phase === "SETUP_GRAMMAR" && line.text.includes("[G")) ? (
                                // 문법 Setup 단계에서 선택지 클릭 가능하게 처리
                                <span
                                    className="cursor-pointer hover:bg-[#00ff41] hover:text-black hover:font-bold transition-colors px-1"
                                    onClick={() => {
                                        const match = line.text.match(/\\[G\\d+\\]\\s(.+)/);
                                        if (match) handleGrammarClick(match[1]);
                                    }}
                                >
                                    {line.text}
                                </span>
                            ) : (
                                line.text
                            )}
                        </div>
                    ))}

                    {loading && (
                        <div className="text-amber-600 font-bold mt-4 animate-pulse">
                            [Sys] PROCESSING DATA...<span className="blink">_</span>
                        </div>
                    )}

                    <div ref={bottomRef} className="h-4" />
                </div>

                {/* 하단 명령줄 (고정) */}
                <form onSubmit={onSubmit} className="flex gap-2 p-2 border-t-2 border-[#00ff41] bg-[#050505]">
                    <span className="text-white font-bold mt-[2px] hidden sm:inline">C:\\USER{">"}</span>
                    <span className="text-white font-bold mt-[2px] sm:hidden">{">"}</span>
                    <input
                        ref={inputRef}
                        type="text"
                        value={inputVal}
                        onChange={(e) => setInputVal(e.target.value)}
                        disabled={loading}
                        placeholder={
                            loading ? ""
                                : phase === "SETUP_TOPIC" ? "주제 번호(T1~T6)를 입력하거나 클릭하세요..."
                                    : phase === "SETUP_GRAMMAR" ? "문법 번호(G1~G6)를 입력하거나 클릭하세요..."
                                        : "영작문을 입력! (!레벨 / 패스)"
                        }
                        className="flex-1 bg-transparent text-[#00ff41] outline-none border-none placeholder-green-800/50 caret-white"
                        autoFocus
                        autoComplete="off"
                        spellCheck="false"
                    />
                </form>
            </div>
        </div>
    );
}
