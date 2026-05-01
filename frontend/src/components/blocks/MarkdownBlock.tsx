import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { MarkdownData } from "@/types";

export default function MarkdownBlock({ data }: { data: MarkdownData }) {
  return (
    <div className="markdown-body">
      <ReactMarkdown remarkPlugins={[remarkGfm]}>
        {data.content || ""}
      </ReactMarkdown>
    </div>
  );
}
