"use client"
import React, { useMemo } from 'react';

export interface DisplayMessage {
  role: 'user' | 'assistant';
  content: string;
}

function formatContent(content: string): React.ReactNode {
  if (!content) return null;

  // Split by markdown-style headers and paragraphs
  const lines = content.split('\n');
  const elements: React.ReactNode[] = [];

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];

    if (!line.trim()) {
      elements.push(<div key={i} className="h-2" />);
      continue;
    }

    // Headers
    if (line.startsWith('### ')) {
      elements.push(
        <h4 key={i} className="text-sm font-bold mt-3 mb-1 text-black">
          {line.replace('### ', '')}
        </h4>
      );
    } else if (line.startsWith('## ')) {
      elements.push(
        <h3 key={i} className="text-base font-bold mt-4 mb-2 text-black">
          {line.replace('## ', '')}
        </h3>
      );
    } else if (line.startsWith('# ')) {
      elements.push(
        <h2 key={i} className="text-lg font-bold mt-5 mb-2 text-black">
          {line.replace('# ', '')}
        </h2>
      );
    }
    // Bold
    else if (line.startsWith('**') && line.includes('**')) {
      const clean = line.replace(/\*\*/g, '');
      elements.push(
        <p key={i} className="text-sm font-bold text-black mt-1">
          {clean}
        </p>
      );
    }
    // List items
    else if (line.trim().startsWith('- ') || line.trim().startsWith('* ')) {
      const clean = line.trim().replace(/^[-*]\s+/, '');
      elements.push(
        <li key={i} className="text-sm text-[#3a3a3a] ml-4 list-disc leading-relaxed">
          {clean}
        </li>
      );
    }
    // Numbered list
    else if (/^\d+[\.\)]\s/.test(line.trim())) {
      const clean = line.trim().replace(/^\d+[\.\)]\s+/, '');
      elements.push(
        <li key={i} className="text-sm text-[#3a3a3a] ml-4 list-decimal leading-relaxed">
          {clean}
        </li>
      );
    }
    // Emoji or icon line
    else if (/^[⚠️✅❌🔥💡📌🏷️⭐]/.test(line.trim())) {
      elements.push(
        <p key={i} className="text-sm text-[#3a3a3a] leading-relaxed">
          {line}
        </p>
      );
    }
    // Regular paragraph
    else {
      elements.push(
        <p key={i} className="text-sm text-[#3a3a3a] leading-relaxed">
          {line}
        </p>
      );
    }
  }

  return <>{elements}</>;
}

export const MessageItem = React.memo(function MessageItem({ msg }: { msg: DisplayMessage }) {
  const formattedContent = useMemo(() => {
    if (!msg) return null;
    if (typeof msg.content === 'string') return formatContent(msg.content);
    return msg.content;
  }, [msg?.content]);

  if (!msg) return null;

  if (msg.role === 'user') {
    return (
      <div className="max-w-3xl mx-auto flex justify-end">
        <div className="max-w-[75%] bg-[#F9F8F6] border border-black/5 px-5 py-3.5">
          <p className="text-sm text-[#1d1d1f] leading-relaxed whitespace-pre-wrap">
            {msg.content}
          </p>
        </div>
      </div>
    );
  }

  // Assistant message
  return (
    <div className="max-w-3xl mx-auto flex gap-5">
      <div className="w-9 h-9 flex items-center justify-center shrink-0 border border-black/10 bg-[#F9F8F6] text-[#8C7A6B]">
        <span className="font-serif italic text-xs">E</span>
      </div>
      <div className="min-w-0 flex-1 pt-0.5">
        <div className="text-sm text-[#3a3a3a] leading-[1.8] font-light space-y-1">
          {formattedContent}
        </div>
      </div>
    </div>
  );
});
