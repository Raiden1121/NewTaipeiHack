import { Building2, Globe, SendHorizontal } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { SEED_CHAT, type ChatMessage } from "../placeholderData";

function UserMessage({ message }: { message: ChatMessage }) {
  return (
    <div className="flex justify-end">
      <p className="max-w-[80%] rounded-2xl rounded-br-sm bg-primary px-4 py-2 text-sm font-medium text-primary-foreground">
        {message.content}
      </p>
    </div>
  );
}

function AssistantMessage({ message }: { message: ChatMessage }) {
  return (
    <div className="flex gap-3">
      <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-primary text-primary-foreground">
        <Building2 className="h-4 w-4" aria-hidden="true" />
      </span>
      <div className="flex min-w-0 flex-1 flex-col gap-3">
        <div className="rounded-2xl rounded-tl-sm bg-slate-50 p-4 text-sm leading-relaxed text-slate-700">
          <p>{message.content}</p>
          {message.suggestions ? (
            <div className="mt-3 flex flex-col gap-3">
              {message.suggestions.map((suggestion, index) => (
                <div
                  key={suggestion.title}
                  className="rounded-xl border border-slate-200 bg-surface p-3"
                >
                  <p className="text-sm font-bold text-slate-900">
                    {index + 1}. {suggestion.title}
                  </p>
                  <p className="mt-1 text-xs leading-relaxed text-slate-500">
                    {suggestion.body}
                  </p>
                </div>
              ))}
            </div>
          ) : null}
        </div>
        {message.sourceNote ? (
          <p className="flex items-center gap-1.5 text-[11px] text-accent-slate">
            <Globe className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />
            {message.sourceNote}
          </p>
        ) : null}
      </div>
    </div>
  );
}

export default function PolicyDecisionAssistant() {
  return (
    <Card>
      <CardContent className="flex flex-col gap-4 p-5">
        <div className="flex max-h-[520px] flex-col gap-5 overflow-y-auto pr-1">
          {SEED_CHAT.map((message) =>
            message.role === "user" ? (
              <UserMessage key={message.id} message={message} />
            ) : (
              <AssistantMessage key={message.id} message={message} />
            ),
          )}
        </div>

        <div className="flex items-center gap-2 rounded-xl border border-slate-200 bg-slate-50 p-2">
          <input
            type="text"
            disabled
            placeholder="輸入政策問題（展示佔位，尚未串接 AI agent）"
            className="min-w-0 flex-1 bg-transparent px-2 text-sm text-slate-700 placeholder:text-slate-400 focus:outline-none disabled:cursor-not-allowed"
          />
          <Button size="sm" type="button" disabled aria-label="送出">
            <SendHorizontal className="h-4 w-4" aria-hidden="true" />
          </Button>
        </div>
        <p className="text-[11px] text-slate-400">
          此對話為展示佔位內容，實際 AI 政策分析尚未串接。
        </p>
      </CardContent>
    </Card>
  );
}
