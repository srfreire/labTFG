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
    <div className="flex flex-col h-full">
      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        <h2 className="text-[11px] uppercase tracking-[2px] mb-4 text-text-muted">
          Environment Spec
        </h2>

        {/* Mode toggle */}
        <div className="flex gap-2">
          {(['upload', 'paste'] as Mode[]).map((m) => (
            <button
              key={m}
              className="text-[10px] uppercase tracking-[1px] text-white border border-text-faint px-4 py-1.5"
              style={{
                background: mode === m ? 'rgba(255,255,255,0.08)' : 'transparent',
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
            <span className="text-[11px] text-text-dim">
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
            className="w-full text-[11px] text-white bg-surface border border-text-ghost p-3 resize-y min-h-[160px] outline-none font-mono"
            placeholder="Paste JSON here..."
            value={rawJson}
            onChange={(e) => tryParse(e.target.value)}
          />
        )}

        {/* Error */}
        {error && (
          <div className="text-[10px] text-accent-red">
            {error}
          </div>
        )}

        {/* JSON preview */}
        {isValid && (
          <div>
            <span className="text-[10px] uppercase tracking-[1px] text-text-faint">
              Preview
            </span>
            <CodeBlock code={JSON.stringify(parsed, null, 2)} language="json" />
          </div>
        )}
      </div>

      {/* Footer */}
      <div className="p-4 border-t border-border">
        <button
          className="text-[11px] uppercase tracking-[1px] font-medium text-white border border-text-faint px-6 py-2 hover:bg-surface-hover disabled:opacity-30 disabled:cursor-not-allowed"
          style={{ cursor: isValid ? 'pointer' : 'not-allowed' }}
          disabled={!isValid}
          onClick={() => onSubmit({ env_spec: parsed! })}
        >
          Continuar
        </button>
      </div>
    </div>
  );
}
