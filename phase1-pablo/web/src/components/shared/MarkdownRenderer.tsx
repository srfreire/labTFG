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
        className={className}
        style={{
          background: 'rgba(255,255,255,0.05)',
          border: '1px solid rgba(255,255,255,0.1)',
          padding: '1px 4px',
          fontSize: '11px',
        }}
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
