"use client";

import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

type MarkdownRendererProps = {
  content: string;
};

export function MarkdownRenderer({ content }: MarkdownRendererProps) {
  return (
    <div className="text-sm leading-relaxed text-slate-700 selection:bg-violet-100 selection:text-violet-900">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          h1: ({ node, ...props }) => (
            <h1 className="mt-8 mb-4 text-2xl font-bold tracking-tight text-slate-900 first:mt-0" {...props} />
          ),
          h2: ({ node, ...props }) => (
            <h2 className="mt-7 mb-3 border-b border-slate-200 pb-2 text-xl font-bold tracking-tight text-slate-900 first:mt-0" {...props} />
          ),
          h3: ({ node, ...props }) => (
            <h3 className="mt-6 mb-2 text-lg font-semibold tracking-tight text-slate-900 first:mt-0" {...props} />
          ),
          h4: ({ node, ...props }) => (
            <h4 className="mt-5 mb-2 text-base font-semibold tracking-tight text-slate-900 first:mt-0" {...props} />
          ),
          p: ({ node, ...props }) => <p className="mb-4 leading-relaxed last:mb-0" {...props} />,
          ul: ({ node, ...props }) => (
            <ul className="mb-4 ml-5 list-disc space-y-1.5 marker:text-slate-400 last:mb-0" {...props} />
          ),
          ol: ({ node, ...props }) => (
            <ol className="mb-4 ml-5 list-decimal space-y-1.5 marker:text-slate-400 marker:font-semibold last:mb-0" {...props} />
          ),
          li: ({ node, ...props }) => <li className="pl-1 leading-relaxed [&>p]:mb-0" {...props} />,
          strong: ({ node, ...props }) => <strong className="font-semibold text-slate-950" {...props} />,
          em: ({ node, ...props }) => <em className="italic text-slate-600" {...props} />,
          a: ({ node, ...props }) => (
            <a 
              className="font-medium text-violet-600 underline decoration-violet-300 underline-offset-2 transition-colors hover:text-violet-700 hover:decoration-violet-500" 
              target="_blank" 
              rel="noopener noreferrer" 
              {...props} 
            />
          ),
          blockquote: ({ node, ...props }) => (
            <blockquote 
              className="my-4 border-l-4 border-violet-300 bg-violet-50/50 py-2 pl-4 pr-2 rounded-r-lg text-slate-600 italic first:my-0 last:my-0" 
              {...props} 
            />
          ),
          table: ({ node, ...props }) => (
            <div className="my-5 w-full overflow-x-auto rounded-xl border border-slate-200 shadow-sm last:my-0">
              <table className="w-full border-collapse text-left text-sm" {...props} />
            </div>
          ),
          thead: ({ node, ...props }) => <thead className="bg-slate-50 text-slate-900" {...props} />,
          th: ({ node, ...props }) => (
            <th className="border-b border-slate-200 px-4 py-3 font-semibold tracking-tight" {...props} />
          ),
          tr: ({ node, ...props }) => (
            <tr className="border-b border-slate-100 transition-colors last:border-0 hover:bg-slate-50/70" {...props} />
          ),
          td: ({ node, ...props }) => <td className="px-4 py-3 align-top text-slate-600" {...props} />,
          code: ({ className, children, node, ...props }: any) => {
            const match = /language-(\w+)/.exec(className || "");
            const isInline = !match && !String(children).includes("\n");
            
            if (isInline) {
              return (
                <code className="rounded-md bg-slate-100 px-1.5 py-0.5 text-[0.85em] font-mono text-violet-600" {...props}>
                  {children}
                </code>
              );
            }

            return (
              <div className="my-5 overflow-hidden rounded-xl border border-slate-800 bg-slate-900 shadow-lg last:my-0">
                {/* Mac Window Header */}
                <div className="flex items-center justify-between border-b border-slate-700/50 bg-slate-800/50 px-4 py-2">
                  <div className="flex items-center gap-1.5">
                    <span className="h-3 w-3 rounded-full bg-red-500/80"></span>
                    <span className="h-3 w-3 rounded-full bg-yellow-500/80"></span>
                    <span className="h-3 w-3 rounded-full bg-green-500/80"></span>
                  </div>
                  {match && (
                    <span className="text-[10px] font-mono font-medium uppercase tracking-wider text-slate-400">
                      {match[1]}
                    </span>
                  )}
                </div>
                <pre className="overflow-x-auto p-4 text-xs leading-relaxed text-slate-200">
                  <code className={className} {...props}>
                    {children}
                  </code>
                </pre>
              </div>
            );
          },
          hr: ({ node, ...props }) => (
            <hr className="my-8 h-px border-0 bg-gradient-to-r from-transparent via-slate-300 to-transparent" {...props} />
          ),
        }}
      >
        {content}
      </ReactMarkdown>
    </div>
  );
}