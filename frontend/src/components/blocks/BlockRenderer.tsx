import { motion } from "framer-motion";
import type { Block } from "@/types";
import MarkdownBlock from "./MarkdownBlock";
import DataTableBlock from "./DataTableBlock";
import InsightCardsBlock from "./InsightCardsBlock";
import LeafletMapBlock from "./LeafletMapBlock";
import FallbackBlock from "./FallbackBlock";

export default function BlockRenderer({ blocks }: { blocks: Block[] | null | undefined }) {
  if (!blocks?.length) return null;

  return (
    <div className="space-y-4">
      {blocks.map((b, i) => (
        <motion.div
          key={i}
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: i * 0.06, duration: 0.35 }}
        >
          {renderOne(b)}
        </motion.div>
      ))}
    </div>
  );
}

function renderOne(b: Block) {
  switch (b.template_id) {
    case "markdown":      return <MarkdownBlock      data={(b as any).data} />;
    case "data-table":    return <DataTableBlock     data={(b as any).data} />;
    case "insight-cards": return <InsightCardsBlock  data={(b as any).data} />;
    case "leaflet-map":   return <LeafletMapBlock    data={(b as any).data} />;
    default:              return <FallbackBlock      template_id={b.template_id} data={b.data} />;
  }
}
