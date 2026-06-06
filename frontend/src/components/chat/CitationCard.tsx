import { FileText, ExternalLink } from "lucide-react";

interface Props {
  content: string;
  score: number;
  source?: string;
}

export function CitationCard({ content, score, source }: Props) {
  return (
    <div className="group p-3 rounded-xl bg-gradient-to-r from-amber-50 to-orange-50 border border-amber-100 hover:shadow-md transition-all">
      <div className="flex items-start gap-2 mb-1">
        <FileText size={14} className="text-amber-500 mt-0.5 shrink-0" />
        <div className="flex-1 min-w-0">
          <p className="text-xs text-gray-600 line-clamp-2">{content}</p>
        </div>
        <ExternalLink
          size={12}
          className="text-amber-400 opacity-0 group-hover:opacity-100 transition-opacity shrink-0"
        />
      </div>
      <div className="flex items-center gap-2">
        <div className="flex-1 h-1.5 bg-amber-200 rounded-full overflow-hidden">
          <div
            className="h-full bg-gradient-to-r from-amber-400 to-orange-400 rounded-full transition-all"
            style={{ width: `${Math.min(score * 100, 100)}%` }}
          />
        </div>
        <span className="text-[10px] text-amber-600 font-medium">
          {(score * 100).toFixed(0)}%
        </span>
      </div>
      {source && (
        <p className="text-[10px] text-amber-500 mt-1 truncate">{source}</p>
      )}
    </div>
  );
}
