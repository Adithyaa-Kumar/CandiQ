// components/InputPanel.tsx
import { useRef, useState, type ChangeEvent, type DragEvent } from "react"

type InputMode = "text" | "file"

interface UploadZoneProps {
  label: string
  accept: string
  textPlaceholder: string
  onFile: (f: File) => void
  onText: (t: string) => void
}

export function UploadZone({ label, accept, textPlaceholder, onFile, onText }: UploadZoneProps) {
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
    if (t) {
      setFile(null)
      setMode("text")
    }
  }

  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-center justify-between">
        <span className="text-xs text-[#4a8aa0] tracking-[0.15em] uppercase">{label}</span>
        <div className="flex gap-1">
          {(["text", "file"] as InputMode[]).map((m) => (
            <button
              key={m}
              type="button"
              onClick={() => setMode(m)}
              className={`text-xs px-3 py-1 transition-colors ${
                mode === m ? "text-accent border-b border-accent" : "text-[#3a5a6a] hover:text-accent"
              }`}
            >
              {m === "text" ? "Paste" : "Upload"}
            </button>
          ))}
        </div>
      </div>

      {mode === "text" ? (
        <textarea
          value={text}
          onChange={(e) => handleText(e.target.value)}
          placeholder={textPlaceholder}
          rows={8}
          className="w-full bg-bg border border-border focus:border-accent/50 rounded px-4 py-3
                     text-sm text-[#c0d0e0] placeholder-[#2a3a4a] outline-none resize-none
                     transition-colors font-mono"
        />
      ) : (
        <div
          onDragOver={(e) => {
            e.preventDefault()
            setDragging(true)
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={handleDrop}
          onClick={() => inputRef.current?.click()}
          className={`flex flex-col items-center justify-center h-40 border rounded cursor-pointer transition-all ${
            dragging
              ? "border-accent bg-accent/5"
              : file
              ? "border-accent/40 bg-accent/5"
              : "border-border border-dashed hover:border-[#2a4a5a] bg-bg"
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
            <>
              <div className="text-accent text-sm">{file.name}</div>
              <div className="text-[#3a5a6a] text-xs mt-1">{(file.size / 1024).toFixed(1)} KB</div>
            </>
          ) : (
            <>
              <div className="text-[#2a4a5a] text-2xl mb-2">↑</div>
              <div className="text-[#3a5a6a] text-xs">Drop file or click to browse</div>
              <div className="text-[#2a3a4a] text-xs mt-1">{accept.split(",").join(" · ")}</div>
            </>
          )}
        </div>
      )}
    </div>
  )
}