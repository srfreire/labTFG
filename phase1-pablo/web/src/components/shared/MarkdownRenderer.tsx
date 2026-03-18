import Markdown from 'react-markdown';
import remarkMath from 'remark-math';
import remarkGfm from 'remark-gfm';
import rehypeKatex from 'rehype-katex';
import 'katex/dist/katex.min.css';
import CodeBlock from './CodeBlock';
import type { Components } from 'react-markdown';

interface MarkdownRendererProps {
  content: string;
  className?: string;
}

const components: Components = {
  code({ className, children, ...rest }) {
    const match = /language-(\w+)/.exec(className || '');
    const text = String(children).replace(/\n$/, '');

    if (match) {
      return <CodeBlock code={text} language={match[1]} />;
    }

    return (
      <code
        className={`${className ?? ''} bg-surface-hover border border-border px-1 py-px text-[13px] rounded`}
        {...rest}
      >
        {children}
      </code>
    );
  },

  pre({ children }) {
    return <>{children}</>;
  },
};

export default function MarkdownRenderer({ content, className }: MarkdownRendererProps) {
  const classes = ['markdown-body', className].filter(Boolean).join(' ');

  return (
    <div className={classes}>
      <Markdown
        remarkPlugins={[remarkMath, remarkGfm]}
        rehypePlugins={[rehypeKatex]}
        components={components}
      >
        {content}
      </Markdown>
    </div>
  );
}
