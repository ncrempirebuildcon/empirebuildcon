/**
 * FormattedText: shows WhatsApp-style text (`*bold*`, `_italic_`, `- ` bullets with two-space
 * nesting, blank-line paragraphs) as React elements. Used in the CMS previews now and on the
 * public site in Phase 5 (ARCHITECTURE.md §6 "Formatted text").
 *
 * SECURITY: the text is parsed by our own parser (format/formattedText.ts) into plain objects and
 * rendered as <p>, <ul>, <li>, <strong>, <em> and <br> only. Every piece of the text is a React
 * text child, so "<script>" or "<b>" shows as those characters. Never swap this for an HTML
 * renderer or `dangerouslySetInnerHTML` (SECURITY.md §5; the lint rule bans it).
 */
import type { ReactNode } from "react";
import { cx } from "../cx";
import {
  parseFormattedText,
  type BlockNode,
  type InlineNode,
  type ListItemNode,
} from "../format/formattedText";

export interface FormattedTextProps {
  /** The stored text. Empty or blank text renders `empty` (nothing by default). */
  text: string | null | undefined;
  /** Shown when there is no text, e.g. "Nothing to preview yet." */
  empty?: ReactNode;
  className?: string;
}

function renderInline(nodes: readonly InlineNode[]): ReactNode[] {
  return nodes.map((node, index) => {
    if (node.type === "text") return node.text;
    const children = renderInline(node.children);
    return node.type === "bold" ? (
      <strong key={index} className="font-bold text-ivory">
        {children}
      </strong>
    ) : (
      <em key={index} className="italic">
        {children}
      </em>
    );
  });
}

function renderLines(lines: readonly InlineNode[][]): ReactNode[] {
  return lines.flatMap((line, index) =>
    index === 0 ? [renderInline(line)] : [<br key={`br-${index}`} />, renderInline(line)],
  );
}

function List({ items, depth }: { items: readonly ListItemNode[]; depth: number }) {
  return (
    <ul
      className={cx(
        "flex flex-col gap-1 pl-5",
        depth === 0 ? "list-disc" : depth === 1 ? "list-[circle]" : "list-[square]",
      )}
    >
      {items.map((item, index) => (
        <li key={index}>
          {renderInline(item.children)}
          {item.sublist.length > 0 ? (
            <div className="mt-1">
              <List items={item.sublist} depth={depth + 1} />
            </div>
          ) : null}
        </li>
      ))}
    </ul>
  );
}

function Block({ block }: { block: BlockNode }) {
  if (block.type === "list") return <List items={block.items} depth={0} />;
  return <p>{renderLines(block.lines)}</p>;
}

export function FormattedText({ text, empty = null, className }: FormattedTextProps) {
  const blocks = parseFormattedText(text ?? "");
  if (blocks.length === 0) return <>{empty}</>;
  return (
    <div className={cx("flex flex-col gap-3 [overflow-wrap:anywhere]", className)}>
      {blocks.map((block, index) => (
        <Block key={index} block={block} />
      ))}
    </div>
  );
}
