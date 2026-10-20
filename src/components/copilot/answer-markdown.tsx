'use client';

import { memo } from 'react';
import ReactMarkdown, { type Components, type Options } from 'react-markdown';
import rehypeKatex from 'rehype-katex';
import remarkGfm from 'remark-gfm';
import remarkMath from 'remark-math';
import 'katex/dist/katex.min.css';

// Answers quote money with "$", so single-dollar math is off: only $$…$$ renders as a formula.
const remarkPlugins: Options['remarkPlugins'] = [remarkGfm, [remarkMath, { singleDollarTextMath: false }]];
// strict: false lets labels like \text{现金余额} render in every UI language instead of warning.
const rehypePlugins: Options['rehypePlugins'] = [[rehypeKatex, { strict: false, output: 'html' }]];

const components: Components = {
  p: ({ children }) => <p className="leading-relaxed [&:not(:first-child)]:mt-2.5">{children}</p>,
  strong: ({ children }) => <strong className="font-medium text-foreground">{children}</strong>,
  ul: ({ children }) => <ul className="mt-2 space-y-1 pl-4 marker:text-muted-foreground [list-style:disc]">{children}</ul>,
  ol: ({ children }) => <ol className="mt-2 space-y-1 pl-4 marker:text-muted-foreground [list-style:decimal]">{children}</ol>,
  li: ({ children }) => <li className="pl-0.5 leading-relaxed">{children}</li>,
  code: ({ children }) => <code className="rounded bg-muted px-1.5 py-0.5 font-mono text-[0.85em]">{children}</code>,
  table: ({ children }) => (
    <div className="mt-2.5 overflow-x-auto rounded-lg border border-border/60">
      <table className="figures w-full border-collapse text-xs sm:text-sm">{children}</table>
    </div>
  ),
  // `style` carries the column alignment from the markdown (|---:| right-aligns number columns).
  th: ({ children, style }) => (
    <th style={style} className="whitespace-nowrap border-b bg-muted/40 px-3 py-1.5 text-left text-xs font-medium text-muted-foreground">
      {children}
    </th>
  ),
  td: ({ children, style }) => (
    <td style={style} className="border-b px-3 py-1.5 align-top text-xs sm:text-sm">
      {children}
    </td>
  ),
  blockquote: ({ children }) => <blockquote className="mt-2.5 border-l-2 border-primary/50 pl-3 text-xs sm:text-sm text-ink-2">{children}</blockquote>,
  a: ({ children, href }) => (
    <a href={href} className="font-medium text-primary underline underline-offset-2">
      {children}
    </a>
  ),
};

/** Renders a model answer: bold, lists, tables and $$ display formulas. Raw HTML in the answer is never rendered. */
// Memoized: the chat re-renders on every keystroke, and re-parsing each answer's markdown and KaTeX made typing lag.
export const AnswerMarkdown = memo(function AnswerMarkdown({ text }: { text: string }) {
  return (
    <div className="answer-md text-sm sm:text-[14.5px] leading-relaxed text-foreground [&_.katex-display]:my-2.5 [&_.katex-display]:overflow-x-auto [&_.katex-display]:rounded-lg [&_.katex-display]:bg-muted/50 [&_.katex-display]:px-3.5 [&_.katex-display]:py-2">
      <ReactMarkdown remarkPlugins={remarkPlugins} rehypePlugins={rehypePlugins} components={components}>
        {text}
      </ReactMarkdown>
    </div>
  );
});
