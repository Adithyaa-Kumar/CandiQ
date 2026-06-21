import { useRef, useState, type ChangeEvent, type DragEvent } from "react"

type InputMode = "text" | "file"

interface UploadZoneProps {
  label: string
  sublabel?: string
  accept: string
  textPlaceholder: string
  onFile: (f: File) => void
  onText: (t: string) => void
  uploadProgress?: number | null  // 0-100, null = not uploading
}

export function UploadZone({
  label, sublabel, accept, textPlaceholder, onFile, onText, uploadProgress
}: UploadZoneProps) {
  const [mode, setMode] = useState<InputMode>("text")
  const [file, setFile] = useState<File | null>(null)
  const [text, setText] = useState("")
  const [dragging, setDragging] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)

  const handleFile = (f: File) => {
    setFile(f)
    setMode("file")
    onFile(f)
  }

  const handleDrop = (e: DragEvent) => {
    e.preventDefault()
    setDragging(false)
    const f = e.dataTransfer.files[0]
    if (f) handleFile(f)
  }

  const handleText = (t: string) => {
    setText(t)
    onText(t)
    if (t) { setFile(null); setMode("text") }
  }

  const clearFile = () => {
    setFile(null)
    onFile(null as unknown as File)
    if (inputRef.current) inputRef.current.value = ""
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-3">
        <div>
          <span className="text-sm font-medium text-text-primary">{label}</span>
          {sublabel && <span className="text-xs text-text-tertiary ml-2">{sublabel}</span>}
        </div>
        <div className="flex gap-1 bg-surface rounded-lg p-0.5">
          {(["text", "file"] as InputMode[]).map((m) => (
            <button
              key={m}
              type="button"
              onClick={() => setMode(m)}
              className={`text-xs px-3 py-1.5 rounded-md transition-all font-medium ${
                mode === m
                  ? "bg-bg text-text-primary shadow-card"
                  : "text-text-tertiary hover:text-text-secondary"
              }`}
            >
              {m === "text" ? "Paste text" : "Upload file"}
            </button>
          ))}
        </div>
      </div>

      {mode === "text" ? (
        <textarea
          value={text}
          onChange={(e) => handleText(e.target.value)}
          placeholder={textPlaceholder}
          rows={7}
          className="w-full border border-border rounded-xl px-4 py-3 text-sm text-text-primary
                     placeholder-text-tertiary outline-none focus:border-accent focus:ring-2
                     focus:ring-accent/10 transition-all resize-none font-mono bg-bg leading-relaxed"
        />
      ) : (
        <div>
          <div
            onDragOver={(e) => { e.preventDefault(); setDragging(true) }}
            onDragLeave={() => setDragging(false)}
            onDrop={handleDrop}
            onClick={() => !file && inputRef.current?.click()}
            className={`flex flex-col items-center justify-center h-36 border-2 rounded-xl
                        cursor-pointer transition-all ${
              dragging
                ? "border-accent bg-accent-light"
                : file
                ? "border-border bg-surface cursor-default"
                : "border-dashed border-border-2 hover:border-accent hover:bg-accent-light/50 bg-surface"
            }`}
          >
            <input
              ref={inputRef}
              type="file"
              accept={accept}
              className="hidden"
              onChange={(e: ChangeEvent<HTMLInputElement>) => {
                const f = e.target.files?.[0]
                if (f) handleFile(f)
              }}
            />
            {file ? (
              <div className="text-center">
                <div className="w-10 h-10 bg-success-light rounded-xl flex items-center justify-center mx-auto mb-2">
                  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#059669" strokeWidth="2">
                    <polyline points="20 6 9 17 4 12"/>
                  </svg>
                </div>
                <div className="text-sm font-medium text-text-primary">{file.name}</div>
                <div className="text-xs text-text-tertiary mt-0.5">{(file.size / 1024).toFixed(1)} KB</div>
                <button
                  onClick={(e) => { e.stopPropagation(); clearFile() }}
                  className="text-xs text-text-tertiary hover:text-error mt-2 transition-colors"
                >
                  Remove
                </button>
              </div>
            ) : (
              <div className="text-center">
                <div className="w-10 h-10 bg-surface-2 rounded-xl flex items-center justify-center mx-auto mb-2">
                  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#94a3b8" strokeWidth="2">
                    <path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4"/>
                    <polyline points="17 8 12 3 7 8"/>
                    <line x1="12" y1="3" x2="12" y2="15"/>
                  </svg>
                </div>
                <div className="text-sm text-text-secondary font-medium">Drop file or click to browse</div>
                <div className="text-xs text-text-tertiary mt-1">{accept.split(",").join(" · ")}</div>
              </div>
            )}
          </div>

          {/* Upload progress bar */}
          {uploadProgress !== null && uploadProgress !== undefined && uploadProgress >= 0 && (
            <div className="mt-3">
              <div className="flex justify-between text-xs text-text-tertiary mb-1">
                <span>Uploading…</span>
                <span>{uploadProgress}%</span>
              </div>
              <div className="h-1.5 bg-surface-2 rounded-full overflow-hidden">
                <div
                  className="h-full bg-accent rounded-full transition-all duration-300"
                  style={{ width: `${uploadProgress}%` }}
                />
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  )
}