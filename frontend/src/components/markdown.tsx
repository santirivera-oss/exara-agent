"use client";

import ReactMarkdown, { Components } from "react-markdown";
import remarkGfm from "remark-gfm";
import { Prism as SyntaxHighlighter } from "react-syntax-highlighter";
import { vscDarkPlus } from "react-syntax-highlighter/dist/esm/styles/prism";
import { ReactNode } from "react";

interface Props {
  children: string;
}

/**
 * Markdown renderer tuned for agent output.
 *
 * - GFM tables, task lists, strikethrough
 * - Fenced code blocks with Prism syntax highlighting (vsc-dark-plus theme)
 * - Inline code, lists, headings, blockquotes styled for our dark UI
 */
export function Markdown({ children }: Props) {
  return (
    <div className="markdown text-sm leading-relaxed">
      <ReactMarkdown remarkPlugins={[remarkGfm]} components={components}>
        {children}
      </ReactMarkdown>
    </div>
  );
}

const components: Components = {
  code({ className, children, ...rest }) {
    const match = /language-(\w+)/.exec(className || "");
    const code = String(children).replace(/\n$/, "");
    const inline = !match && !code.includes("\n");

    if (inline) {
      return (
        <code className="rounded bg-slate-800 px-1.5 py-0.5 font-mono text-[0.85em] text-amber-300" {...rest}>
          {children}
        </code>
      );
    }

    // Fenced block. SyntaxHighlighter's typings expect any-ish nodes; cast for compatibility.
    return (
      <SyntaxHighlighter
        style={vscDarkPlus}
        language={match?.[1] ?? "text"}
        PreTag="div"
        customStyle={{
          margin: "0.5rem 0",
          padding: "0.75rem",
          borderRadius: "6px",
          fontSize: "0.78rem",
          background: "rgba(0,0,0,0.45)",
        }}
        codeTagProps={{ style: { fontFamily: "var(--font-geist-mono), monospace" } }}
      >
        {code}
      </SyntaxHighlighter>
    );
  },
  p({ children }: { children?: ReactNode }) {
    return <p className="my-2">{children}</p>;
  },
  ul({ children }: { children?: ReactNode }) {
    return <ul className="my-2 ml-5 list-disc space-y-1">{children}</ul>;
  },
  ol({ children }: { children?: ReactNode }) {
    return <ol className="my-2 ml-5 list-decimal space-y-1">{children}</ol>;
  },
  li({ children }: { children?: ReactNode }) {
    return <li className="leading-snug">{children}</li>;
  },
  h1({ children }: { children?: ReactNode }) {
    return <h1 className="mb-2 mt-4 text-lg font-semibold text-emerald-300">{children}</h1>;
  },
  h2({ children }: { children?: ReactNode }) {
    return <h2 className="mb-2 mt-3 text-base font-semibold text-emerald-300">{children}</h2>;
  },
  h3({ children }: { children?: ReactNode }) {
    return <h3 className="mb-1 mt-3 text-sm font-semibold text-emerald-300">{children}</h3>;
  },
  blockquote({ children }: { children?: ReactNode }) {
    return (
      <blockquote className="my-2 border-l-2 border-slate-600 pl-3 text-slate-400 italic">
        {children}
      </blockquote>
    );
  },
  a({ href, children }: { href?: string; children?: ReactNode }) {
    return (
      <a href={href} target="_blank" rel="noreferrer noopener" className="text-cyan-400 underline hover:text-cyan-300">
        {children}
      </a>
    );
  },
  table({ children }: { children?: ReactNode }) {
    return <table className="my-2 w-full border-collapse text-xs">{children}</table>;
  },
  th({ children }: { children?: ReactNode }) {
    return <th className="border border-slate-700 bg-slate-800 px-2 py-1 text-left font-semibold">{children}</th>;
  },
  td({ children }: { children?: ReactNode }) {
    return <td className="border border-slate-700 px-2 py-1">{children}</td>;
  },
};
