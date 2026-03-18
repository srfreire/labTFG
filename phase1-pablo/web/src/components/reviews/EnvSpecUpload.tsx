import { useState, useRef, useCallback } from 'react';
import CodeBlock from '../shared/CodeBlock';

interface EnvSpecUploadProps {
  onSubmit: (response: { env_spec: Record<string, unknown> }) => void;
  defaultJson?: string;
}

type Mode = 'upload' | 'paste';

export default function EnvSpecUpload({ onSubmit, defaultJson }: EnvSpecUploadProps) {
  const [mode, setMode] = useState<Mode>(defaultJson ? 'paste' : 'upload');
  const [rawJson, setRawJson] = useState(defaultJson ?? '');
  const [parsed, setParsed] = useState<Record<string, unknown> | null>(() => {
    if (!defaultJson) return null;
    try {
      const obj = JSON.parse(defaultJson);
      return typeof obj === 'object' && obj !== null && !Array.isArray(obj) ? obj : null;
    } catch { return null; }
  });
  const [error, setError] = useState<string | null>(null);
  const [dragging, setDragging] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const tryParse = useCallback((text: string) => {
    setRawJson(text);
    try {
      const obj = JSON.parse(text);
      if (typeof obj !== 'object' || obj === null || Array.isArray(obj)) {
        setParsed(null);
        setError('JSON must be an object');
        return;
      }
      setParsed(obj);
      setError(null);
    } catch (e) {
      setParsed(null);
      setError((e as Error).message);
    }
  }, []);

  const handleFile = useCallback(
    (file: File) => {
      const reader = new FileReader();
      reader.onload = (e) => {
        const text = e.target?.result as string;
        tryParse(text);
      };
      reader.readAsText(file);
    },
    [tryParse],
  );

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      setDragging(false);
      const file = e.dataTransfer.files[0];
      if (file) handleFile(file);
    },
    [handleFile],
  );

  const isValid = parsed !== null;

  return (
    <div className="flex flex-col h-full" style={{ fontFamily: "'IBM Plex Mono', monospace" }}>
      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        <h2
          className="text-[11px] uppercase tracking-[2px] mb-4"
          style={{ color: 'rgba(255,255,255,0.5)' }}
        >
          Environment Spec
        </h2>

        {/* Mode toggle */}
        <div className="flex gap-2">
          {(['upload', 'paste'] as Mode[]).map((m) => (
            <button
              key={m}
              className="text-[10px] uppercase tracking-[1px] text-white"
              style={{
                border: '1px solid rgba(255,255,255,0.3)',
                background: mode === m ? 'rgba(255,255,255,0.08)' : 'transparent',
                padding: '6px 16px',
              }}
              onClick={() => setMode(m)}
            >
              {m === 'upload' ? 'Upload file' : 'Paste JSON'}
            </button>
          ))}
        </div>

        {/* Upload mode */}
        {mode === 'upload' && (
          <div
            className="flex items-center justify-center p-8 cursor-pointer min-h-[160px] border-box"
            style={{
              border: `2px dashed ${dragging ? 'rgba(255,255,255,0.5)' : 'rgba(255,255,255,0.2)'}`,
              background: dragging ? 'rgba(255,255,255,0.03)' : 'transparent',
              transition: 'border-color 0.15s, background 0.15s',
            }}
            onDragOver={(e) => {
              e.preventDefault();
              setDragging(true);
            }}
            onDragLeave={() => setDragging(false)}
            onDrop={handleDrop}
            onClick={() => fileInputRef.current?.click()}
          >
            <span
              className="text-[11px]"
              style={{ color: 'rgba(255,255,255,0.4)' }}
            >
              Drop env_spec.json here
            </span>
            <input
              ref={fileInputRef}
              type="file"
              accept=".json"
              className="hidden"
              onChange={(e) => {
                const file = e.target.files?.[0];
                if (file) handleFile(file);
              }}
            />
          </div>
        )}

        {/* Paste mode */}
        {mode === 'paste' && (
          <textarea
            className="w-full text-[11px] text-white"
            style={{
              background: '#090909',
              border: '1px solid rgba(255,255,255,0.15)',
              fontFamily: "'IBM Plex Mono', monospace",
              padding: '12px',
              resize: 'vertical',
              minHeight: '160px',
              outline: 'none',
            }}
            placeholder="Paste JSON here..."
            value={rawJson}
            onChange={(e) => tryParse(e.target.value)}
          />
        )}

        {/* Error */}
        {error && (
          <div className="text-[10px]" style={{ color: '#ff4444' }}>
            {error}
          </div>
        )}

        {/* JSON preview */}
        {isValid && (
          <div>
            <span
              className="text-[10px] uppercase tracking-[1px]"
              style={{ color: 'rgba(255,255,255,0.3)' }}
            >
              Preview
            </span>
            <CodeBlock code={JSON.stringify(parsed, null, 2)} language="json" />
          </div>
        )}
      </div>

      {/* Footer */}
      <div className="p-4" style={{ borderTop: '1px solid rgba(255,255,255,0.1)' }}>
        <button
          className="text-[11px] uppercase tracking-[1px] font-medium text-white"
          style={{
            border: '1px solid rgba(255,255,255,0.3)',
            background: 'transparent',
            padding: '8px 24px',
            opacity: isValid ? 1 : 0.3,
            cursor: isValid ? 'pointer' : 'not-allowed',
          }}
          disabled={!isValid}
          onMouseEnter={(e) => {
            if (isValid)
              (e.currentTarget as HTMLButtonElement).style.background =
                'rgba(255,255,255,0.05)';
          }}
          onMouseLeave={(e) => {
            (e.currentTarget as HTMLButtonElement).style.background = 'transparent';
          }}
          onClick={() => onSubmit({ env_spec: parsed! })}
        >
          Continuar
        </button>
      </div>
    </div>
  );
}
