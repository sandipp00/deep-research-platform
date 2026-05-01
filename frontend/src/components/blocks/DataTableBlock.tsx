import { useMemo, useState } from "react";
import { ArrowDown, ArrowUp, ArrowUpDown } from "lucide-react";
import type { DataTableData } from "@/types";

export default function DataTableBlock({ data }: { data: DataTableData }) {
  const [sortKey, setSortKey] = useState<string | null>(null);
  const [dir, setDir] = useState<"asc" | "desc">("asc");

  const columns = data.columns ?? [];
  const rows = data.rows ?? [];

  const sorted = useMemo(() => {
    if (!sortKey) return rows;
    const copy = [...rows];
    copy.sort((a, b) => {
      const av = String(a[sortKey] ?? "").toLowerCase();
      const bv = String(b[sortKey] ?? "").toLowerCase();
      const an = parseFloat(av), bn = parseFloat(bv);
      const both = !isNaN(an) && !isNaN(bn);
      const cmp = both ? an - bn : av.localeCompare(bv);
      return dir === "asc" ? cmp : -cmp;
    });
    return copy;
  }, [rows, sortKey, dir]);

  function toggleSort(col: string) {
    if (sortKey === col) setDir(dir === "asc" ? "desc" : "asc");
    else { setSortKey(col); setDir("asc"); }
  }

  function renderCell(v: unknown) {
    if (v == null) return <span className="text-zinc-500">—</span>;
    if (typeof v === "string" && /^https?:\/\//.test(v)) {
      return (
        <a href={v} target="_blank" rel="noreferrer"
           className="text-accent-cyan hover:underline underline-offset-4 truncate block max-w-[28ch]">
          {v.replace(/^https?:\/\//, "")}
        </a>
      );
    }
    return String(v);
  }

  return (
    <div className="glass rounded-2xl overflow-hidden">
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-white/[0.06]">
              {columns.map((c) => (
                <th key={c}
                    className="text-left px-4 py-3 font-medium text-zinc-300 cursor-pointer select-none hover:text-white"
                    onClick={() => toggleSort(c)}>
                  <span className="inline-flex items-center gap-1.5">
                    {c}
                    {sortKey === c
                      ? (dir === "asc" ? <ArrowUp size={12} /> : <ArrowDown size={12} />)
                      : <ArrowUpDown size={12} className="opacity-40" />}
                  </span>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {sorted.map((row, i) => (
              <tr key={i} className="border-b border-white/[0.04] last:border-0 hover:bg-white/[0.02]">
                {columns.map((c) => (
                  <td key={c} className="px-4 py-3 text-zinc-200 align-top">
                    {renderCell(row[c])}
                  </td>
                ))}
              </tr>
            ))}
            {sorted.length === 0 && (
              <tr><td colSpan={columns.length}
                       className="px-4 py-8 text-center text-zinc-500">No rows</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
