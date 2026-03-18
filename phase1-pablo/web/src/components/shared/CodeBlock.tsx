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
        <span className="absolute top-1.5 right-2 text-[9px] uppercase tracking-[1px] text-text-faint">
          {language}
        </span>
      )}
      <SyntaxHighlighter
        language={language}
        style={vs2015}
        customStyle={{
          background: '#090909',
          border: '1px solid rgba(255,255,255,0.1)',
          borderRadius: 0,
          padding: '14px 16px',
          margin: 0,
          fontSize: '11px',
          fontFamily: 'inherit',
        }}
      >
        {code}
      </SyntaxHighlighter>
    </div>
  );
}
