import { useRef, type ReactNode } from "react";

/** A button that opens the file dialog for a score and hands the chosen file over. */
export function FilePicker({
  onFile,
  disabled,
  className,
  children,
}: {
  onFile: (file: File) => void;
  disabled?: boolean;
  className?: string;
  children: ReactNode;
}) {
  const input = useRef<HTMLInputElement>(null);
  return (
    <>
      <input
        ref={input}
        type="file"
        accept=".musicxml,.xml,.mxl"
        hidden
        onChange={(e) => {
          const file = e.target.files?.[0];
          e.target.value = ""; // so choosing the same file again still fires
          if (file) onFile(file);
        }}
      />
      <button type="button" disabled={disabled} className={className} onClick={() => input.current?.click()}>
        {children}
      </button>
    </>
  );
}

export const buttonClass =
  "rounded-md border border-zinc-700 px-3 py-2 text-sm hover:bg-zinc-800 disabled:cursor-not-allowed disabled:opacity-50";
