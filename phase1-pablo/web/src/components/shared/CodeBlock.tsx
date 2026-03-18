import SyntaxHighlighter from 'react-syntax-highlighter';
import { vs2015 } from 'react-syntax-highlighter/dist/esm/styles/hljs';

interface CodeBlockProps {
  code: string;
  language?: string;
}

export default function CodeBlock({ code, language }: CodeBlockProps) {
  return (
    <div className="relative my-2">
      {language && (
        <span className="absolute top-1.5 right-2 text-[11px] uppercase tracking-[1px] text-text-faint">
          {language}
        </span>
      )}
      <SyntaxHighlighter
        language={language}
        style={vs2015}
        customStyle={{
          background: 'var(--color-surface)',
          border: '1px solid var(--color-border)',
          borderRadius: 8,
          padding: '14px 16px',
          margin: 0,
          fontSize: '13px',
          fontFamily: 'inherit',
        }}
      >
        {code}
      </SyntaxHighlighter>
    </div>
  );
}
