import { useEffect, useRef, useState, type FormEvent } from "react";
import { AnimatePresence, motion } from "motion/react";
import { Bot, SendHorizontal, ShieldCheck, Sparkles } from "lucide-react";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

type ChatRole = "user" | "assistant";

interface ChatMessage {
  id: string;
  role: ChatRole;
  content: string;
}

// AI 尚未串接，固定以此句回覆所有提問。
const FIXED_REPLY = "我只是個語言模型，這件事我幫不上忙。";
const REPLY_DELAY_MS = 700;

const GREETING: ChatMessage = {
  id: "greeting",
  role: "assistant",
  content: "您好，我是政策分析助理，請問有什麼可以協助？",
};

// 問題範例，點擊後填入輸入框；使用者送出第一則訊息後不再顯示。
const EXAMPLE_PROMPTS = [
  "新北市青年薪資成長率偏低，可以怎麼提升？",
  "哪個行政區的青年人口流失最嚴重？",
  "三重區青年就業率偏低，有什麼政策建議？",
];

function createMessageId(): string {
  return typeof crypto !== "undefined" && "randomUUID" in crypto
    ? crypto.randomUUID()
    : Math.random().toString(36).slice(2);
}

function MessageBubble({ message }: { message: ChatMessage }) {
  const isUser = message.role === "user";

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.25 }}
      className={cn("flex gap-3", isUser && "justify-end")}
    >
      {!isUser ? (
        <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-primary text-primary-foreground">
          <Bot className="h-4 w-4" aria-hidden="true" />
        </span>
      ) : null}
      <p
        className={cn(
          "max-w-[80%] rounded-2xl px-4 py-2.5 text-sm leading-relaxed",
          isUser
            ? "rounded-br-sm bg-primary font-medium text-primary-foreground"
            : "rounded-tl-sm border border-slate-200 bg-surface text-slate-700 shadow-sm",
        )}
      >
        {message.content}
      </p>
    </motion.div>
  );
}

function TypingDots() {
  return (
    <div className="flex items-center gap-1">
      {[0, 1, 2].map((dot) => (
        <motion.span
          key={dot}
          className="h-1.5 w-1.5 rounded-full bg-accent-slate"
          animate={{ y: [0, -4, 0] }}
          transition={{
            duration: 0.8,
            repeat: Infinity,
            delay: dot * 0.15,
            ease: "easeInOut",
          }}
        />
      ))}
    </div>
  );
}

function TypingRow() {
  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      className="flex gap-3"
    >
      <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-primary text-primary-foreground">
        <Bot className="h-4 w-4" aria-hidden="true" />
      </span>
      <div className="flex items-center rounded-2xl rounded-tl-sm border border-slate-200 bg-surface px-4 py-3 shadow-sm">
        <TypingDots />
      </div>
    </motion.div>
  );
}

function TrustedSourceToggle({
  enabled,
  onToggle,
}: {
  enabled: boolean;
  onToggle: () => void;
}) {
  return (
    <label className="flex items-center gap-2 text-xs font-semibold text-slate-500">
      <span>可信任來源</span>
      <button
        type="button"
        role="switch"
        aria-checked={enabled}
        aria-label="僅引用可信任來源"
        onClick={onToggle}
        className={cn(
          "relative h-5 w-9 shrink-0 rounded-full transition-colors",
          enabled ? "bg-primary" : "bg-slate-200",
        )}
      >
        <span
          className={cn(
            "absolute left-0.5 top-0.5 h-4 w-4 rounded-full bg-white shadow transition-transform",
            enabled ? "translate-x-4" : "translate-x-0",
          )}
        />
      </button>
    </label>
  );
}

function ExamplePrompts({
  onSelect,
}: {
  onSelect: (prompt: string) => void;
}) {
  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      transition={{ duration: 0.2 }}
      className="flex flex-1 flex-col items-center justify-center gap-3 px-4 text-center"
    >
      <p className="flex items-center gap-1.5 text-xs font-semibold text-accent-slate">
        <Sparkles className="h-3.5 w-3.5" aria-hidden="true" />
        試著問問看
      </p>
      <div className="flex flex-col gap-2">
        {EXAMPLE_PROMPTS.map((prompt) => (
          <button
            key={prompt}
            type="button"
            onClick={() => onSelect(prompt)}
            className="rounded-xl border border-slate-200 bg-surface px-4 py-2 text-sm text-slate-600 shadow-sm transition-colors hover:border-primary/40 hover:text-primary"
          >
            {prompt}
          </button>
        ))}
      </div>
    </motion.div>
  );
}

