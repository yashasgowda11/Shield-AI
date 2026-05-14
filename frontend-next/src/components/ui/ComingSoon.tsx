import { Construction } from "lucide-react";

interface Props {
  title: string;
  description: string;
  streamlitPath?: string; // e.g. "5_Risk_Dashboard"
}

export default function ComingSoon({ title, description, streamlitPath }: Props) {
  return (
    <div className="flex flex-col items-center justify-center flex-1 p-12 text-center">
      <div className="w-16 h-16 rounded-2xl flex items-center justify-center mb-6"
        style={{ background: "var(--bg-card)", border: "1px solid var(--border)" }}>
        <Construction size={28} style={{ color: "var(--accent)" }} />
      </div>

      <h2 className="text-xl font-semibold text-white mb-2">{title}</h2>
      <p className="text-sm max-w-sm mb-6" style={{ color: "var(--text-muted)" }}>
        {description}
      </p>

      {streamlitPath && (
        <a
          href={`http://localhost:8501/${streamlitPath}`}
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex items-center gap-2 text-sm px-4 py-2 rounded-lg border transition-colors hover:brightness-110"
          style={{ borderColor: "var(--accent)", color: "var(--accent)", background: "var(--accent)11" }}
        >
          Open in Streamlit (current version) →
        </a>
      )}
    </div>
  );
}
