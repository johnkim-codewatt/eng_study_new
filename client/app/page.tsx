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
    const [theme, setTheme] = useState<"retro" | "duo">("retro");

    // App Phase: "SPLASH" -> "SETUP_TOPIC" -> "SETUP_GRAMMAR" -> "CHAT"
    const [phase, setPhase] = useState<"SPLASH" | "SETUP_TOPIC" | "SETUP_GRAMMAR" | "CHAT">("SPLASH");

    // 상태 저장을 위한 임시 변수
    const [selectedTopicTemp, setSelectedTopicTemp] = useState<string>("");

    const bottomRef = useRef<HTMLDivElement>(null);
    const inputRef = useRef<HTMLInputElement>(null);

    const API_URL = "http://127.0.0.1:8000";

    const TOPIC_LIST = ["일상", "비즈니스", "여행", "학교", "연애", "취미"];
    const GRAMMAR_LIST = ["랜덤", "현재완료", "수동태", "가정법", "관계대명사", "조동사"];

    // 초기 로드 시 아트 및 테마 설정
    useEffect(() => {
        // Splash Screen 타이머 (3초 후 SETUP_TOPIC으로 이동)
        if (phase === "SPLASH") {
            const timer = setTimeout(() => {
                setPhase("SETUP_TOPIC");
                initSetupPhase();
            }, 3000);
            return () => clearTimeout(timer);
        }
    }, [phase]);

    const initSetupPhase = () => {
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
    };

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
            appendLine("tutor", `\n[📝 Question]\n${data.guide}`);
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
                appendLine("tutor", `\n================================\n[Tutor Feedback]\n${data.feedback}\n================================`);
            }
            if (data.system_alert) {
                appendLine("system", `\n[Sys] ${data.system_alert}`);
            }
            if (data.next_question) {
                appendLine("tutor", `\n[📝 Next Question]\n${data.next_question}`);
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
                    appendLine("system", "\n[Sys] 이어서 집중 학습할 문법을 선택해 주십시오.");
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
            appendLine("system", "\n[Sys] 이어서 집중 학습할 문법을 선택해 주십시오.");
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

    const toggleTheme = () => {
        setTheme(prev => prev === "retro" ? "duo" : "retro");
    };

    return (
        <div className={`min-h-screen p-2 flex flex-col select-none relative overflow-hidden transition-colors duration-300 ${theme === "retro" ? "crt-flicker" : ""}`} style={{ backgroundColor: 'var(--background)', color: 'var(--foreground)', fontFamily: 'var(--font-primary)' }} data-theme={theme}>
            {/* CRT Overlay Effect (Retro Only) */}
            {theme === "retro" && <div className="crt-overlay"></div>}

            {phase === "SPLASH" ? (
                /* Splash Screen UI */
                <div className="flex-1 flex flex-col items-center justify-center relative z-10 rounded-xl" style={{ backgroundColor: theme === "retro" ? 'var(--color-dos-blue)' : 'var(--color-duo-green)' }}>
                    <pre className="text-center font-bold mb-8 leading-tight sm:text-lg md:text-xl lg:text-2xl" style={{ color: theme === "retro" ? 'var(--warning)' : 'white' }}>
                        {theme === "retro" ? `
 _______   _______  ____    ____  ______   ______    _______  _______   
|       \\ |   ____| \\   \\  /   / /      | /  __  \\  |       \\|   ____|  
|  .--.  ||  |__     \\   \\/   / |  ,----'|  |  |  | |  .--.  |  |__     
|  |  |  ||   __|     \\      /  |  |     |  |  |  | |  |  |  |   __|    
|  '--'  ||  |____     \\    /   |  \`----.|  \`--'  | |  '--'  |  |____   
|_______/ |_______|     \\__/     \\______| \\______/  |_______| |_______|  
` : `
  ___  ___  _  _  ___  ___  ___  ___ 
 |   \\| __|| || |/ __|/ _ \\|   \\| __|
 | |) | _| | \\/ | (__| (_) | |) | _| 
 |___/|___| \\__/ \\___|\\___/|___/|___|
`}
                    </pre>
                    <div className="font-bold animate-pulse text-lg" style={{ color: theme === "retro" ? 'var(--foreground)' : 'white' }}>
                        Loading DEVCODE Tutor System... <span className={theme === "retro" ? "blink" : ""}>{theme === "retro" ? "_" : "🔄"}</span>
                    </div>
                </div>
            ) : theme === "retro" ? (
                /* 고전 스타일 윈도우 프레임 */
                <div className="flex-1 flex flex-col border-[4px] p-[4px] relative z-10" style={{ borderColor: 'var(--foreground)', backgroundColor: 'var(--color-dos-blue)' }}>
                    {/* 상태바 Header */}
                    <div className="font-bold px-4 py-2 flex justify-between items-center text-sm sm:text-base border-b-[4px]" style={{ backgroundColor: 'var(--foreground)', color: 'var(--color-dos-blue)', borderColor: 'var(--foreground)' }}>
                        <span>[ DEVCODE ] <span className="opacity-80 ml-2">{session ? `USER: ${session.user}` : "STATUS: OFFLINE"}</span></span>
                        <span className="animate-pulse">_</span>
                        <div className="flex items-center gap-4">
                            <span className="hidden sm:inline">
                                {session
                                    ? `LV: [${session.level}] | TPC: [${session.topic}]` + (session.mode === "REVIEW" ? ` | MODE: [REVIEW ${session.review_progress}]` : "")
                                    : "AWAITING CONNECTION..."}
                            </span>
                            <button
                                onClick={toggleTheme}
                                className="px-2 py-1 text-xs sm:text-sm rounded border-2 transition-transform active:scale-95"
                                style={{ backgroundColor: 'var(--color-dos-black)', color: 'var(--warning)', borderColor: 'var(--warning)' }}
                                title="Toggle Theme"
                            >
                                ✨ DUO
                            </button>
                        </div>
                    </div>

                    {/* 대화 로그 영역 */}
                    <div
                        className="flex-1 overflow-y-auto p-4 space-y-3 whitespace-pre-wrap word-break text-base sm:text-lg leading-relaxed"
                        onClick={() => inputRef.current?.focus()}
                    >
                        {lines.map((line, i) => (
                            <div
                                key={i}
                                className={
                                    line.type === "ascii" ? "font-bold tracking-widest leading-tight" :
                                        line.type === "system" ? "" :
                                            line.type === "error" ? "font-bold px-2 py-1 inline-block" :
                                                line.type === "user" ? "font-bold opacity-90" : ""
                                }
                                style={{
                                    color: line.type === "ascii" ? 'var(--warning)' :
                                        line.type === "system" ? 'var(--accent)' :
                                            line.type === "error" ? 'var(--foreground)' :
                                                line.type === "user" ? 'var(--foreground)' : 'var(--foreground)',
                                    backgroundColor: line.type === "error" ? 'var(--error)' : 'transparent'
                                }}
                            >
                                {(line.type === "system" && phase === "SETUP_TOPIC" && line.text.includes("[T")) ? (
                                    <span
                                        className="cursor-pointer transition-colors px-2 py-1 inline-block mb-1"
                                        style={{ color: 'var(--foreground)' }}
                                        onClick={() => {
                                            const match = line.text.match(/\[T\d+\]\s(.+)/);
                                            if (match) handleTopicClick(match[1]);
                                        }}
                                        onMouseEnter={(e) => {
                                            e.currentTarget.style.backgroundColor = 'var(--highlight-bg)';
                                            e.currentTarget.style.color = 'var(--highlight-fg)';
                                        }}
                                        onMouseLeave={(e) => {
                                            e.currentTarget.style.backgroundColor = 'transparent';
                                            e.currentTarget.style.color = 'var(--foreground)';
                                        }}
                                    >
                                        {line.text}
                                    </span>
                                ) : (line.type === "system" && phase === "SETUP_GRAMMAR" && line.text.includes("[G")) ? (
                                    <span
                                        className="cursor-pointer transition-colors px-2 py-1 inline-block mb-1"
                                        style={{ color: 'var(--foreground)' }}
                                        onClick={() => {
                                            const match = line.text.match(/\[G\d+\]\s(.+)/);
                                            if (match) handleGrammarClick(match[1]);
                                        }}
                                        onMouseEnter={(e) => {
                                            e.currentTarget.style.backgroundColor = 'var(--highlight-bg)';
                                            e.currentTarget.style.color = 'var(--highlight-fg)';
                                        }}
                                        onMouseLeave={(e) => {
                                            e.currentTarget.style.backgroundColor = 'transparent';
                                            e.currentTarget.style.color = 'var(--foreground)';
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
                            <div className="font-bold mt-4 animate-pulse inline-block px-2 py-1" style={{ color: 'var(--color-dos-black)', backgroundColor: 'var(--warning)' }}>
                                [Sys] PROCESSING DATA...<span className="blink">_</span>
                            </div>
                        )}
                        <div ref={bottomRef} className="h-4" />
                    </div>

                    {/* 하단 명령줄 (고정) */}
                    <form onSubmit={onSubmit} className="flex gap-2 p-3 border-t-[4px] relative z-10" style={{ borderColor: 'var(--foreground)', backgroundColor: 'var(--color-dos-blue)' }}>
                        <span className="font-bold mt-[2px] hidden sm:inline" style={{ color: 'var(--foreground)' }}>C:\\USER{">"}</span>
                        <span className="font-bold mt-[2px] sm:hidden" style={{ color: 'var(--foreground)' }}>{">"}</span>
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
                            className="flex-1 bg-transparent outline-none border-none caret-white sm:text-lg"
                            style={{ color: 'var(--warning)' }}
                            autoFocus
                            autoComplete="off"
                            spellCheck="false"
                        />
                    </form>
                </div>
            ) : (
                /* 모던 완전 듀오링고 스타일 프레임 */
                <div className="w-full max-w-2xl mx-auto flex-1 flex flex-col relative z-10 sm:my-6 bg-white sm:rounded-[2rem] shadow-2xl overflow-hidden sm:border-2 border-[var(--color-duo-border)] transition-all duration-300">
                    {/* 모던 헤더 */}
                    <div className="flex justify-between items-center p-4 border-b-2 border-slate-100 bg-white z-20">
                        <div className="flex items-center gap-3">
                            <div className="w-12 h-12 rounded-2xl bg-[var(--color-duo-green)] flex items-center justify-center text-2xl shadow-sm text-white border-b-[4px] border-[var(--color-duo-green-dark)]">🦉</div>
                            <div>
                                <h1 className="font-extrabold text-[#4b4b4b] text-xl tracking-tight leading-none mb-1">DEVCODE</h1>
                                <div className="text-sm font-bold text-[#afafaf] uppercase tracking-wide">
                                    {session ? `LV ${session.level} • ${session.topic}` : "학습 준비 중..."}
                                </div>
                            </div>
                        </div>
                        <button
                            onClick={toggleTheme}
                            className="px-4 py-2 text-sm font-bold text-[#afafaf] bg-slate-100 rounded-xl border-b-[3px] border-slate-200 active:border-b-0 active:translate-y-[3px] transition-all hover:text-[#4b4b4b] hover:bg-slate-200"
                        >
                            💾 DOS
                        </button>
                    </div>

                    {/* 대화 로그 영역 */}
                    <div
                        className="flex-1 overflow-y-auto p-4 sm:p-6 space-y-5 bg-slate-50"
                        onClick={() => inputRef.current?.focus()}
                    >
                        {lines.filter(l => l.type !== "ascii").map((line, i) => (
                            <div
                                key={i}
                                className={`flex ${line.type === "user" ? "justify-end" : "justify-start"}`}
                            >
                                {line.type !== "user" && (
                                    <div className="w-10 h-10 rounded-full bg-blue-100 flex items-center justify-center mr-3 shrink-0 text-xl border-b-2 border-blue-200 shadow-sm">
                                        {line.type === "error" ? "⚠️" : "🤖"}
                                    </div>
                                )}
                                <div className="flex flex-col max-w-[85%]">
                                    <div
                                        className={`p-4 sm:text-[17px] leading-relaxed shadow-sm whitespace-pre-wrap word-break ${line.type === "user"
                                            ? "bg-[var(--color-duo-blue)] text-white rounded-2xl rounded-tr-sm font-bold"
                                            : line.type === "error"
                                                ? "bg-red-500 text-white rounded-2xl rounded-tl-sm font-bold"
                                                : "bg-white border-2 border-slate-200 text-[#4b4b4b] rounded-2xl rounded-tl-sm font-medium"
                                            }`}
                                    >
                                        {(line.type === "system" && phase === "SETUP_TOPIC" && line.text.includes("[T")) ? (
                                            <span
                                                className="block cursor-pointer p-4 my-2 border-2 border-slate-200 rounded-xl bg-white text-[#4b4b4b] font-bold active:translate-y-1 active:border-b-2 border-b-[4px] hover:bg-blue-50 hover:border-blue-400 hover:text-blue-500 transition-all text-center text-lg"
                                                onClick={() => {
                                                    const match = line.text.match(/\[T\d+\]\s(.+)/);
                                                    if (match) handleTopicClick(match[1]);
                                                }}
                                            >
                                                {line.text.replace(/\[T\d+\]\s/, "🎯 ")}
                                            </span>
                                        ) : (line.type === "system" && phase === "SETUP_GRAMMAR" && line.text.includes("[G")) ? (
                                            <span
                                                className="block cursor-pointer p-4 my-2 border-2 border-slate-200 rounded-xl bg-white text-[#4b4b4b] font-bold active:translate-y-1 active:border-b-2 border-b-[4px] hover:bg-green-50 hover:border-green-400 hover:text-green-600 transition-all text-center text-lg"
                                                onClick={() => {
                                                    const match = line.text.match(/\[G\d+\]\s(.+)/);
                                                    if (match) handleGrammarClick(match[1]);
                                                }}
                                            >
                                                {line.text.replace(/\[G\d+\]\s/, "📝 ")}
                                            </span>
                                        ) : (
                                            line.text.replace(/\[Sys\]\s?/, "")
                                        )}
                                    </div>
                                </div>
                            </div>
                        ))}

                        {loading && (
                            <div className="flex justify-start">
                                <div className="w-10 h-10 rounded-full bg-blue-100 flex items-center justify-center mr-3 shrink-0 text-xl border-b-2 border-blue-200 shadow-sm">
                                    🤖
                                </div>
                                <div className="px-5 py-4 bg-white border-2 border-slate-200 rounded-2xl rounded-tl-sm shadow-sm flex items-center h-[56px]">
                                    <div className="flex space-x-2 items-center">
                                        <div className="w-2.5 h-2.5 bg-gray-300 rounded-full animate-bounce"></div>
                                        <div className="w-2.5 h-2.5 bg-gray-300 rounded-full animate-bounce" style={{ animationDelay: "0.15s" }}></div>
                                        <div className="w-2.5 h-2.5 bg-gray-300 rounded-full animate-bounce" style={{ animationDelay: "0.3s" }}></div>
                                    </div>
                                </div>
                            </div>
                        )}

                        <div ref={bottomRef} className="h-4" />
                    </div>

                    {/* 하단 명령줄 (Duo) */}
                    <form onSubmit={onSubmit} className="p-4 bg-white border-t-2 border-slate-100 z-20 shadow-[0_-10px_15px_-3px_rgba(0,0,0,0.03)] sm:rounded-b-3xl">
                        <div className="flex gap-3">
                            <input
                                ref={inputRef}
                                type="text"
                                value={inputVal}
                                onChange={(e) => setInputVal(e.target.value)}
                                disabled={loading}
                                placeholder={
                                    loading ? "입력 대기 중..."
                                        : phase === "SETUP_TOPIC" ? "선택하거나 입력하세요..."
                                            : phase === "SETUP_GRAMMAR" ? "선택하거나 입력하세요..."
                                                : "여기에 영작해 보세요! (!레벨 / 패스)"
                                }
                                className="flex-1 px-5 py-4 bg-slate-50 border-2 border-slate-200 focus:border-[var(--color-duo-blue)] focus:bg-white rounded-2xl outline-none text-[#4b4b4b] sm:text-lg font-bold transition-colors placeholder:text-[#afafaf] placeholder:font-bold"
                                autoFocus
                                autoComplete="off"
                                spellCheck="false"
                            />
                            <button
                                type="submit"
                                disabled={loading || !inputVal.trim()}
                                className="px-8 font-extrabold text-white rounded-2xl transition-all border-b-[4px] disabled:opacity-50 disabled:active:translate-y-0 active:border-b-0 active:translate-y-[4px] bg-[var(--color-duo-green)] border-[var(--color-duo-green-dark)] hover:bg-[#61df02] shadow-sm flex items-center justify-center text-lg hidden sm:block"
                            >
                                확인
                            </button>
                            {/* 모바일 최적화 버튼 (접근성) */}
                            <button
                                type="submit"
                                disabled={loading || !inputVal.trim()}
                                className="w-14 font-extrabold text-white rounded-2xl transition-all border-b-[4px] disabled:opacity-50 disabled:active:translate-y-0 active:border-b-0 active:translate-y-[4px] bg-[var(--color-duo-green)] border-[var(--color-duo-green-dark)] hover:bg-[#61df02] shadow-sm flex items-center justify-center text-lg sm:hidden"
                            >
                                ↑
                            </button>
                        </div>
                    </form>
                </div>
            )}
        </div>
    );
}