export default function PolicyDecisionAssistant() {
  const [messages, setMessages] = useState<ChatMessage[]>([GREETING]);
  const [input, setInput] = useState("");
  const [isTyping, setIsTyping] = useState(false);
  const [trustedSourcesOnly, setTrustedSourcesOnly] = useState(false);
  const scrollAreaRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const timeoutRef = useRef<number | null>(null);

  const hasUserMessage = messages.some((message) => message.role === "user");
  const showExamples = !hasUserMessage && input.trim().length === 0;

  useEffect(() => {
    // 只捲動聊天內部區域，避免 scrollIntoView 連帶捲動整個頁面。
    const scrollArea = scrollAreaRef.current;
    if (!scrollArea) return;
    scrollArea.scrollTo({ top: scrollArea.scrollHeight, behavior: "smooth" });
  }, [messages, isTyping]);

  useEffect(() => {
    return () => {
      if (timeoutRef.current !== null) {
        window.clearTimeout(timeoutRef.current);
      }
    };
  }, []);

  function handleExampleClick(prompt: string) {
    setInput(prompt);
    inputRef.current?.focus({ preventScroll: true });
  }

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const trimmed = input.trim();
    if (!trimmed || isTyping) return;

    setMessages((prev) => [
      ...prev,
      { id: createMessageId(), role: "user", content: trimmed },
    ]);
    setInput("");
    setIsTyping(true);

    timeoutRef.current = window.setTimeout(() => {
      setMessages((prev) => [
        ...prev,
        { id: createMessageId(), role: "assistant", content: FIXED_REPLY },
      ]);
      setIsTyping(false);
    }, REPLY_DELAY_MS);
  }

  return (
    <Card className="overflow-hidden p-0">
      <div className="flex items-center justify-between gap-3 border-b border-slate-100 px-5 py-4">
        <div className="flex items-center gap-2.5">
          <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-primary text-primary-foreground">
            <Bot className="h-4 w-4" aria-hidden="true" />
          </span>
          <div>
            <p className="text-sm font-bold text-slate-900">政策分析助理</p>
            <p className="text-xs text-slate-400">由大語言模型驅動</p>
          </div>
        </div>
        <div className="flex items-center gap-4">
          <TrustedSourceToggle
            enabled={trustedSourcesOnly}
            onToggle={() => setTrustedSourcesOnly((prev) => !prev)}
          />
          <span className="flex items-center gap-1.5 text-xs font-semibold text-accent-teal">
            <span className="h-2 w-2 rounded-full bg-accent-teal" aria-hidden="true" />
            在線
          </span>
        </div>
      </div>

      <div className="flex flex-col gap-4 p-5">
        <div
          ref={scrollAreaRef}
          className="flex h-[420px] flex-col gap-4 overflow-y-auto rounded-2xl bg-background p-4"
        >
          {messages.map((message) => (
            <MessageBubble key={message.id} message={message} />
          ))}
          {isTyping ? <TypingRow /> : null}
          <AnimatePresence>
            {showExamples ? (
              <ExamplePrompts onSelect={handleExampleClick} />
            ) : null}
          </AnimatePresence>
        </div>

        {trustedSourcesOnly ? (
          <p className="flex items-center gap-1.5 text-[11px] font-medium text-accent-teal">
            <ShieldCheck className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />
            已啟用：僅引用政府公開資料與可信任來源
          </p>
        ) : null}

        <form
          onSubmit={handleSubmit}
          className="flex items-center gap-2 rounded-full border border-slate-200 bg-surface px-2 py-1.5 shadow-sm focus-within:ring-2 focus-within:ring-primary/40"
        >
          <input
            ref={inputRef}
            type="text"
            value={input}
            onChange={(event) => setInput(event.target.value)}
            disabled={isTyping}
            placeholder="輸入政策問題，按 Enter 送出"
            className="min-w-0 flex-1 bg-transparent px-2 text-sm text-slate-700 placeholder:text-slate-400 focus:outline-none disabled:cursor-not-allowed"
          />
          <Button
            type="submit"
            size="sm"
            disabled={isTyping || input.trim().length === 0}
            aria-label="送出"
            className="h-9 w-9 shrink-0 rounded-full p-0"
          >
            <SendHorizontal className="h-4 w-4" aria-hidden="true" />
          </Button>
        </form>
      </div>
    </Card>
  );
}
